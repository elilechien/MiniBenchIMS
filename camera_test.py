def decode_with_dmtx(image_path):
    try:
        # First attempt: plain grayscale
        img = Image.open(image_path).convert("L")
        results = decode(img)
        if results:
            return results[0].data.decode("utf-8")

        # Second attempt: contrast enhanced
        from PIL import ImageEnhance
        img = ImageEnhance.Contrast(img).enhance(2.0)
        results = decode(img)
        if results:
            return results[0].data.decode("utf-8")

        # Optional fallback: call dmtxread (if installed and fast enough)
        # output = subprocess.check_output(["dmtxread", image_path], stderr=subprocess.DEVNULL, timeout=3)
        # return output.decode("utf-8").strip()

        return None
    except Exception as e:
        print(f"✗ Decode error: {e}")
        return None
