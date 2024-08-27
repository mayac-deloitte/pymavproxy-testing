# pymavproxy-testing

### FastAPI for Drone Swarm Using Non-Local Multi-Vehicle SITL

This project provides a FastAPI interface to control a drone swarm using non-local multi-vehicle SITL. Follow the steps below to set up and use the API.

## Setup Instructions

1. **Start the SITL Drone Swarm Simulation**
   - To start the simulation with `X` number of drones, navigate to `ArduPilot/ArduCopter` and run:
     - **Bash:**
       ```bash
       sim_vehicle.py -v copter --count=X --auto-sysid --console --map
       ```
     - **PowerShell:**
       ```powershell
       .\Tools\autotest\sim_vehicle.py -v ArduCopter --count=X --auto-sysid --console --map
       ```

2. **Install Required Packages**
   - Navigate to the `/fast_api_drone` folder and install the necessary packages:
     - **Bash/PowerShell:**
       ```bash
       pip install -r requirements.txt
       ```

3. **Configure the Application**
   - Specify network configurations, default flight values, and mission waypoints in the `config.yaml` file.

4. **Start the FastAPI Application**
   - Run the following command to start the FastAPI application:
     - **Bash/PowerShell:**
       ```bash
       python -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload
       ```

## API Endpoints

Note. If connecting to the API non-locally, replace `localhost` with the appropriate IP address.

### 1. **Connect to Dronesm (REQUIRED)**

   - **Connect All Drones:**
     - **Bash:**
       ```bash
       curl -X POST "http://localhost:8000/connect_all_drones"
       ```
     - **PowerShell:**
       ```powershell
       Invoke-WebRequest -Uri "http://localhost:8000/connect_all_drones" -Method Post
       ```

   - **Connect a Specific Drone** (e.g., `drone_1`):
     - **Bash:**
       ```bash
       curl -X POST "http://localhost:8000/connect_drone" -H "Content-Type: application/json" -d '{"drone_id": "drone_1"}'
       ```
     - **PowerShell:**
       ```powershell
       $body = '{"drone_id": "drone_1"}'
       Invoke-WebRequest -Uri "http://localhost:8000/connect_drone" -Method Post -ContentType "application/json" -Body $body
       ```

### 2. **Telemetry**

   - **Get Telemetry from All Drones:**
     - **Bash:**
       ```bash
       curl -X GET "http://localhost:8000/get_all_telemetry"
       ```
     - **PowerShell:**
       ```powershell
       Invoke-WebRequest -Uri "http://localhost:8000/get_all_telemetry" -Method Get
       ```

   - **Get Telemetry from a Specific Drone** (e.g., `drone_1`):
     - **Bash:**
       ```bash
       curl -X GET "http://localhost:8000/get_telemetry/drone_1"
       ```
     - **PowerShell:**
       ```powershell
       Invoke-WebRequest -Uri "http://localhost:8000/get_telemetry/drone_1" -Method Get
       ```

### 3. **Control Drone Modes**

   - **Change Drone Mode** (e.g., set `drone_1` to `GUIDED` mode):
     - **Bash:**
       ```bash
       curl -X POST "http://localhost:8000/update_drone_mode/drone_1/GUIDED" -H "Content-Type: application/json"
       ```
     - **PowerShell:**
       ```powershell
       Invoke-WebRequest -Uri "http://localhost:8000/update_drone_mode/drone_1/GUIDED" -Method Post -ContentType "application/json"
       ```

### 4. **Set Missions**

   - **Set a Mission for a Specific Drone** (e.g., `mission_1` for `drone_1`):
     - **Bash:**
       ```bash
       curl -X POST "http://localhost:8000/set_mission/drone_1?mission_name=mission_1"
       ```
     - **PowerShell:**
       ```powershell
       Invoke-WebRequest -Uri "http://localhost:8000/set_mission/drone_1?mission_name=mission_1" -Method Post
       ```

   - **Set the Same Mission for All Drones** (e.g., `mission_1`):
     - **Bash:**
       ```bash
       curl -X POST "http://localhost:8000/set_mission_all_drones/mission_1"
       ```
     - **PowerShell:**
       ```powershell
       Invoke-WebRequest -Uri "http://localhost:8000/set_mission_all_drones/mission_1" -Method Post
       ```

### 5. **Set Fences**

   - **Set a Fence for a Specific Drone** (specified in `config.yaml`, e.g., `drone_1`):
     - **Bash:**
       ```bash
       curl -X POST "http://localhost:8000/set_fence/drone_1"
       ```
     - **PowerShell:**
       ```powershell
       Invoke-WebRequest -Uri "http://localhost:8000/set_fence/drone_1" -Method Post
       ```

   - **Set the Same Fence for All Drones**:
     - **Bash:**
       ```bash
       curl -X POST "http://localhost:8000/set_fence_all_drones"
       ```
     - **PowerShell:**
       ```powershell
       Invoke-WebRequest -Uri "http://localhost:8000/set_fence_all_drones" -Method Post
       ```

   - **Enable/Disable Fence for a Specific Drone** (e.g., enable the fence for `drone_1`):
     - **Bash:**
       ```bash
       curl -X POST "http://localhost:8000/enable_fence/drone_1" -H "Content-Type: application/json" -d '{"fence_enable": "ENABLE"}'
       ```
     - **PowerShell:**
       ```powershell
       $body = '{"fence_enable": "ENABLE"}'
       Invoke-WebRequest -Uri "http://localhost:8000/enable_fence/drone_1" -Method Post -ContentType "application/json" -Body $body
       ```

   - **Enable/Disable Fence for All Drones** (e.g., disable the fence for all drones):
     - **Bash:**
       ```bash
       curl -X POST "http://localhost:8000/enable_fence_all_drones" -H "Content-Type: application/json" -d '{"fence_enable": "DISABLE"}'
       ```
     - **PowerShell:**
       ```powershell
       $body = '{"fence_enable": "DISABLE"}'
       Invoke-WebRequest -Uri "http://localhost:8000/enable_fence_all_drones" -Method Post -ContentType "application/json" -Body $body
       ```

### 6. **Set Rally Points**

   - **Set Rally Points for a Specific Drone** (specified in `config.yaml`, e.g., `drone_1`):
     - **Bash:**
       ```bash
       curl -X POST "http://localhost:8000/set_rally/drone_1"
       ```
     - **PowerShell:**
       ```powershell
       Invoke-WebRequest -Uri "http://localhost:8000/set_rally/drone_1" -Method Post
       ```

   - **Set the Same Rally Points for All Drones**:
     - **Bash:**
       ```bash
       curl -X POST "http://localhost:8000/set_rally_all_drones"
       ```
     - **PowerShell:**
       ```powershell
       Invoke-WebRequest -Uri "http://localhost:8000/set_rally_all_drones" -Method Post
       ```
---

## Expected Outputs

Here’s what you can expect as output from each of the `curl` commands listed in the API Endpoints section above:

1. **Connect All Drones**
   ```bash
   curl -X POST "http://localhost:8000/connect_all_drones"
   ```
   **Output:**
   ```json
   {
       "status": "All drones connected successfully",
       "connected_drones": ["drone_1", "drone_2", "drone_3"],
       "failed_drones": []
   }
   ```
   If some drones fail to connect, the `failed_drones` list will contain the drone IDs and error messages.

2. **Connect a Specific Drone**
   ```bash
   curl -X POST "http://localhost:8000/connect_drone" -H "Content-Type: application/json" -d '{"drone_id": "drone_1"}'
   ```
   **Output:**
   ```json
   {
       "status": "Drone drone_1 connected successfully"
   }
   ```
   If the drone fails to connect, you’ll receive an error message in the `detail` field.

3. **Get Telemetry from All Drones**
   ```bash
   curl -X GET "http://localhost:8000/get_all_telemetry"
   ```
   **Output:**
   ```json
   [
       {
           "drone_id": "drone_1",
           "telemetry": {
               "latitude": 37.7749,
               "longitude": -122.4194,
               "altitude": 100.0,
               "relative_altitude": 50.0,
               "heading": 90.0,
               "battery_remaining": 90,
               "gps_fix": 3
           }
       },
       {
           "drone_id": "drone_2",
           "telemetry": {
               "latitude": 37.7750,
               "longitude": -122.4195,
               "altitude": 100.0,
               "relative_altitude": 50.0,
               "heading": 90.0,
               "battery_remaining": 85,
               "gps_fix": 3
           }
       }
   ]
   ```
   If any drone fails to provide telemetry, the `telemetry` field will be `null` with an `error` field explaining why.

4. **Get Telemetry from a Specific Drone**
   ```bash
   curl -X GET "http://localhost:8000/get_telemetry/drone_1"
   ```
   **Output:**
   ```json
   {
       "latitude": 37.7749,
       "longitude": -122.4194,
       "altitude": 100.0,
       "relative_altitude": 50.0,
       "heading": 90.0,
       "battery_remaining": 90,
       "gps_fix": 3
   }
   ```
   If telemetry retrieval fails, you’ll receive a `500` status code with an error message.

5. **Change Drone Mode**
   ```bash
   curl -X POST "http://localhost:8000/update_drone_mode/drone_1/GUIDED" -H "Content-Type: application/json"
   ```
   **Output:**
   ```json
   {
       "status": "Mode change successful: STABILIZE -> GUIDED"
   }
   ```
   If the mode change fails, the response will include the original and attempted mode names along with an error message.

6. **Set a Mission for a Specific Drone**
   ```bash
   curl -X POST "http://localhost:8000/set_mission/drone_1?mission_name=mission_1"
   ```
   **Output:**
   ```json
   {
       "status": "Mission 'mission_1' auto mode set successfully for drone 'drone_1' and is armed"
   }
   ```
   If there’s an issue with the mission, the response will include a `500` status code with an error message.

7. **Set the Same Mission for All Drones**
   ```bash
   curl -X POST "http://localhost:8000/set_mission_all_drones/mission_1"
   ```
   **Output:**
   ```json
   {
       "status": "Mission set successfully for all drones",
       "successful_drones": ["drone_1", "drone_2", "drone_3"],
       "failed_drones": []
   }
   ```
   If any drone fails to receive the mission, details will be provided in the `failed_drones` list.

8. **Set a Fence for a Specific Drone**
   ```bash
   curl -X POST "http://localhost:8000/set_fence/drone_1"
   ```
   **Output:**
   ```json
   {
       "status": "Geofence set successfully for drone 'drone_1'"
   }
   ```
   If an error occurs, the response will include a `500` status code and an error message.

9. **Set the Same Fence for All Drones**
   ```bash
   curl -X POST "http://localhost:8000/set_fence_all_drones"
   ```
   **Output:**
   ```json
   {
       "status": "Fence set successfully for all drones",
       "successful_drones": ["drone_1", "drone_2"],
       "failed_drones": []
   }
   ```
   The `failed_drones` list will contain details if any drone fails to receive the fence settings.

10. **Enable/Disable Fence for a Specific Drone**
    ```bash
    curl -X POST "http://localhost:8000/enable_fence/drone_1" -H "Content-Type: application/json" -d '{"fence_enable": "ENABLE"}'
    ```
    **Output:**
    ```json
    {
        "status": "Fence ENABLE command sent to the drone 'drone_1' successfully"
    }
    ```
    Errors will be reported in the form of a `500` status code and an error message.

11. **Enable/Disable Fence for All Drones**
    ```bash
    curl -X POST "http://localhost:8000/enable_fence_all_drones" -H "Content-Type: application/json" -d '{"fence_enable": "DISABLE"}'
    ```
    **Output:**
    ```json
    {
        "status": "Fence DISABLE command sent successfully for all drones",
        "successful_drones": ["drone_1", "drone_2"],
        "failed_drones": []
    }
    ```
    Any failures will be detailed in the `failed_drones` list.

12. **Set Rally Points for a Specific Drone**
    ```bash
    curl -X POST "http://localhost:8000/set_rally/drone_1"
    ```
    **Output:**
    ```json
    {
        "status": "Rally points set successfully for drone 'drone_1'"
    }
    ```

13. **Set the Same Rally Points for All Drones**
    ```bash
    curl -X POST "http://localhost:8000/set_rally_all_drones"
    ```
    **Output:**
    ```json
    {
        "status": "Rally points set successfully for all drones",
        "successful_drones": ["drone_1", "drone_2"],
        "failed_drones": []
    }
    ```

Each of these `curl` commands interacts with the FastAPI server and returns a JSON response, detailing the success or failure of the request.
