import cv2
import re
import subprocess
import time
import numpy as np
from pyzbar.pyzbar import decode as pyzbar_decode
from pylibdmtx.pylibdmtx import decode as dmtx_decode
from datetime import datetime
import os
import tempfile

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

def find_camera_device():
    """Find available camera devices"""
    print("Searching for camera devices...")
    
    # Try common camera indices
    for i in range(5):
        cap = cv2.VideoCapture(i)
        if cap.isOpened():
            print(f"Found camera at index {i}")
            cap.release()
            return i
    
    print("No camera found with standard indices, trying libcamera approach...")
    return None

def capture_with_libcamera():
    """Capture a single image using libcamera-still"""
    temp_file = tempfile.mktemp(suffix='.jpg')
    
    try:
        # Capture a single high-quality image
        result = subprocess.run([
            "libcamera-still",
            "-o", temp_file,
            "--width", "1920",
            "--height", "1080",
            "--timeout", "2000",  # 2 second timeout
            "--shutter", "20000",  # 20ms exposure
            "--gain", "4.0",
            "--awb", "auto",
            "--autofocus-mode", "auto",
            "--lens-position", "0.0",
            "--denoise", "cdn_off",
            "--immediate"  # Don't show preview
        ], capture_output=True, text=True, timeout=10)
        
        if result.returncode == 0 and os.path.exists(temp_file):
            # Read the captured image
            image = cv2.imread(temp_file)
            os.unlink(temp_file)  # Clean up temp file
            return image
        else:
            print(f"libcamera-still failed: {result.stderr}")
            if os.path.exists(temp_file):
                os.unlink(temp_file)
            return None
            
    except subprocess.TimeoutExpired:
        print("libcamera-still timeout")
        if os.path.exists(temp_file):
            os.unlink(temp_file)
        return None
    except Exception as e:
        print(f"Error with libcamera-still: {e}")
        if os.path.exists(temp_file):
            os.unlink(temp_file)
        return None

def save_debug_frame(frame, filename_suffix=""):
    """Save frame for debugging"""
    filename = f"/tmp/debug_frame{filename_suffix}.jpg"
    cv2.imwrite(filename, frame)
    print(f"Debug frame saved: {filename}")
    return filename

def main():
    print("Data Matrix Scanner - Starting...")
    
    # First, try to find a USB camera
    camera_index = find_camera_device()
    
    if camera_index is not None:
        print(f"Using USB camera at index {camera_index}")
        use_libcamera = False
        
        cap = cv2.VideoCapture(camera_index)
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1920)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 1080)
        cap.set(cv2.CAP_PROP_FPS, 10)
        
        if not cap.isOpened():
            print("Failed to open USB camera, falling back to libcamera")
            use_libcamera = True
    else:
        print("No USB camera found, using libcamera")
        use_libcamera = True
    
    if use_libcamera:
        # Test libcamera
        test_image = capture_with_libcamera()
        if test_image is None:
            print("ERROR: libcamera-still not working. Please check:")
            print("1. Camera is connected")
            print("2. libcamera-apps are installed")
            print("3. Camera permissions are correct")
            return
        print("libcamera working, using capture mode")
    
    print("\nData Matrix Scanner - Ready!")
    print("Press Ctrl+C to quit")
    if use_libcamera:
        print("Press Enter to capture and scan...")
    print()

    frame_count = 0
    last_scan_time = 0

    try:
        while True:
            frame = None
            
            if use_libcamera:
                # Wait for user input or auto-capture every 3 seconds
                current_time = time.time()
                if current_time - last_scan_time >= 3.0:
                    print(f"Auto-capturing frame #{frame_count + 1}...")
                    frame = capture_with_libcamera()
                    last_scan_time = current_time
                else:
                    # Check for user input (non-blocking)
                    import select
                    import sys
                    if select.select([sys.stdin], [], [], 0.1)[0]:
                        input()  # Consume the input
                        print(f"Manual capture #{frame_count + 1}...")
                        frame = capture_with_libcamera()
                        last_scan_time = time.time()
            else:
                # USB camera continuous mode
                ret, frame = cap.read()
                if not ret:
                    print("Failed to read frame from USB camera")
                    time.sleep(0.1)
                    continue
                
                current_time = time.time()
                if current_time - last_scan_time < 2.5:
                    time.sleep(0.1)
                    continue
                
                print(f"Processing frame #{frame_count + 1}...")
                last_scan_time = current_time
            
            if frame is None:
                continue
                
            frame_count += 1
            
            # Process the frame
            if len(frame.shape) == 3:
                gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            else:
                gray = frame
            
            # Save debug image
            debug_original = save_debug_frame(gray, f"_{frame_count}_original")
            
            print(f"Scanning {gray.shape[1]}x{gray.shape[0]} image...")
            
            # Decode Data Matrix
            decode_start = time.time()
            dmtx_results = dmtx_decode(gray, timeout=3000)
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
                
                # Try QR code as backup
                qr_results = pyzbar_decode(gray)
                if qr_results:
                    print("Found QR code instead:")
                    for result in qr_results:
                        try:
                            data = result.data.decode("utf-8")
                            print(f"QR Data: {data}")
                        except:
                            print(f"QR Data (bytes): {result.data}")

    except KeyboardInterrupt:
        print("\nStopped by user.")
    finally:
        if not use_libcamera and 'cap' in locals():
            cap.release()
        print("Scanner stopped.")

if __name__ == "__main__":
    main()