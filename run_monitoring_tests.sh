#!/bin/bash

# System Monitoring Integration Tests Runner
# This script runs integration tests for the system monitoring feature

set -e

echo "=== System Monitoring Integration Tests ==="
echo ""

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Check if backend is running
echo -e "${YELLOW}[1/4] Checking backend status...${NC}"
if curl -f http://localhost:8000/health > /dev/null 2>&1; then
    echo -e "${GREEN}✓ Backend is running${NC}"
else
    echo -e "${RED}✗ Backend is not running on port 8000${NC}"
    echo "Please start the backend with: ./scripts/start_api.sh"
    exit 1
fi

# Check if system monitoring endpoints are accessible
echo -e "${YELLOW}[2/4] Checking monitoring endpoints...${NC}"
if curl -f http://localhost:8000/api/monitoring/system/current > /dev/null 2>&1; then
    echo -e "${GREEN}✓ Monitoring endpoints accessible${NC}"
else
    echo -e "${RED}✗ Monitoring endpoints not accessible${NC}"
    echo "System monitoring may not be initialized properly"
    exit 1
fi

# Run Python integration tests
echo -e "${YELLOW}[3/4] Running Python integration tests...${NC}"
if python -m pytest tests/test_system_monitoring_integration.py -v; then
    echo -e "${GREEN}✓ Python tests passed${NC}"
else
    echo -e "${RED}✗ Python tests failed${NC}"
    exit 1
fi

# Manual test checklist
echo ""
echo -e "${YELLOW}[4/4] Manual testing checklist:${NC}"
echo ""
echo "Frontend tests (open http://localhost:3000):"
echo "  [ ] Click settings button in top-right"
echo "  [ ] Toggle 'System Monitoring' checkbox"
echo "  [ ] Verify badge appears in top-right corner"
echo "  [ ] Click badge to open sidebar"
echo "  [ ] Verify GPU metrics are displayed"
echo "  [ ] Verify timeline graph shows data"
echo "  [ ] Change metric type (GPU Memory, GPU Temp, CPU, RAM)"
echo "  [ ] Click Export button to download metrics"
echo "  [ ] Close sidebar and disable monitoring in settings"
echo ""
echo -e "${GREEN}All automated tests passed!${NC}"
echo ""
