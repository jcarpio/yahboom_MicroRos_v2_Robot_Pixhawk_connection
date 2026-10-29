# ARBOREON — From MAVROS Telemetry to Accepted RC Overrides: Complete Experimental Record and Reproduction Guide

**Date:** 29 October 2026  
**Platform:** Raspberry Pi 5 (8 GB), Yahboom MicroROS V2 two-motor rover, ESP32-S3, Cube Black / ArduRover 4.7.2, ROS 2 Humble, MAVROS, ArduDeck  
**Document type:** Technical investigation, experimental report, diagnostic scripts, and engineering handover  
**Companion:** *ARBOREON — Complete Raspberry Pi 5, Yahboom MicroROS V2, Pixhawk Cube Black, MAVROS and ArduDeck Integration Handover* (29 October 2026, supplied as source).  
**Scope:** The **subsequent** investigation of Pixhawk differential-output configuration, ROS 2 PWM-to-Twist bridge, MAVROS identity, MAVLink RC overrides, radio failsafe, and MANUAL mode. The companion covers the preceding Wi-Fi, UDP micro-ROS, first wheel movement, and ArduDeck integration.

> **Evidence legend:** **OBSERVED** = operator-pasted console output or direct observation. **EXECUTED** = command/script was run in the session, although not necessarily all its internal effects were proven. **RECONSTRUCTED** = faithful, cleaned-up equivalent of an executed interactive snippet; exact shell-paste bytes are not guaranteed. **PROPOSED** = not yet performed. **UNKNOWN** = no evidence. The original transcript contains occasional corrupted shell paste displays (`'Y...`) even when the executed Python produced a valid result. The scripts below are formatted cleanly for reproduction; do not mistake this reconstruction for a byte-for-byte archival transcript.

---

## Abstract

This report traces a multi-stage debugging process to integrate a Pixhawk Cube Black running ArduRover 4.7.2 with a Yahboom MicroROS V2 differential-drive platform. The aim was to let ArduRover produce motor commands that can be translated by ROS 2 into `/cmd_vel`, while preserving independently verifiable safety constraints. Initial attempts to observe or inject RC commands failed in ways that looked like absent radio hardware, misconfigured ROS topics, incorrect servo functions, or a nonresponsive flight controller. The investigation established that the apparent failure was primarily a **MAVLink source-system identity mismatch**: although ROS parameter `/mavros/system_id` was changed to 254 at runtime, transmitted `RC_CHANNELS_OVERRIDE` messages continued to carry source `SYSID=1`, whereas ArduPilot was configured to authorize GCS IDs 254–255. A custom MAVROS startup corrected the effective identity. Subsequent raw-MAVLink inspection confirmed that RC1 changed from 1500 to 1600 microseconds on demand, and returned to 1500 after an explicit command. A second issue was discovered: without continuous valid RC input, the ArduPilot **radio failsafe** entered critical status and HOLD. Continuous neutral overrides cleared the radio failsafe and enabled a successful **HOLD → MANUAL** transition while disarmed. When the stream ended, ArduRover later returned to HOLD and critical status. **No armed non-neutral differential PWM output or Pixhawk-driven wheel motion was demonstrated.**

## 1. Motivation, objective, and boundaries

The ARBOREON research robot is intended for supervised and eventually autonomous olive-grove work. A Raspberry Pi runs ROS 2 and communicates over Wi-Fi/micro-ROS with an ESP32 motor controller. A Cube Black running ArduRover supplies a mature flight/rover control stack (modes, RC/MAVLink commands, failsafes, missions, navigation). The engineering challenge is that **the Cube does not electrically drive the two Yahboom motors**: it generates logical servo/PWM outputs exposed by MAVROS; a separate bridge must interpret those outputs and publish ROS velocity commands. A functioning Pixhawk telemetry link therefore does **not** prove Pixhawk-to-wheel control.

The companion handover already verified the Pi/ESP32 network and agent, ROS topics, motor motion from a direct ROS test, and Mac ArduDeck telemetry. This experiment had five progressively stronger objectives:

1. Assign the correct ArduRover left/right output functions and read both outputs.
2. Develop a read-only differential PWM interpreter, then a guarded bench-only live bridge.
3. Determine whether MAVROS can send accepted RC virtual inputs when there is no physical RC receiver.
4. Identify the reason `MANUAL` requests initially failed and demonstrate a safe disarmed mode transition.
5. Set up a reproducible foundation for future **motor-power-off** PWM tests, followed eventually by supervised powered tests *only after* calibration and safety checks.

The observed end state satisfies (1), the read-only and guarded portions of (2), and the acceptance/mode aspects of (3)–(4). Objective (5) remains **future work**.

### 1.1 Topology at the end of the experiments

```text
MacBook / ArduDeck (GCS, typically SYSID 255)
      ^ optional MAVLink UDP endpoint :14550
      |
Raspberry Pi 5 / Docker arboreon-dev / ROS_DOMAIN_ID=20
      |-- MAVROS process: ONE instance, custom launch
      |       |-- /mavros UAS component: effective MAVLink SYSID 254 / COMPID 191
      |       |-- /mavros/rc/override -> RC_CHANNELS_OVERRIDE (message 70)
      |       |-- /mavros/state       <- HEARTBEAT (message 0)
      |       |-- /mavros/rc/out      <- SERVO_OUTPUT_RAW (message 36)
      |       |-- /mavros/rc/in       <- RC_CHANNELS (message 65; empty when chancount=0)
      |       +-- /uas1/mavlink_sink and /uas1/mavlink_source (raw MAVLink)
      |               |
      |          USB /dev/ttyACM0:115200
      |               |
      |          Pixhawk Cube Black / ArduRover 4.7.2 / vehicle SYSID=1
      |          SERVO1_FUNCTION=73  (throttle left)
      |          SERVO3_FUNCTION=74  (throttle right)
      |
      |-- PWM-to-Twist bridge (BENCH implementation; last seen STOPPED)
      |       /mavros/rc/out + /mavros/state -> /cmd_vel
      |                                            |
      |-- micro-ROS Agent UDP 8090 <----- Wi-Fi ------ ESP32-S3 MicroROS V2
      |                                              -> two drive motors
      +-- /odom_raw, /imu, /scan, /battery ...        (cutter disconnected)
```

### 1.2 Reproducibility environment

| Item | Observed configuration |
|---|---|
| Raspberry | Pi 5 8 GB; host accessed as `pi@raspberrypi` |
| Container | `arboreon-dev` |
| ROS | ROS 2 Humble inside Docker, not installed on host shell |
| ROS domain | `20` |
| MAVROS executable | `/opt/ros/humble/lib/mavros/mavros_node` |
| FCU device | `/dev/ttyACM0:115200` |
| Vehicle | Cube Black, ArduRover 4.7.2, system ID `1` |
| MAVROS UAS source (final, observed on wire) | `254:191` |
| MAVROS router | `fcu_urls=['/dev/ttyACM0:115200']`, `uas_urls=['/uas1']`, `gcs_urls=[]` in one check |
| Raw MAVLink | `/uas1/mavlink_source` (observed incoming), `/uas1/mavlink_sink` (observed outgoing) |
| RC input | `/mavros/rc/override`, `mavros_msgs/msg/OverrideRCIn` |
| Servo output | `/mavros/rc/out`, `mavros_msgs/msg/RCOut`, approx. 5 Hz |
| ROS motor command | `/cmd_vel`, `geometry_msgs/msg/Twist`, ESP32 subscriber BEST_EFFORT |
| Physical RC receiver | Not connected / `RC_CHANNELS.chancount=0` |
| Safety context | Wheels suspended for earlier motor test, mower/cutter disconnected, operator-confirmed physical motor power cutoff; all RC/mode diagnostics in this report with motor power OFF |

**Critical shell rule:** run `docker exec ...` on the *Raspberry host*. Inside `bash -lc`, source ROS and export the domain:

```bash
source /opt/ros/humble/setup.bash
export ROS_DOMAIN_ID=20
```

## 2. Executive results and chronology

### 2.1 Experimental milestones (chronological)

| Stage | Test / observation | Actual result | Confidence |
|---|---|---|---|
| 1 | Direct ROS `/cmd_vel` into Yahboom | Suspended wheels moved forward at 0.03 m/s command and stopped | **OBSERVED**; predecessor report |
| 2 | ArduRover differential output assignment | `SERVO1_FUNCTION=73`, `SERVO3_FUNCTION=74`; trims 1500; ranges 1100–1900 | **OBSERVED** in subsequent parameter reads |
| 3 | Read-only PWM-to-Twist bridge | Neutral `1500/1500` -> 0 linear/0 angular; HOLD and disarm block output; arithmetic tests passed | **OBSERVED**; bridge conversion not physically calibrated |
| 4 | `--live` bridge startup interlock | Required seeing a disarmed state after startup; HOLD blocked motion despite arming | **OBSERVED** |
| 5 | Duplicate bridge processes | Four dry processes and three live processes discovered; ultimately zero `/cmd_vel` publishers | **OBSERVED** |
| 6 | Neutral RC override, before identity fix | `/mavros/rc/in` empty; output `1500/1500` | **OBSERVED**, inconclusive |
| 7 | Source ID analysis | `/mavros/system_id=1`, Pixhawk `MAV_GCS_SYSID=255` | **OBSERVED** |
| 8 | Change `/mavros/system_id` at runtime | Parameter read 254; outgoing RC_OVERRIDE still source **1:191** | **OBSERVED**, important negative result |
| 9 | Configure Pixhawk authorized range | `MAV_GCS_SYSID=254`, `MAV_GCS_SYSID_HI=255` | **OBSERVED** |
| 10 | Decode raw `RC_CHANNELS` | Message 65 arrived; `chancount=0`, `rssi=255`, RC1=1500, RC3=1000 | **OBSERVED** |
| 11 | Rebuild custom MAVROS launch; remove duplicate MAVROS | One MAVROS node PID 8263; parameter YAML loaded | **OBSERVED** |
| 12 | Validate actual sender ID | Heartbeat/system time/timesync outgoing from source `254:191` | **OBSERVED** |
| 13 | RC1 differential diagnostic | `RC1 1500 -> 1600` in incoming raw MAVLink; output RC_OVERRIDE 70 from `254:191` | **OBSERVED** acceptance |
| 14 | Release after override | After explicit release, RC1 remained at 1600 on readback; explicit RC1=1500 restored to 1500 | **OBSERVED**; release not same as command neutral |
| 15 | Request MANUAL with no maintained RC | `mode_sent=True` but mode remained HOLD; status later 5 (CRITICAL) | **OBSERVED** |
| 16 | Check ArduPilot notices | `Radio failsafe on`; also hardware safety switch, accel and compass calibration warnings | **OBSERVED** |
| 17 | Stream neutral RC continuously | `Radio Failsafe Cleared`; status 5 -> 3 (STANDBY) | **OBSERVED** |
| 18 | Stop/release neutral RC | First 8-second observation remained STANDBY, later tests returned to HOLD/CRITICAL | **OBSERVED**; time/event behavior not fully characterized |
| 19 | Inspect `MODE_CH` and attempt `MODE_CH=0` | Channel 8 assigned; MODE1..MODE6 all 0; changing MODE_CH alone did not clear failsafe or enter MANUAL | **OBSERVED** |
| 20 | Keep neutral RC and request MANUAL | `Radio Failsafe Cleared`; mode HOLD -> MANUAL; status 5 -> 3 -> 4; disarmed | **OBSERVED** |
| 21 | End of RC stream and subsequent read | Mode returned to HOLD, state 5; servo outputs 1500/1500; no `/cmd_vel` publishers | **OBSERVED** |
| 22 | Arm with non-neutral RC, measure servo mix, wheels driven by Pixhawk | **NOT PERFORMED** |

### 2.2 Final observed state

- **Final Pixhawk:** `connected: true`, `armed: false`, `mode: HOLD`, `system_status: 5` after stopping RC virtual input; servo outputs 1 and 3 `1500` µs.
- **MAVROS:** exactly one node (PID `8263` in that snapshot), launched with custom identity configuration and proven outgoing `SYSID=254, COMPID=191`.
- **ArduPilot authorization:** GCS system-ID range `254..255`. Vehicle system ID remained `1`.
- **Motor bridge:** no active Python bridge and `Publisher count: 0` on `/cmd_vel` in the last checks.
- **RC receiver:** MAVLink `RC_CHANNELS` explicitly advertised `chancount=0`; this is not by itself a failure of MAVLink RC overrides.
- **Failures not resolved:** hardware safety-switch condition, accelerometer calibration, compass calibration, lack of GNSS fix; full loss-of-link safety and powered Pixhawk-driven wheels.

## 3. The differential output bridge: development and bench tests

### 3.1 Why the bridge is needed

The Cube Black is connected to the Raspberry by USB MAVLink, not to the motor-driver input stages. ArduRover servo outputs 1 and 3 appear in `/mavros/rc/out.channels[0]` and `[2]` (ROS indices are zero-based). To drive Yahboom, translate valid values into a ROS `Twist` command, using the intended skid-steer relation:

```text
u_left  = clamp((PWM1 - 1500) / 400, -1, +1)
u_right = clamp((PWM3 - 1500) / 400, -1, +1)
v_left  = u_left  * v_wheel_max
v_right = u_right * v_wheel_max
linear.x  = (v_left + v_right)/2
angular.z = (v_right - v_left)/wheel_separation
```

Initial **assumptions**: PWM valid interval 1100–1900 µs, trim 1500, deadband ±15 µs, wheel speed scaling 0.03 m/s, wheel separation 0.25 m. These are **bench limits/placeholders, not physical calibration**. Encoder readings, inversion, friction and wheel geometry must be measured. Never treat a `0` on inactive servo channels as a valid motor PWM.

### 3.2 Pure arithmetic testing

The first script `arboreon_mavros_bridge.py` implemented a read-only PWM interpreter. A separate pure-Python test suite, `test_bridge_math.py`, checked 1500/1500 neutral, forward, reverse, opposite-direction turns and invalid PWM values. The observed result was **seven math tests passed**. See **Appendices A and B** for the complete preserved source files.

The bridge initially printed repeated:

```text
PWM L=1500 R=1500 | v=0.000 m/s w=0.000 rad/s |
armed=False mode=HOLD eligible=False | OBSERVE ONLY
```

State arrives near 1 Hz, output near 5 Hz. The bridge used *arrival-time monotonic age* rather than relying on potentially inconsistent MAVLink-derived header timestamps. A longer state freshness threshold was necessary when an initial threshold was too strict relative to the ~1 Hz state stream.

### 3.3 Guarded `--live` script and startup interlock

The preserved `/mnt/data/arboreon_bridge/arboreon_mavros_bridge_live.py` is included in Appendix C. It defaults to **dry-run** and creates a `/cmd_vel` publisher only with `--live`. It observes a disarmed state at least once after starting, rejects HOLD, checks `connected`, freshness and valid output channel count/range; it does **not** recheck `SERVO*_FUNCTION` at runtime. It publishes zero velocity when ineligible, with a 10 Hz timer; fault latch requires a disarm to reset.

An actual execution showed:

```text
LIVE STARTUP_INTERLOCK: must observe disarmed once ... armed=? mode=?
LIVE DISARMED L=1500 R=1500 v=+0.000 w=+0.000 armed=False mode=HOLD
LIVE MODE_BLOCKED:HOLD L=1500 R=1500 v=+0.000 w=+0.000 armed=True mode=HOLD
```

The user armed the Cube while keeping HOLD and the suspended-wheel/no-cutter safety setup. **No actual wheel motion from this bridge was established.** A subsequent run started while the Pixhawk was already armed; it remained in `STARTUP_INTERLOCK`—an expected protection against adopting an unknown active state.

The operator's physical motor-power cutoff was tested, and a short *no-explicit-zero* ROS test suggested motor commands time out if publishing stops; **the actual ESP32 watchdog interval and behavior on Wi-Fi/Agent loss have not been measured**. The live bridge itself should not be considered a certified safety system or deployed with an active cutter.

### 3.4 Duplicate publishers discovered

The diagnostic:

```bash
docker exec arboreon-dev bash -lc '
  pgrep -af arboreon_mavros_bridge_live.py || true
'
```

revealed **seven** simultaneous processes (four dry and three `--live`). The live instances could publish concurrently to `/cmd_vel`. This is dangerous even if every current message is zero. They were stopped/cleared and verified with:

```bash
docker exec arboreon-dev bash -lc '
  ps -eo pid,args | grep "[p]ython3 /tmp/arboreon_mavros_bridge" || true
  source /opt/ros/humble/setup.bash
  export ROS_DOMAIN_ID=20
  ros2 topic info /cmd_vel -v
'
```

Later, two older named bridge processes (`arboreon_mavros_bridge.py` and `_v2.py`) also remained. The final results repeatedly showed **0 publishers / 1 ESP32 subscriber**. An arming or PWM test must not run with multiple controllers competing for `/cmd_vel`.

## 4. Identifying MAVROS's RC override problem

### 4.1 First symptoms: apparent absence of radio channels

With the Pixhawk in HOLD, disarmed, the first one-shot and five-second sustained override probes sent RC1/RC3 neutrals using `/mavros/rc/override`. `/mavros/rc/in` returned `channels: []` throughout. `/mavros/rc/out` stayed at `[1500,0,1500,0,...]`, around 5 Hz.

**Interpretation at that time:** inconclusive. HOLD/disarm require outputs to remain neutral; therefore unchanged outputs cannot show whether the incoming overrides were accepted. `RCIn.channels=[]` is a telemetric representation of RC availability; it is not direct proof that override messages were discarded.

For repeatability, the sustained neutral sender used `OverrideRCIn.channels` of length 18, `65535` for *ignore/no-change*, explicitly setting RC1 and RC3, then publishing 18 zeros to *release*. Note that the operator's initial steering test used RC3=1000; later the reported RC3 trim was 1500 and min 1100. **These values should not be conflated**; 1000 was part of a diagnostic with motors unpowered, not an approved powered neutral throttle setting.

### 4.2 Parameters and source-versus-target distinction

The successful ROS queries discovered:

```text
/mavros system_id=1; component_id=191       # SOURCE (initial)
/mavros_node tgt_system=1; tgt_component=1   # FCU TARGET
/mavros/param MAV_SYSID=1                    # FCU identity
/mavros/param MAV_GCS_SYSID=255              # authorized GCS ID (initial)
/mavros/param MAV_GCS_SYSID_HI=0             # initial value
/mavros/param MAV_OPTIONS=0
/mavros/param RC_OPTIONS=32
/mavros/param RC_OVERRIDE_TIME=3.0
```

The original MAVROS launch was:

```bash
ros2 launch mavros apm.launch fcu_url:=/dev/ttyACM0:115200
```

In this deployment, `apm.launch` is **XML**, not `apm.launch.py`, and includes `node.launch`. `node.launch` declares `fcu_url`, `gcs_url`, `tgt_system`, `tgt_component`, plugin YAML and config YAML, but did **not** declare source `system_id` explicitly. The source default was `1`; `/uas1` was an **internal UAS router endpoint**, not a SYSID. Router parameters were:

```text
fcu_urls=['/dev/ttyACM0:115200']
gcs_urls=[]
uas_urls=['/uas1']
```

**Critical differentiation:** the FCU system ID must stay `1`. Setting MAVROS's source ID to an authorized GCS value is conceptually different from setting the vehicle target ID.

### 4.3 Configure authorized GCS source IDs

The team set, and read back, these ArduPilot parameters:

```text
MAV_GCS_SYSID_HI=255
MAV_GCS_SYSID=254
```

ArduPilot now permitted the inclusive range 254–255. The original attempt using `ros2 service call /mavros/param/set mavros_msgs/srv/ParamSet` hung because the service was advertised with multiple types (`ParamSet`, `ParamSetV2`) and the tool invocation was unreliable in that environment. **The route that worked was `ros2 param set /mavros/param`**, verifying each parameter before proceeding:

```bash
# READ this section and its precautions before changing an actual FCU:
# Only replicate these writes after recording your original values.
docker exec arboreon-dev bash -lc '
  source /opt/ros/humble/setup.bash
  export ROS_DOMAIN_ID=20
  ros2 param set /mavros/param MAV_GCS_SYSID_HI 255
  ros2 param get /mavros/param MAV_GCS_SYSID_HI
  ros2 param set /mavros/param MAV_GCS_SYSID 254
  ros2 param get /mavros/param MAV_GCS_SYSID
'
```

**Operational caveat:** changing authorized GCS IDs affects which stations may control the robot; inventory all GCS clients first. The session observed a heartbeat `SYSID=255, COMPID=190`, compatible with an existing ground station. A range is appropriate only if it matches actual control architecture and firmware semantics. Retain a recovery path and original parameter backup.

### 4.4 Runtime parameter change did not change the wire

The ROS command:

```bash
ros2 param set /mavros system_id 254
ros2 param get /mavros system_id  # 254
```

reported success, but a raw outgoing MAVLink monitor of `/uas1/mavlink_sink` counted **1,905** `RC_CHANNELS_OVERRIDE` frames, all showing source **SYSID=1, COMPID=191**:

```text
OVERRIDE SALIENTE SYSID=1 COMPID=191
TOTAL OVERRIDES: 1905
EMISORES: {(1, 191): 1905}
```

**This is the central discovery of the entire investigation.** A successful ROS parameter write did not update the already-initialized MAVLink sender identity. A restart with initialization-time parameters was required. The large count (1,905 in a two-second application-level probe) is a count observed on the local router topic, **not a measured serial transmission rate or proof that 1,905 packets crossed USB**.

### 4.5 Raw MAVLink revealed why RCIn was empty

The team inspected `mavros_msgs/msg/Mavlink` on `/uas1/mavlink_source` (passive telemetry), using MAVLink message IDs:

| ID | Message | Purpose |
|---:|---|---|
| 0 | HEARTBEAT | Vehicle/GCS status and source identifier |
| 36 | SERVO_OUTPUT_RAW | PWM outputs |
| 65 | RC_CHANNELS | RC input fields, `chancount`, RSSI |
| 70 | RC_CHANNELS_OVERRIDE | GCS/companion pilot inputs (observed on outgoing sink) |
| 111 | TIMESYNC | Time synchronization |

The raw observations included IDs 65 (21 messages in one ~5 s probe), 36 (12), and 0 (8), alongside other telemetry. Decode `payload64` as *little-endian uint64 words*, respecting actual MAVLink payload length. For `RC_CHANNELS` (common.xml), the layout is 4-byte `time_boot_ms`, 18 little-endian uint16 channels, one uint8 `chancount` at byte **40**, and one uint8 `rssi` at byte **41**.

Repeated output:

```text
RC_CHANNELS #1 ... chancount=0 rssi=255
channels=[1500,1500,1000,1500,0,0,0,0,0,0,0,0,0,0,0,0,0,0]
... repeated 15 times ...
```

A `chancount=0` frame declares **no valid physical RC receiver channels**. MAVROS consequently provided `RC_IN=[]`, even while the outgoing RC override path could still work. RC values present in the payload should not be mistaken for real physical receiver availability when `chancount=0`.

### 4.6 Build the custom startup and stop duplicate MAVROS instances

A custom XML launch was created by copying the standard `node.launch` and `apm.launch` under `/tmp`. A dedicated YAML with `/mavros.ros__parameters.system_id=254`, `component_id=191` was included via `<param from="..."/>` inside the MAVROS node. `ros2 launch ... --show-args` validated argument resolution but not wire behavior. In the session, a first attempt `kill -INT 184` **did not** stop original launch PID 184 or child PID 185; starting the custom launch anyway briefly created **two competing MAVROS instances** on the same USB port. The old process was subsequently stopped. The single verified new MAVROS process was PID 8263.

The new process reported remote FCU address `1.1`, with `/dev/ttyACM0:115200` open. The ROS parameter file `/tmp/arboreon_mavros_identity.yaml` appeared explicitly in its command line. A passive five-second outbound raw MAVLink monitor showed:

```text
MSG_ID=0   SYSID=254 COMPID=191 COUNT=4
MSG_ID=2   SYSID=254 COMPID=191 COUNT=4
MSG_ID=111 SYSID=254 COMPID=191 COUNT=44
SYSID 254 OBSERVADO
```

**This established that source ID 254 was effective on the wire.** The initial outgoing frames were heartbeat, system time and timesync, not yet RC overrides.

### 4.7 Accepted RC override — decisive A/B comparison

After the launch correction, the team transmitted `RC1=1600` with `RC3=1000` for ~2 seconds (motors OFF, disarmed HOLD) and monitored both directions:

```text
ANTES:   (1500, 1000, 0)
DURANTE: (1500, 1000, 0)
DURANTE: (1600, 1000, 0)
DURANTE: (1600, 1000, 0)
DURANTE: (1600, 1000, 0)
OVERRIDES SALIENTES: {(254, 191): 1891}
MENSAJES RC RECIBIDOS: 13
ULTIMA LECTURA: (1600, 1000, 0)
OVERRIDE LIBERADO
```

The third tuple field was `chancount=0`. **Evidence of acceptance is the change in FCU-originated RC1 payload value**, not `RCIn.channels`. The 1,891 outgoing count is a raw router-topic event count and is not a USB throughput benchmark.

### 4.8 Releasing an override is not the same as commanding neutral

Immediately after the release message, a passive five-second reader saw fifteen reports of `RC1=1600`, `RC3=1000`, `chancount=0`. This showed **no confirmed return to the expected neutral RC value**. It is compatible with ArduPilot displaying its last retained channel value after override release when no receiver is available; it does **not** by itself show that active control remains applied indefinitely.

A new explicit RC1=1500 override caused:

```text
RC1 ANTES: 1600
RC1 DESPUES DE NEUTRO: 1500
RC1 FINAL OBSERVADO: 1500
OVERRIDE LIBERADO
```

**Engineering consequence:** the safe shutdown sequence must explicitly neutralize valid commanded channels **before** releasing the override. It must still be supported by an independent local watchdog and hardware power disable; a `finally:` block cannot guarantee delivery after Wi-Fi/USB/process failure.

## 5. Mode-selection and failsafe investigation

### 5.1 MANUAL request while no RC stream was maintained

The service call:

```bash
ros2 service call /mavros/set_mode mavros_msgs/srv/SetMode \
  '{base_mode: 0, custom_mode: MANUAL}'
```

returned `mode_sent=True`, but repeated `/mavros/state` observations remained `HOLD`, disarmed. The status later changed to `system_status=5` (**MAV_STATE_CRITICAL**). A successful service response means MAVROS dispatched the request; **it does not confirm acceptance/retention of MANUAL**.

### 5.2 Relevant ArduRover failsafe parameters

| Parameter | Observed | Note |
|---|---:|---|
| `FS_THR_ENABLE` | 1 | Radio/throttle failsafe enabled |
| `FS_THR_VALUE` | 910 | Threshold setting, not a guarantee about override timeout |
| `FS_ACTION` | 2 | HOLD action in this firmware configuration |
| `FS_TIMEOUT` | 1.5 s | Read successfully earlier; a later `timeout` caused CLI traceback |
| `FS_GCS_ENABLE` | 0 | Ground-control-station failsafe disabled; not a micro-ROS/ESP32 stop assurance |
| `FS_EKF_ACTION` | 1 | Configured EKF-related action |
| `RC_OVERRIDE_TIME` | 3.0 s | Override timeout setting |
| `MAV1_RC_CHAN` | 1 | RC-channel telemetry configured; raw ID 65 observed |
| `MODE_CH` (initial) | 8 | RC mode-selection channel |
| `MODE1`...`MODE6` | all 0 | Selected-mode slots set to Manual in this firmware |
| `RC8_OPTION` | 0 | No auxiliary option assigned |
| `RC8_MIN/TRIM/MAX` | 1100/1500/1900 | RC8 calibration |

`FS_TIMEOUT` ROS command in one run raised `ExternalShutdownException` because `timeout 4` interrupted the CLI. That is not a Pixhawk fault.

### 5.3 ArduPilot's explicit prearm alerts

The `/mavros/statustext/recv` subscriber returned four warnings (severity 2):

```text
PreArm: Hardware safety switch
PreArm: 3D Accel calibration needed
PreArm: Compass not calibrated
PreArm: Radio failsafe on
```

This **directly confirms the active radio failsafe at that point**; it also confirms outstanding prearm conditions. It does not prove the radio failsafe is the only possible reason for any mode behavior.

### 5.4 Neutral override stream clears the radio failsafe

The five-second `arboreon_failsafe_recovery_test` published RC1=1500 and RC3=1500 continuously, while listening for `StatusText` and `State`:

```text
INICIO: HOLD 5
ESTADO: HOLD 5
ALERTA: Radio Failsafe Cleared
ESTADO: HOLD 3
FINAL: ('HOLD', 3)
OVERRIDE LIBERADO
```

This is **strong causal evidence** that the missing continuous virtual RC stream contributed to the critical/HOLD behavior. The Pixhawk was disarmed and no wheel motion was requested.

An eight-second passive follow-up after a release showed `HOLD`, `armed=False`, `system_status=3`, with no new text alerts. Therefore **a release followed by 8 seconds cannot be assumed to be equivalent to an abrupt link failure** or to trigger an immediate fallback in all states.

### 5.5 Mode-selector hypothesis tested separately

The configuration was `MODE_CH=8`, `RC8_OPTION=0`, `RC8_TRIM=1500`, with MODE1–MODE6 all 0. The operator changed `MODE_CH=0` through ROS parameters, then requested MANUAL **without a sustained RC stream**. Result:

```text
MODE_CH: 0 (applied)
mode_sent: true
armed: false
mode: HOLD
system_status: 5
SERVO1/3: 1500/1500
```

Changing the selector alone did not clear the critical state or produce MANUAL. **No restoration of MODE_CH=8 is shown in the transcript**, so the final observed setting is `MODE_CH=0`. Record this in any next handover. A subsequent controlled test should determine whether `MODE_CH=0` is the desired long-term policy, but do not ascribe the earlier failure primarily to RC8.

### 5.6 Neutral RC + MANUAL request succeeds

The decisive eight-second `arboreon_manual_neutral_test` did the following: require connected, disarmed FCU; transmit neutral RC continuously; wait until `system_status==3`; submit a single `SetMode(MANUAL)` request while still streaming; observe resulting state and text alerts; release RC on exit.

Observed:

```text
INICIO: HOLD 5
t=0.1s mode=HOLD status=5
ARDUPILOT: Radio Failsafe Cleared
t=1.1s mode=HOLD status=3
ARDUPILOT: PreArm: Hardware safety switch
ARDUPILOT: PreArm: 3D Accel calibration needed
ARDUPILOT: PreArm: Compass not calibrated
MANUAL SOLICITADO
t=3.2s mode=MANUAL status=4
...
t=7.3s mode=MANUAL status=4
ESTADO FINAL: ('MANUAL', 4)
OVERRIDE LIBERADO
```

**`system_status=4` is MAV_STATE_ACTIVE**, not proof of arming. `armed` was not included in the program's printed final tuple; the test logic would have aborted if it became true. Additional subsequent state read showed `armed: false`. This was a **mode-control** success, not an actuation success.

### 5.7 Subsequent return to HOLD and critical status

The next standalone read showed:

```text
connected: true
armed: false
mode: HOLD
system_status: 5
rc/out.channels = [1500, 0, 1500, 0, ...]
/cmd_vel Publisher count: 0; Subscription count: 1
```

This is **consistent with** radio failsafe after ending the stream, as `FS_ACTION=2` requests HOLD. However, no synchronized raw event trace or forced USB/Wi-Fi cut was recorded in that transition, so do not claim a precise trigger interval, certified communications watchdog, or demonstrated wheel stopping under link failure. In particular, the earlier eight-second released observation remained in STANDBY.

## 6. Safety analysis and interpretation pitfalls

1. **Flight-controller mode is not an arm-state substitute.** `system_status=4` did not mean `armed=True`; inspect `State.armed` explicitly.
2. **`mode_sent=True` is not FCU mode confirmation.** Always observe subsequent `/mavros/state.mode`.
3. **`RC_CHANNELS.chancount=0` is not proof that MAVLink overrides fail.** This project demonstrated accepted overrides while count was zero.
4. **A ROS parameter change is not necessarily a MAVLink identity change.** Verify raw packet source ID after restarting MAVROS.
5. **Never run two MAVROS instances against one USB serial device.** First attempt had old PIDs 184/185 still alive when new PID 8263 started; correct this before interpreting results.
6. **Never run multiple `/cmd_vel` publishers without arbitration.** Three `--live` bridge processes were found concurrently.
7. **RC release (`0`) is not commanded neutral (`1500`).** The project observed last reported RC1=1600 after release.
8. **The appropriate neutral RC3 value for motor-power-on operation must be validated against rover configuration.** Diagnostic RC3=1000 was used only unpowered; RC3_TRIM=1500, MIN=1100, MAX=1900. Even with 1500 inputs, do not assume skid-steer outputs cannot move until independently checked.
9. **Prearm warnings remain unresolved:** safety switch, 3D accelerometer calibration, compass calibration; do not disable checks just to arm.
10. **Failsafes are layered.** `FS_ACTION=2`/HOLD is at the Pixhawk level; the motor driver receives asynchronous Wi-Fi ROS commands. Loss of ROS/UDP/ESP32 power or stale Twist can invalidate software stop assumptions. Use an independently tested ESP32 command timeout and motor-power cutoff.
11. **Bench-only mechanical conditions:** disconnect the cutting implement, suspend wheels, maintain independent motor cutoff, keep people clear. No ground-level vehicle or mowing tests are supported by this record.
12. **Frame timestamps differ from receive time.** `/mavros/rc/out.header.stamp` was observed much older than `/mavros/state.header.stamp` in some snapshots, despite ~5 Hz fresh ROS deliveries. Use monotonic receipt-age for immediate bridge freshness, and investigate time-sync before deploying navigation.
13. **A script's `finally:` release may not run on power loss or kill -9**, and cannot reach a disconnected motor controller.
14. **State readbacks can lag**, and `timeout` can intentionally interrupt ROS CLI calls, producing Python tracebacks unrelated to FCU failure.
15. **Parameter changes are configuration changes.** Back up original values and record their state; in this session the `MODE_CH` final known value was `0`, and the GCS ID range became 254–255.

## 7. Consolidated reproducible operator procedure

This is a **diagnostic reproduction sequence**, NOT a production control recipe. Work on the bench, with the cutting tool disconnected, motor power OFF, Pixhawk disarmed, and a confirmed physical emergency cutoff. The companion document covers first-time Wi-Fi/Agent setup.

### 7.1 Confirm ROS, FCU, and single-writer status

```bash
# Raspberry Pi host:
docker exec arboreon-dev bash -lc '
  source /opt/ros/humble/setup.bash
  export ROS_DOMAIN_ID=20
  ros2 topic echo /mavros/state --once
  ros2 topic echo /mavros/rc/out --once
  ros2 topic info /cmd_vel -v
  ps -eo pid,ppid,args | grep -E "[/]mavros_node|[p]ython3 /tmp/arboreon_mavros_bridge" || true
'
```

Require **exactly one MAVROS executable**, **zero unintended `/cmd_vel` publishers**, and **disarmed**. If multiple MAVROS instances exist, stop the old launch/process before starting a replacement. Never blindly reuse PIDs from this report; they are session-specific.

### 7.2 Read parameter baseline and make backup

```bash
docker exec arboreon-dev bash -lc '
  source /opt/ros/humble/setup.bash
  export ROS_DOMAIN_ID=20
  for p in MAV_SYSID MAV_GCS_SYSID MAV_GCS_SYSID_HI MAV_OPTIONS RC_OPTIONS \
           RC_OVERRIDE_TIME MAV1_RC_CHAN FS_THR_ENABLE FS_THR_VALUE \
           FS_ACTION FS_TIMEOUT FS_GCS_ENABLE MODE_CH \
           SERVO1_FUNCTION SERVO3_FUNCTION SERVO1_TRIM SERVO3_TRIM \
           RC1_MIN RC1_TRIM RC1_MAX RC3_MIN RC3_TRIM RC3_MAX; do
    echo "=== $p ==="
    timeout 6 ros2 param get /mavros/param "$p" || true
  done
'
```

The session previously saved the 876-parameter export at `/home/pi/arboreon_pixhawk_params_backup.json` (operator context); **the current contents/presence were not revalidated in this documentation pass**. For a new operator, create and preserve a fresh native `.param` backup through a supported GCS before writing anything.

### 7.3 Source identity: read *both* ROS parameters and raw sender identity

```bash
docker exec arboreon-dev bash -lc '
  source /opt/ros/humble/setup.bash
  export ROS_DOMAIN_ID=20
  ros2 param get /mavros system_id
  ros2 param get /mavros component_id
  ros2 param get /mavros_node tgt_system
  ros2 param get /mavros_node tgt_component
  ros2 param get /mavros/param MAV_SYSID
  ros2 param get /mavros/param MAV_GCS_SYSID
  ros2 param get /mavros/param MAV_GCS_SYSID_HI
'
```

Then run **Appendix D** (passive outgoing sink monitor). Treat raw SYSID as definitive for the actual transmitted message; an `Integer value is: 254` reading is not sufficient.

### 7.4 Rebuild a custom launch without altering `/opt/ros/humble`

Use **Appendix E**. It copies the installed `node.launch`, adds an identity YAML include to its MAVROS node, copies `apm.launch` to point at the custom node launch, and validates the launch argument list. It preserves the standard plugins and FCU target. Be aware that the example uses `/tmp` and is **not persistent** across container recreation. A permanent deployment requires a host-mounted directory and matching updated file references. The operator also copied files to `/root/arboreon/mavros/`, but those copies retained references to `/tmp` and so were *not* a fully self-contained persistent setup.

**Controlled restart:** Ensure all bridges are stopped; disarm; remove motor power; stop the existing MAVROS parent and child and confirm they disappeared; only then run:

```bash
# In a terminal kept open on Pi:
docker exec -it arboreon-dev bash -lc '
  source /opt/ros/humble/setup.bash
  export ROS_DOMAIN_ID=20
  ros2 launch /tmp/arboreon_apm.launch fcu_url:=/dev/ttyACM0:115200
'
```

Do NOT use the original `ros2 launch mavros apm.launch ...` at the same time. If a supervisor respawns it, fix that startup policy first. Confirm only one `/opt/ros/humble/lib/mavros/mavros_node` process remains, state.connected=true, armed=false, and outbound heartbeat `SYSID=254`.

### 7.5 Determine whether physical RC channels exist

Run **Appendix F** for passive raw MAVLink decoding. In this session, `chancount=0`, with RC1/RC3 payload numbers. It explains the empty ROS `RCIn` result; it does **not** prevent tests of an authorized virtual RC input.

### 7.6 Verify accepted override with motor power OFF

Run **Appendix G** (bounded source-ID and RC1 test), but **only** on a secured disarmed bench. The sample uses RC1 1600 and RC3 1000 to reproduce the **historical diagnostic**, not to establish a safe operating neutral. It refuses non-disarmed/non-HOLD state. After the test, run **Appendix H** to command RC1 back to 1500 and verify, because releasing alone did not return the display to neutral in this session.

### 7.7 Validate radio failsafe recovery and mode-change logic

Run **Appendix I** to stream neutral RC while monitoring failsafe state (disarmed HOLD). The successful operator log included `Radio Failsafe Cleared`, status 5->3. Run **Appendix J** for an 8-second passive status read after release. **Appendix K** can request MANUAL after status returns to 3, while holding a neutral stream, remaining disarmed. When it ends, observe the FCU state and note that subsequent HOLD/CRITICAL may recur. **Do not arm, feed powered motors, or launch `/cmd_vel` live during these tests.**

### 7.8 Stop and capture evidence

End with `/mavros/state`, `/mavros/rc/out`, `/cmd_vel` publishers, active MAVROS processes and any `/mavros/statustext/recv` alarms. Use session timestamps and include the FCU firmware version, saved `.param` file, source scripts and source IDs in a reproducible issue report.

## 8. Troubleshooting matrix

| Symptom | Actual finding in this project | Better diagnostic |
|---|---|---|
| `ros2: command not found` | ROS not sourced inside Docker shell | `source /opt/ros/humble/setup.bash`; domain 20 |
| `/mavros/rc/in` prints `array('H')` / `[]` | Raw `RC_CHANNELS.chancount=0` | Raw MAVLink message 65 decoder |
| RC overrides appear to have no effect | Source sender SYSID 1 not authorized when configured range 254–255 | Observe outgoing raw message 70 on `/uas1/mavlink_sink` |
| `ros2 param get /mavros system_id` says 254 but outgoing stays 1 | Runtime parameter changed but sender identity did not update | Restart with initialization-time YAML, observe actual raw SYSID |
| `ParamSet` service call waits | Service advertised with multiple types and CLI resolution inconsistent | Use verified `ros2 param set /mavros/param ...`; verify each readback |
| `ros2 param describe --verbose` errors | ROS 2 Humble CLI version lacks `--verbose` | Use `ros2 param describe /mavros system_id` |
| `ros2 launch --show-args` passes but source unchanged | Argument display is not an actual serial/wire test | Observe outbound raw MAVLink after single-instance restart |
| `kill -INT 184` does not stop MAVROS | Old launch and child remained alive | Verify PIDs; terminate gracefully; check supervisor before restart |
| Newly started MAVROS sees FCU but two processes exist | Contested USB, duplicate ROS nodes | Stop old instance; require one `/mavros_node` process |
| `mode_sent=True` but mode=HOLD | Command dispatched, but FCU remained/reverted HOLD | Monitor STATE and STATUSTEXT under continuous neutral RC |
| `system_status=5` | MAV_STATE_CRITICAL; explicit `Radio failsafe on` observed | StatusText plus sustained-RC diagnostic |
| Release RC1 but readback stays 1600 | Release does not command a neutral value with no receiver | Explicit RC1 1500 then verify; independent motor inhibit still required |
| MODE_CH=8 | RC8 selector assigned; switching to 0 alone did not solve HOLD | Distinguish mode-selector effect from radio failsafe |
| `ExternalShutdownException` | CLI interrupted by `timeout` | Distinguish intended timeout from actual connection loss |
| Servo header appears old although 5 Hz stream received | Timestamp/time-sync discrepancy | Monotonic receipt time; later investigate TIMESYNC |
| No PWM differential even with override | Tests so far were HOLD and/or disarmed | Do not infer servo mixing failure; future supervised armed bench test only after prearm fixes |

## 9. Remaining engineering work and proposed experimental acceptance criteria

These items are **NOT TESTED** in the current report.

### 9.1 Prearm readiness and hardware

Resolve `PreArm: Hardware safety switch`, `PreArm: 3D Accel calibration needed` and `PreArm: Compass not calibrated` using official ArduPilot/ArduDeck procedures. Confirm physical motor cutoff, independent ESP32 watchdog behavior during lost `/cmd_vel`, link failure and process crash. Record `MODE_CH=0` as the current setting and decide intentionally whether a physical RC mode selector will be required.

### 9.2 Bench differential servo-output test, motor power OFF

Prerequisites: completed calibrations and arming checks; reviewed throttle/steering mapping, reboot/start behavior; single MAVROS, zero other motor publishers; verified neutral input and emergency-stop handling. Proposed acceptance outcomes: FCU remains controllable while transmitting neutral virtual RC; outputs 1/3 are 1500 at baseline; a *brief, bounded, supervised* non-neutral request produces expected **different** channel values; explicit neutral and disarm return both outputs to 1500; HOLD and radio failsafe suppress movement outputs. Do not connect powered wheels until all are measured.

### 9.3 Controlled powered wheel test

Only later, with suspended wheels, cutter disconnected, independent cutoff, verified local motor watchdog, a *single* supervised bridge and a second person or accessible stop, repeat small pulses and verify actual wheel direction. Run fault-injection tests for MAVROS process exit, ROS domain mismatch, UDP Agent loss, Wi-Fi loss, USB unplug and actual ESP32 control timeout. The current `--live` bridge is a **bench prototype**, not a rated safety controller.

### 9.4 Navigation readiness

No GPS fix, position injection, RTK, autonomous mission, orchard traversal, or centimeter-scale ground navigation is proven. Integrate position estimation and appropriate GPS/odometry fusion before `AUTO` or `GUIDED` mission claims.

## 10. Source provenance, artifacts and external references

**Primary evidence:** operator command/results in the ARBOREON investigation conversation on 29 October 2026, including logs reproduced here. **Companion context:** supplied 76 KB handover entitled *ARBOREON — Complete Raspberry Pi 5, Yahboom MicroROS V2, Pixhawk Cube Black, MAVROS and ArduDeck Integration Handover*, including its historical superseded Appendix A. The companion's initial claim that 73/74 had not been applied was accurate at its earlier snapshot; this follow-up verifies that they **were** subsequently applied. The companion's claims about first motor movement apply to a **direct ROS command**, not Pixhawk-driven movement.

**Locally recovered source files:** `arboreon_mavros_bridge.py`, `arboreon_mavros_bridge_live.py`, `test_bridge_math.py` from the conversation's attached working directory. All three are included below as source appendices. The later quick interactive diagnostic snippets are reproduced as cleaned, runnable versions.

**Useful official starting points** (check current firmware/version details before reuse):

- ArduPilot Rover: https://ardupilot.org/rover/
- ArduPilot servo function/output mapping: https://ardupilot.org/rover/docs/common-rcoutput-mapping.html
- ArduPilot RC input over MAVLink: https://ardupilot.org/dev/docs/mavlink-rcinput.html
- MAVLink common messages: https://mavlink.io/en/messages/common.html
- MAVROS: https://github.com/mavlink/mavros
- ROS 2 Humble: https://docs.ros.org/en/humble/
- micro-ROS Agent: https://github.com/micro-ROS/micro-ROS-Agent
- Yahboom MicroROS V2: https://www.yahboom.net/study/MicroROS-V2

The preceding report remains the authoritative record for Raspberry Wi-Fi, physical hardware, early ROS bring-up, initial Yahboom wheel test, and ArduDeck setup. The present report should be read as an **addendum that supersedes the predecessor's older limitations concerning servo assignments, MAVROS source identity, RC virtual acceptance, and disarmed MANUAL transition**, not as evidence of completed autonomous motion.

---

# Appendix — Executed / recovered scripts and commands

The appendix preserves the most consequential experimental scripts. Use them only under the stated bench restrictions. `reconstructed` means formatted from the executed code and outputs; descriptions of results are historical and are not assurances for a different robot or firmware.

## A. Original read-only differential PWM bridge

**RECOVERED SOURCE.** Read-only, no motor-command publisher; the original file can contain experimental tuning and should be audited before reuse.

Source: `arboreon_mavros_bridge.py`

```python
#!/usr/bin/env python3
"""ARBOREON Cube Black PWM -> differential Twist bridge.

Default is read-only. Actuation is deliberately disabled in this commissioning
build until an independent motor-power interlock and MCU-side loss-of-command
watchdog have been verified. Never equate host-side zero publishing with an E-stop.
"""
import math
import time
import rclpy
from rclpy.node import Node
from mavros_msgs.msg import State, RCOut

PWM_MIN = 1100
PWM_TRIM = 1500
PWM_MAX = 1900
PWM_DEADBAND = 15
MAX_WHEEL_SPEED = 0.10   # theoretical m/s, NOT calibrated
WHEEL_SEPARATION = 0.25  # example only; measure robot
PWM_MAX_AGE_S = 0.60
STATE_MAX_AGE_S = 2.50  # diagnostic only; not certified for motor safety
ALLOWED_MODES = frozenset({'MANUAL', 'STEERING', 'ACRO', 'GUIDED', 'AUTO'})


def pwm_to_fraction(pwm):
    if not isinstance(pwm, (int, float)) or not math.isfinite(pwm):
        raise ValueError('Non-finite PWM')
    if not PWM_MIN <= pwm <= PWM_MAX:
        raise ValueError(f'PWM outside [{PWM_MIN}, {PWM_MAX}]: {pwm}')
    delta = pwm - PWM_TRIM
    if abs(delta) <= PWM_DEADBAND:
        return 0.0
    return max(-1.0, min(1.0, delta / (PWM_MAX - PWM_TRIM)))


def convert_pwm(left, right):
    v_left = MAX_WHEEL_SPEED * pwm_to_fraction(left)
    v_right = MAX_WHEEL_SPEED * pwm_to_fraction(right)
    linear = (v_left + v_right) / 2.0
    angular = (v_right - v_left) / WHEEL_SEPARATION
    return linear, angular


def evaluate(state, state_age, pwm, pwm_age):
    if state is None or pwm is None:
        return 'WAITING_FOR_MAVROS', 0.0, 0.0
    if state_age > STATE_MAX_AGE_S or pwm_age > PWM_MAX_AGE_S:
        return 'STALE_DATA', 0.0, 0.0
    if not state.connected:
        return 'FCU_DISCONNECTED', 0.0, 0.0
    if not state.armed:
        return 'DISARMED', 0.0, 0.0
    if state.mode not in ALLOWED_MODES:
        return f'MODE_BLOCKED:{state.mode}', 0.0, 0.0
    if len(pwm.channels) < 3:
        return 'INVALID_CHANNEL_COUNT', 0.0, 0.0
    try:
        linear, angular = convert_pwm(pwm.channels[0], pwm.channels[2])
    except ValueError:
        return 'INVALID_PWM', 0.0, 0.0
    return 'CANDIDATE_ONLY', linear, angular


class Bridge(Node):
    def __init__(self):
        super().__init__('arboreon_pwm_bridge_observer')
        self.state = None
        self.pwm = None
        self.state_received = None
        self.pwm_received = None
        self.create_subscription(State, '/mavros/state', self.on_state, 10)
        self.create_subscription(RCOut, '/mavros/rc/out', self.on_pwm, 10)
        self.create_timer(0.5, self.report)
        self.get_logger().info('READ-ONLY: no /cmd_vel publisher is created')

    def on_state(self, msg):
        self.state = msg
        self.state_received = time.monotonic()

    def on_pwm(self, msg):
        self.pwm = msg
        self.pwm_received = time.monotonic()

    def report(self):
        now = time.monotonic()
        sa = math.inf if self.state_received is None else now - self.state_received
        pa = math.inf if self.pwm_received is None else now - self.pwm_received
        status, linear, angular = evaluate(self.state, sa, self.pwm, pa)
        armed = self.state.armed if self.state is not None else '?'
        mode = self.state.mode if self.state is not None else '?'
        left = self.pwm.channels[0] if self.pwm and len(self.pwm.channels) >= 3 else '?'
        right = self.pwm.channels[2] if self.pwm and len(self.pwm.channels) >= 3 else '?'
        print(f'{status} | PWM L={left} R={right} | v={linear:+.3f} m/s '
              f'w={angular:+.3f} rad/s | armed={armed} mode={mode} '
              f'age(state,pwm)=({sa:.2f},{pa:.2f})s | OBSERVE ONLY', flush=True)


def main():
    rclpy.init()
    node = Bridge()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == '__main__':
    main()
```

## B. Original pure-math test suite

**RECOVERED SOURCE.** The observed original run passed seven arithmetic tests.

Source: `test_bridge_math.py`

```python
"""Pure-math tests (no ROS, no motor commands)."""
import pathlib, ast

# Extract independent pure functions/constants without importing ROS.
source = pathlib.Path(__file__).with_name('arboreon_mavros_bridge.py').read_text()
tree = ast.parse(source)
keep = {'PWM_MIN', 'PWM_TRIM', 'PWM_MAX', 'PWM_DEADBAND', 'MAX_WHEEL_SPEED', 'WHEEL_SEPARATION'}
statements = [n for n in tree.body if isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id in keep for t in n.targets)]
statements += [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name in ('pwm_to_fraction', 'convert_pwm')]
ns = {'math': __import__('math')}
exec(compile(ast.Module(body=statements, type_ignores=[]), '<math-only>', 'exec'), ns)
convert = ns['convert_pwm']
for l, r, v, w in [(1500,1500,0,0),(1600,1600,.025,0),(1400,1400,-.025,0),(1400,1600,0,.2),(1600,1400,0,-.2)]:
    actual = convert(l,r)
    assert abs(actual[0]-v)<1e-8 and abs(actual[1]-w)<1e-8, (l,r,actual)
for l,r in [(0,1500),(2000,1500)]:
    try: convert(l,r)
    except ValueError: pass
    else: raise AssertionError('Invalid PWM accepted')
print('7 math tests passed; no ROS motor commands sent')
```

## C. Original guarded live PWM-to-Twist bridge

**RECOVERED SOURCE.** Default dry-run; `--live` publishes to real motors. Included for documentation, NOT permission to run with powered actuators.

Source: `arboreon_mavros_bridge_live.py`

```python
#!/usr/bin/env python3
"""ARBOREON PWM -> Twist supervised bench bridge (ROS 2 Humble).

Default DRY RUN; --live must be explicitly supplied. This is NOT a certified
safety controller. The ESP32 must independently time out commands and a motor
power cutoff must be available. Never run with a cutter attached.
"""
import argparse
import math
import time
import rclpy
from rclpy.node import Node
from mavros_msgs.msg import State, RCOut
from geometry_msgs.msg import Twist

TRIM, RANGE = 1500, 400
DEADBAND = 15
MAX_WHEEL_MPS = 0.03  # conservative command scale; not calibrated
WHEELBASE_M = 0.25    # placeholder, measure wheel separation
PWM_TIMEOUT = 0.50   # PWM observed at 5 Hz
STATE_TIMEOUT = 1.80 # state observed ~1 Hz
ALLOWED_MODES = {'MANUAL'}  # add a mode only after testing its semantics


def velocity(left, right):
    if not all(isinstance(x, (int, float)) and math.isfinite(x) and 1100 <= x <= 1900
               for x in (left, right)):
        raise ValueError('Invalid PWM')
    def wheel(x):
        d = x - TRIM
        return 0.0 if abs(d) <= DEADBAND else MAX_WHEEL_MPS * d / RANGE
    vl, vr = wheel(left), wheel(right)
    return (vl + vr) / 2, (vr - vl) / WHEELBASE_M


class Bridge(Node):
    def __init__(self, live):
        super().__init__('arboreon_supervised_pwm_bridge')
        self.live = live
        self.state = None
        self.pwm = None
        self.ts_state = None
        self.ts_pwm = None
        self.saw_disarmed = False
        self.fault_latched = False
        self.previous_armed = False
        self.last_report = 0
        self.pub = self.create_publisher(Twist, '/cmd_vel', 10) if live else None
        self.create_subscription(State, '/mavros/state', self.on_state, 10)
        self.create_subscription(RCOut, '/mavros/rc/out', self.on_pwm, 10)
        self.create_timer(0.1, self.tick)
        self.get_logger().warn('LIVE /cmd_vel ENABLED' if live else 'DRY RUN - no /cmd_vel publisher')

    def on_state(self, msg):
        self.state = msg
        self.ts_state = time.monotonic()
        if not msg.armed:
            self.saw_disarmed = True
            self.fault_latched = False  # deliberate disarm required after detected fault

    def on_pwm(self, msg):
        self.pwm = msg
        self.ts_pwm = time.monotonic()

    def tick(self):
        now = time.monotonic()
        reason = 'READY'
        v, w = 0.0, 0.0
        if not self.saw_disarmed:
            reason = 'STARTUP_INTERLOCK: must observe disarmed once'
        elif self.fault_latched:
            reason = 'FAULT_LATCHED: disarm before re-enabling'
        elif self.state is None or self.pwm is None:
            reason = 'WAITING_FOR_DATA'
        elif now - self.ts_state > STATE_TIMEOUT or now - self.ts_pwm > PWM_TIMEOUT:
            reason = 'STALE_DATA'
        elif not self.state.connected:
            reason = 'FCU_DISCONNECTED'
        elif not self.state.armed:
            reason = 'DISARMED'
        elif self.state.mode not in ALLOWED_MODES:
            reason = 'MODE_BLOCKED:' + self.state.mode
        elif len(self.pwm.channels) < 3:
            reason = 'CHANNELS_MISSING'
        else:
            try:
                v, w = velocity(self.pwm.channels[0], self.pwm.channels[2])
            except ValueError:
                reason = 'INVALID_PWM'

        if reason in ('STALE_DATA', 'FCU_DISCONNECTED', 'CHANNELS_MISSING', 'INVALID_PWM'):
            self.fault_latched = True
            v, w = 0.0, 0.0
        if self.pub is not None:
            msg = Twist()
            msg.linear.x, msg.angular.z = v, w
            self.pub.publish(msg)
        if now - self.last_report >= 1:
            left = self.pwm.channels[0] if self.pwm and len(self.pwm.channels) > 2 else '?'
            right = self.pwm.channels[2] if self.pwm and len(self.pwm.channels) > 2 else '?'
            print(f'{"LIVE" if self.live else "DRY"} {reason} '
                  f'L={left} R={right} v={v:+.3f} w={w:+.3f} '
                  f'armed={getattr(self.state, "armed", "?")} '
                  f'mode={getattr(self.state, "mode", "?")}', flush=True)
            self.last_report = now

    def stop(self):
        if self.pub is not None:
            for _ in range(10):
                self.pub.publish(Twist())
                time.sleep(0.05)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--live', action='store_true', help='Publish to actual /cmd_vel')
    args = ap.parse_args()
    rclpy.init()
    node = Bridge(args.live)
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.stop()  # Best effort only; loss of Wi-Fi can prevent delivery
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == '__main__':
    main()
```

## D. Passive outgoing MAVLink source-ID inspection (RECONSTRUCTED, EXECUTED)

This is the **read-only** check that showed `SYSID=254` for messages 0, 2 and 111 after the custom launch. When the operator had previously added an RC sender, the same sink topic showed RC override message 70 from source 1, revealing the mismatch.

```python
#!/usr/bin/env python3
"""Observe outgoing MAVLink source IDs for five seconds. No messages sent."""
import time
import rclpy
from mavros_msgs.msg import Mavlink
from rclpy.qos import qos_profile_sensor_data

rclpy.init()
node = rclpy.create_node('arboreon_sysid_verify')
seen = {}

def callback(msg):
    key = (msg.msgid, msg.sysid, msg.compid)
    seen[key] = seen.get(key, 0) + 1

sub = node.create_subscription(
    Mavlink, '/uas1/mavlink_sink', callback, qos_profile_sensor_data)
try:
    end = time.monotonic() + 5
    while time.monotonic() < end:
        rclpy.spin_once(node, timeout_sec=0.1)
finally:
    node.destroy_node()
    rclpy.shutdown()

for (msgid, sysid, compid), count in sorted(seen.items()):
    print(f'MSG_ID={msgid} SYSID={sysid} COMPID={compid} COUNT={count}')
if 254 in {sysid for _, sysid, _ in seen}:
    print('SYSID 254 OBSERVED')
else:
    print('SYSID 254 NOT OBSERVED (or no outgoing data)')
```

Launch from Raspberry host after saving it inside the container:

```bash
docker exec arboreon-dev bash -lc '
  source /opt/ros/humble/setup.bash
  export ROS_DOMAIN_ID=20
  python3 /tmp/arboreon_sysid_verify.py
'
```

To run a standalone Python script from this document, save its fenced contents as the named `.py` on the Raspberry host, then copy it inside Docker with `docker cp <local.py> arboreon-dev:/tmp/<name>.py`. The source code in the appendix is not automatically installed by this report.

## E. Custom MAVROS XML launch and identity YAML generator (RECONSTRUCTED, EXECUTED)

The executed sequence first wrote a YAML file, then generated two launch files. A second pass replaced the custom node-launch with one derived from the untouched package original and added a YAML include. This version represents that **final validated arrangement**. It deliberately retains the exact `/tmp` paths used in the session, and validates the `apm.launch` include before proceeding. It creates files but does **not** start MAVROS.

```python
#!/usr/bin/env python3
"""Build ARBOREON MAVROS launch files without editing installed ROS packages."""
from pathlib import Path
import xml.etree.ElementTree as ET
import yaml

pkg = Path('/opt/ros/humble/share/mavros/launch')
node_source = pkg / 'node.launch'
apm_source = pkg / 'apm.launch'
identity = Path('/tmp/arboreon_mavros_identity.yaml')
node_target = Path('/tmp/arboreon_node.launch')
apm_target = Path('/tmp/arboreon_apm.launch')

# IMPORTANT: system_id is the companion sender; MAV_SYSID is the FCU vehicle ID.
identity.write_text('''/mavros:
  ros__parameters:
    system_id: 254
    component_id: 191
    target_system_id: 1
    target_component_id: 1
''')

# Preserve standard launch settings and plugin-loading order; add UAS identity.
tree = ET.parse(node_source)
node = next(e for e in tree.getroot().iter('node')
            if e.get('exec') == 'mavros_node')
ET.SubElement(node, 'param', {'from': str(identity)})
tree.write(node_target, encoding='unicode')

original_include = '$(find-pkg-share mavros)/launch/node.launch'
content = apm_source.read_text()
assert original_include in content, 'Unexpected upstream APM launch format'
apm_target.write_text(content.replace(original_include, str(node_target)))

parsed = yaml.safe_load(identity.read_text())
assert parsed['/mavros']['ros__parameters']['system_id'] == 254
assert str(node_target) in apm_target.read_text()
ET.parse(node_target)
ET.parse(apm_target)
print('CONFIGURATION VALIDATED')
print(identity, node_target, apm_target, sep='\n')
```

After saving it inside Docker as `/tmp/build_arboreon_mavros_launch.py`, execute and show arguments:

```bash
docker exec arboreon-dev bash -lc '
  source /opt/ros/humble/setup.bash
  export ROS_DOMAIN_ID=20
  python3 /tmp/build_arboreon_mavros_launch.py
  timeout 10 ros2 launch /tmp/arboreon_apm.launch --show-args
'
```

**Important naming nuance:** The ROS 2 parameters `target_system_id` and `target_component_id` in the UAS YAML do not substitute for `tgt_system` / `tgt_component` in the MAVROS executable launch. The FCU destination remained 1/1 in the standard `apm.launch` arguments. The actual effective outbound 254 identity was verified **after** starting the generated launcher.

**Controlled restart procedure (only on disarmed, unpowered bench):**

```bash
# Inspect, never assume historical PID values are current:
docker exec arboreon-dev bash -lc '
  ps -eo pid,ppid,args | grep -E "[/]mavros_node|[r]os2 launch mavros|[r]os2 launch /tmp/arboreon_apm.launch" || true
'
# Terminate the original process using its CURRENT PIDs and verify it exited.
# If any MAVROS node remains, DO NOT start a second one.
# Then, and only then:
docker exec -it arboreon-dev bash -lc '
  source /opt/ros/humble/setup.bash
  export ROS_DOMAIN_ID=20
  ros2 launch /tmp/arboreon_apm.launch fcu_url:=/dev/ttyACM0:115200
'
```

**What actually went wrong in the historical session:** the original processes at 184 and 185 survived `kill -INT 184` after 3 seconds, yet the new launcher was started anyway. This temporarily introduced two MAVROS instances. The old pair was later stopped; the verified final process was PID 8263. Future operators must enforce a no-duplicates gate.

## F. Passive raw-MAVLink `RC_CHANNELS` decoder (RECONSTRUCTED, EXECUTED)

The key result was `chancount=0`, `rssi=255`, and diagnostic channel payload `[1500,1500,1000,1500,...]`, explaining empty `/mavros/rc/in` without proving override failure. The code reconstructs only the observed message 65 fields. It handles padded `payload64` while respecting actual `len` when available.

```python
#!/usr/bin/env python3
import time
import struct
import rclpy
from mavros_msgs.msg import Mavlink
from rclpy.qos import qos_profile_sensor_data

rclpy.init()
node = rclpy.create_node('arboreon_rc_raw_decode')
seen = 0

def callback(msg):
    global seen
    if msg.msgid != 65 or msg.sysid != 1:
        return
    data = b''.join(int(x).to_bytes(8, 'little') for x in msg.payload64)
    if len(data) < 42:
        return
    channels = [struct.unpack_from('<H', data, 4 + 2*i)[0] for i in range(18)]
    chancount, rssi = data[40], data[41]
    seen += 1
    print(f'RC_CHANNELS #{seen} chancount={chancount} '
          f'rssi={rssi} channels={channels}', flush=True)

sub = node.create_subscription(Mavlink, '/uas1/mavlink_source',
                               callback, qos_profile_sensor_data)
try:
    end = time.monotonic() + 4
    while time.monotonic() < end:
        rclpy.spin_once(node, timeout_sec=0.1)
finally:
    node.destroy_node()
    rclpy.shutdown()
```

## G. Two-second RC1 override acceptance and outgoing-source validation (RECONSTRUCTED, EXECUTED)

**Bench constraints: motor power OFF; Pixhawk disarmed in HOLD; no other override sender/bridge.** This reproduces the successful experiment in which **RC1 changed 1500 → 1600 while `chancount` stayed 0**. The diagnostic `RC3=1000` matches the recorded test but is **not approved as powered neutral**. The command uses the real asynchronous `SetMode`/state workflow only in Appendix K; this probe does not change mode.

```python
#!/usr/bin/env python3
import time
import struct
import rclpy
from mavros_msgs.msg import Mavlink, OverrideRCIn, State
from rclpy.qos import qos_profile_sensor_data

rclpy.init()
node = rclpy.create_node('arboreon_rc_254_test')
state = None
rc = None
tx_ids = {}
rc_count = 0

def state_cb(msg):
    global state
    state = msg

def rx_cb(msg):
    global rc, rc_count
    if msg.msgid != 65 or msg.sysid != 1:
        return
    data = b''.join(int(x).to_bytes(8, 'little') for x in msg.payload64)
    if len(data) >= 42:
        rc = (struct.unpack_from('<H', data, 4)[0],
              struct.unpack_from('<H', data, 8)[0], data[40])
        rc_count += 1

def tx_cb(msg):
    if msg.msgid == 70:
        key = (msg.sysid, msg.compid)
        tx_ids[key] = tx_ids.get(key, 0) + 1

node.create_subscription(State, '/mavros/state', state_cb, qos_profile_sensor_data)
node.create_subscription(Mavlink, '/uas1/mavlink_source', rx_cb,
                         qos_profile_sensor_data)
node.create_subscription(Mavlink, '/uas1/mavlink_sink', tx_cb,
                         qos_profile_sensor_data)
pub = node.create_publisher(OverrideRCIn, '/mavros/rc/override', 10)

probe = OverrideRCIn()
probe.channels = [65535]*18
probe.channels[0] = 1600  # RC1 steering -- unpowered FCU experiment only
probe.channels[2] = 1000  # RC3 recorded test value -- NOT powered neutral
release = OverrideRCIn()
release.channels = [0]*18
neutral = OverrideRCIn()
neutral.channels = [65535]*18
neutral.channels[0] = 1500  # explicit neutral before release

try:
    deadline = time.monotonic() + 5
    while (state is None or rc is None) and time.monotonic() < deadline:
        rclpy.spin_once(node, timeout_sec=0.1)
    if not (state and rc and state.connected and not state.armed
            and state.mode == 'HOLD'):
        print('ABORTED: state invalid or no telemetry')
    else:
        print('BEFORE:', rc)
        start = time.monotonic()
        next_report = start
        while time.monotonic() - start < 2:
            rclpy.spin_once(node, timeout_sec=0.05)
            if not state.connected or state.armed or state.mode != 'HOLD':
                print('ABORTED: unexpected FCU state')
                break
            pub.publish(probe)
            now = time.monotonic()
            if now >= next_report:
                print('DURING:', rc, flush=True)
                next_report = now + 0.5
finally:
    # Improved reproduction: return RC1 to 1500 explicitly before releasing.
    for _ in range(20):
        pub.publish(neutral)
        rclpy.spin_once(node, timeout_sec=0.05)
    print('RC AFTER EXPLICIT NEUTRAL:', rc)
    for _ in range(10):
        pub.publish(release)
        rclpy.spin_once(node, timeout_sec=0.05)
    print('OUTGOING OVERRIDES:', tx_ids)
    print('RC MESSAGES RECEIVED:', rc_count)
    print('OVERRIDE RELEASED')
    node.destroy_node()
    rclpy.shutdown()
```

**Historical difference:** the original executed diagnostic went straight from `probe` to `release` and *did not* include the explicit-neutral step. This cleaned-up reproduction adds it because the next test proved that release alone left reported RC1 at 1600. Keep the original experimental observation and the improved reproduction separate.

## H. Explicit RC1 return to neutral (RECONSTRUCTED, EXECUTED)

The exact experimental purpose was to distinguish `release` from `neutral`. Expected logged outcome: RC1 1600 → 1500 while disarmed in HOLD. The script leaves RC3 unchanged (65535 = ignore), then releases all channels.

```python
#!/usr/bin/env python3
import time
import struct
import rclpy
from mavros_msgs.msg import OverrideRCIn, Mavlink, State
from rclpy.qos import qos_profile_sensor_data

rclpy.init()
node = rclpy.create_node('arboreon_restore_rc1')
state, rc1 = None, None

def on_state(msg):
    global state
    state = msg

def on_raw(msg):
    global rc1
    if msg.msgid == 65 and msg.sysid == 1:
        data = b''.join(int(x).to_bytes(8, 'little') for x in msg.payload64)
        if len(data) >= 6:
            rc1 = struct.unpack_from('<H', data, 4)[0]

node.create_subscription(State, '/mavros/state', on_state,
                         qos_profile_sensor_data)
node.create_subscription(Mavlink, '/uas1/mavlink_source', on_raw,
                         qos_profile_sensor_data)
pub = node.create_publisher(OverrideRCIn, '/mavros/rc/override', 10)
neutral = OverrideRCIn()
neutral.channels = [65535]*18
neutral.channels[0] = 1500
release = OverrideRCIn()
release.channels = [0]*18

try:
    deadline = time.monotonic()+5
    while (state is None or rc1 is None) and time.monotonic() < deadline:
        rclpy.spin_once(node, timeout_sec=0.1)
    if not (state and state.connected and not state.armed and
            state.mode == 'HOLD' and rc1 is not None):
        print('ABORTED: unsafe/unknown state')
    else:
        print('RC1 BEFORE:', rc1)
        start = time.monotonic()
        while time.monotonic() - start < 3:
            rclpy.spin_once(node, timeout_sec=0.05)
            if not state.connected or state.armed or state.mode != 'HOLD':
                print('ABORTED: state changed')
                break
            pub.publish(neutral)
        print('RC1 AFTER NEUTRAL:', rc1)
finally:
    for _ in range(10):
        pub.publish(release)
        rclpy.spin_once(node, timeout_sec=0.05)
    print('RC1 FINAL OBSERVED:', rc1)
    print('OVERRIDE RELEASED')
    node.destroy_node()
    rclpy.shutdown()
```

## I. Five-second continuous neutral RC and failsafe-clear monitoring (RECONSTRUCTED, EXECUTED)

This experiment produced `Radio Failsafe Cleared` and `system_status=5 -> 3`, while mode stayed HOLD. It sends no steering or throttle motion request; the FCU is **required to be disarmed in HOLD**.

```python
#!/usr/bin/env python3
import time
import rclpy
from mavros_msgs.msg import OverrideRCIn, State, StatusText
from rclpy.qos import qos_profile_sensor_data

rclpy.init()
node = rclpy.create_node('arboreon_failsafe_recovery_test')
state = None
alerts = []

def on_state(msg):
    global state
    state = msg

def on_alert(msg):
    if 'failsafe' in msg.text.lower():
        alerts.append(msg.text)
        print('ALERT:', msg.text, flush=True)

node.create_subscription(State, '/mavros/state', on_state,
                         qos_profile_sensor_data)
node.create_subscription(StatusText, '/mavros/statustext/recv', on_alert,
                         qos_profile_sensor_data)
pub = node.create_publisher(OverrideRCIn, '/mavros/rc/override', 10)
neutral = OverrideRCIn()
neutral.channels = [65535]*18
neutral.channels[0] = 1500
neutral.channels[2] = 1500
release = OverrideRCIn()
release.channels = [0]*18

try:
    deadline = time.monotonic()+5
    while state is None and time.monotonic() < deadline:
        rclpy.spin_once(node, timeout_sec=0.1)
    if not (state and state.connected and not state.armed and
            state.mode == 'HOLD'):
        print('ABORTED: FCU not disarmed in HOLD')
    else:
        print('START:', state.mode, state.system_status)
        start = time.monotonic()
        next_print = start
        while time.monotonic()-start < 5:
            rclpy.spin_once(node, timeout_sec=0.05)
            if not state.connected or state.armed or state.mode != 'HOLD':
                print('ABORTED: unexpected FCU state')
                break
            pub.publish(neutral)
            now = time.monotonic()
            if now >= next_print:
                print('STATE:', state.mode, state.system_status, flush=True)
                next_print = now + 1
finally:
    for _ in range(10):
        pub.publish(release)
        rclpy.spin_once(node, timeout_sec=0.05)
    print('ALERTS:', alerts)
    print('FINAL:', (state.mode, state.system_status) if state else None)
    print('OVERRIDE RELEASED')
    node.destroy_node()
    rclpy.shutdown()
```

## J. Passive failsafe follow-up (RECONSTRUCTED, EXECUTED)

This script **does not** publish overrides and runs for eight seconds. The operator observed all status values `3` after one explicit release; the later loss-of-stream observation following MANUAL was different and ended in status 5/HOLD.

```python
#!/usr/bin/env python3
import time
import rclpy
from mavros_msgs.msg import State, StatusText
from rclpy.qos import qos_profile_sensor_data

rclpy.init()
node = rclpy.create_node('arboreon_failsafe_monitor')
state, alerts = None, []

def on_state(msg):
    global state
    state = msg

def on_alert(msg):
    if 'failsafe' in msg.text.lower():
        alerts.append(msg.text)
        print('ALERT:', msg.text, flush=True)

node.create_subscription(State, '/mavros/state', on_state,
                         qos_profile_sensor_data)
node.create_subscription(StatusText, '/mavros/statustext/recv', on_alert,
                         qos_profile_sensor_data)
start = time.monotonic()
next_report = start
try:
    while time.monotonic()-start < 8:
        rclpy.spin_once(node, timeout_sec=0.1)
        now = time.monotonic()
        if state is not None and now >= next_report:
            print(f't={now-start:.1f}s mode={state.mode} '
                  f'armed={state.armed} status={state.system_status}',
                  flush=True)
            next_report = now + 1
finally:
    print('ALERTS:', alerts)
    node.destroy_node()
    rclpy.shutdown()
```

## K. Maintain neutral RC, clear failsafe, request MANUAL (RECONSTRUCTED, EXECUTED)

This is the **successful disarmed mode-change experiment**, not a motor test. It publishes RC1=1500, RC3=1500, waits for `system_status==3`, sends one asynchronous `SetMode(MANUAL)` and continues neutral RC while observing the response and `StatusText`. On exit, channels are released. Historical output showed `Radio Failsafe Cleared` followed by `mode=MANUAL`, `system_status=4`; later without the stream it reverted to HOLD, status 5.

```python
#!/usr/bin/env python3
import time
import rclpy
from mavros_msgs.msg import OverrideRCIn, State, StatusText
from mavros_msgs.srv import SetMode
from rclpy.qos import qos_profile_sensor_data

rclpy.init()
node = rclpy.create_node('arboreon_manual_neutral_test')
state = None
alerts = []

def state_cb(msg):
    global state
    state = msg

def alert_cb(msg):
    alerts.append(msg.text)
    print('ARDUPILOT:', msg.text, flush=True)

node.create_subscription(State, '/mavros/state', state_cb,
                         qos_profile_sensor_data)
node.create_subscription(StatusText, '/mavros/statustext/recv', alert_cb,
                         qos_profile_sensor_data)
pub = node.create_publisher(OverrideRCIn, '/mavros/rc/override', 10)
client = node.create_client(SetMode, '/mavros/set_mode')
neutral = OverrideRCIn()
neutral.channels = [65535]*18
neutral.channels[0] = 1500
neutral.channels[2] = 1500
release = OverrideRCIn()
release.channels = [0]*18

try:
    deadline = time.monotonic()+5
    while state is None and time.monotonic() < deadline:
        rclpy.spin_once(node, timeout_sec=0.05)
    if not (state and state.connected and not state.armed):
        print('ABORTED: FCU state invalid')
    elif not client.wait_for_service(timeout_sec=3):
        print('ABORTED: SetMode unavailable')
    else:
        print('START:', state.mode, state.system_status)
        start = time.monotonic()
        next_print = start
        requested = False
        future = None
        while time.monotonic()-start < 8:
            rclpy.spin_once(node, timeout_sec=0.05)
            if not state.connected or state.armed:
                print('ABORTED: unexpected disconnection or arm')
                break
            pub.publish(neutral)
            elapsed = time.monotonic()-start
            if elapsed >= 3 and not requested and state.system_status == 3:
                req = SetMode.Request()
                req.base_mode = 0
                req.custom_mode = 'MANUAL'
                future = client.call_async(req)
                print('MANUAL REQUESTED', flush=True)
                requested = True
            if time.monotonic() >= next_print:
                print(f't={elapsed:.1f}s mode={state.mode} '
                      f'status={state.system_status} armed={state.armed}',
                      flush=True)
                next_print = time.monotonic()+1
        if future and future.done():
            print('SET_MODE RESPONSE:', future.result())
finally:
    for _ in range(10):
        pub.publish(release)
        rclpy.spin_once(node, timeout_sec=0.05)
    print('FINAL:', (state.mode, state.system_status, state.armed)
          if state else None)
    print('OVERRIDE RELEASED')
    node.destroy_node()
    rclpy.shutdown()
```

**Historical fidelity note:** the executed script printed only `(state.mode, state.system_status)` at the end and did not inspect `future.result()`. This reproduction logs `armed` and, if available, the asynchronous service result as additional diagnostics. It does not claim those extra fields were present in the pasted historical output.

## L. Diagnostic shell commands and parameter timeline (EXECUTED)

### L.1 Core topic discovery

```bash
docker exec arboreon-dev bash -lc '
  source /opt/ros/humble/setup.bash
  export ROS_DOMAIN_ID=20
  timeout 5 ros2 node list | grep mavros
  timeout 5 ros2 service list -t | grep -E "/mavros/(param/set|set_mode|set_message_interval)" || true
  timeout 5 ros2 topic list -t | grep -Ei "rc/|manual_control|mavlink" || true
  timeout -s INT 6 ros2 topic hz /mavros/rc/out || true
  timeout 5 ros2 topic echo /mavros/state --once
'
```

Examples from session: `/mavros/rc/out` averaged ~5 Hz; `/mavros/rc/in --field channels` printed `array('H')` because the array was empty; raw `/uas1/mavlink_source` received message ID 65 with `chancount=0`.

### L.2 FCU GCS-authorization parameters (historical writes)

```bash
# Write only if deliberately using GCS source IDs 254..255 on your robot.
# Always save original values and confirm a recovery path first.
docker exec arboreon-dev bash -lc '
  source /opt/ros/humble/setup.bash
  export ROS_DOMAIN_ID=20
  timeout 10 ros2 param set /mavros/param MAV_GCS_SYSID_HI 255
  timeout 10 ros2 param get /mavros/param MAV_GCS_SYSID_HI
  timeout 10 ros2 param set /mavros/param MAV_GCS_SYSID 254
  timeout 10 ros2 param get /mavros/param MAV_GCS_SYSID
'
```

### L.3 Disarmed MANUAL request (insufficient without neutral RC in the recorded tests)

```bash
docker exec arboreon-dev bash -lc '
  source /opt/ros/humble/setup.bash
  export ROS_DOMAIN_ID=20
  timeout 10 ros2 service call /mavros/set_mode \
    mavros_msgs/srv/SetMode \
    "{base_mode: 0, custom_mode: MANUAL}"
  sleep 3
  timeout 5 ros2 topic echo /mavros/state --once
'
```

The service returned `mode_sent=True` but **HOLD persisted** when radio failsafe remained active. Later, the same request made while continuous neutral virtual RC was clearing the radio failsafe **succeeded**.

### L.4 Selected mode and safety checks

```bash
docker exec arboreon-dev bash -lc '
  source /opt/ros/humble/setup.bash
  export ROS_DOMAIN_ID=20
  for p in RC1_MIN RC1_TRIM RC1_MAX RC3_MIN RC3_TRIM RC3_MAX \
           SERVO1_FUNCTION SERVO3_FUNCTION SERVO1_TRIM SERVO3_TRIM \
           MOT_SAFE_DISARM RC_OPTIONS FS_THR_ENABLE FS_THR_VALUE \
           FS_ACTION FS_TIMEOUT FS_EKF_ACTION FS_GCS_ENABLE \
           MODE_CH RC8_MIN RC8_TRIM RC8_MAX RC8_OPTION \
           MODE1 MODE2 MODE3 MODE4 MODE5 MODE6; do
    echo "$p:"
    timeout 5 ros2 param get /mavros/param "$p" || true
  done
'
```

`MOT_SAFE_DISARM=0` was observed, but should not be interpreted in isolation as a verified powered motor-output guarantee. No permission to disable safety checks follows from this setting.

### L.5 Diagnostic mode-selector change (historically executed, not a demonstrated solution)

```bash
# This was tested with the FCU DISARMED and motor power OFF:
ros2 param set /mavros/param MODE_CH 0
ros2 param get /mavros/param MODE_CH  # 0
```

It did **not** fix HOLD/CRITICAL without continuous neutral RC. The final value observed in this session is **0**. A future engineering decision should either deliberately keep it and document the mode-control strategy or restore the previously recorded value 8 after checking the physical control design; do not make an undocumented change.

### L.6 Listen for ArduPilot prearm/failsafe text

```bash
docker exec arboreon-dev bash -lc '
  source /opt/ros/humble/setup.bash
  export ROS_DOMAIN_ID=20
  timeout -s INT 12 ros2 topic echo /mavros/statustext/recv || true
  timeout 5 ros2 topic echo /mavros/state --once || true
'
```

Observed `PreArm: Hardware safety switch`, `PreArm: 3D Accel calibration needed`, `PreArm: Compass not calibrated`, `PreArm: Radio failsafe on`; later `Radio Failsafe Cleared` on the sustained neutral RC stream.

## M. Reproducibility checklist and final acceptance inventory

- [x] Raspberry Pi 5 and Yahboom ESP32 micro-ROS linked (companion report).
- [x] Direct ROS `/cmd_vel` moved and stopped both suspended wheels (companion report; **not Pixhawk control**).
- [x] Cube Black ArduRover 4.7.2 ↔ MAVROS working.
- [x] ArduRover differential outputs set to 73/74 and read back.
- [x] Read-only differential bridge and guarded bench-mode software tested on neutral output.
- [x] Disarmed/HOLD bridge gating demonstrated; no non-neutral bridge actuation proven.
- [x] Duplicate bridge publishers discovered and removed.
- [x] Physical RC absent (`RC_CHANNELS.chancount=0`) and `RCIn` empty explained.
- [x] ROS runtime `system_id` mismatch against effective raw-MAVLink SYSID identified.
- [x] FCU authorization set/read back as 254–255.
- [x] Custom MAVROS startup yielded outgoing MAVLink source 254:191.
- [x] FCU accepted an RC1 virtual steering override (1500 → 1600).
- [x] Explicit RC1 neutral restoration (1600 → 1500) proven.
- [x] Radio failsafe cleared while streaming neutral RC and returned to critical/HOLD in later no-stream observation.
- [x] HOLD → MANUAL achieved under continuous neutral RC while disarmed.
- [ ] Hardware switch and accelerometer/compass prearm alerts resolved.
- [ ] Bench **armed** neutral PWM outputs documented with reliable state checks.
- [ ] Non-neutral output differential left/right PWM measured with motor power OFF.
- [ ] Single live bridge tested in a supervised suspended-wheel Pixhawk-driven experiment.
- [ ] Local ESP32 watchdog time and stop-on-Wi-Fi-loss physically proven.
- [ ] Independent motor-enable/cutter interlock designed and verified for field operation.
- [ ] Real-world navigation, positioning, mission and stop distances validated.

**Final experimental conclusion:** MAVROS sender identity, not the lack of a physical RC receiver, was the crucial obstacle to accepted RC overrides. Correcting startup-time source SYSID to 254 enabled actual steering override acceptance. With an uninterrupted virtual RC stream, ArduRover cleared its radio failsafe and accepted a disarmed MANUAL mode request. When that stream ceased, a later observation found HOLD/CRITICAL again. The interface is now diagnostically understood, but powered differential motor control and failsafe engineering remain unverified future work.

## N. Early diagnostic variants and command history (RECONSTRUCTED from executed snippets)

These are retained to document **negative tests** and prevent a future engineer from repeating them under the false assumption that they proved rejection by ArduPilot.

### N.1 Five-second RC neutral override with `/mavros/rc/in` subscriber

Executed before the MAVROS source-SYSID correction. The original printed about 30 `RC INPUT: []` messages and then `PRUEBA FINALIZADA`.

```python
import time
import rclpy
from mavros_msgs.msg import OverrideRCIn, RCIn

rclpy.init()
node = rclpy.create_node('arboreon_rc_check')
pub = node.create_publisher(OverrideRCIn, '/mavros/rc/override', 10)
node.create_subscription(RCIn, '/mavros/rc/in',
                         lambda m: print('RC INPUT:', list(m.channels), flush=True), 10)
neutral = OverrideRCIn()
neutral.channels = [65535] * 18
neutral.channels[0] = 1500
neutral.channels[2] = 1500
release = OverrideRCIn()
release.channels = [0] * 18
try:
    start = time.monotonic()
    while time.monotonic()-start < 5:
        pub.publish(neutral)
        rclpy.spin_once(node, timeout_sec=0.1)
finally:
    for _ in range(10):
        pub.publish(release)
        rclpy.spin_once(node, timeout_sec=0.1)
    node.destroy_node()
    rclpy.shutdown()
print('PRUEBA FINALIZADA')
```

**Why it could not resolve the case:** RC receiver channel count was zero, so ROS `RCIn` was empty even after override reception was later proven through direct MAVLink message 65 payload values.

### N.2 Five-second RC-in and PWM-out combined observer

This variant sent neutral RC1=1500 and RC3=1500 while subscribing to `/mavros/rc/in` and `/mavros/rc/out`, printing about once per second. Observed:

```text
t=0.1s RC_IN=[] PWM_OUT=None
t=1.1s RC_IN=[] PWM_OUT=[1500, 0, 1500, 0]
t=2.1s RC_IN=[] PWM_OUT=[1500, 0, 1500, 0]
t=3.2s RC_IN=[] PWM_OUT=[1500, 0, 1500, 0]
t=4.2s RC_IN=[] PWM_OUT=[1500, 0, 1500, 0]
```

Equivalent code:

```python
import time
import rclpy
from mavros_msgs.msg import OverrideRCIn, RCIn, RCOut
from rclpy.qos import qos_profile_sensor_data

rclpy.init()
node = rclpy.create_node('arboreon_rc_validation')
last_in, last_out = None, None

def on_input(m):
    global last_in
    last_in = list(m.channels)

def on_output(m):
    global last_out
    last_out = list(m.channels)

node.create_subscription(RCIn, '/mavros/rc/in', on_input, qos_profile_sensor_data)
node.create_subscription(RCOut, '/mavros/rc/out', on_output, qos_profile_sensor_data)
pub = node.create_publisher(OverrideRCIn, '/mavros/rc/override', 10)
neutral = OverrideRCIn()
neutral.channels = [65535] * 18
neutral.channels[0] = 1500
neutral.channels[2] = 1500
release = OverrideRCIn()
release.channels = [0] * 18
try:
    start = time.monotonic()
    next_print = start
    while time.monotonic()-start < 5:
        pub.publish(neutral)
        rclpy.spin_once(node, timeout_sec=0.1)
        now = time.monotonic()
        if now >= next_print:
            print(f't={now-start:.1f}s RC_IN={last_in} '
                  f'PWM_OUT={last_out[:4] if last_out else None}', flush=True)
            next_print = now+1
finally:
    for _ in range(10):
        pub.publish(release)
        rclpy.spin_once(node, timeout_sec=0.1)
    node.destroy_node()
    rclpy.shutdown()
print('RC LIBERADO - PRUEBA FINALIZADA')
```

### N.3 Outbound MAVLink override detector (the experiment that counted 1,905 messages)

This was the direct proof that an in-process change to `/mavros/system_id` had **not** updated the source identity. All raw message-70 events had `(SYSID,COMPID)=(1,191)` before the restart. **This test sent RC1=1500 and RC3=1000 with motor power OFF**, and did not command a maneuver.

```python
import time
import rclpy
from mavros_msgs.msg import Mavlink, OverrideRCIn, State
from rclpy.qos import qos_profile_sensor_data

rclpy.init()
node = rclpy.create_node('arboreon_outgoing_rc_check')
state = None
count = 0
senders = {}

def on_state(m):
    global state
    state = m

def on_mavlink(m):
    global count
    if m.msgid == 70:
        count += 1
        key = (m.sysid, m.compid)
        senders[key] = senders.get(key, 0) + 1
        if count <= 5:
            print(f'OVERRIDE OUT SYSID={m.sysid} COMPID={m.compid}', flush=True)

node.create_subscription(State, '/mavros/state', on_state, qos_profile_sensor_data)
node.create_subscription(Mavlink, '/uas1/mavlink_sink',
                         on_mavlink, qos_profile_sensor_data)
pub = node.create_publisher(OverrideRCIn, '/mavros/rc/override', 10)
probe = OverrideRCIn()
probe.channels = [65535]*18
probe.channels[0] = 1500
probe.channels[2] = 1000
release = OverrideRCIn()
release.channels = [0]*18
try:
    deadline = time.monotonic()+4
    while state is None and time.monotonic() < deadline:
        rclpy.spin_once(node, timeout_sec=0.1)
    if not (state and state.connected and not state.armed and state.mode == 'HOLD'):
        print('ABORTED: FCU not disarmed in HOLD')
    else:
        end = time.monotonic()+2
        while time.monotonic() < end:
            rclpy.spin_once(node, timeout_sec=0.05)
            if not state.connected or state.armed or state.mode != 'HOLD':
                print('ABORTED: unexpected state')
                break
            pub.publish(probe)
finally:
    for _ in range(10):
        pub.publish(release)
        rclpy.spin_once(node, timeout_sec=0.05)
    print('TOTAL OVERRIDES:', count)
    print('SENDERS:', senders)
    node.destroy_node()
    rclpy.shutdown()
```

### N.4 Quick raw MAVLink message-frequency inventory

Before the detailed decoder, the operator ran a passive reader counting IDs and printing the first payload words for 65, 36 and 0. A five-second capture included 21 message-65 frames, 12 message-36 frames and 8 message-0 frames. This is a *local DDS sample*, not an exhaustive FCU traffic capture.

```python
import time
import rclpy
from mavros_msgs.msg import Mavlink
from rclpy.qos import qos_profile_sensor_data

rclpy.init()
node = rclpy.create_node('arboreon_mavlink_inspect')
counts = {}

def cb(m):
    counts[m.msgid] = counts.get(m.msgid, 0)+1
    if m.msgid in (65, 36, 0):
        print(f'MSG_ID={m.msgid} SYSID={m.sysid} '
              f'COMPID={m.compid} PAYLOAD64={list(m.payload64[:3])}', flush=True)

node.create_subscription(Mavlink, '/uas1/mavlink_source',
                         cb, qos_profile_sensor_data)
try:
    end = time.monotonic()+5
    while time.monotonic() < end:
        rclpy.spin_once(node, timeout_sec=0.1)
finally:
    print('MESSAGE COUNTS:', counts)
    node.destroy_node()
    rclpy.shutdown()
```

### N.5 Diagnostic commands that did not support a conclusion

```bash
# These were investigative only; do not substitute them for wire evidence.
ros2 param get /mavros_node system_id      # Parameter not set
ros2 param get /mavros_node component_id   # Parameter not set
ros2 param get /mavros system_id           # Actual UAS parameter
ros2 param get /mavros component_id

# This Humble CLI did not support --verbose:
ros2 param describe /mavros system_id --verbose

# This CLI call waited for a service compatible with its specified type:
ros2 service call /mavros/param/set mavros_msgs/srv/ParamSet \
  '{param_id: MAV_GCS_SYSID_HI, value: {integer: 255, real: 0.0}}'

# The actual service list showed multiple offered types:
ros2 service list -t | grep '/mavros/param/set'
# /mavros/param/set [mavros_msgs/srv/ParamSet, mavros_msgs/srv/ParamSetV2]
# /mavros/param/set_parameters [rcl_interfaces/srv/SetParameters]
```

The tested, successful path for changing FCU parameters was `ros2 param set /mavros/param ...`, accompanied by verification using `ros2 param get`. A process remaining connected is not sufficient to prove a changed MAVLink sender identity: use the raw sink/source checks above.

---

**End of companion technical report.**
