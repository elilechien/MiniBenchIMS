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
        return filename if os.path.exists(filename) else None
    except subprocess.CalledProcessError as e:
        print(f"✗ Camera capture failed: {e}")
        return None

def preprocess_for_detection(image):
    h, w = image.shape[:2]
    
    # Crop out outer sixths
    x1 = w // 6
    x2 = w - w // 6
    cropped = image[x1:x2, :]

    return cropped, x1  # return offset so coordinates can be mapped back if needed

def decode_with_region_detection(image_path, padding=5):
    try:
        image = cv2.imread(image_path)
        cropped_image, offset_x = preprocess_for_detection(image)
        gray = cv2.cvtColor(cropped_image, cv2.COLOR_BGR2GRAY)
        thresh = cv2.adaptiveThreshold(
            gray, 255,
            cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
            cv2.THRESH_BINARY_INV, 11, 2
        )

        contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        candidates = []

        for cnt in contours:
            x, y, w, h = cv2.boundingRect(cnt)
            aspect = w / float(h)
            if 60 < w < 400 and 0.85 < aspect < 1.15:
                area = cv2.contourArea(cnt)
                if area < 1000:
                    continue

                # Add padding (with clipping to image boundaries)
                x1 = max(x - padding, 0)
                y1 = max(y - padding, 0)
                x2 = min(x + w + padding, gray.shape[1])
                y2 = min(y + h + padding, gray.shape[0])
                region = gray[y1:y2, x1:x2]

                candidates.append(region)

                # 🟩 Draw rectangle on original image
                cv2.rectangle(image, (x1, y1), (x2, y2), (0, 255, 0), 2)
                print(f"→ Candidate at (x={x}, y={y}, w={w}, h={h})")

        cv2.imwrite("/tmp/debug_regions.jpg", image)

        for region in candidates:
            pil_img = Image.fromarray(region).convert("L")
            result = decode(pil_img)
            if result:
                return result[0].data.decode("utf-8")

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

            print("✓ Captured image, detecting candidates...")
            raw = decode_with_region_detection(img_path)
            if not raw:
                print("✗ No valid Data Matrix detected.\n")
                print("📸 Debug saved to /tmp/debug_regions.jpg\n")
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
