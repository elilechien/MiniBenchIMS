#!/usr/bin/env python3
"""
Simple Bin Detector
Quick calibration with single tolerance and continuous monitoring
"""

import time
import json
import os
from gpiozero import DistanceSensor

# GPIO pin configuration
TRIGGER_PIN = 23
ECHO_PIN = 24

# Default settings
DEFAULT_BIN_POSITIONS = [1, 3, 5, 7, 9, 11, 13, 15]  # inches
BIN_NAMES = ['A1', 'A2', 'A3', 'A4', 'A5', 'A6', 'A7', 'A8']
CALIBRATION_FILE = "bin_calibration.json"
DEBOUNCE_TIME = 1.0  # seconds

class BinDetector:
    def __init__(self, bin_positions, tolerance):
        self.bin_positions = bin_positions
        self.tolerance = tolerance
        self.last_bin = None
        self.last_change_time = 0
        self.current_bin = None
    
    def get_bin(self, distance_inches):
        """Get the bin at the given distance"""
        for i, bin_distance in enumerate(self.bin_positions):
            if abs(distance_inches - bin_distance) <= self.tolerance:
                return BIN_NAMES[i]
        return None
    
    def get_debounced_bin(self, distance_inches):
        """Get bin with debounce applied"""
        current_time = time.time()
        detected_bin = self.get_bin(distance_inches)
        
        # If bin changed, start debounce timer
        if detected_bin != self.last_bin:
            self.last_bin = detected_bin
            self.last_change_time = current_time
            return None
        
        # If same bin detected and debounce time passed, confirm it
        if current_time - self.last_change_time >= DEBOUNCE_TIME:
            if self.current_bin != detected_bin:
                self.current_bin = detected_bin
                return detected_bin
        
        return self.current_bin

def load_calibration():
    """Load calibration from file"""
    if os.path.exists(CALIBRATION_FILE):
        try:
            with open(CALIBRATION_FILE, 'r') as f:
                data = json.load(f)
                return data.get('bin_positions', DEFAULT_BIN_POSITIONS), data.get('tolerance', 0.5)
        except:
            pass
    return DEFAULT_BIN_POSITIONS, 0.5

def save_calibration(bin_positions, tolerance):
    """Save calibration to file"""
    data = {
        'bin_positions': bin_positions,
        'tolerance': tolerance,
        'timestamp': time.strftime('%Y-%m-%d %H:%M:%S')
    }
    with open(CALIBRATION_FILE, 'w') as f:
        json.dump(data, f, indent=2)
    print(f"Calibration saved: {len(bin_positions)} bins with ±{tolerance:.1f} in tolerance")

def quick_calibration():
    """Quick calibration through all bins"""
    print("\n=== Quick Calibration ===")
    print("Place an object at each bin position when prompted")
    print("-" * 40)
    
    try:
        sensor = DistanceSensor(echo=ECHO_PIN, trigger=TRIGGER_PIN, max_distance=4.0)
        bin_positions = []
        
        for i, bin_name in enumerate(BIN_NAMES):
            print(f"\nPosition object at {bin_name}")
            input("Press Enter when ready...")
            
            # Take 5 readings
            readings = []
            for j in range(5):
                try:
                    distance_m = sensor.distance
                    distance_inches = distance_m * 39.3701
                    readings.append(distance_inches)
                    print(f"  Reading {j+1}: {distance_inches:.1f} in")
                    time.sleep(0.3)
                except Exception as e:
                    print(f"  Reading {j+1}: Error - {e}")
            
            if readings:
                avg_distance = sum(readings) / len(readings)
                bin_positions.append(avg_distance)
                print(f"  {bin_name}: {avg_distance:.1f} in")
            else:
                print(f"  No valid readings for {bin_name}, using default")
                bin_positions.append(DEFAULT_BIN_POSITIONS[i])
        
        # Get tolerance from user
        print(f"\nBin positions:")
        for i, (name, pos) in enumerate(zip(BIN_NAMES, bin_positions)):
            print(f"  {name}: {pos:.1f} in")
        
        while True:
            try:
                tolerance = float(input("\nEnter tolerance (inches): ").strip())
                if tolerance > 0:
                    break
                else:
                    print("Tolerance must be positive")
            except ValueError:
                print("Please enter a valid number")
        
        # Save calibration
        save_calibration(bin_positions, tolerance)
        return bin_positions, tolerance
        
    except Exception as e:
        print(f"Error during calibration: {e}")
        return DEFAULT_BIN_POSITIONS, 0.5
    finally:
        try:
            sensor.close()
        except:
            pass

def continuous_monitoring():
    """Continuous bin monitoring with debounce"""
    bin_positions, tolerance = load_calibration()
    detector = BinDetector(bin_positions, tolerance)
    
    print("\n=== Continuous Bin Monitoring ===")
    print(f"Tolerance: ±{tolerance:.1f} in")
    print("Bin positions:")
    for i, (name, pos) in enumerate(zip(BIN_NAMES, bin_positions)):
        print(f"  {name}: {pos:.1f} in")
    print("Press Ctrl+C to stop")
    print("-" * 40)
    
    try:
        sensor = DistanceSensor(echo=ECHO_PIN, trigger=TRIGGER_PIN, max_distance=4.0)
        last_display = None
        
        while True:
            try:
                distance_m = sensor.distance
                distance_inches = distance_m * 39.3701
                
                # Get immediate and debounced detection
                immediate_bin = detector.get_bin(distance_inches)
                debounced_bin = detector.get_debounced_bin(distance_inches)
                
                # Create display string
                if debounced_bin:
                    display = f"🎯 ACTIVE: {debounced_bin} | Distance: {distance_inches:.1f} in"
                elif immediate_bin:
                    display = f"⏳ DETECTING: {immediate_bin} | Distance: {distance_inches:.1f} in"
                else:
                    display = f"📡 NO BIN | Distance: {distance_inches:.1f} in"
                
                # Only update if display changed
                if display != last_display:
                    print(f"\n{display}")
                    last_display = display
                else:
                    print(f"{display}", end='\r')
                
                time.sleep(0.2)
                
            except KeyboardInterrupt:
                print("\n\nMonitoring stopped")
                break
            except Exception as e:
                print(f"\nError: {e}")
                time.sleep(1)
                
    except Exception as e:
        print(f"Error setting up sensor: {e}")
    finally:
        try:
            sensor.close()
        except:
            pass

def main():
    """Main menu"""
    bin_positions, tolerance = load_calibration()
    
    print("Simple Bin Detector")
    print("=" * 30)
    print(f"Current tolerance: ±{tolerance:.1f} in")
    print("Bin positions:")
    for i, (name, pos) in enumerate(zip(BIN_NAMES, bin_positions)):
        print(f"  {name}: {pos:.1f} in")
    
    while True:
        print("\nOptions:")
        print("1. Quick calibration")
        print("2. Continuous monitoring")
        print("3. Exit")
        
        choice = input("\nEnter choice (1-3): ").strip()
        
        if choice == "1":
            quick_calibration()
            # Reload after calibration
            bin_positions, tolerance = load_calibration()
        elif choice == "2":
            continuous_monitoring()
        elif choice == "3":
            print("Goodbye!")
            break
        else:
            print("Invalid choice")

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\nProgram interrupted")
    except Exception as e:
        print(f"\nUnexpected error: {e}") 