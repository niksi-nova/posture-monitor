import serial
import time

# Make sure start.bat is closed before running this!
# Change COM6 to whatever port your ESP32 is on.
print("Connecting to ESP32...")
ser = serial.Serial('COM6', 115200, timeout=2.0)
time.sleep(2)  # wait for serial connection to stabilize

print("Sending vibration command...")
ser.write(b"V\n")
ser.flush()
time.sleep(1)  # Wait for the motor to finish buzzing before closing!
print("Done!")

ser.close()
