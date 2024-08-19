from pymavlink import mavutil
from network import DEFAULT_CONNECTION_STRING

# Start a connection listening to a TCP port
the_connection = mavutil.mavlink_connection(DEFAULT_CONNECTION_STRING)

# Wait for the first heartbeat
#   This sets the system and component ID of remote system for the link
the_connection.wait_heartbeat()
print("Heartbeat from system (system %u component %u)" %
      (the_connection.target_system, the_connection.target_component))

# Send a MAVLink command to set the yaw orientation of the vehicle
the_connection.mav.command_long_send(
    the_connection.target_system,  # Target system ID (e.g., the vehicle you're controlling)
    the_connection.target_component,  # Target component ID within the system (e.g., autopilot)
    mavutil.mavlink.MAV_CMD_CONDITION_YAW,  # MAVLink command to change the yaw orientation
    0,  # Confirmation (0 to execute the command immediately)
    45,  # Target yaw angle in degrees (relative to the current heading)
    25,  # Yaw speed in degrees per second
    -1,  # Direction (-1 for counterclockwise, 1 for clockwise)
    1,  # Relative offset (1 for relative, 0 for absolute)
    0, 0, 0  # Unused parameters (set to 0)
)

# Send a MAVLink command to change the speed of the vehicle
the_connection.mav.command_long_send(
    the_connection.target_system,  # Target system ID (e.g., the vehicle you're controlling)
    the_connection.target_component,  # Target component ID within the system (e.g., autopilot)
    mavutil.mavlink.MAV_CMD_DO_CHANGE_SPEED,  # MAVLink command to change speed
    0,  # Confirmation (0 to execute the command immediately)
    0,  # Speed type: 0 for airspeed, 1 for ground speed, 2 for climb rate, 3 for descent rate
    5,  # Desired speed (in m/s for airspeed or ground speed)
    0,  # Throttle (not used, so set to 0)
    0, 0, 0, 0  # Unused parameters (set to 0)
)