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
    
class TriangleMissionRequest(BaseModel):
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

def set_mode_guided(master):
    set_mode_message = dialect.MAVLink_command_long_message(
        target_system=master.target_system,
        target_component=master.target_component,
        command=dialect.MAV_CMD_DO_SET_MODE,
        confirmation=0,
        param1=dialect.MAV_MODE_FLAG_CUSTOM_MODE_ENABLED,
        param2="GUIDED",
        param3=0,
        param4=0,
        param5=0,
        param6=0,
        param7=0)
    
    master.mav.send(set_mode_message)

def calculate_triangle_waypoints(center_lat, center_lon, altitude, side_length, separation_distance):
    waypoints = []
    angle_offset = 60  # degrees

    for i in range(3):
        angle = math.radians(i * angle_offset)
        dx = (side_length + separation_distance) * math.cos(angle) / 111139  # convert meters to degrees latitude
        dy = (side_length + separation_distance) * math.sin(angle) / (111139 * math.cos(math.radians(center_lat)))  # adjust for longitude
        lat = center_lat + dx
        lon = center_lon + dy
        waypoints.append(Waypoint(latitude=lat, longitude=lon, altitude=altitude, command=16))  # MAV_CMD_NAV_WAYPOINT
    
    return waypoints

def send_mission_plan(drone_id: str, waypoints):
    master = drone_connections.get(drone_id)
    if not master:
        raise HTTPException(status_code=404, detail=f"Drone with ID {drone_id} not found")

    # Ensure the drone is in GUIDED mode
    set_mode_guided(master)

    # Clear existing mission items
    master.waypoint_clear_all_send()

    for i, waypoint in enumerate(waypoints):
        # Send each waypoint or command
        master.mav.mission_item_send(
            master.target_system, master.target_component, i,
            mavutil.mavlink.MAV_FRAME_GLOBAL_RELATIVE_ALT,
            waypoint.command,  # Command (e.g., MAV_CMD_NAV_WAYPOINT, MAV_CMD_NAV_TAKEOFF)
            0, 1, 0, 0, 0, 0, waypoint.latitude, waypoint.longitude, waypoint.altitude
        )
        time.sleep(1)  # A short delay between commands

    # Send mission start command
    master.mav.command_long_send(
        master.target_system, master.target_component,
        mavutil.mavlink.MAV_CMD_MISSION_START,
        0, 0, 0, 0, 0, 0, 0, 0, 0
    )

@app.post("/upload_mission_triangle")
async def upload_mission_triangle(request: TriangleMissionRequest):

    center_lat = request.center_lat
    center_lon = request.center_lon
    try:
        # Calculate the triangle waypoints for each drone with safe separation
        waypoints_1 = calculate_triangle_waypoints(center_lat, center_lon, default_altitude, default_side_length, min_separation_distance)
        waypoints_2 = calculate_triangle_waypoints(center_lat, center_lon, default_altitude, default_side_length, min_separation_distance)
        waypoints_3 = calculate_triangle_waypoints(center_lat, center_lon, default_altitude, default_side_length, min_separation_distance)
        
        # Upload mission plans for each drone
        send_mission_plan('drone_1', waypoints_1)
        send_mission_plan('drone_2', waypoints_2)
        send_mission_plan('drone_3', waypoints_3)

        return {"status": "Mission plans uploaded successfully to all drones with safe separation"}
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
            relative_altitude=relative_altitude if relative_altitude is not None else 0.0,
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
