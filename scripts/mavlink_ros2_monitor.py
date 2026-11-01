#!/usr/bin/env python3
# ROS 2 node for telemetry monitoring only; no /cmd_vel publisher.
import time
import rclpy
from rclpy.node import Node
from pymavlink import mavutil

class MAVLinkMonitor(Node):
    def __init__(self):
        super().__init__('mavlink_ros2_monitor')
        self.mav = mavutil.mavlink_connection('udpin:127.0.0.1:14551')
        self.armed = False
        self.mode = None
        self.last_heartbeat = 0.0
        self.last_servo = 0.0
        self.create_timer(0.1, self.update)
        self.get_logger().info('Monitor started; no motor commands published')

    def update(self):
        for _ in range(30):
            msg = self.mav.recv_match(blocking=False)
            if msg is None:
                break
            if msg.get_srcSystem() != 1:
                continue
            if msg.get_type() == 'HEARTBEAT':
                if msg.get_srcComponent() != 1:
                    continue
                self.armed = bool(msg.base_mode & 128)
                self.mode = msg.custom_mode
                self.last_heartbeat = time.monotonic()
            elif msg.get_type() == 'SERVO_OUTPUT_RAW':
                left = (msg.servo1_raw - 1500) / 500.0
                right = (msg.servo3_raw - 1500) / 500.0
                self.last_servo = time.monotonic()
                self.get_logger().info(f'ARM={self.armed} MODE={self.mode} L={left:+.2f} R={right:+.2f}')

def main():
    rclpy.init()
    node = MAVLinkMonitor()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.mav.close()
        node.destroy_node()
        rclpy.shutdown()

if __name__ == '__main__':
    main()
