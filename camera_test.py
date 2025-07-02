import subprocess
import os
import re
import time
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
    # Only crop vertical thirds
    y1 = h // 3
    y2 = h - h // 3
    cropped = image[y1:y2, :]
    return cropped, 0, y1

def decode_with_region_detection(image_path):
    try:
        image = cv2.imread(image_path)
        cropped_image, offset_x, offset_y = preprocess_for_detection(image)
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
            region = gray[y:y+h, x:x+w]
            if np.std(region) < 15:
                continue

            if 50 < w < 600 and 0.6 < aspect < 1.4:
                area = cv2.contourArea(cnt)
                if area < 800:
                    continue

                pad_x = int(w * 0.08)
                pad_y = int(h * 0.08)
                x1 = max(x - pad_x, 0)
                y1 = max(y - pad_y, 0)
                x2 = min(x + w + pad_x, gray.shape[1])
                y2 = min(y + h + pad_y, gray.shape[0])
                region = gray[y1:y2, x1:x2]
                candidates.append(region)

                # Draw rectangle in full image coordinates
                rx1 = int((x1 / gray.shape[1]) * cropped_image.shape[1]) + offset_x
                ry1 = int((y1 / gray.shape[0]) * cropped_image.shape[0]) + offset_y
                rx2 = int((x2 / gray.shape[1]) * cropped_image.shape[1]) + offset_x
                ry2 = int((y2 / gray.shape[0]) * cropped_image.shape[0]) + offset_y
                cv2.rectangle(image, (rx1, ry1), (rx2, ry2), (0, 255, 0), 2)
                print(f"→ Candidate at full (x={rx1}, y={ry1}, w={rx2 - rx1}, h={ry2 - ry1})")

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
            t0 = time.time()

            t1 = time.time()
            img_path = capture_image()
            t2 = time.time()

            if not img_path:
                print("✗ Image capture failed.\n")
                continue

            print("✓ Captured image, detecting candidates...")
            raw = decode_with_region_detection(img_path)
            t3 = time.time()

            # Full frame fallback decode (grayscale PIL)
            print("Trying full-frame fallback decode...")
            try:
                full_pil = Image.open(img_path).convert("L")
                result = decode(full_pil)
                if result:
                    print("→ Full-frame fallback:", result[0].data.decode())
            except:
                print("✗ Full-frame decode failed.")

            if not raw:
                print("✗ No valid Data Matrix detected.\n")
                print("📸 Debug saved to /tmp/debug_regions.jpg\n")
            else:
                print(f"\n✓ Data Matrix Found:\n  {repr(raw)}")
                parsed = parse_digikey_data_matrix(raw)
                if parsed:
                    print("✓ Parsed Digi-Key Info:")
                    for k, v in parsed.items():
                        print(f"  {k}: {v}")
                else:
                    print("✗ Data does not match Digi-Key format.\n")

            print(f"\n⏱️ Timing:")
            print(f"  Capture time: {(t2 - t1):.2f} sec")
            print(f"  Decode time:  {(t3 - t2):.2f} sec")
            print(f"  Total time:   {(t3 - t0):.2f} sec\n")

        except KeyboardInterrupt:
            print("\nExiting.")
            break
        except Exception as e:
            print(f"✗ Unexpected runtime error: {e}\n")

if __name__ == "__main__":
    main()
