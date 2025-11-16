#!/bin/bash
# Measure Qwen container startup and model loading performance

set -e

echo "=== QWEN CONTAINER PERFORMANCE TEST ==="
echo ""

# Test 1: Measure health endpoint readiness
echo "[Test 1] Measuring time to health endpoint ready..."
START=$(date +%s)
while ! curl -sf http://localhost:8002/health > /dev/null 2>&1; do
    sleep 0.5
done
END=$(date +%s)
HEALTH_TIME=$((END - START))
echo "✓ Health endpoint ready in ${HEALTH_TIME} seconds"
echo ""

# Check current health status
echo "[Test 2] Checking health status..."
HEALTH_RESPONSE=$(curl -s http://localhost:8002/health)
echo "Health response: ${HEALTH_RESPONSE}"
MODEL_LOADED=$(echo "$HEALTH_RESPONSE" | grep -o '"model_loaded":[^,}]*' | cut -d':' -f2)
echo "Model currently loaded: ${MODEL_LOADED}"
echo ""

# Test 3: Measure first inference (model load + inference)
echo "[Test 3] Measuring first inference time (includes model loading)..."
echo "Sending test inference request..."

START=$(date +%s)
RESPONSE=$(curl -s -X POST http://localhost:8002/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "qwen",
    "messages": [
      {
        "role": "user",
        "content": [
          {"type": "text", "text": "Say hello"}
        ]
      }
    ],
    "max_tokens": 10,
    "temperature": 0.0,
    "auto_unload": false
  }')
END=$(date +%s)
FIRST_INFERENCE_TIME=$((END - START))

# Check if response was successful
if echo "$RESPONSE" | grep -q '"choices"'; then
    echo "✓ First inference completed in ${FIRST_INFERENCE_TIME} seconds"
    TEXT=$(echo "$RESPONSE" | grep -o '"content":"[^"]*"' | head -1 | cut -d'"' -f4)
    echo "Response text: ${TEXT}"
else
    echo "✗ First inference failed"
    echo "Error response: ${RESPONSE}"
fi
echo ""

# Test 4: Measure second inference (model already loaded)
echo "[Test 4] Measuring second inference time (model cached)..."
sleep 2  # Brief pause

START=$(date +%s)
RESPONSE=$(curl -s -X POST http://localhost:8002/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "qwen",
    "messages": [
      {
        "role": "user",
        "content": [
          {"type": "text", "text": "Say hello"}
        ]
      }
    ],
    "max_tokens": 10,
    "temperature": 0.0,
    "auto_unload": true
  }')
END=$(date +%s)
SECOND_INFERENCE_TIME=$((END - START))

if echo "$RESPONSE" | grep -q '"choices"'; then
    echo "✓ Second inference completed in ${SECOND_INFERENCE_TIME} seconds"
else
    echo "✗ Second inference failed"
fi
echo ""

# Calculate model load time
MODEL_LOAD_TIME=$((FIRST_INFERENCE_TIME - SECOND_INFERENCE_TIME))
echo "=== PERFORMANCE SUMMARY ==="
echo "Container health ready:     ${HEALTH_TIME}s"
echo "First inference (+ load):   ${FIRST_INFERENCE_TIME}s"
echo "Second inference (cached):  ${SECOND_INFERENCE_TIME}s"
echo "Estimated model load time:  ${MODEL_LOAD_TIME}s"
echo ""
echo "Note: Model load time = First inference - Second inference"
echo "This assumes inference time is constant between requests"
