# pymavproxy-testing

### FastAPI for Drone Swarm Communication
1. Get inside the `/fast_api_drone` folder.
2. Install all neccessary packages, using:
```shell
pip install -r requirements.txt
```
3. Specifify network configurations in `config.yaml`.
4. To start the app, run:
```shell
python3 -m uvicorn main:app --reload
```
5. To connect all your drones, in another terminal run:
```shell
curl -X POST "http://127.0.0.1:8000/connect_all_drones"
```  
6. To connect a specific drone, e.g.`drone_1`, run:
```shell
curl -X POST "http://127.0.0.1:8000/connect_drone" -H "Content-Type: application/json" -d '{"drone_id": "drone_1"}'
```  
7. To get telemtry from all your drones, run:
```shell
curl -X GET "http://127.0.0.1:8000/get_all_telemetry"
```
8. To get telemtry from a specific drone, e.g.`drone_1`, run:
```shell
curl -X GET "http://127.0.0.1:8000/get_telemetry/drone_1"
```


### Multi vehicle SITL using non-local GCS without PyMAVPROXY.
1. Get inside the `/tutorials` folder.
2. Install all neccessary packages, using:
3. Specifify your network configuration in `network.py`.
