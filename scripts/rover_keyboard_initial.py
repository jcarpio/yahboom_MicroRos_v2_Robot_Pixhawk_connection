#!/usr/bin/env python3
# Historical initial WASD prototype, superseded by rover_keyboard.py.
import curses
import time
from pymavlink import mavutil

PORT = 'udpin:127.0.0.1:14552'
NEUTRAL = 1500
STEP = 60
RATE = 10
KEY_TIMEOUT = 0.25
MAX_DURATION = 120.0
MANUAL = 0

def send_rc(mav, steering, throttle):
    channels = [65535] * 18
    channels[0] = steering
    channels[2] = throttle
    mav.mav.rc_channels_override_send(1, 1, *channels)

def main(stdscr):
    curses.curs_set(0)
    stdscr.nodelay(True)
    stdscr.keypad(True)
    mav = mavutil.mavlink_connection(PORT, source_system=254)
    armed = False
    mode = None
    last_hb = 0.0
    stdscr.addstr(0, 0, 'Waiting for Pixhawk via MAVLink...')
    end_wait = time.monotonic() + 10
    while time.monotonic() < end_wait:
        msg = mav.recv_match(blocking=False)
        if msg and msg.get_type() == 'HEARTBEAT':
            if msg.get_srcSystem() == 1 and msg.get_srcComponent() == 1:
                last_hb = time.monotonic()
                armed = bool(msg.base_mode & 128)
                mode = msg.custom_mode
                break
        time.sleep(0.05)
    if last_hb == 0:
        mav.close()
        raise RuntimeError('No Pixhawk heartbeat received')
    start = time.monotonic()
    last_key_time = 0.0
    last_key = None
    interval = 1.0 / RATE
    try:
        while time.monotonic() - start < MAX_DURATION:
            tick = time.monotonic()
            for _ in range(40):
                msg = mav.recv_match(blocking=False)
                if msg is None:
                    break
                if msg.get_type() == 'HEARTBEAT' and msg.get_srcSystem() == 1 and msg.get_srcComponent() == 1:
                    last_hb = time.monotonic()
                    armed = bool(msg.base_mode & 128)
                    mode = msg.custom_mode
            key = stdscr.getch()
            if key in (ord('q'), ord('Q')):
                break
            if key == ord(' '):
                last_key = None
                last_key_time = 0.0
            elif key in [ord(c) for c in 'wWaAsSdD']:
                last_key = chr(key).lower()
                last_key_time = time.monotonic()
            steer = NEUTRAL
            throttle = NEUTRAL
            hb_ok = time.monotonic() - last_hb < 2.0
            allowed = armed and mode == MANUAL and hb_ok
            if allowed and time.monotonic() - last_key_time < KEY_TIMEOUT:
                if last_key == 'w':
                    throttle = NEUTRAL + STEP
                elif last_key == 's':
                    throttle = NEUTRAL - STEP
                elif last_key == 'a':
                    steer = NEUTRAL - STEP
                elif last_key == 'd':
                    steer = NEUTRAL + STEP
            send_rc(mav, steer, throttle)
            stdscr.erase()
            stdscr.addstr(0, 0, 'YAHBOOM - WASD CONTROL')
            stdscr.addstr(2, 0, 'W forward   S reverse')
            stdscr.addstr(3, 0, 'A left      D right')
            stdscr.addstr(4, 0, 'SPACE neutral   Q quit')
            stdscr.addstr(6, 0, f'ARM={armed} MODE={mode}')
            stdscr.addstr(7, 0, f'HEARTBEAT_OK={hb_ok}')
            stdscr.addstr(8, 0, f'RC1={steer} RC3={throttle}')
            stdscr.refresh()
            time.sleep(max(0.0, interval - (time.monotonic() - tick)))
    finally:
        for _ in range(10):
            send_rc(mav, NEUTRAL, NEUTRAL)
            time.sleep(0.05)
        mav.close()

if __name__ == '__main__':
    curses.wrapper(main)
