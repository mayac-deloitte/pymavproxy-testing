from pymavlink import mavutil
from network import DEFAULT_CONNECTION_STRING

# Start a connection listening to a UDP port
the_connection = mavutil.mavlink_connection(DEFAULT_CONNECTION_STRING)

# Wait for the first heartbeat
#   This sets the system and component ID of remote system for the link
the_connection.wait_heartbeat()
print("Heartbeat from system (system %u component %u)" %
    (the_connection.target_system, the_connection.target_component))

# Send a MAVLink message to set the vehicle's target position in local NED (North-East-Down) coordinates
the_connection.mav.send(mavutil.mavlink.MAVLink_set_position_target_local_ned_message(
    10,  # Time since system boot in milliseconds (typically provided by the autopilot or GCS)
    the_connection.target_system,  # Target system ID (e.g., the vehicle you're controlling)
    the_connection.target_component,  # Target component ID within the system (e.g., autopilot)
    mavutil.mavlink.MAV_FRAME_LOCAL_NED,  # Coordinate frame: Local NED (North-East-Down)
    int(0b010111111000),  # Type mask (defines which inputs are ignored, e.g., velocity, acceleration)
    40, 0, -10,  # Target position in NED coordinates (X=40m North, Y=0m East, Z=-10m Down)
    0, 0, 0,  # Target velocity (0 means no specific velocity target)
    0, 0, 0,  # Target acceleration or force (0 means no specific acceleration target)
    1.57,  # Target yaw angle in radians (1.57 radians = 90 degrees)
    0.5  # Target yaw rate in radians/second
))

# Send a MAVLink message to set the vehicle's target position in global coordinates (latitude, longitude, altitude)
# the_connection.mav.send(mavutil.mavlink.MAVLink_set_position_target_global_int_message(
#     10,  # Time since system boot in milliseconds (typically provided by the autopilot or GCS)
#     the_connection.target_system,  # Target system ID (e.g., the vehicle you're controlling)
#     the_connection.target_component,  # Target component ID within the system (e.g., autopilot)
#     mavutil.mavlink.MAV_FRAME_GLOBAL_RELATIVE_ALT,  # Coordinate frame: Global coordinates with relative altitude
#     int(0b110111111000),  # Type mask (defines which inputs are ignored, e.g., velocity, acceleration)
#     int(-35.3629849 * 10 ** 7),  # Target latitude in degrees, multiplied by 10^7 (MAVLink format)
#     int(149.1649185 * 10 ** 7),  # Target longitude in degrees, multiplied by 10^7 (MAVLink format)
#     10,  # Target altitude in meters above the home position (relative altitude)
#     0, 0, 0,  # Target velocity (0 means no specific velocity target)
#     0, 0, 0,  # Target acceleration or force (0 means no specific acceleration target)
#     1.57,  # Target yaw angle in radians (1.57 radians = 90 degrees)
#     0.5  # Target yaw rate in radians/second
# ))

while True:
    msg = the_connection.recv_match(
        type='LOCAL_POSITION_NED', blocking=True)
    print(msg)