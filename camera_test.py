import subprocess
import cv2
import time
import os
import re
from pylibdmtx.pylibdmtx import decode

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

def capture_image(filename="/tmp/frame.jpg"):
    subprocess.run([
    "libcamera-still",
    "-o", filename,
    "--width", "1280",
    "--height", "720",
    "--timeout", "2000",
    "--autofocus-mode", "auto",
    "--lens-position", "0.0"
    ])
    return filename if os.path.exists(filename) else None

def main():
    print("Starting minimal DigiKey Data Matrix scanner...")
    while True:
        input("Press Enter to capture and scan...")

        img_path = capture_image()
        if not img_path:
            print("Image capture failed.")
            continue

        image = cv2.imread(img_path, cv2.IMREAD_GRAYSCALE)
        results = decode(image)

        if not results:
            print("✗ No Data Matrix found.")
            continue

        for r in results:
            try:
                raw = r.data.decode("utf-8")
                print(f"✓ Raw Data: {repr(raw)}")
                parsed = parse_digikey_data_matrix(raw)
                if parsed:
                    print("✓ Parsed Digi-Key Info:")
                    for k, v in parsed.items():
                        print(f"  {k}: {v}")
                else:
                    print("✗ Not a Digi-Key code")
            except Exception as e:
                print(f"✗ Decode error: {e}")

if __name__ == "__main__":
    main()
