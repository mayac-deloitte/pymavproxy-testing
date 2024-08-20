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

# Define a Pydantic model for the mission plan
class MissionPlan(BaseModel):
    drone_id: str
    waypoints: List[Waypoint]

    @field_validator('waypoints', mode='before')
    def check_waypoints_not_empty(cls, v):
        if len(v) < 1:
            raise ValueError('The waypoints list must contain at least one waypoint.')
        return v
    
class TargetMissionRequest(BaseModel):
    center_lat: float
    center_lon: float

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



def send_mission_plan_and_start(drone_id: str, waypoints):
    master = drone_connections.get(drone_id)
    if not master:
        raise HTTPException(status_code=404, detail=f"Drone with ID {drone_id} not found")

    # Clear existing mission items
    master.waypoint_clear_all_send()

    # Send MISSION_COUNT message
    master.mav.mission_count_send(
        master.target_system,
        master.target_component,
        len(waypoints),
        mavutil.mavlink.MAV_MISSION_TYPE_MISSION
    )

    # Loop until MISSION_ACK is received
    while True:
        msg = master.recv_match(type=['MISSION_REQUEST', 'MISSION_ACK'], blocking=True)
        
        if msg.get_type() == 'MISSION_REQUEST':
            seq = msg.seq
            waypoint = waypoints[seq]

            master.mav.mission_item_int_send(
                master.target_system,
                master.target_component,
                seq,
                mavutil.mavlink.MAV_FRAME_GLOBAL_RELATIVE_ALT,
                waypoint.command,
                0,  # Current waypoint (0 or 1)
                1,  # Auto-continue to the next waypoint
                0, 0, 0, 0,  # Parameters (unused in this context)
                int(waypoint.latitude * 1e7),  # Latitude as an integer
                int(waypoint.longitude * 1e7),  # Longitude as an integer
                waypoint.altitude * 1000  # Altitude in millimeters
            )

        elif msg.get_type() == 'MISSION_ACK':
            if msg.type == mavutil.mavlink.MAV_MISSION_ACCEPTED:
                print(f"Mission upload to drone {drone_id} is successful")
                break
            else:
                raise HTTPException(status_code=500, detail=f"Mission upload to drone {drone_id} failed with type {msg.type}")

    # Ensure the drone is in AUTO mode
    set_mode(master)

@app.post("/upload_mission_to_location")
async def upload_mission_to_location(request: TargetMissionRequest):
    center_lat = request.center_lat
    center_lon = request.center_lon
    try:
        # Define a single waypoint for all drones
        waypoint = Waypoint(latitude=center_lat, longitude=center_lon, altitude=default_altitude, command=16)

        # Upload the same mission plan and start the mission for each drone
        for drone_id in drone_connections.keys():
            send_mission_plan_and_start(drone_id, [waypoint])

        return {"status": "Mission plans uploaded and started successfully for all drones"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

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
