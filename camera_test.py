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

def capture_single_frame():
    """Optimized single frame capture"""
    result = subprocess.run([
        "libcamera-still",
        "--immediate",
        "--width", "800",  # Good balance for detection
        "--height", "600", 
        "--encoding", "jpg",
        "--quality", "90",
        "--shutter", "4000",  # Fast enough to avoid blur
        "--gain", "1.5",
        "--awb", "auto",
        "--denoise", "cdn_off",  # Keep sharp
        "--output", "/tmp/capture.jpg"
    ], stderr=subprocess.DEVNULL)
    
    if result.returncode == 0:
        frame = cv2.imread("/tmp/capture.jpg")
        return True, frame
    else:
        return False, None

print("Data Matrix Scanner - SSH/Headless Mode")
print("Controls:")
print("  ENTER - Capture and scan")
print("  'c' + ENTER - Toggle continuous mode")
print("  'q' + ENTER - Quit")
print()

continuous_mode = False
last_scan_time = 0

def get_user_input():
    """Non-blocking input check"""
    import select
    import sys
    
    if select.select([sys.stdin], [], [], 0) == ([sys.stdin], [], []):
        return sys.stdin.readline().strip()
    return None

try:
    while True:
        current_time = time.time()
        should_scan = False
        
        # Check if we should scan
        if continuous_mode:
            # In continuous mode, respect the 1.5s decode time + small buffer
            if current_time - last_scan_time >= 2.0:
                should_scan = True
                print("Auto-scanning...")
        else:
            # Manual mode - wait for input
            print("Ready to scan - press ENTER...")
            user_input = input().strip()
            
            if user_input == 'q':
                break
            elif user_input == 'c':
                continuous_mode = not continuous_mode
                mode_text = "CONTINUOUS" if continuous_mode else "MANUAL"
                print(f"Switched to {mode_text} mode")
                last_scan_time = current_time - 2.0  # Allow immediate scan
                continue
            else:  # Enter or any other input
                should_scan = True
        
        if should_scan:
            print("Capturing...")
            capture_start = time.time()
            
            # Capture frame
            ret, frame = capture_single_frame()
            if not ret:
                print("Capture failed!")
                continue
            
            capture_time = time.time() - capture_start
            print(f"Capture: {capture_time:.3f}s")
            
            # Process image
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            
            # Apply sharpening to reduce blur
            enhanced = quick_sharpen(gray)
            
            # Save debug image (since we can't display it)
            cv2.imwrite('/tmp/debug_enhanced.jpg', enhanced)
            print(f"Debug image saved: /tmp/debug_enhanced.jpg ({enhanced.shape[1]}x{enhanced.shape[0]})")
            
            # Start decode
            print("Decoding Data Matrix...")
            decode_start = time.time()
            
            # Use 50% size for speed
            small_enhanced = cv2.resize(enhanced, None, fx=0.5, fy=0.5)
            print(f"  Processing at 50% size ({small_enhanced.shape[1]}x{small_enhanced.shape[0]})...")
            
            dmtx_results = dmtx_decode(small_enhanced, timeout=2000)  # 2 second timeout
            
            decode_time = time.time() - decode_start
            total_time = decode_time + capture_time
            
            if dmtx_results:
                for result in dmtx_results:
                    try:
                        raw = result.data.decode("utf-8")
                        
                        print(f"\n{'='*50}")
                        print(f"✓ DATA MATRIX FOUND! (Total: {total_time:.3f}s)")
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
                print(f"✗ No Data Matrix detected ({total_time:.3f}s)")
            
            last_scan_time = time.time()

except KeyboardInterrupt:
    print("\nStopped by user.")
finally:
    print("Scanner closed.")