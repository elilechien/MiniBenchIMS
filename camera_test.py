import cv2
from datetime import datetime

# Open the camera
cap = cv2.VideoCapture(1)

if not cap.isOpened():
    print("Camera not found.")
    exit()

try:
    while True:
        ret, frame = cap.read()
        if not ret:
            print("Failed to capture.")
            continue

        # Show frame
        cv2.imshow("Live Capture", frame)

        # Save with timestamp (optional)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"frame_{timestamp}.jpg"
        cv2.imwrite(filename, frame)
        print(f"Saved {filename}")

        # Wait 2 seconds (2000ms), check for quit key
        if cv2.waitKey(2000) & 0xFF == ord('q'):
            break

except KeyboardInterrupt:
    print("Stopped by user.")

finally:
    cap.release()
    cv2.destroyAllWindows()
