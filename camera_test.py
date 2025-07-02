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
    ], capture_output=True, stderr=subprocess.DEVNULL)
    
    if result.returncode == 0:
        frame = cv2.imread("/tmp/capture.jpg")
        return True, frame
    else:
        return False, None

print("Data Matrix Scanner - Optimized for 1.5s decode time")
print("Controls:")
print("  SPACE - Capture and scan")
print("  'c' - Continuous mode")
print("  'q' - Quit")
print()

continuous_mode = False
last_scan_time = 0

try:
    while True:
        current_time = time.time()
        should_scan = False
        
        # Check if we should scan
        if continuous_mode:
            # In continuous mode, respect the 1.5s decode time + small buffer
            if current_time - last_scan_time >= 2.0:
                should_scan = True
        else:
            # Manual mode - show live preview
            ret, frame = capture_single_frame()
            if ret:
                # Show preview with instruction
                display_frame = frame.copy()
                cv2.putText(display_frame, "Press SPACE to scan", (10, 30), 
                           cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2)
                cv2.putText(display_frame, "Press 'c' for continuous", (10, 70), 
                           cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
                cv2.imshow('Preview', display_frame)
        
        # Handle keyboard input
        key = cv2.waitKey(100) & 0xFF
        if key == ord('q'):
            break
        elif key == ord('c'):
            continuous_mode = not continuous_mode
            mode_text = "CONTINUOUS" if continuous_mode else "MANUAL"
            print(f"Switched to {mode_text} mode")
            last_scan_time = current_time - 2.0  # Allow immediate scan
        elif key == ord(' '):  # Spacebar
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
            
            # Show what we're scanning
            cv2.imshow('Scanning...', enhanced)
            cv2.waitKey(1)  # Force display update
            
            # Start decode
            print("Decoding Data Matrix...")
            decode_start = time.time()
            
            # Try different sizes for best chance of detection
            sizes_to_try = [
                ("full", enhanced),
                ("75%", cv2.resize(enhanced, None, fx=0.75, fy=0.75)),
                ("50%", cv2.resize(enhanced, None, fx=0.5, fy=0.5))
            ]
            
            found_result = False
            
            for size_name, img in sizes_to_try:
                if found_result:
                    break
                    
                print(f"  Trying {size_name} size ({img.shape[1]}x{img.shape[0]})...")
                size_start = time.time()
                
                dmtx_results = dmtx_decode(img, timeout=2000)  # 2 second timeout
                
                size_time = time.time() - size_start
                print(f"    {size_name}: {size_time:.3f}s")
                
                if dmtx_results:
                    for result in dmtx_results:
                        try:
                            raw = result.data.decode("utf-8")
                            
                            total_time = time.time() - decode_start + capture_time
                            print(f"\n{'='*50}")
                            print(f"✓ DATA MATRIX FOUND! (Total: {total_time:.3f}s)")
                            print(f"Size: {size_name}")
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
                            found_result = True
                            break
                            
                        except UnicodeDecodeError:
                            print(f"    Unicode decode error")
                            continue
                
                # If found result, break out of size loop
                if found_result:
                    break
            
            if not found_result:
                total_time = time.time() - decode_start + capture_time
                print(f"✗ No Data Matrix detected ({total_time:.3f}s)")
            
            last_scan_time = time.time()
            
            # In manual mode, show result briefly
            if not continuous_mode:
                time.sleep(1)

except KeyboardInterrupt:
    print("\nStopped by user.")
finally:
    cv2.destroyAllWindows()
    print("Scanner closed.")