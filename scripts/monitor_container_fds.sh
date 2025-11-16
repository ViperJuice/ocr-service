#!/bin/bash
# Monitor file descriptors in Docker containers
# Usage: ./scripts/monitor_container_fds.sh [interval_seconds]

INTERVAL="${1:-5}"  # Default 5 seconds

echo "Monitoring Docker container file descriptors every ${INTERVAL}s"
echo "Press Ctrl+C to stop"
echo ""

while true; do
    echo "=== $(date) ==="

    for container in deepseek-ocr qwen-vl; do
        if docker ps --format '{{.Names}}' | grep -q "^${container}$"; then
            echo ""
            echo "Container: $container"

            # Get main process PID inside container
            PID=$(docker exec $container sh -c 'echo $$')

            # Get file descriptor count
            FD_COUNT=$(docker exec $container sh -c "ls -1 /proc/self/fd 2>/dev/null | wc -l" 2>/dev/null || echo "N/A")

            # Get ulimit
            ULIMIT=$(docker exec $container sh -c 'ulimit -n' 2>/dev/null || echo "N/A")

            # Get actual process FD count if available
            PROC_FD=$(docker exec $container sh -c "ls -1 /proc/1/fd 2>/dev/null | wc -l" 2>/dev/null || echo "N/A")

            echo "  Current FDs (shell): $FD_COUNT"
            echo "  Current FDs (PID 1): $PROC_FD"
            echo "  Ulimit: $ULIMIT"

            # Calculate percentage if we have numbers
            if [[ "$PROC_FD" != "N/A" && "$ULIMIT" != "N/A" ]]; then
                PERCENT=$(awk "BEGIN {printf \"%.1f\", ($PROC_FD / $ULIMIT) * 100}")
                echo "  Usage: ${PERCENT}%"

                # Warn if high
                if (( $(echo "$PERCENT > 80" | bc -l) )); then
                    echo "  ⚠️  WARNING: High FD usage!"
                fi
            fi
        else
            echo ""
            echo "Container: $container [NOT RUNNING]"
        fi
    done

    echo ""
    echo "---"
    sleep "$INTERVAL"
done
