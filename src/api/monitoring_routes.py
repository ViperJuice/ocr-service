"""FastAPI routes for system monitoring endpoints."""
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse
from typing import List, Dict, Any, Optional
import asyncio
import json
from pathlib import Path
import logging

from .monitoring_service import MonitoringService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/monitoring", tags=["monitoring"])
monitoring_service = MonitoringService()

# Dependency injection for system-wide monitoring
_system_monitor: Optional = None
_job_manager: Optional = None
_model_manager: Optional = None

def set_managers(system_monitor, job_manager, model_manager=None):
    """Set manager instances for dependency injection."""
    global _system_monitor, _job_manager, _model_manager
    _system_monitor = system_monitor
    _job_manager = job_manager
    _model_manager = model_manager
    logger.info("Monitoring routes: managers set for system-wide monitoring")


@router.get("/current")
async def get_current_metrics(
    job_id: Optional[str] = Query(None, description="Job ID to get metrics for. If not provided, returns latest job.")
) -> Dict[str, Any]:
    """
    Get the most recent metrics snapshot.

    Returns:
        Latest metrics including system stats, GPU usage, stage progress, etc.
    """
    metrics = monitoring_service.get_latest_metrics(job_id)

    if metrics is None:
        raise HTTPException(
            status_code=404,
            detail=f"No metrics found{' for job ' + job_id if job_id else ''}"
        )

    return metrics


@router.get("/history")
async def get_metrics_history(
    job_id: Optional[str] = Query(None, description="Job ID to get history for"),
    minutes: int = Query(60, ge=1, le=1440, description="Time window in minutes (max 24 hours)"),
    event_type: Optional[str] = Query(None, description="Filter by event type (e.g., 'stage_transition')")
) -> List[Dict[str, Any]]:
    """
    Get historical metrics for the specified time window.

    Args:
        job_id: Optional job identifier
        minutes: Time window in minutes (1-1440, default: 60)
        event_type: Optional filter by event_type

    Returns:
        List of metrics entries
    """
    metrics = monitoring_service.get_metrics_history(
        job_id=job_id,
        minutes=minutes,
        event_type=event_type
    )

    return metrics


@router.get("/jobs")
async def get_active_jobs() -> List[str]:
    """
    Get list of active jobs with monitoring data.

    Returns:
        List of job IDs
    """
    return monitoring_service.get_active_jobs()


@router.get("/jobs/{job_id}")
async def get_job_summary(job_id: str) -> Dict[str, Any]:
    """
    Get summary information for a specific job.

    Args:
        job_id: Job identifier

    Returns:
        Job summary including start time, duration, progress, and stage transitions
    """
    summary = monitoring_service.get_job_summary(job_id)

    if summary is None:
        raise HTTPException(
            status_code=404,
            detail=f"Job {job_id} not found"
        )

    return summary


@router.get("/stream")
async def stream_metrics(
    job_id: Optional[str] = Query(None, description="Job ID to stream metrics for"),
    interval: int = Query(2, ge=1, le=30, description="Update interval in seconds")
):
    """
    Server-Sent Events (SSE) stream of real-time metrics.

    Args:
        job_id: Optional job identifier
        interval: Update interval in seconds (1-30, default: 2)

    Returns:
        SSE stream of metrics updates
    """
    async def event_generator():
        """Generate SSE events with metrics updates."""
        while True:
            try:
                metrics = monitoring_service.get_latest_metrics(job_id)

                if metrics:
                    # Format as SSE event
                    data = json.dumps(metrics)
                    yield f"data: {data}\n\n"
                else:
                    # Send keepalive
                    yield ": keepalive\n\n"

                await asyncio.sleep(interval)

            except Exception as e:
                # Send error event
                error_data = json.dumps({"error": str(e)})
                yield f"event: error\ndata: {error_data}\n\n"
                break

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"  # Disable nginx buffering
        }
    )


@router.get("/pages")
async def get_page_completions(
    job_id: Optional[str] = Query(None, description="Job ID to get page completions for"),
    stage: Optional[str] = Query(None, description="Filter by stage (ocr or merge)")
) -> List[Dict[str, Any]]:
    """
    Get all page completion events with detailed per-page metrics.

    Args:
        job_id: Optional job identifier
        stage: Optional filter by stage ("ocr" or "merge")

    Returns:
        List of page completion events
    """
    pages = monitoring_service.get_page_completions(job_id=job_id, stage=stage)
    return pages


@router.get("/health")
async def health_check() -> Dict[str, str]:
    """
    Health check endpoint.

    Returns:
        Status message
    """
    return {"status": "ok", "service": "monitoring"}


# ========== System-wide Monitoring Endpoints ==========

@router.get("/system/current")
async def get_system_metrics():
    """
    Get current system-wide metrics.

    Returns:
        SystemMetrics: Complete system snapshot
    """
    if not _system_monitor or not _job_manager:
        raise HTTPException(
            status_code=503,
            detail="System monitoring not initialized"
        )

    try:
        metrics = monitoring_service.get_system_metrics(
            system_monitor=_system_monitor,
            job_manager=_job_manager,
            model_manager=_model_manager
        )
        return metrics
    except Exception as e:
        logger.error(f"Failed to get system metrics: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to collect system metrics: {str(e)}"
        )


@router.get("/system/history")
async def get_system_metrics_history(
    seconds: int = Query(60, ge=10, le=3600, description="Seconds of history to retrieve")
):
    """
    Get historical system metrics.

    Args:
        seconds: Number of seconds of history (10-3600)

    Returns:
        Historical metrics with time range
    """
    if not _system_monitor:
        raise HTTPException(
            status_code=503,
            detail="System monitoring not initialized"
        )

    try:
        history = monitoring_service.get_system_metrics_history(
            system_monitor=_system_monitor,
            seconds=seconds
        )
        return history
    except Exception as e:
        logger.error(f"Failed to get metrics history: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to retrieve metrics history: {str(e)}"
        )


@router.get("/system/stream")
async def stream_system_metrics(
    interval: int = Query(1, ge=1, le=30, description="Update interval in seconds")
):
    """
    Server-Sent Events stream of system metrics.

    Args:
        interval: Seconds between updates (1-30)

    Returns:
        StreamingResponse with SSE
    """
    if not _system_monitor or not _job_manager:
        raise HTTPException(
            status_code=503,
            detail="System monitoring not initialized"
        )

    async def event_generator():
        """Generate SSE events."""
        try:
            while True:
                # Get current metrics
                metrics = monitoring_service.get_system_metrics(
                    system_monitor=_system_monitor,
                    job_manager=_job_manager,
                    model_manager=_model_manager
                )

                # Format as SSE
                yield f"data: {json.dumps(metrics)}\n\n"

                # Wait for next interval
                await asyncio.sleep(interval)

        except asyncio.CancelledError:
            # Client disconnected
            logger.info("System metrics stream client disconnected")
        except Exception as e:
            logger.error(f"Error in system metrics stream: {e}")
            yield f"event: error\ndata: {json.dumps({'error': str(e)})}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"
        }
    )
