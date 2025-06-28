#!/usr/bin/env python3
"""
Ultrasonic Sensor Test Script
Tests HC-SR04 or similar ultrasonic distance sensor using gpiozero
"""

import time
import gpiozero
from gpiozero import DistanceSensor
import statistics

# GPIO pin configuration for ultrasonic sensor
TRIGGER_PIN = 23  # GPIO23
ECHO_PIN = 24     # GPIO24

def test_ultrasonic_sensor():
    """Test the ultrasonic sensor with multiple readings and statistics"""
    
    print("=== Ultrasonic Sensor Test ===")
    print(f"Trigger Pin: GPIO{TRIGGER_PIN}")
    print(f"Echo Pin: GPIO{ECHO_PIN}")
    print("=" * 30)
    
    try:
        # Initialize the distance sensor
        # max_distance=4.0 meters, threshold_distance=0.1 meters
        sensor = DistanceSensor(
            echo=ECHO_PIN,
            trigger=TRIGGER_PIN,
            max_distance=4.0,
            threshold_distance=0.1
        )
        
        print("Sensor initialized successfully!")
        print("Taking 10 distance measurements...")
        print("-" * 30)
        
        # Take multiple readings for accuracy
        readings = []
        for i in range(10):
            try:
                distance = sensor.distance
                readings.append(distance)
                print(f"Reading {i+1:2d}: {distance:.3f} meters ({distance*100:.1f} cm)")
                time.sleep(0.5)  # Wait between readings
            except Exception as e:
                print(f"Reading {i+1:2d}: Error - {e}")
                time.sleep(0.5)
        
        if readings:
            # Calculate statistics
            avg_distance = statistics.mean(readings)
            median_distance = statistics.median(readings)
            min_distance = min(readings)
            max_distance = max(readings)
            std_dev = statistics.stdev(readings) if len(readings) > 1 else 0
            
            print("-" * 30)
            print("STATISTICS:")
            print(f"Average:     {avg_distance:.3f} m ({avg_distance*100:.1f} cm)")
            print(f"Median:      {median_distance:.3f} m ({median_distance*100:.1f} cm)")
            print(f"Min:         {min_distance:.3f} m ({min_distance*100:.1f} cm)")
            print(f"Max:         {max_distance:.3f} m ({max_distance*100:.1f} cm)")
            print(f"Std Dev:     {std_dev:.3f} m ({std_dev*100:.1f} cm)")
            print(f"Range:       {max_distance - min_distance:.3f} m ({(max_distance - min_distance)*100:.1f} cm)")
            
            # Quality assessment
            if std_dev < 0.01:  # Less than 1cm standard deviation
                print("✅ Excellent consistency")
            elif std_dev < 0.02:  # Less than 2cm standard deviation
                print("✅ Good consistency")
            elif std_dev < 0.05:  # Less than 5cm standard deviation
                print("⚠️  Moderate consistency")
            else:
                print("❌ Poor consistency - check sensor placement")
                
        else:
            print("❌ No successful readings obtained")
            
    except Exception as e:
        print(f"❌ Error initializing sensor: {e}")
        print("\nTroubleshooting tips:")
        print("1. Check GPIO pin connections")
        print("2. Ensure sensor has proper power (5V)")
        print("3. Verify trigger and echo pins are correct")
        print("4. Check for loose connections")
        return False
    
    finally:
        try:
            sensor.close()
            print("\nSensor resources cleaned up")
        except:
            pass
    
    return True

def continuous_monitoring():
    """Continuous distance monitoring with real-time display"""
    
    print("\n=== Continuous Monitoring Mode ===")
    print("Press Ctrl+C to stop")
    print("-" * 30)
    
    try:
        sensor = DistanceSensor(
            echo=ECHO_PIN,
            trigger=TRIGGER_PIN,
            max_distance=4.0,
            threshold_distance=0.1
        )
        
        while True:
            try:
                distance = sensor.distance
                print(f"Distance: {distance:.3f} m ({distance*100:.1f} cm)", end='\r')
                time.sleep(0.1)
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

def proximity_detection():
    """Test proximity detection with configurable threshold"""
    
    print("\n=== Proximity Detection Test ===")
    threshold = float(input("Enter proximity threshold in meters (e.g., 0.5): ") or "0.5")
    
    try:
        sensor = DistanceSensor(
            echo=ECHO_PIN,
            trigger=TRIGGER_PIN,
            max_distance=4.0,
            threshold_distance=threshold
        )
        
        print(f"Monitoring for objects closer than {threshold} meters...")
        print("Press Ctrl+C to stop")
        print("-" * 40)
        
        while True:
            try:
                distance = sensor.distance
                if distance < threshold:
                    print(f"🚨 PROXIMITY ALERT: {distance:.3f} m ({distance*100:.1f} cm)")
                else:
                    print(f"Distance: {distance:.3f} m ({distance*100:.1f} cm) - Safe", end='\r')
                time.sleep(0.2)
            except KeyboardInterrupt:
                print("\n\nProximity detection stopped")
                break
            except Exception as e:
                print(f"\nError: {e}")
                time.sleep(1)
                
    except Exception as e:
        print(f"❌ Error in proximity mode: {e}")
    finally:
        try:
            sensor.close()
        except:
            pass

def main():
    """Main menu for ultrasonic sensor testing"""
    
    print("Ultrasonic Sensor Test Suite")
    print("=" * 30)
    
    while True:
        print("\nSelect test mode:")
        print("1. Basic sensor test (10 readings)")
        print("2. Continuous monitoring")
        print("3. Proximity detection")
        print("4. Exit")
        
        choice = input("\nEnter choice (1-4): ").strip()
        
        if choice == "1":
            test_ultrasonic_sensor()
        elif choice == "2":
            continuous_monitoring()
        elif choice == "3":
            proximity_detection()
        elif choice == "4":
            print("Goodbye!")
            break
        else:
            print("Invalid choice. Please enter 1-4.")

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\nTest interrupted by user")
    except Exception as e:
        print(f"\nUnexpected error: {e}")
