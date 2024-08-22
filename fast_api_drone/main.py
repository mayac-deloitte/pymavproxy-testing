from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, field_validator
from pymavlink import mavutil
import time
import math
import yaml
from typing import List, Optional
import pymavlink.dialects.v20.all as dialect

app = FastAPI()

class ConnectDroneRequest(BaseModel):
    drone_id: str

# Load configuration from YAML
with open("config.yaml", "r") as config_file:
    config = yaml.safe_load(config_file)

# Access the configuration
drone_connections = {}
min_separation_distance = config["settings"]["min_separation_distance"]
default_altitude = config["settings"]["default_altitude"]
default_side_length = config["settings"]["default_side_length"]

# Define a Pydantic model for a single waypoint
class Waypoint(BaseModel):
    latitude: float
    longitude: float
    altitude: float
    command: int  # MAVLink command (e.g., MAV_CMD_NAV_WAYPOINT, MAV_CMD_NAV_TAKEOFF)

# Define a Pydantic model for telemetry data
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

@app.post("/connect_drone")
async def connect_drone(request: ConnectDroneRequest):
    drone_id = request.drone_id
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

@app.post("/connect_all_drones")
async def connect_all_drones():
    connected_drones = []
    failed_drones = []

    for drone_id in config["drones"]:
        try:
            connection_string = config["drones"][drone_id]
            if drone_id not in drone_connections:
                master = mavutil.mavlink_connection(connection_string)
                master.wait_heartbeat()
                drone_connections[drone_id] = master
                connected_drones.append(drone_id)
            else:
                connected_drones.append(drone_id)
        except Exception as e:
            failed_drones.append((drone_id, str(e)))

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
    master = drone_connections.get(drone_id)
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

def set_mission(master, target_locations: List[Waypoint]):

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
        set_mission(master, mission_waypoints)
        return {"status": f"Mission '{mission_name}' auto mode set successfully for drone '{drone_id}' and is armed"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to set mission auto mode: {str(e)}")

# Define the get_telemetry function here
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
        
        # Wait for a new MAVLink message
        msg_glboal_position = master.recv_match(type='GLOBAL_POSITION_INT', timeout=10, blocking = True)
        msg_sys_status = master.recv_match(type='SYS_STATUS', timeout=10, blocking = True)
        msg_gps = master.recv_match(type='GPS_RAW_INT', timeout=10, blocking = True)

        if msg_glboal_position is None:
            raise ValueError("No global position telemetry message received")
        if msg_sys_status is None:
            raise ValueError("No system status telemetry message received")
        if msg_gps is None:
            raise ValueError("No raw GPS telemetry message received")

        latitude = msg_glboal_position.lat / 1e7
        longitude = msg_glboal_position.lon / 1e7
        altitude = msg_glboal_position.alt / 1000.0
        relative_altitude = msg_glboal_position.relative_alt / 1000.0
        heading = msg_glboal_position.hdg / 100.0

        battery_remaining = msg_sys_status.battery_remaining

        gps_fix = msg_gps.fix_type
        
        # Return telemetry data
        telemetry_data = Telemetry(
            latitude=latitude if latitude is not None else 0.0,
            longitude=longitude if longitude is not None else 0.0,
            altitude=altitude if altitude is not None else 0.0,
            relative_altitude=relative_altitude,
            heading=heading,
            battery_remaining=battery_remaining,
            gps_fix=gps_fix
        )
        return telemetry_data

    except Exception as e:
        print(f"Error retrieving telemetry data: {e}")
        raise

@app.get("/get_telemetry/{drone_id}", response_model=Telemetry)
async def get_telemetry_endpoint(drone_id: str):
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
