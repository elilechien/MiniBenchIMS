import gpiozero as GPIO
import time

TRIG = 23  # GPIO pin for trigger
ECHO = 24  # GPIO pin for echo

GPIO.setmode(GPIO.BCM)
GPIO.setup(TRIG, GPIO.OUT)
GPIO.setup(ECHO, GPIO.IN)

def get_distance():
    GPIO.output(TRIG, True)
    time.sleep(0.00001)  # 10µs pulse
    GPIO.output(TRIG, False)

    while GPIO.input(ECHO) == 0:
        start = time.time()
    while GPIO.input(ECHO) == 1:
        end = time.time()

    duration = end - start
    distance = duration * 17150  # speed of sound / 2
    return round(distance, 2)

try:
    while True:
        print("Distance:", get_distance(), "cm")
        time.sleep(0.5)
except KeyboardInterrupt:
    GPIO.cleanup()
