from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, field_validator
from pymavlink import mavutil
import time
import math
import yaml
from typing import List, Optional

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
    heading: Optional[float] = None
    battery_voltage: Optional[float] = None
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

    # Ensure the drone is in GUIDE
    # D mode
    master.set_mode_guided()

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
async def upload_mission_triangle(center_lat: float, center_lon: float):
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
        # Wait for a new MAVLink message
        msg = master.recv_match(type=['GLOBAL_POSITION_INT', 'BATTERY_STATUS', 'GPS_RAW_INT'], timeout=10)
        if msg is None:
            raise ValueError("No telemetry message received")

        # Parse messages
        latitude = longitude = altitude = heading = battery_voltage = gps_fix = None
        
        if msg.get_type() == 'GLOBAL_POSITION_INT':
            latitude = msg.lat / 1e7
            longitude = msg.lon / 1e7
            altitude = msg.alt / 1000.0

        elif msg.get_type() == 'BATTERY_STATUS':
            battery_voltage = msg.voltages[0] / 1000.0  # Example, adjust based on actual message

        elif msg.get_type() == 'GPS_RAW_INT':
            gps_fix = msg.fix_type
        
        # Return telemetry data
        telemetry_data = Telemetry(
            latitude=latitude if latitude is not None else 0.0,
            longitude=longitude if longitude is not None else 0.0,
            altitude=altitude if altitude is not None else 0.0,
            heading=heading,
            battery_voltage=battery_voltage,
            gps_fix=gps_fix
        )
        return telemetry_data

    except Exception as e:
        print(f"Error retrieving telemetry data: {e}")
        raise

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
