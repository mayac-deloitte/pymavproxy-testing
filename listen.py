from pymavlink import mavutil
from network import DEFAULT_CONNECTION_STRING

# Start a connection using TCP to the specified IP address and port
the_connection = mavutil.mavlink_connection(DEFAULT_CONNECTION_STRING)

# Wait for the first heartbeat
#   This sets the system and component ID of remote system for the link
the_connection.wait_heartbeat()
print("Heartbeat from system (system %u component %u)" % (the_connection.target_system, the_connection.target_component))

# Once connected, use 'the_connection' to get and send messages

while True:
    msg = the_connection.recv_match(blocking=True) # Can put "type= " here
    print(msg)