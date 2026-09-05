#!/bin/bash

# Navigate to the directory where this script is located
cd "$(dirname "$0")"

echo "=================================================="
echo "          Restarting TeacherOps Web App           "
echo "=================================================="

PORT=8765
URL="http://127.0.0.1:${PORT}"

# Stop any existing process running on the port
echo "Stopping any existing TeacherOps server instances on port ${PORT}..."
PID=$(lsof -ti :${PORT} 2>/dev/null)
if [ -n "$PID" ]; then
    echo "Terminating existing process (PID: $PID)..."
    kill -9 $PID 2>/dev/null
    sleep 0.8
fi

# Activate virtual environment if present
if [ -f "venv/bin/activate" ]; then
    source venv/bin/activate
elif [ -f "sandbox_venv/bin/activate" ]; then
    source sandbox_venv/bin/activate
fi

# Verify required packages are installed
if ! python3 -c "import fastapi, uvicorn" 2>/dev/null; then
    echo "Installing required packages (fastapi, uvicorn)..."
    python3 -m pip install fastapi uvicorn
fi

# Initialize SQLite database if needed
python3 agent.py init >/dev/null 2>&1

echo "Starting fresh server at ${URL}..."
echo "Reopening browser..."
echo "Press Ctrl+C in this terminal to stop the server."
echo "=================================================="

# Reopen the website in the default browser after server launch
(
    sleep 1.2
    open "$URL"
) &

# Start the FastAPI server
python3 -m uvicorn main:app --host 127.0.0.1 --port "$PORT" --reload
