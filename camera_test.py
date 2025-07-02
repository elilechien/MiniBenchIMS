import subprocess
import os
import re

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

def decode_with_dmtx(image_path):
    try:
        output = subprocess.check_output(["dmtxread", image_path], stderr=subprocess.DEVNULL, timeout=2)
        return output.decode("utf-8").strip()
    except subprocess.CalledProcessError:
        return None
    except subprocess.TimeoutExpired:
        return None

def main():
    print("DigiKey Data Matrix Scanner\nPress Enter to capture and scan...\n")

    while True:
        input("➤ Press Enter to scan...")
        img_path = capture_image()
        if not img_path:
            print("✗ Image capture failed.")
            continue

        print("✓ Captured image, running dmtxread...")
        raw = decode_with_dmtx(img_path)
        if not raw:
            print("✗ No Data Matrix found.\n")
            continue

        print(f"\n✓ Data Matrix Found: {repr(raw)}")
        parsed = parse_digikey_data_matrix(raw)
        if parsed:
            print("✓ Parsed Digi-Key Info:")
            for k, v in parsed.items():
                print(f"  {k}: {v}")
        else:
            print("✗ Not a Digi-Key format.\n")

if __name__ == "__main__":
    main()
