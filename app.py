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
import signal
import sys

# === OS CONFIG ===
os.environ["DISPLAY"] = ":0"
os.chdir(os.path.dirname(os.path.abspath(__file__)))

# === CSV Path ===
csv_path = "inventory.csv"

# === SHARED STATE ===
current_bin_obj = None
shutdown_event = threading.Event()

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

# === SIGNAL HANDLING ===
def signal_handler(signum, frame):
    """Handle Ctrl+C gracefully"""
    print("\nShutting down gracefully...")
    shutdown_event.set()
    
    # Close GPIO resources
    try:
        button.close()
        encoder.close()
    except:
        pass
    
    # Exit the application
    sys.exit(0)

# Register signal handler
signal.signal(signal.SIGINT, signal_handler)

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
    while not shutdown_event.is_set():
        try:
            user_cmd = input("Enter command (Add, Clear, Update, Open): ").strip()
        except (EOFError, KeyboardInterrupt):
            # Handle Ctrl+C in the input loop
            break

        with csv_lock:
            df = pd.read_csv(csv_path)

        if user_cmd == "Add":
            try:
                Name = input("Component Name: ").strip()
                Quantity = int(input("Component Quantity: ").strip())
                Bin_location = input("Bin Location (e.g., A1): ").strip().upper()
            except (EOFError, KeyboardInterrupt):
                break

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
            try:
                Bin_location = input("Bin Location (e.g., A1): ").strip().upper()
            except (EOFError, KeyboardInterrupt):
                break

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
            try:
                Bin_location = input("Open which bin (e.g., A1)? ").strip().upper()
            except (EOFError, KeyboardInterrupt):
                break

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
    
    print("User input loop terminated.")

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
    
    # Run Flask in a way that can be interrupted
    try:
        app.run(host="0.0.0.0", port=5000, use_reloader=False)
    except KeyboardInterrupt:
        print("Flask server terminated.")
    finally:
        print("Flask server shutdown complete.")

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
    
    def go_home():
        """Clear current bin and return to home (row selection)"""
        nonlocal current_row, current_col, current_bin
        
        # Clear current bin state
        current_row = None
        current_col = None
        current_bin = None
        
        # Clear any open bin in the system
        with state_lock:
            global current_bin_obj
            current_bin_obj = None
        
        # Show home screen (row selection)
        show_home_screen()
    
    def create_centered_matrix(parent, items, command_func, title_text):
        """Create a centered 2x5 matrix of buttons"""
        # Clear content frame
        for widget in content_frame.winfo_children():
            widget.destroy()
        
        # Title label
        title_label = tk.Label(content_frame, text=title_text, 
                              font=('Arial', 18, 'bold'), 
                              bg='#2c3e50', fg='white')
        title_label.pack(pady=(0, 20))
        
        # Create 2x5 matrix frame for items
        matrix_frame = tk.Frame(content_frame, bg='#2c3e50')
        matrix_frame.pack()
        
        # Calculate centering
        total_items = len(items)
        items_per_row = 5
        num_rows = (total_items + items_per_row - 1) // items_per_row  # Ceiling division
        
        # Create buttons in 2x5 matrix
        for i, item in enumerate(items):
            row_num = i // items_per_row  # Row in matrix
            col_num = i % items_per_row   # Column in matrix
            
            btn = tk.Button(matrix_frame, text=str(item), 
                           font=('Arial', 16, 'bold'),
                           width=8, height=3,
                           bg='#34495e', fg='white',
                           activebackground='#3498db',
                           command=lambda x=item: command_func(x))
            btn.grid(row=row_num, column=col_num, padx=10, pady=10)
        
        # Add Home button at the bottom
        home_btn = tk.Button(content_frame, text="🏠 Home", 
                            font=('Arial', 12, 'bold'),
                            bg='#e74c3c', fg='white',
                            activebackground='#c0392b',
                            command=go_home)
        home_btn.pack(pady=20)
    
    def show_home_screen():
        """Show home screen (row selection)"""
        create_centered_matrix(content_frame, valid_rows, select_row, "Select Bin Row:")
        
    def show_row_selection():
        """Show row selection screen (same as home screen now)"""
        show_home_screen()
    
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
        """Show edit screen with bin contents and options"""
        # Clear content frame
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
        bin_label.pack(pady=(0, 20))
        
        # Load and display bin contents
        bins = load_bins()
        bin_obj = find_bin(bins, current_bin)
        
        # Content display frame
        content_display_frame = tk.Frame(content_frame, bg='#2c3e50')
        content_display_frame.pack(pady=20, fill='x', padx=20)
        
        if bin_obj and bin_obj.name and bin_obj.quantity > 0:
            # Show bin contents
            contents_label = tk.Label(content_display_frame, text="Bin Contents:", 
                                     font=('Arial', 16, 'bold'), 
                                     bg='#2c3e50', fg='white')
            contents_label.pack(anchor='w')
            
            item_label = tk.Label(content_display_frame, 
                                 text=f"Item: {bin_obj.name}", 
                                 font=('Arial', 14), 
                                 bg='#2c3e50', fg='white')
            item_label.pack(anchor='w', pady=(10, 5))
            
            quantity_label = tk.Label(content_display_frame, 
                                     text=f"Quantity: {bin_obj.quantity}", 
                                     font=('Arial', 14), 
                                     bg='#2c3e50', fg='white')
            quantity_label.pack(anchor='w', pady=(0, 10))
        else:
            # Show empty bin
            empty_label = tk.Label(content_display_frame, text="Bin is empty", 
                                  font=('Arial', 14), 
                                  bg='#2c3e50', fg='#95a5a6')
            empty_label.pack(pady=10)
        
        # Options frame
        options_frame = tk.Frame(content_frame, bg='#2c3e50')
        options_frame.pack(pady=20)
        
        # Adjust button
        adjust_btn = tk.Button(options_frame, text="Adjust", 
                              font=('Arial', 14, 'bold'),
                              width=12, height=2,
                              bg='#3498db', fg='white',
                              activebackground='#2980b9',
                              command=lambda: show_adjustment_screen(bin_obj))
        adjust_btn.pack(pady=10)
        
        # Clear button
        clear_btn = tk.Button(options_frame, text="Clear", 
                             font=('Arial', 14, 'bold'),
                             width=12, height=2,
                             bg='#e74c3c', fg='white',
                             activebackground='#c0392b',
                             command=lambda: clear_bin(bin_obj))
        clear_btn.pack(pady=10)
        
        # Add button
        add_btn = tk.Button(options_frame, text="Add", 
                           font=('Arial', 14, 'bold'),
                           width=12, height=2,
                           bg='#27ae60', fg='white',
                           activebackground='#229954',
                           command=lambda: add_to_bin(bin_obj))
        add_btn.pack(pady=10)
        
        # Back to home button
        home_btn = tk.Button(content_frame, text="← Back to Home", 
                            font=('Arial', 12),
                            bg='#95a5a6', fg='white',
                            activebackground='#7f8c8d',
                            command=show_home_screen)
        home_btn.pack(pady=20)
    
    def show_adjustment_screen(bin_obj):
        """Show adjustment screen for quantity"""
        # Clear content frame
        for widget in content_frame.winfo_children():
            widget.destroy()
        
        # Adjustment screen title
        adjust_title = tk.Label(content_frame, text="Adjust Quantity", 
                               font=('Arial', 24, 'bold'), 
                               bg='#2c3e50', fg='white')
        adjust_title.pack(pady=(0, 20))
        
        # Show current bin info
        bin_info_label = tk.Label(content_frame, text=f"Bin: {current_bin}", 
                                 font=('Arial', 16), 
                                 bg='#2c3e50', fg='white')
        bin_info_label.pack(pady=(0, 10))
        
        if bin_obj and bin_obj.name:
            item_label = tk.Label(content_frame, text=f"Item: {bin_obj.name}", 
                                 font=('Arial', 16), 
                                 bg='#2c3e50', fg='white')
            item_label.pack(pady=(0, 10))
        
        # Current quantity
        current_qty = bin_obj.quantity if bin_obj else 0
        qty_label = tk.Label(content_frame, text=f"Current Quantity: {current_qty}", 
                            font=('Arial', 16), 
                            bg='#2c3e50', fg='white')
        qty_label.pack(pady=(0, 20))
        
        # Quantity input frame
        input_frame = tk.Frame(content_frame, bg='#2c3e50')
        input_frame.pack(pady=20)
        
        # New quantity label and entry
        new_qty_label = tk.Label(input_frame, text="New Quantity:", 
                                font=('Arial', 14), 
                                bg='#2c3e50', fg='white')
        new_qty_label.pack()
        
        qty_entry = tk.Entry(input_frame, font=('Arial', 16), width=10)
        qty_entry.pack(pady=10)
        qty_entry.insert(0, str(current_qty))
        qty_entry.focus()
        
        # Buttons frame
        button_frame = tk.Frame(content_frame, bg='#2c3e50')
        button_frame.pack(pady=20)
        
        # Save button
        save_btn = tk.Button(button_frame, text="Save", 
                            font=('Arial', 14, 'bold'),
                            width=10, height=2,
                            bg='#27ae60', fg='white',
                            activebackground='#229954',
                            command=lambda: save_adjustment(qty_entry.get()))
        save_btn.pack(side='left', padx=10)
        
        # Cancel button
        cancel_btn = tk.Button(button_frame, text="Cancel", 
                              font=('Arial', 14, 'bold'),
                              width=10, height=2,
                              bg='#95a5a6', fg='white',
                              activebackground='#7f8c8d',
                              command=show_edit_screen)
        cancel_btn.pack(side='left', padx=10)
    
    def save_adjustment(new_quantity_str):
        """Save the adjusted quantity"""
        try:
            new_quantity = int(new_quantity_str)
            if new_quantity < 0:
                messagebox.showerror("Error", "Quantity cannot be negative")
                return
            
            # Load bins and update
            bins = load_bins()
            bin_obj = find_bin(bins, current_bin)
            
            if not bin_obj:
                # Create new bin if it doesn't exist
                bin_obj = Bin("", 0, current_bin)
                bins.append(bin_obj)
            
            bin_obj.quantity = new_quantity
            if new_quantity == 0:
                bin_obj.name = ""  # Clear name if quantity is 0
            
            save_bins(bins)
            messagebox.showinfo("Success", f"Quantity updated to {new_quantity}")
            show_edit_screen()
            
        except ValueError:
            messagebox.showerror("Error", "Please enter a valid number")
    
    def clear_bin(bin_obj):
        """Clear the bin contents"""
        if not bin_obj or not bin_obj.name or bin_obj.quantity == 0:
            messagebox.showinfo("Info", "Bin is already empty")
            return
        
        # Ask for confirmation
        result = messagebox.askyesno("Confirm Clear", 
                                   f"Are you sure you want to clear bin {current_bin}?\n"
                                   f"This will remove {bin_obj.name} (Qty: {bin_obj.quantity})")
        
        if result:
            # Load bins and clear
            bins = load_bins()
            bin_obj = find_bin(bins, current_bin)
            
            if bin_obj:
                bin_obj.name = ""
                bin_obj.quantity = 0
                save_bins(bins)
                messagebox.showinfo("Success", f"Bin {current_bin} has been cleared")
                show_edit_screen()
    
    def add_to_bin(bin_obj):
        """Add items to bin (placeholder for barcode scanning)"""
        # For now, show a simple input dialog
        # In the future, this would integrate with camera/barcode scanning
        
        # Create a simple dialog for manual entry
        dialog = tk.Toplevel()
        dialog.title("Add to Bin")
        dialog.geometry("400x300")
        dialog.configure(bg='#2c3e50')
        dialog.transient(root)  # Make dialog modal
        dialog.grab_set()
        
        # Center the dialog
        dialog.geometry("+%d+%d" % (root.winfo_rootx() + 50, root.winfo_rooty() + 50))
        
        # Dialog content
        title_label = tk.Label(dialog, text="Add Item to Bin", 
                              font=('Arial', 18, 'bold'), 
                              bg='#2c3e50', fg='white')
        title_label.pack(pady=(20, 10))
        
        bin_label = tk.Label(dialog, text=f"Bin: {current_bin}", 
                            font=('Arial', 14), 
                            bg='#2c3e50', fg='white')
        bin_label.pack(pady=(0, 20))
        
        # Input frame
        input_frame = tk.Frame(dialog, bg='#2c3e50')
        input_frame.pack(pady=10)
        
        # Item name
        name_label = tk.Label(input_frame, text="Item Name:", 
                             font=('Arial', 12), 
                             bg='#2c3e50', fg='white')
        name_label.pack(anchor='w')
        
        name_entry = tk.Entry(input_frame, font=('Arial', 12), width=30)
        name_entry.pack(pady=(5, 15), fill='x')
        
        # Quantity
        qty_label = tk.Label(input_frame, text="Quantity:", 
                            font=('Arial', 12), 
                            bg='#2c3e50', fg='white')
        qty_label.pack(anchor='w')
        
        qty_entry = tk.Entry(input_frame, font=('Arial', 12), width=30)
        qty_entry.pack(pady=(5, 15), fill='x')
        qty_entry.insert(0, "1")
        
        # Buttons
        button_frame = tk.Frame(dialog, bg='#2c3e50')
        button_frame.pack(pady=20)
        
        def save_item():
            name = name_entry.get().strip()
            qty_str = qty_entry.get().strip()
            
            if not name:
                messagebox.showerror("Error", "Please enter an item name")
                return
            
            try:
                quantity = int(qty_str)
                if quantity <= 0:
                    messagebox.showerror("Error", "Quantity must be positive")
                    return
            except ValueError:
                messagebox.showerror("Error", "Please enter a valid quantity")
                return
            
            # Load bins and add item
            bins = load_bins()
            bin_obj = find_bin(bins, current_bin)
            
            if not bin_obj:
                bin_obj = Bin(name, quantity, current_bin)
                bins.append(bin_obj)
            else:
                bin_obj.name = name
                bin_obj.quantity = quantity
            
            save_bins(bins)
            messagebox.showinfo("Success", f"Added {name} (Qty: {quantity}) to bin {current_bin}")
            dialog.destroy()
            show_edit_screen()
        
        def cancel_add():
            dialog.destroy()
        
        save_btn = tk.Button(button_frame, text="Save", 
                            font=('Arial', 12, 'bold'),
                            width=10, height=2,
                            bg='#27ae60', fg='white',
                            activebackground='#229954',
                            command=save_item)
        save_btn.pack(side='left', padx=10)
        
        cancel_btn = tk.Button(button_frame, text="Cancel", 
                              font=('Arial', 12, 'bold'),
                              width=10, height=2,
                              bg='#95a5a6', fg='white',
                              activebackground='#7f8c8d',
                              command=cancel_add)
        cancel_btn.pack(side='left', padx=10)
        
        # Focus on name entry
        name_entry.focus()
    
    # Start with home screen
    show_home_screen()
    
    # Handle window close event
    def on_closing():
        print("Tkinter GUI closing...")
        shutdown_event.set()
        root.quit()
        root.destroy()
    
    root.protocol("WM_DELETE_WINDOW", on_closing)
    
    # Start the GUI with shutdown checking
    try:
        while not shutdown_event.is_set():
            root.update()
            time.sleep(0.1)  # Small delay to allow checking shutdown event
    except tk.TclError:
        # Window was closed
        pass
    finally:
        print("Tkinter GUI shutdown complete.")

# === THREADING ===
# Start background threads
user_input_thread = threading.Thread(target=user_input_loop, daemon=True)
flask_thread = threading.Thread(target=start_flask, daemon=True)

user_input_thread.start()
flask_thread.start()

# Start Tkinter GUI (this will block until GUI closes)
try:
    start_tkinter_gui()
except KeyboardInterrupt:
    print("\nReceived interrupt signal...")
finally:
    # Set shutdown event to stop all threads
    shutdown_event.set()
    
    # Wait for threads to finish (with timeout)
    print("Waiting for threads to finish...")
    user_input_thread.join(timeout=2)
    flask_thread.join(timeout=2)
    
    # Close GPIO resources
    try:
        button.close()
        encoder.close()
    except:
        pass
    
    print("Application shutdown complete.")
