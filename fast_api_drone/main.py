from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from pymavlink import mavutil
import time
import asyncio
import yaml
from typing import List, Optional
import pymavlink.dialects.v20.all as dialect

app = FastAPI()

# Load configuration from YAML
with open("config.yaml", "r") as config_file:
    config = yaml.safe_load(config_file)

# Access the configuration
drone_connections = {}
separation_time= config["settings"]["separation_time"]

class Waypoint(BaseModel):
    latitude: float
    longitude: float
    altitude: float
    command: int  # MAVLink command (e.g., MAV_CMD_NAV_WAYPOINT, MAV_CMD_NAV_TAKEOFF)

class Telemetry(BaseModel):
    latitude: float
    longitude: float
    altitude: float
    relative_altitude: Optional[float] = None
    heading: Optional[float] = None
    battery_remaining: Optional[float] = None
    gps_fix: Optional[int] = None

class DroneTelemetryResponse(BaseModel):
    drone_id: str
    telemetry: Optional[Telemetry] = None
    error: Optional[str] = None

class ConnectDroneRequest(BaseModel):
    drone_id: str

class FenceEnableRequest(BaseModel):
    fence_enable: str

def connect_drone_by_id(drone_id: str):
    """Function to connect to a drone by its ID."""
    try:
        connection_string = config["drones"][drone_id]
        if drone_id not in drone_connections:
            master = mavutil.mavlink_connection(connection_string)
            master.wait_heartbeat()
            drone_connections[drone_id] = master
        return {"status": f"Drone {drone_id} connected successfully"}
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Drone ID {drone_id} not found in config")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/connect_drone")
async def connect_drone_endpoint(request: ConnectDroneRequest):
    """Endpoint to connect to a single drone by ID."""
    return connect_drone_by_id(request.drone_id)

@app.post("/connect_all_drones")
async def connect_all_drones_endpoint():
    """Endpoint to connect to all drones specified in the config."""
    connected_drones = []
    failed_drones = []

    for drone_id in config["drones"]:
        try:
            response = connect_drone_by_id(drone_id)
            connected_drones.append(drone_id)
        except HTTPException as e:
            failed_drones.append({"drone_id": drone_id, "error": str(e)})

    if failed_drones:
        return {
            "status": "Some drones failed to connect",
            "connected_drones": connected_drones,
            "failed_drones": failed_drones
        }
    else:
        return {"status": "All drones connected successfully", "connected_drones": connected_drones}

def set_mode(master, flight_mode: str):

    # get supported flight modes
    flight_modes = master.mode_mapping()

    if flight_mode not in flight_modes.keys():
        print(flight_mode, "is not supported")
        exit(1)

    # create change mode message
    set_mode_message = dialect.MAVLink_command_long_message(
        target_system=master.target_system,
        target_component=master.target_component,
        command=dialect.MAV_CMD_DO_SET_MODE,
        confirmation=0,
        param1=dialect.MAV_MODE_FLAG_CUSTOM_MODE_ENABLED,
        param2=flight_modes[flight_mode],
        param3=0,
        param4=0,
        param5=0,
        param6=0,
        param7=0
    )

    message = master.recv_match(type=dialect.MAVLink_heartbeat_message.msgname, blocking=True)
    message = message.to_dict()
    mode_id = message["custom_mode"]

    # get mode name
    flight_mode_names = list(flight_modes.keys())
    flight_mode_ids = list(flight_modes.values())
    flight_mode_index = flight_mode_ids.index(mode_id)
    flight_mode_name_before = flight_mode_names[flight_mode_index]

    # change flight mode
    master.mav.send(set_mode_message)

    # do below always
    while True:
        message = master.recv_match(type=dialect.MAVLink_command_ack_message.msgname, blocking=True)
        message = message.to_dict()

        # check is the COMMAND_ACK is for DO_SET_MODE
        if message["command"] == dialect.MAV_CMD_DO_SET_MODE:
            if message["result"] == dialect.MAV_RESULT_ACCEPTED:
                result = "accepted"
            else:
                result = "failed"
            break

    # catch HEARTBEAT message
    message = master.recv_match(type=dialect.MAVLink_heartbeat_message.msgname, blocking=True)
    message = message.to_dict()
    mode_id = message["custom_mode"]

    # get mode name
    flight_mode_names = list(flight_modes.keys())
    flight_mode_ids = list(flight_modes.values())
    flight_mode_index = flight_mode_ids.index(mode_id)
    flight_mode_name = flight_mode_names[flight_mode_index]

    return flight_mode_name_before, flight_mode_name, result

@app.post("/update_drone_mode/{drone_id}/{flight_mode}")
async def update_drone_mode_endpoint(drone_id: str, flight_mode: str):
    if not master:
        raise HTTPException(status_code=404, detail=f"Drone with ID {drone_id} not found")
    
    try:
        mode_before, mode_after, result = set_mode(master, flight_mode.upper())
        if result == "accepted":
            return {
                "status": f"Mode change successful: {mode_before} -> {mode_after}"
            }
        else:
            raise HTTPException(status_code=500, detail=f"Mode change failed: {mode_before} -> {mode_after}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

def set_mission_and_start(master, target_locations: List[Waypoint]):

    message = dialect.MAVLink_mission_count_message(target_system=master.target_system,
                                                    target_component=master.target_component,
                                                    count=len(target_locations) + 2,
                                                    mission_type=dialect.MAV_MISSION_TYPE_MISSION)
    
    master.mav.send(message)

    # this loop will run until receive a valid MISSION_ACK message
    while True:
        message = master.recv_match(blocking=True)
        message = message.to_dict()
        if message["mavpackettype"] == dialect.MAVLink_mission_request_message.msgname:
            if message["mission_type"] == dialect.MAV_MISSION_TYPE_MISSION:

                seq = message["seq"]

                # create mission item int message
                if seq == 0:
                    # create mission item int message that contains the home location (0th mission item)
                    message = dialect.MAVLink_mission_item_int_message(target_system=master.target_system,
                                                                    target_component=master.target_component,
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
                    message = dialect.MAVLink_mission_item_int_message(target_system=master.target_system,
                                                                    target_component=master.target_component,
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
                                                                    z=target_locations[0].altitude,
                                                                    mission_type=dialect.MAV_MISSION_TYPE_MISSION)

                # send target locations to the vehicle
                else:
                    waypoint = target_locations[seq - 2]  # Adjust for home and takeoff locations
                    # create mission item int message that contains a target location
                    message = dialect.MAVLink_mission_item_int_message(target_system=master.target_system,
                                                                    target_component=master.target_component,
                                                                    seq=seq,
                                                                    frame=dialect.MAV_FRAME_GLOBAL_RELATIVE_ALT,
                                                                    command=dialect.MAV_CMD_NAV_WAYPOINT,
                                                                    current=0,
                                                                    autocontinue=0,
                                                                    param1=0,
                                                                    param2=0,
                                                                    param3=0,
                                                                    param4=0,
                                                                    x=max(min(int(waypoint.latitude * 1e7), 2147483647), -2147483648), # Ensure valid range for a 32-bit signed integer using
                                                                    y=max(min(int(waypoint.longitude * 1e7), 2147483647), -2147483648),
                                                                    z=waypoint.altitude,
                                                                    mission_type=dialect.MAV_MISSION_TYPE_MISSION)

                # send the mission item int message to the vehicle
                master.mav.send(message)

        # check this message is MISSION_ACK
        elif message["mavpackettype"] == dialect.MAVLink_mission_ack_message.msgname:
            if message["mission_type"] == dialect.MAV_MISSION_TYPE_MISSION and \
                    message["type"] == dialect.MAV_MISSION_ACCEPTED:
                print("Mission upload is successful")
                break

    # desired flight mode
    FLIGHT_MODE = "AUTO"
    flight_modes = master.mode_mapping()
    if FLIGHT_MODE not in flight_modes.keys():
        print(FLIGHT_MODE, "is not supported")
        exit(1)

    # create change mode message
    set_mode_message = dialect.MAVLink_command_long_message(
        target_system=master.target_system,
        target_component=master.target_component,
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
    print("Connected to system:", master.target_system, ", component:", master.target_component)

    message = master.recv_match(type=dialect.MAVLink_heartbeat_message.msgname, blocking=True)
    message = message.to_dict()
    mode_id = message["custom_mode"]

    # get mode name
    flight_mode_names = list(flight_modes.keys())
    flight_mode_ids = list(flight_modes.values())
    flight_mode_index = flight_mode_ids.index(mode_id)
    flight_mode_name = flight_mode_names[flight_mode_index]

    # print mode name
    print("Mode name before:", flight_mode_name)

    # change flight mode
    master.mav.send(set_mode_message)

    # do below always
    while True:
        message = master.recv_match(type=dialect.MAVLink_command_ack_message.msgname, blocking=True)
        message = message.to_dict()
        if message["command"] == dialect.MAV_CMD_DO_SET_MODE:
            if message["result"] == dialect.MAV_RESULT_ACCEPTED:
                print("Changing mode to", FLIGHT_MODE, "accepted from the vehicle")
            else:
                print("Changing mode to", FLIGHT_MODE, "failed")
            break

    message = master.recv_match(type=dialect.MAVLink_heartbeat_message.msgname, blocking=True)
    message = message.to_dict()
    mode_id = message["custom_mode"]

    # get mode name
    flight_mode_names = list(flight_modes.keys())
    flight_mode_ids = list(flight_modes.values())
    flight_mode_index = flight_mode_ids.index(mode_id)
    flight_mode_name = flight_mode_names[flight_mode_index]

    # print mode name
    print("Mode name after:", flight_mode_name)

    # Create and send PARAM_SET message to set AUTO_OPTIONS to 7
    PARAM_NAME = "AUTO_OPTIONS"

    parameter_set_message = dialect.MAVLink_param_set_message(
        target_system=master.target_system,
        target_component=master.target_component,
        param_id=PARAM_NAME.encode("utf-8"),  # Encode to bytes as required by MAVLink
        param_value=int(7),  # Set AUTO_OPTIONS to 7
        param_type=dialect.MAV_PARAM_TYPE_REAL32
    )

    master.mav.send(parameter_set_message)
    print(f"Sent request to set {PARAM_NAME} to 7")

    # Verify that the parameter was set correctly
    while True:
        # Receive PARAM_VALUE messages
        message = master.recv_match(type="PARAM_VALUE", blocking=True).to_dict()

        # Check if the parameter is AUTO_OPTIONS
        if message["param_id"].strip('\x00') == PARAM_NAME:  # Strip null characters
            print(f"{message['param_id']} = {message['param_value']}")
            break

    # vehicle arm message
    vehicle_arm_message = dialect.MAVLink_command_long_message(
        target_system=master.target_system,
        target_component=master.target_component,
        command=dialect.MAV_CMD_COMPONENT_ARM_DISARM,
        confirmation=0,
        param1=1, # VEHICLE_ARM
        param2=0,
        param3=0,
        param4=0,
        param5=0,
        param6=0,
        param7=0
    )

    # Attempt to arm the vehicle
    while True:
        print("Attempting to arm the vehicle...")
        master.mav.send(vehicle_arm_message)
        ack_message = master.recv_match(type=dialect.MAVLink_command_ack_message.msgname, blocking=True)
        ack_message = ack_message.to_dict()

        # Check if the arm command was accepted
        if ack_message["result"] == dialect.MAV_RESULT_ACCEPTED and ack_message["command"] == dialect.MAV_CMD_COMPONENT_ARM_DISARM:
            print("Arm command accepted, waiting for the vehicle to be armed...")

            # Monitor the heartbeat for arming status
            while True:
                heartbeat = master.recv_match(type=dialect.MAVLink_heartbeat_message.msgname, blocking=True)
                heartbeat = heartbeat.to_dict()

                # Check if the vehicle is armed
                armed = heartbeat["base_mode"] & dialect.MAV_MODE_FLAG_SAFETY_ARMED
                if armed:
                    print("Vehicle is armed!")
                    return  # Exit the function once the vehicle is armed
        else:
            print("Failed to arm the vehicle. Retrying...")

        time.sleep(10)

@app.post("/set_mission/{drone_id}")
async def set_mission_endpoint(drone_id: str, mission_name: str):
    try:
        # Load the waypoints for the specified mission from the config
        if mission_name not in config["waypoints"]:
            raise HTTPException(status_code=404, detail=f"Mission '{mission_name}' not found in config")
        
        mission_waypoints = [Waypoint(**wp) for wp in config["waypoints"][mission_name]]
        master = drone_connections.get(drone_id)
        set_mission_and_start(master, mission_waypoints)
        return {"status": f"Mission '{mission_name}' auto mode set successfully for drone '{drone_id}' and is armed"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to set mission auto mode: {str(e)}")

@app.post("/set_mission_all_drones/{mission_name}")
async def set_mission_all_drones_endpoint(mission_name: str):
    successful_drones = []
    failed_drones = []

    for drone_id, master in drone_connections.items():
        try:
            # Load the waypoints for the specified mission from the config
            if mission_name not in config["waypoints"]:
                raise HTTPException(status_code=404, detail=f"Mission '{mission_name}' not found in config")
            
            mission_waypoints = [Waypoint(**wp) for wp in config["waypoints"][mission_name]]
            set_mission_and_start(master, mission_waypoints)
            successful_drones.append(drone_id)

            # Add a delay between missions
            await asyncio.sleep(separation_time)

        except Exception as e:
            failed_drones.append({"drone_id": drone_id, "error": str(e)})

    if failed_drones:
        return {
            "status": "Some drones failed to set the mission",
            "successful_drones": successful_drones,
            "failed_drones": failed_drones
        }
    else:
        return {"status": "Mission set successfully for all drones", "successful_drones": successful_drones}

async def set_fence(master, fence_coordinates: List[List[float]]):

    # introduce FENCE_TOTAL and FENCE_ACTION as byte array and do not use parameter index
    FENCE_TOTAL = "FENCE_TOTAL".encode(encoding="utf-8")
    FENCE_ACTION = "FENCE_ACTION".encode(encoding="utf8")
    PARAM_INDEX = -1

    message = dialect.MAVLink_param_request_read_message(target_system=master.target_system,
                                                        target_component=master.target_component,
                                                        param_id=FENCE_ACTION,
                                                        param_index=PARAM_INDEX)
    master.mav.send(message)

    while True:
        message = master.recv_match(type=dialect.MAVLink_param_value_message.msgname,
                                    blocking=True)
        message = message.to_dict()
        if message["param_id"] == "FENCE_ACTION":
            fence_action_original = int(message["param_value"])
            break

    print("FENCE_ACTION parameter original:", fence_action_original)

    while True:
        message = dialect.MAVLink_param_set_message(target_system=master.target_system,
                                                    target_component=master.target_component,
                                                    param_id=FENCE_ACTION,
                                                    param_value=dialect.FENCE_ACTION_NONE,
                                                    param_type=dialect.MAV_PARAM_TYPE_REAL32)
        master.mav.send(message)
        message = master.recv_match(type=dialect.MAVLink_param_value_message.msgname,
                                    blocking=True)
        message = message.to_dict()
        if message["param_id"] == "FENCE_ACTION":
            if int(message["param_value"]) == dialect.FENCE_ACTION_NONE:
                print("FENCE_ACTION reset to 0 successfully")
                break
            else:
                print("Failed to reset FENCE_ACTION to 0, trying again")

    while True:
        message = dialect.MAVLink_param_set_message(target_system=master.target_system,
                                                    target_component=master.target_component,
                                                    param_id=FENCE_TOTAL,
                                                    param_value=0,
                                                    param_type=dialect.MAV_PARAM_TYPE_REAL32)
        master.mav.send(message)
        message = master.recv_match(type=dialect.MAVLink_param_value_message.msgname,
                                    blocking=True)
        message = message.to_dict()
        if message["param_id"] == "FENCE_TOTAL":
            if int(message["param_value"]) == 0:
                print("FENCE_TOTAL reset to 0 successfully")
                break
            else:
                print("Failed to reset FENCE_TOTAL to 0")

    while True:
        message = dialect.MAVLink_param_set_message(target_system=master.target_system,
                                                    target_component=master.target_component,
                                                    param_id=FENCE_TOTAL,
                                                    param_value=len(fence_coordinates),
                                                    param_type=dialect.MAV_PARAM_TYPE_REAL32)
        master.mav.send(message)
        message = master.recv_match(type=dialect.MAVLink_param_value_message.msgname,
                                    blocking=True)
        message = message.to_dict()
        if message["param_id"] == "FENCE_TOTAL":
            if int(message["param_value"]) == len(fence_coordinates):
                print("FENCE_TOTAL set to {0} successfully".format(len(fence_coordinates)))
                break
            else:
                print("Failed to set FENCE_TOTAL to {0}".format(len(fence_coordinates)))
                
    idx = 0

    # run until all the fence items uploaded successfully
    while idx < len(fence_coordinates):
        message = dialect.MAVLink_fence_point_message(target_system=master.target_system,
                                                    target_component=master.target_component,
                                                    idx=idx,
                                                    count=len(fence_coordinates),
                                                    lat=fence_coordinates[idx][0],
                                                    lng=fence_coordinates[idx][1])
        master.mav.send(message)

        message = dialect.MAVLink_fence_fetch_point_message(target_system=master.target_system,
                                                            target_component=master.target_component,
                                                            idx=idx)
        master.mav.send(message)
        message = master.recv_match(type=dialect.MAVLink_fence_point_message.msgname,
                                    blocking=True)
        message = message.to_dict()

        latitude = message["lat"]
        longitude = message["lng"]

        if latitude != 0.0 and longitude != 0:
            idx += 1

    print("All the fence items uploaded successfully")

    while True:
        message = dialect.MAVLink_param_set_message(target_system=master.target_system,
                                                    target_component=master.target_component,
                                                    param_id=FENCE_ACTION,
                                                    param_value=fence_action_original,
                                                    param_type=dialect.MAV_PARAM_TYPE_REAL32)
        master.mav.send(message)
        message = master.recv_match(type=dialect.MAVLink_param_value_message.msgname,
                                    blocking=True)
        message = message.to_dict()

        if message["param_id"] == "FENCE_ACTION":
            if int(message["param_value"]) == fence_action_original:
                print("FENCE_ACTION set to original value {0} successfully".format(fence_action_original))
                break
            else:
                print("Failed to set FENCE_ACTION to original value {0} ".format(fence_action_original))

@app.post("/set_fence/{drone_id}")
async def set_fence_endpoint(drone_id: str):
    try:
        # Get the drone connection from the global dictionary
        master = drone_connections.get(drone_id)
        if not master:
            raise HTTPException(status_code=404, detail=f"Drone with ID {drone_id} not found")
        
        # Load the fence coordinates from the config file
        if "fence" not in config or "coordinates" not in config["fence"]:
            raise HTTPException(status_code=404, detail="Fence coordinates not found in config file")
        
        fence_coordinates = config["fence"]["coordinates"]
        
        # Set the fence using the loaded coordinates
        await set_fence(master, fence_coordinates)
        
        return {"status": f"Geofence set successfully for drone '{drone_id}'"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to set geofence: {str(e)}")

@app.post("/set_fence_all_drones")
async def set_fence_all_drones():
    successful_drones = []
    failed_drones = []

    if "fence" not in config or "coordinates" not in config["fence"]:
        raise HTTPException(status_code=404, detail="Fence coordinates not found in config file")
    
    fence_coordinates = config["fence"]["coordinates"]

    for drone_id, master in drone_connections.items():
        try:
            await set_fence(master, fence_coordinates)
            successful_drones.append(drone_id)
            await asyncio.sleep(1)
        except Exception as e:
            failed_drones.append({"drone_id": drone_id, "error": str(e)})

    if failed_drones:
        return {
            "status": "Some drones failed to set the fence",
            "successful_drones": successful_drones,
            "failed_drones": failed_drones
        }
    else:
        return {"status": "Fence set successfully for all drones", "successful_drones": successful_drones}

@app.post("/enable_fence/{drone_id}")
async def enable_fence_endpoint(drone_id: str, request: FenceEnableRequest):

    fence_enable_definition = {
        "DISABLE": 0,
        "ENABLE": 1,
        "DISABLE_FLOOR_ONLY": 2
    }

    fence_enable = request.fence_enable.upper()

    if fence_enable not in fence_enable_definition:
        raise HTTPException(status_code=400, detail="Unsupported fence enable mode")
    
    master = drone_connections.get(drone_id)
    if not master:
        raise HTTPException(status_code=404, detail=f"Drone with ID {drone_id} not found")
    try:
        message = dialect.MAVLink_command_long_message(
            target_system=master.target_system,
            target_component=master.target_component,
            command=dialect.MAV_CMD_DO_FENCE_ENABLE,
            confirmation=0,
            param1=fence_enable_definition[fence_enable],
            param2=0,
            param3=0,
            param4=0,
            param5=0,
            param6=0,
            param7=0
        )
        master.mav.send(message)
        return {"status": f"Fence {fence_enable} command sent to the drone '{drone_id}' successfully"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to send fence command: {str(e)}")

@app.post("/enable_fence_all_drones")
async def enable_fence_all_drones(request: FenceEnableRequest):
    """
    Enable the fence for all drones with the specified mode (ENABLE, DISABLE, DISABLE_FLOOR_ONLY).
    """
    fence_enable_definition = {
        "DISABLE": 0,
        "ENABLE": 1,
        "DISABLE_FLOOR_ONLY": 2
    }

    fence_enable = request.fence_enable.upper()

    if fence_enable not in fence_enable_definition:
        raise HTTPException(status_code=400, detail="Unsupported fence enable mode")

    successful_drones = []
    failed_drones = []

    for drone_id, master in drone_connections.items():
        try:
            message = dialect.MAVLink_command_long_message(
                target_system=master.target_system,
                target_component=master.target_component,
                command=dialect.MAV_CMD_DO_FENCE_ENABLE,
                confirmation=0,
                param1=fence_enable_definition[fence_enable],
                param2=0,
                param3=0,
                param4=0,
                param5=0,
                param6=0,
                param7=0
            )
            master.mav.send(message)
            successful_drones.append(drone_id)
            await asyncio.sleep(1)

        except Exception as e:
            failed_drones.append({"drone_id": drone_id, "error": str(e)})

    if failed_drones:
        return {
            "status": "Some drones failed to enable the fence",
            "successful_drones": successful_drones,
            "failed_drones": failed_drones
        }
    else:
        return {"status": "Fence enabled successfully for all drones", "successful_drones": successful_drones}

async def set_rally(master, rally_coordinates: List[List[float]]):
    # introduce RALLY_TOTAL as byte array and do not use parameter index
    RALLY_TOTAL = "RALLY_TOTAL".encode(encoding="utf-8")
    PARAM_INDEX = -1

    # run until parameter set successfully
    while True:

        # create parameter set message
        message = dialect.MAVLink_param_set_message(target_system=master.target_system,
                                                    target_component=master.target_component,
                                                    param_id=RALLY_TOTAL,
                                                    param_value=len(rally_coordinates),
                                                    param_type=dialect.MAV_PARAM_TYPE_REAL32)

        # send parameter set message to the vehicle
        master.mav.send(message)

        # wait for PARAM_VALUE message
        message = master.recv_match(type=dialect.MAVLink_param_value_message.msgname,
                                    blocking=True)

        # convert the message to dictionary
        message = message.to_dict()

        # make sure this parameter value message is for RALLY_TOTAL
        if message["param_id"] == "RALLY_TOTAL":

            # make sure that parameter value set successfully
            if int(message["param_value"]) == len(rally_coordinates):
                print("RALLY_TOTAL set to {0} successfully".format(len(rally_coordinates)))

                # break the loop
                break

            # should send param set message again
            else:
                print("Failed to set RALLY_TOTAL to {0}".format(len(rally_coordinates)))

    # initialize rally point item index counter
    idx = 0

    # run until all the rally point items uploaded successfully
    while idx < len(rally_coordinates):

        # create RALLY_POINT message
        message = dialect.MAVLink_rally_point_message(target_system=master.target_system,
                                                    target_component=master.target_component,
                                                    idx=idx,
                                                    count=len(rally_coordinates),
                                                    lat=int(rally_coordinates[idx][0] * 1e7),
                                                    lng=int(rally_coordinates[idx][1] * 1e7),
                                                    alt=int(rally_coordinates[idx][2]),
                                                    break_alt=0,
                                                    land_dir=0,
                                                    flags=0)

        # send RALLY_POINT message to the vehicle
        master.mav.send(message)

        # create RALLY_FETCH_POINT message
        message = dialect.MAVLink_rally_fetch_point_message(target_system=master.target_system,
                                                            target_component=master.target_component,
                                                            idx=idx)

        # send this message to vehicle
        master.mav.send(message)

        # wait for RALLY_POINT message
        message = master.recv_match(type=dialect.MAVLink_rally_point_message.msgname,
                                    blocking=True)

        # convert the message to dictionary
        message = message.to_dict()

        # make sure this RALLY_POINT message is for the same rally point item
        if message["idx"] == idx and \
                message["count"] == len(rally_coordinates) and \
                message["lat"] == int(rally_coordinates[idx][0] * 1e7) and \
                message["lng"] == int(rally_coordinates[idx][1] * 1e7) and \
                message["alt"] == int(rally_coordinates[idx][2]):

            # increment rally point item index counter
            idx += 1

            # inform user
            print("Rally point {0} uploaded successfully".format(idx))

        # should send RALLY_POINT message again
        else:
            print("Failed to upload rally point {0}".format(idx))

    print("All the rally point items uploaded successfully")

@app.post("/set_rally_point/{drone_id}")
async def set_rally_endpoint(drone_id: str):
    try:
        # Get the drone connection from the global dictionary
        master = drone_connections.get(drone_id)
        if not master:
            raise HTTPException(status_code=404, detail=f"Drone with ID {drone_id} not found")
        
        # Load the fence coordinates from the config file
        if "rally" not in config or "coordinates" not in config["rally"]:
            raise HTTPException(status_code=404, detail="Rally coordinates not found in config file")
        
        rally_coordinates = config["rally"]["coordinates"]
        
        # Set the fence using the loaded coordinates
        await set_rally(master, rally_coordinates)
        
        return {"status": f"Rally points set successfully for drone '{drone_id}'"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to set rally points: {str(e)}")

@app.post("/set_rally_all_drones")
async def set_rally_all_drones():
    successful_drones = []
    failed_drones = []

    if "rally" not in config or "coordinates" not in config["rally"]:
        raise HTTPException(status_code=404, detail="Rally coordinates not found in config file")
    
    rally_coordinates = config["rally"]["coordinates"]

    for drone_id, master in drone_connections.items():
        try:
            await set_rally(master, rally_coordinates)
            successful_drones.append(drone_id)
            await asyncio.sleep(1)
        except Exception as e:
            failed_drones.append({"drone_id": drone_id, "error": str(e)})

    if failed_drones:
        return {
            "status": "Some drones failed to set the rally points",
            "successful_drones": successful_drones,
            "failed_drones": failed_drones
        }
    else:
        return {"status": "Rally points set successfully for all drones", "successful_drones": successful_drones}

async def get_telemetry(master: mavutil.mavlink_connection) -> Telemetry:
    try:
        # create request data stream message
        request = dialect.MAVLink_request_data_stream_message(target_system=master.target_system,
                                                                target_component=master.target_component,
                                                                req_stream_id=0,
                                                                req_message_rate=10,
                                                                start_stop=1)

        # send request data stream message to the vehicle
        master.mav.send(request)
        
        while True:
            
            msg_global_position_int = master.recv_match(type=dialect.MAVLink_global_position_int_message.msgname, blocking=True)
            # msg_sys_status = master.recv_match(type=dialect.MAVLink_sys_status_message.msgname, blocking=True)
            # msg_gps = master.recv_match(type=dialect.MAVLink_gps_raw_int_message.msgname, blocking=True)

            if msg_global_position_int is None:
                raise ValueError("No global position telemetry message received")
            # if msg_sys_status is None:
                # raise ValueError("No system status telemetry message received")
            # if msg_gps is None:
                # raise ValueError("No raw GPS telemetry message received")

            latitude = msg_global_position_int.lat / 1e7
            longitude = msg_global_position_int.lon / 1e7
            altitude = msg_global_position_int.alt / 1000.0
            relative_altitude = msg_global_position_int.relative_alt / 1000.0
            heading = msg_global_position_int.hdg / 100.0
            # battery_remaining = msg_sys_status.battery_remaining
            # gps_fix = msg_gps.fix_type
            
            # Return telemetry data
            telemetry_data = Telemetry(
                latitude=latitude if latitude is not None else 0.0,
                longitude=longitude if longitude is not None else 0.0,
                altitude=altitude if altitude is not None else 0.0,
                relative_altitude=relative_altitude,
                heading=heading,
                # battery_remaining=battery_remaining,
                # gps_fix=gps_fix
            )
            return telemetry_data

    except Exception as e:
        print(f"Error retrieving telemetry data: {e}")
        raise

@app.get("/get_telemetry/{drone_id}", response_model=Telemetry)
async def get_telemetry_endpoint(drone_id: str):
    connect_drone_by_id(drone_id)
    master = drone_connections.get(drone_id)
    if not master:
        raise HTTPException(status_code=404, detail=f"Drone with ID {drone_id} not found")
    
    try:
        telemetry = await get_telemetry(master)
        return telemetry
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    
@app.get("/get_all_telemetry", response_model=List[DroneTelemetryResponse])
async def get_all_telemetry():
    all_telemetry = []
    
    for drone_id, master in drone_connections.items():
        connect_drone_by_id(drone_id)
        try:
            telemetry = await get_telemetry(master)
            all_telemetry.append({
                "drone_id": drone_id,
                "telemetry": telemetry
            })
        except Exception as e:
            all_telemetry.append({
                "drone_id": drone_id,
                "error": str(e)
            })
    
    return all_telemetry

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
