#!/bin/bash
set -e

# Run script for Chat Server (local development)

echo "=== Chat Server Setup ==="

# Check if Redis is running
if ! redis-cli ping > /dev/null 2>&1; then
    echo "Starting Redis..."
    if command -v docker &> /dev/null; then
        docker run -d --name chat_redis -p 6379:6379 redis:7-alpine
        echo "[OK] Redis started in Docker"
    else
        echo "ERROR: Redis not running and Docker not found"
        echo "Please install Redis or Docker"
        exit 1
    fi
else
    echo "[OK] Redis is running"
fi

# Check if certificates exist
if [ ! -f "server.crt" ] || [ ! -f "server.key" ]; then
    echo "Generating TLS certificates..."
    ./generate_cert.sh
    echo "[OK] Certificates generated"
else
    echo "[OK] Certificates exist"
fi

# Install Python dependencies
if [ ! -d "venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv venv
    source venv/bin/activate
    pip install -r requirements.txt
    echo "[OK] Dependencies installed"
else
    echo "[OK] Virtual environment exists"
    source venv/bin/activate
fi

echo ""
echo "=== Starting Chat Server ==="
echo "Host: localhost:9999"
echo "TLS: Enabled"
echo "Press Ctrl+C to stop"
echo ""

python server.py
