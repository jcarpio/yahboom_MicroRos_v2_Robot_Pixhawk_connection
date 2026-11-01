# Extension 02 — Autonomous Mission Mode (AUTO): Cube Black → RFD868x → ROS 2 → Yahboom MicroROS V2

**Date:** 1 November 2026  
**Project:** Wireless ArduPilot–micro-ROS differential-drive integration, without Raspberry Pi  
**Status:** AUTO navigation commands demonstrated with suspended wheels; real-world waypoint arrival **not yet verified**.  
**Companion document:** `Pixhawk_Yahboom_MicroROS_No_RaspberryPi_README.md` (original manual-control experiment).  
**Experimental safety classification:** lab-only, supervised, non-hazardous chassis.

> **Important:** This record preserves a real bench experiment, including intentionally bypassed arming checks and a temporarily disabled fence. These are **not** recommended field settings. No end-to-end stop on Wi-Fi loss or ESP32 motor watchdog has been verified. Re-enable and validate protections before allowing the robot to drive outdoors. A software zero command is not a substitute for a hardware emergency stop.

## 1. Executive summary

This addendum documents the transition from **manual MAVLink RC overrides** to a first **Mission Planner mission executed in ArduRover AUTO mode**, using the same no-extra-motor-wiring architecture. The robot's motor controller is the Yahboom MicroROS V2 board; the Cube Black does **not** drive it by physical PWM wires. Instead, Pixhawk reports its computed skid-steer PWM-equivalent left/right commands over the existing RFD868x telemetry radios. An Ubuntu 22.04 ARM64 virtual machine in UTM on a Mac runs MAVProxy, a Python bridge, ROS 2 Humble and a micro-ROS UDP agent. The Python bridge publishes `geometry_msgs/msg/Twist` to `/cmd_vel`, received by the Yahboom controller over its already configured Wi-Fi.

What has been **observed**: the link and physical wheel actuation worked in MANUAL; both wheels advanced and steering worked; Mission Planner's one-waypoint mission was recognized; the autopilot initially rejected arm due to missing position estimate, then initialized EKF3 and GPS, reported `Mission: 1 WP`, moved to `waypoint 1`, and accepted arming in AUTO. The experimenter reported that the autopilot was attempting to navigate toward the waypoint. This is a **bench demonstration of AUTO command generation**, not verification of GPS guidance accuracy or successful field traversal.

## 2. Motivation, existing setup and scope

The companion UTM VM temporarily replaces the Raspberry Pi 5 while it is unavailable. This preserves a working ROS 2/micro-ROS environment and avoids designing a new ESC interface for the Cube Black. The approach is attractive for experimenting with ArduPilot AUTO missions and ROS 2 sensors, before migrating the bridge and agent onboard.

```
Mission Planner / ArduDeck (GCS)
       | MAVLink via MAVProxy network output
       v
Mac + UTM Ubuntu VM (192.168.1.52)
       | MAVProxy <----> RFD868x radio ~~~~ RFD868x <----> Cube Black
       |                          ArduRover 4.7.2 and mission execution
       |                          SERVO_OUTPUT_RAW (channels 1 and 3)
       v
Python MAVLink -> ROS 2 bridge (UDP 127.0.0.1:14551)
       |
       v
/cmd_vel  (ROS_DOMAIN_ID=40) --> micro-ROS agent UDP/8090
                                      |
                                     Wi-Fi
                                      |
                            Yahboom MicroROS V2 ESP32
                                      |
                              Existing motor driver
                                      |
                           Left/right wheel motors
```

**No new motor-control cabling to the Pixhawk was required.** This is not a completely wireless Pixhawk: it still uses the existing RFD868x and its existing power/GPS connections; the Yahboom board has its own motor wiring and power. No PWM wire, ESC adapter or UART cable was installed between the Pixhawk and Yahboom controller.

## 3. Reproduction prerequisites

- Working, adapted **Ubuntu 22.04 ARM64** in **UTM on a Mac**, with network reachability between VM and Yahboom Wi-Fi network. The conversion of the vendor OS image to UTM was not recorded in enough detail to claim a universally reproducible image-build procedure; begin from the validated VM as explained in the original README.
- ROS 2 Humble installed, Yahboom packages in `~/microros_ws`, micro-ROS agent in `~/uros_ws`, working ESP32/Yahboom firmware and `/cmd_vel` subscriber.
- Cube Black running **ArduRover 4.7.2**, GPS, an existing telemetry pair of **RFD868x**, and a ground control station with Mission Planner.
- Python packages `pymavlink`, `rclpy`, `geometry_msgs`. Do not overwrite the ROS-provided Python environment with incompatible packages.
- Robot mechanically immobilized for bench experiments; motor power cutoff accessible; no cutting tool connected.

Check ROS environment and connectivity:

```bash
export ROS_DOMAIN_ID=40
source /opt/ros/humble/setup.bash
source ~/uros_ws/install/setup.bash  # if installed here
ros2 node list
ros2 topic info /cmd_vel -v
ros2 topic echo /battery --once
```

Observed in the successful run: `/micro_ros_task_node` subscribed to `geometry_msgs/msg/Twist` on `/cmd_vel` using BEST_EFFORT QoS; battery topic reported ~10.89 V; Ubuntu's earlier joystick publisher was stopped before introducing the custom bridge.

Launch the existing agent **only if it is not already running**, and only if the board is targeting this host and UDP port:

```bash
export ROS_DOMAIN_ID=40
source /opt/ros/humble/setup.bash
source ~/uros_ws/install/setup.bash
ros2 run micro_ros_agent micro_ros_agent udp4 --port 8090 -v6
```

## 4. Reproduce MAVProxy message distribution

The VM's serial device was `/dev/ttyUSB0` at **57600 baud**, connected to the RFD868x radio (not direct Pixhawk USB). A representative invocation, using the Pixhawk GCS system identifier, is:

```bash
mavproxy.py --master=/dev/ttyUSB0,57600 \
  --source-system=254 \
  --out=udp:192.168.1.57:14550
```

The actual initial experiment used MAVProxy's default `source_system=255`; the autopilot was subsequently found to have `MAV_GCS_SYSID=254`. These values should be made consistent when testing GCS control and failsafe semantics. Do not assume all third-party clients have been tested with that source ID.

At MAVProxy's interactive prompt:

```text
output add 127.0.0.1:14551
output add 127.0.0.1:14552
output
```

Expected outputs, provided neither is duplicated:

```text
3 outputs
0: 192.168.1.57:14550
1: 127.0.0.1:14551
2: 127.0.0.1:14552
```

The `14551` endpoint feeds the motor bridge. The `14552` endpoint was added later for the terminal WASD program; without it WASD showed `ARM=False MODE=None HB_OK=False` even while the motor bridge had fresh telemetry. Ports are listening destinations (Python uses `udpin:`). Do not start multiple listeners on the same UDP port.

## 5. Recorded ArduRover parameter inventory

The following table distinguishes values explicitly observed in MAVProxy or reported by the operator from candidate values not verified. It is a **provenance-aware snapshot**, not a complete exported `.param` file. Some parameters may have been changed after the last captured output; read back the values before use.

| Parameter | Bench value | Evidence | Notes |
|---|---|---|---|
| `Firmware` | `ArduRover 4.7.2` | Confirmed boot log | Firmware running on Cube Black |
| `SERVO1_FUNCTION` | `73` | Confirmed | Skid-steer left motor output, carried as MAVLink telemetry |
| `SERVO3_FUNCTION` | `74` | Confirmed | Skid-steer right motor output, carried as MAVLink telemetry |
| `RCMAP_ROLL` | `1` | Confirmed | Steering input channel |
| `RCMAP_THROTTLE` | `3` | Confirmed | Throttle input channel |
| `RC3_TRIM` | `1500` | Confirmed | Throttle RC trim; calibration to be confirmed |
| `PILOT_STEER_TYPE` | `0` | Confirmed | Pilot steering type |
| `RC_OVERRIDE_TIME` | `3` | Confirmed | RC override timeout, seconds |
| `RC_OPTIONS` | `32` | Confirmed | RC option bitmask; check release-specific definitions |
| `MAV_GCS_SYSID` | `254` | Confirmed | Target GCS system identity; match MAVProxy sender when needed |
| `FS_GCS_ENABLE` | `1` | Confirmed after change | GCS failsafe enabled during bench work |
| `FS_ACTION` | `2` | Confirmed after change | Configured failsafe action HOLD |
| `FS_TIMEOUT` | `1.5` | Confirmed | Failsafe timeout value, seconds |
| `FENCE_ENABLE` | `1 then 0` | Observed 1; change to 0 instructed | Bench geofence disabled after polygon breach / RTL; present current state must be re-read |
| `FENCE_ACTION` | `1` | Confirmed | Fence breach action; triggered RTL in tests |
| `FENCE_TYPE` | `6` | Confirmed | Circular and polygon fence bits |
| `OA_TYPE` | `2` | Confirmed | Dijkstra avoidance; NOT BendyRuler |
| `ARMING_SKIPCHK` | `1048062 (0xFFD​FE)` | User-reported final bench value | Broad skip mask; not all mandatory checks can be bypassed; not for outdoor use |
| `ARMING_CHECK` | `N/A on 4.7 parameter model` | Earlier reference obsolete | Renamed with inverted bitmask semantics |
| `SERIAL1_PROTOCOL` | `Unverified` | Recommended 2 if TELEM1 uses MAVLink2 | Confirm physical radio port before setting |
| `SERIAL1_BAUD` | `Unverified` | 57 if TELEM1 uses 57600 | Radio serial speed observed on VM, not necessarily autopilot param |
| `MOT_SLEWRATE` | `Unverified` | Latency suspected | Measure, do not guess |
| `FS_THR_ENABLE` | `Unverified` | Not captured | Must inspect |
| `MODE_CH` | `Unverified` | Not captured | Must inspect |
| `PRX1_TYPE` | `Not set/verified` | Future LiDAR work | Candidate 2 for MAVLink proximity |

### 5.1 Very important: ARMING_SKIPCHK vs ARMING_CHECK

ArduPilot **4.7** changed `ARMING_CHECK` to `ARMING_SKIPCHK`; this is **not merely a rename**. `ARMING_CHECK` selected checks to execute, whereas `ARMING_SKIPCHK` selects checks to omit. In 4.7.2, the operator reported **`ARMING_SKIPCHK=1048062`** for this bench experiment:

```text
Decimal: 1048062
Hexadecimal: 0xFFDFE
Set bit indices: 1, 2, 3, 4, 5, 6, 7, 8, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19
```

The bitmask includes bits **1–8 and 10–19**, omitting the listed non-mandatory check categories in the firmware's bit mapping (e.g. compass, GPS lock, INS, RC channels, power/battery, logging, system and mission categories). Bits 0 and 9 are not set. Mandatory conditions may still prevent arming — as actually seen with `Need Position Estimate` in AUTO. The official recommended default is **`ARMING_SKIPCHK=0`**. This value was an experimental bypass and must **not be copied to a field vehicle**. Instead restore `0` and resolve reported failures; do not suppress position, safety-switch, voltage, mission or GPS faults simply to make arming succeed.

Capture current value:

```text
param show ARMING_SKIPCHK
```

For the **pre-field safety restoration**, after repairing the underlying causes:

```text
mode HOLD
disarm
param set ARMING_SKIPCHK 0
param show ARMING_SKIPCHK
```

For a reproducible snapshot, save **all parameters**, not only selected settings. In MAVProxy (after confirming your local MAVProxy version's parameters commands):

```text
param fetch
param save cube_black_auto_bench.param
```

Mission Planner also provides **Full Parameter List/Tree → Save to file**. Check the file includes `ARMING_SKIPCHK` and the servo/motor/avoidance parameters. Keep separate *bench* and *field-safe* parameter snapshots, with date and firmware hash.

### 5.2 Geofence and unexpected RTL

Earlier bench testing showed `PreArm: Vehicle breaching Polygon fence`, `fence breach`, `fence OK` and unexpected RTL (`MODE=11`) while physically stationary; a Dijkstra path failure was also shown. `FENCE_ENABLE=1`, `FENCE_ACTION=1`, `FENCE_TYPE=6` were reported. A temporary change to `FENCE_ENABLE=0` allowed limited suspended-wheel MANUAL testing. Confirm its current value before each session. For field driving, build a suitable fence on the **actual** site, verify GPS/RTK, restore `FENCE_ENABLE=1` and confirm predictable RTL/HOLD behavior. Do not restore an obsolete fence from a different geographical area.

### 5.3 Obstacle-avoidance algorithm clarification

The recorded `OA_TYPE=2` is **Dijkstra**, not BendyRuler. Dijkstra is primarily suited to planning around known polygonal exclusion areas; for dynamic LiDAR obstacles in AUTO, evaluate `OA_TYPE=1` (BendyRuler) after proximity sensing is connected and validated. Leave `OA_TYPE` changes out of the benchmark until the vehicle's navigation and sensor geometry have been verified.

## 6. Mission Planner AUTO: observed sequence

1. In Mission Planner, keep a copy of the existing mission, create/upload a **minimal one-waypoint** mission, and read it back. The exact waypoint coordinates were not included in the captured log, so they cannot be reconstructed from this report.
2. In MAVProxy, while immobilized, set `mode HOLD`, `disarm`; stop the keyboard controller and confirm no stale RC overrides are being sent (`rc 1 0`, `rc 3 0` if appropriate).
3. Confirm that the original manual-only bridge publishes zero in AUTO, because `self.mode == MANUAL_MODE` filters it out. This is a useful dry-run mode.
4. The operator then extended the enabling condition to allow `AUTO_MODE`, **without bypassing** its heartbeat, fresh-servo and test-duration checks. The modified script appears in full below.
5. When first attempting AUTO arm, ArduRover returned:

```text
AUTO> Got COMMAND_ACK: COMPONENT_ARM_DISARM: FAILED
AP: Arm: Need Position Estimate
AP: PreArm: Need Position Estimate
```

6. The log subsequently showed:

```text
AP: EKF3 IMU0 origin set
AP: EKF3 IMU1 origin set
AP: Mission: 1 WP
AP: EKF3 IMU0 is using GPS
AP: EKF3 IMU1 is using GPS
AP: Field Elevation Set: 7m
waypoint 1
AUTO> Got COMMAND_ACK: COMPONENT_ARM_DISARM: ACCEPTED
AP: Throttle armed
ARMED
Arming checks disabled
```

7. This means the autopilot recognized the loaded mission, acquired a position estimate suitable to proceed and accepted arming. The owner observed the system **attempting to head toward the waypoint**. No completed track, actual displacement or waypoint-arrival confirmation has yet been captured. Avoid equating `waypoint 1` with mission completion.

**To end any supervised bench run**, issue separately:

```text
mode HOLD
disarm
```

If actuators do not stop, cut motor power physically. Do not rely on the Wi-Fi link to deliver the final zero message.

## 7. AUTO-mode change to the ROS 2 bridge

The essential code change from the previously verified manual-only version is:

```diff
 MANUAL_MODE = 0
+AUTO_MODE = 10
 ...
- enabled = self.armed and self.mode == MANUAL_MODE and heartbeat_ok and servo_ok and within_test
+ enabled = self.armed and self.mode in (MANUAL_MODE, AUTO_MODE) and heartbeat_ok and servo_ok and within_test
```

**Do not write** `self.armed and self.mode == MANUAL_MODE or self.mode == AUTO_MODE and ...`, because operator precedence can allow AUTO to bypass safeguards. This patch is included as `scripts/mavlink_ros2_bridge_auto_bench.py` and is **for bench testing only**.

### 7.1 Complete reproducible experimental bridge source

```python
#!/usr/bin/env python3
# Historical bench-only motion bridge: do not use for unattended field operation.
import time
import rclpy
from rclpy.node import Node
from rclpy.qos import QoSProfile, ReliabilityPolicy, DurabilityPolicy
from geometry_msgs.msg import Twist
from pymavlink import mavutil

MAVLINK_PORT = 'udpin:127.0.0.1:14551'
TOPIC = '/cmd_vel'
PWM_CENTER = 1500
PWM_SPAN = 500
MAX_LINEAR = 0.08
MAX_ANGULAR = 0.30
NOMINAL_SPEED = 0.40      # Provisional conversion scale, m/s
WHEEL_SEPARATION = 0.22   # Placeholder, not a measured robot dimension
HEARTBEAT_TIMEOUT = 2.0
SERVO_TIMEOUT = 0.6
TEST_DURATION = 180.0     # Initial trial used 30.0 s
MANUAL_MODE = 0
AUTO_MODE = 10

def clamp(value, low, high):
    return max(low, min(high, value))

class MAVLinkROS2Bridge(Node):
    def __init__(self):
        super().__init__('mavlink_ros2_bridge_motion')
        qos = QoSProfile(depth=10)
        qos.reliability = ReliabilityPolicy.BEST_EFFORT
        qos.durability = DurabilityPolicy.VOLATILE
        self.publisher = self.create_publisher(Twist, TOPIC, qos)
        self.mav = mavutil.mavlink_connection(MAVLINK_PORT)
        self.armed = False
        self.mode = None
        self.pwm_left = 1500
        self.pwm_right = 1500
        self.last_heartbeat = 0.0
        self.last_servo = 0.0
        self.started = time.monotonic()
        self.last_log = 0.0
        self.create_timer(0.1, self.update)
        self.get_logger().info('Bench AUTO experiment bridge started, time limited')

    def read_mavlink(self):
        for _ in range(100):
            msg = self.mav.recv_match(blocking=False)
            if msg is None:
                break
            if msg.get_srcSystem() != 1:
                continue
            now = time.monotonic()
            kind = msg.get_type()
            if kind == 'HEARTBEAT':
                if msg.get_srcComponent() != 1:
                    continue
                self.armed = bool(msg.base_mode & 128)
                self.mode = msg.custom_mode
                self.last_heartbeat = now
            elif kind == 'SERVO_OUTPUT_RAW':
                if msg.get_srcComponent() != 1:
                    continue
                self.pwm_left = msg.servo1_raw
                self.pwm_right = msg.servo3_raw
                self.last_servo = now

    def update(self):
        self.read_mavlink()
        now = time.monotonic()
        heartbeat_ok = self.last_heartbeat > 0 and now - self.last_heartbeat < HEARTBEAT_TIMEOUT
        servo_ok = self.last_servo > 0 and now - self.last_servo < SERVO_TIMEOUT
        within_test = now - self.started < TEST_DURATION
        enabled = self.armed and self.mode in (MANUAL_MODE, AUTO_MODE) and heartbeat_ok and servo_ok and within_test
        command = Twist()
        if enabled:
            left = clamp((self.pwm_left - PWM_CENTER) / PWM_SPAN, -1.0, 1.0)
            right = clamp((self.pwm_right - PWM_CENTER) / PWM_SPAN, -1.0, 1.0)
            v_left = left * NOMINAL_SPEED
            v_right = right * NOMINAL_SPEED
            linear = (v_left + v_right) / 2.0
            angular = (v_right - v_left) / WHEEL_SEPARATION
            command.linear.x = clamp(linear, -MAX_LINEAR, MAX_LINEAR)
            command.angular.z = clamp(angular, -MAX_ANGULAR, MAX_ANGULAR)
        self.publisher.publish(command)
        if now - self.last_log >= 0.5:
            elapsed = now - self.started
            self.get_logger().info(
                f'ARM={self.armed} MODE={self.mode} PWM=({self.pwm_left},{self.pwm_right}) '
                f'V={command.linear.x:+.3f} W={command.angular.z:+.3f} ENABLED={enabled} '
                f'HB_OK={heartbeat_ok} SERVO_OK={servo_ok} TIME_OK={within_test} ELAPSED={elapsed:.1f}s'
            )
            self.last_log = now

    def stop(self):
        for _ in range(10):
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
        node.stop()
        node.destroy_node()
        rclpy.shutdown()

if __name__ == '__main__':
    main()
```

### 7.2 Executing the AUTO bench bridge

Stop the previous bridge before starting the new one; **only one** publisher should control `/cmd_vel`:

```bash
export ROS_DOMAIN_ID=40
source /opt/ros/humble/setup.bash
python3 scripts/mavlink_ros2_bridge_auto_bench.py
```

Observe `ros2 topic info /cmd_vel -v`, `ros2 topic hz /cmd_vel`, the bridge's `ARM`, `MODE`, `HB_OK`, `SERVO_OK`, `TIME_OK`, `PWM`, `V`, `W` status and ArduPilot's `MISSION_CURRENT`/`SERVO_OUTPUT_RAW` in telemetry. This script gates on recent HEARTBEAT and servo values; it does **not** independently validate actual motion, waypoint progress or physical emergency stops. It continues publishing zeros when disabled, and it times out after 180 s. Any movement caused by a nonzero command is limited in software, not guaranteed safe mechanically.

## 8. Data already demonstrated versus not demonstrated

| Capability | Evidence | Result |
|---|---|---|
| Two-wheel differential forward motion | `rc 3 1550`, user observed both wheels turning forward | Demonstrated on bench |
| Steering left/right | RC channel 1 overrides, user observed turning | Demonstrated on bench |
| WASD remote control | 14552 output added; wheels subsequently responded; repeat/latency improvements reported | Demonstrated, latency not instrumented |
| micro-ROS transport | `/micro_ros_task_node` subscriber, battery topic, successful movement | Demonstrated |
| Python ROS 2 output | 10.003 Hz measured on `/cmd_vel` | Demonstrated |
| AUTO mission recognition | `Mission: 1 WP`, `waypoint 1`, arm accepted | Demonstrated |
| AUTO servo-to-motor chain | Operator reports attempting to navigate after AUTO added | Preliminary bench demonstration |
| Outdoor waypoint arrival | No GPS track/waypoint reached evidence | Not demonstrated |
| On-board ESP32 motor command timeout | Source not verified | Not demonstrated |
| Physical emergency stop / independent cutoff | Not instrumented | Not demonstrated |
| Avoidance of a real LiDAR obstacle | No avoidance trial | Not demonstrated |

## 9. Next research phase: LiDAR obstacle avoidance

The Yahboom robot already published `/scan` in earlier tests, alongside `/cmd_vel`, `/odom_raw`, `/imu` and `/battery`. The next objective is to prevent a rover driving an AUTO waypoint mission into a tree, rock, person or test obstacle, then navigate around it and resume the mission. This requires **feeding obstacle information back into the ArduPilot planner**, not only calculating wheel commands from its PWM output.

### 9.1 First choice: ROS 2 LaserScan to ArduPilot MAVLink proximity (recommended prototype)

```
LiDAR -> Yahboom /scan (sensor_msgs/LaserScan)
                  |
                  v
Ubuntu ROS 2 converter (filter invalid ranges, account for sensor pose)
                  |
                  v
MAVLink OBSTACLE_DISTANCE (or DISTANCE_SENSOR sectors)
                  |
                  v
MAVProxy -> RFD868x -> Cube Black
                  |
                  v
ArduRover PRX1_TYPE=2 (MAVLink proximity)
                  |
                  v
BendyRuler avoidance (evaluate OA_TYPE=1)
                  |
                  v
Updated SERVO_OUTPUT_RAW -> existing motor bridge -> /cmd_vel
```

A suitable ROS 2 node would subscribe to `sensor_msgs/msg/LaserScan`, map azimuths into `OBSTACLE_DISTANCE`'s sector/range encoding, reject NaN/Inf/stale scans, convert metres to centimetres, apply sensor position/yaw offsets and send MAVLink at a measured, bounded rate. ArduPilot's documented proximity interface accepts MAVLink input (`PRX1_TYPE=2`), and MAVLink `OBSTACLE_DISTANCE` supports arrays of ranges. **Do not enable this blindly**: verify the precise message dialect, frame orientation, sensor maximum range, orientation and freshness for the firmware in use. Avoid treating `scan` absence as clear space.

For the baseline, with the rover in HOLD and motor power isolated, collect:

```bash
export ROS_DOMAIN_ID=40
source /opt/ros/humble/setup.bash
ros2 topic info /scan -v
ros2 topic hz /scan
ros2 topic echo /scan --once
ros2 topic info /odom_raw -v
```

Query the relevant Pixhawk parameters individually in MAVProxy:

```text
param show PRX1_TYPE
param show OA_TYPE
param show OA_BR_LOOKAHEAD
param show OA_MARGIN_MAX
param show AVOID_ENABLE
param show FENCE_ENABLE
```

Suggested **evaluation plan** (not current settings): set MAVLink proximity type only after you have validated the ROS 2→MAVLink conversion; compare BendyRuler `OA_TYPE=1` with the existing `OA_TYPE=2` Dijkstra; begin with a static object and a stop-only gate before attempting detours. The choice of stop distance must include braking capability, latency, obstacle width and the robot's real footprint. Test with the chassis supported and actuators disconnected first, then in a safe, fenced test space.

### 9.2 Alternative: local ROS 2 safety supervisor

A separate ROS 2 supervisor can consume `/scan`, the proposed `/cmd_vel` and, later, odometry. It would apply a conservative stop or speed cap to imminent front-sector obstacles. This is valuable as a redundant local guard but **a simple stop gate will not make ArduPilot replan the route**. To avoid an obstacle and then return to AUTO, the planner must receive valid proximity data (route above), or a separate ROS 2 Nav2 controller must assume path planning and control. Avoid two simultaneous `/cmd_vel` publishers; use one arbiter that outputs to the motor topic, with separate input topics for planner and safety commands.

### 9.3 Constraints of current offboard architecture

Because `/scan` and `/cmd_vel` currently traverse Wi-Fi through the UTM machine and MAVLink traverses RFD868x, a full LiDAR→Pixhawk→motor obstacle-avoidance loop will have additional communication delay. It could fail if either wireless link breaks. Ultimately move the ROS 2 agent/bridge and local obstacle-stop logic onto a suitable **onboard computer** (e.g. repaired Raspberry Pi), while retaining the Pixhawk for GPS mission management and RFD868x for supervision. The lack of an independent local motor watchdog is the major blocker for field operation. A LiDAR alone cannot provide reliable person detection in all conditions; for agricultural equipment add appropriate hardware safety and other sensing.

### 9.4 Milestones and validation measurements

1. Verify orientation and timing of `/scan`: front obstacle at robot-front angle, correct range, no mirrored sectors.
2. Produce MAVLink obstacle messages and verify Pixhawk proximity reports; do not enable wheel motion.
3. Test stop-on-obstacle with a fail-closed freshness check.
4. Verify BendyRuler's detour selection in AUTO with motor output disconnected, inspecting headings/commands.
5. Run a slow supervised field trial within an appropriately configured geofence and record distances, braking, latency and route outcomes.
6. Verify resumption of the original waypoint mission and record logs showing avoidance success and final arrival.

## 10. Field-readiness gate (unresolved)

Before any real-world autonomous motion:

- Restore `ARMING_SKIPCHK=0`; repair position, compass, voltage/battery, RC/GCS and safety-switch prearm faults instead of suppressing them.
- Rebuild and enable a location-correct geofence; check GPS accuracy and home, and confirm no surprise RTL.
- Implement and verify a **firmware-local ESP32 motor command watchdog** and an independent electrical stop; test radio/Wi-Fi/VM failure with wheels lifted.
- Measure real `WHEEL_SEPARATION`, wheel directions, speed mapping and encoder feedback; tune steering and speed based on field odometry.
- Ensure AUTO uses reliable navigation state and that stopping/holding the mission is possible from an independent channel.
- Log GPS trajectory, mission advancement, obstacle locations and motor commands for post-run evaluation.

## 11. References

1. [ArduPilot Rover 4.7.2 parameters: ARMING_SKIPCHK and other settings](https://ardupilot.org/rover/docs/parameters-Rover-stable-V4.7.2.html)
2. [ArduPilot arming parameter name changes](https://ardupilot.org/rover/docs/common-param-name-changes.html)
3. [ArduPilot Rover: Motor and Servo Configuration](https://ardupilot.org/rover/docs/rover-motor-and-servo-configuration.html)
4. [ArduPilot Rover: Proximity Sensors](https://docs.ardupilot.org/rover/docs/common-proximity-landingpage.html)
5. [ArduPilot Rover: BendyRuler object avoidance](https://ardupilot.org/rover/docs/common-oa-bendyruler.html)
6. [ArduPilot Rover: Intel RealSense depth camera integration (MAVLink obstacle protocol example)](https://ardupilot.org/rover/docs/common-realsense-depth-camera.html)
7. [ArduPilot Rover: Arming and Disarming](https://ardupilot.org/rover/docs/arming-your-rover.html)

## Appendix A. Command summary

```text
# From MAVProxy (diagnostics first)
output
param show SERVO1_FUNCTION
param show SERVO3_FUNCTION
param show RCMAP_ROLL
param show RCMAP_THROTTLE
param show MAV_GCS_SYSID
param show FS_GCS_ENABLE
param show FS_ACTION
param show FS_TIMEOUT
param show FENCE_ENABLE
param show FENCE_ACTION
param show FENCE_TYPE
param show ARMING_SKIPCHK
param show OA_TYPE
param show PRX1_TYPE
wp list
status

# Only for a supervised already-safe bench test:
mode HOLD
disarm
# Mission was uploaded and read back in Mission Planner
mode AUTO
# Do not arm until positioning and the safety envelope are verified.

# End of trial
mode HOLD
disarm
```

## Appendix B. Version note

The original README's reference to `ARMING_CHECK` should be superseded for firmware 4.7.2 by `ARMING_SKIPCHK`, and its explanation of `OA_TYPE=2` as BendyRuler should be corrected to **Dijkstra**. This addendum records the first AUTO experiment but does not retroactively claim field navigation success or a verified on-board safety watchdog.


---

## 12. Follow-up: ArduDeck mission display, manual intervention, and slow movement

**Experiment date:** 1 November 2026. **Evidence:** operator report and an ArduDeck screenshot showing a connected ArduPilot **Ground Rover**, UDP port **14550**, three waypoints, approximately **17 m** of planned travel, an estimate of **~1 minute**, and **Current: WP 2 of 3**. The image captures a planned mission and a status display, **not proof of physical waypoint arrival**. The operator separately confirmed that manual keyboard controls move the wheels and that the rover can generate AUTO motor commands on the suspended chassis. Outdoor route completion has **not** yet been demonstrated.

### 12.1 Why the commanded motor movement is slow

There are **two independent layers of speed limitation**:

1. **ArduRover mission navigation:** the autopilot determines a target speed and its left/right output commands, taking waypoint speeds, turns, acceleration limits, controller tuning, failsafes and proximity into account.
2. **The custom MAVLink-to-ROS 2 bridge:** it maps ArduRover's PWM-equivalent motor outputs into a `Twist` and **clamps the final linear and angular commands**. This clamp may dominate the observed speed regardless of the mission speed configured in Mission Planner.

The **recorded bridge source** in section 7 has these deliberately conservative bench settings:

```python
MAX_LINEAR = 0.08        # maximum requested linear speed (m/s)
MAX_ANGULAR = 0.30       # maximum requested angular speed (rad/s)
NOMINAL_SPEED = 0.40     # assumed wheel speed at full-scale PWM; not calibrated
WHEEL_SEPARATION = 0.22 # provisional track width; not measured
```

The `MAX_LINEAR` cap equals **0.288 km/h**, or **4.8 m/min**, for a sustained command of 0.08 m/s. This is a cap on the **published command**, not a verified physical speed. The firmware's own control response and the robot's wheel/encoder geometry can produce a different measured velocity.

The conversion in the experimental bridge is:

```python
left = clamp((pwm_left - 1500) / 500, -1.0, 1.0)
right = clamp((pwm_right - 1500) / 500, -1.0, 1.0)
v_left = left * NOMINAL_SPEED
v_right = right * NOMINAL_SPEED
linear = (v_left + v_right) / 2.0
angular = (v_right - v_left) / WHEEL_SEPARATION
command.linear.x = clamp(linear, -MAX_LINEAR, MAX_LINEAR)
command.angular.z = clamp(angular, -MAX_ANGULAR, MAX_ANGULAR)
```

The final `Twist` is **not a direct pass-through** of ArduRover speed control: clipping linear and angular terms independently may alter the relative left/right motor speeds and thus the curvature of turns. This is particularly relevant in AUTO, where accurate path following requires careful motor mapping and calibration. **Do not assume the current bridge will track a GPS route accurately on the ground.**

### 12.2 Inspect the mission speed configuration before editing it

With the vehicle in HOLD and disarmed, query each parameter separately from MAVProxy:

```text
param show WP_SPEED
param show CRUISE_SPEED
param show CRUISE_THROTTLE
param show ATC_ACCEL_MAX
param show MOT_SLEWRATE
param show WP_RADIUS
```

The meanings and units are version-specific; confirm them against the installed **ArduRover 4.7.2** parameter documentation and parameter metadata before changing anything.

| Parameter | What to investigate |
|:--|:--|
| `WP_SPEED` | Desired ground speed for waypoint navigation (typically m/s, but verify the version-specific definition). |
| `CRUISE_SPEED` | Speed reference used in the vehicle controller; distinguish it from mission-specific speed. |
| `CRUISE_THROTTLE` | Assumed throttle/output for cruising; a tuning value, not a hard speed cap. |
| `ATC_ACCEL_MAX` | Acceleration constraint, which can dominate short missions. |
| `MOT_SLEWRATE` | How quickly output is permitted to change; too restrictive a setting can feel like control latency. |
| `WP_RADIUS` | Waypoint acceptance distance; relevant when the route is only a few metres long. |

**Recorded values:** values for the six parameters above were *requested but not returned in the conversation*. They are **unknown**, not confirmed settings. Preserve their actual output in the experiment log before tuning.

For a **future** controlled experiment, `WP_SPEED=0.3` m/s was suggested as an example target, **not an applied setting**:

```text
# Example only; not recorded as applied:
param set WP_SPEED 0.3
param show WP_SPEED
```

Similarly, `MAX_LINEAR = 0.12` m/s was suggested as a possible **future bench-only** increase in the bridge. It is **not** the observed configuration. Before applying changes, start with the chassis mechanically supported, confirm the effective output and motor stop behavior, and calibrate encoder-based motion. Short waypoint spacing, turns and acceleration/deceleration may explain low average speeds even after raising a speed target.

### 12.3 Interpret the orange shaded shape in ArduDeck

In the ArduDeck screenshot a **translucent orange polygon** and orange connecting lines are visible around the rover/waypoint markers; the editor is on the **Mission** tab and shows **3 waypoints**. This looks like **mission-planning/coverage geometry**, perhaps associated with a **Survey** region, rather than a LiDAR field-of-view or a detected obstacle. The screenshot **alone does not prove** whether the polygon is a survey boundary, route overlay or a separately configured geofence.

To identify it reproducibly:

1. In ArduDeck toggle **Mission** and **Geofence** views separately.
2. Observe which view retains the orange polygon and whether the selected Survey tool displays it.
3. Inspect the waypoint/mission item list and any saved polygon or fence collection.
4. Do not treat the shaded shape as obstacle detection. The `/scan` → Pixhawk proximity integration is not yet implemented.

The underlying screenshot's scale label reports roughly **17 m** planned distance and an estimated **~1 minute**. Such a short course can spend much of its time turning and slowing around waypoints.

### 12.4 Manual takeover while AUTO is running

The operator confirmed **WASD keyboard movement works** in MANUAL. However, the existing `rover_keyboard.py` from the companion README permits RC commands only if `armed and mode == 0 and heartbeat_ok`; it does **not** automatically switch from AUTO to MANUAL when a key is pressed. A connected controller is therefore **not yet a verified emergency takeover mechanism**.

For controlled experiments, the intended intervention flow is:

```text
# Request stop from MAVProxy or a single authoritative GCS:
mode HOLD

# Verify mode == HOLD and wheel outputs stop.
# To take over after safe assessment:
mode MANUAL
# Use WASD only after the control-mode change is confirmed.

# To re-enter navigation after checking route/position/safety:
mode AUTO

# Terminate the trial:
mode HOLD
disarm
```

An RC throttle input may affect AUTO speed through **speed nudging**, depending on ArduRover configuration; it should **not** be interpreted as reliable manual steering override in AUTO. Changing back to AUTO may resume the existing mission from its retained state; verify the mission sequence number rather than assuming it restarts or skips the same waypoints.

A proposed **future** keyboard interface would add:

- `H`: request HOLD and confirm it from a fresh vehicle heartbeat;
- `M`: request MANUAL and verify the mode change before enabling WASD;
- `R`: request AUTO **after explicit user confirmation** and navigation-state checks;
- a physical independent emergency stop and onboard command timeout, neither of which has yet been verified.

These H/M/R functions have **not** been coded or tested in the existing keyboard script. Do not describe the current keyboard as emergency-stop hardware. The `SPACE` key sends a *neutral RC command* only while the software and both links are operating; that is **not** an independent safe stop.

### 12.5 Suggested non-invasive diagnostic run

Keep the chassis suspended and cutting attachments removed. Start by recording, without parameter edits:

```text
# MAVProxy: one command at a time
mode HOLD
disarm
param show WP_SPEED
param show CRUISE_SPEED
param show CRUISE_THROTTLE
param show ATC_ACCEL_MAX
param show MOT_SLEWRATE
param show WP_RADIUS
param show FENCE_ENABLE
param show ARMING_SKIPCHK
```

While the bridge runs, observe the calculated PWM and the published linear/angular commands in two different terminals:

```bash
export ROS_DOMAIN_ID=40
source /opt/ros/humble/setup.bash
ros2 topic echo /cmd_vel
```

```bash
export ROS_DOMAIN_ID=40
source /opt/ros/humble/setup.bash
ros2 topic echo /odom_raw --once
```

Compare (a) the requested mission speed, (b) the ArduPilot `SERVO_OUTPUT_RAW` motor commands, (c) the bridge's `V` and `W` after clipping, and (d) the measured wheel odometry when available. Do not mistake GPS-derived drift in a stationary suspended robot for real travel.

### 12.6 Release criteria before supervised outdoor AUTO

The successful current bench test **does not establish outdoor safety**. Before the robot leaves the test stand:

1. Restore and pass arming checks instead of leaving `ARMING_SKIPCHK=1048062` in place; configure battery/voltage sensing or an appropriate monitored power system.
2. Re-enable and define a **correct location-specific geofence**; the earlier `FENCE_ENABLE=0` was a bench workaround for an unwanted RTL.
3. Verify an **ESP32 firmware-local motor watchdog** on `/cmd_vel` loss and an independent hardware power cut/stop.
4. Validate manual takeover as a **mode change** from AUTO to MANUAL or HOLD, rather than relying on WASD to override AUTO.
5. Calibrate PWM-to-velocity mapping, physical track width, motor direction, encoder odometry, braking distance, link delay and output saturation.
6. Start with an isolated outdoor area, a short low-speed route, a spotter and a positive way to interrupt movement; log waypoint progression and measured actual track.

**Research next step:** add and validate LiDAR obstacle detection with `/scan` and MAVLink proximity, then evaluate ArduPilot's route deviation/recovery for a static obstacle. This remains experimental and is **not** implemented in the present mission bridge. See section 9.

### 12.7 Supplementary references

- [ArduPilot Rover speed and throttle tuning](https://ardupilot.org/rover/docs/rover-tuning-throttle-and-speed.html)
- [ArduPilot Rover waypoint navigation](https://ardupilot.org/rover/docs/auto-mode.html)
- [ArduPilot Rover complete parameter reference](https://ardupilot.org/rover/docs/parameters-Rover-stable-V4.7.2.html)
- [ArduPilot MAVLink RC input / joystick control](https://ardupilot.org/dev/docs/mavlink-rcinput.html)
