import pandas as pd
import threading
import time
from flask import Flask, render_template, send_file, request, jsonify
import tkinter as tk
from gpiozero import Button, RotaryEncoder
import os

# === OS CONFIG ===
os.environ["DISPLAY"] = ":0"
os.chdir(os.path.dirname(os.path.abspath(__file__)))

# === CSV Path ===
csv_path = "inventory.csv"

# === SHARED STATE ===
current_bin_obj = None
current_adjustment = 0

# === THREAD SYNCHRONIZATION ===
state_lock = threading.Lock()
csv_lock = threading.Lock()

# --- Bin class definition ---
class Bin:
    def __init__(self, name, quantity, location):
        self.name = name
        self.quantity = int(quantity)
        self.location = location

    def adjust_quantity(self, amount):
        self.quantity += amount

    def to_dict(self):
        return {
            'Name': self.name,
            'Quantity': self.quantity,
            'Location': self.location
        }

    @staticmethod
    def from_dict(d):
        return Bin(d['Name'], d['Quantity'], d['Location'])

# --- Helper functions for CSV <-> Bin ---
def load_bins():
    try:
        df = pd.read_csv(csv_path)
        return [Bin.from_dict(row) for row in df.to_dict(orient='records')]
    except Exception:
        return []

def save_bins(bins):
    df = pd.DataFrame([b.to_dict() for b in bins])
    df.to_csv(csv_path, index=False)

# --- Helper to find a bin by location ---
def find_bin(bins, location):
    for b in bins:
        if b.location == location:
            return b
    return None

# === ROTARY ENCODER SETUP ===
def button_pressed(channel=None):
    global current_adjustment, current_bin_obj
    with state_lock:
        if current_bin_obj is None:
            return
        local_bin = current_bin_obj.location
        local_adjustment = current_adjustment
    with csv_lock:
        bins = load_bins()
        b = find_bin(bins, local_bin)
        if not b:
            return
        b.adjust_quantity(local_adjustment)
        if b.quantity <= 0:
            bins.remove(b)
            save_bins(bins)
            with state_lock:
                current_bin_obj = None
                current_adjustment = 0
        else:
            save_bins(bins)
            with state_lock:
                current_bin_obj = b
                current_adjustment = 0

def rotary_cw():
    global current_adjustment
    with state_lock:
        if current_bin_obj is not None:
            current_adjustment += 1

def rotary_ccw():
    global current_adjustment
    with state_lock:
        if current_bin_obj is not None:
            current_adjustment -= 1

# define RE GPIO pins and event detects
SW,DT,CLK = 17, 27, 22
button = Button(SW, pull_up=True, bounce_time=0.1)
encoder = RotaryEncoder(CLK, DT,wrap=False, max_steps=0)
button.when_pressed = button_pressed
encoder.when_rotated_clockwise = rotary_cw
encoder.when_rotated_counter_clockwise = rotary_ccw

def user_input_loop():
    global current_bin_obj, current_adjustment
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
                global current_bin_obj
                current_bin_obj = df.iloc[iBin].to_dict()

        elif user_cmd == "Close":
            with state_lock:
                current_bin_obj = None
                current_adjustment = 0

        else:
            print("Unknown command.")

# === FLASK SERVER FOR INVENTORY ===
app = Flask(__name__)

def get_current_status():
    with state_lock:
        if current_bin_obj:
            return {
                'current_bin': current_bin_obj.location,
                'current_name': current_bin_obj.name,
                'current_quantity': int(current_bin_obj.quantity)
            }
        else:
            return {
                'current_bin': None,
                'current_name': None,
                'current_quantity': None
            }

@app.route("/")
def index():
    try:
        df = pd.read_csv(csv_path)
        table_html = df.to_html(index=False, classes="table")
        return render_template("index.html", table=table_html, **get_current_status())
    except Exception as e:
        return f"<p>Error loading CSV: {e}</p>"

@app.route("/add", methods=['GET', 'POST'])
def add_item():
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        quantity = request.form.get('quantity', '').strip()
        bin_location = request.form.get('bin_location', '').strip()
        
        if name and quantity and bin_location:
            try:
                quantity = int(quantity)
                bin_location = f"Bin-{bin_location}"
                with csv_lock:
                    bins = load_bins()
                    if find_bin(bins, bin_location):
                        return render_template("index.html", 
                                             table=pd.DataFrame([b.to_dict() for b in bins]).to_html(index=False, classes="table"),
                                             error="Bin already occupied.",
                                             **get_current_status())
                    new_bin = Bin(name, quantity, bin_location)
                    bins.append(new_bin)
                    bins.sort(key=lambda b: b.location)
                    save_bins(bins)
                    with state_lock:
                        global current_bin_obj
                        current_bin_obj = new_bin
                    return render_template("index.html", 
                                         table=pd.DataFrame([b.to_dict() for b in bins]).to_html(index=False, classes="table"),
                                         success="Inventory updated successfully.",
                                         **get_current_status())
            except ValueError:
                return render_template("index.html", 
                                     table=pd.DataFrame([b.to_dict() for b in load_bins()]).to_html(index=False, classes="table"),
                                     error="Invalid quantity. Please enter a number.",
                                     **get_current_status())
        else:
            return render_template("index.html", 
                                 table=pd.DataFrame([b.to_dict() for b in load_bins()]).to_html(index=False, classes="table"),
                                 error="All fields are required.",
                                 **get_current_status())
    
    return render_template("index.html", 
                         table=pd.DataFrame([b.to_dict() for b in load_bins()]).to_html(index=False, classes="table"),
                         **get_current_status())

@app.route("/remove", methods=['GET', 'POST'])
def remove_item():
    if request.method == 'POST':
        bin_location = request.form.get('bin_location', '').strip()
        if bin_location:
            bin_location = f"Bin-{bin_location}"
            with csv_lock:
                bins = load_bins()
                b = find_bin(bins, bin_location)
                if b:
                    bins.remove(b)
                    save_bins(bins)
                    return render_template("index.html", 
                                         table=pd.DataFrame([b.to_dict() for b in bins]).to_html(index=False, classes="table"),
                                         success=f"Removed {bin_location}.",
                                         **get_current_status())
                else:
                    return render_template("index.html", 
                                         table=pd.DataFrame([b.to_dict() for b in bins]).to_html(index=False, classes="table"),
                                         error=f"{bin_location} not found.",
                                         **get_current_status())
        else:
            return render_template("index.html", 
                                 table=pd.DataFrame([b.to_dict() for b in load_bins()]).to_html(index=False, classes="table"),
                                 error="Bin location is required.",
                                 **get_current_status())
    return render_template("index.html", 
                         table=pd.DataFrame([b.to_dict() for b in load_bins()]).to_html(index=False, classes="table"),
                         **get_current_status())

@app.route("/open", methods=['GET', 'POST'])
def open_bin():
    if request.method == 'POST':
        bin_location = request.form.get('bin_location', '').strip()
        if bin_location:
            bin_location = f"Bin-{bin_location}"
            with csv_lock:
                bins = load_bins()
                b = find_bin(bins, bin_location)
                if b:
                    with state_lock:
                        global current_bin_obj
                        current_bin_obj = b
                    return render_template("index.html", 
                                         table=pd.DataFrame([b.to_dict() for b in bins]).to_html(index=False, classes="table"),
                                         success=f"Opened {bin_location} - {b.name} (Qty: {b.quantity})",
                                         **get_current_status())
                else:
                    return render_template("index.html", 
                                         table=pd.DataFrame([b.to_dict() for b in bins]).to_html(index=False, classes="table"),
                                         error=f"{bin_location} not found.",
                                         **get_current_status())
        else:
            return render_template("index.html", 
                                 table=pd.DataFrame([b.to_dict() for b in load_bins()]).to_html(index=False, classes="table"),
                                 error="Bin location is required.",
                                 **get_current_status())
    return render_template("index.html", 
                         table=pd.DataFrame([b.to_dict() for b in load_bins()]).to_html(index=False, classes="table"),
                         **get_current_status())

@app.route("/close", methods=['POST'])
def close_bin():
    with state_lock:
        global current_bin_obj, current_adjustment
        current_bin_obj = None
        current_adjustment = 0
    bins = load_bins()
    return render_template("index.html", 
                         table=pd.DataFrame([b.to_dict() for b in bins]).to_html(index=False, classes="table"),
                         success="Bin closed.",
                         **get_current_status())

@app.route("/status")
def get_status():
    with state_lock:
        status = {
            'current_bin': current_bin_obj.location if current_bin_obj else None,
            'current_name': current_bin_obj.name if current_bin_obj else None,
            'current_quantity': int(current_bin_obj.quantity) if current_bin_obj else None
        }
    return jsonify(status)

@app.route("/apply-adjustment", methods=['POST'])
def apply_adjustment():
    global current_bin_obj
    if not request.is_json:
        return jsonify({'success': False, 'error': 'Invalid request format'})
    data = request.get_json()
    adjustment = data.get('adjustment', 0)
    with state_lock:
        if current_bin_obj is None:
            return jsonify({'success': False, 'error': 'No bin currently open'})
        local_bin = current_bin_obj.location
    with csv_lock:
        bins = load_bins()
        b = find_bin(bins, local_bin)
        if not b:
            return jsonify({'success': False, 'error': 'Bin not found'})
        b.adjust_quantity(adjustment)
        if b.quantity <= 0:
            bins.remove(b)
            save_bins(bins)
            with state_lock:
                current_bin_obj = None
            return jsonify({'success': True, 'message': f'Removed {local_bin} - quantity was 0 or less'})
        else:
            save_bins(bins)
            with state_lock:
                current_bin_obj = b
            return jsonify({'success': True, 'message': f'Updated {local_bin} quantity to {b.quantity}'})

@app.route("/download")
def download_csv():
    return send_file(csv_path, as_attachment=True)

def start_flask():
    import logging
    log = logging.getLogger('werkzeug')
    log.setLevel(logging.ERROR)
    app.run(host="0.0.0.0", port=5000)

def start_tkinter_gui():
    import tkinter as tk
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
            local_bin = current_bin_obj.location if current_bin_obj else None
            local_name = current_bin_obj.name if current_bin_obj else None
            local_quantity = current_bin_obj.quantity if current_bin_obj else None
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
            adj_label_text.config(text="Adjustment")
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

    update_display()
    root.mainloop()

# === THREADING ===
threading.Thread(target=user_input_loop, daemon=True).start()
threading.Thread(target=start_flask, daemon=True).start()
start_tkinter_gui()
