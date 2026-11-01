# Cable-Free Motor Integration: ArduPilot Cube Black + RFD868x + Yahboom MicroROS V2 over ROS 2

**From an adapted Ubuntu-on-UTM image on a Mac to keyboard-controlled differential-drive wheels — without a Raspberry Pi and without motor-control wiring between the Pixhawk and the Yahboom board**

> **Project status:** Bench-proven manual drive (forward, steering, stop); keyboard-driven motion also proven, but **noticeable latency remains unresolved**. Autonomous mission execution is the next milestone, **not yet demonstrated**. The onboard Yahboom loss-of-command watchdog and end-to-end emergency stop are **not verified**. Do not use this experimental setup for unattended or hazardous machinery.
>
> **Reproduction scope:** The documented system assumes an **already adapted and bootable** Ubuntu 22.04.5 ARM64 UTM VM with ROS 2 Humble and the Yahboom workspaces. The precise history of how the vendor's original image was adapted is not fully preserved in the test log; do not treat the image-conversion notes as a validated universal ARM64 conversion recipe. The instructions below begin with verification of that working image and provide conditional installation steps for missing packages.

## 1. Abstract

This report documents the hands-on integration of a **Cube Black running ArduRover 4.7.2** and a **two-drive-motor Yahboom MicroROS V2 robot** using a Mac-hosted Ubuntu UTM virtual machine. The Pixhawk remains responsible for vehicle state, navigation modes and calculation of the two skid-steering outputs. A pair of existing **RFD868x radios** carries bidirectional MAVLink traffic to **MAVProxy** on Ubuntu. A small Python bridge receives ArduRover's **`SERVO_OUTPUT_RAW`** telemetry, translates its left- and right-wheel PWM-equivalent commands into a ROS 2 **`geometry_msgs/msg/Twist`**, and publishes those commands to the ESP32-based Yahboom controller via an existing **micro-ROS UDP agent and Wi-Fi**.

This arrangement **does not require any wire from Pixhawk motor outputs to the Yahboom motor driver**. The Cube Black's servo outputs are interpreted as **telemetry values**, not used as physical PWM outputs. Both sides retain their pre-existing power and communication connections: the Cube Black already has a telemetry radio and the robot already has its motor-board wiring and Wi-Fi connection. The Raspberry Pi 5 was not used in this experiment.

The proof of concept was built progressively: verify the radio; confirm RC overrides; restore the micro-ROS agent; check ROS 2 subscriptions; receive PWM telemetry in Python; publish zero-velocity commands; enable a 10 Hz bounded motion bridge; diagnose unexpected RTL due to an existing geofence; and finally drive the suspended wheels from MAVProxy and a terminal WASD interface with adjustable speed levels.

## 2. Why this architecture?

### 2.1 Background

The small Yahboom MicroROS V2 chassis has two independent drive motors with encoders controlled by its own micro-ROS-enabled motor board. It exposes `/cmd_vel`, odometry, IMU, battery and LiDAR topics through an ESP32/micro-ROS implementation. Separately, a Cube Black autopilot, GPS and RFD868x link were available for ArduRover navigation and remote supervision. A Raspberry Pi 5 intended as an onboard companion was temporarily unavailable, so the experiments used the existing UTM VM at `192.168.1.52` as the ROS 2 host and micro-ROS agent.

A traditional ArduRover skid-steer installation wires the autopilot's left and right PWM outputs to motor ESCs. Here that would duplicate or bypass the Yahboom board's existing micro-ROS motor-control capability. Instead, the project uses a **software bridge**, preserving both controllers and leveraging ArduPilot's existing navigation stack. The goal is to make future missions uploaded from a ground control station drive the robot via ROS 2. That final mission-control step remains to be engineered and validated.

### 2.2 Research and engineering motivations

- Reuse a working ArduPilot navigation controller **without a custom PWM-to-motor wiring harness**.
- Keep access to ROS 2 sensors, motor commands and future autonomy/obstacle avoidance components.
- Reuse the long-range RFD868x telemetry link instead of buying another RC transmitter for the initial proof of concept.
- Decouple **control/planning** (ArduRover) from **motor actuation** (Yahboom micro-ROS firmware).
- Continue development while the Raspberry Pi 5 is disconnected.
- Establish a pathway to route upload, AUTO mode, GPS/RTK experiments and field navigation.

### 2.3 What “no extra wiring” does and does not mean

**No physical Pixhawk PWM/servo-output cables were connected to the Yahboom motor board.** The bridge reads the numeric outputs transmitted in MAVLink messages. This does **not** mean the complete hardware installation has no wires: motors, battery, radio-to-Pixhawk serial wiring, sensors and existing power circuits remain physically connected. USB serial on the **Ubuntu end** connects the local RFD868x radio to the VM; the communication from Ubuntu to Yahboom is over Wi-Fi. The Cube Black and Yahboom motor controller are **not directly connected by cable**.

## 3. Complete tested topology

```text
MacBook (host; observed 192.168.1.57)
  |
  +-- UTM Ubuntu 22.04.5 ARM64 VM (observed 192.168.1.52)
  |     ROS 2 Humble / ROS_DOMAIN_ID=40
  |     MAVProxy --master=/dev/ttyUSB0,57600
  |     |-- UDP 192.168.1.57:14550 -> ground-control UI (ArduDeck)
  |     |-- UDP 127.0.0.1:14551 -> Python MAVLink-to-ROS-2 bridge
  |     |-- UDP 127.0.0.1:14552 <-> terminal WASD controller
  |     |
  |     +-- micro_ros_agent udp4 --port 8090
  |              | Wi-Fi (ROS 2 XRCE-DDS bridge)
  |              v
  |         Yahboom MicroROS V2 ESP32 control board
  |              |  subscribes /cmd_vel (Twist)
  |              +-- Motor LEFT, motor RIGHT (existing wiring)
  |
  +-- USB/serial adapter: /dev/ttyUSB0 -> RFD868x #1
                ... 868 MHz RF link ...
                              RFD868x #2 -> Pixhawk Cube Black
                                  ArduRover 4.7.2
                                  SERVO1_FUNCTION=73 (ThrottleLeft)
                                  SERVO3_FUNCTION=74 (ThrottleRight)
```

**Control round trip:** WASD → MAVLink `RC_CHANNELS_OVERRIDE` → MAVProxy → RFD868x → Pixhawk → ArduRover mixed motor outputs → `SERVO_OUTPUT_RAW` → RFD868x → MAVProxy → Python bridge → ROS 2 `/cmd_vel` → micro-ROS agent → Yahboom ESP32 → motor driver. This round trip, filtering, smoothing and Wi-Fi account for multiple potential latency sources. It is **not** a zero-latency direct RC connection.

### 3.1 Observed IPs, ports and roles

| Resource | Tested value | Meaning |
|---|---|---|
| Mac host / ground-control destination | `192.168.1.57` | Receives MAVLink UI feed (application used: ArduDeck) |
| Ubuntu UTM VM | `192.168.1.52` | MAVProxy, micro-ROS agent, ROS 2 nodes |
| Raspberry Pi 5 | `192.168.1.58` | **Not connected / not used** |
| Micro-ROS UDP agent | `192.168.1.52:8090` | Yahboom connects over Wi-Fi |
| ROS domain | `40` | Working domain on UTM VM and ROS 2 processes |
| Radio serial on VM | `/dev/ttyUSB0` | Local RFD868x USB serial device |
| Radio serial bit rate | `57600` | Confirmed MAVProxy connection setting |
| Ground control telemetry | UDP `192.168.1.57:14550` | MAVProxy output 0 |
| Local MAVLink bridge input | UDP `127.0.0.1:14551` | MAVProxy output 1 |
| Local WASD MAVLink client | UDP `127.0.0.1:14552` | MAVProxy output 2, added after a failure |
| Pixhawk MAVLink IDs | system 1, component 1 | Observed from heartbeat |
| Accepted GCS system ID | `MAV_GCS_SYSID=254` | Was different from MAVProxy's initially displayed default 255 |

Use **your own** IP addresses and discovered serial device if reproducing elsewhere; these are observed lab values, not universal defaults.

## 4. Equipment and software

### Hardware

1. MacBook capable of running UTM; adapted Ubuntu VM with network access to the robot.
2. **Cube Black** flight controller already flashed with **ArduRover 4.7.2**, with its existing GPS and RFD868x connected.
3. Two paired compatible RFD868x radio modules: one associated with Cube Black, the other on the Ubuntu side via USB serial.
4. Yahboom **MicroROS V2, two powered drive wheels**; ESP32/micro-ROS-enabled controller and existing motor wiring.
5. Appropriate independent power for the robot and Pixhawk, safely arranged for bench testing.
6. Secure support that keeps **both wheels off the ground**; physical means to disconnect motor power.
7. A Wi-Fi network connecting the robot and Ubuntu VM. No Raspberry Pi is required.

### Software verified or used

- Ubuntu **22.04.5 ARM64/aarch64**, adapted and running inside UTM.
- ROS **2 Humble** (`/opt/ros/humble`).
- User workspace `~/microros_ws` containing `microros_v2_bringup` and related Yahboom packages.
- micro-ROS Agent built in `~/uros_ws`, observed install directory `/home/yahboom/uros_ws/install/micro_ros_agent`.
- Python 3.10, `rclpy`, `geometry_msgs`, `pymavlink`.
- MAVProxy running on `/dev/ttyUSB0` at `57600` baud.
- ArduDeck on the Mac as an optional GCS; it is **not** needed for terminal teleoperation.

### 4.1 Notes on the adapted UTM image

A previous preparation investigated a vendor `Rosmaster-Ubuntu22.04.vmdk` and conversion to `Rosmaster-Ubuntu22.04.qcow2`. That image originally described an **x86-64** VMware guest. A working **ARM64** Ubuntu 22.04.5 UTM installation was later confirmed. Converting an x86-64 disk container from VMDK to QCOW2 **does not convert its guest architecture to ARM64**. These two historical observations must not be conflated into a proven conversion procedure. To reproduce the present experiment, start from a **bootable, tested Ubuntu ARM64 VM** with ROS 2 Humble/Yahboom files installed, or emulate x86-64 explicitly if using the unmodified x86-64 vendor guest. The exact adapted-image build method is an open documentation gap.

Check the working VM:

```bash
uname -m                    # expected: aarch64 for tested VM
lsb_release -a
ip -4 addr
ip route
ros2 --help
ls /opt/ros/humble/setup.bash
ls ~/microros_ws/src
ls ~/uros_ws/install
```

For UTM, use a network configuration that permits the VM to be reached by the robot on the LAN (the observed VM IP was `192.168.1.52`). **Merely running NAT with an isolated guest IP may prevent the ESP32 from reaching the agent.** Verify reachability, not just internet access. The initial environment also used UTM USB passthrough for a CP2102 USB-to-UART device on `/dev/ttyUSB0`.

## 5. Prepare Ubuntu and Python

This procedure **does not install ArduPilot firmware on Ubuntu**. ArduRover already runs on the Cube Black. Ubuntu only needs MAVProxy, Python/pymavlink, ROS 2, the micro-ROS agent, and our bridge. SITL is optional and was **not** used in the successful physical-wheel demonstration.

```bash
sudo apt update
sudo apt install -y python3-pip python3-venv git python3-serial
source /opt/ros/humble/setup.bash
python3 -c 'import rclpy; from geometry_msgs.msg import Twist; print("ROS 2 Python OK")'
python3 -c 'from pymavlink import mavutil; print("pymavlink OK")'
command -v mavproxy.py
```

If `pymavlink` or MAVProxy is absent, install into an environment that can see the **same ROS 2 Python packages** as the system's ROS installation. On this working image, the user used the system Python and `pymavlink` from `~/.local/lib/python3.10/site-packages`. One possible installation for the tested Ubuntu 22.04 environment is:

```bash
python3 -m pip install --user pymavlink MAVProxy
```

If pip refuses, follow Ubuntu/ROS environment compatibility guidance; do **not** blindly replace `/usr/bin/python3` or mix incompatible ROS 2 Python versions. A separate virtual environment may require system-site-packages to import apt-installed `rclpy`.

Serial device discovery:

```bash
lsusb
ls -l /dev/ttyUSB*
id -nG
sudo usermod -aG dialout "$USER"   # only if serial permission is denied
# Log out / back in after changing groups.
```

An earlier `module load map` issue caused an `Illegal instruction` related to the Python OpenCV installation in ARM64. It did **not** prevent the serial-only MAVProxy workflow. The mapped GUI is optional. If reproducing the map issue, inspect conflicting `opencv-python` wheels and the distribution's `python3-opencv` package rather than changing a working serial stack unnecessarily.

## 6. Restore micro-ROS connectivity without Raspberry Pi

### 6.1 Set the agent endpoint on the robot

The Yahboom firmware must already be configured for the working Wi-Fi network and to reach the agent at **`192.168.1.52` UDP port `8090`**. The precise firmware Wi-Fi provisioning method and credential values are **not available in this test transcript**; use the vendor-specific configuration flow for your particular board/firmware. These credentials should **not** be committed to GitHub. The micro-ROS agent does **not** publish motor commands itself; it bridges the ROS 2 domain with the ESP32.

### 6.2 Start the agent

On the Ubuntu VM, in terminal **A**:

```bash
export ROS_DOMAIN_ID=40
source /opt/ros/humble/setup.bash
source ~/uros_ws/install/local_setup.bash
ros2 run micro_ros_agent micro_ros_agent udp4 --port 8090 -v6
```

Alternatively, the project workspace had a previously used Yahboom launch command:

```bash
export ROS_DOMAIN_ID=40
source /opt/ros/humble/setup.bash
source ~/uros_ws/install/local_setup.bash
source ~/microros_ws/install/local_setup.bash
ros2 launch microros_v2_bringup test_connect.launch.py
```

**Use one agent startup method at a time**; inspect the launch file before combining these. The `joy_control` demo can run from a separate launch process but should be stopped before another `/cmd_vel` publisher is activated.

Agent diagnostics:

```bash
ps aux | grep '[m]icro_ros_agent'
sudo ss -lunp | grep 8090
```

### 6.3 Verify ROS graph

In terminal **B**:

```bash
export ROS_DOMAIN_ID=40
source /opt/ros/humble/setup.bash
ros2 node list
ros2 topic list
ros2 topic info /cmd_vel -v
ros2 topic echo /battery --once
```

The first attempt found only `/parameter_events` and `/rosout`; `/cmd_vel` was unknown because the robot session was absent. After launching Yahboom's joystick-control program and restoring communication, the following were observed:

```text
/micro_ros_task_node
/joy_control                 # when the Yahboom demo is still running

/battery
/beep
/cmd_ptz_angle
/cmd_vel
/imu
/joy
/joy/set_feedback
/odom_raw
/parameter_events
/ptz_angle
/rosout
/scan
```

Important `topic info` values observed:

```text
Type: geometry_msgs/msg/Twist
Publisher count: 1       # joy_control until stopped
Node name: joy_control
Endpoint type: PUBLISHER
Reliability: RELIABLE
Subscription count: 1
Node name: micro_ros_task_node
Endpoint type: SUBSCRIPTION
Reliability: BEST_EFFORT
```

A reliable publisher can communicate with a best-effort subscriber under DDS request/offered compatibility. Later our motion bridge used **BEST_EFFORT** explicitly. The actual `/battery` sample returned:

```yaml
data: 10.89309024810791
```

This confirmed a running micro-ROS telemetry path. This sample should not be used to estimate battery capacity without a verified chemistry/voltage mapping.

### 6.4 Stop only the original joystick demo

The observed process list was:

```text
PID 132221: /opt/ros/humble/lib/joy/joy_node
PID 132223: .../common_demo/joy_control_node --ros-args ...
```

Use `ps` first, because PIDs are temporary:

```bash
ps aux | grep -E 'joy_control|joy_node|teleop_twist_joy'
# For the historical run only:
kill -TERM 132221 132223
```

**Do not paste the old numeric PIDs on a different run.** When both are launched under a common parent, stopping the parent may also stop the agent; always verify the ROS graph afterward:

```bash
ros2 topic info /cmd_vel -v
```

Observed result: `Publisher count: 0`, `Subscription count: 1`, with `micro_ros_task_node` present. That was the desired state before launching our own controller.

## 7. Bring up ArduPilot telemetry via RFD868x

### 7.1 Hardware path

The local RFD868x USB serial adapter appears in Ubuntu as `/dev/ttyUSB0`. The other paired radio is already attached to a Pixhawk telemetry port. **No Pixhawk PWM outputs were wired to the robot motors.** The RFD radios are the Pixhawk's existing communications hardware, not a newly invented wireless interface.

### 7.2 Start MAVProxy

In terminal **C**:

```bash
mavproxy.py \
  --master=/dev/ttyUSB0,57600 \
  --source-system=254 \
  --out=udp:192.168.1.57:14550
```

The original successful launch omitted `--source-system=254` and displayed `source_system=255`; later the Pixhawk's `MAV_GCS_SYSID=254` was discovered, so explicitly using `254` is the more consistent reproduction. The receive-only and MAVProxy-console tests worked before the correction. It matters when evaluating acceptance of **external** control and failsafe origin IDs.

Representative console:

```text
Connect /dev/ttyUSB0,57600 source_system=255   # initial historical run
Waiting for heartbeat from /dev/ttyUSB0
Detected vehicle 1:1 on link 0
AP: ArduRover V4.7.2
AP: CubeBlack ...
Received 885 parameters (ftp)
```

Keep MAVProxy open while the rest of the stack runs. `status` prints RC inputs, heartbeat, `SERVO_OUTPUT_RAW`, GPS, power, fence and radio state. **MAV errors** were non-zero but did not prevent the demonstrator from working; evaluate their rate and meaning before field use.

### 7.3 Add both loopback endpoints

At the `MAV>`/`HOLD>`/`MANUAL>` MAVProxy prompt (not in the Linux shell):

```text
output add 127.0.0.1:14551
output add 127.0.0.1:14552
output
```

The *final* desired output table is:

```text
3 outputs
0: 192.168.1.57:14550
1: 127.0.0.1:14551
2: 127.0.0.1:14552
```

Avoid duplicate outputs. When MAVProxy was restarted, the third endpoint was accidentally missing. The WASD program then showed `ARM=False`, `MODE=None`, `HB_OK=False` despite the motor bridge showing `ARM=True`, `MODE=0`: **the missing 14552 output caused that specific failure**. Re-adding the port restored keyboard motion.

The UDP endpoints are **bidirectional when forwarded by MAVProxy**, provided client forwarding (`mavfwd`) and the receiving client's MAVLink endpoint behavior are correct. Check `set mavfwd` in MAVProxy if outgoing RC overrides fail to reach the vehicle. A successfully received heartbeat alone does not prove uplink command forwarding.

### 7.4 Initial safe commands

At the MAVProxy prompt, **submit commands individually**. In the session, rapid pasted commands occasionally concatenated, yielding errors such as `Unknown command 'disarmrc 1 1500'`.

```text
status
mode HOLD
disarm
rc 1 1500
rc 3 1500
```

The observed `HEARTBEAT` fields were consistent with system 1, component 1 and `custom_mode=4` (HOLD). `base_mode & 128` determines armed status, rather than assuming the prompt alone is sufficient. The initial session **was armed unexpectedly**, so disarm and verify explicitly before bench work.

## 8. Confirmed Cube Black / ArduRover parameters

Recorded from the *working* aircraft/rover configuration:

| Parameter | Recorded value | Meaning / caveat |
|---|---:|---|
| Firmware | ArduRover **4.7.2** | Physical Cube Black, not SITL |
| `RCMAP_ROLL` | `1` | Steering from RC channel 1 |
| `RCMAP_THROTTLE` | `3` | Throttle from RC channel 3 |
| `RC3_TRIM` | `1500` | Channel trim; does not alone prove motor neutral |
| `PILOT_STEER_TYPE` | `0` | Tested pilot steering behavior |
| `SERVO1_FUNCTION` | `73` | ThrottleLeft in skid steer |
| `SERVO3_FUNCTION` | `74` | ThrottleRight in skid steer |
| `MAV_GCS_SYSID` | `254` | Authorized GCS source system ID |
| `RC_OVERRIDE_TIME` | `3.0` | MAVLink RC override expiry, seconds |
| `RC_OPTIONS` | `32` | Bit 5 set: throttle-at-zero arming check |
| `FS_GCS_ENABLE` | changed `0` → `1` | GCS failsafe enabled during session |
| `FS_ACTION` | `2` | HOLD on the relevant rover failsafe |
| `FS_TIMEOUT` | `1.5` | Recorded rover failsafe timeout; not an end-to-end actuator stop guarantee |
| `FENCE_ENABLE` | changed `1` → `0` | **Temporarily disabled for suspended-wheel bench tests only** |
| `FENCE_ACTION` | `1` | RTL/HOLD behavior on fence breach |
| `FENCE_TYPE` | `6` | Cylindrical/circular + polygon fence bitmask |
| `OA_TYPE` | `2` | BendyRuler obstacle avoidance setting |

Additional parameters queried but **not confirmed in the shared output** include `ARMING_CHECK`, `MAV_OPTIONS`, `MOT_SLEWRATE`, `FS_THR_ENABLE` and `MODE_CH`. Do not fill those from guesses. Arming checks had previously been reported as disabled, but a numeric `ARMING_CHECK` value was not captured.

Read key values with MAVProxy:

```text
param show SERVO1_FUNCTION
param show SERVO3_FUNCTION
param show RCMAP_ROLL
param show RCMAP_THROTTLE
param show MAV_GCS_SYSID
param show RC_OVERRIDE_TIME
param show FS_GCS_ENABLE
param show FS_ACTION
param show FENCE_ENABLE
param show FENCE_ACTION
param show MOT_SLEWRATE
```

**Do not blindly write the recorded values to a different rover.** They are a reference configuration, not a universally safe parameter file. Record current values and back up parameters before changing anything.

### 8.1 Failsafe steps used

At the time, the GCS failsafe was disabled, so the following settings were applied after ensuring the vehicle was disarmed:

```text
param set FS_ACTION 2
param set FS_GCS_ENABLE 1
param show FS_ACTION
param show FS_GCS_ENABLE
```

They returned `FS_ACTION 2` and `FS_GCS_ENABLE 1.0`. **These settings do not guarantee motor stop on loss of Wi-Fi between Ubuntu and the Yahboom ESP32**. The Pixhawk cannot enforce a motor-board watchdog across a disconnected radio/ROS link.

### 8.2 Why the rover unexpectedly entered RTL

During tests, the motor bridge reported `ARM=True MODE=11` and changing PWM outputs (e.g. 1366, then 1290), but `ENABLED=False`. ArduRover mode `11` is **RTL**, while the bridge deliberately only permits manual motion in mode `0`. Ground-control screenshots showed `PreArm: Vehicle breaching Polygon fence` and `Dijkstra: could not find path`. MAVProxy later reported `fence breach` and `fence OK`.

The recorded fence parameters were `FENCE_ENABLE=1`, `FENCE_ACTION=1`, `FENCE_TYPE=6`. A fence breach was a **strong explanation** for the unexpected mode transition; the exact full event timeline was not independently reconstructed from onboard logs. Since this was a suspended-wheel test, the fence was **temporarily disabled**:

```text
mode HOLD
disarm
param set FENCE_ENABLE 0
param show FENCE_ENABLE
```

This allowed a later `ARM=True MODE=0 ENABLED=True` bench test. **Restore and validate a suitable fence (`FENCE_ENABLE=1`) before any outdoor autonomous mission.** Do not leave the experimental bench override in a production configuration. GPS jitter with a stationary suspended rover can make the map appear to move and can trigger near-boundary events; do not interpret a ground-control map movement as physical wheel motion.

## 9. Test MAVLink steering/throttle from MAVProxy before using ROS 2

These were the essential channel tests, **not** yet requiring joystick hardware:

```text
mode HOLD
disarm
rc 1 1500
rc 3 1500
rc 1 1600
status
```

The `RC_CHANNELS` report showed `chan1_raw: 1600`, proving the radio uplink accepted a steering command. It also showed `chancount: 0` (no conventional receiver channels detected); this should not be interpreted as a populated physical RC receiver. `SERVO_OUTPUT_RAW` was initially neutral at 1500/1500 while the rover was in HOLD.

Release old overrides as needed:

```text
rc 1 0
rc 3 0
```

A zero in these MAVProxy `rc` commands requests release of the override; it is **not** a desired motor PWM of 0 µs. In the keyboard script, 65535 is used for *unchanged* fields on MAVLink channels 1-18. Other RC input fields may have special MAVLink semantics; do not freely interchange 0, 65535 and 65534 without checking the protocol.

## 10. Verify Yahboom `/cmd_vel` independently

Before bridging ArduRover, a **zero-velocity** message was published directly:

```bash
export ROS_DOMAIN_ID=40
source /opt/ros/humble/setup.bash
ros2 topic pub --once /cmd_vel geometry_msgs/msg/Twist \
  '{linear: {x: 0.0}, angular: {z: 0.0}}'
```

At first it printed `Waiting for at least 1 matching subscription(s)...`; then:

```text
publisher: beginning loop
publishing #1: geometry_msgs.msg.Twist(...linear.x=0.0...angular.z=0.0...)
```

A 10 Hz zero-command test followed:

```bash
ros2 topic pub -r 10 /cmd_vel geometry_msgs/msg/Twist \
  '{linear: {x: 0.0}, angular: {z: 0.0}}'
```

`ros2 topic info /cmd_vel -v` reported one publisher (`_ros2cli_...`) and one subscriber (`micro_ros_task_node`). This proves graph discovery and message publication, **not yet physical motor execution**. Terminate the test publisher with `Ctrl+C` and confirm `Publisher count: 0` before running the bridge.

## 11. Build the bridge in stages

The experiment used a deliberate sequence of increasingly capable Python programs. **Complete, syntax-checked source of every named script is reproduced in Appendix A**, and standalone `.py` copies are included in the accompanying project archive. Do not launch multiple scripts that bind the same UDP port or publish conflicting commands on `/cmd_vel` simultaneously.

### Stage 1 — Raw MAVLink receive test

With MAVProxy output `127.0.0.1:14551` configured, run:

```bash
python3 scripts/mavlink_receive_test.py
```

Observed repeated lines equivalent to:

```text
Mode: 4, Armed: False
Left: 1500, Right: 1500
```

The actual one-off here-document received the same information. On `Ctrl+C`, a `KeyboardInterrupt` traceback appeared in that ad hoc version; the standalone appendix script handles it cleanly. Receiving `SERVO_OUTPUT_RAW` with both channels neutral confirmed a valid downlink from Pixhawk via RFD868x, MAVProxy and local UDP.

### Stage 2 — Normalized PWM diagnostic

Run `scripts/mavlink_ros2_bridge.py`. The historical name includes `ros2` but this first prototype uses **pymavlink only**; it does not create a ROS node and never publishes to motors. Its simple arithmetic is:

```text
normalized_left  = clamp((servo1_raw - 1500) / 500, -1, 1)
normalized_right = clamp((servo3_raw - 1500) / 500, -1, 1)
normalized_linear  = (normalized_left + normalized_right) / 2
normalized_angular = (normalized_right - normalized_left) / 2
```

This produces **unitless diagnostics**, not metres/second or radians/second. It printed repeated `ARM=False MODE=4 L=+0.00 R=+0.00 V=+0.00 W=+0.00` and terminated correctly on `Ctrl+C`.

### Stage 3 — ROS 2 monitor, no motor publisher

Run in terminal D (with port 14551 free):

```bash
export ROS_DOMAIN_ID=40
source /opt/ros/humble/setup.bash
python3 scripts/mavlink_ros2_monitor.py
```

In terminal B:

```bash
ros2 node list
```

Observed:

```text
/mavlink_ros2_monitor
/micro_ros_task_node
```

This proves a ROS 2 Python node and an ESP32 micro-ROS node can coexist in the same domain while MAVLink messages are being consumed. It does **not** itself publish motion.

### Stage 4 — Safe zero-velocity bridge

After stopping the monitor, run:

```bash
python3 scripts/mavlink_ros2_bridge_safe.py
```

The safe bridge reads heartbeat and servo telemetry and publishes **only zero** to `/cmd_vel`, at nominal 10 Hz. Logs showed:

```text
ARM=False MODE=4 HEARTBEAT_OK=True SERVO_OK=True CMD_VEL=0
```

The first log briefly reported false heartbeat/servo flags before packets arrived; this is a normal startup transient. A frequency check:

```bash
ros2 topic hz /cmd_vel
ros2 topic echo /cmd_vel --once
```

Produced approximately **10.003 Hz** over 149 samples, intervals **0.083–0.119 s** and standard deviation around **0.00244 s**. This is **publisher-message timing**, not a measured actuation or round-trip delay.

### Stage 5 — Limited-motion bridge

Stop the zero-velocity bridge (to prevent conflicting publishers), then run:

```bash
export ROS_DOMAIN_ID=40
source /opt/ros/humble/setup.bash
python3 scripts/mavlink_ros2_bridge_motion.py
```

This was the bench-only bridge that successfully drove the wheels. It reads physical Pixhawk system 1, component 1 heartbeat (`armed`, `custom_mode`) and the two servo telemetry values. The code uses the following **provisional** calibration and limits:

| Setting | Historical value | Note |
|---|---:|---|
| PWM centre | 1500 µs | Observed neutral in tests |
| PWM span | 500 µs | ±500 normalization assumption |
| Wheel speed scale | 0.40 m/s | **Not measured/calibrated** |
| Wheel separation | 0.22 m | **Placeholder, not measured** |
| Maximum linear command | ±0.08 m/s | Software output clamp |
| Maximum angular command | ±0.30 rad/s | Software output clamp |
| Heartbeat freshness | 2 s | Local receive freshness check |
| Servo freshness | 0.6 s | Local receive freshness check |
| Publish interval | 0.1 s | Nominal 10 Hz |
| Test duration | First 30 s, then 180 s | Session-start timeout |
| Allowed mode | `MANUAL=0` | Blocks RTL (`11`) and HOLD (`4`) |

Wheel-level conversion:

```text
uL = clamp((PWM1 - 1500)/500, -1, 1)
uR = clamp((PWM3 - 1500)/500, -1, 1)
vL = uL * 0.40
vR = uR * 0.40
linear.x  = clamp((vL + vR)/2, -0.08, +0.08)
angular.z = clamp((vR - vL)/0.22, -0.30, +0.30)
```

Motion is enabled only when:

```text
armed AND mode == MANUAL AND heartbeat_fresh
      AND servo_output_fresh AND within_test_duration
```

On failure of any condition it **publishes a zero Twist**. The code also publishes repeated zero on normal shutdown. **This is not an independent hardware fail-safe**; a disconnected Wi-Fi link can prevent stop messages from reaching the motor board. Furthermore, the bridge's 180-second timeout **does not stop the Python process**; it continues publishing zero while reporting `TIME_OK=False` until restarted.

### Stage 6 — Investigate `ENABLED=False`

Several real problems were found:

1. **Time window expired.** At `ELAPSED=508.3s`, logs showed `TIME_OK=False` and `ENABLED=False`; reset by disarming and restarting the bridge. We initially had a 30 s window, too short to complete setup, then changed it to **180 s**.
2. **Pixhawk intentionally disarmed/HOLD.** At `ARM=False MODE=4` or `ARM=False MODE=0`, `ENABLED=False` is correct.
3. **Unwanted RTL.** At `ARM=True MODE=11`, `ENABLED=False` is a deliberate block, even though PWM may change.
4. **Valid enabled state.** Eventually logs showed:

   ```text
   ARM=True MODE=0 PWM=(1500,1500) V=+0.000 W=+0.000
   ENABLED=True HB_OK=True SERVO_OK=True TIME_OK=True
   ```

This troubleshooting was made explicit by adding `HB_OK`, `SERVO_OK`, `TIME_OK`, and `ELAPSED` fields to the motion-bridge log. The appendix contains the **final diagnostic version**.

## 12. First proven physical wheel movement

**Bench-only!** Both wheels were suspended, with no cutting tools fitted or energized. The tested MAVProxy sequence, after confirming a suitable bench geofence configuration and with a running, time-valid motion bridge, was:

```text
rc 1 1500
rc 3 1500
mode MANUAL
arm throttle
```

**`arm` alone is not the command** in this MAVProxy configuration: it returns `usage: arm <check|uncheck|...|throttle|...>`. The successful command was `arm throttle`.

After checking `ARM=True MODE=0 ENABLED=True`, a very small forward command was given:

```text
rc 3 1550
```

**Observed result:** **both wheels moved forward in the same direction.** The user then confirmed that steering commands also worked:

```text
rc 3 1500
rc 1 1450
rc 1 1500
rc 1 1550
```

**Observed result:** the wheels steered as expected, and the robot stopped afterward. The physical motion is the core evidence that all interfaces were successfully chained without Pixhawk-to-motor wiring.

Always finish with separate commands:

```text
rc 1 1500
rc 3 1500
mode HOLD
disarm
```

If the wheels do not stop, **disconnect motor power**. A command over wireless transport cannot be assumed to arrive under fault conditions. Do not force arm if pre-arm checks fail; investigate the cause.

## 13. Keyboard teleoperation through MAVLink

### 13.1 Why a third MAVProxy endpoint is needed

The keyboard script reads vehicle heartbeat on UDP `14552`, then sends `RC_CHANNELS_OVERRIDE` back through that MAVProxy output connection. When `output` listed only `192.168.1.57:14550` and `127.0.0.1:14551`, the keyboard UI reported:

```text
ARM=False MODE=None HB_OK=False
RC1=1500 RC3=1500
Movement enabled: False
```

Adding `output add 127.0.0.1:14552` and restarting the keyboard program restored the necessary telemetry and allowed keyboard-driven wheel movement.

### 13.2 Controls in final tested script

| Key | Action |
|---|---|
| `W` | Request forward throttle while key repeat is detected |
| `S` | Request reverse throttle |
| `A` | Request left steering |
| `D` | Request right steering |
| `+` or `=` | Increase commanded throttle level |
| `-` | Decrease commanded throttle level |
| `Space` | Request neutral values |
| `Q` | Exit and send repeated neutral RC values |

The five throttle levels were **±30, ±60, ±90, ±120, ±150 µs** relative to 1500 µs. Steering uses a fixed ±60 µs. The keyboard script sends **10 updates/s**, returns to neutral after about **350 ms** without another key event, and exits after **120 seconds**. It requires a **recent Pixhawk heartbeat**, `ARM=True` and `MODE=0` before sending non-neutral RC values. MAVLink sender system ID is `254`, component `190`.

**Important limitation:** this terminal version uses `curses.getch()` and the operating system's *key-repeat* behavior. It does **not** know a key's actual held/released state, does **not** implement true simultaneous `W+A` or `W+D`, and can stutter, delay or temporarily return to neutral as key repeats pause. Do not present it as a low-latency RC replacement. The user verified keyboard wheel movement, but then reported **very large delay between pressing `W` and motor movement**. That delay had **not been measured or resolved** at the end of the session.

### 13.3 Running the keyboard UI

Start these components in separate terminals, in this order:

1. Terminal A: micro-ROS agent, robot connected.
2. Terminal C: MAVProxy and all three outputs.
3. Terminal D: **one** `mavlink_ros2_bridge_motion.py` process.
4. Terminal E: `rover_keyboard.py`.

```bash
python3 scripts/rover_keyboard.py
```

At first the UI should show `ARM=False`, `MODE=4` (HOLD), `HB_OK=True`, movement disabled. From MAVProxy, with channels centred, in the suspended-wheel environment:

```text
mode MANUAL
arm throttle
```

The keyboard UI should update to `ARM=True MODE=0 HB_OK=True` and display movement enabled. A short `W` press requests forward. Return to neutral with Space, exit with `Q`, then `mode HOLD` and `disarm` in MAVProxy. **The keyboard program does not itself arm or disarm the vehicle.**

### 13.4 Finding the source of latency — pending investigation

Compare two paths while monitoring the motion bridge's `PWM=(...)` and `V/W` logs:

- **Direct MAVProxy:** brief `rc 3 1560` followed by `rc 3 1500`.
- **Terminal WASD:** `W` at level 2 (±60 µs) followed by Space/Q.

If direct MAVProxy is fast and keyboard is slow, focus on `curses`/key repeat, MAVProxy port 14552, UDP forwarding and key timeout. If both are slow, inspect RFD radio round trip, ArduRover smoothing (`param show MOT_SLEWRATE`), PWM-update frequency, ROS 2 scheduling, micro-ROS transport and Yahboom firmware ramp/deadband. ArduPilot documents that MAVLink RC input can be **laggy due to telemetry bandwidth and shared traffic**; the manual mode also retains throttle slew limits. No latency benchmark was completed in this run.

For meaningful measurement, add monotonic timestamps at keyboard key acquisition, RC transmit, RC_CHANNELS receive, SERVO_OUTPUT_RAW receive, `/cmd_vel` publication and encoder/odometry response. Do not infer actuation latency from `ros2 topic hz` alone.

## 14. Watchdog and safety status

**Critical open item:** A local watchdog **on the Yahboom motor controller itself** has not been verified. The ROS 2 Python bridge's heartbeat/servo timeouts and its repeated zero messages do not stop motors when the micro-ROS/Wi-Fi path fails and the ESP32 cannot receive them. Test only with wheels securely suspended until the motor-board firmware is inspected or independently verified to stop after input expiry. Before a larger outdoor rover or cutting machinery is operated, provide an independent physical emergency stop that can cut actuator power.

A search in `~/microros_ws/src` found software-side features such as:

```text
poseFollow.py: publishes /cmd_vel, has zero-Twist stop behavior
RobotCtrl.py: hand_lost_timeout_sec (default 0.5 s)
gestureFollow.py: hand/gesture tracking timeout
media_common.py: task_control_timeout()
```

These are **application-level or sensor-tracking timeouts**, **not proof of an ESP32 motor safety watchdog**. Vendor documentation for a specific micro-ROS speed-control subscriber *example* mentions a **1500 ms timeout**, but that is **not proof that the exact shipped Yahboom firmware currently running on this robot implements it**. This must be established from that firmware or a controlled motor-power-safe test. Likewise, `FS_GCS_ENABLE=1`, `FS_ACTION=2` only protect cases the Pixhawk is able to detect; neither is a substitute for a motor-board watchdog.

Search the firmware/workspace, without reflashing during this test:

```bash
find ~/microros_ws ~/uros_ws -type f \
  \( -name '*.ino' -o -name 'platformio.ini' -o -name 'sdkconfig' \
     -o -name '*motor*.cpp' -o -name '*micro_ros*.cpp' \) \
  2>/dev/null | head -80

grep -RniE 'cmd_vel_callback|twist_callback|motor_stop|stop_motor|last_cmd_vel|millis\(\)' \
  ~/microros_ws/src --include='*.cpp' --include='*.c' \
  --include='*.h' --include='*.ino' 2>/dev/null | head -60
```

### Safety limitations of the exact historical scripts

- The motion bridge gates on **arm state, MANUAL mode, fresh heartbeat, fresh servo telemetry and elapsed time**; it does **not** independently validate link quality, wheel feedback, loss of DDS subscription, physical motor enable or geofence restored state.
- The script has **provisional kinematic dimensions** and does **not** calibrate actual motor speed from encoders.
- A stationary wheel's PWM may drift slightly (e.g. `1519`), which can cause an unrequested small speed command. A **neutral deadband** should be added before ground use.
- `rc_channels_override_send` from a separate MAVLink client shares a GCS system ID (`254`) with MAVProxy; source-ID policy and forwarding behavior should be validated in the intended deployment.
- `MOT_SLEWRATE` had **not yet been read** despite reported lag.
- A monitoring UI or second ground station (e.g. ArduDeck) can change modes or issue commands; keep a single control authority during critical tests.
- The movement bridge is configured **MANUAL-only**. It will intentionally publish zeros in **AUTO**, **GUIDED**, **RTL**, and HOLD. This must be revisited intentionally to support route execution and is **not** a code bug.
- The controller has no independent hardware kill and the absence of the Raspberry Pi means computation is off-board, relying on Wi-Fi as well as the RFD radios.

## 15. Troubleshooting reference

| Symptom | Observed cause / diagnosis | Remedy |
|---|---|---|
| ROS graph shows only `/rosout`, `/parameter_events` | micro-ROS agent/robot session absent | Start/verify agent at UDP 8090; confirm ESP32 configured to `192.168.1.52`; use domain 40 |
| `/cmd_vel` has publisher `joy_control` | Original Yahboom joystick demo still running | Stop its `joy_node` and `joy_control_node` processes; retain the agent |
| `/cmd_vel` has no subscriber | Robot disconnected / wrong ROS domain | Check micro-ROS session and endpoint |
| `MAVProxy Waiting for heartbeat` | Radio/serial link not ready | Verify RFD pairing, `/dev/ttyUSB0`, USB passthrough and 57600 baud |
| `Unknown command 'disarmrc 1 1500'` | Console pasted adjacent commands without newline handling | Enter one command at a time |
| `arm` prints usage text | `arm` requires subcommand | In safe bench conditions use `arm throttle`, not force arm |
| `ARM=True MODE=11 ENABLED=False` | Rover in RTL, bridge MANUAL-only | Investigate fence and other causes; do not defeat bridge mode gate |
| `PreArm: Vehicle breaching Polygon fence` | Fence position violated | Inspect/reconfigure fence; bench-only temporary disable with restoration |
| `TIME_OK=False` at 508 s | 180 s test time elapsed | Disarm and restart bridge; don't extend indefinitely for unattended motion |
| `HB_OK=False` on first log only | Startup before first heartbeat | Allow initialization; investigate if persistent |
| WASD `ARM=False MODE=None HB_OK=False` while bridge works | Missing MAVProxy UDP output 14552 | `output`; add 127.0.0.1:14552 and restart WASD |
| WASD keys do nothing while `HB_OK=True` | Not armed, not MANUAL, or keyboard port forwarding issue | Check status; compare direct MAVProxy `rc` path |
| WASD motion delayed | Key-repeat / radio MAVLink path / motor slew (unresolved) | Measure pipeline timing; query `MOT_SLEWRATE`, review radio traffic |
| `ros2 topic hz /cmd_vel` ~10 Hz but no wheel motion | Only publication proved | Inspect armed/mode gate, PWM changes, motor power and actual firmware execution |
| MAVProxy GUI `Illegal instruction` with map | Previous ARM64 OpenCV conflict | Use terminal MAVProxy, or repair OpenCV if GUI needed |

## 16. Repeatable bench runbook (short form)

**Only use this with both wheels securely suspended, no cutting tooling, accessible physical power cutoff, and no person near rotating parts.** Confirm the firmware-specific watchdog before any ground driving.

```bash
# A. Ubuntu environment (each ROS 2 terminal)
export ROS_DOMAIN_ID=40
source /opt/ros/humble/setup.bash

# B. Agent (terminal A)
source ~/uros_ws/install/local_setup.bash
ros2 run micro_ros_agent micro_ros_agent udp4 --port 8090 -v6

# C. Confirm robot ROS 2 endpoint (terminal B)
ros2 topic info /cmd_vel -v
ros2 topic echo /battery --once

# D. MAVProxy (terminal C; source ID consistent with MAV_GCS_SYSID)
mavproxy.py --master=/dev/ttyUSB0,57600 --source-system=254 \
  --out=udp:192.168.1.57:14550
# At MAVProxy prompt:
# output add 127.0.0.1:14551
# output add 127.0.0.1:14552
# output

# E. Movement bridge (terminal D, after stopping other /cmd_vel publishers)
export ROS_DOMAIN_ID=40
source /opt/ros/humble/setup.bash
python3 scripts/mavlink_ros2_bridge_motion.py

# F. WASD UI (terminal E)
python3 scripts/rover_keyboard.py
```

Then, in MAVProxy, one line at a time and **only for the controlled bench test**:

```text
mode HOLD
disarm
rc 1 1500
rc 3 1500
mode MANUAL
arm throttle
```

Verify `ARM=True MODE=0 HB_OK=True` and `ENABLED=True`, then test a very short keypress. **Do not launch the keyboard before the third UDP output exists.** At shutdown, press `Q`, then:

```text
rc 1 1500
rc 3 1500
mode HOLD
disarm
```

Stop the bridge, ROS 2 agent and MAVProxy only after the wheels have stopped and motor power is safe. Restore a meaningful fence before leaving bench-testing conditions.

## 17. Next milestone: uploaded route execution

The long-term goal is to **upload a route/mission and let the robot execute it autonomously**. That has **not** been demonstrated in this experiment. A robust path is:

1. **Firmware-safety gate first:** verify an actual ESP32 watchdog and actuator power cut, add a manual emergency stop and restore/rebuild the geographic fence.
2. **Remove bench-only assumptions deliberately:** verify wheel radius, track width, encoder signs, command deadband and actual ROS 2 motor velocity scaling. Compare onboard odometry `/odom_raw` with ArduPilot output and GPS motion.
3. **Control-mode architecture:** safely extend the bridge beyond `MANUAL=0` to support `AUTO=10` and potentially `GUIDED=15` **only when mission state and reliable position data permit**, with strict mode, armed, age-of-data, failsafe, obstacle and speed checks. Never simply delete the mode check.
4. **Trajectory and obstacle behavior:** ensure the planner's speed and turning targets map to physically realizable `/cmd_vel` commands and ArduRover's steering mixing. Evaluate BendyRuler and fence interactions (`OA_TYPE=2`) and the relevant location source.
5. **Mission preparation:** on a ground station, create a small outdoor course in a surveyed safe area with no bystanders, save/upload waypoints to Cube Black, verify on the GCS and confirm home and fences. The `AUTO` mode normally follows waypoints stored on the autopilot, not commands manually stepped from the terminal.
6. **Progressive validation:** first mission status + outputs with wheels suspended; then an empty open test field at minimal speed with an independent stop available; eventually RTK and agricultural waypoint/circling logic.
7. **Deploy onboard:** when the Raspberry Pi returns, consider moving the micro-ROS agent and MAVLink-to-ROS-2 bridge onto the rover, using a **local Pixhawk-to-companion interface** and eliminating the Wi-Fi return path from actuation. This was **not** part of the current successful setup and will require a revised wiring and safety review.

For automatic navigation, the current bridge intentionally produces **zero velocity** in `AUTO=10` because it only enables `MANUAL=0`. This is the key next software modification, but doing it safely requires more than changing a number. ArduPilot's official AUTO documentation describes uploading and executing waypoint missions; it does not replace the need to validate our particular motor bridge.

## 18. Session evidence and conclusions

| Milestone | Evidence / result |
|---|---|
| RFD radio link | MAVProxy detected ArduRover 4.7.2 on Cube Black and received 885 parameters |
| Remote RC override | `rc 1 1600` appeared in `RC_CHANNELS.chan1_raw` |
| Yahboom connection | `micro_ros_task_node` subscribed to `/cmd_vel` |
| Robot telemetry | `/battery` yielded 10.89309024810791 |
| Python radio downlink | `HEARTBEAT` and `SERVO_OUTPUT_RAW` received on UDP 14551 |
| ROS 2 monitor | `/mavlink_ros2_monitor` and `/micro_ros_task_node` visible simultaneously |
| Zero-velocity bridge | `/cmd_vel` published around 10 Hz and content was zero |
| Geofence diagnosis | Polygon breach messages, unintended RTL, `FENCE_ACTION=1` |
| Motion gate | `ARM=True MODE=0 ENABLED=True` confirmed |
| Physical wheels | **Both wheels drove forward together and steered successfully** |
| Terminal controller | WASD wheel movement worked after adding UDP 14552 |
| Keyboard latency | **High perceived delay; unresolved** |
| Autonomous mission | **Not yet attempted successfully** |
| ESP32 local watchdog | **Not verified** |

**Main result:** a real two-wheel Yahboom MicroROS V2 robot was driven using Pixhawk's ArduRover skid-steering output **entirely via telemetry and ROS 2**, with **no physical PWM/motor wiring between the Pixhawk and Yahboom** and **no Raspberry Pi in the loop**. The project reached a verified manual-motion proof of concept. It is not yet a field-ready or autonomous navigation system.

## 19. References

1. ArduPilot, *Rover Motor and Servo Configuration* — skid-steer outputs 73/74: https://docs.ardupilot.org/rover/docs/rover-motor-and-servo-configuration.html
2. ArduPilot, *Manual Mode* — manual control and throttle slew behavior: https://docs.ardupilot.org/rover/docs/manual-mode.html
3. ArduPilot, *RC Input via MAVLink* — `RC_CHANNELS_OVERRIDE`, SYSID and latency: https://ardupilot.org/dev/docs/mavlink-rcinput.html
4. ArduPilot, *Rover Fences* — breach actions and RTL/HOLD: https://docs.ardupilot.org/rover/docs/common-geofencing-landing-page.html
5. ArduPilot, *Rover AUTO Mode* — uploading/executing waypoints: https://docs.ardupilot.org/rover/docs/auto-mode.html
6. ArduPilot, *Rover Parameters*: https://ardupilot.org/rover/docs/parameters.html
7. Yahboom, *MicroROS V2: Subscribe to Speed Control Topic*: https://www.yahboom.net/study/MicroROS-V2/20222/
8. Yahboom, *MicroROS V2: Publish IMU Data*: https://www.yahboom.net/study/microros-v2/20224
9. MAVProxy project: https://ardupilot.org/mavproxy/
10. ROS 2 Humble documentation: https://docs.ros.org/en/humble/

The **bench results, parameter values, IP addresses, commands and bugs** in this README come from the recorded experiment, not from the official references. The references establish relevant published behavior and should be revisited when upgrading software.

---

# Appendix A — Complete Python scripts used in the integration

The scripts below capture the source that was written and tested, including the diagnostic iterations. The final motion-bridge appendix includes the **extended diagnostic log** and the **180-second** test window; earlier iterations used a 30-second window and a shorter log. Each example expects the corresponding MAVProxy UDP output to be active. Only one process should bind UDP 14551 at a time.

## A.1 — One-off MAVLink telemetry receiver (`mavlink_receive_test.py`)

```python
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

```

## A.2 — Initial PWM normalization diagnostic (`mavlink_ros2_bridge.py`)

```python
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

```

## A.3 — ROS 2 telemetry monitor (`mavlink_ros2_monitor.py`)

```python
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

```

## A.4 — Zero-command safe bridge (`mavlink_ros2_bridge_safe.py`)

```python
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

```

## A.5 — Limited-motion bridge with diagnostics (`mavlink_ros2_bridge_motion.py`)

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
        self.get_logger().info('Bench motion bridge started, time limited')

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
        enabled = self.armed and self.mode == MANUAL_MODE and heartbeat_ok and servo_ok and within_test
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

## A.6 — Initial WASD controller (`rover_keyboard_initial.py`)

```python
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

```

## A.7 — Final terminal WASD controller with speed levels (`rover_keyboard.py`)

```python
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

```

# Appendix B — Additional console and troubleshooting snippets

These are commands used during the session; they are not independent files.

### B.1 Local UDP packet test on 14552

**First exit the WASD script** so only this process binds UDP port 14552:

```python
import socket
s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
s.bind(('127.0.0.1', 14552))
s.settimeout(5)
print('Listening for MAVLink UDP on 14552...')
try:
    for i in range(5):
        data, addr = s.recvfrom(4096)
        print(f'Packet {i+1}: {len(data)} bytes from {addr}')
except socket.timeout:
    print('No data within five seconds')
finally:
    s.close()
```

### B.2 Inspect active Yahboom joystick and agent processes

```bash
ps aux | grep -E 'joy_control|joy_node|teleop_twist_joy|micro_ros_agent'
sudo ss -lunp | grep 8090
ros2 topic info /cmd_vel -v
```

### B.3 Search workspace for a board-level watchdog

```bash
grep -RniE 'cmd_vel|watchdog|timeout|last_cmd|last_twist' \
  ~/microros_ws/src \
  --include='*.py' --include='*.cpp' --include='*.c' \
  --include='*.h' --include='*.hpp' \
  2>/dev/null | head -80
```

### B.4 Validate installed Python files

```bash
python3 -m py_compile scripts/*.py
```

### B.5 Example failed/successful logs

```text
# Initial condition — expected no motion
ARM=False MODE=4 PWM=(1500,1500) V=+0.000 W=+0.000 ENABLED=False

# GCS mode changed but vehicle not armed
ARM=False MODE=0 PWM=(1500,1500) ENABLED=False HB_OK=True SERVO_OK=True TIME_OK=True

# Fence-related RTL (bridge correctly blocks)
ARM=True MODE=11 PWM=(1366,1366) V=+0.000 W=+0.000 ENABLED=False

# Expired bench timeout (bridge correctly blocks)
ARM=False MODE=0 PWM=(1500,1500) ENABLED=False TIME_OK=False ELAPSED=508.3s

# Successful authorization for bench movement
ARM=True MODE=0 PWM=(1500,1500) V=+0.000 W=+0.000 ENABLED=True
HB_OK=True SERVO_OK=True TIME_OK=True

# Keyboard bug caused by absent MAVProxy output 14552
WASD: ARM=False MODE=None HB_OK=False
Bridge: ARM=True MODE=0 HB_OK=True
```

## License and contribution notes

This document reports a specific experiment and includes demonstration scripts created for it. The scripts are **experimental examples**, not a certified robot safety controller. Validate firmware versions, vendor licensing, calibration, and safety systems before incorporating these examples into another project. Never commit real network passwords or device secrets. Contributions particularly welcome: measured latency data, verified ESP32 watchdog behavior, a true keydown/keyup teleop interface, field-safe motor actuation, and the planned AUTO waypoint mission bridge.
