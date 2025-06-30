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
        
        # Update current_bin_obj if it's the one being updated
        with state_lock:
            global current_bin_obj
            if current_bin_obj and current_bin_obj.location == original_location:
                current_bin_obj.name = name
                current_bin_obj.quantity = quantity
                current_bin_obj.location = location
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
            
            # Update current_bin_obj if it's one of the bins being updated
            with state_lock:
                global current_bin_obj
                if current_bin_obj:
                    for change in changes:
                        original_location = change.get('original_location', '').strip()
                        if current_bin_obj.location == original_location:
                            # Reload the current bin from the updated data
                            updated_bin = find_bin(bins, original_location)
                            if updated_bin:
                                current_bin_obj.name = updated_bin.name
                                current_bin_obj.quantity = updated_bin.quantity
                                current_bin_obj.location = updated_bin.location
                            break
            
        return jsonify({'success': True, 'message': f'Updated {len(changes)} bins successfully'})
        
    except Exception as e:
        return jsonify({'success': False, 'error': f'Error updating bins: {str(e)}'})

def start_flask():
    import logging
    log = logging.getLogger('werkzeug')
    log.setLevel(logging.ERROR)
    app.run(host="0.0.0.0", port=5000)

def start_tkinter_gui():
    """Start the Tkinter GUI"""
    
    # Create main window
    root = tk.Tk()
    root.title("Nextbin")
    root.geometry("800x600")
    root.configure(bg='#2c3e50')
    
    # Global variables for the GUI
    current_row = None
    current_col = None
    current_bin = None
    
    # Valid rows and columns
    valid_rows = ['A', 'B', 'C', 'D', 'E', 'F', 'G', 'H']
    valid_cols = [1, 2, 3, 4, 5, 6, 7, 8]
    
    # Create main frame
    main_frame = tk.Frame(root, bg='#2c3e50')
    main_frame.pack(expand=True, fill='both', padx=20, pady=20)
    
    # Content frame
    content_frame = tk.Frame(main_frame, bg='#2c3e50')
    content_frame.pack(expand=True, fill='both')
    
    def show_home_screen():
        """Show home screen with main options"""
        # Clear content frame
        for widget in content_frame.winfo_children():
            widget.destroy()
        
        # Title label
        title_label = tk.Label(content_frame, text="Nextbin Home:", 
                              font=('Arial', 24, 'bold'), 
                              bg='#2c3e50', fg='white')
        title_label.pack(pady=(0, 40))
        
        # Main options frame
        options_frame = tk.Frame(content_frame, bg='#2c3e50')
        options_frame.pack()
        
        # Select Bin button
        select_bin_btn = tk.Button(options_frame, text="Select Bin", 
                                  font=('Arial', 16, 'bold'),
                                  width=15, height=3,
                                  bg='#3498db', fg='white',
                                  activebackground='#2980b9',
                                  command=show_row_selection)
        select_bin_btn.pack(pady=20)

        
    def show_row_selection():
        """Show row selection screen"""
        # Clear content frame
        for widget in content_frame.winfo_children():
            widget.destroy()
        
        # Row selection label
        row_label = tk.Label(content_frame, text="Select Bin Row:", 
                            font=('Arial', 18, 'bold'), 
                            bg='#2c3e50', fg='white')
        row_label.pack(pady=(0, 20))
        
        # Create 2x5 matrix frame for rows
        matrix_frame = tk.Frame(content_frame, bg='#2c3e50')
        matrix_frame.pack()
        
        # Create row buttons in 2x5 matrix
        row_buttons = []
        for i, row in enumerate(valid_rows):
            row_num = i // 5  # Row in matrix (0 or 1)
            col_num = i % 5   # Column in matrix (0-4)
            
            btn = tk.Button(matrix_frame, text=row, 
                           font=('Arial', 16, 'bold'),
                           width=8, height=3,
                           bg='#34495e', fg='white',
                           activebackground='#3498db',
                           command=lambda r=row: select_row(r))
            btn.grid(row=row_num, column=col_num, padx=10, pady=10)
            row_buttons.append(btn)
        
        # Back to home button
        back_btn = tk.Button(content_frame, text="← Back to Home", 
                            font=('Arial', 12),
                            bg='#e74c3c', fg='white',
                            activebackground='#c0392b',
                            command=show_home_screen)
        back_btn.pack(pady=20)
    
    def select_row(row):
        """Handle row selection"""
        nonlocal current_row
        current_row = row
        show_column_selection()
    
    def show_column_selection():
        """Show column selection screen"""
        # Clear content frame
        for widget in content_frame.winfo_children():
            widget.destroy()
        
        # Column selection label
        col_label = tk.Label(content_frame, text=f"Selected Row: {current_row}\nSelect Bin Column:", 
                            font=('Arial', 18, 'bold'), 
                            bg='#2c3e50', fg='white')
        col_label.pack(pady=(0, 20))
        
        # Create 2x5 matrix frame for columns
        matrix_frame = tk.Frame(content_frame, bg='#2c3e50')
        matrix_frame.pack()
        
        # Create column buttons in 2x5 matrix
        col_buttons = []
        for i, col in enumerate(valid_cols):
            row_num = i // 5  # Row in matrix (0 or 1)
            col_num = i % 5   # Column in matrix (0-4)
            
            btn = tk.Button(matrix_frame, text=str(col), 
                           font=('Arial', 16, 'bold'),
                           width=8, height=3,
                           bg='#34495e', fg='white',
                           activebackground='#3498db',
                           command=lambda c=col: select_column(c))
            btn.grid(row=row_num, column=col_num, padx=10, pady=10)
            col_buttons.append(btn)
        
        # Back button
        back_btn = tk.Button(content_frame, text="← Back to Rows", 
                            font=('Arial', 12),
                            bg='#e74c3c', fg='white',
                            activebackground='#c0392b',
                            command=show_row_selection)
        back_btn.pack(pady=20)
    
    def select_column(col):
        """Handle column selection"""
        nonlocal current_col, current_bin
        current_col = col
        current_bin = f"{current_row}{current_col}"
        show_edit_screen()
    
    def show_edit_screen():
        """Show edit screen"""
        # Clear content frame instead of main frame
        for widget in content_frame.winfo_children():
            widget.destroy()
        
        # Edit screen title
        edit_title = tk.Label(content_frame, text="Nextbin edit", 
                             font=('Arial', 24, 'bold'), 
                             bg='#2c3e50', fg='white')
        edit_title.pack(pady=(0, 20))
        
        # Show selected bin
        bin_label = tk.Label(content_frame, text=f"Selected Bin: {current_bin}", 
                            font=('Arial', 18), 
                            bg='#2c3e50', fg='white')
        bin_label.pack(pady=20)
        
        # Back to home button
        home_btn = tk.Button(content_frame, text="← Back to Home", 
                            font=('Arial', 14),
                            bg='#e74c3c', fg='white',
                            activebackground='#c0392b',
                            command=show_home_screen)
        home_btn.pack(pady=20)
    
    # Start with home screen
    show_home_screen()
    
    # Start the GUI
    root.mainloop()

# === THREADING ===
threading.Thread(target=user_input_loop, daemon=True).start()
threading.Thread(target=start_flask, daemon=True).start()
start_tkinter_gui()
