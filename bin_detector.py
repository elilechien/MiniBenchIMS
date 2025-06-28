#!/usr/bin/env python3
"""
Bin Detector Script with Individual Calibration
Uses ultrasonic sensor to determine which bin is currently active
Supports individual calibration for each bin
"""

import time
import gpiozero
from gpiozero import DistanceSensor
import statistics
import json
import os

# GPIO pin configuration for ultrasonic sensor
TRIGGER_PIN = 23  # GPIO23
ECHO_PIN = 24     # GPIO24

# Default bin positions (in inches from sensor) - can be calibrated
DEFAULT_BIN_POSITIONS = [1, 3, 5, 7, 9, 11, 13, 15]  # inches
BIN_NAMES = ['A1', 'A2', 'A3', 'A4', 'A5', 'A6', 'A7', 'A8']

# Calibration file
CALIBRATION_FILE = "bin_calibration.json"

def load_calibration():
    """Load calibration data from file"""
    if os.path.exists(CALIBRATION_FILE):
        try:
            with open(CALIBRATION_FILE, 'r') as f:
                data = json.load(f)
                return data.get('bin_positions', DEFAULT_BIN_POSITIONS)
        except Exception as e:
            print(f"Warning: Could not load calibration file: {e}")
            return DEFAULT_BIN_POSITIONS
    return DEFAULT_BIN_POSITIONS

def save_calibration(bin_positions):
    """Save calibration data to file"""
    try:
        data = {
            'bin_positions': bin_positions,
            'timestamp': time.strftime('%Y-%m-%d %H:%M:%S')
        }
        with open(CALIBRATION_FILE, 'w') as f:
            json.dump(data, f, indent=2)
        print(f"Calibration saved to {CALIBRATION_FILE}")
    except Exception as e:
        print(f"Error saving calibration: {e}")

def get_active_bin(distance_inches, bin_positions):
    """
    Determine which bin is active based on distance
    Returns the first bin whose center distance is greater than the measured distance
    """
    for i, bin_distance in enumerate(bin_positions):
        if distance_inches < bin_distance:
            return BIN_NAMES[i], bin_distance
    return None, None

def calibrate_individual_bin(bin_name, expected_distance):
    """Calibrate a single bin with multiple readings"""
    
    print(f"\n=== Calibrating {bin_name} ===")
    print(f"Expected position: {expected_distance} inches")
    print("Place an object at this bin position")
    input("Press Enter when ready to measure...")
    
    try:
        sensor = DistanceSensor(
            echo=ECHO_PIN,
            trigger=TRIGGER_PIN,
            max_distance=4.0,
            threshold_distance=0.1
        )
        
        readings = []
        print("Taking 10 readings...")
        
        for i in range(10):
            try:
                distance_m = sensor.distance
                distance_inches = distance_m * 39.3701
                readings.append(distance_inches)
                print(f"  Reading {i+1:2d}: {distance_inches:.1f} in")
                time.sleep(0.3)
            except Exception as e:
                print(f"  Reading {i+1:2d}: Error - {e}")
        
        if readings:
            avg_distance = statistics.mean(readings)
            std_dev = statistics.stdev(readings) if len(readings) > 1 else 0
            difference = avg_distance - expected_distance
            
            print(f"\nResults for {bin_name}:")
            print(f"  Average distance: {avg_distance:.1f} in")
            print(f"  Standard deviation: {std_dev:.1f} in")
            print(f"  Difference from expected: {difference:+.1f} in")
            
            if abs(difference) > 0.5:
                print(f"  ⚠️  Large difference detected")
            
            # Ask user to confirm or adjust
            print(f"\nOptions:")
            print(f"1. Use measured distance ({avg_distance:.1f} in)")
            print(f"2. Use expected distance ({expected_distance} in)")
            print(f"3. Enter custom distance")
            
            choice = input("Enter choice (1-3): ").strip()
            
            if choice == "1":
                return avg_distance
            elif choice == "2":
                return expected_distance
            elif choice == "3":
                custom_distance = float(input("Enter custom distance (inches): "))
                return custom_distance
            else:
                print("Invalid choice, using measured distance")
                return avg_distance
        else:
            print("No valid readings obtained")
            return expected_distance
            
    except Exception as e:
        print(f"Error during calibration: {e}")
        return expected_distance
    finally:
        try:
            sensor.close()
        except:
            pass

def full_calibration():
    """Full calibration for all bins"""
    
    print("\n=== Full Bin Calibration ===")
    print("This will calibrate each bin individually")
    print("You can skip any bin by pressing Enter without input")
    print("-" * 50)
    
    bin_positions = load_calibration().copy()
    
    print("Current calibration:")
    for i, (name, pos) in enumerate(zip(BIN_NAMES, bin_positions)):
        print(f"  {name}: {pos} inches")
    
    print("\nStarting calibration...")
    
    for i, bin_name in enumerate(BIN_NAMES):
        current_pos = bin_positions[i]
        print(f"\n{'='*20}")
        print(f"Calibrating {bin_name}")
        print(f"Current position: {current_pos} inches")
        
        # Ask if user wants to calibrate this bin
        calibrate = input(f"Calibrate {bin_name}? (y/n, default=y): ").strip().lower()
        if calibrate in ['n', 'no']:
            print(f"Skipping {bin_name}")
            continue
        
        # Calibrate the bin
        new_position = calibrate_individual_bin(bin_name, current_pos)
        bin_positions[i] = new_position
        print(f"{bin_name} calibrated to {new_position:.1f} inches")
    
    # Show final calibration
    print("\n" + "="*50)
    print("FINAL CALIBRATION:")
    print("="*50)
    for i, (name, pos) in enumerate(zip(BIN_NAMES, bin_positions)):
        print(f"  {name}: {pos:.1f} inches")
    
    # Save calibration
    save_choice = input("\nSave this calibration? (y/n): ").strip().lower()
    if save_choice in ['y', 'yes']:
        save_calibration(bin_positions)
        print("Calibration saved!")
    else:
        print("Calibration not saved")

def quick_calibration():
    """Quick calibration - measure all bins in sequence"""
    
    print("\n=== Quick Calibration ===")
    print("This will measure all bins in sequence")
    print("Place an object at each bin position when prompted")
    print("-" * 40)
    
    try:
        sensor = DistanceSensor(
            echo=ECHO_PIN,
            trigger=TRIGGER_PIN,
            max_distance=4.0,
            threshold_distance=0.1
        )
        
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
                avg_distance = statistics.mean(readings)
                bin_positions.append(avg_distance)
                print(f"  {bin_name} calibrated to {avg_distance:.1f} inches")
            else:
                print(f"  No valid readings for {bin_name}, using default")
                bin_positions.append(DEFAULT_BIN_POSITIONS[i])
        
        # Show results
        print("\n" + "="*40)
        print("CALIBRATION RESULTS:")
        print("="*40)
        for i, (name, pos) in enumerate(zip(BIN_NAMES, bin_positions)):
            print(f"  {name}: {pos:.1f} inches")
        
        # Save calibration
        save_choice = input("\nSave this calibration? (y/n): ").strip().lower()
        if save_choice in ['y', 'yes']:
            save_calibration(bin_positions)
            print("Calibration saved!")
        else:
            print("Calibration not saved")
            
    except Exception as e:
        print(f"Error during quick calibration: {e}")
    finally:
        try:
            sensor.close()
        except:
            pass

def test_bin_detection():
    """Test bin detection with current calibration"""
    
    bin_positions = load_calibration()
    
    print("=== Bin Detection Test ===")
    print("Current bin positions (inches from sensor):")
    for i, (name, pos) in enumerate(zip(BIN_NAMES, bin_positions)):
        print(f"  {name}: {pos:.1f} inches")
    print("=" * 40)
    
    try:
        sensor = DistanceSensor(
            echo=ECHO_PIN,
            trigger=TRIGGER_PIN,
            max_distance=4.0,
            threshold_distance=0.1
        )
        
        print("Taking 10 readings to test bin detection...")
        print("-" * 40)
        
        readings = []
        bin_counts = {}
        
        for i in range(10):
            try:
                distance_m = sensor.distance
                distance_inches = distance_m * 39.3701
                readings.append(distance_inches)
                
                active_bin, bin_distance = get_active_bin(distance_inches, bin_positions)
                
                if active_bin:
                    bin_counts[active_bin] = bin_counts.get(active_bin, 0) + 1
                    print(f"Reading {i+1:2d}: {distance_inches:.1f} in → {active_bin} (center: {bin_distance:.1f} in)")
                else:
                    print(f"Reading {i+1:2d}: {distance_inches:.1f} in → No bin detected (too far)")
                
                time.sleep(0.5)
                
            except Exception as e:
                print(f"Reading {i+1:2d}: Error - {e}")
                time.sleep(0.5)
        
        if readings:
            # Calculate statistics
            avg_distance = statistics.mean(readings)
            std_dev = statistics.stdev(readings) if len(readings) > 1 else 0
            
            print("-" * 40)
            print("STATISTICS:")
            print(f"Average distance: {avg_distance:.1f} inches")
            print(f"Standard deviation: {std_dev:.1f} inches")
            
            # Show bin detection results
            print("\nBIN DETECTION RESULTS:")
            if bin_counts:
                for bin_name in BIN_NAMES:
                    count = bin_counts.get(bin_name, 0)
                    percentage = (count / len(readings)) * 100
                    print(f"  {bin_name}: {count}/{len(readings)} readings ({percentage:.0f}%)")
            else:
                print("  No bins detected in any reading")
                
    except Exception as e:
        print(f"❌ Error: {e}")
        return False
    finally:
        try:
            sensor.close()
        except:
            pass
    
    return True

def continuous_bin_monitoring():
    """Continuously monitor and display the active bin"""
    
    bin_positions = load_calibration()
    
    print("\n=== Continuous Bin Monitoring ===")
    print("Current calibration:")
    for i, (name, pos) in enumerate(zip(BIN_NAMES, bin_positions)):
        print(f"  {name}: {pos:.1f} inches")
    print("Press Ctrl+C to stop")
    print("-" * 40)
    
    try:
        sensor = DistanceSensor(
            echo=ECHO_PIN,
            trigger=TRIGGER_PIN,
            max_distance=4.0,
            threshold_distance=0.1
        )
        
        last_bin = None
        
        while True:
            try:
                distance_m = sensor.distance
                distance_inches = distance_m * 39.3701
                active_bin, bin_distance = get_active_bin(distance_inches, bin_positions)
                
                # Only update display if bin changes
                if active_bin != last_bin:
                    if active_bin:
                        print(f"\n🎯 ACTIVE BIN: {active_bin} (Distance: {distance_inches:.1f} in, Center: {bin_distance:.1f} in)")
                    else:
                        print(f"\n❌ NO BIN: Distance {distance_inches:.1f} in (too far)")
                    last_bin = active_bin
                else:
                    # Show current status
                    if active_bin:
                        print(f"Active: {active_bin} | Distance: {distance_inches:.1f} in | Center: {bin_distance:.1f} in", end='\r')
                    else:
                        print(f"No bin detected | Distance: {distance_inches:.1f} in", end='\r')
                
                time.sleep(0.2)
                
            except KeyboardInterrupt:
                print("\n\nMonitoring stopped by user")
                break
            except Exception as e:
                print(f"\nError: {e}")
                time.sleep(1)
                
    except Exception as e:
        print(f"❌ Error in continuous mode: {e}")
    finally:
        try:
            sensor.close()
        except:
            pass

def main():
    """Main menu for bin detection testing"""
    
    bin_positions = load_calibration()
    
    print("Bin Detection System with Calibration")
    print("=" * 40)
    print("Current bin positions:")
    for i, (name, pos) in enumerate(zip(BIN_NAMES, bin_positions)):
        print(f"  {name}: {pos:.1f} inches")
    
    while True:
        print("\nSelect mode:")
        print("1. Test bin detection (10 readings)")
        print("2. Continuous bin monitoring")
        print("3. Full calibration (individual bins)")
        print("4. Quick calibration (all bins)")
        print("5. View/Reset calibration")
        print("6. Exit")
        
        choice = input("\nEnter choice (1-6): ").strip()
        
        if choice == "1":
            test_bin_detection()
        elif choice == "2":
            continuous_bin_monitoring()
        elif choice == "3":
            full_calibration()
        elif choice == "4":
            quick_calibration()
        elif choice == "5":
            view_calibration()
        elif choice == "6":
            print("Goodbye!")
            break
        else:
            print("Invalid choice. Please enter 1-6.")

def view_calibration():
    """View current calibration and reset options"""
    
    bin_positions = load_calibration()
    
    print("\n=== Current Calibration ===")
    print(f"Calibration file: {CALIBRATION_FILE}")
    
    if os.path.exists(CALIBRATION_FILE):
        try:
            with open(CALIBRATION_FILE, 'r') as f:
                data = json.load(f)
                timestamp = data.get('timestamp', 'Unknown')
                print(f"Last saved: {timestamp}")
        except:
            print("Last saved: Unknown")
    
    print("\nBin positions:")
    for i, (name, pos) in enumerate(zip(BIN_NAMES, bin_positions)):
        print(f"  {name}: {pos:.1f} inches")
    
    print("\nOptions:")
    print("1. Reset to default positions")
    print("2. Back to main menu")
    
    choice = input("Enter choice (1-2): ").strip()
    
    if choice == "1":
        reset_choice = input("Are you sure you want to reset to default positions? (y/n): ").strip().lower()
        if reset_choice in ['y', 'yes']:
            if os.path.exists(CALIBRATION_FILE):
                os.remove(CALIBRATION_FILE)
                print("Calibration reset to defaults")
            else:
                print("No calibration file found, already using defaults")

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\nProgram interrupted by user")
    except Exception as e:
        print(f"\nUnexpected error: {e}") 