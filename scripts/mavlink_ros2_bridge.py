#!/usr/bin/env python3
# Historical diagnostic prototype. DOES NOT issue motion commands.
import time
from pymavlink import mavutil

PORT = 'udpin:127.0.0.1:14551'
PWM_NEUTRAL = 1500
PWM_RANGE = 500
mav = mavutil.mavlink_connection(PORT)
armed = False
mode = None
last_heartbeat = 0

def normalize(pwm):
    return max(-1.0, min(1.0, (pwm - PWM_NEUTRAL) / PWM_RANGE))

print('MAVLink -> ROS 2 bridge')
print('DIAGNOSTIC MODE: motors are not commanded')
try:
    while True:
        msg = mav.recv_match(type=['HEARTBEAT', 'SERVO_OUTPUT_RAW'], blocking=True, timeout=1)
        if msg is None or msg.get_srcSystem() != 1:
            continue
        if msg.get_type() == 'HEARTBEAT':
            if msg.get_srcComponent() != 1:
                continue
            armed = bool(msg.base_mode & 128)
            mode = msg.custom_mode
            last_heartbeat = time.monotonic()
        elif msg.get_type() == 'SERVO_OUTPUT_RAW':
            left = normalize(msg.servo1_raw)
            right = normalize(msg.servo3_raw)
            valid = armed and mode != 4 and time.monotonic() - last_heartbeat < 2
            linear = (left + right) / 2
            angular = (right - left) / 2
            if not valid:
                linear = 0.0
                angular = 0.0
            print(f'ARM={armed} MODE={mode} L={left:+.2f} R={right:+.2f} V={linear:+.2f} W={angular:+.2f}', flush=True)
except KeyboardInterrupt:
    print('\nStopped')
finally:
    mav.close()
