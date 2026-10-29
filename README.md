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
