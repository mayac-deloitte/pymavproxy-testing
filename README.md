# pymavproxy-testing

### FastAPI for Drone Swarm Using Non-Local Multi-Vehicle SITL

This project provides a FastAPI interface to control a drone swarm using non-local multi-vehicle SITL. Follow the steps below to set up and use the API.

## Setup Instructions

1. **Start the SITL Drone Swarm Simulation**
   - To start the simulation with `X` number of drones, navigate to `ArduPilot/ArduCopter` and run:
     ```shell
     sim_vehicle.py -v copter --count=X --auto-sysid --console --map
     ```

2. **Install Required Packages**
   - Navigate to the `/fast_api_drone` folder and install the necessary packages:
     ```shell
     pip install -r requirements.txt
     ```

3. **Configure the Application**
   - Specify network configurations, default flight values, and mission waypoints in the `config.yaml` file.

4. **Start the FastAPI Application**
   - Run the following command to start the FastAPI application:
     ```shell
     python3 -m uvicorn main:app --reload
     ```

## API Endpoints

1. **Connect to Drones**

   - **Connect All Drones**:
     ```shell
     curl -X POST "http://127.0.0.1:8000/connect_all_drones"
     ```

   - **Connect a Specific Drone** (e.g., `drone_1`):
     ```shell
     curl -X POST "http://127.0.0.1:8000/connect_drone" -H "Content-Type: application/json" -d '{"drone_id": "drone_1"}'
     ```

2. **Telemetry**

   - **Get Telemetry from All Drones**:
     ```shell
     curl -X GET "http://127.0.0.1:8000/get_all_telemetry"
     ```

   - **Get Telemetry from a Specific Drone** (e.g., `drone_1`):
     ```shell
     curl -X GET "http://127.0.0.1:8000/get_telemetry/drone_1"
     ```

3. **Control Drone Modes**

   - **Change Drone Mode** (e.g., set `drone_1` to `GUIDED` mode):
     ```shell
     curl -X POST "http://localhost:8000/update_drone_mode/drone_1/GUIDED" -H "Content-Type: application/json"
     ```

4. **Set Missions**

   - **Set a Mission for a Specific Drone** (e.g., `mission_1` for `drone_1`):
     ```shell
     curl -X POST "http://localhost:8000/set_mission/drone_1?mission_name=mission_1"
     ```

   - **Set the Same Mission for All Drones** (e.g., `mission_1`):
     ```shell
     curl -X POST "http://localhost:8000/set_mission_all_drones/mission_1"
     ```

5. **Set Fences**

   - **Set a Fence for a Specific Drone** (specified in `config.yaml`, e.g., `drone_1`):
     ```shell
     curl -X POST "http://localhost:8000/set_fence/drone_1"
     ```

   - **Set the Same Fence for All Drones**:
     ```shell
     curl -X POST "http://localhost:8000/set_fence_all_drones"
     ```

   - **Enable/Disable Fence for a Specific Drone** (e.g., enable the fence for `drone_1`):
     ```shell
     curl -X POST "http://localhost:8000/enable_fence/drone_1" -H "Content-Type: application/json" -d '{"fence_enable": "ENABLE"}'
     ```

   - **Enable/Disable Fence for All Drones** (e.g., disable the fence for all drones):
     ```shell
     curl -X POST "http://localhost:8000/enable_fence_all_drones" -H "Content-Type: application/json" -d '{"fence_enable": "DISABLE"}'
     ```

6. **Set Rally Points**

   - **Set Rally Points for a Specific Drone** (specified in `config.yaml`, e.g., `drone_1`):
     ```shell
     curl -X POST "http://localhost:8000/set_rally/drone_1"
     ```

   - **Set the Same Rally Points for All Drones**:
     ```shell
     curl -X POST "http://localhost:8000/set_rally_all_drones"
     ```

---
