#!/usr/bin/env python3
"""
Bin Detector Script
Uses ultrasonic sensor to determine which bin is currently active
Bins are positioned at 1, 3, 5, 7, 9, 11, 13, and 15 inches from sensor
"""

import time
import gpiozero
from gpiozero import DistanceSensor
import statistics

# GPIO pin configuration for ultrasonic sensor
TRIGGER_PIN = 23  # GPIO23
ECHO_PIN = 24     # GPIO24

# Bin positions (in inches from sensor)
BIN_POSITIONS = [1, 3, 5, 7, 9, 11, 13, 15]  # inches
BIN_NAMES = ['A1', 'A2', 'A3', 'A4', 'A5', 'A6', 'A7', 'A8']

def get_active_bin(distance_inches):
    """
    Determine which bin is active based on distance
    Returns the first bin whose center distance is greater than the measured distance
    """
    for i, bin_distance in enumerate(BIN_POSITIONS):
        if distance_inches < bin_distance:
            return BIN_NAMES[i], bin_distance
    return None, None

def test_bin_detection():
    """Test bin detection with multiple readings"""
    
    print("=== Bin Detection Test ===")
    print("Bin positions (inches from sensor):")
    for i, (name, pos) in enumerate(zip(BIN_NAMES, BIN_POSITIONS)):
        print(f"  {name}: {pos} inches")
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
                
                active_bin, bin_distance = get_active_bin(distance_inches)
                
                if active_bin:
                    bin_counts[active_bin] = bin_counts.get(active_bin, 0) + 1
                    print(f"Reading {i+1:2d}: {distance_inches:.1f} in → {active_bin} (center: {bin_distance} in)")
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
    
    print("\n=== Continuous Bin Monitoring ===")
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
                active_bin, bin_distance = get_active_bin(distance_inches)
                
                # Only update display if bin changes
                if active_bin != last_bin:
                    if active_bin:
                        print(f"\n🎯 ACTIVE BIN: {active_bin} (Distance: {distance_inches:.1f} in, Center: {bin_distance} in)")
                    else:
                        print(f"\n❌ NO BIN: Distance {distance_inches:.1f} in (too far)")
                    last_bin = active_bin
                else:
                    # Show current status
                    if active_bin:
                        print(f"Active: {active_bin} | Distance: {distance_inches:.1f} in | Center: {bin_distance} in", end='\r')
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

def bin_calibration():
    """Calibration mode to help position bins correctly"""
    
    print("\n=== Bin Calibration Mode ===")
    print("This mode helps you position bins at the correct distances")
    print("Place an object at each bin position and record the readings")
    print("-" * 50)
    
    try:
        sensor = DistanceSensor(
            echo=ECHO_PIN,
            trigger=TRIGGER_PIN,
            max_distance=4.0,
            threshold_distance=0.1
        )
        
        calibration_data = {}
        
        for i, (bin_name, expected_distance) in enumerate(zip(BIN_NAMES, BIN_POSITIONS)):
            print(f"\nPosition object at {bin_name} (expected: {expected_distance} inches)")
            input("Press Enter when ready to measure...")
            
            # Take multiple readings for accuracy
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
                std_dev = statistics.stdev(readings) if len(readings) > 1 else 0
                calibration_data[bin_name] = {
                    'expected': expected_distance,
                    'measured': avg_distance,
                    'std_dev': std_dev,
                    'difference': avg_distance - expected_distance
                }
                
                print(f"  Average: {avg_distance:.1f} in")
                print(f"  Difference from expected: {avg_distance - expected_distance:+.1f} in")
        
        # Show calibration summary
        print("\n" + "=" * 50)
        print("CALIBRATION SUMMARY:")
        print("=" * 50)
        print(f"{'Bin':<4} {'Expected':<9} {'Measured':<9} {'Diff':<6} {'Std Dev':<8}")
        print("-" * 50)
        
        for bin_name in BIN_NAMES:
            data = calibration_data[bin_name]
            print(f"{bin_name:<4} {data['expected']:<9.1f} {data['measured']:<9.1f} "
                  f"{data['difference']:<+6.1f} {data['std_dev']:<8.1f}")
        
        print("\nRecommendations:")
        for bin_name in BIN_NAMES:
            data = calibration_data[bin_name]
            if abs(data['difference']) > 0.5:
                print(f"  {bin_name}: Adjust position by {data['difference']:+.1f} inches")
            else:
                print(f"  {bin_name}: Position looks good (±0.5 in tolerance)")
                
    except Exception as e:
        print(f"❌ Error in calibration mode: {e}")
    finally:
        try:
            sensor.close()
        except:
            pass

def main():
    """Main menu for bin detection testing"""
    
    print("Bin Detection System")
    print("=" * 30)
    print("Bin positions: 1, 3, 5, 7, 9, 11, 13, 15 inches from sensor")
    
    while True:
        print("\nSelect mode:")
        print("1. Test bin detection (10 readings)")
        print("2. Continuous bin monitoring")
        print("3. Bin calibration mode")
        print("4. Exit")
        
        choice = input("\nEnter choice (1-4): ").strip()
        
        if choice == "1":
            test_bin_detection()
        elif choice == "2":
            continuous_bin_monitoring()
        elif choice == "3":
            bin_calibration()
        elif choice == "4":
            print("Goodbye!")
            break
        else:
            print("Invalid choice. Please enter 1-4.")

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\nProgram interrupted by user")
    except Exception as e:
        print(f"\nUnexpected error: {e}") 