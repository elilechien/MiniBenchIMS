import pandas as pd
import threading
import time
from flask import Flask, render_template
import random as r
import logging
import RPi.GPIO as GPIO

app = Flask(__name__)
csv_path = "inventory.csv"

### PIN DESCRIPTIONS
SW = 17
DT = 27
CLK = 22
button = False

### GPIO SETUP

## ROTARY ENCODER
GPIO.setmode(GPIO.BCM)
GPIO.setup(CLK, GPIO.IN, pull_up_down=GPIO.PUD_UP)
GPIO.setup(DT, GPIO.IN, pull_up_down=GPIO.PUD_UP)
GPIO.setup(SW, GPIO.IN, pull_up_down=GPIO.PUD_UP)

def button_pressed(channel):
    global button 
    button = True

GPIO.add_event_detect(SW, GPIO.FALLING, callback=button_pressed, bouncetime=300)

counter = 0
last_clk = GPIO.input(CLK)

def rotary_loop():
    while True:
        global last_clk, counter
        clk_state = GPIO.input(CLK)

        if clk_state != last_clk:
            dt_state = GPIO.input(DT)
            counter += 1 if dt_state != clk_state else -1
        last_clk = clk_state
        time.sleep(0.001)


def get_sensor_data(df):
    for i, row in df.iterrows():
        qty = row["Quantity"] + r.randint(-10, 10)
        df.at[i, "Quantity"] = max(qty, 0)
    return df

def update_inventory_loop():
    while True:
        df = pd.read_csv(csv_path)
        df["Quantity"] = df["Quantity"].astype(int)
        df = get_sensor_data(df)
        df.to_csv(csv_path, index=False)
        time.sleep(1)

def user_input_loop():
    while True:
        user_cmd = input("Enter command (Add, Rem, Update): ").strip()
        if user_cmd == "Add":
            Name = input("Component Name: ").strip()
            Quantity = int(input("Component Quantity: ").strip())
            Bin_Location = input("Bin Location: ").strip()
            Bin_location = "Bin-" + Bin_Location
            df = pd.read_csv(csv_path)

            if Bin_location in df["Location"].values:
                print("Bin already occupied. Please choose a different bin.")
            else:
                df.loc[len(df)] = [Name, Quantity, Bin_location]
                df.sort_values(by="Location", inplace=True)
                df.to_csv(csv_path, index=False)
                print("Inventory updated.")
        elif user_cmd == "Rem":

            Bin_Location = input("Bin Location: ").strip()
            Bin_location = "Bin-" + Bin_Location
            df = pd.read_csv(csv_path)

            iBin = df[df["Location"] == Bin_location].index[0]
            Name = df.at[iBin, "Name"]
            Quantity = df.at[iBin, "Quantity"]

            df.drop(iBin, inplace=True)
            df.to_csv(csv_path, index=False)
            print(f"Removed {Quantity} {Name} from {Bin_location}. Bin is now empty.")

        elif user_cmd == 'Open':
            global button, counter

            Bin_Location = input("Which Bin do you want to open? ").strip()
            Bin_location = "Bin-" + Bin_Location
            df = pd.read_csv(csv_path)

            if(Bin_location not in df["Location"].values):
                print(f"{Bin_Location} not found in Inventory.")
                continue

            iBin = df[df["Location"] == Bin_location].index[0]
            Name = df.at[iBin, "Name"]
            Quantity = df.at[iBin, "Quantity"]
            print(f"Current Coutnt ({Bin_Location}): {Quantity} of {Name}")
            
            #Rotary Encoder Inputer

            print("Enter the Inventory Adjustment Amount")
            counter = 0
            prev_counter = 0
            while(not button):
                if(counter != prev_counter):
                    print(f"Adjustment Amount: {counter}")
                    prev_counter = counter

            button = False #acknowledge the button press
            df.at[iBin, "Quantity"] -= counter
            counter = 0

            df.to_csv(csv_path, index=False)
            print("Inventory Updated.")
            print(f"New Count ({Bin_Location}): {Quantity} of {Name}")

        else:
            print("Unknown command.")

@app.route("/")
def index():
    try:
        df = pd.read_csv(csv_path)
        table_html = df.to_html(classes="table", index=False)
    except Exception as e:
        table_html = f"<p>Error loading CSV: {e}</p>"
    return render_template("index.html", table=table_html)

if __name__ == "__main__":
    log = logging.getLogger('werkzeug')
    log.setLevel(logging.ERROR)

    threading.Thread(target=update_inventory_loop, daemon=True).start()
    threading.Thread(target=rotary_loop, daemon=True).start()
    threading.Thread(target=user_input_loop, daemon=False).start()

    app.run(host="0.0.0.0", port=5005)
