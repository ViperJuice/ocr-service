#!/bin/bash
# Measure full container stop/start cycle

set -e

echo "=== FULL CONTAINER RESTART TEST ==="
echo ""

# Step 1: Stop container
echo "[1/3] Stopping Qwen container..."
STOP_START=$(date +%s)
docker stop qwen-vl > /dev/null 2>&1
STOP_END=$(date +%s)
STOP_TIME=$((STOP_END - STOP_START))
echo "✓ Container stopped in ${STOP_TIME}s"
echo ""

# Step 2: Start container
echo "[2/3] Starting Qwen container..."
START_TIME=$(date +%s)
docker start qwen-vl > /dev/null 2>&1
CONTAINER_UP=$(date +%s)
STARTUP_TIME=$((CONTAINER_UP - START_TIME))
echo "✓ Container started in ${STARTUP_TIME}s"
echo ""

# Step 3: Wait for health endpoint
echo "[3/3] Waiting for health endpoint..."
HEALTH_START=$(date +%s)
MAX_WAIT=30
ELAPSED=0

while [ $ELAPSED -lt $MAX_WAIT ]; do
    if curl -sf http://localhost:8002/health > /dev/null 2>&1; then
        HEALTH_END=$(date +%s)
        HEALTH_TIME=$((HEALTH_END - HEALTH_START))
        echo "✓ Health endpoint ready in ${HEALTH_TIME}s"
        break
    fi
    sleep 0.5
    ELAPSED=$(($(date +%s) - HEALTH_START))
done

if [ $ELAPSED -ge $MAX_WAIT ]; then
    echo "✗ Health endpoint not ready after ${MAX_WAIT}s"
    exit 1
fi

# Total restart time
TOTAL_TIME=$((HEALTH_END - STOP_START))

echo ""
echo "=== RESTART TIMING BREAKDOWN ==="
echo "Stop container:             ${STOP_TIME}s"
echo "Start container:            ${STARTUP_TIME}s"
echo "Wait for health:            ${HEALTH_TIME}s"
echo "-----------------------------------"
echo "TOTAL RESTART TIME:         ${TOTAL_TIME}s"
echo ""
echo "Note: This is the overhead per job if using container restart strategy"
echo "Compare to 21s model load time in current architecture"
