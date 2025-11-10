"""Processing API routes."""
import logging
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, UploadFile, File, HTTPException, Depends
from fastapi.responses import FileResponse

from .models import (
    JobSubmitRequest,
    FileUploadResponse,
    JobSubmitResponse,
    JobStatusResponse,
    JobResultResponse,
    JobCancelResponse,
)
from .services import FileManager, PromptManager, JobManager, JobStatus

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

    job = job_manager.create_job(
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
