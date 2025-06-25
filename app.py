import pandas as pd
import threading
import time
from flask import Flask, render_template
import random as r
import logging

app = Flask(__name__)
csv_path = "inventory.csv"

import random as r

def get_sensor_data(df):
    for i, row in df.iterrows():
        qty = row["Quantity"] + r.randint(-10, 10)
        df.at[i, "Quantity"] = max(qty, 0)
    return df

def update_inventory_loop():
    while True:
            # Load the CSV
            df = pd.read_csv(csv_path)
            df["Quantity"] = df["Quantity"].astype(int)

            # Append new sensor data (replace with real sensor logic)
            df = get_sensor_data(df)

            # Save back to CSV
            df.to_csv(csv_path, index=False)

            time.sleep(1)

import threading

def user_input_loop():
    while True:
        user_cmd = input("Enter command (Add, Rem, Update): ").strip()
        if user_cmd == "Add":
            Name = input("Component Name: ").strip()
            Quantity = int(input("Component Quantity: ").strip())
            Bin_Location = input("Bin Location: ").strip()
            Bin_location = "Bin-" + Bin_Location
            df = pd.read_csv(csv_path)

            if(Bin_location in df["Location"].values):
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
    log.setLevel(logging.ERROR)  # or logging.CRITICAL to suppress almost all
    threading.Thread(target=update_inventory_loop, daemon=True).start()
    threading.Thread(target=user_input_loop, daemon=False).start()  # don't daemon if you want input to block

    app.run(host="0.0.0.0", port=5005)