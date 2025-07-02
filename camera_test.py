import cv2
import re
import subprocess
import time
import numpy as np
from pyzbar.pyzbar import decode as pyzbar_decode
from pylibdmtx.pylibdmtx import decode as dmtx_decode
from datetime import datetime

def parse_digikey_data_matrix(raw: str):
    if raw.startswith("[)>06"):
        raw = raw[5:]
    fields = re.split(r'[\x1d\x1e\x04]+', raw)
    result = {}
    for field in fields:
        if field.startswith("P") and not field.startswith("1P") and not field.startswith("30P"):
            result["digi_key_pn"] = field[1:]
        elif field.startswith("1P"):
            result["mfr_pn"] = field[2:]
        elif field.startswith("Q"):
            result["qty"] = field[1:]
        elif field.startswith("1T"):
            result["lot_code"] = field[2:]
        elif field.startswith("9D"):
            result["date_code"] = field[2:]
        elif field.startswith("12Z"):
            result["mid"] = field[3:]
    return result

def quick_sharpen(gray):
    """Fast sharpening to reduce blur"""
    kernel = np.array([[-1,-1,-1], [-1,9,-1], [-1,-1,-1]], dtype=np.float32)
    return cv2.filter2D(gray, -1, kernel)

# Start video stream for continuous autofocus with preview
print("Starting libcamera video stream with preview for focus monitoring...")
cam_stream = subprocess.Popen([
    "libcamera-vid",
    "-t", "0",
    "--width", "800",
    "--height", "600",
    "--framerate", "10",
    "--codec", "mjpeg",
    "--shutter", "4000",  # Fast shutter to reduce blur
    "--gain", "1.5",
    "--awb", "auto",
    "--autofocus-mode", "continuous",  # Continuous autofocus
    "--lens-position", "0.0",  # Let autofocus work
    "--denoise", "cdn_off",
    "--preview", "0,0,400,300",  # Small preview window
    "--output", "/dev/video10"
], stderr=subprocess.DEVNULL)

print("Preview window should appear - position your camera and wait for focus...")
time.sleep(5)  # Give more time for camera to start and focus

cap = cv2.VideoCapture("/dev/video10")
cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
cap.set(cv2.CAP_PROP_FPS, 10)
cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc('M','J','P','G'))

if not cap.isOpened():
    print("Failed to open camera.")
    cam_stream.terminate()
    exit()

print("Data Matrix Scanner - Continuous Mode with Preview")
print("Press Ctrl+C to quit")
print()

frame_count = 0

def save_debug_frame(frame, filename_suffix=""):
    """Save frame for debugging"""
    filename = f"/tmp/debug_frame{filename_suffix}.jpg"
    cv2.imwrite(filename, frame)
    print(f"Debug frame saved: {filename}")
    return filename

try:
    last_scan_time = 0
    
    while True:
        # Always read frames to keep video stream flowing
        ret, frame = cap.read()
        if not ret:
            print("Failed to read frame")
            time.sleep(0.1)
            continue
        
        frame_count += 1
        current_time = time.time()
        
        # Continuous scanning with 2.5 second intervals
        if current_time - last_scan_time >= 2.5:
            print(f"Auto-scanning frame #{frame_count}...")
            
            # Process the current frame at full resolution
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            
            # Apply sharpening
            enhanced = quick_sharpen(gray)
            
            # Save debug images
            debug_original = save_debug_frame(gray, "_original")
            debug_enhanced = save_debug_frame(enhanced, "_enhanced")
            
            print(f"Processing {enhanced.shape[1]}x{enhanced.shape[0]} image at full resolution...")
            
            # Decode at full resolution
            decode_start = time.time()
            dmtx_results = dmtx_decode(enhanced, timeout=2000)
            decode_time = time.time() - decode_start
            
            if dmtx_results:
                for result in dmtx_results:
                    try:
                        raw = result.data.decode("utf-8")
                        
                        print(f"\n{'='*50}")
                        print(f"✓ DATA MATRIX FOUND! ({decode_time:.3f}s)")
                        print(f"Raw: {repr(raw)}")
                        
                        parsed = parse_digikey_data_matrix(raw)
                        if "digi_key_pn" in parsed:
                            print(f"✓ DIGIKEY PART DETECTED:")
                            for key, value in parsed.items():
                                print(f"  {key}: {value}")
                        else:
                            print(f"✗ Unknown format")
                            print(f"Parsed: {parsed}")
                        
                        print(f"{'='*50}\n")
                        break
                        
                    except UnicodeDecodeError:
                        print(f"Unicode decode error")
                        continue
            else:
                print(f"✗ No Data Matrix detected ({decode_time:.3f}s)")
            
            last_scan_time = time.time()
        
        # Small delay to prevent excessive CPU usage
        time.sleep(0.1)

except KeyboardInterrupt:
    print("\nStopped by user.")
finally:
    cap.release()
    cam_stream.terminate()
    print("Camera stream stopped.")