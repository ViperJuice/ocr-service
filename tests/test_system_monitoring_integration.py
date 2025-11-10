"""Integration tests for system monitoring feature."""
import pytest
import httpx
import asyncio
import json
from datetime import datetime


@pytest.fixture
async def api_client():
    """Create async HTTP client."""
    async with httpx.AsyncClient(base_url="http://localhost:8000") as client:
        yield client


@pytest.mark.asyncio
async def test_system_current_endpoint(api_client):
    """Test /api/monitoring/system/current."""
    response = await api_client.get("/api/monitoring/system/current")

    assert response.status_code == 200
    data = response.json()

    # Schema validation
    required_fields = [
        "timestamp", "cpu_percent", "ram_used_gb", "ram_total_gb",
        "ram_percent", "gpus", "queue"
    ]
    for field in required_fields:
        assert field in data, f"Missing required field: {field}"

    # Type validation
    assert isinstance(data["cpu_percent"], (int, float))
    assert 0 <= data["cpu_percent"] <= 100

    assert isinstance(data["gpus"], list)
    assert isinstance(data["queue"], dict)

    # Timestamp validation
    datetime.fromisoformat(data["timestamp"].replace('Z', '+00:00'))


@pytest.mark.asyncio
async def test_system_history_endpoint(api_client):
    """Test /api/monitoring/system/history."""
    response = await api_client.get("/api/monitoring/system/history?seconds=30")

    assert response.status_code == 200
    data = response.json()

    assert "metrics" in data
    assert "time_range" in data
    assert isinstance(data["metrics"], list)

    # Validate ordering
    if len(data["metrics"]) > 1:
        timestamps = [m["timestamp"] for m in data["metrics"]]
        assert timestamps == sorted(timestamps)


@pytest.mark.asyncio
async def test_sse_stream_endpoint(api_client):
    """Test /api/monitoring/system/stream."""
    received_events = []

    async with api_client.stream(
        "GET",
        "/api/monitoring/system/stream?interval=1"
    ) as response:
        assert response.status_code == 200
        assert "text/event-stream" in response.headers["content-type"]

        # Collect 3 events
        async for line in response.aiter_lines():
            if line.startswith("data: "):
                data = json.loads(line[6:])
                received_events.append(data)

                if len(received_events) >= 3:
                    break

    assert len(received_events) == 3

    # Validate event structure
    for event in received_events:
        assert "timestamp" in event
        assert "cpu_percent" in event


@pytest.mark.asyncio
async def test_sse_invalid_interval(api_client):
    """Test SSE with invalid interval parameter."""
    response = await api_client.get("/api/monitoring/system/stream?interval=100")
    assert response.status_code == 422  # Validation error


@pytest.mark.asyncio
async def test_concurrent_requests(api_client):
    """Test multiple concurrent requests."""
    tasks = [
        api_client.get("/api/monitoring/system/current")
        for _ in range(5)
    ]

    responses = await asyncio.gather(*tasks)

    # All should succeed
    assert all(r.status_code == 200 for r in responses)

    # Data should be similar (within 1 second)
    timestamps = [
        datetime.fromisoformat(r.json()["timestamp"].replace('Z', '+00:00'))
        for r in responses
    ]
    time_diff = (max(timestamps) - min(timestamps)).total_seconds()
    assert time_diff < 1.0


@pytest.mark.asyncio
async def test_gpu_metrics_structure(api_client):
    """Test GPU metrics structure."""
    response = await api_client.get("/api/monitoring/system/current")
    data = response.json()

    if len(data["gpus"]) > 0:
        gpu = data["gpus"][0]

        # Required GPU fields
        assert "id" in gpu
        assert "name" in gpu
        assert "memory_used_mb" in gpu
        assert "memory_total_mb" in gpu
        assert "memory_percent" in gpu
        assert "utilization_percent" in gpu
        assert "temperature_c" in gpu

        # Value ranges
        assert 0 <= gpu["memory_percent"] <= 1
        assert 0 <= gpu["utilization_percent"] <= 100
        assert gpu["memory_used_mb"] <= gpu["memory_total_mb"]


@pytest.mark.asyncio
async def test_queue_stats_structure(api_client):
    """Test queue stats structure."""
    response = await api_client.get("/api/monitoring/system/current")
    data = response.json()

    queue = data["queue"]
    required_keys = ["queued", "processing", "completed", "failed", "cancelled"]

    for key in required_keys:
        assert key in queue
        assert isinstance(queue[key], int)
        assert queue[key] >= 0


@pytest.mark.asyncio
async def test_history_time_range(api_client):
    """Test history time range validation."""
    # Valid request
    response = await api_client.get("/api/monitoring/system/history?seconds=30")
    assert response.status_code == 200

    # Below minimum
    response = await api_client.get("/api/monitoring/system/history?seconds=5")
    assert response.status_code == 422

    # Above maximum
    response = await api_client.get("/api/monitoring/system/history?seconds=5000")
    assert response.status_code == 422


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
