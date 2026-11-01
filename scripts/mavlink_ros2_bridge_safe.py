#!/usr/bin/env python3
# Safe-stage ROS 2 bridge: publishes ONLY zero velocity at 10 Hz.
import time
import rclpy
from rclpy.node import Node
from geometry_msgs.msg import Twist
from pymavlink import mavutil

class MAVLinkROS2Bridge(Node):
    def __init__(self):
        super().__init__('mavlink_ros2_bridge')
        self.publisher = self.create_publisher(Twist, '/cmd_vel', 10)
        self.mav = mavutil.mavlink_connection('udpin:127.0.0.1:14551')
        self.armed = False
        self.mode = None
        self.last_heartbeat = 0.0
        self.last_servo = 0.0
        self.last_log = 0.0
        self.create_timer(0.1, self.update)
        self.get_logger().info('Safe bridge: publishes zero velocity only')

    def update(self):
        now = time.monotonic()
        for _ in range(50):
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
                self.last_heartbeat = now
            elif msg.get_type() == 'SERVO_OUTPUT_RAW':
                self.last_servo = now
        self.publisher.publish(Twist())
        if now - self.last_log >= 2.0:
            hb_ok = now - self.last_heartbeat < 2.0
            servo_ok = now - self.last_servo < 1.0
            self.get_logger().info(f'ARM={self.armed} MODE={self.mode} HEARTBEAT_OK={hb_ok} SERVO_OK={servo_ok} CMD_VEL=0')
            self.last_log = now

    def close(self):
        for _ in range(5):
            self.publisher.publish(Twist())
            time.sleep(0.05)
        self.mav.close()

def main():
    rclpy.init()
    node = MAVLinkROS2Bridge()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.close()
        node.destroy_node()
        rclpy.shutdown()

if __name__ == '__main__':
    main()
