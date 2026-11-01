#!/usr/bin/env python3
# Final version used in the session. Bench-only; terminal key repeat may introduce lag.
import curses
import time
from pymavlink import mavutil

PORT = 'udpin:127.0.0.1:14552'
NEUTRAL = 1500
SPEED_LEVELS = [30, 60, 90, 120, 150]
STEERING_STEP = 60
KEY_TIMEOUT = 0.35
TEST_DURATION = 120.0
RATE = 10

def send_rc(mav, steering, throttle):
    channels = [65535] * 18
    channels[0] = steering
    channels[2] = throttle
    mav.mav.rc_channels_override_send(1, 1, *channels)

def main(stdscr):
    curses.curs_set(0)
    stdscr.nodelay(True)
    stdscr.keypad(True)
    mav = mavutil.mavlink_connection(PORT, source_system=254, source_component=190)
    armed = False
    mode = None
    last_heartbeat = 0.0
    speed_level = 0
    last_key = None
    last_key_time = 0.0
    start = time.monotonic()
    try:
        while time.monotonic() - start < TEST_DURATION:
            tick = time.monotonic()
            for _ in range(50):
                msg = mav.recv_match(blocking=False)
                if msg is None:
                    break
                if msg.get_type() == 'HEARTBEAT' and msg.get_srcSystem() == 1 and msg.get_srcComponent() == 1:
                    armed = bool(msg.base_mode & 128)
                    mode = msg.custom_mode
                    last_heartbeat = time.monotonic()
            key = stdscr.getch()
            if key in (ord('q'), ord('Q')):
                break
            elif key == ord(' '):
                last_key = None
                last_key_time = 0.0
            elif key in (ord('+'), ord('=')):
                speed_level = min(speed_level + 1, len(SPEED_LEVELS) - 1)
            elif key == ord('-'):
                speed_level = max(speed_level - 1, 0)
            elif key in (ord('w'), ord('W'), ord('a'), ord('A'), ord('s'), ord('S'), ord('d'), ord('D')):
                last_key = chr(key).lower()
                last_key_time = time.monotonic()
            steering = NEUTRAL
            throttle = NEUTRAL
            heartbeat_ok = time.monotonic() - last_heartbeat < 2.0 and last_heartbeat > 0
            enabled = heartbeat_ok and armed and mode == 0
            speed = SPEED_LEVELS[speed_level]
            if enabled and time.monotonic() - last_key_time < KEY_TIMEOUT:
                if last_key == 'w':
                    throttle = NEUTRAL + speed
                elif last_key == 's':
                    throttle = NEUTRAL - speed
                elif last_key == 'a':
                    steering = NEUTRAL - STEERING_STEP
                elif last_key == 'd':
                    steering = NEUTRAL + STEERING_STEP
            if heartbeat_ok:
                send_rc(mav, steering, throttle)
            stdscr.erase()
            stdscr.addstr(0, 0, 'YAHBOOM - WASD CONTROL')
            stdscr.addstr(2, 0, 'W: Forward   S: Reverse')
            stdscr.addstr(3, 0, 'A: Left      D: Right')
            stdscr.addstr(4, 0, '+: Faster    -: Slower')
            stdscr.addstr(5, 0, 'SPACE: Neutral   Q: Quit')
            stdscr.addstr(7, 0, f'Speed level {speed_level+1}/5 (PWM +/-{speed})')
            stdscr.addstr(8, 0, f'ARM={armed} MODE={mode} HB_OK={heartbeat_ok}')
            stdscr.addstr(9, 0, f'RC1={steering} RC3={throttle}')
            stdscr.addstr(10, 0, f'Movement enabled: {enabled}')
            stdscr.refresh()
            time.sleep(max(0.0, (1.0/RATE) - (time.monotonic() - tick)))
    finally:
        for _ in range(10):
            send_rc(mav, NEUTRAL, NEUTRAL)
            time.sleep(0.05)
        mav.close()

if __name__ == '__main__':
    curses.wrapper(main)
