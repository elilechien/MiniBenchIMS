import cv2
import re
import subprocess
import time
from pyzbar.pyzbar import decode
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

# Start libcamera-vid to stream to v4l2loopback
cam_stream = subprocess.Popen([
    "libcamera-vid",
    "-t", "0",
    "--width", "640",
    "--height", "480",
    "--framerate", "5",
    "--codec", "mjpeg",
    "--output", "/dev/video10"
])

time.sleep(3)

cap = cv2.VideoCapture("/dev/video10")
cap.set(cv2.CAP_PROP_BUFFERSIZE, 2)

print("Resolution:", cap.get(cv2.CAP_PROP_FRAME_WIDTH), "x", cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

if not cap.isOpened():
    print("Failed to open camera.")
    exit()

try:
    while True:
        ret, frame = cap.read()
        if not ret:
            print("Frame capture failed.")
            time.sleep(1)
            continue
        
        frame = cv2.cvtColor(frame, cv2.COLOR_BGRA2BGR)
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        
        start = time.time()
        results = decode(gray)
        elapsed = time.time() - start
        print(f"Decode time: {elapsed:.3f}s")
        
        if results:
            for result in results:
                raw = result.data.decode("utf-8")
                print(f"\n=== BARCODE DETECTED ===")
                print(f"Type: {result.type}")
                print(f"Raw data: {repr(raw)}")
                print(f"Raw bytes: {result.data}")
                
                # Show each character with its hex value for debugging
                print("Character breakdown:")
                for i, char in enumerate(raw):
                    print(f"  [{i:2d}]: '{char}' (0x{ord(char):02x})")
                
                parsed = parse_digikey_data_matrix(raw)
                print(f"Parsed fields: {parsed}")
                
                if "digi_key_pn" in parsed:
                    print("✓ DIGIKEY DATAMATRIX DETECTED:")
                    print(parsed)
                else:
                    print("✗ Not recognized as Digikey format")
                print("=" * 30)
                
                # Add delay to avoid spam
                time.sleep(2)
        
        if cv2.waitKey(1) & 0xFF == ord('q'):
            break

except KeyboardInterrupt:
    print("Stopped by user.")
finally:
    cap.release()
    cam_stream.terminate()
    cv2.destroyAllWindows()