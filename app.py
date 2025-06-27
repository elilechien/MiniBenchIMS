import pandas as pd
import threading
import time
from flask import Flask, render_template, send_file, request, jsonify
import tkinter as tk
from tkinter import messagebox
from gpiozero import Button, RotaryEncoder
import os
import subprocess
import queue

# === OS CONFIG ===
os.environ["DISPLAY"] = ":0"
os.chdir(os.path.dirname(os.path.abspath(__file__)))

# === CSV Path ===
csv_path = "inventory.csv"

# === SHARED STATE ===
current_bin_obj = None

# === THREAD SYNCHRONIZATION ===
state_lock = threading.Lock()
csv_lock = threading.Lock()

# === GLOBAL SELECTION STATE ===
valid_rows = ['A', 'B', 'C', 'D', 'E', 'F', 'G', 'H']
valid_columns = [1, 2, 3, 4, 5, 6, 7, 8]
selected_row_index = 0
selected_column_index = 0
selection_mode = "row"  # "row" or "column"

# === THREAD COMMUNICATION ===
gui_event_queue = queue.Queue()

# --- Bin class definition ---
class Bin:
    def __init__(self, name, quantity, location):
        self.name = name
        self.quantity = int(quantity)
        self.location = location
        self.adjustment = 0  # Store pending adjustment for this bin

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
        # Handle NaN values from CSV
        name = d['Name']
        if pd.isna(name):
            name = ""
        return Bin(name, d['Quantity'], d['Location'])

# --- Helper functions for CSV <-> Bin ---
def load_bins():
    try:
        df = pd.read_csv(csv_path)
        return [Bin.from_dict(row) for row in df.to_dict(orient='records')]
    except Exception:
        return []

def save_bins(bins):
    try:
        df = pd.DataFrame([b.to_dict() for b in bins])
        df.to_csv(csv_path, index=False)
    except Exception as e:
        print(f"Error saving bins: {e}")
        # Don't let the error break the application

# --- Helper to find a bin by location ---
def find_bin(bins, location):
    for b in bins:
        if b.location == location:
            return b
    return None

# === ROTARY ENCODER SETUP ===
def button_pressed(channel=None):
    global current_bin_obj
    with state_lock:
        if current_bin_obj is None:
            # No bin open - use selection mode
            button_pressed_selection()
            return
        # Bin is open - use adjustment mode
        local_bin = current_bin_obj.location
        local_adjustment = current_bin_obj.adjustment
    with csv_lock:
        bins = load_bins()
        b = find_bin(bins, local_bin)
        if not b:
            return
        b.adjust_quantity(local_adjustment)
        if b.quantity <= 0:
            # Clear name and set quantity to 0 when removing
            b.name = ""
            b.quantity = 0
            save_bins(bins)
            with state_lock:
                current_bin_obj = None
        else:
            save_bins(bins)
            with state_lock:
                current_bin_obj = b
                current_bin_obj.adjustment = 0

def rotary_cw():
    global current_bin_obj
    with state_lock:
        if current_bin_obj is None:
            # No bin open - use selection mode
            rotary_cw_selection()
        else:
            # Bin is open - use adjustment mode
            if current_bin_obj is not None:
                current_bin_obj.adjustment += 1

def rotary_ccw():
    global current_bin_obj
    with state_lock:
        if current_bin_obj is None:
            # No bin open - use selection mode
            rotary_ccw_selection()
        else:
            # Bin is open - use adjustment mode
            if current_bin_obj is not None:
                current_bin_obj.adjustment -= 1

# define RE GPIO pins and event detects
SW,DT,CLK = 17, 27, 22
button = Button(SW, pull_up=True, bounce_time=0.1)
encoder = RotaryEncoder(CLK, DT,wrap=False, max_steps=0)
button.when_pressed = button_pressed
encoder.when_rotated_clockwise = rotary_cw
encoder.when_rotated_counter_clockwise = rotary_ccw

# Global selection functions
def rotary_cw_selection():
    global selected_row_index, selected_column_index
    if selection_mode == "row":
        selected_row_index = (selected_row_index + 1) % len(valid_rows)
    else:  # column
        selected_column_index = (selected_column_index + 1) % len(valid_columns)

def rotary_ccw_selection():
    global selected_row_index, selected_column_index
    if selection_mode == "row":
        selected_row_index = (selected_row_index - 1) % len(valid_rows)
    else:  # column
        selected_column_index = (selected_column_index - 1) % len(valid_columns)

def button_pressed_selection():
    global selection_mode, selected_row_index, selected_column_index
    
    if selection_mode == "row":
        selection_mode = "column"
    else:
        # Open the selected bin when column is selected
        selected_bin = f"{valid_rows[selected_row_index]}{valid_columns[selected_column_index]}"
        
        with csv_lock:
            bins = load_bins()
            b = find_bin(bins, selected_bin)
            if b:
                # Send message to GUI to open the bin
                gui_event_queue.put(("OPEN_BIN", selected_bin))
            else:
                # Create empty bin if it doesn't exist
                new_bin = Bin("", 0, selected_bin)
                bins.append(new_bin)
                bins.sort(key=lambda b: b.location)
                save_bins(bins)
                # Send message to GUI to open the new bin
                gui_event_queue.put(("OPEN_BIN", selected_bin))

def user_input_loop():
    global current_bin_obj
    time.sleep(2)
    while True:
        user_cmd = input("Enter command (Add, Clear, Update, Open): ").strip()

        with csv_lock:
            df = pd.read_csv(csv_path)

        if user_cmd == "Add":
            Name = input("Component Name: ").strip()
            Quantity = int(input("Component Quantity: ").strip())
            Bin_location = input("Bin Location (e.g., A1): ").strip().upper()

            with csv_lock:
                df = pd.read_csv(csv_path)
                if Bin_location in df["Location"].values:
                    print("Bin already occupied.")
                else:
                    df.loc[len(df)] = [Name, Quantity, Bin_location]
                    df.sort_values(by="Location", inplace=True)
                    df.to_csv(csv_path, index=False)
                    print("Inventory updated.")

        elif user_cmd == "Clear":
            Bin_location = input("Bin Location (e.g., A1): ").strip().upper()

            with csv_lock:
                bins = load_bins()
                b = find_bin(bins, Bin_location)
                if b:
                    b.name = ""  # Clear name
                    b.quantity = 0  # Set quantity to 0
                    save_bins(bins)
                    print(f"Cleared {Bin_location}.")
                else:
                    print(f"{Bin_location} not found.")

        elif user_cmd == "Open":
            Bin_location = input("Open which bin (e.g., A1)? ").strip().upper()

            with csv_lock:
                bins = load_bins()
                b = find_bin(bins, Bin_location)
                if not b:
                    print(f"{Bin_location} not found.")
                    continue

            with state_lock:
                global current_bin_obj
                current_bin_obj = b

        elif user_cmd == "Close":
            with state_lock:
                current_bin_obj = None

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
                'current_quantity': int(current_bin_obj.quantity),
                'current_adjustment': current_bin_obj.adjustment if current_bin_obj else 0
            }
        else:
            return {
                'current_bin': None,
                'current_name': None,
                'current_quantity': None,
                'current_adjustment': None
            }

@app.route("/")
def index():
    try:
        bins = load_bins()
        table_data = [b.to_dict() for b in bins]
        return render_template("index.html", table_data=table_data, **get_current_status())
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
                bin_location = bin_location.upper()  # Convert to uppercase for consistency
                with csv_lock:
                    bins = load_bins()
                    if find_bin(bins, bin_location):
                        table_data = [b.to_dict() for b in bins]
                        return render_template("index.html", 
                                             table_data=table_data,
                                             error="Bin already occupied.",
                                             **get_current_status())
                    new_bin = Bin(name, quantity, bin_location)
                    bins.append(new_bin)
                    bins.sort(key=lambda b: b.location)
                    save_bins(bins)
                    with state_lock:
                        global current_bin_obj
                        current_bin_obj = new_bin
                    table_data = [b.to_dict() for b in bins]
                    return render_template("index.html", 
                                         table_data=table_data,
                                         success="Inventory updated successfully.",
                                         **get_current_status())
            except ValueError:
                bins = load_bins()
                table_data = [b.to_dict() for b in bins]
                return render_template("index.html", 
                                     table_data=table_data,
                                     error="Invalid quantity. Please enter a number.",
                                     **get_current_status())
        else:
            bins = load_bins()
            table_data = [b.to_dict() for b in bins]
            return render_template("index.html", 
                                 table_data=table_data,
                                 error="All fields are required.",
                                 **get_current_status())
    
    bins = load_bins()
    table_data = [b.to_dict() for b in bins]
    return render_template("index.html", 
                         table_data=table_data,
                         **get_current_status())

@app.route("/clear", methods=['GET', 'POST'])
def clear_item():
    if request.method == 'POST':
        bin_location = request.form.get('bin_location', '').strip().upper()
        
        if bin_location:
            with csv_lock:
                bins = load_bins()
                b = find_bin(bins, bin_location)
                if b:
                    b.name = ""  # Clear name
                    b.quantity = 0  # Set quantity to 0
                    save_bins(bins)
                    
                    # Close the bin if it's currently open in Tkinter GUI
                    with state_lock:
                        global current_bin_obj
                        if current_bin_obj and current_bin_obj.location == bin_location:
                            current_bin_obj = None
                    
                    table_data = [b.to_dict() for b in bins]
                    return render_template("index.html", 
                                         table_data=table_data,
                                         success=f"Cleared {bin_location}.",
                                         **get_current_status())
                else:
                    table_data = [b.to_dict() for b in bins]
                    return render_template("index.html", 
                                         table_data=table_data,
                                         error=f"{bin_location} not found.",
                                         **get_current_status())
        else:
            bins = load_bins()
            table_data = [b.to_dict() for b in bins]
            return render_template("index.html", 
                                 table_data=table_data,
                                 error="Bin location is required.",
                                 **get_current_status())
    
    # GET request - show the form
    bins = load_bins()
    table_data = [b.to_dict() for b in bins]
    return render_template("index.html", table_data=table_data, **get_current_status())

@app.route("/open", methods=['GET', 'POST'])
def open_bin():
    if request.method == 'POST':
        bin_location = request.form.get('bin_location', '').strip()
        if bin_location:
            bin_location = bin_location.upper()  # Convert to uppercase for consistency
            with csv_lock:
                bins = load_bins()
                b = find_bin(bins, bin_location)
                if b:
                    with state_lock:
                        global current_bin_obj
                        current_bin_obj = b
                    table_data = [b.to_dict() for b in bins]
                    return render_template("index.html", 
                                         table_data=table_data,
                                         success=f"Opened {bin_location} - {b.name} (Qty: {b.quantity})",
                                         **get_current_status())
                else:
                    table_data = [b.to_dict() for b in bins]
                    return render_template("index.html", 
                                         table_data=table_data,
                                         error=f"{bin_location} not found.",
                                         **get_current_status())
        else:
            bins = load_bins()
            table_data = [b.to_dict() for b in bins]
            return render_template("index.html", 
                                 table_data=table_data,
                                 error="Bin location is required.",
                                 **get_current_status())
    bins = load_bins()
    table_data = [b.to_dict() for b in bins]
    return render_template("index.html", 
                         table_data=table_data,
                         **get_current_status())

@app.route("/close", methods=['POST'])
def close_bin():
    with state_lock:
        global current_bin_obj
        current_bin_obj = None
    bins = load_bins()
    table_data = [b.to_dict() for b in bins]
    return render_template("index.html", 
                         table_data=table_data,
                         success="Bin closed.",
                         **get_current_status())

@app.route("/status")
def get_status():
    with state_lock:
        status = {
            'current_bin': current_bin_obj.location if current_bin_obj else None,
            'current_name': current_bin_obj.name if current_bin_obj else None,
            'current_quantity': int(current_bin_obj.quantity) if current_bin_obj else None,
            'current_adjustment': current_bin_obj.adjustment if current_bin_obj else None
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
            # Clear name and set quantity to 0 when removing
            b.name = ""
            b.quantity = 0
            save_bins(bins)
            with state_lock:
                current_bin_obj = None
            return jsonify({'success': True, 'message': f'Cleared {local_bin}'})
        else:
            save_bins(bins)
            with state_lock:
                current_bin_obj = b
                current_bin_obj.adjustment = 0
            return jsonify({'success': True, 'message': f'Updated {local_bin} quantity to {b.quantity}'})

@app.route("/download")
def download_csv():
    return send_file(csv_path, as_attachment=True)

@app.route("/update-bin", methods=['POST'])
def update_bin():
    data = request.get_json()
    name = data.get('name', '').strip()
    quantity = data.get('quantity', '').strip()
    location = data.get('location', '').strip()
    original_location = data.get('original_location', '').strip()
    try:
        quantity = int(quantity)
    except Exception:
        return jsonify({'success': False, 'error': 'Invalid quantity'})
    with csv_lock:
        bins = load_bins()
        b = find_bin(bins, original_location)
        if not b:
            return jsonify({'success': False, 'error': 'Original bin not found'})
        b.name = name
        b.quantity = quantity
        b.location = location
        save_bins(bins)
    return jsonify({'success': True})

@app.route("/update-all-bins", methods=['POST'])
def update_all_bins():
    if not request.is_json:
        return jsonify({'success': False, 'error': 'Invalid request format'})
    
    data = request.get_json()
    changes = data.get('changes', [])
    
    if not changes:
        return jsonify({'success': False, 'error': 'No changes provided'})
    
    try:
        with csv_lock:
            bins = load_bins()
            
            # Process all changes
            for change in changes:
                name = change.get('name', '').strip()
                quantity = change.get('quantity', '').strip()
                location = change.get('location', '').strip()
                original_location = change.get('original_location', '').strip()
                
                try:
                    quantity = int(quantity)
                except ValueError:
                    return jsonify({'success': False, 'error': f'Invalid quantity for {original_location}'})
                
                # Find the bin to update
                b = find_bin(bins, original_location)
                if not b:
                    return jsonify({'success': False, 'error': f'Original bin {original_location} not found'})
                
                # Update the bin
                b.name = name
                b.quantity = quantity
                b.location = location
            
            # Save all changes
            save_bins(bins)
            
        return jsonify({'success': True, 'message': f'Updated {len(changes)} bins successfully'})
        
    except Exception as e:
        return jsonify({'success': False, 'error': f'Error updating bins: {str(e)}'})

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

    title = tk.Label(root, text="MiniBench Inventory", font=("Helvetica", 48, "bold"),
                    fg="#FFD700", bg="#1e1e1e")
    title.pack(pady=40)

    main_frame = tk.Frame(root, bg="#1e1e1e")
    main_frame.pack(expand=True, fill="both", padx=20, pady=20)
    main_frame.columnconfigure(0, weight=1)
    main_frame.columnconfigure(1, weight=1)
    main_frame.rowconfigure(0, weight=1)

    left_frame = tk.Frame(main_frame, bg="#1e1e1e")
    left_frame.pack(side="left", expand=True, fill="both", padx=(20, 10))
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
    right_frame.pack(side="right", expand=True, fill="both", padx=(10, 20))
    right_frame.rowconfigure(0, weight=1)
    right_frame.columnconfigure(0, weight=1)

    # Create a container for all right-side elements using pack
    right_container = tk.Frame(right_frame, bg="#1e1e1e")
    right_container.grid(row=0, column=0, sticky="nsew")

    adj_container = tk.Frame(right_container, bg="#1e1e1e")
    adj_container.pack(expand=True, fill="both")

    adj_label_text = tk.Label(adj_container, text="Adjustment", font=("Helvetica", 28), fg="#FFFFFF", bg="#1e1e1e",
                            anchor="center", justify="center")
    adj_label_text.pack(pady=(0, 5), anchor="center")

    adj_value = tk.Label(adj_container, text="0", font=("Helvetica", 72, "bold"),
                        fg="#FFFFFF", bg="#1e1e1e", anchor="center", justify="center")
    adj_value.pack(anchor="center")

    # Button frame for close and clear buttons
    button_frame = tk.Frame(right_container, bg="#1e1e1e")
    
    # Close Bin button
    def close_bin():
        with state_lock:
            global current_bin_obj
            current_bin_obj = None

    close_button = tk.Button(button_frame, text="Close Bin", font=("Helvetica", 16, "bold"),
                            fg="#FFFFFF", bg="#dc3545",
                            command=close_bin,
                            relief="flat", bd=0,
                            width=12, height=2)
    close_button.pack(side="left", padx=(0, 10))

    # Clear Bin button
    def clear_bin():
        global current_bin_obj
        if current_bin_obj is None:
            return  # No bin is open, nothing to clear
        
        with state_lock:
            local_bin = current_bin_obj.location
        if local_bin:
            with csv_lock:
                bins = load_bins()
                b = find_bin(bins, local_bin)
                if b:
                    b.name = ""  # Clear name
                    b.quantity = 0  # Set quantity to 0
                    save_bins(bins)
                    with state_lock:
                        current_bin_obj = None

    clear_button = tk.Button(button_frame, text="Clear Bin", font=("Helvetica", 16, "bold"),
                            fg="#FFFFFF", bg="#ff8c00",  # Orange color
                            command=clear_bin,
                            relief="flat", bd=0,
                            width=12, height=2)
    clear_button.pack(side="left")

    # Selection controls - moved outside left/right frame structure
    selection_frame = tk.Frame(main_frame, bg="#1e1e1e")
    
    # Row selection
    row_label = tk.Label(selection_frame, text="Row:", font=("Helvetica", 28), fg="#FFFFFF", bg="#1e1e1e",
                        anchor="center", justify="center")
    row_label.pack(side="left", padx=(0, 10))
    
    row_display = tk.Label(selection_frame, text=valid_rows[selected_row_index], font=("Helvetica", 32, "bold"), 
                          fg="#FFD700", bg="#333333", relief="solid", bd=2, width=3)  # Use current global value
    row_display.pack(side="left", padx=(0, 20))
    
    # Column selection
    col_label = tk.Label(selection_frame, text="Column:", font=("Helvetica", 28), fg="#FFFFFF", bg="#1e1e1e",
                        anchor="center", justify="center")
    col_label.pack(side="left", padx=(0, 10))
    
    col_display = tk.Label(selection_frame, text=str(valid_columns[selected_column_index]), font=("Helvetica", 32, "bold"), 
                          fg="#00BFFF", bg="#1e1e1e", relief="solid", bd=2, width=3)  # Use current global value
    col_display.pack(side="left")

    # Open selected bin button
    def open_selected_bin():
        try:
            global current_bin_obj
            # Read the current selection from the display labels
            current_row = row_display.cget("text")
            current_col = col_display.cget("text")
            selected_bin = f"{current_row}{current_col}"
            
            with csv_lock:
                bins = load_bins()
                b = find_bin(bins, selected_bin)
                if b:
                    with state_lock:
                        current_bin_obj = b
                else:
                    # Create empty bin if it doesn't exist
                    new_bin = Bin("", 0, selected_bin)
                    bins.append(new_bin)
                    bins.sort(key=lambda b: b.location)
                    save_bins(bins)
                    with state_lock:
                        current_bin_obj = new_bin
        except Exception as e:
            print(f"Error opening selected bin: {e}")
            # Don't let the error break the application

    # Clear selected bin button
    def clear_selected_bin():
        try:
            # Read the current selection from the display labels
            current_row = row_display.cget("text")
            current_col = col_display.cget("text")
            selected_bin = f"{current_row}{current_col}"
            
            with csv_lock:
                bins = load_bins()
                b = find_bin(bins, selected_bin)
                if b:
                    b.name = ""  # Clear name
                    b.quantity = 0  # Set quantity to 0
                    save_bins(bins)
                    print(f"Cleared {selected_bin}")
                else:
                    print(f"{selected_bin} not found")
        except Exception as e:
            print(f"Error clearing selected bin: {e}")
            # Don't let the error break the application

    # Button frame for selection buttons
    selection_button_frame = tk.Frame(main_frame, bg="#1e1e1e")
    
    open_button = tk.Button(selection_button_frame, text="Open Selected Bin", font=("Helvetica", 20, "bold"),
                           fg="#FFFFFF", bg="#28a745",
                           command=open_selected_bin,
                           relief="flat", bd=0,
                           width=15, height=2)
    open_button.pack(side="left", padx=(0, 10))

    clear_selected_button = tk.Button(selection_button_frame, text="Clear Selected Bin", font=("Helvetica", 20, "bold"),
                                     fg="#FFFFFF", bg="#ff8c00",  # Orange color
                                     command=clear_selected_bin,
                                     relief="flat", bd=0,
                                     width=15, height=2)
    clear_selected_button.pack(side="left", padx=(0, 10))

    # Fill selected bin button
    def fill_selected_bin():
        try:
            global current_bin_obj
            # Read the current selection from the display labels
            current_row = row_display.cget("text")
            current_col = col_display.cget("text")
            selected_bin = f"{current_row}{current_col}"
            
            # Create a new window for filling the bin
            fill_window = tk.Toplevel(root)
            fill_window.title(f"Fill Bin {selected_bin}")
            fill_window.configure(bg="#1e1e1e")
            fill_window.attributes('-fullscreen', True)
            
            # Center the window content
            fill_frame = tk.Frame(fill_window, bg="#1e1e1e")
            fill_frame.pack(expand=True, fill="both", padx=50, pady=50)
            
            # Title
            title_label = tk.Label(fill_frame, text=f"Fill Bin {selected_bin}", 
                                  font=("Helvetica", 36, "bold"), fg="#FFD700", bg="#1e1e1e")
            title_label.pack(pady=(0, 40))
            
            # Part name entry
            name_frame = tk.Frame(fill_frame, bg="#1e1e1e")
            name_frame.pack(pady=20)
            
            name_label = tk.Label(name_frame, text="Part Name:", font=("Helvetica", 24), 
                                 fg="#FFFFFF", bg="#1e1e1e")
            name_label.pack()
            
            name_entry = tk.Entry(name_frame, font=("Helvetica", 20), width=30)
            name_entry.pack(pady=10)
            name_entry.focus()
            
            # Quantity entry
            qty_frame = tk.Frame(fill_frame, bg="#1e1e1e")
            qty_frame.pack(pady=20)
            
            qty_label = tk.Label(qty_frame, text="Quantity:", font=("Helvetica", 24), 
                                fg="#FFFFFF", bg="#1e1e1e")
            qty_label.pack()
            
            qty_entry = tk.Entry(qty_frame, font=("Helvetica", 20), width=10)
            qty_entry.pack(pady=10)
            qty_entry.insert(0, "1")  # Default quantity
            
            # Buttons frame
            button_frame = tk.Frame(fill_frame, bg="#1e1e1e")
            button_frame.pack(pady=40)
            
            def save_fill():
                try:
                    part_name = name_entry.get().strip()
                    quantity = int(qty_entry.get().strip())
                    
                    if not part_name:
                        tk.messagebox.showerror("Error", "Please enter a part name")
                        return
                    
                    if quantity <= 0:
                        tk.messagebox.showerror("Error", "Quantity must be greater than 0")
                        return
                    
                    with csv_lock:
                        bins = load_bins()
                        b = find_bin(bins, selected_bin)
                        if b:
                            b.name = part_name
                            b.quantity = quantity
                        else:
                            # Create new bin if it doesn't exist
                            new_bin = Bin(part_name, quantity, selected_bin)
                            bins.append(new_bin)
                            bins.sort(key=lambda b: b.location)
                        
                        save_bins(bins)
                    
                    fill_window.destroy()
                    tk.messagebox.showinfo("Success", f"Filled {selected_bin} with {part_name} (Qty: {quantity})")
                    
                except ValueError:
                    tk.messagebox.showerror("Error", "Please enter a valid quantity")
                except Exception as e:
                    tk.messagebox.showerror("Error", f"Error filling bin: {e}")
            
            def cancel_fill():
                fill_window.destroy()
            
            # Save button
            save_button = tk.Button(button_frame, text="Save", font=("Helvetica", 20, "bold"),
                                   fg="#FFFFFF", bg="#28a745",
                                   command=save_fill,
                                   relief="flat", bd=0,
                                   width=10, height=2)
            save_button.pack(side="left", padx=(0, 20))
            
            # Cancel button
            cancel_button = tk.Button(button_frame, text="Cancel", font=("Helvetica", 20, "bold"),
                                     fg="#FFFFFF", bg="#6c757d",
                                     command=cancel_fill,
                                     relief="flat", bd=0,
                                     width=10, height=2)
            cancel_button.pack(side="left")
            
            # Bind Enter key to save
            fill_window.bind('<Return>', lambda e: save_fill())
            fill_window.bind('<Escape>', lambda e: cancel_fill())
            
        except Exception as e:
            print(f"Error opening fill window: {e}")
            # Don't let the error break the application

    fill_selected_button = tk.Button(selection_button_frame, text="Fill Selected Bin", font=("Helvetica", 20, "bold"),
                                    fg="#FFFFFF", bg="#007bff",  # Blue color
                                    command=fill_selected_bin,
                                    relief="flat", bd=0,
                                    width=15, height=2)
    fill_selected_button.pack(side="left")

    # Selection functions - use global state
    def select_row():
        global selection_mode
        selection_mode = "row"
        row_display.config(fg="#FFD700", bg="#333333")  # Highlight row
        col_display.config(fg="#00BFFF", bg="#1e1e1e")  # Unhighlight column
    
    def select_column():
        global selection_mode
        selection_mode = "column"
        col_display.config(fg="#FFD700", bg="#333333")  # Highlight column
        row_display.config(fg="#00BFFF", bg="#1e1e1e")  # Unhighlight row
    
    # Bind click events to selection boxes
    row_display.bind('<Button-1>', lambda e: select_row())
    col_display.bind('<Button-1>', lambda e: select_column())
    
    # Remove the duplicate selection functions - they're now global

    def update_display():
        global selected_row_index, selected_column_index, selection_mode, current_bin_obj
        
        # Check for messages from rotary encoder thread
        try:
            while not gui_event_queue.empty():
                message_type, data = gui_event_queue.get_nowait()
                if message_type == "OPEN_BIN":
                    with csv_lock:
                        bins = load_bins()
                        b = find_bin(bins, data)
                        if b:
                            with state_lock:
                                current_bin_obj = b
        except queue.Empty:
            pass  # No messages in queue
        
        # Update selection display based on global state
        current_row_text = valid_rows[selected_row_index]
        current_col_text = str(valid_columns[selected_column_index])
        
        row_display.config(text=current_row_text)
        col_display.config(text=current_col_text)
        
        # Update highlighting based on selection mode
        if selection_mode == "row":
            row_display.config(fg="#FFD700", bg="#333333")  # Highlight row
            col_display.config(fg="#00BFFF", bg="#1e1e1e")  # Unhighlight column
        else:
            col_display.config(fg="#FFD700", bg="#333333")  # Highlight column
            row_display.config(fg="#00BFFF", bg="#1e1e1e")  # Unhighlight row
        
        with state_lock:
            local_bin = current_bin_obj.location if current_bin_obj else None
            local_name = current_bin_obj.name if current_bin_obj else None
            local_quantity = current_bin_obj.quantity if current_bin_obj else None
            local_adjustment = current_bin_obj.adjustment if current_bin_obj else None
        
        if local_bin:
            main_frame.pack(expand=True, fill="both")
            title.pack(pady=40)
            
            # Hide the no_bin_label if it exists
            if hasattr(root, 'no_bin_label'):
                root.no_bin_label.grid_remove()
            
            # Show the left and right frames
            left_frame.pack(side="left", expand=True, fill="both", padx=(20, 10))
            right_frame.pack(side="right", expand=True, fill="both", padx=(10, 20))
            
            # Hide selection controls when bin is open
            selection_frame.pack_forget()
            selection_button_frame.pack_forget()
            
            # Show adjustment container when bin is open
            adj_container.pack(expand=True, fill="both")
            # Show button frame when bin is open
            button_frame.pack(pady=20)
            # Show left frame labels when bin is open
            bin_label.pack(pady=20, anchor="center", fill="x", expand=True)
            name_label.pack(pady=20, anchor="center", fill="x", expand=True)
            qty_label.pack(pady=20, anchor="center", fill="x", expand=True)
            bin_label.config(text=f"{local_bin}")
            available_width = name_label.winfo_width()
            if available_width <= 1:
                available_width = 400
            
            # Handle empty bin name - convert NaN to empty string
            if local_name is None or (isinstance(local_name, float) and pd.isna(local_name)) or (isinstance(local_name, str) and local_name.strip() == ""):
                part_text = "Empty"
            else:
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
            
            # Handle quantity display
            if local_quantity == 0:
                qty_label.config(text="Qty: 0")
            else:
                qty_label.config(text=f"Qty: {local_quantity}")
            
            adj_label_text.config(text="Adjustment")
            sign = "+" if local_adjustment > 0 else ""
            adj_value.config(text=f"{sign}{local_adjustment}")
        else:
            # Hide left frame labels when no bin is open
            bin_label.pack_forget()
            name_label.pack_forget()
            qty_label.pack_forget()
            title.pack(pady=40)
            
            # Hide the left and right frames
            left_frame.pack_forget()
            right_frame.pack_forget()
            
            # Show selection controls when no bin is open
            selection_frame.pack(pady=20)
            selection_button_frame.pack(pady=10)
            
            # Hide adjustment container when no bin is open
            adj_container.pack_forget()
            # Hide button frame when no bin is open
            button_frame.pack_forget()
        root.after(200, update_display)

    update_display()
    root.mainloop()

# === THREADING ===
threading.Thread(target=user_input_loop, daemon=True).start()
threading.Thread(target=start_flask, daemon=True).start()
start_tkinter_gui()
