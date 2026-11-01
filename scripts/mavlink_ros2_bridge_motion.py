#!/usr/bin/env python3
import time
import rclpy
from rclpy.node import Node
from rclpy.qos import QoSProfile, ReliabilityPolicy, DurabilityPolicy
from geometry_msgs.msg import Twist
from pymavlink import mavutil

# Configuraci\u00f3n de la prueba
MAVLINK_PORT = "udpin:127.0.0.1:14551"
TOPIC = "/cmd_vel"

PWM_CENTER = 1500
PWM_SPAN = 500

# L\u00edmites conservadores para las ruedas suspendidas
MAX_LINEAR = 0.08       # m/s
MAX_ANGULAR = 0.30      # rad/s

# Par\u00e1metros iniciales para la conversi\u00f3n.
# Se calibrar\u00e1n posteriormente.
NOMINAL_SPEED = 0.40    # m/s
WHEEL_SEPARATION = 0.22 # metros (provisional)

HEARTBEAT_TIMEOUT = 2.0
SERVO_TIMEOUT = 0.6
TEST_DURATION = 180.0

# ArduRover: MANUAL = 0, HOLD = 4
MANUAL_MODE = 0
AUTO_MODE = 10
HOLD_MODE = 4
RTL_MODE = 11


def clamp(value, low, high):
    return max(low, min(high, value))


class MAVLinkROS2Bridge(Node):

    def __init__(self):
        super().__init__("mavlink_ros2_bridge_motion")

        qos = QoSProfile(depth=10)
        qos.reliability = ReliabilityPolicy.BEST_EFFORT
        qos.durability = DurabilityPolicy.VOLATILE

        self.publisher = self.create_publisher(
            Twist, TOPIC, qos
        )

        self.mav = mavutil.mavlink_connection(
            MAVLINK_PORT
        )

        self.armed = False
        self.mode = None
        self.pwm_left = 1500
        self.pwm_right = 1500

        self.last_heartbeat = 0.0
        self.last_servo = 0.0
        self.started = time.monotonic()
        self.last_log = 0.0

        self.create_timer(0.1, self.update)

        self.get_logger().info(
            "Puente iniciado: movimiento limitado "
            "durante 30 segundos"
        )

    def read_mavlink(self):
        for _ in range(100):
            msg = self.mav.recv_match(blocking=False)

            if msg is None:
                break

            if msg.get_srcSystem() != 1:
                continue

            now = time.monotonic()
            kind = msg.get_type()

            if kind == "HEARTBEAT":
                if msg.get_srcComponent() != 1:
                    continue

                self.armed = bool(msg.base_mode & 128)
                self.mode = msg.custom_mode
                self.last_heartbeat = now

            elif kind == "SERVO_OUTPUT_RAW":
                if msg.get_srcComponent() != 1:
                    continue

                self.pwm_left = msg.servo1_raw
                self.pwm_right = msg.servo3_raw
                self.last_servo = now

    def update(self):
        self.read_mavlink()

        now = time.monotonic()

        heartbeat_ok = (
            self.last_heartbeat > 0 and
            now - self.last_heartbeat < HEARTBEAT_TIMEOUT
        )

        servo_ok = (
            self.last_servo > 0 and
            now - self.last_servo < SERVO_TIMEOUT
        )

        within_test = (
            now - self.started < TEST_DURATION
        )

        enabled = (
            self.armed
            and (self.mode == AUTO_MODE or self.mode == MANUAL_MODE)
            and heartbeat_ok
            and servo_ok
            and within_test
        )

        command = Twist()

        if enabled:
            left = clamp(
                (self.pwm_left - PWM_CENTER) / PWM_SPAN,
                -1.0, 1.0
            )
            right = clamp(
                (self.pwm_right - PWM_CENTER) / PWM_SPAN,
                -1.0, 1.0
            )

            v_left = left * NOMINAL_SPEED
            v_right = right * NOMINAL_SPEED

            linear = (v_left + v_right) / 2
            angular = (
                (v_right - v_left) / WHEEL_SEPARATION
            )

            command.linear.x = clamp(
                linear, -MAX_LINEAR, MAX_LINEAR
            )
            command.angular.z = clamp(
                angular, -MAX_ANGULAR, MAX_ANGULAR
            )

        self.publisher.publish(command)


        if now - self.last_log >= 0.5:
            elapsed = now - self.started

            self.get_logger().info(
                f"ARM={self.armed} MODE={self.mode} "
                f"PWM=({self.pwm_left},{self.pwm_right}) "
                f"V={command.linear.x:+.3f} "
                f"W={command.angular.z:+.3f} "
                f"ENABLED={enabled} "
                f"HB_OK={heartbeat_ok} "
                f"SERVO_OK={servo_ok} "
                f"TIME_OK={within_test} "
                f"ELAPSED={elapsed:.1f}s"
            )

            self.last_log = now

    def stop(self):
        zero = Twist()
        for _ in range(10):
            self.publisher.publish(zero)
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
        node.stop()
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
