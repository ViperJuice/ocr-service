"""Processing API routes."""
import logging
import asyncio
import json
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, UploadFile, File, HTTPException, Depends
from fastapi.responses import FileResponse, StreamingResponse

from .models import (
    JobSubmitRequest,
    FileUploadResponse,
    JobSubmitResponse,
    JobStatusResponse,
    JobResultResponse,
    JobCancelResponse,
    OcrOutputResponse,
)
from .services import FileManager, PromptManager, JobManager, JobStatus
from .services.result_emitter import get_result_emitter

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/process", tags=["processing"])


# Dependency injection - these will be set by main.py
_file_manager: Optional[FileManager] = None
_prompt_manager: Optional[PromptManager] = None
_job_manager: Optional[JobManager] = None
_model_manager = None


def set_managers(file_manager, prompt_manager, job_manager, model_manager):
    """Set manager instances (called from main.py)."""
    global _file_manager, _prompt_manager, _job_manager, _model_manager
    _file_manager = file_manager
    _prompt_manager = prompt_manager
    _job_manager = job_manager
    _model_manager = model_manager


def get_file_manager() -> FileManager:
    """Get file manager instance."""
    if _file_manager is None:
        raise HTTPException(status_code=500, detail="FileManager not initialized")
    return _file_manager


def get_prompt_manager() -> PromptManager:
    """Get prompt manager instance."""
    if _prompt_manager is None:
        raise HTTPException(status_code=500, detail="PromptManager not initialized")
    return _prompt_manager


def get_job_manager() -> JobManager:
    """Get job manager instance."""
    if _job_manager is None:
        raise HTTPException(status_code=500, detail="JobManager not initialized")
    return _job_manager


def get_model_manager():
    """Get model manager instance."""
    if _model_manager is None:
        raise HTTPException(status_code=500, detail="ModelManager not initialized")
    return _model_manager


@router.post("/upload", response_model=FileUploadResponse, status_code=201)
async def upload_file(
    file: UploadFile = File(...),
    file_manager: FileManager = Depends(get_file_manager)
):
    """
    Upload a file for processing.

    Args:
        file: PDF or image file

    Returns:
        FileUploadResponse with file metadata
    """
    metadata = await file_manager.save_upload(file)

    return FileUploadResponse(
        file_id=metadata.file_id,
        filename=metadata.filename,
        size_bytes=metadata.size_bytes,
        mime_type=metadata.mime_type,
        uploaded_at=metadata.uploaded_at,
        expires_at=metadata.expires_at,
    )


@router.post("/jobs", response_model=JobSubmitResponse, status_code=202)
async def submit_job(
    request: JobSubmitRequest,
    file_manager: FileManager = Depends(get_file_manager),
    prompt_manager: PromptManager = Depends(get_prompt_manager),
    job_manager: JobManager = Depends(get_job_manager),
    model_manager = Depends(get_model_manager)
):
    """
    Submit a processing job.

    Args:
        request: Job submission request

    Returns:
        JobSubmitResponse with job ID and status
    """
    # LOG: What backend received from frontend
    import json
    logger.info("=== BACKEND RECEIVED REQUEST ===")
    logger.info(f"Endpoint: POST /api/v1/process/jobs")
    logger.info(f"Request body: {json.dumps(request.model_dump(exclude_none=True), indent=2)}")
    logger.info("================================")

    # Validate file exists
    try:
        file_metadata = file_manager.get_file_info(request.file_id)
    except HTTPException as e:
        if e.status_code == 404:
            raise HTTPException(status_code=404, detail=f"File not found: {request.file_id}")
        raise

    # Determine model to use
    from config.settings import get_settings
    settings = get_settings()
    model = request.model or settings.default_model

    # Validate custom prompts if provided
    if request.custom_prompts:
        for prompt_type, template in request.custom_prompts.items():
            validation = prompt_manager.validate_prompt(prompt_type, template, model)
            if not validation.valid:
                raise HTTPException(
                    status_code=422,
                    detail=f"Invalid prompt for type '{prompt_type}': {', '.join(validation.warnings)}"
                )

    # Create job
    processing_opts = request.processing_options.model_dump() if request.processing_options else {}

    job = await job_manager.create_job(
        file_id=request.file_id,
        filename=file_metadata.filename,
        model=model,
        prompt_type=request.prompt_type or "markdown",
        custom_prompts=request.custom_prompts,
        processing_options=processing_opts,
        output_format=request.output_format,
        estimated_pages=file_metadata.page_count,
    )

    # Start job processing asynchronously
    job_manager.start_job(
        job_id=job.job_id,
        file_manager=file_manager,
        prompt_manager=prompt_manager,
        model_manager=model_manager
    )

    return JobSubmitResponse(
        job_id=job.job_id,
        status="queued",
        created_at=job.created_at,
        file_id=job.file_id,
        estimated_pages=job.total_pages,
        monitor_url=f"/api/monitoring/stream?job_id={job.job_id}"
    )


@router.get("/jobs/{job_id}", response_model=JobStatusResponse)
async def get_job_status(
    job_id: str,
    job_manager: JobManager = Depends(get_job_manager)
):
    """
    Get job status and details.

    Args:
        job_id: Job ID

    Returns:
        JobStatusResponse with current status
    """
    try:
        job = job_manager.get_job(job_id)
    except ValueError:
        raise HTTPException(status_code=404, detail=f"Job not found: {job_id}")

    # Calculate estimated remaining time (rough estimate)
    estimated_remaining = None
    if job.status == JobStatus.PROCESSING and job.progress_pct > 0:
        if job.started_at:
            from datetime import datetime
            elapsed = (datetime.utcnow() - job.started_at).total_seconds()
            if job.progress_pct > 0:
                total_estimated = elapsed / (job.progress_pct / 100.0)
                estimated_remaining = int(total_estimated - elapsed)

    return JobStatusResponse(
        job_id=job.job_id,
        status=job.status.value,
        created_at=job.created_at,
        started_at=job.started_at,
        completed_at=job.completed_at,
        file_id=job.file_id,
        filename=job.filename,
        total_pages=job.total_pages,
        pages_completed=job.pages_completed,
        current_stage=job.current_stage,
        progress_pct=job.progress_pct,
        estimated_remaining_seconds=estimated_remaining,
        error=job.error,
    )


@router.get("/jobs/{job_id}/result", response_model=JobResultResponse)
async def get_job_result(
    job_id: str,
    job_manager: JobManager = Depends(get_job_manager)
):
    """
    Get processing results.

    Args:
        job_id: Job ID

    Returns:
        JobResultResponse with result content
    """
    try:
        job = job_manager.get_job(job_id)
    except ValueError:
        raise HTTPException(status_code=404, detail=f"Job not found: {job_id}")

    if job.status != JobStatus.COMPLETED:
        raise HTTPException(
            status_code=409,
            detail=f"Job not completed yet (status: {job.status.value})"
        )

    try:
        result = job_manager.get_job_result(job_id)
    except ValueError as e:
        raise HTTPException(status_code=500, detail=str(e))

    return JobResultResponse(
        job_id=job.job_id,
        status="completed",
        result=result,
        completed_at=job.completed_at,
    )


@router.get("/jobs/{job_id}/result/download")
async def download_job_result(
    job_id: str,
    job_manager: JobManager = Depends(get_job_manager)
):
    """
    Download processing results as file.

    Args:
        job_id: Job ID

    Returns:
        FileResponse with result file
    """
    try:
        job = job_manager.get_job(job_id)
    except ValueError:
        raise HTTPException(status_code=404, detail=f"Job not found: {job_id}")

    if job.status != JobStatus.COMPLETED:
        raise HTTPException(
            status_code=409,
            detail=f"Job not completed yet (status: {job.status.value})"
        )

    if not job.result_path or not job.result_path.exists():
        raise HTTPException(status_code=404, detail="Result file not found")

    # Determine media type
    media_type_map = {
        "markdown": "text/markdown",
        "text": "text/plain",
        "json": "application/json",
    }
    media_type = media_type_map.get(job.output_format, "text/plain")

    # Generate download filename
    base_name = Path(job.filename).stem
    download_filename = f"{base_name}.{job.output_format}"

    return FileResponse(
        path=job.result_path,
        media_type=media_type,
        filename=download_filename,
        headers={"Content-Disposition": f'attachment; filename="{download_filename}"'}
    )


@router.delete("/jobs/{job_id}", response_model=JobCancelResponse)
async def cancel_job(
    job_id: str,
    job_manager: JobManager = Depends(get_job_manager)
):
    """
    Cancel a running job.

    Args:
        job_id: Job ID

    Returns:
        JobCancelResponse confirming cancellation
    """
    try:
        job = job_manager.get_job(job_id)
    except ValueError:
        raise HTTPException(status_code=404, detail=f"Job not found: {job_id}")

    try:
        job_manager.cancel_job(job_id)
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))

    return JobCancelResponse(
        job_id=job_id,
        status="cancelled",
        message="Job cancelled successfully"
    )


# PHASE 4: SSE endpoint deprecated - Use Supabase Realtime instead
#
# @router.get("/jobs/{job_id}/stream-results")
# async def stream_job_results(
#     job_id: str,
#     job_manager: JobManager = Depends(get_job_manager)
# ):
#     """
#     Server-Sent Events (SSE) stream of page results as they complete.
#
#     Args:
#         job_id: Job ID
#
#     Returns:
#         SSE stream with ocr_page_complete, merge_page_complete, stage_complete events
#     """
#     # Verify job exists
#     try:
#         job = job_manager.get_job(job_id)
#     except ValueError:
#         raise HTTPException(status_code=404, detail=f"Job not found: {job_id}")
#
#     result_emitter = get_result_emitter()
#
#     async def event_generator():
#         """Generate SSE events for this job."""
#         client_queue = asyncio.Queue()
#
#         try:
#             # Register this client
#             await result_emitter.register_client(job_id, client_queue)
#             logger.info(f"[DEBUG SSE] Client connected and registered for job {job_id}")
#
#             # If job is already completed, send completion event
#             if job.status == JobStatus.COMPLETED:
#                 event = {
#                     "event": "job_complete",
#                     "data": {"timestamp": job.completed_at.isoformat() + 'Z' if job.completed_at else ""}
#                 }
#                 yield f"event: {event['event']}\ndata: {json.dumps(event['data'])}\n\n"
#                 return
#
#             # Stream events as they arrive
#             while True:
#                 try:
#                     # Wait for next event with timeout
#                     event = await asyncio.wait_for(client_queue.get(), timeout=30.0)
#
#                     # Format as SSE
#                     event_type = event.get("event", "message")
#                     data = json.dumps(event.get("data", {}))
#                     logger.info(f"[DEBUG SSE] Sending event '{event_type}' to client for job {job_id}")
#                     yield f"event: {event_type}\ndata: {data}\n\n"
#
#                     # Exit if job complete
#                     if event_type == "job_complete":
#                         break
#
#                 except asyncio.TimeoutError:
#                     # Send keepalive
#                     logger.debug(f"[DEBUG SSE] Sending keepalive for job {job_id}")
#                     yield ": keepalive\n\n"
#
#         except asyncio.CancelledError:
#             logger.info(f"SSE client disconnected for job {job_id}")
#         except Exception as e:
#             logger.error(f"Error in SSE stream for job {job_id}: {e}")
#             error_data = json.dumps({"error": str(e)})
#             yield f"event: error\ndata: {error_data}\n\n"
#         finally:
#             # Unregister client
#             await result_emitter.unregister_client(job_id, client_queue)
#
#     return StreamingResponse(
#         event_generator(),
#         media_type="text/event-stream",
#         headers={
#             "Cache-Control": "no-cache",
#             "Connection": "keep-alive",
#             "X-Accel-Buffering": "no"
#         }
#     )


@router.get("/jobs/{job_id}/stream-results")
async def stream_results_deprecated(job_id: str):
    """
    DEPRECATED: SSE endpoint removed in Phase 4.

    Use Supabase Realtime subscriptions instead:
    - Frontend: useRealtimeJob hook
    - Backend: Database writes trigger Realtime broadcasts

    See Also:
    - web/hooks/useRealtimeJob.ts
    - specs/PHASE_4_IMPLEMENTATION_PLAN.md
    """
    raise HTTPException(
        status_code=410,
        detail={
            "error": "SSE endpoint deprecated",
            "message": "Use Supabase Realtime subscriptions instead",
            "migration_guide": "See web/hooks/useRealtimeJob.ts",
            "job_id": job_id
        }
    )


@router.get("/jobs/{job_id}/ocr-output", response_model=OcrOutputResponse)
async def get_ocr_output(
    job_id: str,
    job_manager: JobManager = Depends(get_job_manager)
):
    """
    Get cached OCR intermediate results.

    Args:
        job_id: Job ID

    Returns:
        OcrOutputResponse with all OCR page results
    """
    try:
        job = job_manager.get_job(job_id)
    except ValueError:
        raise HTTPException(status_code=404, detail=f"Job not found: {job_id}")

    # Find intermediate cache directory
    output_path = job.result_path or (job_manager.output_directory / job_id)
    cache_dir = output_path.parent / f"{output_path.stem}.ocr_cache"

    if not cache_dir.exists():
        raise HTTPException(status_code=404, detail="OCR cache not found")

    # Load all OCR results
    from ...preprocessing.intermediate_cache import IntermediateCache
    cache = IntermediateCache(cache_dir)

    completed_pages = cache.list_completed_pages()
    pages = []

    for page_num in sorted(completed_pages):
        ocr_result = cache.load_ocr_result(page_num)
        if ocr_result:
            pages.append({
                "page_num": page_num + 1,  # Convert to 1-indexed
                "text": ocr_result.ocr_text,
                "processing_time": ocr_result.processing_time,
                "metadata": ocr_result.metadata
            })

    return OcrOutputResponse(
        job_id=job_id,
        pages=pages,
        total_pages=len(pages)
    )


@router.get("/jobs/{job_id}/original")
async def get_original_file(
    job_id: str,
    file_manager: FileManager = Depends(get_file_manager),
    job_manager: JobManager = Depends(get_job_manager)
):
    """
    Return original uploaded file.

    Args:
        job_id: Job ID

    Returns:
        FileResponse with original file
    """
    try:
        job = job_manager.get_job(job_id)
    except ValueError:
        raise HTTPException(status_code=404, detail=f"Job not found: {job_id}")

    # Get original file
    try:
        file_path = file_manager.get_file_path(job.file_id)
    except HTTPException as e:
        if e.status_code == 404:
            raise HTTPException(status_code=404, detail=f"Original file not found for job {job_id}")
        raise

    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Original file no longer exists")

    # Determine media type from file extension
    mime_type_map = {
        ".pdf": "application/pdf",
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".tiff": "image/tiff",
        ".tif": "image/tiff"
    }
    media_type = mime_type_map.get(file_path.suffix.lower(), "application/octet-stream")

    return FileResponse(
        path=file_path,
        media_type=media_type,
        filename=job.filename
    )
