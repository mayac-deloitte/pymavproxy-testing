from fastapi import FastAPI, HTTPException, Depends, Response
from pydantic import BaseModel
from pymavlink import mavutil
import time
import asyncio
import yaml
from typing import List, Optional, Dict
import pymavlink.dialects.v20.all as dialect
# import speech_recognition as sr
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse
import re

app = FastAPI()

app.mount("/static", StaticFiles(directory="static"), name="static")

# Dependency to load and provide the configuration
def get_config():
    with open("config.yaml", "r") as config_file:
        return yaml.safe_load(config_file)

# Dependency to manage drone connections
drone_connections: Dict[str, mavutil.mavlink_connection] = {}

def get_drone_connections():
    return drone_connections

class Waypoint(BaseModel):
    latitude: float
    longitude: float
    altitude: float
    command: int  # MAVLink command (e.g., MAV_CMD_NAV_WAYPOINT, MAV_CMD_NAV_TAKEOFF)

class Telemetry(BaseModel):
    latitude: float
    longitude: float
    altitude: float
    velocity: float
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

class ChatCommand(BaseModel):
    command: str

def is_authorized_system_id(drone_id: str, system_id: int, config: Dict) -> bool:
    """Check if the system ID matches the one in the config."""
    expected_system_id = config["drones"][drone_id].get("system_id")
    return system_id == expected_system_id

def connect_drone_by_id(drone_id: str, config: Dict, drone_connections: Dict):
    """Function to connect to a drone by its ID."""
    try:
        drone_config = config["drones"].get(drone_id)
        if drone_config is None:
            raise HTTPException(status_code=404, detail=f"Drone ID {drone_id} not found in config")

        connection_string = drone_config.get("connection_string")
        if connection_string is None:
            raise HTTPException(status_code=400, detail=f"Connection string for drone {drone_id} is missing")

        if drone_id not in drone_connections:
            master = mavutil.mavlink_connection(connection_string)
            master.wait_heartbeat()

            system_id = master.target_system
            if not is_authorized_system_id(drone_id, system_id, config):
                raise HTTPException(status_code=403, detail="Unauthorized system ID for this drone")

            # Store the connection if successful
            drone_connections[drone_id] = master

        return {"status": f"Drone {drone_id} connected successfully"}

    except KeyError:
        raise HTTPException(status_code=404, detail=f"Drone ID {drone_id} not found in config")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/connect_drone")
async def connect_drone_endpoint(request: ConnectDroneRequest, config: Dict = Depends(get_config), drone_connections: Dict = Depends(get_drone_connections)):
    """Endpoint to connect to a single drone by ID."""
    return connect_drone_by_id(request.drone_id, config, drone_connections)

@app.post("/connect_all_drones")
async def connect_all_drones_endpoint(config: Dict = Depends(get_config), drone_connections: Dict = Depends(get_drone_connections)):
    """Endpoint to connect to all drones specified in the config."""
    connected_drones = []
    failed_drones = []

    # Iterate through each drone in the config
    for drone_id in config["drones"]:
        try:
            response = connect_drone_by_id(drone_id, config, drone_connections)
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

async def set_mode(master, flight_mode: str):
    # Get supported flight modes
    flight_modes = master.mode_mapping()

    if flight_mode not in flight_modes:
        raise RuntimeError(f"{flight_mode} is not supported")

    # Create change mode message
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

    # Send the mode change message
    master.mav.send(set_mode_message)

    try:
        # Use asyncio.to_thread to run the blocking recv_match call in a non-blocking way
        mav_message = await asyncio.to_thread(
            master.recv_match, type=dialect.MAVLink_command_ack_message.msgname, blocking=True
        )

        # Convert the MAVLink message to a dictionary
        message = mav_message.to_dict()

        if message["command"] == dialect.MAV_CMD_DO_SET_MODE:
            if message["result"] == dialect.MAV_RESULT_ACCEPTED:
                print(f"Changing mode to {flight_mode} accepted by the vehicle")
                return "accepted"
            else:
                print(f"Changing mode to {flight_mode} failed")
                return "failed"

    except asyncio.TimeoutError:
        print(f"Timeout while waiting for mode change to {flight_mode}")
        return "timeout"

@app.post("/set_mode/{drone_id}/{flight_mode}")
async def set_mode_endpoint(drone_id: str, flight_mode: str, drone_connections: Dict = Depends(get_drone_connections)):
    master = drone_connections.get(drone_id)
    if not master:
        raise HTTPException(status_code=404, detail=f"Drone with ID {drone_id} not found")
    
    try:
        result = await set_mode(master, flight_mode.upper())
        if result == "accepted":
            return {
                "status": f"Mode change to {flight_mode.upper()} successful for drone {drone_id}"
            }
        elif result == "timeout":
            return {
                "status": f"Timeout while changing mode to {flight_mode.upper()} for drone {drone_id}"
            }
        else:
            return {
                "status": f"Mode change to {flight_mode.upper()} failed for drone {drone_id}"
            }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/set_mode_all_drones/{flight_mode}")
async def set_mode_all_drones(flight_mode: str, drone_connections: Dict = Depends(get_drone_connections)):
    results = {}
    
    for drone_id, master in drone_connections.items():
        try:
            # Call the set_mode function for each drone
            result = await set_mode(master, flight_mode.upper())
            if result == "accepted":
                results[drone_id] = f"Mode change to {flight_mode.upper()} successful"
            elif result == "timeout":
                results[drone_id] = f"Timeout while changing mode to {flight_mode.upper()}"
            else:
                results[drone_id] = f"Mode change to {flight_mode.upper()} failed"
        except Exception as e:
            # If any exception occurs, log the error for that specific drone
            results[drone_id] = f"Error: {str(e)}"

    # Return a dictionary with the results for each drone
    return {
        "status": results
    }

async def set_mission_and_start(master, target_locations: List[Waypoint]):
    # Send the mission count message asynchronously
    await asyncio.to_thread(master.mav.send, dialect.MAVLink_mission_count_message(
        target_system=master.target_system,
        target_component=master.target_component,
        count=len(target_locations) + 2,
        mission_type=dialect.MAV_MISSION_TYPE_MISSION
    ))

    # Loop until we receive a valid MISSION_ACK message
    while True:
        message = await asyncio.to_thread(master.recv_match, blocking=True)
        message = message.to_dict()

        if message["mavpackettype"] == dialect.MAVLink_mission_request_message.msgname:
            if message["mission_type"] == dialect.MAV_MISSION_TYPE_MISSION:
                seq = message["seq"]

                # Create the appropriate mission item message
                if seq == 0:
                    mission_item_message = dialect.MAVLink_mission_item_int_message(
                        target_system=master.target_system,
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
                        mission_type=dialect.MAV_MISSION_TYPE_MISSION
                    )
                elif seq == 1:
                    mission_item_message = dialect.MAVLink_mission_item_int_message(
                        target_system=master.target_system,
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
                        mission_type=dialect.MAV_MISSION_TYPE_MISSION
                    )
                else:
                    waypoint = target_locations[seq - 2]  # Adjust for home and takeoff locations
                    mission_item_message = dialect.MAVLink_mission_item_int_message(
                        target_system=master.target_system,
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
                        x=max(min(int(waypoint.latitude * 1e7), 2147483647), -2147483648),
                        y=max(min(int(waypoint.longitude * 1e7), 2147483647), -2147483648),
                        z=waypoint.altitude,
                        mission_type=dialect.MAV_MISSION_TYPE_MISSION
                    )

                # Send the mission item message asynchronously
                await asyncio.to_thread(master.mav.send, mission_item_message)

        # Check if the message is MISSION_ACK
        elif message["mavpackettype"] == dialect.MAVLink_mission_ack_message.msgname:
            if message["mission_type"] == dialect.MAV_MISSION_TYPE_MISSION and message["type"] == dialect.MAV_MISSION_ACCEPTED:
                print("Mission upload is successful")
                break

    # Set flight mode to AUTO
    FLIGHT_MODE = "AUTO"
    flight_modes = master.mode_mapping()

    if FLIGHT_MODE not in flight_modes:
        raise RuntimeError(f"{FLIGHT_MODE} is not supported")

    # Create and send the change mode message
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

    await asyncio.to_thread(master.mav.send, set_mode_message)

    # Wait for mode change acknowledgment
    while True:
        message = await asyncio.to_thread(master.recv_match, type=dialect.MAVLink_command_ack_message.msgname, blocking=True)
        message = message.to_dict()
        if message["command"] == dialect.MAV_CMD_DO_SET_MODE:
            if message["result"] == dialect.MAV_RESULT_ACCEPTED:
                print(f"Changing mode to {FLIGHT_MODE} accepted by the vehicle")
            else:
                print(f"Changing mode to {FLIGHT_MODE} failed")
            break

    # Arm the vehicle
    vehicle_arm_message = dialect.MAVLink_command_long_message(
        target_system=master.target_system,
        target_component=master.target_component,
        command=dialect.MAV_CMD_COMPONENT_ARM_DISARM,
        confirmation=0,
        param1=1,  # VEHICLE_ARM
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
        await asyncio.to_thread(master.mav.send, vehicle_arm_message)
        ack_message = await asyncio.to_thread(master.recv_match, type=dialect.MAVLink_command_ack_message.msgname, blocking=True)
        ack_message = ack_message.to_dict()

        # Check if the arm command was accepted
        if ack_message["result"] == dialect.MAV_RESULT_ACCEPTED and ack_message["command"] == dialect.MAV_CMD_COMPONENT_ARM_DISARM:
            print("Arm command accepted, waiting for the vehicle to be armed...")

            # Monitor the heartbeat for arming status
            while True:
                heartbeat = await asyncio.to_thread(master.recv_match, type=dialect.MAVLink_heartbeat_message.msgname, blocking=True)
                heartbeat = heartbeat.to_dict()

                # Check if the vehicle is armed
                armed = heartbeat["base_mode"] & dialect.MAV_MODE_FLAG_SAFETY_ARMED
                if armed:
                    print("Vehicle is armed!")
                    return  # Exit the function once the vehicle is armed
        else:
            print("Failed to arm the vehicle. Retrying...")

        await asyncio.sleep(10)  # Sleep for a while before retrying

@app.post("/set_mission/{drone_id}")
async def set_mission_endpoint(drone_id: str, mission_name: str, config: Dict = Depends(get_config), drone_connections: Dict = Depends(get_drone_connections)):
    try:
        if mission_name not in config["waypoints"]:
            raise HTTPException(status_code=404, detail=f"Mission '{mission_name}' not found in config")
        
        mission_waypoints = [Waypoint(**wp) for wp in config["waypoints"][mission_name]]
        master = drone_connections.get(drone_id)
        if not master:
            raise HTTPException(status_code=404, detail=f"Drone with ID {drone_id} not found")

        # This is correct, assuming set_mission_and_start is async
        await set_mission_and_start(master, mission_waypoints)

        return {"status": f"Mission '{mission_name}' auto mode set successfully for drone '{drone_id}' and is armed"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to set mission auto mode: {str(e)}")

@app.post("/set_mission_all_drones/{mission_name}")
async def set_mission_all_drones_endpoint(mission_name: str, config: Dict = Depends(get_config), drone_connections: Dict = Depends(get_drone_connections)):
    successful_drones = []
    failed_drones = []

    for drone_id, master in drone_connections.items():
        try:
            # Load the waypoints for the specified mission from the config
            if mission_name not in config["waypoints"]:
                raise HTTPException(status_code=404, detail=f"Mission '{mission_name}' not found in config")
            
            mission_waypoints = [Waypoint(**wp) for wp in config["waypoints"][mission_name]]
            
            # Await the mission setting for each drone
            await set_mission_and_start(master, mission_waypoints)
            successful_drones.append(drone_id)

            # Add a delay between missions
            await asyncio.sleep(config["settings"]["separation_time"])

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
    # introduce FENCE_TOTAL and FENCE_ACTION as byte arrays
    FENCE_TOTAL = "FENCE_TOTAL".encode(encoding="utf-8")
    FENCE_ACTION = "FENCE_ACTION".encode(encoding="utf8")
    PARAM_INDEX = -1

    # Request FENCE_ACTION parameter
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

    # Set FENCE_ACTION to none
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

    # Reset FENCE_TOTAL to 0
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

    # Set FENCE_TOTAL to the number of fence coordinates
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
                print(f"FENCE_TOTAL set to {len(fence_coordinates)} successfully")
                break
            else:
                print(f"Failed to set FENCE_TOTAL to {len(fence_coordinates)}")

    # Upload fence points
    idx = 0
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

    # Reset FENCE_ACTION to the original value
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
                print(f"FENCE_ACTION set to original value {fence_action_original} successfully")
                break
            else:
                print(f"Failed to set FENCE_ACTION to original value {fence_action_original}")

@app.post("/set_fence/{drone_id}")
async def set_fence_endpoint(drone_id: str, config: Dict = Depends(get_config), drone_connections: Dict = Depends(get_drone_connections)):
    try:
        # Get the drone connection from the dependency
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
async def set_fence_all_drones_endpoint(config: Dict = Depends(get_config), drone_connections: Dict = Depends(get_drone_connections)):
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
async def enable_fence_endpoint(drone_id: str, request: FenceEnableRequest, drone_connections: Dict = Depends(get_drone_connections)):

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
async def enable_fence_all_drones_endpoint(request: FenceEnableRequest, drone_connections: Dict = Depends(get_drone_connections)):
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

@app.post("/set_rally/{drone_id}")
async def set_rally_endpoint(drone_id: str, config: Dict = Depends(get_config), drone_connections: Dict = Depends(get_drone_connections)):
    try:
        # Get the drone connection from the global dictionary
        master = drone_connections.get(drone_id)
        if not master:
            raise HTTPException(status_code=404, detail=f"Drone with ID {drone_id} not found")
        
        # Load the rally coordinates from the config file
        if "rally" not in config or "coordinates" not in config["rally"]:
            raise HTTPException(status_code=404, detail="Rally coordinates not found in config file")
        
        rally_coordinates = config["rally"]["coordinates"]
        
        # Set the rally points using the loaded coordinates
        await set_rally(master, rally_coordinates)
        
        return {"status": f"Rally points set successfully for drone '{drone_id}'"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to set rally points: {str(e)}")

@app.post("/set_rally_all_drones")
async def set_rally_all_drones(config: Dict = Depends(get_config), drone_connections: Dict = Depends(get_drone_connections)):
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
            
            msg_global_position_int = master.recv_match(type=dialect.MAVLink_global_position_int_message.msgname)
            msg_sys_status = master.recv_match(type=dialect.MAVLink_battery_status_message.msgname)
            msg_gps = master.recv_match(type=dialect.MAVLink_gps_raw_int_message.msgname)

            if msg_global_position_int is None:
                raise ValueError("No global position telemetry message received")
            if msg_sys_status is None:
                raise ValueError("No system status telemetry message received")
            if msg_gps is None:
                raise ValueError("No raw GPS telemetry message received")

            latitude = msg_global_position_int.lat / 1e7
            longitude = msg_global_position_int.lon / 1e7
            altitude = msg_global_position_int.alt / 1000.0
            relative_altitude = msg_global_position_int.relative_alt / 1000.0
            heading = msg_global_position_int.hdg / 100.0
            velocity = msg_gps.vel / 100.0
            battery_remaining = msg_sys_status.battery_remaining
            gps_fix = msg_gps.fix_type
            
            # Return telemetry data
            telemetry_data = Telemetry(
                latitude=latitude if latitude is not None else 0.0,
                longitude=longitude if longitude is not None else 0.0,
                altitude=altitude if altitude is not None else 0.0,
                velocity=velocity if velocity is not None else 0.0,
                relative_altitude=relative_altitude,
                heading=heading,
                battery_remaining=battery_remaining,
                gps_fix = gps_fix
            )
            return telemetry_data

    except Exception as e:
        print(f"Error retrieving telemetry data: {e}")
        raise

@app.get("/get_telemetry/{drone_id}", response_model=Telemetry)
async def get_telemetry_endpoint(response: Response, drone_id: str, drone_connections: Dict = Depends(get_drone_connections)):
    master = drone_connections.get(drone_id)
    if not master:
        raise HTTPException(status_code=404, detail=f"Drone with ID {drone_id} not found")
    
    # Add cache-control headers to prevent caching
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    
    try:
        telemetry = await get_telemetry(master)
        return telemetry
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    
@app.get("/get_all_telemetry", response_model=List[DroneTelemetryResponse])
async def get_all_telemetry(response: Response, drone_connections: Dict = Depends(get_drone_connections)):
    # Add cache-control headers to prevent caching
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    
    all_telemetry = []
    for drone_id, master in drone_connections.items():
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

# Scalable command dictionary with exact drone names and mission names like mission_1, mission_2
commands = {
    # Connection commands
    r"connect drone (drone_\w+)": {"function": connect_drone_by_id, "params": {"drone_id": None}},
    r"connect all drones": {"function": connect_all_drones_endpoint, "params": {}},

    # Mission commands with specific mission name format (e.g., mission_1, mission_2)
    r"start mission (mission_\d+) for drone (drone_\w+)": {"function": set_mission_endpoint, "params": {"drone_id": None, "mission_name": None}},
    r"start mission (mission_\d+) for all drones": {"function": set_mission_all_drones_endpoint, "params": {"mission_name": None}},

    # Fence commands
    r"enable fence for drone (drone_\w+)": {"function": enable_fence_endpoint, "params": {"drone_id": None, "request": FenceEnableRequest(fence_enable="ENABLE")}},
    r"enable fence (\w+) for all drones": {"function": enable_fence_all_drones_endpoint, "params": {"request": FenceEnableRequest(fence_enable="ENABLE")}},
    r"set fence for drone (drone_\w+)": {"function": set_fence_endpoint, "params": {"drone_id": None}},
    r"set fence for all drones": {"function": set_fence_all_drones_endpoint, "params": {}},

    # Rally commands
    r"set rally for drone (drone_\w+)": {"function": set_rally_endpoint, "params": {"drone_id": None}},
    r"set rally for all drones": {"function": set_rally_all_drones, "params": {}},

    # Mode change commands
    r"set mode (\w+) for drone (drone_\w+)": {"function": set_mode_endpoint, "params": {"drone_id": None, "flight_mode": None}},
    r"set mode (\w+) for all drones": {"function": set_mode_all_drones, "params": {"flight_mode": None}},

    # Telemetry commands
    r"get telemetry for drone (drone_\w+)": {"function": get_telemetry_endpoint, "params": {"drone_id": None}},
    r"get telemetry for all drones": {"function": get_all_telemetry, "params": {}}
}

# Preprocessing function to handle voice recognition quirks
def preprocess_command(command: str) -> str:
    # Replace common voice recognition errors
    command = command.lower()
    command = command.replace("underscore", "_")  # Convert 'underscore' to '_'
    
    # Handle numbers in words
    number_words = {
        "one": "1",
        "two": "2",
        "three": "3",
        "four": "4",
        "five": "5",
        "six": "6",
        "seven": "7",
        "eight": "8",
        "nine": "9",
        "zero": "0"
    }
    
    for word, num in number_words.items():
        command = command.replace(word, num)  # Convert number words to digits

    return command

async def trigger_action(command: str, drone_connections: Dict = Depends(get_drone_connections), config: Dict = Depends(get_config)):
    # Preprocess the command to handle voice quirks
    command = preprocess_command(command)

    for pattern, command_info in commands.items():
        match = re.match(pattern, command)
        if match:
            params = command_info.get("params", {}).copy()
            groups = match.groups()
            
            # Dynamically set drone_id and mission_name based on the matched groups
            if "drone_id" in params:
                params["drone_id"] = groups[-1]  # The last group is the drone name
            if "mission_name" in params:
                params["mission_name"] = groups[0]  # The first group is the mission name

            function = command_info["function"]

            try:
                # Handle async functions
                if asyncio.iscoroutinefunction(function):
                    result = await function(drone_connections=drone_connections, config=config, **params)
                else:
                    result = function(drone_connections=drone_connections, config=config, **params)
                print(f"Triggered {command} with result: {result}")
                return {"status": "success", "result": result}
            except Exception as e:
                print(f"Error triggering {command}: {e}")
                return {"status": "error", "message": str(e)}
    print(f"Command '{command}' not found in command list.")
    return {"status": "error", "message": "Command not found"}

@app.post("/trigger_command")
async def trigger_command(command: ChatCommand, drone_connections: Dict = Depends(get_drone_connections), config: Dict = Depends(get_config)):
    # Preprocess and trigger the action
    response = await trigger_action(command.command.lower(), drone_connections=drone_connections, config=config)
    return response

@app.get("/chatbot", response_class=HTMLResponse)
async def get_chatbot():
    with open("static/chatbot.html") as f:
        return f.read()

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)