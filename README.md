# ARBOREON — Complete Yahboom MicroROS V2, Pixhawk Cube Black, MAVROS and ArduDeck Integration Handover with and without Raspberri Pi

**Date:** 29 October 2026  
**Document language:** English  
**Audience:** Engineers reproducing the setup, diagnosing the links, and implementing a safe ArduRover-to-ROS 2 motor interface.  
**Status at handover:** Raspberry Wi-Fi verified; ESP32-S3 micro-ROS over Wi-Fi verified; **both suspended drive wheels moved and stopped on ROS 2 command**; Yahboom encoder odometry verified; Pixhawk Cube Black ↔ MAVROS verified; MAVLink routed to **ArduDeck on MacBook, connected and receiving telemetry**. **Autonomous navigation and Pixhawk-to-wheel actuation not yet implemented.**

> **Evidence conventions.** **VERIFIED** denotes a user-observed measurement, log or outcome from the session. **RECONSTRUCTED** denotes a functional example derived from the verified behavior when the exact original source is not retained here. **PROPOSED / NOT EXECUTED** denotes the next engineering step. Do not treat the earlier chronological diagnostic report (Appendix A) as the current system state: it was written *before* the breakthrough in Yahboom UDP connectivity and motor actuation.

## Updates
### 2026-11-01 — Extension 02 — Autonomous Mission Mode (AUTO): Cube Black → RFD868x → ROS 2 → Yahboom MicroROS V2

**[Read document →](Quick_Start_Autonomous_Mission_with_Pixhawk_Cube_Black_and_Yahboom_MicroROS_V2_No_Raspberry_Pi.md)**

### 2026-11-01 — Extension 02 — Autonomous Mission Mode (AUTO): Cube Black → RFD868x → ROS 2 → Yahboom MicroROS V2

**[Read document →](MISSION_AUTO_LIDAR_NEXT_STEPS.md)**


### 2026-11-01 — Cable-Free Motor Integration: ArduPilot Cube Black + RFD868x + Yahboom MicroROS V2 over ROS 2 without Raspberry Pi

**[Read document →](MicroRos_V2_Pixhawk_connection_without_Raspberry_Pi.md)**


### 2026-10-31 — MicroRos V2 Agent Raspberry Pi 5 and Ubuntu MacOS MicroRos Migration notes 

**[Read Migration notes →](microros_v2_agent_migration_note.md)**

### 2026-10-30 — MAVROS RC Control and Failsafe Investigation

A major milestone in the ARBOREON project: successful integration of MAVLink-based virtual RC control between the Raspberry Pi 5, MAVROS, and the Pixhawk Cube Black running ArduRover 4.7.2.

**Key achievements:**
- Resolved a MAVLink System ID mismatch (SYSID 1 → 254).
- Successfully transmitted and validated virtual RC channel overrides.
- Confirmed radio failsafe recovery using continuous RC commands.
- Achieved HOLD → MANUAL transitions and observed automatic return to HOLD after RC signal loss.
- Verified neutral motor outputs and documented remaining safety requirements.

The complete investigation includes experimental results, troubleshooting steps, and reproducible Python and ROS 2 scripts.

**[Read the full technical report →](ARBOREON_MAVROS_RC_Failsafe_Investigation_2026-10-29_EN.md)**

**Next milestone:** Validate differential PWM outputs and supervised motor actuation with the Yahboom MicroROS V2 platform.

## 1. Current outcome in one page

### What actually works (VERIFIED)

1. Raspberry Pi 5 (8 GB), Debian Bookworm, reachable on home WLAN `WiFi-Casa` at **192.168.1.58** during the session; home Wi-Fi reconnect after reboot confirmed. DHCP address is not guaranteed permanent.
2. Main ROS 2 Humble execution environment: Docker container **`arboreon-dev`** based on `arboreon:backup`; ROS domain **`20`**. The Raspberry host itself is **not** the ROS 2 command environment.
3. Yahboom **MicroROS V2, two drive motors**, ESP32-S3-WROOM-1U, CP2102 attached as `/dev/ttyUSB0`. Robot Manager was used to reconfigure the V2 ESP32 from a former SSID/IP/domain to Wi-Fi UDP agent address **192.168.1.58:8090**, `ROS_DOMAIN_ID=20`. Its network address observed in UDP Agent logs: **192.168.1.54**.
4. `arboreon-agent-udp` (micro-ROS Agent in host-network Docker) established real XRCE-DDS sessions and successfully created DDS participants and endpoints. The actual connected node is **`/micro_ros_task_node`**, not the Pi5 manual's expected `/YB_Car_Node`.
5. Actual ESP32 subscribers: `/cmd_vel` (`geometry_msgs/msg/Twist`), `/beep` (`std_msgs/msg/UInt16`), `/cmd_ptz_angle` (`geometry_msgs/msg/Vector3`). Actual publishers: `/battery` (`std_msgs/msg/Float32`), `/imu` (`sensor_msgs/msg/Imu`), `/odom_raw` (`nav_msgs/msg/Odometry`), `/ptz_angle` (`geometry_msgs/msg/Vector3`), `/scan` (`sensor_msgs/msg/LaserScan`).
6. Buzzer test: `/beep` data `1` sounded; data `0` stopped it. Battery reported **12.835550308227539**, believed to be volts but unit should be checked against firmware.
7. The user executed a short `rclpy` velocity script publishing `linear.x = 0.03 m/s` for **0.5 s** at **10 Hz**, then repeatedly publishing zero for ~**2 s**. **Both suspended wheels visibly turned forward and stopped.** `/odom_raw` velocity increased during test and decayed to zero. It is not yet evidence of calibrated physical speed, directional symmetry, a tested timeout, or safe unattended operation.
8. Cube Black attached as `/dev/ttyACM0`, connected by `ros2 launch mavros apm.launch fcu_url:=/dev/ttyACM0:115200`. ArduRover firmware **4.7.2**; MAVROS reported connected, `HOLD`, disarmed, `system_status=5` (MAV_STATE_CRITICAL), not ready for AUTO navigation. Current indoor GPS had **no fix, 0 satellites**, position `0,0` in ArduDeck.
9. The MAVROS parameter pull succeeded: **876 ArduPilot parameters received**. Original wheel output functions are `SERVO1_FUNCTION=26` (ground steering) and `SERVO3_FUNCTION=70` (throttle). Their PWM ranges are `1100–1900 µs`, neutral `1500 µs`, reversals `0`.
10. `/mavros_router/add_endpoint` provided a link to **ArduDeck Beta 1.1** running on MacBook **192.168.1.57**, using UDP **14550**. User explicitly confirmed **connection succeeded**, and screenshot showed live `HOLD`, `DISARMED`, heading **22°**, speed **0.0 m/s**, no GPS fix, `UDP :14550` connected.

### What is NOT yet complete

- No verified ROS node currently translates Cube's actual servo output `/mavros/rc/out` into Yahboom `/cmd_vel`.
- `SERVO1_FUNCTION=73` (Throttle Left) and `SERVO3_FUNCTION=74` (Throttle Right) were **proposed but not applied**.
- No autonomous route, `AUTO` waypoint following, `GUIDED` movement, valid position-estimation source to Pixhawk, arming, field navigation, or physical displacement test has been completed.
- `FS_GCS_ENABLE=0`; the micro-ROS/Wi-Fi loss stop behavior is not proven. The present `FS_THR_ENABLE=1` cannot be assumed to protect the ESP32 wireless motor commands.
- The Mac application is **ArduDeck**, not Mission Planner. It offers Mission Planning, but the route editor and mission uploading were not completed.

## 2. Logical and physical architecture

```text
                                  Home access point
                             WiFi-Casa / 192.168.1.x
                                        |
                 +----------------------+----------------------+
                 |                      |                      |
      MacBook Pro (ArduDeck)      Raspberry Pi 5         Yahboom ESP32-S3
         192.168.1.57              192.168.1.58          192.168.1.54
         UDP listen :14550         host Debian           UDP micro-ROS client
                 ^                      |                 ROS_DOMAIN_ID=20
                 |                      +-- Docker (host net) --+ 
                 |                          |                    |
       MAVLink over UDP           arboreon-dev             arboreon-agent-udp
       GCS endpoint               ROS 2 Humble              UDP port 8090
                 |                  MAVROS                         |
                 +--- /mavros_router ---+                          |
                                       |                          |
                                   USB /dev/ttyACM0          DDS ROS 2 topics
                                       |                          |
                                 Cube Black / Rover           /cmd_vel -> ESP32
                                    4.7.2                    /odom_raw <- ESP32
                                  (currently HOLD)           /imu, /scan, etc.

Current working motor path: ROS 2 /cmd_vel -> Agent -> ESP32 -> two motor drivers.
Future intended path: Cube Rover servo outputs -> MAVROS /mavros/rc/out
    -> NEW arm-gated, watchdog-protected differential bridge -> /cmd_vel.
```

**Important:** A telemetry connection to Pixhawk is **not** itself a motor-control connection. `/mavros/setpoint_velocity/cmd_vel` is not the Cube's output and should not be misrepresented as the Cube driving the Yahboom motors. The right candidate signal for a PWM-derived bridge is `/mavros/rc/out`, subject to actual output assignment and runtime validation.

### Device / host mapping

| Component | Observed identifier | Notes |
|---|---|---|
| Raspberry Pi | `pi@raspberrypi`, Wi-Fi `192.168.1.58` | Address via DHCP; confirmed for this session. |
| MacBook Pro | `jose@Joses-MacBook-Pro`, Wi-Fi `192.168.1.57` | Command used: `ipconfig getifaddr en0`. |
| Cube Black | `/dev/ttyACM0`, USB `2dae:1011` | MAVROS link at 115200 baud. |
| ESP32-S3 V2 controller USB bridge | `/dev/ttyUSB0`, CP2102 `10c4:ea60` | USB device enumeration does **not** imply current micro-ROS transport is serial. |
| ESP32 controller over Wi-Fi | `192.168.1.54` | Agent log peer address, may change by DHCP. |
| Agent | UDP `0.0.0.0:8090` | Docker `--net=host`, domain 20. |
| ArduDeck connection | UDP `192.168.1.57:14550` | Local receive port on Mac. |
| MAVROS router endpoint | `udp://0.0.0.0:14555@192.168.1.57:14550` | Add as `TYPE_GCS=1`. |

## 3. Reproducible setup: startup order

### 3.1 Host network and persistent Wi-Fi priorities (VERIFIED/RECORDED)

```bash
# On Raspberry Pi host, NOT inside Docker:
sudo nmcli connection modify 'WiFi-Casa' \
  connection.autoconnect yes connection.autoconnect-priority 100
sudo nmcli connection modify 'HUAWEI P20 Pro' \
  connection.autoconnect yes connection.autoconnect-priority 90
sudo nmcli connection modify 'Micro_ros' \
  connection.autoconnect yes connection.autoconnect-priority 10
sudo nmcli connection modify 'Huawei-Internet' connection.autoconnect no

nmcli -f NAME,TYPE,AUTOCONNECT,AUTOCONNECT-PRIORITY connection show
nmcli device status
ip -4 addr show wlan0
ip route
```

After reboot, the user verified that **`WiFi-Casa` connected automatically first**. Huawei fallback was *not* validated. Never publish Wi-Fi credentials in a public Git repo. Prefer a DHCP reservation for `192.168.1.58`, because ESP32 stores this Agent destination.

### 3.2 Manufacturer container autostart (OBSERVED)

Files on the Raspberry host:

`~/.config/autostart/start.desktop`:

```ini
[Desktop Entry]
Encoding=UTF-8
Type=Application
Name=myprogram
Exec=lxterminal -e bash -c "sh /home/pi/start_agent_rpi5.sh"
Terminal=true
```

`~/.config/autostart/uros.desktop`:

```ini
[Desktop Entry]
Encoding=UTF-8
Type=Application
Name=myprogram2
Exec=lxterminal -e bash -c "sh /home/pi/ros2_humble.sh"
Terminal=true
```

The original `/home/pi/start_agent_rpi5.sh` starts a **serial** Agent on `/dev/ttyUSB0` at `921600`. This was **not** compatible with the *actual active* Wi-Fi configuration of the V2 board. Do not assume serial discovery means the motor controller is connected. Stop conflicting Agent instances before testing, and later clean up the autostart configuration so that only the correct intended agent is launched.

Check containers:

```bash
docker ps --format 'table {{.Names}}\t{{.Status}}\t{{.Image}}'
docker ps -a --format 'table {{.Names}}\t{{.Status}}\t{{.Image}}'
docker start arboreon-dev   # only if stopped
```

### 3.3 Yahboom V2 Robot Manager: actual successful settings (VERIFIED)

The correct controller is the older **MicroROS V2** with 2 motors, not Yahboom's different **MicroROS Pi5 X3/4-motor controller**. A **Robot Manager GUI** capable of reading/writing V2 settings successfully changed its communication details. The user observed the GUI and subsequent Agent success; the exact download location, exact button sequence, and complete exported original settings are **not captured here**. Do not invent them.

| Setting | Previously observed | Successfully written / confirmed target |
|---|---|---|
| Wi-Fi SSID | `NOS-149D` | `WiFi-Casa` |
| Agent/server IPv4 | `192.168.1.52` | `192.168.1.58` |
| UDP Agent port | Not reliably retained | `8090` |
| ROS domain | `40` | `20` |
| Car type | `ptz` (recorded earlier) | Preserve V2 model-specific choice unless verified |
| Servo offsets | `-5`, `0` (recorded earlier) | Preserve original calibration |
| Motor PID | `1.80, 0.12, 0.00` (recorded earlier) | Preserve original calibration |
| IMU PID | `2.40, 0.00, 0.16` (recorded earlier) | Preserve original calibration |
| Motor scaling | `1, 1` (recorded earlier) | Preserve original calibration |
| Firmware | `1.1.0` | Not reflashed |

**Power trap:** flipping the board's physical OFF switch while the micro-USB is attached may **not restart the ESP32**; USB can continue supplying logic power. Thus the V2's configuration/connection state can persist across a motor-power switch cycle. Don't blindly use `KEY1` as a reset: its exact function was not verified. A deliberate power cycle/reset must account for every supply path, and should be performed only when it is safe.

**Do not execute** `/home/pi/config_robot.py` directly on this V2 board. Its `__main__` block is intended for the other Pi5 robot and writes `CAR_TYPE_RPI5` and different PID/servo settings. The read-only probes of that mismatched protocol returned `None`; the Robot Manager GUI is what worked.

### 3.4 Start the correct micro-ROS UDP Agent (VERIFIED command)

From Raspberry **host**:

```bash
# Stop/remove only if this exact named test container is already running.
docker ps --format '{{.Names}} {{.Image}}'

# Start once (do not run twice with the same name/UDP port):
docker run -d --rm \
  --name arboreon-agent-udp \
  --net=host \
  -e ROS_DOMAIN_ID=20 \
  microros/micro-ros-agent:humble \
  udp4 --port 8090 -v4

docker logs -f arboreon-agent-udp
```

Logs **after V2 configuration succeeded** showed `create_client`, a **session established from `192.168.1.54`**, then `create_participant` and entities corresponding to publishers, subscriptions and data readers. This is the important difference from the earlier unsuccessful serial and UDP tests. A session reestablishment was observed ~70 s later; intermittent reconnect should be investigated, not ignored, before field use.

If the name already exists, do not create a second instance. A deliberate restart when required:

```bash
docker stop arboreon-agent-udp
# Then run the docker run command above again.
```

### 3.5 ROS2 environment and topic checks (VERIFIED)

**On the Pi host**, use `docker exec`; `ros2` is installed *inside* `arboreon-dev`:

```bash
docker exec arboreon-dev bash -lc '
  source /opt/ros/humble/setup.bash
  export ROS_DOMAIN_ID=20
  ros2 node list
  ros2 node info /micro_ros_task_node
  ros2 topic info /cmd_vel -v
  ros2 topic list
'
```

Actual V2 node and topics at success:

```text
/micro_ros_task_node
  Subscribers:
    /beep            std_msgs/msg/UInt16
    /cmd_ptz_angle   geometry_msgs/msg/Vector3
    /cmd_vel         geometry_msgs/msg/Twist
  Publishers:
    /battery         std_msgs/msg/Float32
    /imu             sensor_msgs/msg/Imu
    /odom_raw        nav_msgs/msg/Odometry
    /ptz_angle       geometry_msgs/msg/Vector3
    /scan            sensor_msgs/msg/LaserScan
```

Earlier `ros2 topic info /cmd_vel -v` showed only `joy_ctrl` as publisher and **zero subscribers**; after successful micro-ROS session the ESP32 was confirmed as the subscriber. Be mindful that the preinstalled joystick is also a publisher on `/cmd_vel`; do not allow joystick commands to compete with a future Pixhawk bridge.

The `/cmd_vel` subscriber QoS was **BEST_EFFORT**. A `rclpy` publisher with the usual reliable profile still successfully drove the motor node in this session. Check actual QoS and topic endpoint discovery when troubleshooting.

### 3.6 Safe connectivity test: buzzer and telemetry (VERIFIED behavior)

```bash
docker exec arboreon-dev bash -lc '
  source /opt/ros/humble/setup.bash
  export ROS_DOMAIN_ID=20
  ros2 topic pub --once /beep std_msgs/msg/UInt16 "{data: 1}"
  ros2 topic pub --once /beep std_msgs/msg/UInt16 "{data: 0}"
'
```

The buzzer started/stopped accordingly. The board published `/battery` = `12.835550308227539` (unit likely volts; verify firmware), and credible `/odom_raw` velocity. Example checks:

```bash
docker exec arboreon-dev bash -lc '
  source /opt/ros/humble/setup.bash
  export ROS_DOMAIN_ID=20
  ros2 topic echo /battery --once
  ros2 topic echo /odom_raw --once
  ros2 topic hz /odom_raw
'
```

### 3.7 The FIRST MOTOR MOVEMENT: test script

**VERIFIED parameters and result:** The user ran a Python 3 `rclpy` script from `/tmp/test_motors.py` inside `arboreon-dev`: `Twist.linear.x=0.03` for ~0.5 seconds, publishing at 10 Hz after ~2 seconds for ROS endpoint discovery; then zero for ~2 seconds. Both suspended wheels turned forward and stopped. `/odom_raw` showed measured `twist.twist.linear.x` roughly `0.00281`, `0.00331`, `0.00475`, `0.00113` m/s during/near the pulse and angular residual up to about `+0.05544 rad/s`; after stop it decayed close to numerical zero. No wheel-ground calibration can be deduced from a half-second airborne test.

**RECONSTRUCTED, self-contained equivalent** of that script (the precise bytes of the original file were not preserved in the available conversation record). Save on Pi host as `~/test_motors.py`:

```python
#!/usr/bin/env python3
"""Bench-only ROS 2 test for Yahboom V2. Wheels suspended, cutter disconnected."""
import time
import rclpy
from geometry_msgs.msg import Twist

TOPIC = '/cmd_vel'
SPEED_M_S = 0.03
PULSE_S = 0.5
RATE_HZ = 10.0
DISCOVERY_S = 2.0
STOP_REPEAT_S = 2.0


def main():
    rclpy.init()
    node = rclpy.create_node('arboreon_bench_motor_test')
    pub = node.create_publisher(Twist, TOPIC, 10)
    period = 1.0 / RATE_HZ
    try:
        # Allow DDS endpoints / micro-ROS graph to discover this publisher.
        t0 = time.monotonic()
        while time.monotonic() - t0 < DISCOVERY_S:
            rclpy.spin_once(node, timeout_sec=0.05)

        # Brief forward wheel command.
        deadline = time.monotonic() + PULSE_S
        while time.monotonic() < deadline:
            msg = Twist()
            msg.linear.x = SPEED_M_S
            pub.publish(msg)
            rclpy.spin_once(node, timeout_sec=0.0)
            time.sleep(period)
    finally:
        # Repeated zero commands make normal stop observable, but do NOT
        # substitute for an independently validated watchdog/power cutoff.
        deadline = time.monotonic() + STOP_REPEAT_S
        while time.monotonic() < deadline:
            pub.publish(Twist())
            rclpy.spin_once(node, timeout_sec=0.0)
            time.sleep(period)
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
```

Copy and execute using the **verified command structure**:

```bash
# Pi host, not Mac:
docker cp ~/test_motors.py arboreon-dev:/tmp/test_motors.py

docker exec arboreon-dev bash -lc '
source /opt/ros/humble/setup.bash
export ROS_DOMAIN_ID=20
python3 /tmp/test_motors.py
'
```

**Safety limitation:** if Wi-Fi fails after a nonzero message, publishing zero in `finally` may not reach the ESP32. This is a bench demonstration, not an acceptable production emergency stop. Do not enable a cutter; do not put wheels on the ground before independent software/hardware protections are tested.

## 4. Cube Black ↔ MAVROS ↔ ArduDeck: exact procedure

### 4.1 Start and inspect MAVROS (VERIFIED)

```bash
# Pi host, interactive shell 1; leave this running:
docker exec -it arboreon-dev bash
source /opt/ros/humble/setup.bash
export ROS_DOMAIN_ID=20
ros2 launch mavros apm.launch fcu_url:=/dev/ttyACM0:115200
```

MAVROS logged `CON: Got HEARTBEAT, connected` / ArduPilot; controller ArduRover **4.7.2**. A second Pi SSH terminal can query:

```bash
docker exec arboreon-dev bash -lc '
source /opt/ros/humble/setup.bash
export ROS_DOMAIN_ID=20
ros2 topic echo /mavros/state --once
ros2 topic echo /mavros/rc/out --once
'
```

Observed state:

```yaml
connected: true
armed: false
guided: false
manual_input: false
mode: HOLD
system_status: 5
```

Observed `rc/out` while disarmed had channel 1 `1500`, channel 2 `0`, channel 3 `1500`, rest `0`. This is a **neutral output observation**, not proof that the Cube is configured for independent wheel drive. Without an RC receiver, `/mavros/manual_control/control --once` may wait indefinitely; the lack of RC input is not in itself a requirement for an autonomous Rover, but arming/failsafe configuration still needs investigation.

`/mavros/imu/data_raw` and `/imu/data` were observed after requesting MAVLink `RAW_IMU` (message ID 27) and `ATTITUDE` (ID 30) at intervals of 50,000 µs (~20 Hz); the precise commands that set those intervals are not preserved here, so do not claim an exact invocation. Indoor GPS remained invalid. A 15-second `timeout ros2 topic echo /mavros/statustext/recv` produced an `ExternalShutdownException` when SIGTERM ended the CLI; this by itself is **not** proof of MAVROS failure.

### 4.2 Pull/read 876 flight-controller parameters (VERIFIED)

```bash
docker exec arboreon-dev bash -lc '
source /opt/ros/humble/setup.bash
export ROS_DOMAIN_ID=20
ros2 service list -t | grep /mavros/param
ros2 service call /mavros/param/pull \
  mavros_msgs/srv/ParamPull "{force_pull: true}"
'
```

**Actual response:**

```text
mavros_msgs.srv.ParamPull_Response(success=True, param_received=876)
```

Read-only parameter inspection:

```bash
docker exec arboreon-dev bash -lc '
source /opt/ros/humble/setup.bash
export ROS_DOMAIN_ID=20
for p in \
  SERVO1_FUNCTION SERVO3_FUNCTION \
  SERVO1_MIN SERVO1_TRIM SERVO1_MAX SERVO1_REVERSED \
  SERVO3_MIN SERVO3_TRIM SERVO3_MAX SERVO3_REVERSED \
  FRAME_CLASS FRAME_TYPE MOT_SKID_FRIC MOT_THR_MIN MOT_THR_MAX \
  FS_THR_ENABLE FS_GCS_ENABLE ARMING_REQUIRE ARMING_CHECK; do
  echo "===== $p ====="
  ros2 param get /mavros/param "$p"
done
'
```

**Observed values (do not overwrite before backup):**

| Parameter | Value | Interpretation / important caveat |
|---|---:|---|
| `SERVO1_FUNCTION` | `26` | Ground steering; **not** differential-left motor yet. |
| `SERVO3_FUNCTION` | `70` | General throttle; **not** differential-right motor yet. |
| `SERVO1_MIN / TRIM / MAX` | `1100 / 1500 / 1900` | Microseconds. |
| `SERVO3_MIN / TRIM / MAX` | `1100 / 1500 / 1900` | Microseconds. |
| `SERVO1_REVERSED` | `0` | No reversal. |
| `SERVO3_REVERSED` | `0` | No reversal. |
| `FRAME_CLASS` | `1` | Class setting as observed; verify meaning against this firmware's metadata. |
| `FRAME_TYPE` | `0` | Frame setting as observed; verify meaning against firmware. |
| `MOT_SKID_FRIC` | `Parameter not set` | Not found; not evidence of a malfunction. |
| `MOT_THR_MIN` | `0` | Configured minimum throttle. |
| `MOT_THR_MAX` | `100` | Configured throttle limit. |
| `FS_THR_ENABLE` | `1` | Throttle failsafe enabled, but **does not guarantee** stop on ROS/Wi-Fi failure. |
| `FS_GCS_ENABLE` | `0` | GCS failsafe disabled; evaluate before autonomous operation. |
| `ARMING_REQUIRE` | `1` | Arming required. |
| `ARMING_CHECK` | `Parameter not set` | Do **not** infer that safety checks were disabled. |

**PROPOSED / NOT EXECUTED:** assign `SERVO1_FUNCTION=73` (Throttle Left) and `SERVO3_FUNCTION=74` (Throttle Right) for ArduRover skid steering **after exporting the original parameter set and checking wiring/output semantics**. No parameter write command was executed in the captured session. Do not turn off arming checks just to make the bench demonstration run.

### 4.3 Discover MAVLink router service (VERIFIED)

```bash
docker exec arboreon-dev bash -lc '
source /opt/ros/humble/setup.bash
export ROS_DOMAIN_ID=20
ros2 node info /mavros_router
ros2 interface show mavros_msgs/srv/EndpointAdd
'
```

Observed router interfaces:

```text
/mavros_router/add_endpoint [mavros_msgs/srv/EndpointAdd]
/mavros_router/del_endpoint [mavros_msgs/srv/EndpointDel]
/uas1/mavlink_sink   (subscriber)
/uas1/mavlink_source (publisher)
```

Exact verified `EndpointAdd` service definition:

```text
uint8 TYPE_FCU = 0
uint8 TYPE_GCS = 1
uint8 TYPE_UAS = 2
string url
uint8 type
---
bool successful
string reason
uint32 id
```

### 4.4 Configure Mac and bridge MAVLink UDP (VERIFIED CONNECTIVITY)

On **MacBook**:

```bash
ipconfig getifaddr en0
# Observed: 192.168.1.57
```

On **Raspberry host**:

```bash
docker exec arboreon-dev bash -lc '
source /opt/ros/humble/setup.bash
export ROS_DOMAIN_ID=20
ros2 service call /mavros_router/add_endpoint \
  mavros_msgs/srv/EndpointAdd \
  "{url: '\''udp://0.0.0.0:14555@192.168.1.57:14550'\'', type: 1}"
'
```

**IMPORTANT evidence distinction:** The exact `add_endpoint` service response (`successful`, `reason`, `id`) was **not pasted** in the captured conversation, but **the user confirmed “ha conectado!!”** and an ArduDeck screenshot showed live MAVLink connection and FCU status. Therefore the end-to-end route is verified from the UI, though the exact endpoint ID was not retained. Do not blindly add duplicate endpoints. If restarting MAVROS, verify whether the dynamic endpoint persists (often not), then add it once if necessary.

**ArduDeck Beta 1.1 (Mac) configuration actually used:**

| UI control | Value |
|---|---|
| Vehicle family | **ArduPilot** (not the default PX4 choice). |
| Transport | **UDP**. |
| Mode | **Listen (Server)**, *not* `Client (Connect)`. |
| Local Port | **14550**. |
| Protocol | **MAVLink**. |
| Connect | Click after starting/enabling the router endpoint. |

In Client (Connect) view, `192.168.1.1` appeared as a default host; this is the **home router/gateway**, not the Raspberry or Cube. The working layout listens for the Raspberry's outgoing MAVLink stream.

**Final screenshot evidence:** Green `UDP :14550`; `HOLD`; `DISARMED`; heading `22°`; speed `0.0 m/s`; throttle `0%`; GPS `No Fix`, satellites `0`; HDOP/VDOP `100.0`; position latitude `0.000000°`, longitude `0.000000°`; altitude display approximately `-5m` (not valid navigational altitude with no GPS fix). The map's displayed satellite imagery was **not** proof of vehicle location. The UI exposed **Mission Planning** via Quick Launch and a map/planning icon.

## 5. Attempting a tiny Mission Planning route: why it stopped here

The operator intended a route of only a few **centimeters**, with wheels safely suspended. This is an appropriate early *command-chain bench test*, but **not a meaningful standalone GPS waypoint navigation test**:

1. Cube had **no GPS fix**, no valid latitude/longitude. A mission can be edited or uploaded, but autonomous `AUTO` waypoint tracking cannot reliably operate without a compatible valid position estimate.
2. Consumer GPS accuracy is far coarser than a few centimeters. For precise centimeters, establish a trusted local navigation source (encoder/IMU odometry and appropriate EKF integration, potentially RTK GNSS outdoors).
3. Yahboom publishes `/odom_raw` in ROS 2, but it was **not** being fused/injected into ArduPilot's navigation estimator. A free-spinning suspended wheel does not equal real-world displacement.
4. Pixhawk did **not** drive `/cmd_vel`; the crucial servo-PWM-to-Twist bridge did not exist yet.
5. Pixhawk was `DISARMED`, `HOLD`, and status `5` (**CRITICAL**). Arming/prearm issues remained unresolved.

**What was done:** ArduDeck connection, FCU telemetry inspection, read-only parameter analysis, discovery of Mission Planning entry point. **What was NOT done:** Mission Planner installation, actual waypoint creation/upload, `AUTO` execution, Pixhawk-led motor movement, route completion.

## 6. Engineering plan to resume with minimum repetition

### Stage A — preserve this working communication chain

1. Verify Wi-Fi IPs (Mac `192.168.1.57`, Pi `192.168.1.58`, V2 ESP32 peer `192.168.1.54` at the time). Consider DHCP reservations; don't hard-code unvalidated addresses in future field deployments.
2. Confirm `arboreon-dev`, UDP Agent and MAVROS are running, domain 20. Ensure only **one** Agent owns UDP port 8090 and only **one** process owns `/dev/ttyACM0`.
3. From ROS 2 inspect `/micro_ros_task_node` publishers/subscribers and `/mavros/state`; confirm agent logs show a real client session.
4. Keep the cutter disconnected, wheels suspended, independent 12 V motor cutoff accessible.
5. Connect ArduDeck using UDP Listen 14550 and, if needed, add the MAVROS GCS endpoint *once*.

### Stage B — back up and configure the Rover outputs (PROPOSED)

1. Export ArduPilot parameter set using a supported MAVLink tool / GCS before changing any function. Record `SERVO1_FUNCTION=26`, `SERVO3_FUNCTION=70`, PWM ranges, reversals and all failsafe values.
2. Review ArduRover 4.7.2 official motor output documentation. Candidate for differential robot: 73 left, 74 right. Set through GCS only after confirming mappings.
3. With Pixhawk disarmed, log `/mavros/rc/out` neutrals; separately diagnose prearm status and verify RC/GCS failsafes, GPS/EKF and intended mode. Do not defeat safety checks to get an armable flag.

### Stage C — read-only differential output interpreter (PROPOSED)

The intended bridge converts two PWM outputs into chassis velocity after measurement and calibration:

```text
u_left  = clamp((PWM_left  - 1500) / 400, -1, +1)
u_right = clamp((PWM_right - 1500) / 400, -1, +1)
v_left  = Vmax * u_left
v_right = Vmax * u_right
linear.x  = (v_right + v_left) / 2
angular.z = (v_right - v_left) / wheel_separation
```

This is an **illustrative symmetric first-order model**, not calibration. `wheel_separation`, motor inversion, dead zone, physical top speeds and the real mapping of `/mavros/rc/out.channels[]` require empirical validation. Neutral is 1500 µs according to the parameters; do not derive movements from `0` PWM values on inactive channels. Prefer logging-only mode first; require a fresh valid MAVROS state message and `armed == true` before **any** nonzero motor command. `HOLD` should yield zeros. Route execution should additionally require an appropriate autonomous mode and valid position source.

### Stage D — controlled bench movement, if and only if gated bridge is verified (PROPOSED)

- Independent emergency stop and hardware power cutoff.
- No competing `/cmd_vel` publishers (`joy_ctrl` may exist) or explicit arbitration; one selected command source.
- Bounds for speed and yaw, explicit deadband, soft-start/rate limiting, saturation and inversion tests.
- Stop on stale PWM, missing MAVROS state, disarm, HOLD, ROS process death and lost Wi-Fi/ESP32 agent. **Software stop messages alone are not an independent failsafe:** validate ESP32-side command timeout or hardware motor enable cutoff.
- Separate supervised tests: left-forward, right-forward, both-forward, reverse, yaw rotation, neutral, loss of connection, disarm.
- Compare encoder odometry against measured ground motion only after safe ground tests; suspended wheels do not provide distance-traveled ground truth.

### Stage E — navigation (PROPOSED)

- Start with heading and local velocity commands; then integrate a trusted position/heading estimate into ArduPilot's EKF (VIO/odometry via supported MAVLink message path or outdoor GNSS/RTK as appropriate).
- Inspect prearm failures (`MAV_STATUSTEXT` in GCS, ArduPilot prearm messages); verify GPS/EKF status and modes.
- For true centimeter trajectories, build a local ROS2 path controller or external-navigation integration, instead of assuming an ordinary outdoor GPS waypoint spacing of centimeters will work.
- Only then upload a test mission using ArduDeck's Mission Planning and execute `AUTO` in controlled surroundings with tested stopping mechanisms.

## 7. Troubleshooting matrix

| Symptom | Likely explanation | Diagnostic / remedy |
|---|---|---|
| `ros2` not found on Raspberry | ROS 2 runs inside Docker | `docker exec arboreon-dev bash -lc 'source /opt/ros/humble/setup.bash; export ROS_DOMAIN_ID=20; ros2 node list'` |
| `/cmd_vel` has 0 subscribers | ESP32 XRCE client did not connect, or domain mismatch | Check UDP Agent logs, V2 SSID/agent IP, ROS domain and `/micro_ros_task_node`. |
| CP2102 `/dev/ttyUSB0` exists but Agent has no client | V2 uses **Wi-Fi UDP**, not Pi5 default serial Agent | Use `udp4 --port 8090`; avoid treating USB enumeration as serial transport proof. |
| `config_robot.py` reads `None` | Wrong controller/protocol or no configuration window | Prefer V2-compatible Robot Manager; do **not** run Pi5 script main. |
| OFF switch fails to reboot ESP32 | USB back-power still present | Account for micro-USB power; investigate correct reset procedure. |
| `docker exec` fails on Mac | Wrong machine has no Raspberry containers | SSH to Pi then `docker exec`. |
| `bash: pi@raspberrypi:~: command not found` | Shell prompt copied as literal command | Copy only command text, not prompt. |
| `/mavros/manual_control/control --once` hangs | No RC input arriving | Doesn't by itself invalidate autopilot telemetry; do not rely on manual input topics. |
| `ARMING_CHECK: Parameter not set` | This named parameter absent in returned ROS parameter tree | Check firmware's param metadata; do not presume checks off. |
| ArduDeck connects but no GPS | Indoor Cube receives no fix | No AUTO waypoint test yet. |
| ArduDeck has heartbeat wait message | Wrong UDP mode/port, missing router endpoint, link not established | Listen Server port 14550, ArduPilot, verify router endpoint and MAVROS heartbeat. |
| Two ROS nodes publish `/cmd_vel` | Manufacturer `joy_ctrl` plus custom control | Build arbiter/stop competing publisher before enabling autopilot bridge. |
| `ExternalShutdownException` after `timeout ... echo` | `timeout` intentionally sends SIGTERM | Not proof of FCU connection loss. |

## 8. Command cheat sheet: one-copy diagnostic collection

From Raspberry host with `arboreon-dev` and MAVROS already running:

```bash
printf '\n=== Host IP/routes ===\n'
ip -4 addr show wlan0
ip route
printf '\n=== Docker ===\n'
docker ps --format 'table {{.Names}}\t{{.Status}}\t{{.Image}}'
printf '\n=== UDP Agent tail ===\n'
docker logs --tail 25 arboreon-agent-udp
printf '\n=== ROS/MAVROS graph ===\n'
docker exec arboreon-dev bash -lc '
source /opt/ros/humble/setup.bash
export ROS_DOMAIN_ID=20
ros2 node info /micro_ros_task_node
ros2 topic info /cmd_vel -v
ros2 topic echo /mavros/state --once
ros2 topic echo /mavros/rc/out --once
'
```

**Run the above only when MAVROS is active.** Some `--once` commands can wait indefinitely if their publisher is missing; use `Ctrl+C` or a controlled timeout where appropriate. Never paste `pi@raspberrypi:~ $` or a Markdown shell prompt as part of the command.

## 9. Links and references

- Yahboom Pi5 study manual (different hardware variant; do not apply its controller configuration uncritically): https://www.yahboom.net/study/MicroROS-Pi5
- Yahboom MicroROS V2 documentation: https://www.yahboom.net/study/MicroROS-V2
- ROS 2 Humble: https://docs.ros.org/en/humble/
- micro-ROS Agent source: https://github.com/micro-ROS/micro-ROS-Agent
- MAVROS: https://github.com/mavlink/mavros
- ArduPilot Rover documentation: https://ardupilot.org/rover/
- ArduPilot servo function reference: https://ardupilot.org/rover/docs/common-rcoutput-mapping.html

Where a URL is provided as a reference, verify the current page and firmware-specific values before implementation. This handover is primarily a record of actual session commands and observations, not proof that every external reference was consulted during the session.

---

## Appendix A — Earlier detailed troubleshooting report (historical, **superseded status**)

The following earlier report was saved before the successful Robot Manager Wi-Fi reconfiguration, motor test, and ArduDeck connection. It is preserved **verbatim** for historical commands and diagnostic reasoning. Statements like “Agent not connected” and “motors not tested” in this appendix describe an **earlier point in time** and are now superseded by Sections 1–8 above.

# ARBOREON — Raspberry Pi 5 Connectivity and Pixhawk–Yahboom Integration

**Technical configuration record and troubleshooting handover**  
**Date:** 29 October 2026  
**Status:** Home Wi-Fi automatic reconnection verified; Cube Black ↔ MAVROS verified; Yahboom ESP32-S3 ↔ micro-ROS not yet established; motors not tested.  
**Platform:** Yahboom MicroROS V2 **two-drive-motor** robot, Raspberry Pi 5 (8 GB), Pixhawk Cube Black, ROS 2 Humble in Docker.

> **Purpose.** Preserve the actual settings, shell commands, observations, unsuccessful experiments, architecture, and next actions so development can resume without reconstructing the troubleshooting history. Commands shown under **Observed** reflect session evidence; commands under **Proposed** have **not** necessarily been run. Avoid interpreting a proposed configuration as already applied.

## 1. Executive summary

### Confirmed achievements

1. The Raspberry Pi 5 can join the home WLAN `WiFi-Casa`, was observed with IPv4 address **192.168.1.58/23**, default gateway **192.168.1.1**, and could reach `1.1.1.1` (3/3 pings in an earlier test).
2. NetworkManager connection profiles were assigned priorities **100** (`WiFi-Casa`), **90** (`HUAWEI P20 Pro`), and **10** (`Micro_ros`), with automatic connection enabled. After a deliberate Raspberry reboot, the user **observed automatic connection to `WiFi-Casa` first**. Automatic failover to Huawei and the Yahboom hotspot has **not** been tested.
3. The Raspberry recognizes **CubeBlack** as `/dev/ttyACM0` (USB vendor/product `2dae:1011`) and the Yahboom board's **Silicon Labs CP2102 USB–UART bridge** as `/dev/ttyUSB0` (`10c4:ea60`). The onboard controller is visibly based on an **ESP32-S3-WROOM-1U** module.
4. The `arboreon-dev` Docker container (image `arboreon:backup`) contains ROS 2 Humble and installed **MAVROS 2.16.0**. `ros2 launch mavros apm.launch fcu_url:=/dev/ttyACM0:115200` successfully connected to **ArduRover 4.7.2**. `/mavros/state` confirmed `connected: true`, `armed: false`, `guided: false`, `mode: HOLD`, `system_status: 5`.
5. The Yahboom Pi5 image automatically launches both its ROS 2 container and a **serial micro-ROS Agent** at **921600 baud**, but logs showed only serial-port initialization, without any client/session/participant creation.
6. `/cmd_vel` was visible in ROS domain **20** with one publisher (`joy_ctrl`) and **zero subscribers**. No control path to the two motors has been verified. No physical wheel movement was commanded.
7. A replacement **UDP agent** on port **8090** was successfully started on the Raspberry; it also showed no client session. A 15-second `tcpdump` capture on `wlan0` for UDP port 8090 captured **zero packets** (the board's actual network and transport configuration remains unknown).

### Crucial unresolved issues

- Which firmware and transport (**UART serial vs Wi-Fi UDP**) the **two-motor MicroROS V2** board currently uses; what SSID, Agent IP, UDP port, ROS domain and car type it has stored; and how to access its configuration mode reliably.
- Whether the ESP32-S3 is actually power-cycled by the physical switch; the board may remain powered over **micro-USB** even when the motor-power switch is OFF.
- How to restore micro-ROS board topics (`/YB_Car_Node`, `/cmd_vel`, `/beep`, `/imu`, `/odom`, `/scan` as documented for the Pi5 model) without overwriting the V2 board's PID/calibration parameters.
- How to bridge ArduPilot Rover commands to ROS 2 `geometry_msgs/Twist`, validate independent emergency stop and timeouts, resolve ArduPilot's status/prearm issues, and safely test a few centimeters of travel.

---

## 2. Physical equipment and operating environment

| Element | Identified details | Connection / caveat |
|---|---|---|
| Computing | Raspberry Pi 5, 8 GB; Debian Bookworm ARM64 host; home Wi-Fi | ROS 2 is inside Docker, **not installed as `ros2` on the host**. |
| Motor chassis | Yahboom MicroROS V2; **two motor connectors** (`Motor1`, `Motor2`); motors with encoders | Do **not** assume the Pi5 four-motor firmware/wiring is identical. |
| Controller | ESP32-S3-WROOM-1U module, OLED display, buzzer, LEDs, USB-A and micro-USB, `KEY1` | Button labeled `KEY1` is **not confirmed** as RESET; do not press it as a substitute. |
| USB–UART | Silicon Labs CP2102, `10c4:ea60` | Raspberry `/dev/ttyUSB0`; board micro-USB is connected to Raspberry. |
| Flight controller | Cube Black, ArduRover 4.7.2 | Raspberry `/dev/ttyACM0`, MAVLink via MAVROS. |
| Camera | HP 320 FHD USB webcam, `03f0:654a` | ROS/vision tasks independent of motor control. |
| LiDAR | RPLIDAR C1 | ROS 2 scan data was previously observed; full integration pending. |
| Other | Bluetooth speaker paired; Wi-Fi via NetworkManager; remote access via SSH/VNC and user-mentioned ArduDeck | Audio dialogue and voice control are separate future projects. |
| Power | External motor/electronics supply plus USB were used during testing; later 12 V to 5 V/10 A DC/DC planned for mobile operation | Exact power topology and whether OFF cuts ESP32 power remain **unverified**. |

**Safety throughout commissioning:** suspend drive wheels; disconnect any mowing/cutting actuator; keep an accessible independent hardware power cutoff; leave Pixhawk disarmed; never issue a continuous `/cmd_vel` command before a validated motor watchdog and stop procedure exist.

---

## 3. Raspberry Wi-Fi network configuration: what changed

### 3.1 Context and initial behavior

The supplied Yahboom Raspberry image originally exposed or used an AP/hotspot profile called **`Micro_ros`** (factory remote access documented at **10.42.0.1**). The aim was to join the home's existing WLAN while preserving `Micro_ros` as a recovery fallback. NetworkManager also had mobile-tethering profiles: `HUAWEI P20 Pro`, `Huawei-Internet`, `NOS-149D`, and `Yahboom2`.

The user was able to join `WiFi-Casa` manually, but an earlier reboot did **not** reliably reconnect there. After priorities were corrected and an additional reboot was performed, the Raspberry **automatically selected `WiFi-Casa`**. The underlying cause of the earlier failed autoconnect was **not conclusively isolated**; priority ordering and possible competing profiles were addressed.

### 3.2 NetworkManager settings: commands used/recommended

The persistent profile priority settings were set/confirmed with commands of the following form:

```bash
sudo nmcli connection modify "WiFi-Casa" \
  connection.autoconnect yes \
  connection.autoconnect-priority 100

sudo nmcli connection modify "HUAWEI P20 Pro" \
  connection.autoconnect yes \
  connection.autoconnect-priority 90

sudo nmcli connection modify "Micro_ros" \
  connection.autoconnect yes \
  connection.autoconnect-priority 10
```

`Huawei-Internet` is a **separate profile** from the phone's Wi-Fi hotspot. Disabling its automatic connection was recommended to prevent unwanted routing through another interface:

```bash
sudo nmcli connection modify "Huawei-Internet" connection.autoconnect no
```

**Observation caveat:** a `nmcli connection show` listing captured **before** the final changes showed `Huawei-Internet` set to autoconnect `yes` at priority **41**, and `HUAWEI P20 Pro` at priority **21**. The user then requested Huawei Wi-Fi priority **90**, and the next reboot successfully chose home Wi-Fi. We **did not capture a final full NetworkManager dump showing every profile after that reboot**. Check current live values before relying on them.

### 3.3 Verified profile listing before final adjustment

```text
NAME                 AUTOCONNECT    AUTOCONNECT-PRIORITY
WiFi-Casa            yes            100
lo                   no             0
docker0              no             0
Conexión cableada 1  yes           -999
HUAWEI P20 Pro       yes             21
Huawei-Internet      yes             41
Micro_ros            yes             10
NOS-149D             yes              0
Yahboom2             yes              0
```

**Final intended priority:** `WiFi-Casa` = 100; `HUAWEI P20 Pro` = 90; `Micro_ros` = 10. Other Wi-Fi profiles (`NOS-149D`, `Yahboom2`) remained present at priority 0. Whether they should remain enabled depends on future field operation.

### 3.4 How to connect / verify

```bash
# Host, outside Docker
nmcli device status
nmcli -f NAME,TYPE,AUTOCONNECT,AUTOCONNECT-PRIORITY connection show

# Connect manually if necessary (profile must already exist)
sudo nmcli connection up "WiFi-Casa"

# Check address and default gateway
ip -4 addr show wlan0
ip route

# Check Internet route
ping -c 3 1.1.1.1
```

**Observed successful networking:** `wlan0` `192.168.1.58/23`, gateway `192.168.1.1`, Internet ping successful. The address is **DHCP-assigned**, not a static reservation; it can change. One displayed lease later had a finite remaining lifetime. For a reliable ESP32 UDP agent endpoint, reserve the Raspberry IP in the router's DHCP service or otherwise provide a stable discovery/address plan before writing it into board firmware.

### 3.5 Verified reboot outcome

The user ran `sudo reboot`, reconnected after startup and explicitly reported **"Conectó primero con la wifi de casa"**. Thus **automatic connection to the first-choice WLAN is verified**. The following **have not been tested**: fall back to Huawei when home WLAN disappears; return to home WLAN from Huawei without an interface reconnect; fail over to `Micro_ros`; and uninterrupted SSH during transition (not expected when a single Wi-Fi radio changes networks).

### 3.6 Remote access and pitfalls

```bash
# Run from the Mac, not the Pi
ssh pi@raspberrypi.local
# or use the current DHCP address, observed as:
ssh pi@192.168.1.58
```

From the host shell, a typical prompt is `pi@raspberrypi:~ $`. `docker exec ...` must be run **after SSH login to the Pi**, not from the Mac's local `jose@Joses-MacBook-Pro` prompt. The Mac's local Docker daemon was absent and a `docker exec` there failed; this was a host-selection mistake, not a Raspberry Docker failure.

The Yahboom hotspot can be a rescue option when normal WLAN is unavailable, but its AP operation and client infrastructure Wi-Fi compete for the Pi's wireless interface. Avoid unnecessary NetworkManager changes during robotics tests.

### 3.7 Network follow-up tasks

- Capture final priority state after a reboot.
- Verify `Huawei-Internet` remains set to `autoconnect no` if this is still desired; do not confuse it with `HUAWEI P20 Pro` Wi-Fi.
- Test Huawei fallback at a controlled moment; **do not** deliberately cut the user's only remote path without local console access.
- Reserve `192.168.1.58` in the DHCP server (if available), otherwise update the ESP32's configured Agent IP after DHCP changes.
- Keep any Wi-Fi password out of repositories and screenshots; do not embed credentials in this document.

---

## 4. Docker and auto-start architecture discovered

### 4.1 Docker images and containers

| Container/image | Purpose | Status in last relevant capture |
|---|---|---|
| `yahboomtechnology/ros-humble:4.1.2` | Manufacturer's ROS 2 Humble stack | Auto-started under names such as `magical_montalcini`; previously `brave_heyrovsky`. |
| `microros/micro-ros-agent:humble` | Manufacturer's Agent, normally serial | Auto-started under names such as `strange_volhard`; **later stopped manually** for testing. |
| `arboreon-dev` / `arboreon:backup` | Custom ROS 2 + MAVROS environment | Manually started; used for the successful Cube Black connection. |
| `arboreon-agent-udp` / `microros/micro-ros-agent:humble` | Experimental UDP agent at port 8090 | Started and logged `running...`; not confirmed connected to ESP32. |

Container names are automatically generated and **change after restart**. Re-discover:

```bash
docker ps --format 'table {{.Names}}\t{{.Status}}\t{{.Image}}'
docker ps -a --format 'table {{.Names}}\t{{.Status}}\t{{.Image}}'
```

### 4.2 Desktop autostart

`~/.config/autostart/start.desktop`:

```ini
[Desktop Entry]
Encoding=UTF-8
Type=Application
Name=myprogram
Exec=lxterminal -e bash -c "sh /home/pi/start_agent_rpi5.sh"
Terminal=true
```

`~/.config/autostart/uros.desktop`:

```ini
[Desktop Entry]
Encoding=UTF-8
Type=Application
Name=myprogram2
Exec=lxterminal -e bash -c "sh /home/pi/ros2_humble.sh"
Terminal=true
```

**Consequence:** each graphical desktop session may spawn fresh, unnamed Docker containers. Avoid running another Agent on the same serial device; audit active instances before manual startup. Autostart has **not** been permanently changed.

### 4.3 Original serial Agent script

`/home/pi/start_agent_rpi5.sh` contains a commented UDP example and an active serial command:

```bash
#!/bin/bash
# WIFI (commented out)
# docker run -it --rm -v /dev:/dev -v /dev/shm:/dev/shm --privileged --net=host \
#   microros/micro-ros-agent:humble udp4 --port 8090 -v4

# Serial (active)
docker run -it --rm -v /dev:/dev -v /dev/shm:/dev/shm \
  --privileged --net=host microros/micro-ros-agent:humble \
  serial --dev /dev/ttyUSB0 -b 921600 -v4
```

This indicates that **both transports are contemplated by the original script**, but the Pi5 image defaults to **serial**.

### 4.4 Manufacturer ROS container script

`/home/pi/ros2_humble.sh` starts the manufacturer image using privileged host networking, X11 environment, and `/bin/bash /root/1.sh`:

```bash
xhost +
docker run -it \
  --privileged=true \
  --net=host \
  --env="DISPLAY" \
  --env="QT_X11_NO_MITSHM=1" \
  -v /tem/.X11-unix:/tmp/.X11-unix \
  --security-opt apparmor:unconfined \
  -v /dev/input:/dev/input \
  -v /dev/video0:/dev/video0 \
  yahboomtechnology/ros-humble:4.1.2 /bin/bash /root/1.sh
```

**Note:** The source contained `/tem/.X11-unix` (not `/tmp/.X11-unix`) on the host side; this may be a typo but the manufacturer container nevertheless launched. `xhost +` relaxes X11 access controls; consider tightening it in a future hardening pass, not during the current motor-link recovery.

Inside the container, `/root/1.sh` sources ROS Humble, sources `/root/yahboomcar_ws/install/setup.bash`, and starts `supervisor`. Its script also contains an `exec bash` before a subsequent `python3 ~/publish_ip.py`, meaning the later command may not execute as intended; an `IPServer` Supervisor program was separately active.

### 4.5 Supervisor and joystick program

```text
ChassisServer    RUNNING    pid 125
IPServer         RUNNING    pid 126
```

`/etc/supervisor/conf.d/chassis.conf`:

```ini
[program:ChassisServer]
command=sh /root/run_handle.sh
directory=/root/
autostart=true
```

`/root/run_handle.sh` executes:

```bash
source /opt/ros/humble/setup.bash
source /root/yahboomcar_ws/install/setup.bash
ros2 launch yahboomcar_ctrl yahboomcar_joy_launch.py
```

The launch file **only** starts `yahboomcar_ctrl/yahboom_joy` and `joy/joy_node`. It does **not** start a motor bridge. Supervisor log showed both nodes starting. Process inspection confirmed they were running.

The manufacturer workspace includes `yahboomcar_base_node`, `yahboomcar_bringup`, `yahboomcar_ctrl`, and description/navigation packages. `yahboomcar_base_node/src/base_node_X3.cpp` subscribes to `odom_raw` and contains a `wheelbase_ = 0.25` default; **do not infer this is the actual two-motor wheel separation**. The principal `yahboomcar_bringup_launch.py` printed `robot_type = x3` and included IMU filtering, EKF, static TF, and robot description; it did not reveal the missing `cmd_vel` subscriber.

---

## 5. ROS 2 domains, nodes and topic findings

### 5.1 Domain 20 is the current integration target

The actual environment of the running `yahboom_joy` process (`/proc/174/environ`) contained:

```text
ROS_DOMAIN_ID=20
```

The `arboreon-dev` environment also used domain **20** (`MY_DOMAIN_ID: 20`). An earlier attempt to inspect Yahboom topics in domain **0** returned `Unknown topic '/cmd_vel'`; that was **not proof of a broken joystick**, because the live joystick process was configured for domain 20.

ROS 2 CLI discovery was not entirely consistent across commands: `ros2 node list --no-daemon` in the Yahboom container showed only `/local_ip_publisher`, while `ros2 topic info /cmd_vel -v` in domain 20 identified `joy_ctrl` as publisher. Treat discovery/caching and potentially DDS implementation as a *secondary* issue, not the primary cause of absent motor control.

### 5.2 `/cmd_vel` findings

```text
Type: geometry_msgs/msg/Twist
Publisher count: 1
Node name: joy_ctrl
Subscription count: 0
```

The manufacturer's example expects the ESP32-side `/YB_Car_Node` to subscribe to `/cmd_vel` and `/beep`, and to publish IMU/odometry/LiDAR topics **when it connects**. Those are **documented expected interfaces**, not observed live interfaces on this two-motor V2 board.

### 5.3 Commands to verify after the Agent connects

Inside the **right container** (not the Debian host):

```bash
source /opt/ros/humble/setup.bash
export ROS_DOMAIN_ID=20
ros2 node list
ros2 topic list
ros2 topic info /cmd_vel -v
ros2 node info /YB_Car_Node   # only if this node really appears
```

**Non-movement test, only after confirming the board's `/beep` topic and type:**

```bash
ros2 topic info /beep
# If and only if the type is std_msgs/msg/UInt16:
ros2 topic pub --once /beep std_msgs/msg/UInt16 '{data: 1}'
ros2 topic pub --once /beep std_msgs/msg/UInt16 '{data: 0}'
```

Confirm buzzer behavior is safe and there is no unexpected actuator behavior. A buzzer test alone does not prove motor control/stop safety.

---

## 6. Cube Black and MAVROS: confirmed operational

### 6.1 Hardware identification

`lsusb`:

```text
Bus 001 Device 003: ID 2dae:1011 Hex/ProfiCNC CubeBlack
Bus 001 Device 002: ID 10c4:ea60 Silicon Labs CP210x UART Bridge
Bus 003 Device 002: ID 03f0:654a HP, Inc HP 320 FHD Webcam
```

Host devices:

```text
/dev/ttyACM0  # Cube Black
/dev/ttyUSB0  # Yahboom CP2102 bridge
```

`sudo fuser -v /dev/ttyACM0 /dev/ttyUSB0` previously showed the Agent occupying only `/dev/ttyUSB0`, leaving Cube Black free for MAVROS.

### 6.2 MAVROS container and launch

`arboreon-dev` inspect returned:

```text
Network=host Privileged=true
Devices=[]
```

With `--privileged`, the absence of explicit `Devices` mapping does **not** by itself prevent access to host USB devices; this was borne out by the Cube connection.

Host terminal:

```bash
docker start arboreon-dev
docker exec -it arboreon-dev bash
```

Inside the container:

```bash
source /opt/ros/humble/setup.bash
export ROS_DOMAIN_ID=20
ros2 pkg list | grep mavros
ros2 launch mavros apm.launch fcu_url:=/dev/ttyACM0:115200
```

A separate terminal is used to inspect ROS topics while that launch remains running:

```bash
ssh pi@raspberrypi.local
docker exec -it arboreon-dev bash
source /opt/ros/humble/setup.bash
export ROS_DOMAIN_ID=20
ros2 topic echo /mavros/state --once
```

### 6.3 Confirmed `/mavros/state`

```yaml
connected: true
armed: false
guided: false
manual_input: false
mode: HOLD
system_status: 5
```

MAVROS log earlier included `CON: Got HEARTBEAT, connected. FCU: ArduPilot`, reporting **ArduRover 4.7.2**.

### 6.4 Outstanding flight-controller issues

- `system_status: 5` corresponds to **MAV_STATE_CRITICAL**: investigate actual messages/prearm failures rather than interpreting the state field alone as a specific failed component.
- `No GPS fix` was logged indoors; fix/status was invalid, so do not use the previously displayed latitude/longitude for navigation.
- `RTT too high for timesync` warnings appeared (approximately 20 ms). Investigate if timestamp alignment affects sensor fusion, but this did **not** prevent MAVLink heartbeats.
- Earlier commands set MAVLink message intervals for RAW_IMU (ID 27) and ATTITUDE (ID 30) to **50,000 µs** (about 20 Hz); both were acknowledged, but settings may not persist across resets.
- Cube Black is linked to the Raspberry via MAVLink **telemetry**; it does not directly energize Yahboom motor drivers. A deliberate **MAVLink-to-Twist bridge and safety arbiter** is required.
- Neither ArduPilot guided drive nor arming has been validated for this robot. Investigate `STATUSTEXT`, parameters, RC/mode/failsafe configuration, and adequate safety interlocks before attempting movement.

---

## 7. Yahboom micro-ROS investigation: detailed chronology

### 7.1 Serial Agent opened USB but no session

Manufacturer's default Agent command:

```bash
micro_ros_agent serial --dev /dev/ttyUSB0 -b 921600 -v4
```

Container logs across several restarts consistently showed only:

```text
TermiosAgentLinux.cpp | init | running... | fd: 3
Root.cpp | set_verbose_level | logger setup | verbose_level: 4
```

No `create_client`, `create_participant`, `create_subscriber`, or related XRCE-DDS activity was observed. `fd: 3` means an open file descriptor, **not** an established micro-ROS client.

### 7.2 USB detection was stable during normal operation

```bash
ls -l /dev/ttyUSB0
lsusb | grep -i -E 'silicon|cp210'
sudo udevadm info -q property -n /dev/ttyUSB0 | grep -E 'ID_VENDOR|ID_MODEL|ID_SERIAL'
```

Observed:

```text
Silicon Labs CP2102 USB to UART Bridge Controller
ID_VENDOR_ID=10c4
ID_MODEL_ID=ea60
ID_SERIAL_SHORT=0001
```

The `dmesg` stream also correctly tracked physical unplugging/replugging of the CP2102. Repeated entries like `cp210x converter now attached to ttyUSB0` prove USB enumeration, **not** successful ESP32 application communication.

### 7.3 Raw serial experiments were inconclusive

After releasing the serial port, `cat /dev/ttyUSB0 | od -An -tx1` briefly produced primarily `00` and `80` bytes. Explicit host `stty -F /dev/ttyUSB0 921600 raw -echo -ixon -ixoff -crtscts cs8 -parenb -cstopb` did not produce interpretable frames. A later three-second capture produced **0 bytes**.

These outputs do **not** prove the ESP32 speaks that baud rate, prove firmware failure, or establish whether the observed bytes represented valid packets; they may reflect incompatible transport, startup state, timing, or electrical/line settings. Avoid further blind baud-rate trials.

### 7.4 Read-only attempts with original Pi5 `config_robot.py`

Located at:

```text
/home/pi/config_robot.py (17,545 bytes; file dated 2024-02-19)
```

The class `MicroROS_Robot` opens `/dev/ttyUSB0` at **115200 baud** for **configuration**, distinct from the original serial Agent's **921600 baud**. The protocol sends frames beginning `0xFF 0xF8` and expects `0xFF 0xF7` responses; it supports Wi-Fi SSID/password, Agent IP/port, car type, ROS domain, serial baud, servo offsets, PID values and reboot functions.

**CRITICAL:** running the script as `python3 config_robot.py` executes its `__main__` section and **writes settings**, including:

```python
robot.set_car_type(robot.CAR_TYPE_RPI5)
robot.set_ros_domain_id(20)
robot.set_ros_serial_baudrate(921600)
robot.set_ros_namespace("")
robot.set_pwm_servo_offset(1, 0)
robot.set_pwm_servo_offset(2, 0)
robot.set_motor_pid_parm(1, 0.2, 0.2)
robot.set_imu_yaw_pid_parm(1, 0, 0.2)
```

**Do not run that main block on the two-motor V2 board.** It could overwrite model designation and genuine motor/IMU calibration.

A safe import-only query was attempted:

```python
from config_robot import MicroROS_Robot
robot = MicroROS_Robot(port='/dev/ttyUSB0', debug=False)
try:
    print('Firmware:', robot.read_version())
    print('Car type:', robot.read_car_type())
    print('ROS domain:', robot.read_ros_domain_id())
    print('Agent IP:', robot.read_agent_ip_addr())
    print('Agent port:', robot.read_agent_ip_port())
    print('Serial baudrate:', robot.read_ros_serial_baudrate())
finally:
    del robot
```

All six reads returned **`None`**. An additional repeated read loop also returned no response. The initial repetition was carried out without a physical reset; a later repetition involved moving the physical power switch, but the user subsequently discovered that the board could remain powered from USB, so a **real ESP32 reset during its 5-second configuration window has not been conclusively demonstrated**. Even with a real reset, the Pi5 configuration protocol may differ from V2 firmware.

### 7.5 Manufacturer timing guidance

The **Pi5 manual** states that the micro-ROS board enters configuration mode for approximately **five seconds after reset**, with MCU LED blinking approximately every 300 ms, and instructs `python3 config_robot.py` within that window. This is **a procedure for the Pi5 controller**. The two-motor V2 may have different firmware and GUI tooling. A visible `KEY1` button on V2 was **not established** as reset. Do not use unverified buttons or flashing procedures.

### 7.6 UDP Agent experiment

Started on Raspberry host-network Docker:

```bash
docker run -d --rm \
  --name arboreon-agent-udp \
  --net=host \
  -e ROS_DOMAIN_ID=20 \
  microros/micro-ros-agent:humble \
  udp4 --port 8090 -v4
```

Log:

```text
UDPv4AgentLinux.cpp | init | running... | port: 8090
Root.cpp | set_verbose_level | logger setup | verbose_level: 4
```

Host packet check:

```bash
sudo timeout 15 tcpdump -ni wlan0 'udp port 8090'
```

Result:

```text
0 packets captured
0 packets received by filter
0 packets dropped by kernel
```

No UDP client packets on `wlan0:8090` were observed **during that capture interval**. It is not evidence that V2 lacks UDP support; board's stored SSID/IP may be wrong, or its Wi-Fi may not have been initialized then. The exact timing of board reset during that particular 15-second capture was not confirmed.

### 7.7 Neighbor IP test did not identify the ESP32

The Raspberry was at `192.168.1.58`; an active neighbor at `192.168.1.57` (`f6:ff:88:57:b3:d1`) responded to pings. The MAC is locally administered and cannot reliably identify manufacturer. Pings continued while the user reported the Yahboom controller was fully switched off, strongly suggesting `.57` is **another device**, provided board power was indeed absent. Do **not** configure `.57` as the board or Agent IP on this basis.

### 7.8 Power discovery and USB reconnects

A key observation: the **Yahboom switch did not necessarily switch off the ESP32** while the Raspberry micro-USB cable remained connected. This undermines earlier assumptions about a physical reset. The user later confirmed the display and indicators were off, and unplug/replug activity was captured in `dmesg`. The most recent supplied `dmesg -w` output ended with a **USB disconnect** at `[4306.158397]`, with no later attach shown in that excerpt. **Re-check `/dev/ttyUSB0` now** rather than assuming the board remains connected.

Suggested read-only checks:

```bash
ls -l /dev/ttyUSB0
sudo fuser -v /dev/ttyUSB0
dmesg | grep -E 'cp210|ttyUSB' | tail -20
```

---

## 8. MicroROS V2 Robot Manager screenshots: what they do and do not prove

The user supplied screenshots of an application labeled **Robot Manager** (running in a graphical Ubuntu environment, not proven installed on the Raspberry). The **Info** page reported:

```text
Robot Model: MicroRosV2
ROS_DOMAIN_ID: 40
CAR_TYPE: ptz
Current IP: 192.168.1.52
Camera IP: 192.168.1.53
System Image Version: MicroRosV2 1.0.1, released 2026-10-08
Board serial (/dev/microros_board): Not detected
```

**Board Config** displayed:

```text
Serial Port: /dev/ttyUSB0
wifi_ssid: NOS-149D
agent_ip_addr: 192.168.1.52
agent_ip_port: 8090
ros_domain_id: 40
ros_namespace: optional
servo_1_offset: -5
servo_2_offset: 0
motor_pid (P,I,D): 1.8, 0.12, 0.0
imu_yaw_pid (P,I,D): 2.4, 0.0, 0.16
linear_scale: 1.0
angular_scale: 1.0
Loaded last-used/default board config.
```

**CRITICAL distinction:** These values may describe the GUI's **host profile or last-used/default settings**, **not live values read from the physical V2 controller**. The Info screen explicitly warned that `/dev/microros_board` was **Not detected**. No successful **Read Board** response or **Verify** response has been documented. The screen also exposed a Dify API token; do not place screenshots with secrets in public repositories. Rotate the token if genuine.

The GUI was **not found** in normal locations on the Pi:

```bash
command -v robotmanager
command -v robot-manager
find /opt /usr/local /home/pi -iname '*robot*manager*' 2>/dev/null
```

No matches were returned. This means it was not in these checked locations; it does **not** establish that no V2 management tools are available elsewhere (e.g., another Ubuntu VM, an external image, an app bundle).

**Documented V2 approach:** Wi-Fi/UDP micro-ROS Agent port 8090, same LAN, matching Agent IP and `ROS_DOMAIN_ID`; the manufacturer's V2 Agent tutorial identifies a **steady green LED** as successful Agent connectivity. See references.

---

## 9. Desired complete control architecture

```text
Mac / remote workstation (SSH, UI / future operator control)
                 |
             WiFi-Casa
                 |
    Raspberry Pi 5 (Debian host, 192.168.1.58 at last observation)
       |                                     |
       | USB /dev/ttyACM0                    | Wi-Fi UDP 8090 OR UART /dev/ttyUSB0
       v                                     v
 Pixhawk Cube Black                 Yahboom MicroROS V2 ESP32-S3
 ArduRover 4.7.2                    /YB_Car_Node (expected, not observed)
       |                                     |
       v                                     v
 MAVROS, ROS_DOMAIN_ID=20            Two motor channels, encoder feedback
       |                                     ^
       v                                     |
 Verified MAVLink telemetry          /cmd_vel subscriber (currently missing)
       |                                     ^
       +--> [TO DESIGN] safety-checked rover-command -> Twist bridge
                                |
                         stop watchdog, priority mux,
                         arm/mode/failsafe gating
```

**Architectural caution:** `MAVROS /mavros/setpoint_velocity` is primarily an interface for supplying velocity *setpoints to ArduPilot*, not automatically a path for reading its intended motor commands. Selecting the direction of information flow (Pixhawk plans/guides, Raspberry executes wheel velocities) requires a deliberate protocol design. Consider consuming appropriate ArduPilot control/actuator targets or defining a constrained higher-level motion-command protocol, and mapping to differential-drive `Twist` with explicit supervision. Verify the availability and semantics of selected MAVROS/MAVLink messages for ArduRover 4.7.2; do **not** assume a built-in MAVROS-to-`/cmd_vel` bridge exists.

### Differential-drive model (after calibration)

For wheel radius `r`, effective wheel track `b`, commanded linear velocity `v` and angular velocity `omega`, target wheel angular velocities are:

```text
left_wheel_rad_s  = (v - omega*b/2) / r
right_wheel_rad_s = (v + omega*b/2) / r
```

Actual channel polarity, motor ordering, wheel radius/track, encoder count and closed-loop PID must be measured. Do not use the Pi5 sample `wheelbase_ = 0.25` as an unverified actual dimension.

### Movement milestone

A **future** test might command 0.05 m/s for 1 second (nominally 5 cm) **only after** successful stop, watchdog, scaling, and physical motion checks with wheels in the air. Nominal kinematic distance is **not** a measured traveled distance. Do not try to arm ArduPilot with critical/prearm errors or bypass safety checks merely to produce movement.

---

## 10. Recommended recovery and commissioning plan

### Phase A — preserve known-good state

1. Keep `WiFi-Casa` autoconnect first; do not alter network profiles unnecessarily.
2. Back up copies of `~/.config/autostart/*.desktop`, `/home/pi/start_agent_rpi5.sh`, `/home/pi/ros2_humble.sh`, `/home/pi/config_robot.py`, and *sanitized* NetworkManager **non-secret** profile metadata. Do **not** commit `*.nmconnection`, stored passwords, or API keys.
3. Check container state and serial-port ownership before every new session. Docker auto-start may create additional containers and Agent instances.
4. Record OS/firmware versions and commit revisions of integration scripts once confirmed.

### Phase B — determine V2 controller's actual configuration / transport

1. Check whether CP2102 currently enumerates and if the board is actually powered.
2. Find/obtain **the V2-specific Robot Manager or configuration program** from the manufacturer's V2 documentation; run it on the system with actual access to `/dev/ttyUSB0` (not an unrelated Mac/VM without USB passthrough).
3. Verify the physical reset mechanism. Confirm that the ESP32 is truly reset even while USB power remains present; **do not assume the ON/OFF switch performs a full MCU reset**.
4. With all other serial users stopped, attempt **read-only** V2-specific board discovery during the manufacturer-specified configuration window. Record firmware, transport, SSID, Agent IP/port, ROS domain, motor PID and car type.
5. If USB configuration fails, inspect the V2 firmware version/manual and ask Yahboom support for the expected device and reset method. **Do not flash speculative Pi5 four-motor firmware.**

### Phase C — bring up the correct Agent and topic graph

**If the board is confirmed UDP Wi-Fi firmware:**

- Ensure V2 ESP32 joins a supported **2.4 GHz** WLAN with reachability to the Pi.
- Ensure the stored Agent IP matches the Raspberry's **current stable IP** (last observed `192.168.1.58`), port `8090`, ROS domain `20`; save through the V2-specific supported tool only after backing up values.
- Start just one Agent:

```bash
docker run -d --rm --name arboreon-agent-udp \
  --net=host -e ROS_DOMAIN_ID=20 \
  microros/micro-ros-agent:humble udp4 --port 8090 -v4
```

- Check `docker logs`, `sudo ss -lunp | grep 8090`, and, if necessary, a packet capture. Firewall must permit inbound UDP 8090. Confirm the Agent logs a client session and the ROS graph includes the board's subscriber(s).

**If the board is confirmed serial firmware:**

- Use exactly one Agent on the true device and the baud rate declared by the V2 firmware, not merely the Pi5 default.
- Reconfirm that serial configuration mode at 115200 is distinct from normal micro-ROS transport mode.

**In either case:** verify `ros2 node list`, `/cmd_vel` subscriber count and `/beep` type, then conduct a non-movement buzzer check.

### Phase D — flight controller and bridge

1. Confirm MAVROS `connected: true` and correct domain after restarting containers.
2. Investigate ArduPilot `system_status: 5`, GPS/compass/prearm/RC issues and logging.
3. Decide command architecture, implement a safety-checked MAVLink/MAVROS-to-Twist bridge **without** competing with joystick publishing. Introduce a command arbiter/mux so only one source controls motors.
4. Implement **independent hardware e-stop**, configurable velocity/acceleration limits, loss-of-command timeout, zero-command on communication loss, safe startup defaults and watchdog at the motor controller if possible.
5. Verify motor mapping and stop behavior **with wheels lifted**, cutting hardware disconnected, a human supervising at the machine.
6. Only then attempt a very short low-speed translation on level, clear ground, with bounded runtime and measured distance.

### Phase E — more robust field use

- Add DHCP reservation or static Agent-IP strategy.
- Test Huawei fallback and return behavior under controlled conditions.
- Stabilize mobile 12-V to Raspberry 5-V power delivery; check current headroom and brownout detection.
- Add boot health checks for ROS domain, agent transport, Cube Black MAVROS heartbeats, encoder feedback, battery level, and e-stop state.
- Later integrate LiDAR obstacle detection, camera person detection, RTK localization, autonomous olive-tree path following, and cutting controls **behind independent stop logic**.

---

## 11. Session restart cheat sheet

**Run on Raspberry host:**

```bash
# Network
nmcli device status
nmcli -f NAME,TYPE,AUTOCONNECT,AUTOCONNECT-PRIORITY connection show
ip -4 addr show wlan0
ip route

# USB and process ownership
ls -l /dev/ttyACM0 /dev/ttyUSB0
sudo fuser -v /dev/ttyACM0 /dev/ttyUSB0

# Docker instances (names may differ)
docker ps --format 'table {{.Names}}\t{{.Status}}\t{{.Image}}'

# UDP Agent process, if already started
docker logs --tail 40 arboreon-agent-udp
```

**For MAVROS, only when the Cube port is free:**

```bash
docker start arboreon-dev  # if not already up
docker exec -it arboreon-dev bash
source /opt/ros/humble/setup.bash
export ROS_DOMAIN_ID=20
# Only start MAVROS launch if no instance is already using /dev/ttyACM0:
ros2 launch mavros apm.launch fcu_url:=/dev/ttyACM0:115200
```

**In another MAVROS container terminal:**

```bash
source /opt/ros/humble/setup.bash
export ROS_DOMAIN_ID=20
ros2 topic echo /mavros/state --once
ros2 topic info /cmd_vel -v
```

**Do not** run `ros2` in the Debian host shell; `ros2: command not found` is expected there.

---

## 12. Source references and project artifacts

### Yahboom official documentation

1. **MicroROS-Pi5 main manual** — https://www.yahboom.net/study/MicroROS-Pi5/  
   Covers Pi5 robot setup, ROS 2/Docker, micro-ROS Agent, firmware, networking and control examples.
2. **Pi5: micro-ROS board parameter configuration** — https://www.yahboom.net/study/MicroROS-Pi5/10617/  
   `config_robot.py`, factory firmware, `/dev/ttyUSB*`, ~5-second configuration window, reset instructions, ROS domain guidance.
3. **Pi5: connect to micro-ROS Agent** — https://www.yahboom.net/study/MicroROS-Pi5/10618/  
   Agent connection tutorial; treat as Pi5-board-specific until V2 compatibility confirmed.
4. **Pi5: robot information release** — https://www.yahboom.net/study/MicroROS-Pi5/10624/  
   Expected `/YB_Car_Node`, `/cmd_vel`, `/beep`, `/imu`, `/odom` and LiDAR topics, matching ROS domain requirement.
5. **Pi5: quick keyboard control** — https://www.yahboom.net/study/MicroROS-Pi5/10622/  
   ROS control and connection procedure.
6. **MicroROS V2 main manual** — https://www.yahboom.net/study/MicroROS-V2/  
   The reference family for the actual two-motor ESP32-S3 board.
7. **V2: connect to micro-ROS Agent** — https://www.yahboom.net/study/MicroROS-V2/20040/  
   Describes UDP 8090, matching Agent IP/ROS domain/LAN and steady green LED connection indication; shows `ros2 launch microros_v2_bringup test_connect.launch.py` in the vendor's **V2 VM**, not as a demonstrated launch on our Pi5 image.
8. **V2: Wi-Fi network connection** — https://www.yahboom.net/study/MicroROS-V2/20242/  
   NetworkManager Wi-Fi commands.
9. **V2: serial Wi-Fi configuration** — https://www.yahboom.net/study/MicroROS-V2/20075/  
   Configuration topics including 2.4-GHz Wi-Fi, Agent address and default port; important for proper V2-specific tooling.
10. **Yahboom MicroROS-Pi5 hardware/product page** — https://www.yahboom.store/es/collections/r-4-wheels-drive/products/microros-pi5  
    Historical product link referenced by the project; **not proof** of exact V2 board compatibility.

### Software and background references

11. **MAVROS source / documentation** — https://github.com/mavlink/mavros  
    ROS 2 MAVLink bridge.
12. **ArduPilot Rover documentation** — https://ardupilot.org/rover/  
    Rover modes, prearm checks, missions and operation.
13. **ArduPilot Guided Mode** — https://ardupilot.org/rover/docs/guided-mode.html  
    Reference for controller-guided behavior; verify firmware/mode and external command semantics before use.
14. **micro-ROS documentation** — https://micro.ros.org/  
    XRCE-DDS Agent/client architecture.
15. **NetworkManager `nmcli` manual** — https://networkmanager.dev/docs/api/latest/nmcli.html  
    Profile configuration, autoconnect settings and status inspection.
16. **ROS 2 Humble documentation** — https://docs.ros.org/en/humble/  
    Domains, discovery, topics, launch and DDS behavior.

### Local evidence / files inspected directly during troubleshooting

- `/home/pi/.config/autostart/start.desktop`
- `/home/pi/.config/autostart/uros.desktop`
- `/home/pi/start_agent_rpi5.sh`
- `/home/pi/ros2_humble.sh`
- `/home/pi/config_robot.py` (source inspected; **do not execute its main block**)
- `/root/1.sh` and `/root/run_handle.sh` inside Yahboom ROS container
- `/etc/supervisor/conf.d/chassis.conf` inside Yahboom container
- `/root/yahboomcar_ws/src/yahboomcar_ctrl/launch/yahboomcar_joy_launch.py`
- `/root/yahboomcar_ws/src/yahboomcar_base_node/src/base_node_X3.cpp`
- `docker inspect`, `docker logs`, `ros2 node/topic`, `lsusb`, `udevadm`, `fuser`, `stty`, `tcpdump`, `ping`, `dmesg`, `nmcli`, `ip route` shell outputs copied from live tests
- User photographs of the ESP32-S3 board, motor connectors, OLED, LEDs, micro-USB, and Robot Manager GUI screenshots

### Evidence confidence and notation

- **Confirmed:** direct observation in the terminal/session or manufacturer documentation clearly referring to the same model.
- **Manufacturer example:** a procedure shown for Pi5's four-motor control board that may **not** work unchanged on V2.
- **Hypothesis:** an explanation consistent with logs but not proven (e.g., old SSID/IP stored in ESP32, firmware expects UDP, switch does not reset MCU while USB is connected).
- **Pending:** a test not yet performed or without recorded result (e.g., true ESP32 reset followed by a successful V2-specific config read).

---

## 13. Current handover state (end of 29 October 2026 session)

- Wi-Fi home autoconnect: **VERIFIED**, chosen first after reboot.
- Backup Wi-Fi ordering: **CONFIGURED/INTENDED**, not failover-tested.
- Raspberry last observed address: **192.168.1.58/23**, dynamic.
- Pixhawk USB + MAVROS: **VERIFIED CONNECTED**, disarmed HOLD, `system_status=5`.
- Yahboom CP2102 USB: **verified enumerating upon physical connection**; last provided kernel excerpt ended with a disconnect, so recheck live status.
- Yahboom micro-ROS serial: **NOT CONNECTED**.
- Experimental UDP Agent: **LISTENING**, no session observed.
- Board ROS domain, SSID, Agent IP: **UNKNOWN**; Robot Manager values `40`, `NOS-149D`, `192.168.1.52` were displayed but **not verified read from ESP32 hardware**.
- Motor `/cmd_vel` subscriber: **NONE OBSERVED**.
- Pixhawk-to-Yahboom command bridge: **NOT IMPLEMENTED OR VERIFIED**.
- Actual drive movement: **NOT ATTEMPTED**.

**Recommended immediate next action:** verify the board's real power/reset state and live `/dev/ttyUSB0` enumeration, then use the **MicroROS V2-specific configuration path** to read (not write) board firmware/transport/SSID/Agent IP/ROS domain. Once a client session is demonstrated, verify `/beep` and `/cmd_vel` subscriptions, then implement a safety-gated MAVROS bridge. Preserve the known-good Wi-Fi and Pixhawk/MAVROS setup.
