import cv2
import re
import subprocess
import time
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

# Initialize the barcode detector
detector = cv2.barcode.BarcodeDetector()

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
        result = detector.detectAndDecode(gray)
        elapsed = time.time() - start
        print(f"Decode time: {elapsed:.3f}s")
        
        # Handle different OpenCV versions
        if len(result) == 3:
            retval, decoded_info, points = result
            decoded_type = None
        elif len(result) == 4:
            retval, decoded_info, decoded_type, points = result
        else:
            retval = False
            decoded_info = []
            points = None
        
        if retval and decoded_info is not None:
            for i, raw in enumerate(decoded_info):
                if raw:  # Make sure the decoded string is not empty
                    print(f"Raw: {repr(raw)}")
                    parsed = parse_digikey_data_matrix(raw)
                    if "digi_key_pn" in parsed:
                        print("DIGIKEY DATAMATRIX DETECTED:")
                        print(parsed)
                    
                    # Optional: Draw bounding box around detected barcode
                    if points is not None and len(points) > i:
                        pts = points[i].astype(int)
                        cv2.polylines(frame, [pts], True, (0, 255, 0), 2)
        
        # Optional: Display the frame with detected barcodes highlighted
        # cv2.imshow('Barcode Scanner', frame)
        
        if cv2.waitKey(1) & 0xFF == ord('q'):
            break

except KeyboardInterrupt:
    print("Stopped by user.")
finally:
    cap.release()
    cam_stream.terminate()
    cv2.destroyAllWindows()