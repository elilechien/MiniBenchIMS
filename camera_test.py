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

# Start video stream for continuous autofocus
print("Starting libcamera video stream for proper focus...")
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
    "--output", "/dev/video10"
], stderr=subprocess.DEVNULL)

time.sleep(3)  # Give time for camera to start and focus

cap = cv2.VideoCapture("/dev/video10")
cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
cap.set(cv2.CAP_PROP_FPS, 10)
cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc('M','J','P','G'))

if not cap.isOpened():
    print("Failed to open camera.")
    cam_stream.terminate()
    exit()

print("Data Matrix Scanner - SSH Mode with Video Stream")
print("Controls:")
print("  ENTER - Capture and scan current frame")
print("  'c' + ENTER - Toggle continuous mode")
print("  'q' + ENTER - Quit")
print()

continuous_mode = False
last_scan_time = 0
frame_count = 0

def save_debug_frame(frame, filename_suffix=""):
    """Save frame for debugging"""
    filename = f"/tmp/debug_frame{filename_suffix}.jpg"
    cv2.imwrite(filename, frame)
    print(f"Debug frame saved: {filename}")
    return filename

try:
    while True:
        # Always read frames to keep video stream flowing
        ret, frame = cap.read()
        if not ret:
            print("Failed to read frame")
            time.sleep(0.1)
            continue
        
        frame_count += 1
        current_time = time.time()
        should_scan = False
        
        # Save occasional debug frames to show focus quality
        if frame_count % 50 == 0:  # Every 50 frames
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            save_debug_frame(gray, "_focus_check")
            print(f"Focus check frame saved (frame #{frame_count})")
        
        # Check if we should scan
        if continuous_mode:
            # In continuous mode, respect decode time + buffer
            if current_time - last_scan_time >= 2.5:  # Bit more buffer for video
                should_scan = True
                print("Auto-scanning current frame...")
        else:
            # Manual mode - wait for input
            print("Frame ready - press ENTER to scan...")
            user_input = input().strip()
            
            if user_input == 'q':
                break
            elif user_input == 'c':
                continuous_mode = not continuous_mode
                mode_text = "CONTINUOUS" if continuous_mode else "MANUAL"
                print(f"Switched to {mode_text} mode")
                last_scan_time = current_time - 3.0  # Allow immediate scan
                continue
            else:  # Enter or any other input
                should_scan = True
        
        if should_scan:
            print("Processing current frame...")
            
            # Process the current frame
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            
            # Apply sharpening
            enhanced = quick_sharpen(gray)
            
            # Use 50% size for faster detection
            small_enhanced = cv2.resize(enhanced, None, fx=0.5, fy=0.5)
            
            # Save debug images
            debug_original = save_debug_frame(gray, "_original")
            debug_enhanced = save_debug_frame(enhanced, "_enhanced")
            debug_small = save_debug_frame(small_enhanced, "_small")
            
            print(f"Processing {small_enhanced.shape[1]}x{small_enhanced.shape[0]} image...")
            
            # Decode
            decode_start = time.time()
            dmtx_results = dmtx_decode(small_enhanced, timeout=2000)
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

except KeyboardInterrupt:
    print("\nStopped by user.")
finally:
    cap.release()
    cam_stream.terminate()
    print("Camera stream stopped.")