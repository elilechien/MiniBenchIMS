import pandas as pd
import threading
import time
from flask import Flask, render_template, send_file, request, jsonify
import tkinter as tk
from gpiozero import Button, RotaryEncoder
import os
import subprocess

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
    global current_bin_obj
    with state_lock:
        if current_bin_obj is None:
            return
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
    with state_lock:
        if current_bin_obj is not None:
            current_bin_obj.adjustment += 1

def rotary_ccw():
    with state_lock:
        if current_bin_obj is not None:
            current_bin_obj.adjustment -= 1

# define RE GPIO pins and event detects
SW,DT,CLK = 17, 27, 22
button = Button(SW, pull_up=True, bounce_time=0.1)
encoder = RotaryEncoder(CLK, DT,wrap=False, max_steps=0)
button.when_pressed = button_pressed
encoder.when_rotated_clockwise = rotary_cw
encoder.when_rotated_counter_clockwise = rotary_ccw

def user_input_loop():
    global current_bin_obj
    time.sleep(2)
    while True:
        user_cmd = input("Enter command (Add, Rem, Update, Open): ").strip()

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

        elif user_cmd == "Rem":
            Bin_location = input("Bin Location (e.g., A1): ").strip().upper()

            with csv_lock:
                bins = load_bins()
                b = find_bin(bins, Bin_location)
                if b:
                    b.name = ""  # Clear name
                    b.quantity = 0  # Set quantity to 0
                    save_bins(bins)
                    table_data = [b.to_dict() for b in bins]
                    return render_template("index.html", 
                                         table_data=table_data,
                                         success=f"Cleared {Bin_location}.",
                                         **get_current_status())
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

@app.route("/remove", methods=['GET', 'POST'])
def remove_item():
    if request.method == 'POST':
        bin_location = request.form.get('bin_location', '').strip()
        if bin_location:
            bin_location = bin_location.upper()  # Convert to uppercase for consistency
            with csv_lock:
                bins = load_bins()
                b = find_bin(bins, bin_location)
                if b:
                    b.name = ""  # Clear name
                    b.quantity = 0  # Set quantity to 0
                    save_bins(bins)
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
    bins = load_bins()
    table_data = [b.to_dict() for b in bins]
    return render_template("index.html", 
                         table_data=table_data,
                         **get_current_status())

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

    def show_keyboard():
        try:
            # Try to launch matchbox-keyboard (common on Raspberry Pi)
            subprocess.Popen(['matchbox-keyboard'], 
                           stdout=subprocess.DEVNULL, 
                           stderr=subprocess.DEVNULL)
        except FileNotFoundError:
            try:
                # Fallback to onboard (Ubuntu/Debian)
                subprocess.Popen(['onboard'], 
                               stdout=subprocess.DEVNULL, 
                               stderr=subprocess.DEVNULL)
            except FileNotFoundError:
                # If no keyboard found, just focus the entry
                pass

    def hide_keyboard():
        try:
            # Kill matchbox-keyboard
            subprocess.run(['pkill', 'matchbox-keyboard'], 
                         stdout=subprocess.DEVNULL, 
                         stderr=subprocess.DEVNULL)
        except:
            try:
                # Kill onboard
                subprocess.run(['pkill', 'onboard'], 
                             stdout=subprocess.DEVNULL, 
                             stderr=subprocess.DEVNULL)
            except:
                pass

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

    # Close Bin button
    def close_bin():
        with state_lock:
            global current_bin_obj
            current_bin_obj = None

    close_button = tk.Button(right_container, text="Close Bin", font=("Helvetica", 16, "bold"),
                            fg="#FFFFFF", bg="#dc3545",
                            command=close_bin,
                            relief="flat", bd=0,
                            width=12, height=2)
    close_button.pack(pady=20)

    # Row and Column Selection
    valid_rows = ['A', 'B', 'C', 'D', 'E', 'F', 'G', 'H']
    valid_columns = [1, 2, 3, 4, 5, 6, 7, 8]
    
    # Selection state
    selected_row_index = 0
    selected_column_index = 0
    selection_mode = "row"  # "row" or "column"
    
    # Create selection frame
    selection_frame = tk.Frame(right_container, bg="#1e1e1e")
    
    # Row selection
    row_label = tk.Label(selection_frame, text="Row:", font=("Helvetica", 20), fg="#FFFFFF", bg="#1e1e1e",
                        anchor="center", justify="center")
    row_label.pack(side="left", padx=(0, 10))
    
    row_display = tk.Label(selection_frame, text=valid_rows[0], font=("Helvetica", 24, "bold"), 
                          fg="#00BFFF", bg="#1e1e1e", relief="solid", bd=2, width=3)
    row_display.pack(side="left", padx=(0, 20))
    
    # Column selection
    col_label = tk.Label(selection_frame, text="Column:", font=("Helvetica", 20), fg="#FFFFFF", bg="#1e1e1e",
                        anchor="center", justify="center")
    col_label.pack(side="left", padx=(0, 10))
    
    col_display = tk.Label(selection_frame, text=str(valid_columns[0]), font=("Helvetica", 24, "bold"), 
                          fg="#00BFFF", bg="#1e1e1e", relief="solid", bd=2, width=3)
    col_display.pack(side="left")
    
    # Open selected bin button
    def open_selected_bin():
        selected_bin = f"{valid_rows[selected_row_index]}{valid_columns[selected_column_index]}"
        with csv_lock:
            bins = load_bins()
            b = find_bin(bins, selected_bin)
            if b:
                with state_lock:
                    global current_bin_obj
                    current_bin_obj = b
            else:
                # Create empty bin if it doesn't exist
                new_bin = Bin("", 0, selected_bin)
                bins.append(new_bin)
                bins.sort(key=lambda b: b.location)
                save_bins(bins)
                with state_lock:
                    current_bin_obj = new_bin
    
    open_button = tk.Button(right_container, text="Open Selected Bin", font=("Helvetica", 14, "bold"),
                           fg="#FFFFFF", bg="#28a745",
                           command=open_selected_bin,
                           relief="flat", bd=0,
                           width=15, height=2)
    open_button.pack(pady=10)
    
    # Selection functions
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
    
    # Override rotary encoder functions for selection
    def rotary_cw_selection():
        global selected_row_index, selected_column_index
        if selection_mode == "row":
            selected_row_index = (selected_row_index + 1) % len(valid_rows)
            row_display.config(text=valid_rows[selected_row_index])
        else:  # column
            selected_column_index = (selected_column_index + 1) % len(valid_columns)
            col_display.config(text=str(valid_columns[selected_column_index]))
    
    def rotary_ccw_selection():
        global selected_row_index, selected_column_index
        if selection_mode == "row":
            selected_row_index = (selected_row_index - 1) % len(valid_rows)
            row_display.config(text=valid_rows[selected_row_index])
        else:  # column
            selected_column_index = (selected_column_index - 1) % len(valid_columns)
            col_display.config(text=str(valid_columns[selected_column_index]))
    
    # Override button press for selection
    def button_pressed_selection():
        if selection_mode == "row":
            select_column()  # Switch to column selection
        else:
            open_selected_bin()  # Open the selected bin

    def update_display():
        with state_lock:
            local_bin = current_bin_obj.location if current_bin_obj else None
            local_name = current_bin_obj.name if current_bin_obj else None
            local_quantity = current_bin_obj.quantity if current_bin_obj else None
            local_adjustment = current_bin_obj.adjustment if current_bin_obj else None
        
        if local_bin:
            main_frame.pack(expand=True, fill="both")
            title.pack(pady=40)
            if hasattr(root, 'no_bin_label'):
                root.no_bin_label.pack_forget()
            # Show adjustment container when bin is open
            adj_container.pack(expand=True, fill="both")
            # Show close button when bin is open
            close_button.pack(pady=20)
            # Show left frame labels when bin is open
            bin_label.pack(pady=20, anchor="center", fill="x", expand=True)
            name_label.pack(pady=20, anchor="center", fill="x", expand=True)
            qty_label.pack(pady=20, anchor="center", fill="x", expand=True)
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
            # Hide left frame labels when no bin is open
            bin_label.pack_forget()
            name_label.pack_forget()
            qty_label.pack_forget()
            title.pack(pady=40)
            if not hasattr(root, 'no_bin_label'):
                root.no_bin_label = tk.Label(root, text="No bin currently open", 
                                            font=("Helvetica", 48, "bold"),
                                            fg="#FFD700", bg="#1e1e1e")
                root.no_bin_label.pack(expand=True, fill="both")
            else:
                root.no_bin_label.pack(expand=True, fill="both")
            # Hide adjustment container when no bin is open
            adj_container.pack_forget()
            # Hide close button when no bin is open
            close_button.pack_forget()
        root.after(200, update_display)

    update_display()
    root.mainloop()

# === THREADING ===
threading.Thread(target=user_input_loop, daemon=True).start()
threading.Thread(target=start_flask, daemon=True).start()
start_tkinter_gui()
