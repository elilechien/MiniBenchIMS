import subprocess
import os
import re
import cv2
import numpy as np
from PIL import Image
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
    try:
        subprocess.run([
            "libcamera-still",
            "-o", filename,
            "--width", "1280",
            "--height", "720",
            "--timeout", "2000",
            "--autofocus-mode", "auto",
            "--lens-position", "0.0"
        ], check=True)

        if os.path.exists(filename):
            return filename
        return None
    except subprocess.CalledProcessError as e:
        print(f"✗ Camera capture failed: {e}")
        return None

def decode_with_region_detection(image_path):
    try:
        image = cv2.imread(image_path)
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        thresh = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                                       cv2.THRESH_BINARY_INV, 11, 2)

        contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        candidates = []

        for cnt in contours:
            x, y, w, h = cv2.boundingRect(cnt)
            aspect = w / float(h)
            if 20 < w < 300 and 0.85 < aspect < 1.15:
                region = gray[y:y+h, x:x+w]
                candidates.append(region)

        for region in candidates:
            pil_img = Image.fromarray(region).convert("L")
            results = decode(pil_img)
            if results:
                return results[0].data.decode("utf-8")

        return None
    except Exception as e:
        print(f"✗ Region-based decode error: {e}")
        return None

def main():
    print("DigiKey Data Matrix Scanner\nPress Enter to capture and scan...\n")

    while True:
        try:
            input("➤ Press Enter to scan...")
            img_path = capture_image()
            if not img_path:
                print("✗ Image capture failed.\n")
                continue

            print("✓ Captured image, scanning for matrix candidates...")
            raw = decode_with_region_detection(img_path)
            if not raw:
                print("✗ No valid Data Matrix detected.\n")
                continue

            print(f"\n✓ Data Matrix Found:\n  {repr(raw)}")
            parsed = parse_digikey_data_matrix(raw)
            if parsed:
                print("✓ Parsed Digi-Key Info:")
                for k, v in parsed.items():
                    print(f"  {k}: {v}")
            else:
                print("✗ Data does not match Digi-Key format.\n")
        except KeyboardInterrupt:
            print("\nExiting.")
            break
        except Exception as e:
            print(f"✗ Unexpected runtime error: {e}\n")

if __name__ == "__main__":
    main()
