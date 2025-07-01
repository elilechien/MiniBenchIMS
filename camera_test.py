import cv2
import subprocess
from datetime import datetime
import time
import os

try:
    while True:
        # Generate timestamped filename
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"frame_{timestamp}.jpg"

        # Capture using libcamera-still
        subprocess.run([
            "libcamera-still",
            "-t", "1",              # Short exposure time
            "-n",                   # No preview window
            "-o", filename
        ])

        print(f"Saved {filename}")

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
