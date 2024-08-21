"""
    Send MISSION_COUNT message to the vehicle first
    Vehicle will respond to this with MISSION_REQUEST message
    This message contains requested mission item sequence number
    Respond to this message with MISSION_ITEM_INT message as soon as possible
    Vehicle will wait and re-request the MISSION_ITEM_INT messages with limited time and timeout
    After sending the last mission item, vehicle will send MISSION_ACK message

    https://mavlink.io/en/messages/common.html#MISSION_COUNT
    https://mavlink.io/en/messages/common.html#MISSION_REQUEST
    https://mavlink.io/en/messages/common.html#MISSION_ITEM_INT
    https://mavlink.io/en/messages/common.html#MISSION_ACK
"""

import time
import pymavlink.mavutil as utility
import pymavlink.dialects.v20.all as dialect

# create mission item list
target_locations = ((-35.361297, 149.161120, 50.0),
                    (-35.360780, 149.167151, 50.0),
                    (-35.365115, 149.167647, 50.0),
                    (-35.364419, 149.161575, 50.0))

# connect to vehicle
vehicle = utility.mavlink_connection(device="tcp:192.168.1.57:5763")

# wait for a heartbeat
vehicle.wait_heartbeat()

# inform user
print("Connected to system:", vehicle.target_system, ", component:", vehicle.target_component)

# create mission count message
message = dialect.MAVLink_mission_count_message(target_system=vehicle.target_system,
                                                target_component=vehicle.target_component,
                                                count=len(target_locations) + 2,
                                                mission_type=dialect.MAV_MISSION_TYPE_MISSION)

# send mission count message to the vehicle
vehicle.mav.send(message)

# this loop will run until receive a valid MISSION_ACK message
while True:

    # catch a message
    message = vehicle.recv_match(blocking=True)

    # convert this message to dictionary
    message = message.to_dict()

    # check this message is MISSION_REQUEST
    if message["mavpackettype"] == dialect.MAVLink_mission_request_message.msgname:

        # check this request is for mission items
        if message["mission_type"] == dialect.MAV_MISSION_TYPE_MISSION:

            # get the sequence number of requested mission item
            seq = message["seq"]

            # create mission item int message
            if seq == 0:
                # create mission item int message that contains the home location (0th mission item)
                message = dialect.MAVLink_mission_item_int_message(target_system=vehicle.target_system,
                                                                   target_component=vehicle.target_component,
                                                                   seq=seq,
                                                                   frame=dialect.MAV_FRAME_GLOBAL,
                                                                   command=dialect.MAV_CMD_NAV_WAYPOINT,
                                                                   current=0,
                                                                   autocontinue=0,
                                                                   param1=0,
                                                                   param2=0,
                                                                   param3=0,
                                                                   param4=0,
                                                                   x=0,
                                                                   y=0,
                                                                   z=0,
                                                                   mission_type=dialect.MAV_MISSION_TYPE_MISSION)

            # send takeoff mission item
            elif seq == 1:

                # create mission item int message that contains the takeoff command
                message = dialect.MAVLink_mission_item_int_message(target_system=vehicle.target_system,
                                                                   target_component=vehicle.target_component,
                                                                   seq=seq,
                                                                   frame=dialect.MAV_FRAME_GLOBAL_RELATIVE_ALT,
                                                                   command=dialect.MAV_CMD_NAV_TAKEOFF,
                                                                   current=0,
                                                                   autocontinue=0,
                                                                   param1=0,
                                                                   param2=0,
                                                                   param3=0,
                                                                   param4=0,
                                                                   x=0,
                                                                   y=0,
                                                                   z=target_locations[0][2],
                                                                   mission_type=dialect.MAV_MISSION_TYPE_MISSION)

            # send target locations to the vehicle
            else:

                # create mission item int message that contains a target location
                message = dialect.MAVLink_mission_item_int_message(target_system=vehicle.target_system,
                                                                   target_component=vehicle.target_component,
                                                                   seq=seq,
                                                                   frame=dialect.MAV_FRAME_GLOBAL_RELATIVE_ALT,
                                                                   command=dialect.MAV_CMD_NAV_WAYPOINT,
                                                                   current=0,
                                                                   autocontinue=0,
                                                                   param1=0,
                                                                   param2=0,
                                                                   param3=0,
                                                                   param4=0,
                                                                   x=int(target_locations[seq - 2][0] * 1e7),
                                                                   y=int(target_locations[seq - 2][1] * 1e7),
                                                                   z=target_locations[seq - 2][2],
                                                                   mission_type=dialect.MAV_MISSION_TYPE_MISSION)

            # send the mission item int message to the vehicle
            vehicle.mav.send(message)

    # check this message is MISSION_ACK
    elif message["mavpackettype"] == dialect.MAVLink_mission_ack_message.msgname:

        # check this acknowledgement is for mission and it is accepted
        if message["mission_type"] == dialect.MAV_MISSION_TYPE_MISSION and \
                message["type"] == dialect.MAV_MISSION_ACCEPTED:
            # break the loop since the upload is successful
            print("Mission upload is successful")
            break

# desired flight mode
FLIGHT_MODE = "AUTO"

# get supported flight modes
flight_modes = vehicle.mode_mapping()

# check the desired flight mode is supported
if FLIGHT_MODE not in flight_modes.keys():

    # inform user that desired flight mode is not supported by the vehicle
    print(FLIGHT_MODE, "is not supported")

    # exit the code
    exit(1)

# create change mode message
set_mode_message = dialect.MAVLink_command_long_message(
    target_system=vehicle.target_system,
    target_component=vehicle.target_component,
    command=dialect.MAV_CMD_DO_SET_MODE,
    confirmation=0,
    param1=dialect.MAV_MODE_FLAG_CUSTOM_MODE_ENABLED,
    param2=flight_modes[FLIGHT_MODE],
    param3=0,
    param4=0,
    param5=0,
    param6=0,
    param7=0
)

# inform user
print("Connected to system:", vehicle.target_system, ", component:", vehicle.target_component)

# catch HEARTBEAT message
message = vehicle.recv_match(type=dialect.MAVLink_heartbeat_message.msgname, blocking=True)

# convert this message to dictionary
message = message.to_dict()

# get mode id
mode_id = message["custom_mode"]

# get mode name
flight_mode_names = list(flight_modes.keys())
flight_mode_ids = list(flight_modes.values())
flight_mode_index = flight_mode_ids.index(mode_id)
flight_mode_name = flight_mode_names[flight_mode_index]

# print mode name
print("Mode name before:", flight_mode_name)

# change flight mode
vehicle.mav.send(set_mode_message)

# do below always
while True:

    # catch COMMAND_ACK message
    message = vehicle.recv_match(type=dialect.MAVLink_command_ack_message.msgname, blocking=True)

    # convert this message to dictionary
    message = message.to_dict()

    # check is the COMMAND_ACK is for DO_SET_MODE
    if message["command"] == dialect.MAV_CMD_DO_SET_MODE:

        # check the command is accepted or not
        if message["result"] == dialect.MAV_RESULT_ACCEPTED:

            # inform the user
            print("Changing mode to", FLIGHT_MODE, "accepted from the vehicle")

        # not accepted
        else:

            # inform the user
            print("Changing mode to", FLIGHT_MODE, "failed")

        # break the loop
        break

# catch HEARTBEAT message
message = vehicle.recv_match(type=dialect.MAVLink_heartbeat_message.msgname, blocking=True)

# convert this message to dictionary
message = message.to_dict()

# get mode id
mode_id = message["custom_mode"]

# get mode name
flight_mode_names = list(flight_modes.keys())
flight_mode_ids = list(flight_modes.values())
flight_mode_index = flight_mode_ids.index(mode_id)
flight_mode_name = flight_mode_names[flight_mode_index]

# print mode name
print("Mode name after:", flight_mode_name)
