import subprocess
import cv2
import os
import time
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

def find_candidates(image):
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    binary = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                                   cv2.THRESH_BINARY_INV, 11, 2)
    
    num_labels, labels, stats, _ = cv2.connectedComponentsWithStats(binary)
    candidates = []
    
    for i in range(1, num_labels):  # skip background
        x, y, w, h, area = stats[i]
        aspect = w / h
        if 20 < w < 400 and 0.8 < aspect < 1.2:  # roughly square
            candidates.append(image[y:y+h, x:x+w])
            cv2.rectangle(image, (x, y), (x+w, y+h), (0, 255, 0), 2)

    cv2.imwrite("/tmp/debug_bboxes.jpg", image)
    return candidates

def main():
    print("DigiKey Data Matrix Scanner\nPress Enter to capture and scan...\n")
    
    while True:
        input("➤ Press Enter to scan...")
        img_path = capture_image()
        if not img_path:
            print("✗ Image capture failed.")
            continue

        image = cv2.imread(img_path)
        candidates = find_candidates(image)
        print(f"Found {len(candidates)} candidate region(s).")

        found = False
        for i, region in enumerate(candidates):
            gray = cv2.cvtColor(region, cv2.COLOR_BGR2GRAY)
            result = decode(gray)
            if not result:
                continue
            try:
                raw = result[0].data.decode("utf-8")
                print(f"\n✓ Data Matrix Found: {repr(raw)}")
                parsed = parse_digikey_data_matrix(raw)
                if parsed:
                    print("✓ Parsed Digi-Key Info:")
                    for k, v in parsed.items():
                        print(f"  {k}: {v}")
                else:
                    print("✗ Not a Digi-Key format.")
                found = True
                break
            except Exception as e:
                print(f"✗ Decode error: {e}")

        if not found:
            print("✗ No valid Data Matrix detected.\n")

if __name__ == "__main__":
    main()
