# ARBOREON — Mobile-Hotspot Networking, MAVLink, micro-ROS and Field-Test Handover

**Project:** ARBOREON / Yahboom MicroROS V2 differential-drive test platform + Cube Black (ArduRover)  
**Test date:** 2026-11-01  
**Environment:** Huawei P20 Pro Wi-Fi hotspot, Apple MacBook host, Ubuntu 22.04 ARM64 guest in UTM, Yahboom controller, MAVProxy, ArduDeck, ROS 2 Humble  
**Document status:** Reconstructed from terminal outputs, RobotManager screenshots, and confirmed test observations. Items that were not conclusively demonstrated are identified as such.  
**Intended audience:** Field operators, developers, and future maintainers  
**Safety status:** Communications restored; **autonomous motion calibration NOT completed**.

> **Key result:** We successfully restored micro-ROS/joystick operation after moving from the home Wi-Fi network to the phone hotspot; separately recovered Cube Black → MAVProxy → ArduDeck telemetry and Cube Black → MAVProxy → ROS 2 motion-bridge telemetry. We did **not** resolve the final ground-motion/continuous-turning behavior. Do not interpret telemetry success as a validated autonomous-driving system.

---

## 1. Executive summary

Switching the platform from the home WLAN (`192.168.1.0/24`) to a Huawei P20 Pro personal hotspot (`192.168.43.0/24` during this test) changed several device IP addresses. **Two distinct, independent hard-coded destinations broke:**

1. The Yahboom board's **stored micro-ROS Agent IP** remained `192.168.1.52`, the Ubuntu VM's former home-network address. RobotManager needed an explicit **Board Config → `agent_ip_addr`** update to the Ubuntu VM's new hotspot IP, `192.168.43.216`. Merely changing the Wi-Fi SSID did not update the Agent IP. With the Agent running on UDP 8090 and `ROS_DOMAIN_ID=40`, joystick operation was recovered.
2. MAVProxy continued forwarding MAVLink to the MacBook's **old hotspot lease** `192.168.43.109`; the actual macOS Wi-Fi IP later became `192.168.43.128`. Updating the MAVProxy destination to `192.168.43.128:14550` restored ArduDeck telemetry.

A **third, separate MAVLink destination** had been omitted: our Python motion bridge listens at `udpin:127.0.0.1:14551`. Adding `--out=udp:127.0.0.1:14551` to MAVProxy recovered bridge `HEARTBEAT` and `SERVO_OUTPUT_RAW` data (`HB_OK=True`, `SERVO_OK=True`).

The drivetrain subsequently showed insufficient ground motion and sometimes rotated continuously. The joystick provided an important reference: it successfully moved the robot with `linear.x=0.3 m/s` and rotated it with `angular.z=-1.5 rad/s`. These are **commanded ROS velocities**, not measured robot speeds or motor power. Motion-bridge limits and mixer/steering behavior require additional validation.

### Lessons to apply before every field session

- **Discover current IPs first** on **both** operating systems: Ubuntu VM and macOS. Do not reuse an IP from yesterday.
- Update **RobotManager's persistent board configuration** whenever the Agent IP changes; verify by reading back from the board.
- Verify the micro-ROS Agent is listening on **UDP 8090**, and that firmware and ROS nodes agree on `ROS_DOMAIN_ID=40` for this UTM profile.
- Start MAVProxy with **all required outputs at once**: local MAVLink consumer (optional) on 14550, ArduDeck/macOS on 14550, and motion bridge/Ubuntu on 14551.
- Confirm each layer independently: IP → UDP packets → application heartbeat/session → ROS topics → motor command → physically safe actuation.
- **Disable motion while troubleshooting connectivity.** Avoid concurrent publishers on `/cmd_vel` and verify disarm/heartbeat-loss stops before ground or autonomous trials.

---

## 2. System topology

```text
                       Huawei P20 Pro hotspot
                       gateway 192.168.43.1
                       network 192.168.43.0/24
                                |
                +---------------+-----------------+
                |                                 |
        Apple MacBook (macOS)                Yahboom ESP32/controller
        192.168.43.128 (later)              192.168.43.175 (candidate)
        |         |                           micro-ROS client
        |         +-- ArduDeck                Agent target: VM_IP:8090/UDP
        |             UDP LISTEN :14550                 |
        |
        +-- UTM Bridged (Advanced) VM
            Ubuntu ARM64 / ROS 2 Humble
            enp0s1 = 192.168.43.216
                |
                +-- micro-ROS Agent UDP :8090
                |      ROS_DOMAIN_ID=40
                |      <---- Wi-Fi micro-ROS ---- ESP32
                |
                +-- JoystickControl / joy_node
                |      /cmd_vel and related ROS nodes
                |
                +-- USB serial to Cube Black
                |      /dev/ttyUSB0 @ 57600 (observed)
                |      MAVProxy
                |         +--> 127.0.0.1:14550 (optional local app)
                |         +--> 192.168.43.128:14550 (ArduDeck/macOS)
                |         +--> 127.0.0.1:14551 (ROS 2 motion bridge)
                |
                +-- mavlink_ros2_bridge_motion.py
                       MAVLink UDP IN :14551
                       ROS 2 publisher /cmd_vel
```

**Important:** This is a logical diagram; the physical Cube Black USB wiring, ESP32 identity, and exact USB adapters must be checked for the current session. The RFD868x radio is a separate link, not a prerequisite for the working USB → MAVProxy telemetry path. Do not confuse a UTM USB-redirection error with a Wi-Fi/MAVLink error.

### Ports, processes, protocols

| Purpose | Host / endpoint | Protocol / port | Process or configuration |
|---|---|---|---|
| Yahboom board → micro-ROS Agent | Ubuntu VM current Wi-Fi IP | UDP 8090 | `micro_ros_agent udp4 --port 8090` |
| ROS 2 discovery | ROS 2 participants | DDS / ROS-domain-dependent traffic | `ROS_DOMAIN_ID=40` in UTM profile |
| Pixhawk → MAVProxy | Ubuntu `/dev/ttyUSB0` (verify) | Serial 57600 bps | `mavproxy.py --master=...` |
| MAVProxy → optional local listener | Ubuntu loopback | UDP 14550 | `--out=udp:127.0.0.1:14550` |
| MAVProxy → ArduDeck | macOS Wi-Fi IP | UDP 14550 | ArduDeck `Listen (Server)` |
| MAVProxy → ROS 2 motion bridge | Ubuntu loopback | UDP 14551 | `--out=udp:127.0.0.1:14551` |
| Motion bridge → Yahboom | ROS 2 graph | `/cmd_vel` (`geometry_msgs/Twist`) | bridge ROS 2 publisher; agent/controller subscriber path |

**Addresses shown above are historical observations, not permanent configuration.** Recompute/reconfirm them every session. `127.0.0.1` refers to **the process's own OS/network namespace**: within Ubuntu it is not macOS loopback.

---

## 3. Observed IP inventory and what was actually confirmed

| Entity | Address during test | Evidence | Confidence / caveat |
|---|---|---|---|
| Huawei P20 Pro hotspot | `192.168.43.1` | Ubuntu route + successful ping | Confirmed for that session |
| Ubuntu UTM, `enp0s1` | `192.168.43.216/24` | `ip -4 addr show`, `ip route` | Confirmed for that session |
| MacBook macOS Wi-Fi | `192.168.43.128` | `ipconfig getifaddr en0` executed in macOS | Confirmed later; superseded `.109` |
| Initially observed other network device | `192.168.43.109` | `arp-scan`, ping; later used as old ArduDeck destination | Initial identity not independently proven; **do not reuse** |
| ESP32 candidate | `192.168.43.175` | `arp-scan`, ping, ARP MAC | **Likely, not conclusively verified as Yahboom** |
| Candidate MAC for `.175` | `b0:a6:04:c9:99:e4` | ARP response | MAC confirmed for that IP during the scan; ownership not fully established |
| Home Wi-Fi Ubuntu Agent IP | `192.168.1.52` | Previous working setup + RobotManager readback | Historical only, wrong on mobile subnet |
| Raspberry Pi 5 Agent alternative | `192.168.1.58` | Prior alternate configuration | Historical only; **not** this UTM-hotspot Agent |

Linux `arp-scan` output during discovery:

```text
Interface: enp0s1, MAC: 1a:9b:40:1b:c8:1f, IPv4: 192.168.43.216
192.168.43.1    90:2b:d2:4b:43:ad    HUAWEI TECHNOLOGIES CO.,LTD
192.168.43.109  76:6b:e9:37:0e:68    (Unknown: locally administered)
192.168.43.175  b0:a6:04:c9:99:e4    (Unknown)
```

**Do not infer device identity solely from TTL or MAC vendor.** The `.175` device replied with IP TTL 255, which was consistent with an embedded device but not proof of being the ESP32. To conclusively identify it: use RobotManager device info, inspect the hotspot's connected-client list, or repeat scans with just the ESP32 disconnected/reconnected.

---

## 4. Chronology: tests, results, diagnoses

### 4.1 Ubuntu joins phone Wi-Fi and gets an address

Command in Ubuntu UTM:

```bash
ip -4 addr show
ip route
```

Observed:

```text
enp0s1: inet 192.168.43.216/24
 default via 192.168.43.1 dev enp0s1
192.168.43.0/24 dev enp0s1 ... src 192.168.43.216
```

Other adapters (`docker0`, `br-*`, `172.17/18/19.0.0/16`) belonged to Docker and were **not the phone WLAN**. Choose the default-route LAN interface, not a Docker bridge.

Gateway test:

```bash
ping -c 4 192.168.43.1
```

Result: three replies before manual interruption, 0% loss among transmitted packets, ~14.5 ms average RTT. This confirmed Ubuntu → hotspot connectivity; it did **not** validate board → Agent traffic.

### 4.2 Discover other devices

```bash
ip neigh show dev enp0s1
sudo apt-get update
sudo apt-get install -y arp-scan
sudo arp-scan -I enp0s1 192.168.43.0/24
```

`ip neigh` initially showed **only the gateway**. This is normal: the neighbor table caches machines with which the local host has communicated; it is **not** an inventory of all Wi-Fi clients.

`arp-scan` revealed `.109` and `.175`. Both responded to `ping`:

```text
192.168.43.109: 4/4 replies, avg ~0.405 ms, ttl=64
192.168.43.175: 4/4 replies, avg ~12.1 ms, ttl=255
```

A later simultaneous capture/ping to `.175` succeeded:

```bash
sudo timeout 10 tcpdump -ni enp0s1 'host 192.168.43.175' &
sleep 2
ping -c 5 192.168.43.175
wait
```

Observed 5/5 ICMP responses, ~9.3 ms average RTT, ICMP requests and replies plus ARP:

```text
IP 192.168.43.216 > 192.168.43.175: ICMP echo request
IP 192.168.43.175 > 192.168.43.216: ICMP echo reply
ARP, Reply 192.168.43.175 is-at b0:a6:04:c9:99:e4
12 packets captured
```

An earlier `tcpdump` produced zero packets because capture had been stopped **before** executing `ping`; this was a timing error, not evidence of a broken interface. `timeout` exit code **124** is expected when the command times out.

**Operational lesson:** Positive ping proves IP reachability to the responding host, **not** an established micro-ROS session.

### 4.3 Agent initially not running

```bash
sudo ss -lunp | grep 8090
```

Initially: no output → no UDP listener on port 8090 at that moment.

Agent startup in UTM:

```bash
source /opt/ros/humble/setup.bash
source ~/uros_ws/install/setup.bash
export ROS_DOMAIN_ID=40
ros2 run micro_ros_agent micro_ros_agent udp4 --port 8090
```

Observed:

```text
UDPv4AgentLinux.cpp | init | running... | port: 8090
Root.cpp | set_verbose_level | logger setup | verbose_level: 4
```

**Caution:** `running...` proves the Agent started; it does **not** prove the ESP32 connected. Also, the desktop `JoystickControl` launcher later started its **own** Agent. Avoid two simultaneous Agents on UDP 8090; use the launcher **or** a standalone Agent, not both.

### 4.4 Critical persistent configuration error in RobotManager

RobotManager **Board Config → Read Board** showed stored values (Yahboom firmware `1.1.0`):

```ini
wifi_ssid = HUAWEI P20 Pro
agent_ip_addr = 192.168.1.52
agent_ip_port = 8090
ros_domain_id = 40
```

The Wi-Fi SSID had already been changed to the mobile hotspot, **but the Agent destination still pointed to the old home WLAN** (`192.168.1.52`). A Wi-Fi connection alone cannot repair an embedded firmware setting that targets the wrong Agent address.

**Fix for the observed session:**

```ini
agent_ip_addr = 192.168.43.216
agent_ip_port = 8090
ros_domain_id = 40
```

RobotManager workflow:

1. Open **Board Config** and select **Read Board** (read stored values first).
2. Change `agent_ip_addr` to the **current Ubuntu VM IP** found from `ip -4 addr show`.
3. Keep `agent_ip_port=8090` and `ros_domain_id=40` for the current UTM profile.
4. Click **Apply** and then **Read Board** again to verify the persistent value; reboot/reconnect the board if required.
5. Do **not** click **Reset Defaults** during diagnosis.
6. Observe the Agent log for session creation and ROS 2 topics; finally test joystick with the drive safely disabled/raised first.

The screenshots showed other board values (`motor_pid=1.80,0.12,0.00`, `imu_yaw_pid=2.40,0.00,0.16`, `linear_velocity_scale=1`, `angular_velocity_scale=1`, `servo_1_offset=-5`, `servo_2_offset=0`). **These were readbacks, not recommendations to retune.** They were not needed to solve the IP issue. Screenshots briefly showed `Serial device not found: /dev/ttyUSB0` before a later successful board read; re-check which USB serial adapter RobotManager is opening, especially with several devices connected.

**Security note:** The original GUI log included a Wi-Fi passphrase. It is deliberately **omitted** from this repository document. Never commit hotspot credentials, private keys or full connection logs containing secrets.

### 4.5 Joystick was restored

The Ubuntu desktop launcher reported:

```text
=== JoystickControl ARM64 ===
ROS_DOMAIN_ID=40
CAR_TYPE=ptz
[micro_ros_agent] ... running... | port: 8090
[joy_node] Opened joystick: Controller. deadzone: 0.050000
```

After the RobotManager Agent IP was corrected, **joystick control worked** (user-confirmed). This confirms a working end-to-end control path for that configuration, not necessarily that all optional sensors/nodes were available.

**Do not confuse `joy_node` recognizing the USB gamepad with the ESP32 having an Agent session**. Both are needed for the actual end-to-end robot behavior.

### 4.6 Cube Black serial link worked

MAVProxy was started in UTM:

```bash
mavproxy.py \
  --master=/dev/ttyUSB0,57600 \
  --out=udp:127.0.0.1:14550
```

Evidence:

```text
Connect /dev/ttyUSB0,57600 source_system=255
Waiting for heartbeat from /dev/ttyUSB0
Detected vehicle 1:1 on link 0
online system 1
HOLD> Mode HOLD
ENCAP: ArduRover V4.7.2 (...)
AP: CubeBlack ...
```

This established **USB/serial → MAVProxy receiving the Cube Black MAVLink stream**. It did not imply that a separate UDP client was receiving data.

Port path `/dev/ttyUSB0` is **not stable** when USB devices are inserted or removed. Prefer identifying the actual adapter with:

```bash
lsusb
ls -l /dev/serial/by-id/ 2>/dev/null
ls -l /dev/ttyUSB* /dev/ttyACM* 2>/dev/null
sudo dmesg | tail -40
```

### 4.7 ArduDeck UDP issue: stale macOS IP and localhost confusion

ArduDeck was running in **macOS**, outside the Ubuntu guest, configured as:

```text
Listen (Server)
Local Port = 14550
Protocol = MAVLink
Status = Waiting for heartbeat...
```

A MAVProxy output of `127.0.0.1:14550` loops back into **Ubuntu**, not the macOS ArduDeck app. Another MAVProxy output had been set to `192.168.43.109:14550`, but the MacBook's **current** IP was later read from a **macOS Terminal**:

```bash
ipconfig getifaddr en0
# observed: 192.168.43.128
```

A recurring diagnostic mistake was attempting the macOS `ipconfig getifaddr en0` command from the Ubuntu prompt (`yahboom@vm:~$`), where that command does not exist. Run macOS commands in macOS Terminal; Linux commands in Ubuntu.

After updating the MAVProxy destination to the MacBook's latest IP, **ArduDeck telemetry was restored** (user-confirmed).

Use MAVProxy interactive console:

```text
HOLD> output
HOLD> output add 192.168.43.128:14550
HOLD> output
```

Avoid duplicate outputs; inspect the current list and remove stale entries with the supported `output remove <index>` command before adding a replacement. Indices depend on current list order.

Check egress in Ubuntu:

```bash
sudo timeout 10 tcpdump -ni enp0s1 \
  'udp and dst host 192.168.43.128 and dst port 14550'
```

Check arrival on macOS **from macOS Terminal** (interface often `en0`; confirm using `networksetup -listallhardwareports` if necessary):

```bash
sudo tcpdump -ni en0 'udp port 14550'
```

If ArduDeck remains at **Waiting for heartbeat**:

- Verify the **macOS current IP**, not the Ubuntu VM IP.
- Confirm ArduDeck is in **Listen/Server**, local UDP port 14550 and MAVLink protocol.
- Verify MAVProxy is actively connected to the Pixhawk and has an output for **that macOS IP:14550**.
- Capture packets on the source and destination; only then investigate macOS firewall and ArduDeck process binding.

### 4.8 Motion bridge initially had no MAVLink packets

The motion-bridge logs initially showed:

```text
ARM=False MODE=None PWM=(1500,1500)
V=+0.000 W=+0.000 ENABLED=False
HB_OK=False SERVO_OK=False TIME_OK=True
```

Inspecting the local script revealed:

```python
MAVLINK_PORT = "udpin:127.0.0.1:14551"
TOPIC = "/cmd_vel"
```

**Root cause:** MAVProxy was forwarding to UDP 14550 targets but **not 14551**, where the bridge listens.

Fix in MAVProxy interactive console:

```text
HOLD> output add 127.0.0.1:14551
HOLD> output
```

Successful bridge logs then showed:

```text
ARM=True MODE=10 PWM=(1900,1100)
V=+0.000 W=-0.300 ENABLED=True
HB_OK=True SERVO_OK=True TIME_OK=True
```

This confirmed `HEARTBEAT` and `SERVO_OUTPUT_RAW` reception. `MODE=10` corresponds to AUTO in **the bridge's own ArduRover mode constants**; it is **not** a neutral/idle condition. PWM `(1900,1100)` encodes opposite wheel commands and therefore a turn-in-place according to the current mixer. **This was not a successful forward-driving test.**

The bridge later again showed `HB_OK=False`, `SERVO_OK=False`, `MODE=None`, neutral PWM: always re-check the third output **after restarting MAVProxy**. Merely re-running the bridge does not add an output to MAVProxy.

### 4.9 Final ground-motion problem remained unresolved

Observations:

- Wheels responded and accelerated when the platform was suspended, but were initially too weak to launch the heavy robot on the ground.
- The same robot **did move acceptably under direct joystick control**. This makes a general battery/motor incapacity less likely and gives a realistic commanded-speed reference, but does not prove the downstream motor driver is identical under every control path.
- The bridge's conservative velocity clamps were initially `MAX_LINEAR=0.08 m/s`, `MAX_ANGULAR=0.30 rad/s` (later attempted changes included `0.15/0.60` and suggested joystick-matching `0.30/1.50`). **The final tested file contents and successful ground-drive response were not re-verified.**
- At one point the robot **kept turning in circles instead of progressing**. No diagnostic trace conclusively established whether the cause was intended AUTO heading correction, incorrect yaw/heading, differential motor sign/channel mapping, two `/cmd_vel` publishers, or another issue.

**Do not label field autonomy as working.** Communications restored ≠ wheel-direction mapping confirmed ≠ navigating a path safely.

---

## 5. Canonical startup: reproduce the verified network/telemetry setup

### 5.1 Preflight (power and safety)

1. Keep the robot **disarmed**, with wheels **suspended or drive power safely isolated** for communication tests. Keep a physical stop/disarm option available.
2. Connect the MacBook, Ubuntu bridged VM and Yahboom board to the **same phone hotspot**, ensuring the phone allows client-to-client communication.
3. Ensure the Cube Black USB serial adapter is visible in the Ubuntu guest; do not assume a particular `/dev/ttyUSB*` assignment.
4. Connect only the required USB devices. UTM may display USB-redirection issues when attaching an additional device.
5. Prevent simultaneous direct joystick and Pixhawk bridge motion publishers to `/cmd_vel` for actuated tests.

### 5.2 Discover the Ubuntu VM IP (Ubuntu terminal)

```bash
ip -4 addr show enp0s1
ip -4 route get 1.1.1.1
ip route
```

Portable extraction of the **default-route IPv4 source**:

```bash
VM_IF=$(ip -4 route show default | awk 'NR==1 {for(i=1;i<=NF;i++) if($i=="dev") {print $(i+1); exit}}')
VM_IP=$(ip -4 -o addr show dev "$VM_IF" scope global | awk 'NR==1 {split($4,a,"/"); print a[1]}')
printf 'VM_IF=%s\nVM_IP=%s\n' "$VM_IF" "$VM_IP"
```

This detects the active default-route NIC but may select a non-hotspot interface in a multi-homed system. **Inspect the displayed interface, subnet, gateway and hotspot SSID before using it.** No reliance on public internet access is needed for the `ip route` commands.

### 5.3 Discover the macOS Wi-Fi IP (macOS Terminal, NOT Ubuntu)

```bash
networksetup -listallhardwareports
ipconfig getifaddr en0
```

In this session `en0` was the Wi-Fi interface; it may differ on another Mac or with adapters. Confirm which hardware port corresponds to Wi-Fi. Example of a more adaptable macOS one-liner:

```bash
WIFI_IF=$(networksetup -listallhardwareports | awk '/Hardware Port: Wi-Fi/{getline; sub(/^Device: /,""); print; exit}')
MAC_IP=$(ipconfig getifaddr "$WIFI_IF")
printf 'WIFI_IF=%s\nMAC_IP=%s\n' "$WIFI_IF" "$MAC_IP"
```

This must run **on macOS**. If the Mac uses Ethernet for hotspot networking instead of Wi-Fi, select the real connected interface manually.

### 5.4 Confirm hotspot client/board identity

```bash
# Ubuntu
ping -c 3 192.168.43.1                # example gateway: find actual via `ip route`
sudo arp-scan -I "$VM_IF" --localnet
ip neigh show dev "$VM_IF"
```

Check the phone's list of connected hotspot clients and RobotManager. Never automatically assume `.175` or any address from the example is the board.

### 5.5 Update RobotManager Agent IP (mandatory when VM IP changes)

In **RobotManager → Board Config**:

```text
Read Board → confirm Wi-Fi SSID
agent_ip_addr = <current VM_IP>
agent_ip_port = 8090
ros_domain_id = 40
Apply → Read Board → verify value persisted → reconnect/reboot board as needed
```

**This is a persistent board setting.** Changing the Linux shell environment, ROS_DOMAIN_ID, or MAVProxy outputs does **not** rewrite it. Keep SSID and credentials out of repo scripts.

### 5.6 Launch the micro-ROS Agent and joystick

Existing desktop `JoystickControl` script, observed:

```text
ROS_DOMAIN_ID=40
CAR_TYPE=ptz
micro_ros_agent ... udp4, port 8090
joy_node and joy_control_node
```

Launch **that desktop tool** as usual. If running the Agent manually **instead**, use:

```bash
source /opt/ros/humble/setup.bash
source ~/uros_ws/install/setup.bash
export ROS_DOMAIN_ID=40
ros2 run micro_ros_agent micro_ros_agent udp4 --port 8090
```

Diagnostic commands (separate terminal):

```bash
sudo ss -lunp | grep ':8090'
sudo tcpdump -ni "$VM_IF" 'udp port 8090'
ROS_DOMAIN_ID=40 ros2 node list
ROS_DOMAIN_ID=40 ros2 topic list
```

A listening port is a prerequisite, **not** proof of Agent/board session. Observe Agent session messages and verify live ROS traffic.

### 5.7 Confirm the Cube Black USB port before starting MAVProxy

```bash
ls -l /dev/serial/by-id/ 2>/dev/null
lsusb
ls -l /dev/ttyUSB* /dev/ttyACM* 2>/dev/null
ps aux | grep '[m]avproxy'
```

Use the correct real serial path and baud rate. The validated session used `/dev/ttyUSB0,57600`. Stop any prior process holding the port before starting a new MAVProxy.

### 5.8 Start MAVProxy with ALL required UDP outputs

**Example for the IPs at the successful moment of this test** (replace macOS IP every session):

```bash
mavproxy.py \
  --master=/dev/ttyUSB0,57600 \
  --out=udp:127.0.0.1:14550 \
  --out=udp:192.168.43.128:14550 \
  --out=udp:127.0.0.1:14551 \
  --console \
  --map
```

**Purpose of the three outputs:**

1. `127.0.0.1:14550` — optional Ubuntu-local application listener. Safe to omit when unused.
2. `<current macOS Wi-Fi IP>:14550` — ArduDeck receiving MAVLink on Mac.
3. `127.0.0.1:14551` — Python motion bridge in the Ubuntu VM (required for that bridge).

The `--console` / `--map` flags require working MAVProxy GUI dependencies; omit either if the GUI fails. The initial MAVProxy **MAVLink relay** works without those windows.

Check interactive MAVProxy console:

```text
HOLD> output
```

Do **not** assume output indices are fixed: they reflect the current session.

Verify local bridge delivery:

```bash
sudo timeout 10 tcpdump -ni lo 'udp dst port 14551'
```

Verify macOS delivery from Ubuntu:

```bash
sudo timeout 10 tcpdump -ni "$VM_IF" \
  'udp dst port 14550 and dst host 192.168.43.128'
```

ArduDeck should show MAVLink heartbeats and telemetry instead of **Waiting for heartbeat**.

### 5.9 Start the motion bridge only after output 14551 is proven

Relevant local file:

```text
~/mavlink_ros2_bridge_motion.py
```

The file used the following receiving and publishing endpoints:

```python
MAVLINK_PORT = "udpin:127.0.0.1:14551"
TOPIC = "/cmd_vel"
```

Ensure ROS 2 environment matches the controller (`ROS_DOMAIN_ID=40`). For non-actuating checks, keep the Pixhawk disarmed:

```bash
source /opt/ros/humble/setup.bash
export ROS_DOMAIN_ID=40
python3 ~/mavlink_ros2_bridge_motion.py
```

If `pymavlink` or ROS 2 imports are not available in that shell, use the Python environment from the previously working script setup. **Do not install dependencies blindly into system Python.**

Verify `HB_OK=True` and `SERVO_OK=True` only after a valid stream has arrived. With disarm active, `ENABLED=False` and zero commanded velocity is the **expected safe outcome**.

---

## 6. Recommended automation: preflight and IP-aware MAVProxy launcher

**Design decision:** Keep **device discovery** separate from **actuation**. A startup helper may discover the VM IP, display the phone gateway, validate the Mac IP *supplied from macOS*, and launch the telemetry relay. It **must not** silently guess the Mac IP from ARP scans or change the board's persistent RobotManager settings.

### 6.1 Minimal safe preflight (Ubuntu)

The following is a proposed utility, not yet deployed or tested on this robot. Save as `scripts/field_network_preflight.sh` in the repository:

```bash
#!/usr/bin/env bash
set -euo pipefail

VM_IF=$(ip -4 route show default | awk 'NR==1 {for(i=1;i<=NF;i++) if($i=="dev") {print $(i+1); exit}}')
[[ -n "${VM_IF:-}" ]] || { echo 'ERROR: no default-route interface' >&2; exit 1; }
VM_IP=$(ip -4 -o addr show dev "$VM_IF" scope global | awk 'NR==1 {split($4,a,"/"); print a[1]}')
GW=$(ip -4 route show default | awk 'NR==1 {for(i=1;i<=NF;i++) if($i=="via") {print $(i+1); exit}}')
[[ -n "${VM_IP:-}" ]] || { echo 'ERROR: no IPv4 address on default interface' >&2; exit 1; }

printf 'Ubuntu VM interface : %s\n' "$VM_IF"
printf 'Ubuntu VM IPv4      : %s\n' "$VM_IP"
printf 'Default gateway     : %s\n' "${GW:-none}"
printf 'micro-ROS Agent     : %s:8090/UDP\n' "$VM_IP"
printf 'ROS_DOMAIN_ID       : 40 (UTM profile)\n'

if [[ -n "${GW:-}" ]]; then
  ping -c 2 -W 2 "$GW" || echo 'WARNING: gateway ping failed'
fi

if command -v ss >/dev/null; then
  ss -lun | grep -E '(^|[[:space:]])[^[:space:]]*:8090[[:space:]]' || \
    echo 'INFO: UDP 8090 not listening yet (start Agent/JoystickControl)'
fi

cat <<MSG

NEXT STEPS:
  1. On macOS Terminal, find the current Wi-Fi IP (ipconfig getifaddr en0).
  2. In RobotManager, set agent_ip_addr = $VM_IP; Apply and Read Board.
  3. Start only one micro-ROS Agent on UDP 8090.
  4. Confirm the correct Cube Black serial device before MAVProxy.
  5. Start MAVProxy with the CURRENT macOS IP, local :14551 output,
     and any actually needed local :14550 output.
  6. Keep motors disarmed during connectivity diagnosis.
MSG
```

This helper is **read-only** and cannot accidentally arm the Pixhawk or change any hardware settings.

### 6.2 IP-aware MAVProxy launcher (Ubuntu)

The following optional script is a **proposal** for `scripts/start_field_mavproxy.sh`. It prompts for and validates a **macOS IP**; it does not assert that the responding host is definitely the Mac. It requires you to supply the verified serial device path. It will not launch if another MAVProxy process is already running.

```bash
#!/usr/bin/env bash
set -euo pipefail

if pgrep -f '[m]avproxy.py' >/dev/null; then
  echo 'ERROR: another mavproxy.py appears to be running.' >&2
  echo 'Check its existing output list instead of opening the serial port twice.' >&2
  exit 1
fi

VM_IF=$(ip -4 route show default | awk 'NR==1 {for(i=1;i<=NF;i++) if($i=="dev") {print $(i+1); exit}}')
[[ -n "${VM_IF:-}" ]] || { echo 'ERROR: no default network interface' >&2; exit 1; }
VM_CIDR=$(ip -4 -o addr show dev "$VM_IF" scope global | awk 'NR==1 {print $4}')
[[ -n "${VM_CIDR:-}" ]] || { echo 'ERROR: no IPv4 on default interface' >&2; exit 1; }

MAC_IP="${1:-}"
SERIAL_DEVICE="${2:-}"
BAUD="${3:-57600}"

if [[ -z "$MAC_IP" || -z "$SERIAL_DEVICE" ]]; then
  echo "Usage: $0 <MAC_WIFI_IP> <PIXHAWK_SERIAL_DEVICE> [BAUD]" >&2
  echo "Example: $0 192.168.43.128 /dev/ttyUSB0 57600" >&2
  exit 2
fi

python3 - "$VM_CIDR" "$MAC_IP" <<'PY'
import ipaddress, sys
vm_net = ipaddress.ip_interface(sys.argv[1]).network
mac = ipaddress.ip_address(sys.argv[2])
if mac not in vm_net:
    raise SystemExit(f'ERROR: Mac IP {mac} is not within VM network {vm_net}')
print(f'Network match: {mac} is in {vm_net}')
PY

[[ -e "$SERIAL_DEVICE" ]] || { echo "ERROR: missing serial device $SERIAL_DEVICE" >&2; exit 1; }
[[ "$BAUD" =~ ^[0-9]+$ ]] || { echo 'ERROR: BAUD must be numeric' >&2; exit 1; }

printf '\nMAVProxy preflight:\n'
printf '  macOS ArduDeck target : %s:14550\n' "$MAC_IP"
printf '  Local motion bridge   : 127.0.0.1:14551\n'
printf '  Optional local output : 127.0.0.1:14550\n'
printf '  Serial device         : %s @ %s\n' "$SERIAL_DEVICE" "$BAUD"

read -r -p 'Confirm Cube Black is DISARMED and start telemetry relay? [y/N] ' reply
[[ "$reply" == 'y' || "$reply" == 'Y' ]] || exit 0

exec mavproxy.py \
  --master="$SERIAL_DEVICE,$BAUD" \
  --out=udp:127.0.0.1:14550 \
  --out="udp:$MAC_IP:14550" \
  --out=udp:127.0.0.1:14551
```

Example after confirming macOS IPv4 **in macOS** and the Cube Black serial adapter **in Ubuntu**:

```bash
chmod +x scripts/field_network_preflight.sh scripts/start_field_mavproxy.sh
./scripts/field_network_preflight.sh
./scripts/start_field_mavproxy.sh 192.168.43.128 /dev/ttyUSB0 57600
```

**Limitations:** Same-subnet validation does not prove the target Mac actually owns that IP; macOS must be checked. UTM bridged networking and the hotspot must permit peer connectivity. The script does not reconfigure the ESP32 Agent IP or start ROS motion (deliberately). The `pgrep` guard is conservative, not a lock against all serial-port contention. These are untested suggested helpers; review before deploying.

### 6.3 Longer-term improvement: stable addressing

Potential options, in order of practicality:

1. **Preflight discovery + explicit targets:** Most reliable portable workflow; survives DHCP changes on typical phone hotspots.
2. **Hotspot DHCP reservation:** Only if the phone/hotspot firmware actually supports it. Do **not** assume Huawei P20 Pro can reserve DHCP addresses.
3. **Hostname / mDNS resolution:** Investigate whether the board firmware supports a hostname Agent target (instead of numeric `agent_ip_addr`); do not assume support. mDNS can be unreliable across guest/host bridges or hotspot isolation.
4. **Single onboard Agent (Raspberry Pi 5) and local Ethernet/USB topology:** Reduces dependence on the Mac's VM address but requires deliberate ROS-domain, networking and power design. Previous Pi Agent profile used `ROS_DOMAIN_ID=20`, not this VM profile's `40`.
5. **Versioned field profiles** (`home`, `huawei-hotspot`, `rpi-agent`) with explicit stored metadata, not embedded Wi-Fi passwords. Avoid modifying firmware and MAVProxy destinations by memory.

---

## 7. Motion-bridge code audit and controlled calibration

Relevant source captured during the session:

```python
MAVLINK_PORT = "udpin:127.0.0.1:14551"
TOPIC = "/cmd_vel"
PWM_CENTER = 1500
PWM_SPAN = 500
MAX_LINEAR = 0.08         # initial test version
MAX_ANGULAR = 0.30        # initial test version
NOMINAL_SPEED = 0.40
WHEEL_SEPARATION = 0.22
HEARTBEAT_TIMEOUT = 2.0
SERVO_TIMEOUT = 0.6
TEST_DURATION = 180.0
MANUAL_MODE = 0
AUTO_MODE = 10
HOLD_MODE = 4
RTL_MODE = 11
```

Algorithm (simplified):

```python
left  = clamp((pwm_left  - 1500) / 500, -1.0, 1.0)
right = clamp((pwm_right - 1500) / 500, -1.0, 1.0)
v_left  = left  * NOMINAL_SPEED
v_right = right * NOMINAL_SPEED
linear  = (v_left + v_right) / 2
angular = (v_right - v_left) / WHEEL_SEPARATION
command.linear.x  = clamp(linear,  -MAX_LINEAR,  MAX_LINEAR)
command.angular.z = clamp(angular, -MAX_ANGULAR, MAX_ANGULAR)
```

A `Twist` is published at 10 Hz and defaults to zero unless:

```text
armed AND mode ∈ {MANUAL(0), AUTO(10)}
AND a valid HEARTBEAT has arrived within 2.0s
AND SERVO_OUTPUT_RAW has arrived within 0.6s
AND time since bridge startup < 180s
```

The script logs `ARM`, `MODE`, `PWM`, `V`, `W`, `ENABLED`, `HB_OK`, `SERVO_OK`, `TIME_OK`, `ELAPSED`. This is helpful diagnostics, but must not be mistaken for independent measured wheel velocity.

**Documentation/code mismatch:** Startup log said `movement limited for 30 seconds`, but the actual `TEST_DURATION` constant was **180 seconds**. Fix log text or duration before future tests.

### 7.1 Reference commands from successful joystick control

ROS 2 topic `/cmd_vel` observed during manual joystick use:

```yaml
# Forward (observed maximum)
linear:  {x: 0.3, y: 0.0, z: 0.0}
angular: {x: 0.0, y: 0.0, z: 0.0}

# Turn in place (observed maximum in one direction)
linear:  {x: 0.0, y: 0.0, z: 0.0}
angular: {x: 0.0, y: 0.0, z: -1.5}
```

When releasing input, the joystick app sent a **ramp** (e.g. `0.300, 0.284, 0.268, ... 0.012, 0.0` for linear, and also a deceleration toward zero for angular). This suggests joystick control was not a sudden step command.

The bridge initially used much smaller command caps (`0.08 m/s`, `0.30 rad/s`), explaining some lack of effective motion. Suggested matching caps were `0.30 m/s` and `1.50 rad/s`; however **the full commanded output, mechanical sign convention, and final ground behavior were not validated**.

**Warning:** `MAX_LINEAR`, `MAX_ANGULAR`, and `NOMINAL_SPEED` describe *commanded kinematic speed*, **not motor electrical power or stall torque**. Larger values are not a safe substitute for calibrating wheel polarity, PID behavior, motor current or acceleration.

### 7.2 Why the robot turned in place

One confirmed log:

```text
PWM=(1900,1100)
V=+0.000 W=-0.300   # initial angular limit
```

With symmetric equal-and-opposite normalized wheel inputs, linear motion cancels. The bridge thus computed **zero forward movement and nonzero yaw**, exactly a turn-in-place. Later, the operator observed the robot repeatedly turning instead of navigating forward. This could be:

- A legitimate but endless heading correction in AUTO due to wrong yaw, GPS course/heading assumptions or waypoint geometry.
- Incorrect output-function assignment, servo reversal, wheel sign, or left/right indexing between Cube Black, `SERVO_OUTPUT_RAW`, and Yahboom motor wiring.
- Two independent `/cmd_vel` publishers (joystick and bridge) competing.
- Kinematic parameters (`WHEEL_SEPARATION`, wheel scale), dead-zone/velocity tracking or speed controller mismatch.
- Timeouts or mode changes interrupting commands.

**No root cause was conclusively established.** Do not alter servo reversal or increase speed limits without a controlled direction test.

### 7.3 Minimal safe motor-direction validation (future work)

1. **Disarm**, place the platform on secure supports, and arrange an independent emergency stop.
2. Stop all but one `/cmd_vel` publisher. Check `ros2 topic info /cmd_vel -v`.
3. Validate expected positive and negative wheel directions one at a time with a low, bounded command, using an approved existing test tool and a short timeout. Compare actual wheel directions with motor-side labels. Keep body away from wheels.
4. In MANUAL, correlate commanded forward/turn with `SERVO_OUTPUT_RAW` channels and the bridge's signed `linear.x`, `angular.z`. Confirm `servo1_raw` and `servo3_raw` really correspond to the intended left/right motors **for the present Pixhawk parameters**.
5. Confirm manual disarm, loss of heartbeat, loss of servo stream and test-expiry generate a real motor stop. Check downstream motor-controller watchdog behavior, not just published zero messages.
6. Only then attempt slow, supervised ground travel with clear space, reliable location/heading, and an immediately accessible kill/disarm mechanism.

**Additional engineering concern:** The bridge publishes a stream of commands to `/cmd_vel` and zero on shutdown, but publishing zeros at shutdown **is not a substitute for a hardware E-stop and downstream watchdog**. Unexpected process death or networking loss may prevent sending final zeros. A command arbiter should enforce a single active controller and loss-of-command braking.

---

## 8. Troubleshooting matrix

| Symptom | Most likely issue | Fast proof | Action |
|---|---|---|---|
| Ubuntu has no hotspot access | Wrong UTM interface/bridge or phone connection | `ip addr`, `ip route`, `ping <gateway>` | Verify UTM Bridged (Advanced), Mac hotspot connection, DHCP and gateway |
| Ubuntu pings gateway but board does not connect | Board not connected, wrong board Agent IP, hotspot isolation | Phone clients + RobotManager readback + UDP 8090 capture | Correct SSID/Agent address; verify board identity |
| `ip neigh` lists only gateway | Neighbor cache incomplete | `arp-scan`, controlled ping | Do not assume board offline |
| `tcpdump` captured zero | No concurrent traffic, wrong interface/filter, or actual network issue | Run capture and ping **at same time** | Repeat correctly; check interface |
| Agent does not start | No listener or already used port | `ss -lunp | grep 8090` | Launch one Agent only |
| Agent `running...`, no session | Board using old IP, wrong port, no traffic | RobotManager `agent_ip_addr`; `tcpdump udp port 8090` | Apply current VM IP, reboot board, read back |
| `joy_node` sees controller but no robot motion | Agent or board connection absent; ROS domain mismatch; competing publishers | Agent log, ROS topic list, `/cmd_vel` | Validate end-to-end path, `ROS_DOMAIN_ID=40`, arbiter |
| MAVProxy waits for Pixhawk heartbeat | Wrong USB serial adapter/baud, port busy, cable | `/dev/serial/by-id`, `lsusb`, process list | Choose correct device and release port |
| MAVProxy sees Cube, ArduDeck waiting | Old Mac IP, `127.0.0.1` used across VMs, missing output | `output`, macOS IP, `tcpdump` both ends | Add `<CURRENT_MAC_IP>:14550` |
| ArduDeck remains waiting despite packets | Receiver configuration, firewall or application binding | macOS `tcpdump`, ArduDeck Listen/14550 | Fix receiver; verify MAVLink heartbeat format |
| Motion bridge shows `HB_OK=False`, `SERVO_OK=False` | MAVProxy missing local 14551 output; bridge not bound; source stopped | `output`, `tcpdump -ni lo udp port 14551`, `ss` | Add `127.0.0.1:14551`, ensure one bridge listener |
| `HB_OK=True`, `SERVO_OK=True`, `ENABLED=False` | Expected when disarmed/HOLD/test expired, or mode invalid | Log `ARM/MODE/TIME_OK` | Keep safe until intentional, supervised test |
| Bridge sees PWM but wheels weak on ground | Velocity clamps/mixer/dead zone/competition or controller tuning | Compare joystick `/cmd_vel` and bridge output; one publisher | Calibrate commanded velocities and downstream feedback, do not assume battery fault |
| Platform spins continuously in AUTO | Wheel polarity/mixer, heading/navigation error or competing commands | Lifted-wheel MANUAL tests + actual yaw/mission state | Stop AUTO; correct mapping and heading before field mission |
| UTM popup `usbredir protocol parse error ... [0079:181c]` | USB device redirection failure | macOS USB identification + Ubuntu `lsusb` | Identify actual device; reattach carefully; **not proof of RFD failure** |
| `ipconfig` not found | macOS command run inside Ubuntu | Prompt `yahboom@vm:~$` | Open macOS Terminal, not guest shell |

---

## 9. USB / RFD868x incidental finding

When connecting an additional radio device, UTM displayed:

```text
usbredir protocol parse error for USB Device [0079:181c] at 3-2
```

The precise USB device corresponding to `[0079:181c]` was **not conclusively established** during this conversation. The error is in UTM/QEMU USB redirection, not directly in the MAVLink UDP protocol. A separate RFD868x link had **not** been established as the cause of the ArduDeck issue.

Suggested USB identification:

```bash
# macOS Terminal:
system_profiler SPUSBDataType

# Ubuntu UTM:
lsusb
ls -l /dev/serial/by-id/ 2>/dev/null
sudo dmesg | tail -40
```

Do not blindly assume `/dev/ttyUSB0` is still the Cube Black when USB serial adapters are inserted/reordered. Verify the device's physical identity or `/dev/serial/by-id` symlink before MAVProxy launch.

---

## 10. Field-run checklist (copy into each test log)

```text
[ ] Robot disarmed; wheels raised/drive isolated for initial checks
[ ] Hardware stop available; clear test area; operator supervising
[ ] Mac joined intended hotspot SSID
[ ] Ubuntu UTM Bridged networking active
[ ] VM_IF / VM_IP / gateway recorded
[ ] macOS Wi-Fi interface / MAC_IP recorded from macOS Terminal
[ ] ESP32 identified in hotspot clients; board IP confirmed
[ ] RobotManager Board Config Read Board completed
[ ] RobotManager agent_ip_addr == CURRENT VM_IP
[ ] RobotManager agent_ip_port == 8090
[ ] RobotManager ros_domain_id == 40 (this profile)
[ ] Board setting applied and read back successfully
[ ] Exactly one micro-ROS Agent listening UDP 8090
[ ] Joystick session / ROS topics checked
[ ] Cube Black actual serial device verified; baud confirmed
[ ] MAVProxy has Cube Black heartbeat
[ ] MAVProxy local output 127.0.0.1:14551 present
[ ] MAVProxy ArduDeck output CURRENT MAC_IP:14550 present
[ ] ArduDeck Listen (Server), MAVLink, UDP 14550
[ ] ArduDeck heartbeat/telemetry confirmed
[ ] Bridge HB_OK / SERVO_OK verified with robot disarmed
[ ] Only intended publisher may command /cmd_vel
[ ] Disarm, stream-loss, bridge-exit and watchdog stop tested
[ ] Motor directions & heading consistency validated before AUTO
[ ] Record actual session IPs, serial ID, processes, mode and logs
```

Recommended session record template:

```yaml
session_date: YYYY-MM-DD
network:
  ssid: <hotspot name only; NO PASSWORD>
  subnet: <CIDR>
  gateway: <gateway IP>
  vm_interface: <e.g., enp0s1>
  vm_ip: <current VM address>
  mac_wifi_interface: <e.g., en0>
  mac_ip: <current Mac address>
  board_ip: <confirmed controller IP or unknown>
micro_ros:
  agent_target: <vm_ip>:8090
  ros_domain_id: 40
  robotmanager_readback_verified: false
mavlink:
  pixhawk_serial: </dev/serial/by-id/... preferred>
  baud: 57600
  outputs:
    - 127.0.0.1:14550
    - <mac_ip>:14550
    - 127.0.0.1:14551
checks:
  cube_heartbeat: false
  ardudeck_telemetry: false
  bridge_hb_ok: false
  bridge_servo_ok: false
  safe_stop_verified: false
  wheel_direction_verified: false
  autonomous_motion_validated: false
notes: <observations and open issues>
```

---

## 11. Files and commands worth preserving in the repo

| Artifact | Purpose | Caution |
|---|---|---|
| `mavlink_ros2_bridge_motion.py` | MAVLink SERVO/heartbeat → ROS 2 `/cmd_vel` bridge | Current test implementation; review safety and wheel mapping |
| `scripts/field_network_preflight.sh` *(proposed)* | Read current VM IP and report Agent target | No persistent device changes |
| `scripts/start_field_mavproxy.sh` *(proposed)* | Prompt for current Mac IP and launch the 3-output MAVProxy relay | Validate serial device, outputs, and target host |
| RobotManager Board Config readback | Source of board-side Agent address / ROS domain | Do not commit Wi-Fi passwords/screenshots containing them |
| ArduDeck Connection screenshot/config | Show Listen(Server) UDP 14550 MAVLink | A GUI in "Waiting" is not a connected vehicle |
| `mav.tlog` / console logs | MAVLink evidence and incident reconstruction | May contain location/flight details; decide before publishing |
| `ros2 topic info /cmd_vel -v` output | Identify all publishers and subscribers | Important before motion testing |

For code-quality improvements, consider a single **configuration inventory file** (without secrets), a launch supervisor that guarantees exactly one source of `/cmd_vel`, and a watchdog/kill input with independence from Wi-Fi and the guest OS.

---

## 12. Confirmed results versus open issues

### Confirmed

- Ubuntu UTM obtained `192.168.43.216/24` from the Huawei hotspot; gateway `.1` was reachable.
- Network devices `.109` and `.175` were discovered; `.175` was reachable by ping and ARP, though board identity was not definitively proven.
- The micro-ROS Agent was started on UDP 8090 with UTM ROS domain 40.
- RobotManager readback revealed the wrong, old Agent address `192.168.1.52`; after correction, **joystick operation worked**.
- MAVProxy connected to a Cube Black running ArduRover 4.7.2 via `/dev/ttyUSB0,57600`.
- ArduDeck telemetry was restored when MAVProxy targeted macOS' new `192.168.43.128:14550` address.
- Motion bridge telemetry was restored with MAVProxy output `127.0.0.1:14551`; `HB_OK=True` and `SERVO_OK=True` appeared.
- The joystick published observed `0.30 m/s` linear and `-1.50 rad/s` angular command magnitudes and ramped back to zero.

### Still unresolved / explicitly not validated

- Exact IP/MAC attribution of the Yahboom board versus other hotspot clients.
- Final saved bridge speed-limit values after all changes.
- Whether the Pixhawk/Yahboom wheel-channel signs are correct in all modes.
- Why the robot remained weak on the ground through the bridge and later spun in circles.
- Safe, repeatable AUTO navigation and mission completion in the field.
- A robust single-writer `/cmd_vel` command arbiter and proven watchdog/hardware stop path.
- Exact identity/recovery path for UTM USB error `[0079:181c]` with the radio attached.
- Proposed automation scripts above have **not yet been executed/tested** on the live platform.

---

## 13. Quick-reference commands

```bash
# UBUNTU UTM — live network configuration
ip -4 addr show enp0s1
ip route
sudo arp-scan -I enp0s1 --localnet

# UBUNTU UTM — Agent, ROS domain, micro-ROS traffic
sudo ss -lunp | grep 8090
export ROS_DOMAIN_ID=40
ros2 topic list
sudo tcpdump -ni enp0s1 'udp port 8090'

# UBUNTU UTM — Cube serial identity and MAVProxy status
ls -l /dev/serial/by-id/ 2>/dev/null
ps aux | grep '[m]avproxy'

# UBUNTU UTM — UDP verification
sudo timeout 10 tcpdump -ni lo 'udp dst port 14551'
sudo timeout 10 tcpdump -ni enp0s1 'udp dst port 14550'
sudo ss -lunp | grep 14551

# UBUNTU UTM — ROS motion source inspection
ros2 topic info /cmd_vel -v
ros2 topic echo /cmd_vel

# macOS TERMINAL — current host Wi-Fi IP (check interface)
ipconfig getifaddr en0

# macOS TERMINAL — ArduDeck UDP receive inspection
sudo tcpdump -ni en0 'udp port 14550'
```

**Final operational rule:** *Identify network → update RobotManager's Agent address → start one micro-ROS Agent → establish Cube serial MAVLink → verify every MAVProxy UDP output → verify ArduDeck and bridge separately → validate stop and wheel directions → only then permit supervised motion.*

---

*Prepared for the ARBOREON project from the field-debugging session on 2026-11-01. This file intentionally contains no hotspot password or other credentials.*
