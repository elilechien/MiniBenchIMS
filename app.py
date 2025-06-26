import pandas as pd
import threading
import time
import tkinter as tk
import RPi.GPIO as GPIO
from flask import Flask
import os
os.environ["DISPLAY"] = ":0"


# === CSV Path ===
csv_path = "inventory.csv"

# === GPIO PINS ===
SW = 17
DT = 27
CLK = 22

# === SHARED STATE ===
current_bin = None
current_name = None
current_quantity = None
current_adjustment = 0

# === GPIO SETUP ===
GPIO.setmode(GPIO.BCM)
GPIO.setup(CLK, GPIO.IN, pull_up_down=GPIO.PUD_UP)
GPIO.setup(DT, GPIO.IN, pull_up_down=GPIO.PUD_UP)
GPIO.setup(SW, GPIO.IN, pull_up_down=GPIO.PUD_UP)

last_clk = GPIO.input(CLK)

def button_pressed(channel):
    global current_adjustment, current_bin, current_name, current_quantity
    if current_bin is None:
        return
    df = pd.read_csv(csv_path)
    iBin = df[df["Location"] == current_bin].index[0]
    df.at[iBin, "Quantity"] += current_adjustment

    if(df.at[iBin, "Quantity"] <= 0):
        #remove the bin from the csv
        df.drop(iBin, inplace=True)
        df.to_csv(csv_path, index=False)
        current_bin = None
        current_name = None
        current_quantity = None
        current_adjustment = 0
    else:
        current_quantity = df.at[iBin, "Quantity"]
        df.to_csv(csv_path, index=False)
        current_adjustment = 0

GPIO.add_event_detect(SW, GPIO.FALLING, callback=button_pressed, bouncetime=300)

def rotary_loop():
    global current_adjustment, last_clk
    while True:
        clk_state = GPIO.input(CLK)
        dt_state = GPIO.input(DT)
        if clk_state != last_clk and current_bin is not None:
            current_adjustment += 1 if dt_state != clk_state else -1
        last_clk = clk_state
        time.sleep(0.001)

def update_inventory_loop():
    while True:
        df = pd.read_csv(csv_path)
        df["Quantity"] = df["Quantity"].astype(int)
        df.to_csv(csv_path, index=False)
        time.sleep(5)

def user_input_loop():
    global current_bin, current_name, current_quantity, current_adjustment
    while True:
        user_cmd = input("Enter command (Add, Rem, Update, Open): ").strip()
        df = pd.read_csv(csv_path)

        if user_cmd == "Add":
            Name = input("Component Name: ").strip()
            Quantity = int(input("Component Quantity: ").strip())
            Bin_location = "Bin-" + input("Bin Location: ").strip()
            if Bin_location in df["Location"].values:
                print("Bin already occupied.")
            else:
                df.loc[len(df)] = [Name, Quantity, Bin_location]
                df.sort_values(by="Location", inplace=True)
                df.to_csv(csv_path, index=False)
                print("Inventory updated.")

        elif user_cmd == "Rem":
            Bin_location = "Bin-" + input("Bin Location: ").strip()
            iBin = df[df["Location"] == Bin_location].index[0]
            df.drop(iBin, inplace=True)
            df.to_csv(csv_path, index=False)
            print(f"Removed {Bin_location}.")

        elif user_cmd == "Open":
            Bin_location = "Bin-" + input("Open which bin? ").strip()
            if Bin_location not in df["Location"].values:
                print(f"{Bin_location} not found.")
                continue
            iBin = df[df["Location"] == Bin_location].index[0]
            current_bin = Bin_location
            current_name = df.at[iBin, "Name"]
            current_quantity = df.at[iBin, "Quantity"]

        elif user_cmd == "Close":
            current_bin = None
            current_name = None
            current_quantity = None
            current_adjustment = 0

        else:
            print("Unknown command.")

# === FLASK SERVER FOR INVENTORY ===
app = Flask(__name__)

@app.route("/")
def index():
    try:
        df = pd.read_csv(csv_path)
        return df.to_html(index=False, classes="table")
    except Exception as e:
        return f"<p>Error loading CSV: {e}</p>"

def start_flask():
    app.run(host="0.0.0.0", port=5005)

# === TKINTER GUI ===
root = tk.Tk()
root.title("MiniBench Dashboard")
root.attributes('-fullscreen', True)
root.configure(bg="#1e1e1e")

# Top title
title = tk.Label(root, text="MiniBench Inventory", font=("Helvetica", 36, "bold"),
                 fg="#FFD700", bg="#1e1e1e")
title.pack(pady=40)

# Main container frame
main_frame = tk.Frame(root, bg="#1e1e1e")
main_frame.pack(expand=True)

# === LEFT COLUMN ===
left_frame = tk.Frame(main_frame, bg="#1e1e1e")
left_frame.pack(side="left", padx=60)

bin_label = tk.Label(left_frame, font=("Helvetica", 28), fg="#00BFFF", bg="#1e1e1e")
name_label = tk.Label(left_frame, font=("Helvetica", 28), fg="#ADFF2F", bg="#1e1e1e")
qty_label = tk.Label(left_frame, font=("Helvetica", 28), fg="#FF69B4", bg="#1e1e1e")

for label in [bin_label, name_label, qty_label]:
    label.pack(pady=20, anchor="w")

# === RIGHT COLUMN ===
right_frame = tk.Frame(main_frame, bg="#1e1e1e")
right_frame.pack(side="right", padx=60)

adj_label_text = tk.Label(right_frame, text="Adjustment", font=("Helvetica", 28), fg="#FFFFFF", bg="#1e1e1e")
adj_label_text.pack(pady=(0, 20))

adj_value = tk.Label(right_frame, text="0", font=("Helvetica", 72, "bold"), fg="#FFFFFF", bg="#1e1e1e")
adj_value.pack()

# === Update display loop ===
def update_display():
    if current_bin:
        bin_label.config(text=f"Bin: {current_bin}")
        name_label.config(text=f"Part: {current_name}")
        qty_label.config(text=f"Qty: {current_quantity}")
    else:
        bin_label.config(text="No bin currently open")
        name_label.config(text="")
        qty_label.config(text="")

    # Show + for positive counter
    sign = "+" if current_adjustment > 0 else ""
    adj_value.config(text=f"{sign}{current_adjustment}")
    root.after(200, update_display)

# === THREADING ===
threading.Thread(target=rotary_loop, daemon=True).start()
threading.Thread(target=update_inventory_loop, daemon=True).start()
threading.Thread(target=user_input_loop, daemon=True).start()
threading.Thread(target=start_flask, daemon=True).start()

update_display()
root.mainloop()
