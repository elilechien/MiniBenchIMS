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

def detect_and_crop_dmtx_candidates(image):
    gray = image if len(image.shape) == 2 else cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    blurred = cv2.GaussianBlur(gray, (3, 3), 0)
    _, thresh = cv2.threshold(blurred, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)

    # Invert if mostly white
    if cv2.countNonZero(thresh) / (thresh.shape[0] * thresh.shape[1]) > 0.5:
        thresh = cv2.bitwise_not(thresh)

    contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    crops = []

    for i, cnt in enumerate(contours):
        x, y, w, h = cv2.boundingRect(cnt)
        if 20 < w < 500 and 0.8 < w / h < 1.2:  # Square-ish, size bound
            crop = gray[y:y+h, x:x+w]
            crops.append((crop, f"/tmp/crop_{i}.jpg"))
            cv2.imwrite(f"/tmp/crop_{i}.jpg", crop)

    return crops

def main():
    print("Starting Data Matrix scanner...")
    while True:
        input("Press Enter to capture and scan...")

        img_path = capture_image()
        if not img_path:
            print("✗ Image capture failed.")
            continue

        image = cv2.imread(img_path, cv2.IMREAD_GRAYSCALE)
        print(f"Captured image saved to {img_path}")

        crops = detect_and_crop_dmtx_candidates(image)
        print(f"Found {len(crops)} candidate regions")

        found = False
        for crop, filename in crops:
            results = decode(crop)
            if results:
                found = True
                for r in results:
                    try:
                        raw = r.data.decode("utf-8")
                        print(f"\n✓ Raw Data: {repr(raw)}")
                        parsed = parse_digikey_data_matrix(raw)
                        if parsed:
                            print("✓ Parsed Digi-Key Info:")
                            for k, v in parsed.items():
                                print(f"  {k}: {v}")
                        else:
                            print("✓ Data Matrix found, but not Digi-Key")
                    except Exception as e:
                        print(f"✗ Decode error: {e}")
                break

        if not found:
            print("✗ No valid Data Matrix found.")

if __name__ == "__main__":
    main()
