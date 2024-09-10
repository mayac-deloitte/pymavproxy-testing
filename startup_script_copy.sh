#!/bin/bash

# Function to check if the first command was successful
check_success() {
    if [ $? -ne 0 ]; then
        echo "Error: $1 failed to run."
        exit 1
    fi
}

# 1. Join ZeroTier network
echo "Joining ZeroTier network..."
sudo zerotier-cli join ebe7fbd445673728
check_success "ZeroTier join"

# 2. Run sim_vehicle.py in the ArduCopter directory (in a new terminal)
echo "Starting simulation in ArduCopter in a new terminal..."
gnome-terminal -- bash -c "cd ~/Desktop/ardupilot/ArduCopter && sim_vehicle.py -v copter -L JervisBay --count=3 --auto-sysid --console --map; exec bash"
check_success "sim_vehicle.py"

# 3. Start FastAPI in pymavproxy-testing directory (with periodic restart)
echo "Starting FastAPI app with periodic restart..."

restart_fastapi() {
    while true; do
        echo "Starting FastAPI..."
        gnome-terminal -- bash -c "cd ~/Desktop/pymavproxy-testing/fast_api_drone && python3 -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload"
        PID=$!

        # Run the server for 10 seconds
        sleep 10

        echo "Restarting FastAPI..."
        kill $PID

        # Wait for a few seconds before restarting
        sleep 2
    done
}

restart_fastapi &  # Run the function in the background
check_success "FastAPI app restart logic"

echo "All tasks started successfully!"
