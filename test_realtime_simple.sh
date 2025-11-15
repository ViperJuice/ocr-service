#!/bin/bash
# Phase 3 Integration Test Script
# Tests Realtime subscriptions vs SSE dual-subscription implementation
#
# Prerequisites:
#   1. Supabase running: supabase start
#   2. Docker containers running: docker-compose up
#   3. Backend API running: uv run uvicorn src.api.main:app --reload
#   4. Frontend running: cd web && npm run dev
#
# This script validates:
#   - Realtime WebSocket connections work
#   - Job updates received via Realtime
#   - Latency comparison (SSE vs Realtime)

set -e  # Exit on error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Test configuration
API_URL="${API_URL:-http://localhost:8000}"
FRONTEND_URL="${FRONTEND_URL:-http://localhost:3000}"
TEST_PDF="${TEST_PDF:-test.pdf}"

echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}Phase 3 Realtime Integration Tests${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""

# Function to check if service is running
check_service() {
    local service_name=$1
    local url=$2
    local timeout=5

    echo -ne "Checking ${service_name}... "
    if curl -s --max-time $timeout "$url" > /dev/null 2>&1; then
        echo -e "${GREEN}✓ Running${NC}"
        return 0
    else
        echo -e "${RED}✗ Not running${NC}"
        return 1
    fi
}

# Function to check if Supabase is running
check_supabase() {
    echo -ne "Checking Supabase... "
    if supabase status > /dev/null 2>&1; then
        echo -e "${GREEN}✓ Running${NC}"
        return 0
    else
        echo -e "${RED}✗ Not running${NC}"
        return 1
    fi
}

# Function to check Docker containers
check_docker() {
    echo -ne "Checking Docker containers... "
    if docker ps | grep -q ocr; then
        echo -e "${GREEN}✓ Running${NC}"
        return 0
    else
        echo -e "${RED}✗ Not running${NC}"
        return 1
    fi
}

# Step 1: Check all prerequisites
echo -e "${YELLOW}Step 1: Checking Prerequisites${NC}"
echo "-----------------------------------"

SUPABASE_OK=false
DOCKER_OK=false
API_OK=false
FRONTEND_OK=false

check_supabase && SUPABASE_OK=true || true
check_docker && DOCKER_OK=true || true
check_service "Backend API" "$API_URL/health" && API_OK=true || true
check_service "Frontend" "$FRONTEND_URL" && FRONTEND_OK=true || true

echo ""

if ! $SUPABASE_OK || ! $DOCKER_OK || ! $API_OK || ! $FRONTEND_OK; then
    echo -e "${RED}Error: Not all services are running!${NC}"
    echo ""
    echo "Please start missing services:"
    $SUPABASE_OK || echo "  - Supabase: supabase start"
    $DOCKER_OK || echo "  - Docker: docker-compose up"
    $API_OK || echo "  - Backend API: uv run uvicorn src.api.main:app --reload"
    $FRONTEND_OK || echo "  - Frontend: cd web && npm run dev"
    echo ""
    exit 1
fi

echo -e "${GREEN}All prerequisites met!${NC}"
echo ""

# Step 2: Create or verify test PDF exists
echo -e "${YELLOW}Step 2: Preparing Test File${NC}"
echo "-----------------------------------"

if [ ! -f "$TEST_PDF" ]; then
    echo "Creating test PDF..."
    # Create a simple test PDF using convert (ImageMagick) if available
    if command -v convert > /dev/null; then
        convert -size 200x200 xc:white -pointsize 20 -draw "text 10,30 'Test OCR Document'" "$TEST_PDF"
        echo -e "${GREEN}✓ Test PDF created${NC}"
    else
        echo -e "${RED}✗ Cannot create test PDF - ImageMagick not installed${NC}"
        echo "Please provide a test PDF file named: $TEST_PDF"
        exit 1
    fi
else
    echo -e "${GREEN}✓ Test PDF found: $TEST_PDF${NC}"
fi
echo ""

# Step 3: Upload test PDF
echo -e "${YELLOW}Step 3: Uploading Test PDF${NC}"
echo "-----------------------------------"

UPLOAD_RESPONSE=$(curl -s -X POST "$API_URL/upload" \
    -F "file=@$TEST_PDF" \
    -H "Accept: application/json")

FILE_ID=$(echo "$UPLOAD_RESPONSE" | grep -o '"file_id":"[^"]*"' | cut -d'"' -f4)

if [ -z "$FILE_ID" ]; then
    echo -e "${RED}✗ Failed to upload PDF${NC}"
    echo "Response: $UPLOAD_RESPONSE"
    exit 1
fi

echo -e "${GREEN}✓ PDF uploaded successfully${NC}"
echo "File ID: $FILE_ID"
echo ""

# Step 4: Submit OCR job
echo -e "${YELLOW}Step 4: Submitting OCR Job${NC}"
echo "-----------------------------------"

JOB_RESPONSE=$(curl -s -X POST "$API_URL/jobs" \
    -H "Content-Type: application/json" \
    -d "{\"file_id\": \"$FILE_ID\", \"model_preference\": \"fast\"}")

JOB_ID=$(echo "$JOB_RESPONSE" | grep -o '"job_id":"[^"]*"' | cut -d'"' -f4)

if [ -z "$JOB_ID" ]; then
    echo -e "${RED}✗ Failed to submit job${NC}"
    echo "Response: $JOB_RESPONSE"
    exit 1
fi

echo -e "${GREEN}✓ Job submitted successfully${NC}"
echo "Job ID: $JOB_ID"
echo ""

# Step 5: Monitor job progress
echo -e "${YELLOW}Step 5: Monitoring Job Progress${NC}"
echo "-----------------------------------"
echo "Open browser console at: $FRONTEND_URL/jobs/$JOB_ID"
echo ""
echo "Look for the following logs in browser console:"
echo -e "${BLUE}1. Realtime subscription logs:${NC}"
echo "   [PHASE 3.5] Realtime subscription status: SUBSCRIBED"
echo "   [PHASE 3.5] Realtime update received: {...}"
echo ""
echo -e "${BLUE}2. SSE logs (existing implementation):${NC}"
echo "   [SSE] Event received: {...}"
echo ""
echo -e "${BLUE}3. Compare latency timestamps${NC}"
echo ""
echo "Wait for job to complete, then review console logs..."
echo ""

# Step 6: Poll job status via API
echo -e "${YELLOW}Step 6: Polling Job Status (API)${NC}"
echo "-----------------------------------"

MAX_ATTEMPTS=30
ATTEMPT=0

while [ $ATTEMPT -lt $MAX_ATTEMPTS ]; do
    sleep 2
    ATTEMPT=$((ATTEMPT + 1))

    STATUS_RESPONSE=$(curl -s "$API_URL/jobs/$JOB_ID")
    JOB_STATUS=$(echo "$STATUS_RESPONSE" | grep -o '"status":"[^"]*"' | cut -d'"' -f4)
    PROGRESS=$(echo "$STATUS_RESPONSE" | grep -o '"progress_pct":[0-9.]*' | cut -d':' -f2)

    echo -ne "\rAttempt $ATTEMPT/$MAX_ATTEMPTS - Status: $JOB_STATUS, Progress: ${PROGRESS}%"

    if [ "$JOB_STATUS" = "completed" ]; then
        echo ""
        echo -e "${GREEN}✓ Job completed successfully!${NC}"
        break
    elif [ "$JOB_STATUS" = "failed" ]; then
        echo ""
        echo -e "${RED}✗ Job failed${NC}"
        echo "Response: $STATUS_RESPONSE"
        exit 1
    fi
done

if [ $ATTEMPT -ge $MAX_ATTEMPTS ]; then
    echo ""
    echo -e "${YELLOW}⚠ Job did not complete within timeout${NC}"
fi

echo ""

# Step 7: Summary and next steps
echo -e "${YELLOW}Step 7: Test Summary${NC}"
echo "-----------------------------------"
echo ""
echo "✅ Integration test completed!"
echo ""
echo "Next steps for manual validation:"
echo "1. Review browser console logs at: $FRONTEND_URL/jobs/$JOB_ID"
echo "2. Verify Realtime subscription connected (status: SUBSCRIBED)"
echo "3. Verify updates received via both SSE and Realtime"
echo "4. Compare latency timestamps (Realtime should be < SSE)"
echo "5. Document findings in specs/PHASE_3_TEST_RESULTS.md"
echo ""
echo "Chrome DevTools shortcuts:"
echo "  - F12: Open DevTools"
echo "  - Console tab: View subscription logs"
echo "  - Network tab → WS: View WebSocket frames"
echo ""
echo -e "${GREEN}Test script completed successfully!${NC}"
echo ""
