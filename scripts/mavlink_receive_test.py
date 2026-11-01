#!/usr/bin/env python3
from pymavlink import mavutil
import time

master = mavutil.mavlink_connection('udpin:127.0.0.1:14551')
print('Waiting for MAVLink messages...')
end = time.monotonic() + 15
try:
    while time.monotonic() < end:
        msg = master.recv_match(type=['HEARTBEAT', 'SERVO_OUTPUT_RAW'], blocking=True, timeout=2)
        if msg is None:
            continue
        if msg.get_type() == 'HEARTBEAT':
            if msg.get_srcSystem() == 1 and msg.get_srcComponent() == 1:
                armed = bool(msg.base_mode & 128)
                print(f'Mode: {msg.custom_mode}, Armed: {armed}')
        elif msg.get_type() == 'SERVO_OUTPUT_RAW':
            print(f'Left: {msg.servo1_raw}, Right: {msg.servo3_raw}')
except KeyboardInterrupt:
    print('Interrupted')
finally:
    master.close()
