#!/usr/bin/env python3
"""
Bin Detector Script with Individual Calibration and Tolerance
Uses ultrasonic sensor to determine which bin is currently active
Supports individual calibration for each bin with tolerance settings
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
DEFAULT_BIN_TOLERANCES = [0.5, 0.5, 0.5, 0.5, 0.5, 0.5, 0.5, 0.5]  # inches (1/4 of 2" bin width)
BIN_NAMES = ['A1', 'A2', 'A3', 'A4', 'A5', 'A6', 'A7', 'A8']

# Calibration file
CALIBRATION_FILE = "bin_calibration.json"

# Debounce settings
DEBOUNCE_TIME = 1.0  # seconds

class BinDetector:
    """Bin detector with debounce functionality"""
    
    def __init__(self, bin_positions, bin_tolerances):
        self.bin_positions = bin_positions
        self.bin_tolerances = bin_tolerances
        self.last_bin = None
        self.last_bin_time = 0
        self.debounced_bin = None
    
    def get_active_bin(self, distance_inches):
        """
        Determine which bin is active based on distance and tolerance
        Returns the bin if distance is within tolerance of bin center
        """
        for i, (bin_distance, tolerance) in enumerate(zip(self.bin_positions, self.bin_tolerances)):
            # Check if distance is within tolerance of this bin
            if abs(distance_inches - bin_distance) <= tolerance:
                return BIN_NAMES[i], bin_distance, tolerance
        return None, None, None
    
    def get_debounced_bin(self, distance_inches):
        """
        Get the active bin with debounce applied
        Returns the debounced bin state
        """
        current_time = time.time()
        active_bin, bin_distance, tolerance = self.get_active_bin(distance_inches)
        
        # If no bin is detected, reset debounce immediately
        if active_bin is None:
            self.last_bin = None
            self.last_bin_time = 0
            self.debounced_bin = None
            return None, None, None
        
        # If this is a new bin or first detection
        if active_bin != self.last_bin:
            self.last_bin = active_bin
            self.last_bin_time = current_time
            return None, None, None  # Still in debounce period
        
        # If same bin detected, check if debounce period has passed
        if current_time - self.last_bin_time >= DEBOUNCE_TIME:
            if self.debounced_bin != active_bin:
                self.debounced_bin = active_bin
                return active_bin, bin_distance, tolerance
        
        # Still in debounce period
        return None, None, None

def load_calibration():
    """Load calibration data from file"""
    if os.path.exists(CALIBRATION_FILE):
        try:
            with open(CALIBRATION_FILE, 'r') as f:
                data = json.load(f)
                bin_positions = data.get('bin_positions', DEFAULT_BIN_POSITIONS)
                bin_tolerances = data.get('bin_tolerances', DEFAULT_BIN_TOLERANCES)
                return bin_positions, bin_tolerances
        except Exception as e:
            print(f"Warning: Could not load calibration file: {e}")
            return DEFAULT_BIN_POSITIONS, DEFAULT_BIN_TOLERANCES
    return DEFAULT_BIN_POSITIONS, DEFAULT_BIN_TOLERANCES

def save_calibration(bin_positions, bin_tolerances):
    """Save calibration data to file"""
    try:
        data = {
            'bin_positions': bin_positions,
            'bin_tolerances': bin_tolerances,
            'timestamp': time.strftime('%Y-%m-%d %H:%M:%S')
        }
        with open(CALIBRATION_FILE, 'w') as f:
            json.dump(data, f, indent=2)
        print(f"Calibration saved to {CALIBRATION_FILE}")
    except Exception as e:
        print(f"Error saving calibration: {e}")

def get_active_bin(distance_inches, bin_positions, bin_tolerances):
    """
    Determine which bin is active based on distance and tolerance
    Returns the bin if distance is within tolerance of bin center
    """
    for i, (bin_distance, tolerance) in enumerate(zip(bin_positions, bin_tolerances)):
        # Check if distance is within tolerance of this bin
        if abs(distance_inches - bin_distance) <= tolerance:
            return BIN_NAMES[i], bin_distance, tolerance
    return None, None, None

def calibrate_individual_bin(bin_name, expected_distance, current_tolerance):
    """Calibrate a single bin with multiple readings and tolerance setting"""
    
    print(f"\n=== Calibrating {bin_name} ===")
    print(f"Expected position: {expected_distance} inches")
    print(f"Current tolerance: {current_tolerance} inches")
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
            
            # Ask user to confirm or adjust position
            print(f"\nPosition options:")
            print(f"1. Use measured distance ({avg_distance:.1f} in)")
            print(f"2. Use expected distance ({expected_distance} in)")
            print(f"3. Enter custom distance")
            
            choice = input("Enter choice (1-3): ").strip()
            
            if choice == "1":
                final_distance = avg_distance
            elif choice == "2":
                final_distance = expected_distance
            elif choice == "3":
                final_distance = float(input("Enter custom distance (inches): "))
            else:
                print("Invalid choice, using measured distance")
                final_distance = avg_distance
            
            # Now set tolerance
            print(f"\nTolerance setting for {bin_name}:")
            print(f"Current tolerance: {current_tolerance} inches")
            print(f"Recommended tolerance: 1/4 of bin width")
            
            # Calculate recommended tolerance based on bin spacing
            if bin_name == 'A1':
                # For first bin, use distance to next bin
                next_bin_distance = 3.0  # Default A2 position
                recommended_tolerance = (next_bin_distance - final_distance) / 2
            elif bin_name == 'A8':
                # For last bin, use distance from previous bin
                prev_bin_distance = 13.0  # Default A7 position
                recommended_tolerance = (final_distance - prev_bin_distance) / 2
            else:
                # For middle bins, use average of distances to adjacent bins
                bin_index = BIN_NAMES.index(bin_name)
                if bin_index > 0 and bin_index < len(BIN_NAMES) - 1:
                    # This is a simplified calculation - in practice you'd use actual adjacent bin positions
                    recommended_tolerance = 0.5  # Default 1/4 of 2" bin width
                else:
                    recommended_tolerance = 0.5
            
            print(f"Recommended tolerance: {recommended_tolerance:.1f} inches")
            
            tolerance_choice = input("Enter tolerance (inches) or press Enter for recommended: ").strip()
            if tolerance_choice:
                try:
                    final_tolerance = float(tolerance_choice)
                except ValueError:
                    print("Invalid tolerance, using recommended")
                    final_tolerance = recommended_tolerance
            else:
                final_tolerance = recommended_tolerance
            
            print(f"{bin_name} calibrated to {final_distance:.1f} in ± {final_tolerance:.1f} in")
            return final_distance, final_tolerance
        else:
            print("No valid readings obtained")
            return expected_distance, current_tolerance
            
    except Exception as e:
        print(f"Error during calibration: {e}")
        return expected_distance, current_tolerance
    finally:
        try:
            sensor.close()
        except:
            pass

def full_calibration():
    """Full calibration for all bins with tolerance settings"""
    
    print("\n=== Full Bin Calibration ===")
    print("This will calibrate each bin individually with tolerance settings")
    print("You can skip any bin by pressing Enter without input")
    print("-" * 50)
    
    bin_positions, bin_tolerances = load_calibration()
    
    print("Current calibration:")
    for i, (name, pos, tol) in enumerate(zip(BIN_NAMES, bin_positions, bin_tolerances)):
        print(f"  {name}: {pos:.1f} in ± {tol:.1f} in")
    
    print("\nStarting calibration...")
    
    for i, bin_name in enumerate(BIN_NAMES):
        current_pos = bin_positions[i]
        current_tolerance = bin_tolerances[i]
        print(f"\n{'='*20}")
        print(f"Calibrating {bin_name}")
        print(f"Current position: {current_pos:.1f} in ± {current_tolerance:.1f} in")
        
        # Ask if user wants to calibrate this bin
        calibrate = input(f"Calibrate {bin_name}? (y/n, default=y): ").strip().lower()
        if calibrate in ['n', 'no']:
            print(f"Skipping {bin_name}")
            continue
        
        # Calibrate the bin
        new_position, new_tolerance = calibrate_individual_bin(bin_name, current_pos, current_tolerance)
        bin_positions[i] = new_position
        bin_tolerances[i] = new_tolerance
        print(f"{bin_name} calibrated to {new_position:.1f} in ± {new_tolerance:.1f} in")
    
    # Show final calibration
    print("\n" + "="*50)
    print("FINAL CALIBRATION:")
    print("="*50)
    for i, (name, pos, tol) in enumerate(zip(BIN_NAMES, bin_positions, bin_tolerances)):
        print(f"  {name}: {pos:.1f} in ± {tol:.1f} in")
    
    # Save calibration
    save_choice = input("\nSave this calibration? (y/n): ").strip().lower()
    if save_choice in ['y', 'yes']:
        save_calibration(bin_positions, bin_tolerances)
        print("Calibration saved!")
    else:
        print("Calibration not saved")

def quick_calibration():
    """Quick calibration - measure all bins in sequence with tolerance"""
    
    print("\n=== Quick Calibration ===")
    print("This will measure all bins in sequence")
    print("Place an object at each bin position when prompted")
    print("Tolerance will be set to 0.5 inches (1/4 of 2\" bin width)")
    print("-" * 40)
    
    try:
        sensor = DistanceSensor(
            echo=ECHO_PIN,
            trigger=TRIGGER_PIN,
            max_distance=4.0,
            threshold_distance=0.1
        )
        
        bin_positions = []
        bin_tolerances = []
        
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
                bin_tolerances.append(0.5)  # Default tolerance
                print(f"  {bin_name} calibrated to {avg_distance:.1f} in ± 0.5 in")
            else:
                print(f"  No valid readings for {bin_name}, using default")
                bin_positions.append(DEFAULT_BIN_POSITIONS[i])
                bin_tolerances.append(DEFAULT_BIN_TOLERANCES[i])
        
        # Show results
        print("\n" + "="*40)
        print("CALIBRATION RESULTS:")
        print("="*40)
        for i, (name, pos, tol) in enumerate(zip(BIN_NAMES, bin_positions, bin_tolerances)):
            print(f"  {name}: {pos:.1f} in ± {tol:.1f} in")
        
        # Save calibration
        save_choice = input("\nSave this calibration? (y/n): ").strip().lower()
        if save_choice in ['y', 'yes']:
            save_calibration(bin_positions, bin_tolerances)
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
    """Test bin detection with current calibration and tolerance"""
    
    bin_positions, bin_tolerances = load_calibration()
    detector = BinDetector(bin_positions, bin_tolerances)
    
    print("=== Bin Detection Test ===")
    print("Current bin positions (inches from sensor):")
    for i, (name, pos, tol) in enumerate(zip(BIN_NAMES, bin_positions, bin_tolerances)):
        print(f"  {name}: {pos:.1f} in ± {tol:.1f} in")
    print("=" * 40)
    
    try:
        sensor = DistanceSensor(
            echo=ECHO_PIN,
            trigger=TRIGGER_PIN,
            max_distance=4.0,
            threshold_distance=0.1
        )
        
        print("Taking 20 readings to test bin detection with debounce...")
        print("-" * 40)
        
        readings = []
        bin_counts = {}
        debounced_bin_counts = {}
        
        for i in range(20):
            try:
                distance_m = sensor.distance
                distance_inches = distance_m * 39.3701
                readings.append(distance_inches)
                
                # Get immediate detection
                active_bin, bin_distance, tolerance = detector.get_active_bin(distance_inches)
                
                # Get debounced detection
                debounced_bin, debounced_distance, debounced_tolerance = detector.get_debounced_bin(distance_inches)
                
                if active_bin:
                    bin_counts[active_bin] = bin_counts.get(active_bin, 0) + 1
                    print(f"Reading {i+1:2d}: {distance_inches:.1f} in → {active_bin} (center: {bin_distance:.1f} in ± {tolerance:.1f} in)", end='')
                else:
                    print(f"Reading {i+1:2d}: {distance_inches:.1f} in → No bin detected (outside tolerance)", end='')
                
                if debounced_bin:
                    debounced_bin_counts[debounced_bin] = debounced_bin_counts.get(debounced_bin, 0) + 1
                    print(f" [DEBOUNCED: {debounced_bin}]")
                else:
                    print(" [No debounced bin]")
                
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
            
            # Show immediate bin detection results
            print("\nIMMEDIATE BIN DETECTION RESULTS:")
            if bin_counts:
                for bin_name in BIN_NAMES:
                    count = bin_counts.get(bin_name, 0)
                    percentage = (count / len(readings)) * 100
                    print(f"  {bin_name}: {count}/{len(readings)} readings ({percentage:.0f}%)")
            else:
                print("  No bins detected in any reading")
            
            # Show debounced bin detection results
            print("\nDEBOUNCED BIN DETECTION RESULTS:")
            if debounced_bin_counts:
                for bin_name in BIN_NAMES:
                    count = debounced_bin_counts.get(bin_name, 0)
                    percentage = (count / len(readings)) * 100
                    print(f"  {bin_name}: {count}/{len(readings)} readings ({percentage:.0f}%)")
            else:
                print("  No debounced bins detected")
                
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
    """Continuously monitor and display the active bin with tolerance"""
    
    bin_positions, bin_tolerances = load_calibration()
    detector = BinDetector(bin_positions, bin_tolerances)
    
    print("\n=== Continuous Bin Monitoring ===")
    print("Current calibration:")
    for i, (name, pos, tol) in enumerate(zip(BIN_NAMES, bin_positions, bin_tolerances)):
        print(f"  {name}: {pos:.1f} in ± {tol:.1f} in")
    print("Press Ctrl+C to stop")
    print("-" * 40)
    
    try:
        sensor = DistanceSensor(
            echo=ECHO_PIN,
            trigger=TRIGGER_PIN,
            max_distance=4.0,
            threshold_distance=0.1
        )
        
        last_debounced_bin = None
        debounce_start_time = None
        
        while True:
            try:
                distance_m = sensor.distance
                distance_inches = distance_m * 39.3701
                
                # Get immediate detection
                active_bin, bin_distance, tolerance = detector.get_active_bin(distance_inches)
                
                # Get debounced detection
                debounced_bin, debounced_distance, debounced_tolerance = detector.get_debounced_bin(distance_inches)
                
                # Track debounce status
                if active_bin and debounced_bin is None:
                    if debounce_start_time is None:
                        debounce_start_time = time.time()
                        print(f"\n🔍 DETECTING: {active_bin} (Distance: {distance_inches:.1f} in) - Debouncing...")
                elif active_bin is None:
                    debounce_start_time = None
                
                # Only update display if debounced bin changes
                if debounced_bin != last_debounced_bin:
                    if debounced_bin:
                        print(f"\n🎯 ACTIVE BIN: {debounced_bin} (Distance: {distance_inches:.1f} in, Center: {debounced_distance:.1f} in ± {debounced_tolerance:.1f} in)")
                    else:
                        print(f"\n❌ NO BIN: Distance {distance_inches:.1f} in (outside tolerance)")
                    last_debounced_bin = debounced_bin
                else:
                    # Show current status
                    if debounced_bin:
                        print(f"Active: {debounced_bin} | Distance: {distance_inches:.1f} in | Center: {debounced_distance:.1f} in ± {debounced_tolerance:.1f} in", end='\r')
                    elif active_bin:
                        print(f"Detecting: {active_bin} | Distance: {distance_inches:.1f} in | Debouncing...", end='\r')
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
    
    bin_positions, bin_tolerances = load_calibration()
    
    print("Bin Detection System with Calibration and Tolerance")
    print("=" * 50)
    print("Current bin positions:")
    for i, (name, pos, tol) in enumerate(zip(BIN_NAMES, bin_positions, bin_tolerances)):
        print(f"  {name}: {pos:.1f} in ± {tol:.1f} in")
    
    while True:
        print("\nSelect mode:")
        print("1. Test bin detection (20 readings)")
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
    
    bin_positions, bin_tolerances = load_calibration()
    
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
    
    print("\nBin positions and tolerances:")
    for i, (name, pos, tol) in enumerate(zip(BIN_NAMES, bin_positions, bin_tolerances)):
        print(f"  {name}: {pos:.1f} in ± {tol:.1f} in")
    
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