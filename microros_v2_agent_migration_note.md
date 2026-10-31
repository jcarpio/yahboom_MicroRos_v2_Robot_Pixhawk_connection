# MicroROS V2: Migrating the micro-ROS Agent from Ubuntu UTM to Raspberry Pi 5

**Date:** 2026-10-31  
**Hardware:** Yahboom MicroROS V2 robot controller, Raspberry Pi 5  
**Software:** ROS 2 Humble; Ubuntu ARM64 in UTM; Yahboom Robot Manager

## Network configuration

| Setting | Previous: Ubuntu UTM | Current target: Raspberry Pi 5 |
|---|---|---|
| micro-ROS Agent host | `192.168.1.52` | `192.168.1.58` |
| Transport | UDP | UDP |
| Agent port | `8090` | `8090` |
| `ROS_DOMAIN_ID` | `40` | `20` |

The controller's agent IP address and ROS domain were changed in **Robot Manager** to target the Raspberry Pi. The IP `192.168.12.27`, present as a default/example in `~/workspaces/tools/config_robot.py`, was **not** the working Ubuntu UTM address; the actual previous address was `192.168.1.52`.

## Intended topology

```text
Joystick / SLAM / Navigation (Ubuntu UTM, 192.168.1.52)
                     |
                     | ROS 2 / DDS discovery and topics, domain 20
                     v
       Raspberry Pi 5 (192.168.1.58)
           micro-ROS Agent, UDP 8090
                     ^
                     | micro-ROS UDP connection
                     |
          Yahboom MicroROS V2 controller
       agent=192.168.1.58:8090; domain=20
```

**Goal:** Run one agent on the Raspberry Pi and run joystick, mapping, and navigation programs on Ubuntu UTM in the same ROS domain. ROS 2 discovery between the two hosts must work over the network; using the same domain ID alone is not sufficient if multicast/UDP traffic is blocked.

## Observations after migration

### JoystickControl on Ubuntu UTM

The application reported:

```text
ROS_DOMAIN_ID=20
CAR_TYPE=ptz
micro_ros_agent already running, skip.
joy_node: Opened joystick: Controller
```

The controller was recognized locally, and the ROS graph showed:

```text
/joy
/cmd_vel
/beep
/cmd_ptz_angle
/joy/set_feedback
```

However, `ros2 topic info /cmd_vel -v` reported **three publishers** (all named `joy_control`) and **zero subscribers**. This confirms that no `/cmd_vel` subscriber was visible from that Ubuntu environment at the time. The three publisher endpoints may indicate duplicate joystick processes; check rather than assuming.

### SLAM Mapping on Ubuntu UTM

Mapping still launched with the **old domain**:

```text
ROS_DOMAIN_ID=40
CAR_TYPE=ptz
```

Its launch attempted to start another micro-ROS Agent but failed:

```text
bind error | port: 8090, errno: 98
Error while starting IPvX agent!
```

`errno: 98` means the local UDP port was already in use. This error concerns a second agent process on **Ubuntu UTM**; it does not by itself prove whether the agent on the Raspberry Pi is working.

## Recommended checks and changes

1. **Keep the MicroROS V2 controller configured in Robot Manager** for `192.168.1.58`, UDP `8090`, `ROS_DOMAIN_ID=20`.
2. **Ensure the Raspberry Pi micro-ROS Agent runs under domain 20.** Check its actual process environment, not just a shell variable:

   ```bash
   echo "$ROS_DOMAIN_ID"
   pgrep -af micro_ros_agent
   ros2 topic list
   ros2 topic info /cmd_vel -v
   ```

3. **Update Ubuntu UTM launcher scripts** (including `~/microros_ws/src/scripts/mapping.sh`) to use `ROS_DOMAIN_ID=20`. Avoid starting an additional micro-ROS Agent on Ubuntu when the controller is targeting the Raspberry Pi. Back up scripts before editing.
4. **Check connectivity from UTM to the Raspberry Pi:**

   ```bash
   ping -c 3 192.168.1.58
   ```

5. **Inspect, then clean up duplicate local processes as needed:**

   ```bash
   pgrep -af 'joy_control|joy_node|micro_ros_agent'
   sudo ss -lunp | grep 8090
   ```

6. **Compare ROS graphs on both machines in domain 20:**

   ```bash
   export ROS_DOMAIN_ID=20
   ros2 daemon stop
   ros2 daemon start
   ros2 node list
   ros2 topic list
   ros2 topic info /cmd_vel -v
   ros2 topic info /beep -v
   ```

   Run this in an environment with the relevant ROS 2 setup files sourced. The expected end state is one joystick publisher and at least one robot-side `/cmd_vel` subscriber visible from UTM. Verify the subscriber first on the Pi if it is absent on UTM.

7. **Check command generation safely:** with the robot physically secured and drive wheels off the ground, inspect `ros2 topic echo /joy` and `ros2 topic echo /cmd_vel` while operating the joystick. Do not assume receiving joystick messages proves the motors are connected.

## Status / open issue

**Not yet verified:** successful end-to-end joystick control or SLAM Mapping after the migration. We have confirmed a domain mismatch in Mapping, an occupied port on Ubuntu UTM, and no `/cmd_vel` subscriber visible in UTM. The next diagnostic priority is to verify that the Raspberry Pi agent receives the MicroROS V2 connection and that ROS 2/DDS discovery works between Raspberry Pi and Ubuntu UTM.

## Relevant local files

- `~/microros_ws/src/scripts/joystick_control.sh`
- `~/microros_ws/src/scripts/mapping.sh`
- `~/workspaces/scripts/start_micro_ros_agent.sh`
- `~/workspaces/tools/config_robot.py` (may contain outdated/example values)

This note records the observed configuration and troubleshooting steps; it is not confirmation that the new setup is already operational.
