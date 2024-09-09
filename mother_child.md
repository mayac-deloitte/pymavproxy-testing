Here are the updated cURL commands for the **fence**, **rally**, and **mode change** operations based on the new endpoints and logic for mother/child drones:

### 1. **Fence Commands**

#### Set Fence for a Single Drone or Mother with Children

If you're setting the fence for a **single drone** (e.g., `drone_1`) or a **mother drone** (e.g., `mother_drone_1` and all its child drones), the cURL command remains the same but the backend logic will propagate the fence setting to child drones if it's a mother drone.

```bash
curl -X POST "http://127.0.0.1:8000/set_fence/drone_1"
```

For a mother drone (which will propagate to child drones):

```bash
curl -X POST "http://127.0.0.1:8000/set_fence/mother_drone_1"
```

---

### 2. **Rally Commands**

#### Set Rally Points for a Single Drone or Mother with Children

Similarly, you can set rally points for a **single drone** or a **mother drone** with its children. If the `drone_id` corresponds to a mother drone, the rally points will be propagated to all child drones.

```bash
curl -X POST "http://127.0.0.1:8000/set_rally/drone_1"
```

For a mother drone and all its children:

```bash
curl -X POST "http://127.0.0.1:8000/set_rally/mother_drone_1"
```

---

### 3. **Mode Change Commands**

#### Change Mode for a Single Drone or Mother with Children

You can change the flight mode for a **single drone** or a **mother drone** (and propagate to its child drones). The `drone_id` in the URL determines if it's a mother drone or child drone.

For a single drone:

```bash
curl -X POST "http://127.0.0.1:8000/update_drone_mode/drone_1/AUTO"
```

For a mother drone and its children:

```bash
curl -X POST "http://127.0.0.1:8000/update_drone_mode/mother_drone_1/LOITER"
```

---

### 4. **Telemetry for Mother and Child Drones**

To retrieve telemetry for a mother drone and its child drones:

```bash
curl -X GET "http://127.0.0.1:8000/get_telemetry_mother_and_children/mother_drone_1"
```

This command will retrieve telemetry for both the mother drone and all child drones.

---

### Summary of cURL Commands

- **Set Fence**: `/set_fence/{drone_id}`
- **Set Rally**: `/set_rally/{drone_id}`
- **Change Mode**: `/update_drone_mode/{drone_id}/{flight_mode}`
- **Get Telemetry for Mother and Children**: `/get_telemetry_mother_and_children/{mother_drone_id}`

These cURL commands work for both individual drones and mother/child drone configurations, with the backend handling the propagation of commands when applicable.