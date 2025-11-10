"""Batch processing API routes."""
import logging
import json
import asyncio
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse

from .models import BatchJobResponse, BatchResultResponse
from .models.requests import BatchProcessRequest
from .services import FileManager, JobManager, PromptManager, BatchManager, ProgressEmitter

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/batch", tags=["batch"])


# Dependency injection
_batch_manager: Optional[BatchManager] = None
_file_manager: Optional[FileManager] = None
_job_manager: Optional[JobManager] = None
_prompt_manager: Optional[PromptManager] = None
_model_manager = None
_progress_emitter: Optional[ProgressEmitter] = None


def set_managers(
    batch_manager: BatchManager,
    file_manager: FileManager,
    job_manager: JobManager,
    prompt_manager: PromptManager,
    model_manager,
    progress_emitter: ProgressEmitter
):
    """Set manager instances (called from main.py)."""
    global _batch_manager, _file_manager, _job_manager, _prompt_manager, _model_manager, _progress_emitter
    _batch_manager = batch_manager
    _file_manager = file_manager
    _job_manager = job_manager
    _prompt_manager = prompt_manager
    _model_manager = model_manager
    _progress_emitter = progress_emitter


def get_batch_manager() -> BatchManager:
    """Get batch manager instance."""
    if _batch_manager is None:
        raise HTTPException(status_code=500, detail="BatchManager not initialized")
    return _batch_manager


def get_file_manager() -> FileManager:
    """Get file manager instance."""
    if _file_manager is None:
        raise HTTPException(status_code=500, detail="FileManager not initialized")
    return _file_manager


def get_job_manager() -> JobManager:
    """Get job manager instance."""
    if _job_manager is None:
        raise HTTPException(status_code=500, detail="JobManager not initialized")
    return _job_manager


def get_prompt_manager() -> PromptManager:
    """Get prompt manager instance."""
    if _prompt_manager is None:
        raise HTTPException(status_code=500, detail="PromptManager not initialized")
    return _prompt_manager


def get_model_manager():
    """Get model manager instance."""
    if _model_manager is None:
        raise HTTPException(status_code=500, detail="ModelManager not initialized")
    return _model_manager


def get_progress_emitter() -> ProgressEmitter:
    """Get progress emitter instance."""
    if _progress_emitter is None:
        raise HTTPException(status_code=500, detail="ProgressEmitter not initialized")
    return _progress_emitter


@router.post("/process", response_model=BatchJobResponse)
async def submit_batch_job(
    request: BatchProcessRequest,
    batch_manager: BatchManager = Depends(get_batch_manager),
    file_manager: FileManager = Depends(get_file_manager),
    job_manager: JobManager = Depends(get_job_manager),
    prompt_manager: PromptManager = Depends(get_prompt_manager),
    model_manager = Depends(get_model_manager),
    progress_emitter: ProgressEmitter = Depends(get_progress_emitter)
):
    """
    Submit a batch processing job for a directory of PDFs.

    Args:
        request: Batch process request
        batch_manager: Batch manager instance
        file_manager: File manager instance
        job_manager: Job manager instance
        prompt_manager: Prompt manager instance
        model_manager: Model manager instance
        progress_emitter: Progress emitter instance

    Returns:
        BatchJobResponse with batch job information
    """
    try:
        # Validate directory exists
        directory_info = file_manager.get_directory_info(request.directory_id)

        # Create batch job
        batch = batch_manager.create_batch_job(
            directory_id=request.directory_id,
            file_ids=directory_info.file_ids,
            model=request.model,
            prompt_type=request.prompt_type,
            custom_prompts=request.custom_prompts,
            processing_options=request.processing_options.model_dump() if request.processing_options else {},
            output_format=request.output_format
        )

        # Start batch processing asynchronously
        batch_manager.start_batch_job(
            batch_job_id=batch.batch_job_id,
            file_manager=file_manager,
            job_manager=job_manager,
            prompt_manager=prompt_manager,
            model_manager=model_manager,
            progress_emitter=progress_emitter
        )

        # Return response
        return BatchJobResponse(
            batch_job_id=batch.batch_job_id,
            directory_id=batch.directory_id,
            total_documents=batch.total_documents,
            documents_completed=batch.documents_completed,
            overall_progress_pct=batch.overall_progress_pct,
            status=batch.status.value,
            created_at=batch.created_at,
            started_at=batch.started_at,
            completed_at=batch.completed_at,
            error=batch.error
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to submit batch job: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to submit batch job: {str(e)}")


@router.get("/{batch_job_id}/status", response_model=BatchJobResponse)
async def get_batch_status(
    batch_job_id: str,
    batch_manager: BatchManager = Depends(get_batch_manager)
):
    """
    Get batch job status.

    Args:
        batch_job_id: Batch job identifier
        batch_manager: Batch manager instance

    Returns:
        BatchJobResponse with current status
    """
    try:
        batch = batch_manager.get_batch_job(batch_job_id)

        return BatchJobResponse(
            batch_job_id=batch.batch_job_id,
            directory_id=batch.directory_id,
            total_documents=batch.total_documents,
            documents_completed=batch.documents_completed,
            overall_progress_pct=batch.overall_progress_pct,
            status=batch.status.value,
            created_at=batch.created_at,
            started_at=batch.started_at,
            completed_at=batch.completed_at,
            error=batch.error
        )

    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to get batch status: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to get batch status: {str(e)}")


@router.get("/{batch_job_id}/result", response_model=BatchResultResponse)
async def get_batch_result(
    batch_job_id: str,
    batch_manager: BatchManager = Depends(get_batch_manager)
):
    """
    Get batch job results.

    Args:
        batch_job_id: Batch job identifier
        batch_manager: Batch manager instance

    Returns:
        BatchResultResponse with all document results
    """
    try:
        result = batch_manager.get_batch_result(batch_job_id)

        return BatchResultResponse(
            batch_job_id=result["batch_job_id"],
            total_documents=result["total_documents"],
            documents_completed=result["documents_completed"],
            results=result["results"],
            overall_processing_time_seconds=result["overall_processing_time_seconds"]
        )

    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to get batch result: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to get batch result: {str(e)}")


@router.post("/{batch_job_id}/cancel")
async def cancel_batch_job(
    batch_job_id: str,
    batch_manager: BatchManager = Depends(get_batch_manager)
):
    """
    Cancel a running batch job.

    Args:
        batch_job_id: Batch job identifier
        batch_manager: Batch manager instance

    Returns:
        Success message
    """
    try:
        success = batch_manager.cancel_batch_job(batch_job_id)

        return {
            "batch_job_id": batch_job_id,
            "status": "cancelled",
            "message": "Batch job cancelled successfully"
        }

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to cancel batch job: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to cancel batch job: {str(e)}")


@router.get("/progress/stream")
async def stream_progress(
    progress_emitter: ProgressEmitter = Depends(get_progress_emitter)
):
    """
    Server-Sent Events stream for real-time progress updates.

    This endpoint provides a continuous stream of progress events for all jobs and batches.
    Events include:
    - job_progress: Individual job progress updates
    - document_progress: Document-level progress in batch jobs
    - batch_progress: Batch-level aggregated progress
    - completion: Job/batch completion notifications
    - error: Error notifications

    Returns:
        StreamingResponse: SSE stream with progress events
    """
    connection_id = str(uuid.uuid4())

    async def event_generator():
        """Generate SSE events from progress emitter."""
        queue = None
        try:
            # Register connection with progress emitter
            queue = await progress_emitter.register_connection(connection_id)
            logger.info(f"Progress stream connection registered: {connection_id}")

            # Send initial connection success event
            yield f"event: connected\ndata: {json.dumps({'connection_id': connection_id})}\n\n"

            # Stream events from queue
            while True:
                try:
                    # Wait for event with timeout for keepalive
                    event = await asyncio.wait_for(queue.get(), timeout=30.0)

                    # Format as SSE event
                    event_type = event.get("event_type", "message")
                    event_data = json.dumps(event.get("data", {}))

                    yield f"event: {event_type}\ndata: {event_data}\n\n"

                except asyncio.TimeoutError:
                    # Send keepalive comment
                    yield ": keepalive\n\n"

        except asyncio.CancelledError:
            # Client disconnected
            logger.info(f"Progress stream client disconnected: {connection_id}")

        except Exception as e:
            logger.error(f"Error in progress stream: {e}", exc_info=True)
            error_data = json.dumps({"error": str(e)})
            yield f"event: error\ndata: {error_data}\n\n"

        finally:
            # Unregister connection
            if queue is not None:
                await progress_emitter.unregister_connection(connection_id)
                logger.info(f"Progress stream connection unregistered: {connection_id}")

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"  # Disable nginx buffering
        }
    )
