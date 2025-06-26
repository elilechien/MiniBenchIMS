import pandas as pd
import threading
import time
from flask import Flask, render_template, send_file
import random as r
import logging
import tkinter as tk
from gpiozero import Button, RotaryEncoder
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

# === THREAD SYNCHRONIZATION ===
state_lock = threading.Lock()
csv_lock = threading.Lock()

# === GPIO SETUP ===
button = Button(SW, pull_up=True, bounce_time=0.1)
encoder = RotaryEncoder(CLK, DT, wrap=False, max_steps=0)

def button_pressed(channel=None):
    global current_adjustment, current_bin, current_name, current_quantity
    with state_lock:
        if current_bin is None:
            return
        local_bin = current_bin
        local_adjustment = current_adjustment

    with csv_lock:
        df = pd.read_csv(csv_path)
        iBin = df[df["Location"] == local_bin].index[0]
        df.at[iBin, "Quantity"] += local_adjustment

        if df.at[iBin, "Quantity"] <= 0:
            df.drop(iBin, inplace=True)
            df.to_csv(csv_path, index=False)
            with state_lock:
                current_bin = None
                current_name = None
                current_quantity = None
                current_adjustment = 0
        else:
            new_quantity = df.at[iBin, "Quantity"]
            df.to_csv(csv_path, index=False)
            with state_lock:
                current_quantity = new_quantity
                current_adjustment = 0

# === Add GPIO event detect ===
button.when_pressed = button_pressed

def rotary_loop():
    global current_adjustment
    last_steps = 0
    while True:
        current_steps = encoder.steps
        if current_steps != last_steps:
            with state_lock:
                if current_bin is not None:
                    # Calculate the change in steps
                    step_change = current_steps - last_steps
                    current_adjustment += step_change
            last_steps = current_steps
        time.sleep(0.001)

def update_inventory_loop():
    while True:
        with csv_lock:
            df = pd.read_csv(csv_path)
            df["Quantity"] = df["Quantity"].astype(int)
            df.to_csv(csv_path, index=False)
        time.sleep(5)

def user_input_loop():
    global current_bin, current_name, current_quantity, current_adjustment
    time.sleep(2)
    while True:
        user_cmd = input("Enter command (Add, Rem, Update, Open): ").strip()

        with csv_lock:
            df = pd.read_csv(csv_path)

        if user_cmd == "Add":
            Name = input("Component Name: ").strip()
            Quantity = int(input("Component Quantity: ").strip())
            Bin_location = "Bin-" + input("Bin Location: ").strip()

            with csv_lock:
                df = pd.read_csv(csv_path)
                if Bin_location in df["Location"].values:
                    print("Bin already occupied.")
                else:
                    df.loc[len(df)] = [Name, Quantity, Bin_location]
                    df.sort_values(by="Location", inplace=True)
                    df.to_csv(csv_path, index=False)
                    print("Inventory updated.")

        elif user_cmd == "Rem":
            Bin_location = "Bin-" + input("Bin Location: ").strip()

            with csv_lock:
                df = pd.read_csv(csv_path)
                iBin = df[df["Location"] == Bin_location].index[0]
                df.drop(iBin, inplace=True)
                df.to_csv(csv_path, index=False)
                print(f"Removed {Bin_location}.")

        elif user_cmd == "Open":
            Bin_location = "Bin-" + input("Open which bin? ").strip()

            with csv_lock:
                df = pd.read_csv(csv_path)
                if Bin_location not in df["Location"].values:
                    print(f"{Bin_location} not found.")
                    continue
                iBin = df[df["Location"] == Bin_location].index[0]

            with state_lock:
                current_bin = Bin_location
                current_name = df.at[iBin, "Name"]
                current_quantity = df.at[iBin, "Quantity"]

        elif user_cmd == "Close":
            with state_lock:
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
        table_html = df.to_html(index=False, classes="table")
        return render_template("index.html", table=table_html)
    except Exception as e:
        return f"<p>Error loading CSV: {e}</p>"

@app.route("/download")
def download_csv():
    return send_file(csv_path, as_attachment=True)

def start_flask():
    import logging
    log = logging.getLogger('werkzeug')
    log.setLevel(logging.ERROR)
    app.run(host="0.0.0.0", port=5000)

# === TKINTER GUI ===
root = tk.Tk()
root.title("MiniBench Dashboard")
root.attributes('-fullscreen', True)
root.configure(bg="#1e1e1e")

def exit_app():
    root.quit()
    root.destroy()
    os._exit(0)

exit_button = tk.Button(root, text="X", font=("Helvetica", 16, "bold"),
                       fg="#FFFFFF", bg="#FF4444",
                       command=exit_app,
                       relief="flat", bd=0,
                       width=3, height=1)
exit_button.place(relx=0.98, rely=0.02, anchor="ne")

title = tk.Label(root, text="MiniBench Inventory", font=("Helvetica", 36, "bold"),
                fg="#FFD700", bg="#1e1e1e")
title.pack(pady=40)

main_frame = tk.Frame(root, bg="#1e1e1e")
main_frame.pack(expand=True, fill="both")
main_frame.columnconfigure(0, weight=1)
main_frame.columnconfigure(1, weight=1)
main_frame.rowconfigure(0, weight=1)

left_frame = tk.Frame(main_frame, bg="#1e1e1e")
left_frame.grid(row=0, column=0, sticky="nsew", padx=60)
left_frame.rowconfigure(0, weight=1)
left_frame.rowconfigure(1, weight=1)
left_frame.rowconfigure(2, weight=1)
left_frame.rowconfigure(3, weight=1)

bin_label = tk.Label(left_frame, font=("Helvetica", 28), fg="#00BFFF", bg="#1e1e1e",
                    anchor="center", justify="center")
name_label = tk.Label(left_frame, font=("Helvetica", 28), fg="#ADFF2F", bg="#1e1e1e",
                    anchor="center", justify="center")
qty_label = tk.Label(left_frame, font=("Helvetica", 28), fg="#FF69B4", bg="#1e1e1e",
                    anchor="center", justify="center")

for label in [bin_label, name_label, qty_label]:
    label.pack(pady=20, anchor="center", fill="x", expand=True)

right_frame = tk.Frame(main_frame, bg="#1e1e1e")
right_frame.grid(row=0, column=1, sticky="nsew", padx=60)
right_frame.rowconfigure(0, weight=1)

adj_container = tk.Frame(right_frame, bg="#1e1e1e")
adj_container.grid(row=0, column=0)

adj_label_text = tk.Label(adj_container, text="Adjustment", font=("Helvetica", 28), fg="#FFFFFF", bg="#1e1e1e",
                        anchor="center", justify="center")
adj_label_text.pack(pady=(0, 5), anchor="center")

adj_value = tk.Label(adj_container, text="0", font=("Helvetica", 72, "bold"),
                    fg="#FFFFFF", bg="#1e1e1e", anchor="center", justify="center")
adj_value.pack(anchor="center")

def update_display():
    with state_lock:
        local_bin = current_bin
        local_name = current_name
        local_quantity = current_quantity
        local_adjustment = current_adjustment

    if local_bin:
        main_frame.pack(expand=True, fill="both")
        title.pack(pady=40)

        if hasattr(root, 'no_bin_label'):
            root.no_bin_label.pack_forget()

        bin_label.config(text=f"{local_bin}")
        available_width = name_label.winfo_width()
        if available_width <= 1:
            available_width = 400

        part_text = f"{local_name}"
        font_sizes = [28, 24, 20, 16, 14, 12, 10]
        fitted_text = part_text

        for font_size in font_sizes:
            test_font = ("Helvetica", font_size)
            temp_label = tk.Label(root, text=part_text, font=test_font)
            temp_label.update_idletasks()
            text_width = temp_label.winfo_reqwidth()
            temp_label.destroy()

            if text_width <= available_width - 20:
                fitted_text = part_text
                name_label.config(text=fitted_text, font=test_font)
                break
        else:
            max_chars = available_width // 8
            if len(part_text) > max_chars:
                truncated_name = local_name[:max_chars - 7] + "..."
                fitted_text = f"{truncated_name}"
            name_label.config(text=fitted_text, font=("Helvetica", 28))

        qty_label.config(text=f"Qty: {local_quantity}")
        sign = "+" if local_adjustment > 0 else ""
        adj_value.config(text=f"{sign}{local_adjustment}")
    else:
        main_frame.pack_forget()
        title.pack(pady=40)

        if not hasattr(root, 'no_bin_label'):
            root.no_bin_label = tk.Label(root, text="No bin currently open",
                                        font=("Helvetica", 48, "bold"),
                                        fg="#FFD700", bg="#1e1e1e")
            root.no_bin_label.pack(expand=True, fill="both")
        else:
            root.no_bin_label.pack(expand=True, fill="both")

    root.after(200, update_display)

# === THREADING ===
threading.Thread(target=rotary_loop, daemon=True).start()
threading.Thread(target=update_inventory_loop, daemon=True).start()
threading.Thread(target=user_input_loop, daemon=True).start()
threading.Thread(target=start_flask, daemon=True).start()

update_display()
root.mainloop()
