import subprocess
import os
import re
from PIL import Image

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

def capture_image(filename="/tmp/frame.jpg", resized="/tmp/frame_small.jpg"):
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
            # Convert to grayscale and resize to speed up decoding
            img = Image.open(filename).convert("L")
            img = img.resize((480, 360))
            img.save(resized)
            return resized
        return None
    except subprocess.CalledProcessError as e:
        print(f"✗ Camera capture failed: {e}")
        return None

def decode_with_dmtx(image_path):
    try:
        output = subprocess.check_output(["dmtxread", image_path], stderr=subprocess.DEVNULL, timeout=10)
        decoded = output.decode("utf-8").strip()
        return decoded if decoded else None
    except subprocess.TimeoutExpired:
        print("✗ dmtxread timed out.")
        return None
    except subprocess.CalledProcessError:
        print("✗ dmtxread did not find a Data Matrix.")
        return None
    except Exception as e:
        print(f"✗ Unexpected decode error: {e}")
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

            print("✓ Captured and resized image, running dmtxread...")
            raw = decode_with_dmtx(img_path)
            if not raw:
                print("✗ No valid Data Matrix detected.\n")
                continue

            print(f"\n✓ Data Matrix Found:\n  {repr(raw)}")
            parsed = parse_digikey_data_matrix(raw)
            if parsed:
                print("✓ Parsed Digi-Key Info:")
                for k, v in parsed.items():
                    print(f"  {k}: {v}")
                # os.system("aplay /usr/share/sounds/alsa/Front_Center.wav")  # Optional: Success sound
            else:
                print("✗ Data does not match Digi-Key format.\n")
        except KeyboardInterrupt:
            print("\nExiting.")
            break
        except Exception as e:
            print(f"✗ Unexpected runtime error: {e}\n")

if __name__ == "__main__":
    main()
