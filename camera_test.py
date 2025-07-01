import cv2
from datetime import datetime
from pylibdmtx.pylibdmtx import decode
from PIL import Image
import numpy as np
import re
import subprocess
import time

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
    "-t", "0",                       # Run indefinitely
    "--width", "640",
    "--height", "480",
    "--framerate", "30",
    "--codec", "mjpeg",             # Must match v4l2loopback's accepted format
    "--output", "/dev/video10"
])

time.sleep(5)

# Start camera
cap = cv2.VideoCapture("/dev/video10")

if not cap.isOpened():
    print("Failed to open camera.")
    exit()

print("Camera stream started. Press 'q' to quit.")

try:
    while True:
        ret, frame = cap.read()
        if not ret:
            print("Frame capture failed.")
            continue

        # Convert frame to PIL format
        pil_img = Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))

        # Decode Data Matrix
        results = decode(pil_img)

        if len(results) == 1:
            raw = results[0].data.decode("utf-8")
            parsed = parse_digikey_data_matrix(raw)
            if "digi_key_pn" in parsed:
                print("DIGIKEY DATAMATRIX DETECTED:")
                print(parsed)
            else:
                print("Data Matrix found, but not parsed properly.")
        elif len(results) > 1:
            print("Multiple codes detected.")
        else:
            print("No Data Matrix found.")

        # Optional: display video (comment out if headless)
        cv2.imshow("Live Feed", frame)
        if cv2.waitKey(1) & 0xFF == ord('q'):
            break

        # Optional: throttle loop
        # time.sleep(0.5)

except KeyboardInterrupt:
    print("Stopped by user.")

finally:
    cap.release()
    cv2.destroyAllWindows()
