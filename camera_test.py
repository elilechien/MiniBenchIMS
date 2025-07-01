import cv2
import subprocess
from datetime import datetime
import time
import os
from PIL import Image
from pylibdmtx.pylibdmtx import decode
from pathlib import Path
import re

def parse_digikey_data_matrix(raw: str):
    # Remove the header
    if raw.startswith("[)>06"):
        raw = raw[5:]

    # Split on ASCII Group Separator or Record Separator
    # (\x1d = GS, \x1e = RS, \x04 = EOT)
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

try:
    while True:
        # Generate timestamped filename
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"frame.jpg"

        # Capture image
        subprocess.run(["libcamera-still", "-t", "1", "-n", "-o", filename], check=True)

        # Wait until the file is fully written
        img_path = Path(filename)
        max_wait = 2.0  # seconds
        start = time.time()

        while (not img_path.exists() or img_path.stat().st_size == 0) and (time.time() - start < max_wait):
            time.sleep(0.1)

        if img_path.exists() and img_path.stat().st_size > 0:
            img = Image.open(filename)
        else:
            print("Image file not ready or failed to save.")
            continue

        img = Image.open(filename)
        results = decode(img)

        if(len(results) == 1):
            raw = results[0].data.decode("utf-8")

            # Match known field prefixes
            result = parse_digikey_data_matrix(raw)
            if("digi_key_pn" in result):
                print('DIGIKEY DATAMATRIX DETECTED.')
                print(result)
            else:
                print("Data Matrix found, but not parsed properly.")
        else:
            print("No Data Matrix found.")

        # Load and show image using OpenCV
        img = cv2.imread(filename)
        if img is not None:
            cv2.imshow("Live Capture", img)
            if cv2.waitKey(1) & 0xFF == ord('q'):
                break
        else:
            print("Failed to load captured image.")

        # Wait 2 seconds
        time.sleep(2)

except KeyboardInterrupt:
    print("Stopped by user.")

finally:
    cv2.destroyAllWindows()