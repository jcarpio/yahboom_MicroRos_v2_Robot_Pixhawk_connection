# ARBOREON — Safety Architecture, Emergency Stop, Watchdogs, Failsafes and Return Home

**A plain-English engineering guide for the Raspberry Pi 5 + Pixhawk Cube Black + Yahboom MicroROS V2 autonomous agricultural robot**  
**Version:** 1.0 · **Date:** 30 October 2026 · **Status:** Design and verification guide; **not** a declaration of operational or functional-safety compliance

> **The most important rule:** If ARBOREON becomes uncertain about whether it is safe to move, it should stop driving and keep its cutting equipment off. Returning home is an optional navigation task, **not** an emergency stop.

## Who this document is for

This guide is written so that a person without previous robotics experience can understand what protects ARBOREON, what has actually been demonstrated on the bench, what remains untested, and how to evaluate the robot before working near people or olive trees. Engineering notes, test procedures and pseudocode provide a bridge from the simple explanations to implementation.

**Companion reports:**

- *Complete Raspberry Pi 5, Yahboom MicroROS V2, Pixhawk, MAVROS and ArduDeck Integration Handover* (29 October 2026) — the earlier architecture and connectivity report; add its repository link when publishing.
- [MAVROS RC and failsafe experimental investigation](ARBOREON_MAVROS_RC_Failsafe_Investigation_2026-10-29_EN.md) — source-ID diagnosis, RC override tests, HOLD/MANUAL transitions and scripts.

## 1. A simple mental picture: five people looking after the robot

Imagine ARBOREON is a small electric tractor with several helpers:

1. **The operator** can hit a physical emergency-stop button. It must work even when the software is confused.
2. **The Pixhawk** is the driving supervisor. It understands Rover modes, RC inputs and some failsafes.
3. **The Raspberry Pi** is the onboard computer. It runs ROS 2 and MAVROS and will coordinate navigation and perception.
4. **The Yahboom ESP32-S3** is the local motor controller. It must stop the wheels if fresh motor instructions stop arriving.
5. **Sensors and power monitors** tell the system about obstacles, people, motion, battery health and position.

These helpers do **not** all do the same job. If the Raspberry crashes, the emergency-stop button must still work. If the Pixhawk goes into HOLD, the Yahboom must not keep obeying an old speed command. If GPS becomes unreliable, the robot must not guess its way home.

### 1.1 Three different kinds of stopping

| Type | Example | What it means | Can software alone be trusted? |
|---|---|---|---|
| **Normal stop** | Operator releases the joystick | Controller requests zero speed | No, not as an emergency safety measure |
| **Protective stop** | Connection or sensor becomes unreliable | Control system stops motion and blocks automatic restart | Not without independent enforcement and validation |
| **Emergency stop (E-stop)** | Person presses the large red button | A dedicated circuit removes the ability of hazardous actuators to produce motion | **No**: use a suitable physical safety circuit |

**HOLD is not an emergency-stop button.** HOLD is an ArduPilot driving mode that requests stopping; it depends on functioning downstream hardware and software.

## 2. Actual ARBOREON architecture

```text
                          OPERATOR / ARDUDECK
                            (Mac, Wi-Fi)
                                  |
                              MAVLink
                                  |
     +------------------------------------------------------------+
     | Raspberry Pi 5, 8 GB: arboreon-dev / ROS 2 Humble           |
     | MAVROS <---USB /dev/ttyACM0---> PIXHAWK CUBE BLACK         |
     |                  ArduRover 4.7.2                            |
     |           RC input -> Rover logic -> servo outputs         |
     |                         |                                   |
     |             /mavros/rc/out (left/right PWM data)           |
     |                         |                                   |
     |          proposed supervised PWM-to-Twist bridge           |
     |                         | /cmd_vel                           |
     +-------------------------+----------------------------------+
                               | ROS 2 / micro-ROS Agent
                               | UDP 8090 / Wi-Fi
                               v
                        Yahboom ESP32-S3
                        motor driver logic
                               |
                         LEFT / RIGHT
                         wheel motors

       INDEPENDENT HARDWIRED EMERGENCY-STOP PATH (REQUIRED)
        E-stop -> safety-rated circuit/contactor/driver inhibit
                -> removal of wheel and cutter motive power
                  (Pi and Pixhawk may remain powered)
```

**Actual hardware and software observed:** Raspberry Pi 5; Yahboom two-motor MicroROS V2; ESP32-S3 with micro-ROS over Wi-Fi; USB Pixhawk Cube Black running ArduRover 4.7.2; MAVROS in Docker; `ROS_DOMAIN_ID=20`; `/cmd_vel` received by `/micro_ros_task_node`; motor commands sent to Yahboom by the ESP32. The LiDAR and other sensors are not yet validated as an autonomous human-detection safety system.

**Important distinction:** Pixhawk does not directly power Yahboom's motors. The intended PWM-to-ROS bridge is a separate software component. A Pixhawk failsafe cannot stop a wheel motor if the bridge or ESP32 continues driving from its last nonzero command.

## 3. What we have actually verified — evidence table

The word **verified** here means the operator saw or recorded the outcome during the described bench trials. It does not imply certification or field readiness.

| Safety-related claim | Evidence from the actual tests | Status |
|---|---|---|
| A physical switch can cut motor power | Operator reported testing the motor-power cutoff successfully | **Observed**, electrical architecture and safety rating not yet documented |
| Raspberry/Pixhawk stay on when that switch is operated | This is the desired and user-described architecture; the exact power wiring and isolation measurements are not in the retained logs | **Design requirement; verify and document wiring** |
| Robot responds to zero-speed commands | Brief ROS 2 test: both suspended wheels moved at a small requested speed then stopped after zero messages | **Observed on bench** |
| Motors cease movement when commands stop arriving | A short test stopped publishing nonzero `/cmd_vel` and the operator observed wheels stop | **Preliminary observation**; actual ESP32 timeout and network-loss path unmeasured |
| Pixhawk sends safe neutral outputs in HOLD/disarmed | `/mavros/rc/out` reported channels 1 and 3 at 1500 µs | **Observed**, while motor power disabled |
| Guarded bridge prevents unexpected startup movement | `LIVE STARTUP_INTERLOCK`, `LIVE DISARMED`, and `LIVE MODE_BLOCKED:HOLD` logs; a restart while armed stayed blocked | **Observed for these cases**, not a full failure analysis |
| Only one motor command source is active | `ros2 topic info /cmd_vel` confirmed zero publishers after duplicates were killed | **Observed at checkpoint**; not permanent enforcement |
| Pixhawk accepts RC overrides from onboard computer | Correcting MAVROS effective source ID to 254 made raw RC1 change 1500 → 1600 µs | **Observed** |
| Explicit neutral works | Commanded RC1=1500 returned raw RC1 to 1500 | **Observed** |
| Radio failsafe can clear during continuous virtual RC | `Radio Failsafe Cleared`; MAVLink state changed 5 → 3 | **Observed** |
| MANUAL can be selected with live neutral RC | HOLD → MANUAL was observed; state 4 while disarmed | **Observed**, no propulsion |
| Rover returned to HOLD after stream ended | Subsequent state HOLD, `system_status=5`, outputs neutral | **Observed**, exact timing and lower-level cause not fully instrumented |
| Link loss stops powered wheels safely | No combined USB, Wi-Fi, ROS process crash and powered-wheel fault tests | **Not verified** |
| Person/obstacle detection stops cutting or driving | No end-to-end positive/negative test with hazardous actuator | **Not verified** |
| Return to Home works | No reliable outdoor position source or executed RTL/SmartRTL mission in this chain | **Not implemented or verified** |
| Cutting equipment has an independent safe-off circuit | Cutter intentionally remained disconnected during tests | **Required; not verified** |

### 3.1 Why the source-ID discovery mattered

Originally MAVROS displayed ROS parameter `system_id=254` but raw `RC_CHANNELS_OVERRIDE` messages still left the router with **SYSID 1**. After constructing a custom MAVROS launch with the identifier applied at startup, outgoing MAVLink showed **SYSID 254 / COMPID 191**. ArduPilot's authorized GCS range was configured **254–255**, and RC1 override became observable. This was a communications **control-authority** problem, not a motor-controller or ROS subscriber failure.

### 3.2 Current Rover settings from actual logs

| Parameter | Observed value | Plain-language meaning |
|---|---:|---|
| `MAV_SYSID` | 1 | Pixhawk's own vehicle identity |
| MAVROS effective sender SYSID | 254 | Onboard computer's MAVLink identity |
| `MAV_GCS_SYSID` / `_HI` | 254 / 255 | Authorized GCS source ID range |
| `FS_THR_ENABLE` | 1 | Radio/throttle failsafe enabled |
| `FS_THR_VALUE` | 910 | Radio failsafe throttle threshold |
| `FS_TIMEOUT` | 1.5 s | Configured failsafe trigger delay; not a measured total stop time |
| `FS_ACTION` | 2 | HOLD on applicable failsafe |
| `RC_OVERRIDE_TIME` | 3.0 s | RC override expiry configuration |
| `FS_GCS_ENABLE` | 0 | GCS heartbeat failsafe disabled |
| `FS_EKF_ACTION` | 1 | HOLD on applicable position-estimation failure |
| `MODE_CH` | 0 at last test | RC mode selector disabled during diagnostic; originally 8 |
| `SERVO1_FUNCTION` / `SERVO3_FUNCTION` | 73 / 74 | Differential left/right motor outputs |
| `SERVO1_TRIM` / `SERVO3_TRIM` | 1500 / 1500 µs | Neutral output values |
| `RCMAP_THROTTLE` | 3 | Throttle virtual RC channel |

**Do not interpret a nominal timeout as a guaranteed stopping distance or a measured reaction time.** Software scheduling, message freshness, motor controller timeout, braking performance and electrical isolation all contribute.

## 4. Emergency-stop button: motors OFF, computers ON

### 4.1 What the operator wants

Pressing one conspicuous emergency-stop button should **immediately remove the ability of the drive wheels and cutting attachment to generate hazardous motion**, while keeping the Raspberry, Pixhawk and diagnostic logging powered if the electrical design permits. This is often called *separating actuator power from control power*.

**Why keep the computers powered?** They can record what happened, display the cause, preserve logs and help an operator diagnose the fault. Keeping them powered must **never** allow them to bypass the emergency stop.

### 4.2 Conceptual two-power-rail design

```text
BATTERY
   |
   +---- fused control-power branch ----------------------------+
   |                                                          |
   |   protected DC/DC -> Raspberry Pi + Pixhawk + ESP32 logic  |
   |                                                          |
   +---- fused hazardous-actuator branch                       |
       |                                                       |
       +-> E-STOP SAFETY CIRCUIT -> motor enable/contactor      |
                                    |                           |
                                    +-> drive motor power       |
                                    +-> separate cutter inhibit|

E-stop PRESSED: drive and cutter cannot run; diagnostics may stay ON.
E-stop RESET: motors do NOT restart until separately authorized.
```

This is a **conceptual design**, not a wiring diagram. Actual switching technology depends on current, voltage, driver behavior, startup transients, motor coast/brake characteristics, contact welding, overcurrent protection, grounding and fault tolerance. A competent electrical engineer should select and validate the appropriate contactor, safety relay, normally-closed dual-channel E-stop or motor-driver safe-torque-off input where available.

### 4.3 How an E-stop must behave

- It must be reachable and unmistakable, preferably a red mushroom actuator on a yellow background, located where an operator can reach it without entering the danger zone.
- Pressing it must have priority over Raspberry, Pixhawk, Wi-Fi and normal driving commands.
- The safe state must persist while the button remains latched, including during computer restarts or software crashes.
- Resetting the button alone must **not** restart the motors or cutter. Require a separate deliberate reset/enable sequence.
- Test the actual power lines: the Pi may stay on through USB or a separate regulator, which must not back-feed motor power.
- A cutter may continue spinning through inertia **after** its electricity is cut. Guarding, braking and warning times still matter.
- Releasing torque can allow a robot on a slope to roll. A brake or other holding mechanism may be necessary.

### 4.4 What we know about ARBOREON's existing switch

The operator reported an independently operated physical motor cutoff and tested that motor power is removed. That is a valuable first layer. **We have not documented its schematic, contact rating, whether it breaks both motor and cutter energy, emergency-stop category, fault resistance, or whether the Pi/ESP32 remain powered without USB back-feed.** Therefore call it a **tested manual motor-power cutoff**, not yet a certified or fully validated E-stop.

### 4.5 A simple acceptance demonstration (non-hazardous bench setup)

With the cutter disconnected and wheels isolated: verify computer LEDs/network remain on after pressing the switch, motor power is absent using a suitable meter, the wheels cannot move in response to erroneous commands, and a reset alone causes no restart. Repeat after a Raspberry reboot and after an unexpected process stop. Record the actual wiring and operator-visible indicators. **Do not conduct this demonstration around a live blade or near people.**

## 5. What is a watchdog? The robot's kitchen timer

A watchdog is a timer that continuously asks: **“Has the controlling program checked in recently?”** If not, it enters a safe state instead of continuing forever with an old command.

A simplified illustration:

```text
Fresh drive command arrives ----> timer resets
               |
               v
         wheel motor runs
               |
          no fresh command
               |
          timer expires
               v
    MOTOR COMMAND = ZERO and/or
    DRIVER ENABLE = OFF (as designed)
```

### 5.1 The three watchdogs ARBOREON needs

**A. ESP32 local command watchdog — the essential final guard.** The ESP32 drives the motor board, so it must reject old commands locally. It cannot rely on the Raspberry to send a `Twist(0)` after the Wi-Fi link has failed. Prefer a motor-driver inhibit that defaults off when software/heartbeat fails.

**B. Raspberry bridge input watchdog.** The PWM-to-Twist bridge should require fresh, valid `/mavros/rc/out` and `/mavros/state` messages. If the Pixhawk stops sending data, the bridge must immediately stop generating nonzero speeds; it must never reuse the last nonzero PWM indefinitely. A heartbeat from a process is not proof its data is current.

**C. Hardware/supervisor watchdog.** A separate monitor or hardware safe-enable circuit can remove driver power/enable if the Raspberry or ESP32 stops responding altogether. A generic Linux watchdog that merely reboots the Pi is not equivalent to disabling motors immediately.

### 5.2 What was already observed

In a limited bench experiment, the wheels stopped after a short command burst when the ROS publisher stopped transmitting. This **suggests** a motor-command timeout in the Yahboom control path, but the actual timeout duration, firmware implementation, controller power-loss behavior and stop on Wi-Fi outage remain **unmeasured**. A second test used an explicit sequence of zero commands; that proves normal stopping, not watchdog protection.

### 5.3 How to measure watchdogs without guessing

- Use a monotonic timer on a logger and record when the final valid command is published, when the ESP32 changes motor-enable state, and when wheel rotation actually stops.
- Differentiate **command withdrawal**, **publisher crash**, **Wi-Fi loss**, **Agent crash**, **Raspberry crash** and **Pixhawk USB unplug**. They are different failures.
- Measure worst case across repeated runs, various speeds and battery conditions. Set an acceptance limit based on stopping distance and hazard analysis, not a convenient round number.
- Require manual re-enabling after a watchdog trip. Do not allow a restored Wi-Fi connection to resume an old movement request.

### 5.4 Example watchdog logic — EXPLANATION ONLY, not production firmware

```python
# PSEUDOCODE ONLY. Runs conceptually on the motor controller.
# It is NOT a drop-in ESP32/Yahboom implementation.

on_new_valid_motor_command(command):
    if emergency_stop_active or not independently_enabled:
        motor_driver_disable()
        return
    last_valid_command_time = monotonic_time()
    apply_bounded_motor_command(command)

periodic_motor_safety_task():
    if emergency_stop_active:
        motor_driver_disable()
    elif monotonic_time() - last_valid_command_time > LOCAL_TIMEOUT:
        command_zero_speed()
        motor_driver_disable()      # if architecture supports it
        latch_fault('COMMAND_TIMEOUT')
```

The timer must live **close enough to the motor hardware** that a Raspberry crash cannot stop it from running. If ESP32 itself hangs, a truly independent safe-enable/hardware watchdog is still necessary.

## 6. What is a failsafe? The agreed emergency response

A *failsafe* is an automatic reaction when something goes wrong. Examples: radio signal disappears, battery is low, the position estimate becomes unreliable, or the robot cannot move as expected.

### 6.1 What HOLD actually did in our tests

When no valid RC virtual stream was present, the Cube reported `Radio failsafe on`, `system_status=5`, `mode=HOLD`. When valid neutral RC was continuously transmitted, ArduPilot emitted `Radio Failsafe Cleared`, changing from critical to standby (`5 -> 3`). With the live stream present it accepted MANUAL and emitted state 4. After the stream ended, a later reading showed HOLD and status 5 again. Another earlier short observation after explicit release stayed at status 3: **therefore the exact failure timing/semantics cannot be asserted from these logs alone**.

No wheel movement was generated by the Pixhawk in these trials. A return to HOLD is not evidence that a powered Yahboom automatically stops when ROS or Wi-Fi fails.

### 6.2 Which failsafes are configured, and which are not

| Mechanism | Current observed setting/status | Consequence |
|---|---|---|
| Virtual RC loss | `FS_THR_ENABLE=1`, `FS_TIMEOUT=1.5`, `FS_ACTION=2` | Rover can request HOLD on radio/RC loss; **observed at the control level** |
| GCS heartbeat loss | `FS_GCS_ENABLE=0` | Not an active independent heartbeat-loss protection |
| RC override expiration | `RC_OVERRIDE_TIME=3.0` | Override timeout configured; does not turn off Yahboom motor supply |
| EKF position-estimation failure | `FS_EKF_ACTION=1` | HOLD when estimator fails in applicable navigation modes; not a proven field test |
| Battery low/critical | Not fully inventoried | Must inspect and configure for actual battery chemistry and cutoff architecture |
| Collision/person detection | LiDAR/camera integration incomplete | Not a safety-rated person detection system |
| Pixhawk hardware watchdog | Device/firmware supports watchdog concepts | Actual recovery-to-safe behavior on this robot not demonstrated |
| ESP32 command timeout | Preliminary visual stop observation | Needs timed link-loss and motor-enable testing |

**Do not indiscriminately switch on GCS failsafe or change FS_ACTION.** The real communication design (what component sends heartbeat, mission behavior, safe stop capability and control recovery) must be decided first, then measured in realistic failure tests.

### 6.3 Fail-safe versus fail-operational

- **Fail-safe:** stop when information is lost.
- **Fail-operational:** continue a limited task despite a fault, with a separately verified redundant capability.

For the first ARBOREON field prototype, choose **fail-safe stop** instead of attempting navigation after losing trusted sensing or control. It is better to recover a stopped machine than to search for a moving one with failed localization.

## 7. What if Pixhawk messages stop reaching the Raspberry?

This is one of the most important failure scenarios. The Raspberry bridge watches the Pixhawk's reported wheel outputs. Suppose it last saw “drive forward,” then the USB cable disconnects. If it keeps the old value forever, the wheels could continue moving **even though Pixhawk itself is in HOLD or powered off**.

### 7.1 Required behavior

1. The bridge detects lack of *fresh* MAVROS state or output data.
2. It immediately suppresses nonzero `/cmd_vel` commands.
3. A local ESP32 watchdog independently disables drive if fresh commands stop arriving.
4. If an independent motor-enable circuit is fitted, it drops enable on the relevant fault.
5. The machine latches the fault and refuses automatic restart when the USB cable is reconnected.
6. The operator sees a clear reason: `PIXHAWK_LINK_LOST`, with a timestamp.

### 7.2 Why a “zero” message is not enough

It might never arrive. A broken USB connection can prevent fresh input; a failed Pi can prevent output; failed Wi-Fi can prevent the ESP32 receiving the zero message. Always have a second layer at the motor controller and ideally an independent hardware inhibit.

### 7.3 What we have and what is missing

The guarded `arboreon_mavros_bridge_live.py` prototype watches incoming state/output data and has startup/HOLD/disarm interlocks. Those are useful controls demonstrated in limited logging tests. They are **not a certified safety circuit**, and there is no published evidence yet that all process-crash, USB-out, Wi-Fi-out and power-loss paths drive the actual motor hardware to a safe state within an acceptable measured time.

### 7.4 Timestamp pitfalls

At one stage `/mavros/rc/out` messages arrived at roughly 5 Hz, while their embedded `header.stamp` appeared substantially older than `/mavros/state`. That means a safety monitor must distinguish **arrival freshness measured by a local monotonic clock** from **embedded timestamps whose clocks may not be synchronized**. Also detect values out of range, disconnected states and a stalled stream whose timestamps repeat.

### 7.5 Suggested decision rules

```text
IF hardware E-stop active               -> disable motion immediately
ELSE IF stop has been latched            -> do not re-enable automatically
ELSE IF fresh Pixhawk state missing      -> zero + motor inhibit
ELSE IF fresh servo output missing       -> zero + motor inhibit
ELSE IF Pixhawk disarmed                 -> zero
ELSE IF Pixhawk in HOLD                  -> zero
ELSE IF unexpected mode                  -> zero
ELSE IF PWM invalid/out of bounds        -> zero + latch fault
ELSE IF operator has not enabled motion  -> zero
ELSE                                     -> bounded motion request
```

Only adopt this in an engineered system with validated lower-level enforcement; the intended mode whitelist and performance limits need explicit design and testing.

## 8. What if the Raspberry, Wi-Fi or micro-ROS Agent fails?

| Failure | What the operator may see | Required safe reaction | Verified today? |
|---|---|---|---|
| Raspberry power disappears | Status page/network offline | Independent drive/cutter inhibit; controller timeout | **No** |
| Raspberry ROS process crashes | No more `/cmd_vel` messages | ESP32 watchdog/enable OFF | Partially suggested by short no-publish bench test |
| USB Pixhawk cable disconnects | `/mavros/state` stale or disconnected | Bridge blocks output, independent local watchdog | **No end-to-end test** |
| MAVROS exits or restarts | RC virtual stream disappears | Pixhawk HOLD where applicable; Yahboom local stop | RC/HOLD observed, powered-wheel path not proven |
| Wi-Fi AP fails | micro-ROS Agent cannot reach ESP32 | ESP32 timeout independent of Pi | **No** |
| Agent container stops | DDS session disappears | ESP32 stops wheels locally | **No** |
| Robot controller ESP32 hangs | Last outputs may persist | Independent hardware watchdog or safe-enable deasserts | **No** |
| Duplicate ROS publishers appear | Unpredictable competing commands | Single-writer controller/arbitrator, block armed operation | Duplicates found and manually removed; permanent prevention pending |
| Pixhawk reports HOLD while bridge receives old PWM | Mismatched state and command | HOLD must dominate; freshness checks and motor inhibit | Interlock logging observed |
| Battery becomes critically low | Pi reboots or driver voltage sags | Separate monitored power and preemptive protective stop | **Not yet tested** |

**A critical subtlety:** A Pi reboot is not necessarily a stop. If the ESP32 remains powered from a different supply, it may continue to hold an old motor command. Conversely, if the ESP32 is powered over USB, flipping the main switch may not reset its firmware. Verify the actual electrical supply paths.

## 9. What should happen when a person, animal or obstacle appears?

An agricultural robot needs a simple hierarchy:

1. **Unexpected person near moving wheels or cutter:** safety-rated protective stop, cutter disabled, manual inspection and reset.
2. **Stone, tree, stump or unknown object in the planned path:** stop first; replan only after perception is validated and clearance is adequate.
3. **Sensor failure / dirty lens / blocked LiDAR / poor illumination:** stop rather than assume the area is empty.
4. **Known tree trunk:** maintain a defined exclusion zone; navigation and tool control are separate.

The currently used RPLIDAR and camera/YOLO concepts are valuable for navigation research, but **ordinary obstacle detection is not equivalent to certified personnel protection**. A safety case must address range, blind spots, dust, sunlight, vibration, occlusion, approach speed, stopping distance and independent detection failure.

### 9.1 Stopping distance in plain language

If a vehicle is moving at speed `v`, and it takes `t` seconds to detect and react, it travels `v × t` meters before braking even begins. Then braking adds more distance. At 0.5 m/s, a 2-second reaction already means **1 meter of travel before braking**. This is an illustration, not a measured ARBOREON performance value.

Keep sufficient clearance **beyond** the measured worst-case stopping distance plus a safety margin. A robot cannot safely work near people merely because it has a LiDAR.

## 10. Return to Home (RTL): useful, but not an emergency stop

“Return to Home” sounds reassuring. But when a robot is uncertain, attempting to drive somewhere else may be more dangerous than stopping.

### 10.1 Three different ideas

| Feature | Simple meaning | Main risk |
|---|---|---|
| **HOLD** | Stop and stay where you are | Depends on actual motor stop, slope/braking |
| **RTL (Return to Launch)** | Navigate toward the recorded home position | Usually follows a direct route, which may cross obstacles |
| **SmartRTL** | Try to follow a recorded previous path back home | Needs good positioning and a usable path history; not guaranteed obstacle-free |

In Rover, RTL normally navigates to the location where the vehicle was last armed, unless home was changed. SmartRTL attempts to retrace a stored route, then holds position on arrival. These are **navigation modes, not safety-rated collision-avoidance systems**.

### 10.2 What Return Home needs to work

- A correct and deliberate **home location** (not the nearest Wi-Fi router or the Raspberry's IP address).
- A trustworthy **current position and heading** over the entire return route.
- A suitable outdoor GNSS/RTK solution or other validated navigation source; the earlier indoor Cube had no usable GPS fix.
- Sufficient battery reserve and motor power.
- A valid route with no impassable obstacles or people; tree rows and terrain must be considered.
- Appropriate localization failsafe and obstacle handling.
- A complete, functioning drive-control chain from the Pixhawk through ROS to the wheels.

**Current status:** RTL and SmartRTL have **not** been tested or established on ARBOREON. RTK and autonomous orchard navigation are future work. Never label the system “returns home automatically” at this stage.

### 10.3 Should Return Home trigger when Wi-Fi is lost?

**Not for the first field prototype.** If the ESP32 needs that same Wi-Fi connection to receive commands from the Raspberry, the robot cannot reliably drive home after Wi-Fi loss. A direct Cube-to-motor path or independently verified fallback controller would be required, as would safe obstacle perception and navigation. Default to stopping when that link is lost.

### 10.4 Safer future recovery policy

```text
Operator presses E-stop?                  -> STOP. Never RTL.
Person or unknown obstacle detected?      -> STOP and disable cutter.
Motor control / ESP32 link lost?          -> STOP; not RTL.
Pixhawk data lost or stale?                -> STOP; not RTL.
GPS/EKF invalid?                          -> STOP; not RTL.
Battery critically low?                   -> STOP safely if return cannot be guaranteed.
Battery low but navigation healthy?        -> consider RTL only after separate validation.
Operator requests return, all healthy?    -> optional controlled RTL/SmartRTL.
```

### 10.5 SmartRTL is not a magical breadcrumb guarantee

SmartRTL records/simplifies the path travelled and needs a good position estimate on arming. If its path buffer fills or it lacks reliable position, it may become unavailable. The configured `FS_ACTION` determines whether the autopilot chooses RTL or HOLD in some SmartRTL fallback cases. That does **not** make a hazardous autonomous journey automatically safe.

## 11. A layered safety policy for ARBOREON

Think of protections like nested fences. Each layer should catch failures that escape the previous one.

| Layer | Responsibility | Proposed enforcement |
|---|---|---|
| 0: Operator and physical safety | Emergency stop, guards, physical separation | Independent actuator-power cutoff and deliberate reset |
| 1: Motor drive hardware | Cannot hold hazardous torque if its controller fails | Default-off enable, contactor/STO where appropriate, cutter disconnect |
| 2: ESP32 | Only accept recent valid motor commands | Local watchdog, output bounds, stop-on-disconnect, latched fault |
| 3: Raspberry bridge | Do not extrapolate stale Pixhawk PWM | State freshness, servo freshness, startup interlock, mode/arm gating, rate/velocity limits |
| 4: Pixhawk | Mode supervision and available ArduRover failsafes | HOLD/RC failsafe/EKF/battery as intentionally configured |
| 5: Navigation and perception | Plan safe motion and avoid hazards | Valid localization, bounded route, obstacle monitoring, safe fallbacks |
| 6: Operator monitoring | See faults, intervene and recover | Logs, clear indicator, warning, remote stop as supplementary channel |

**One extra rule:** No single ordinary software process should have unilateral authority to re-enable the drive or cutter after a fault. A reset request and a separate safety-enable condition are different things.

## 12. Before every test: a non-technical operator checklist

- [ ] The cutting tool is physically disconnected or independently secured.
- [ ] The robot cannot roll away; wheels are suspended or mechanically restrained as appropriate.
- [ ] No person or animal is within reach of moving components.
- [ ] The physical motor-power cutoff works and is within reach.
- [ ] The Raspberry, Pixhawk and ESP32 are powered as intended; no unexpected USB back-feed.
- [ ] Only one MAVROS process and one authorized motor-command publisher are active.
- [ ] Pixhawk's actual mode and armed state are visible.
- [ ] Expected outputs are neutral before any change.
- [ ] No unresolved prearm warnings are bypassed.
- [ ] A second operator or equivalent independent shutdown capability is available for powered bench tests.
- [ ] The test has an explicit STOP condition and a written way back to a safe state.

## 13. Safety tests to perform, in the right order

The tests below are **acceptance plans**, not instructions to defeat the existing safety checks or energize a mower. Record each result and mark it PASS/FAIL/NOT RUN. Stop at the first unexpected outcome.

### Stage 0 — wiring and independent power isolation

1. Draw both battery branches and identify fuses, regulator, motor driver, switch and cutter wiring.
2. Verify power cutoff removes hazardous actuator energy without unexpectedly back-feeding it through USB.
3. Verify E-stop remains latched during software reboot and cannot cause auto-restart when released.
4. Verify cutter safely stops and cannot re-energize; use a simulator/dummy load before working with an actual blade.

**Acceptance:** measured power isolation, safe reset and documented wiring. Until then, do not claim an emergency-stop safety function is complete.

### Stage 1 — static ROS/MAVROS health (motor power OFF)

Record `/mavros/state`, `/mavros/rc/out`, `/cmd_vel` publisher count, and process list. Verify a single MAVROS endpoint and the expected sender SYSID. If input becomes stale, the bridge must not enable movement.

### Stage 2 — explicit neutral / release (motor power OFF)

Observe raw RC1 and RC3, command neutral, then release override. In our actual trials, release alone initially left the last reported RC1 at 1600, whereas explicitly commanding 1500 returned it to 1500. This is a reason to command neutral **before** release in normal shutdown, but not a substitute for independent motor stopping on link failure.

### Stage 3 — failsafe and mode selection (motor power OFF)

Reproduce the *observed* logical sequence: loss of virtual RC may produce radio failsafe/HOLD; continuous valid neutral RC produced `Radio Failsafe Cleared`; after recovery, changing to MANUAL succeeded without arming. Monitor `STATUSTEXT` and the actual `armed` flag. **Do not treat `system_status=4` alone as proof of armed motors.**

### Stage 4 — output mixing (motor power OFF)

Only after resolving prearm warnings and confirming electrical isolation, check a short, bounded differential RC input and observe both left/right servo outputs. Record correct signs, neutral response, disarm and HOLD behavior. **This stage has not yet been executed successfully in the provided record.**

### Stage 5 — local motor watchdog and link fault injection

With wheels safely suspended, cutter disconnected, and independent cutoff already proven, test one fault at a time: stop the publishing process, interrupt the Agent, disrupt Wi-Fi, unplug Pixhawk USB, kill MAVROS, restart Raspberry and reboot ESP32. Measure hardware motor response and whether any old nonzero command is replayed. **All such end-to-end powered failure tests are still pending.**

### Stage 6 — navigation, obstacles and Return Home

Test only in a controlled environment with validated position accuracy, obstacle protection and independent stop. Begin with conservative speed, marked exclusion zones and an open field. RTL/SmartRTL must be validated separately; no occupied orchard, live blade or unattended deployment during initial commissioning.

## 14. Failure-injection evidence sheet (copy for each test)

```text
ARBOREON SAFETY TEST REPORT
Test ID / operator / date:
Firmware and Git revision:
Pixhawk mode and armed state:
Battery and motor/cutter power state:
Fault deliberately introduced:
Initial /cmd_vel value:
Last valid /mavros/rc/out reception time:
Last valid /cmd_vel reception time at ESP32:
Time controller commanded zero:
Time motor driver was actually disabled:
Time wheel motion physically stopped:
Time cutter became non-hazardous (if applicable):
Observed STATUSTEXT / mode / system_status:
Did the robot restart automatically? (must be NO for latched fault):
Unexpected behavior:
Result: PASS / FAIL / NOT RUN
Evidence links (video, logs, screenshots):
Corrective action and retest date:
```

## 15. Simple monitoring commands (read-only)

The following commands are **inspection tools**, not a complete safety controller. They must be run on the Raspberry host, which executes ROS 2 **inside** `arboreon-dev`.

```bash
# Confirm Pixhawk state, outgoing motor PWM and safety messages.
docker exec arboreon-dev bash -lc '
  source /opt/ros/humble/setup.bash
  export ROS_DOMAIN_ID=20
  timeout 5 ros2 topic echo /mavros/state --once
  timeout 5 ros2 topic echo /mavros/rc/out --once
  timeout 5 ros2 topic info /cmd_vel -v
'
```

```bash
# Snapshot of key failsafe settings, read-only.
docker exec arboreon-dev bash -lc '
  source /opt/ros/humble/setup.bash
  export ROS_DOMAIN_ID=20
  for p in FS_THR_ENABLE FS_THR_VALUE FS_TIMEOUT FS_ACTION \
           FS_GCS_ENABLE RC_OVERRIDE_TIME FS_EKF_ACTION \
           MODE_CH SERVO1_FUNCTION SERVO3_FUNCTION; do
    printf "%s: " "$p"
    timeout 7 ros2 param get /mavros/param "$p" || true
  done
'
```

```bash
# Observe newly emitted ArduPilot warnings for a bounded interval.
docker exec arboreon-dev bash -lc '
  source /opt/ros/humble/setup.bash
  export ROS_DOMAIN_ID=20
  timeout -s INT 12 ros2 topic echo /mavros/statustext/recv
'
```

A `timeout`-induced Python/ROS exception in a CLI may mean the inspection process was interrupted, not that the flight controller failed. Repeatedly launching `--live` bridges can create duplicate publishers; inspect the process and DDS graph rather than assuming an earlier test has ended.

### 15.1 Where the actual experimental scripts live

The companion investigation report contains complete executed/reconstructed Python scripts for raw MAVLink decoding, source-ID verification, RC override, failsafe recovery and HOLD/MANUAL transitions, together with the recovered original `arboreon_mavros_bridge.py`, guarded `arboreon_mavros_bridge_live.py`, and arithmetic tests. **Those scripts document experimental behavior; they are not safety-certified field firmware.** Prefer linking to them rather than copying a risky powered-motion recipe into a beginner safety chapter.

## 16. What to do when something goes wrong: operator decision card

| What you notice | Immediate operator action | What NOT to do |
|---|---|---|
| Robot moves when it should be stopped | Press physical E-stop; keep clear; isolate energy | Do not rely only on Wi-Fi app or terminal |
| Cutter is still spinning | Keep away until fully stopped and secured | Do not approach because LEDs are green |
| “Radio Failsafe” / HOLD appears | Leave drive disabled; inspect logs/link | Do not bypass safety checks to force MANUAL |
| Lost Wi-Fi / no robot telemetry | Assume commands may be stale; use independent shutdown | Do not assume no telemetry means motors are off |
| Bad GPS/EKF | Stop and recover locally | Do not request Return Home blindly |
| Low battery | Safely stop before brownout, then inspect power | Do not assume automatic RTL is reliable |
| Unexpected reboot | Keep motor enable off; perform fresh preflight | Do not allow boot to resume old motion |
| Person enters work zone | Stop propulsion and cutter, inspect area | Do not rely on unverified AI detection |

## 17. Implementation priorities: a realistic roadmap

**Priority 0 — before any powered field movement:** Document and validate the physical motor cutoff and cutter isolation, preserve separate logic power, prevent auto-restart, complete Pixhawk safety-switch and calibration warnings. Establish a single motor-command publisher and safe startup state.

**Priority 1 — before supervised moving-wheel tests:** Implement/measure ESP32 local command timeout and independent motor inhibit, finish the PWM-to-Twist bridge validity checks, verify nonzero PWM mixing with motors unpowered, and test link-loss behavior with wheels suspended and cutter detached.

**Priority 2 — before orchard navigation:** Validate obstacle detection, stop distance, battery monitoring, localization, boundaries/geofencing and field recovery. Ensure sensor failures result in a stop, not a blind movement command.

**Priority 3 — optional automated return:** Integrate a reliable outdoor position estimate, deliberate home location, safe route/obstacle policy and an independently verified control path. Then test RTL/SmartRTL gradually, with an operator and independent stop present.

## 18. Glossary — plain words

| Term | Meaning |
|---|---|
| **E-stop** | Physical emergency stopping mechanism that acts independently of the robot's main computer |
| **Watchdog** | Timer that notices when expected activity or valid commands stop |
| **Failsafe** | Predefined response when a system detects a fault |
| **HOLD** | ArduRover mode that commands the vehicle to stop |
| **MANUAL** | ArduRover mode accepting pilot input, not proof that motors are energized |
| **RTL / Return Home** | Navigation command to go back to recorded home |
| **SmartRTL** | Attempts to return along a previously recorded path |
| **MAVLink** | Messages exchanged between Pixhawk, MAVROS and control stations |
| **MAVROS** | ROS 2 gateway to MAVLink autopilots |
| **RC override** | Virtual remote-control input sent by software |
| **PWM** | Numerical signal often used to represent servo/motor demand; 1500 µs was neutral in our observed outputs |
| **/cmd_vel** | ROS 2 topic carrying desired linear and rotational speed |
| **ESP32** | Microcontroller closest to Yahboom's motor control hardware |
| **EKF** | Software that estimates position/attitude from sensors |
| **GNSS / RTK** | Satellite position system / precision corrections; neither alone guarantees obstacle avoidance |
| **STO / motor inhibit** | Hardware-supported mechanism to prevent motor torque generation, if offered by a suitable driver |
| **Latched fault** | Error state that stays active until a deliberate reset rather than clearing automatically |

## 19. Honest bottom line

ARBOREON has already demonstrated a working communication chain, accepted MAVLink RC commands, recovery from an ArduPilot radio failsafe and transitions into MANUAL when virtual RC is sustained. The independent motor-power switch has been manually tested. Those are valuable engineering milestones.

**They are not proof that the assembled agricultural robot can safely operate unattended, stop during all connection failures, detect every person, control a cutter safely or return home.** The next safety milestone is to prove, with instruments and repeatable bench tests, that the hazardous actuators enter and remain in a safe state even when the Raspberry, Pixhawk, ESP32 or network fails.

## 20. References and source provenance

### Project-specific evidence

1. `ARBOREON_MAVROS_RC_Failsafe_Investigation_2026-10-29_EN.md` — observed experiments, source-ID bug, raw MAVLink logs, RC commands, guarded bridge and failsafe traces.
2. `ARBOREON — Complete Raspberry Pi 5, Yahboom MicroROS V2, Pixhawk Cube Black, MAVROS and ArduDeck Integration Handover` (29 Oct 2026) — hardware inventory, ROS 2 architecture, initial motor and connectivity tests.
3. The user's subsequent logged bench tests: motor-power cutoff, held command/zero command observations, neutral outputs, parameter reads, MANUAL/RC/HOLD transitions and STATUSTEXT alerts.

### ArduPilot and practical background (checked 30 October 2026)

- Rover failsafes: https://ardupilot.org/rover/docs/rover-failsafes.html
- Rover parameter meanings and choices: https://ardupilot.org/rover/docs/parameters.html
- Rover RTL: https://ardupilot.org/rover/docs/rtl-mode.html
- Rover SmartRTL: https://ardupilot.org/rover/docs/smartrtl-mode.html
- Rover safety switch: https://ardupilot.org/rover/docs/common-safety-switch-pixhawk.html
- Rover EKF failsafe: https://ardupilot.org/rover/docs/common-ekf-inav-failsafe.html
- ROS 2 documentation: https://docs.ros.org/en/humble/
- MAVROS: https://github.com/mavlink/mavros

**Reference note:** ArduPilot software features and parameter names are firmware-version dependent. Consult the actual ArduRover 4.7.2 parameter metadata before changing configuration. General standards guidance is not a substitute for an applicable machinery risk assessment or professional electrical safety review. Practical design choices depend on local legal requirements, the real drive/cutter power circuitry, duty cycle and the intended operating environment.
