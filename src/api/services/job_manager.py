"""Job lifecycle management service."""
import uuid
import threading
import logging
import time
import asyncio
from pathlib import Path
from datetime import datetime
from typing import Dict, Optional, Any
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger(__name__)


class JobStatus(Enum):
    """Job status enum."""
    QUEUED = "queued"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class Job:
    """Internal job representation."""
    job_id: str
    file_id: str
    filename: str
    model: str
    prompt_type: str
    custom_prompts: Optional[Dict[str, str]]
    processing_options: Dict[str, Any]
    output_format: str
    status: JobStatus
    created_at: datetime
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    total_pages: Optional[int] = None
    pages_completed: int = 0
    current_stage: Optional[str] = None
    progress_pct: float = 0.0
    result_path: Optional[Path] = None
    error: Optional[str] = None
    cancel_requested: bool = False
    parent_batch_id: Optional[str] = None  # NEW: Parent batch job ID if applicable


class JobManager:
    """Manage job lifecycle and processing."""

    def __init__(
        self,
        processing_directory: str,
        output_directory: str,
        max_concurrent_jobs: int = 2,
        result_emitter=None,
        event_loop=None,
        job_repository=None
    ):
        """
        Initialize job manager.

        Args:
            processing_directory: Directory for active processing
            output_directory: Directory for completed results
            max_concurrent_jobs: Maximum concurrent processing jobs
            result_emitter: Optional ResultEmitter for streaming results
            event_loop: Optional event loop for thread-safe async operations
            job_repository: Optional JobRepository for database writes (Phase 2)
        """
        self.processing_directory = Path(processing_directory)
        self.output_directory = Path(output_directory)
        self.max_concurrent_jobs = max_concurrent_jobs
        self.result_emitter = result_emitter
        self._event_loop = event_loop
        self.job_repository = job_repository

        self.processing_directory.mkdir(parents=True, exist_ok=True)
        self.output_directory.mkdir(parents=True, exist_ok=True)

        # In-memory job registry
        self.jobs: Dict[str, Job] = {}
        self.job_lock = threading.Lock()

        # Processing threads
        self.processing_threads: Dict[str, threading.Thread] = {}

        # Progress callbacks
        self.progress_callbacks: Dict[str, Any] = {}

        # Active processing count
        self.active_count = 0

        # Semaphore for enforcing max concurrent jobs
        self.job_semaphore = threading.Semaphore(max_concurrent_jobs)

        logger.info(
            f"JobManager initialized: processing={processing_directory}, "
            f"output={output_directory}, max_concurrent={max_concurrent_jobs}"
        )

    def create_job(
        self,
        file_id: str,
        filename: str,
        model: str,
        prompt_type: str,
        custom_prompts: Optional[Dict[str, str]],
        processing_options: Dict[str, Any],
        output_format: str,
        estimated_pages: Optional[int] = None
    ) -> Job:
        """
        Create a new job.

        Args:
            file_id: File ID to process
            filename: Original filename
            model: Model to use
            prompt_type: Prompt type
            custom_prompts: Optional custom prompts
            processing_options: Processing options
            output_format: Output format
            estimated_pages: Estimated page count

        Returns:
            Job object
        """
        job_id = str(uuid.uuid4())

        with self.job_lock:
            job = Job(
                job_id=job_id,
                file_id=file_id,
                filename=filename,
                model=model,
                prompt_type=prompt_type,
                custom_prompts=custom_prompts,
                processing_options=processing_options,
                output_format=output_format,
                status=JobStatus.QUEUED,
                created_at=datetime.utcnow(),
                total_pages=estimated_pages,
            )
            self.jobs[job_id] = job

        logger.info(f"Job created: {job_id} for file {file_id}")

        # Write to database (Phase 2: dual-write)
        if self.job_repository and self._event_loop:
            try:
                from uuid import UUID

                # Get user_id from processing_options or use dev default
                user_id_str = processing_options.get('user_id', 'a0000000-0000-0000-0000-000000000001')

                future = asyncio.run_coroutine_threadsafe(
                    self.job_repository.create_job(
                        user_id=UUID(user_id_str),
                        file_id=UUID(file_id),
                        filename=filename,
                        model=model,
                        prompt_type=prompt_type,
                        custom_prompts=custom_prompts,
                        processing_options=processing_options,
                        output_format=output_format,
                        parent_batch_id=UUID(job.parent_batch_id) if job.parent_batch_id else None
                    ),
                    self._event_loop
                )

                db_job = future.result(timeout=5)
                logger.info(f"Job {job_id} written to database")

                # Log creation event
                future_event = asyncio.run_coroutine_threadsafe(
                    self.job_repository.create_job_event(
                        job_id=UUID(job_id),
                        event_type="job_created",
                        event_data={
                            "filename": filename,
                            "model": model,
                            "estimated_pages": estimated_pages
                        }
                    ),
                    self._event_loop
                )
                future_event.result(timeout=5)

            except Exception as e:
                logger.error(f"Failed to write job {job_id} to database: {e}", exc_info=True)
                # Don't fail request - fallback to in-memory

        return job

    def get_job(self, job_id: str) -> Job:
        """
        Get job by ID.

        Args:
            job_id: Job ID

        Returns:
            Job object

        Raises:
            ValueError: If job not found
        """
        with self.job_lock:
            if job_id not in self.jobs:
                raise ValueError(f"Job not found: {job_id}")
            return self.jobs[job_id]

    def start_job(
        self,
        job_id: str,
        file_manager,
        prompt_manager,
        model_manager
    ) -> None:
        """
        Start processing a job asynchronously.

        Args:
            job_id: Job ID
            file_manager: FileManager instance
            prompt_manager: PromptManager instance
            model_manager: ModelManager instance
        """
        job = self.get_job(job_id)

        # Update status
        with self.job_lock:
            job.status = JobStatus.PROCESSING
            job.started_at = datetime.utcnow()

        # Update database (Phase 2: dual-write)
        if self.job_repository and self._event_loop:
            try:
                from uuid import UUID

                future = asyncio.run_coroutine_threadsafe(
                    self.job_repository.update_job_status(
                        job_id=UUID(job_id),
                        status="processing",
                        started_at=job.started_at
                    ),
                    self._event_loop
                )
                future.result(timeout=5)

                # Log start event
                future_event = asyncio.run_coroutine_threadsafe(
                    self.job_repository.create_job_event(
                        job_id=UUID(job_id),
                        event_type="job_started",
                        event_data={"started_at": job.started_at.isoformat()}
                    ),
                    self._event_loop
                )
                future_event.result(timeout=5)

            except Exception as e:
                logger.error(f"Failed to update job {job_id} status in database: {e}")

        # Create processing thread
        thread = threading.Thread(
            target=self._process_job_async,
            args=(job, file_manager, prompt_manager, model_manager),
            daemon=True
        )

        self.processing_threads[job_id] = thread
        thread.start()

        logger.info(f"Job processing started: {job_id}")

    def _process_job_async(
        self,
        job: Job,
        file_manager,
        prompt_manager,
        model_manager
    ) -> None:
        """
        Process job asynchronously (runs in background thread).

        Args:
            job: Job object
            file_manager: FileManager instance
            prompt_manager: PromptManager instance
            model_manager: ModelManager instance
        """
        # Acquire semaphore to enforce max concurrent jobs
        logger.info(f"Job {job.job_id} waiting for processing slot...")
        self.job_semaphore.acquire()

        try:
            logger.info(f"Job {job.job_id} starting processing (container mode)...")
            # Get file path
            file_path = file_manager.get_file_path(job.file_id)

            # Get prompts (merge custom with defaults)
            default_prompts = prompt_manager.get_default_prompts(job.model)
            merged_prompts = prompt_manager.merge_prompts(default_prompts, job.custom_prompts)

            # Set up output path
            output_filename = f"{job.job_id}.{job.output_format}"
            output_path = self.output_directory / job.job_id / output_filename

            # Create job output directory
            output_path.parent.mkdir(parents=True, exist_ok=True)

            # Import processing pipeline
            from ...preprocessing.staged_pipeline import StagedPipelineProcessor
            from ...preprocessing.pdf_handler import PDFHandler

            # Initialize PDF handler
            pdf_handler = PDFHandler()

            # Create progress callback for this job
            def progress_callback(progress_pct: float, pages_completed: int, stage: str):
                """Progress callback from staged pipeline."""
                self._emit_progress(job.job_id, progress_pct, pages_completed, stage)

            # Initialize staged pipeline
            processor = StagedPipelineProcessor(
                model_manager=model_manager,
                pdf_handler=pdf_handler,
                verbose=False,
                enable_memory_profiling=False,
                enable_system_monitoring=True,
                prefer_quality=job.processing_options.get('prefer_quality', True),
                progress_callback=progress_callback,
                result_emitter=self.result_emitter,
                job_id=job.job_id,
                event_loop=self._event_loop
            )

            # Extract page range from processing options
            start_page = job.processing_options.get('start_page')
            end_page = job.processing_options.get('end_page')

            # Check for cancellation before starting
            if job.cancel_requested:
                with self.job_lock:
                    job.status = JobStatus.CANCELLED
                    job.completed_at = datetime.utcnow()
                logger.info(f"Job cancelled before processing: {job.job_id}")
                return

            # Process PDF
            result = processor.process_pdf(
                pdf_path=file_path,
                output_path=output_path,
                dpi=job.processing_options.get('dpi', 300),
                output_format=job.output_format,
                resume=False,  # API jobs don't support resume initially
                job_id=job.job_id,
                start_page=start_page,
                end_page=end_page
            )

            # Check for cancellation after processing
            if job.cancel_requested:
                with self.job_lock:
                    job.status = JobStatus.CANCELLED
                    job.completed_at = datetime.utcnow()
                logger.info(f"Job cancelled after processing: {job.job_id}")
                return

            # Update job status
            with self.job_lock:
                job.status = JobStatus.COMPLETED
                job.completed_at = datetime.utcnow()
                job.result_path = output_path
                job.total_pages = result.get('total_pages')
                job.pages_completed = result.get('total_pages', 0)
                job.progress_pct = 100.0

            # Update database (Phase 2: dual-write)
            if self.job_repository and self._event_loop:
                try:
                    from uuid import UUID

                    future = asyncio.run_coroutine_threadsafe(
                        self.job_repository.update_job_status(
                            job_id=UUID(job.job_id),
                            status="completed",
                            completed_at=job.completed_at
                        ),
                        self._event_loop
                    )
                    future.result(timeout=5)

                    # Update result path
                    future_result = asyncio.run_coroutine_threadsafe(
                        self.job_repository.update_job_result(
                            job_id=UUID(job.job_id),
                            result_path=str(output_path)
                        ),
                        self._event_loop
                    )
                    future_result.result(timeout=5)

                    # Log completion event
                    processing_time = (job.completed_at - job.started_at).total_seconds() if job.started_at else 0
                    future_event = asyncio.run_coroutine_threadsafe(
                        self.job_repository.create_job_event(
                            job_id=UUID(job.job_id),
                            event_type="job_completed",
                            event_data={
                                "total_pages": job.total_pages,
                                "processing_time": processing_time
                            }
                        ),
                        self._event_loop
                    )
                    future_event.result(timeout=5)

                except Exception as e:
                    logger.error(f"Failed to update job {job.job_id} completion in database: {e}")

            logger.info(f"Job completed successfully: {job.job_id}")

        except Exception as e:
            logger.error(f"Job processing failed: {job.job_id}: {e}", exc_info=True)

            # Update job status to failed
            with self.job_lock:
                job.status = JobStatus.FAILED
                job.completed_at = datetime.utcnow()
                job.error = str(e)

            # Update database (Phase 2: dual-write)
            if self.job_repository and self._event_loop:
                try:
                    from uuid import UUID

                    future = asyncio.run_coroutine_threadsafe(
                        self.job_repository.update_job_status(
                            job_id=UUID(job.job_id),
                            status="failed",
                            error_message=str(e),
                            completed_at=job.completed_at
                        ),
                        self._event_loop
                    )
                    future.result(timeout=5)

                    # Log failure event
                    future_event = asyncio.run_coroutine_threadsafe(
                        self.job_repository.create_job_event(
                            job_id=UUID(job.job_id),
                            event_type="job_failed",
                            event_data={
                                "error": str(e),
                                "error_type": type(e).__name__
                            }
                        ),
                        self._event_loop
                    )
                    future_event.result(timeout=5)

                except Exception as db_error:
                    logger.error(f"Failed to update job {job.job_id} failure in database: {db_error}")

        finally:
            # Unload models explicitly to free GPU memory (emergency fallback)
            if model_manager and self._event_loop:
                try:
                    future = asyncio.run_coroutine_threadsafe(
                        model_manager.unload_all(),
                        self._event_loop
                    )
                    unload_results = future.result(timeout=30)
                    logger.info(f"Job {job.job_id} cleanup: unloaded models - {unload_results}")
                except Exception as e:
                    logger.warning(f"Failed to unload models for job {job.job_id}: {e}")

            # GPU resources managed by containers

            # Release semaphore
            self.job_semaphore.release()
            logger.info(f"Job {job.job_id} released processing slot")

            # Cleanup thread reference
            with self.job_lock:
                if job.job_id in self.processing_threads:
                    del self.processing_threads[job.job_id]

    def cancel_job(self, job_id: str) -> bool:
        """
        Cancel a running job.

        Args:
            job_id: Job ID

        Returns:
            True if cancelled successfully

        Raises:
            ValueError: If job not found or already completed
        """
        job = self.get_job(job_id)

        if job.status == JobStatus.COMPLETED:
            raise ValueError("Cannot cancel completed job")

        if job.status == JobStatus.FAILED:
            raise ValueError("Cannot cancel failed job")

        if job.status == JobStatus.CANCELLED:
            return True  # Already cancelled

        # Set cancellation flag
        with self.job_lock:
            job.cancel_requested = True

        # Wait for thread to finish (with timeout)
        if job_id in self.processing_threads:
            thread = self.processing_threads[job_id]
            thread.join(timeout=10)

            if thread.is_alive():
                logger.warning(f"Job thread did not terminate cleanly: {job_id}")

        # Update status if not already updated by thread
        with self.job_lock:
            if job.status != JobStatus.CANCELLED:
                job.status = JobStatus.CANCELLED
                job.completed_at = datetime.utcnow()

        # Update database (Phase 2: dual-write)
        if self.job_repository and self._event_loop:
            try:
                from uuid import UUID

                future = asyncio.run_coroutine_threadsafe(
                    self.job_repository.update_job_status(
                        job_id=UUID(job_id),
                        status="cancelled",
                        completed_at=job.completed_at
                    ),
                    self._event_loop
                )
                future.result(timeout=5)

                # Log cancellation event
                future_event = asyncio.run_coroutine_threadsafe(
                    self.job_repository.create_job_event(
                        job_id=UUID(job_id),
                        event_type="job_cancelled",
                        event_data={"cancelled_at": job.completed_at.isoformat()}
                    ),
                    self._event_loop
                )
                future_event.result(timeout=5)

            except Exception as e:
                logger.error(f"Failed to update job {job_id} cancellation in database: {e}")

        logger.info(f"Job cancelled: {job_id}")
        return True

    def get_job_result(self, job_id: str) -> Dict[str, Any]:
        """
        Get job result.

        Args:
            job_id: Job ID

        Returns:
            Result dict with content and metadata

        Raises:
            ValueError: If job not found or not completed
        """
        job = self.get_job(job_id)

        if job.status != JobStatus.COMPLETED:
            raise ValueError(f"Job not completed: {job.status.value}")

        if not job.result_path or not job.result_path.exists():
            raise ValueError("Result file not found")

        # Read result file
        with open(job.result_path, 'r', encoding='utf-8') as f:
            content = f.read()

        # Calculate processing time
        processing_time = 0.0
        if job.started_at and job.completed_at:
            processing_time = (job.completed_at - job.started_at).total_seconds()

        # Try to load DeepSeek-OCR intermediate output
        deepseek_ocr_content = None
        cache_dir = job.result_path.parent / f"{job.result_path.stem}.ocr_cache"
        if cache_dir.exists():
            try:
                from ...preprocessing.intermediate_cache import IntermediateCache
                cache = IntermediateCache(cache_dir)
                completed_pages = sorted(cache.list_completed_pages())

                # Combine all OCR results
                ocr_texts = []
                for page_num in completed_pages:
                    ocr_result = cache.load_ocr_result(page_num)
                    if ocr_result:
                        ocr_texts.append(f"--- Page {page_num + 1} ---\n{ocr_result.ocr_text}")

                if ocr_texts:
                    deepseek_ocr_content = "\n\n".join(ocr_texts)
            except Exception as e:
                logger.warning(f"Failed to load OCR cache for job {job_id}: {e}")

        result = {
            "format": job.output_format,
            "content": content,
            "total_pages": job.total_pages,
            "processing_time_seconds": processing_time,
            "model_used": job.model,
            "metadata": {
                "dpi": job.processing_options.get('dpi', 300),
                "method": job.processing_options.get('method', 'auto'),
                "pages_processed": job.total_pages or 0,
            }
        }

        # Add optional fields
        if deepseek_ocr_content:
            result["deepseek_ocr_content"] = deepseek_ocr_content

        # Add original file URL
        result["original_file_url"] = f"/api/v1/process/jobs/{job_id}/original"

        return result

    def update_job_progress(
        self,
        job_id: str,
        progress_pct: float,
        pages_completed: int,
        stage: str
    ) -> None:
        """
        Update job progress metrics.

        Args:
            job_id: Job ID
            progress_pct: Progress percentage (0-100)
            pages_completed: Number of pages completed
            stage: Current stage name
        """
        # Update in-memory (existing)
        with self.job_lock:
            if job_id in self.jobs:
                job = self.jobs[job_id]
                job.progress_pct = progress_pct
                job.pages_completed = pages_completed
                job.current_stage = stage

        # Update database (Phase 2: dual-write)
        if self.job_repository and self._event_loop:
            try:
                from uuid import UUID

                # Get total pages from in-memory job
                total_pages = None
                with self.job_lock:
                    if job_id in self.jobs:
                        total_pages = self.jobs[job_id].total_pages

                future = asyncio.run_coroutine_threadsafe(
                    self.job_repository.update_job_progress(
                        job_id=UUID(job_id),
                        progress_pct=progress_pct,
                        pages_completed=pages_completed,
                        current_stage=stage,
                        total_pages=total_pages
                    ),
                    self._event_loop
                )
                future.result(timeout=5)

            except Exception as e:
                logger.error(f"Failed to update job {job_id} progress in database: {e}")

    def set_progress_callback(self, job_id: str, callback) -> None:
        """
        Set a progress callback for real-time updates.

        Args:
            job_id: Job identifier
            callback: Callback function(progress_pct, pages_completed, stage)
        """
        self.progress_callbacks[job_id] = callback
        logger.info(f"Progress callback set for job: {job_id}")

    def _emit_progress(
        self,
        job_id: str,
        progress_pct: float,
        pages_completed: int,
        stage: str
    ) -> None:
        """
        Internal method to emit progress via callback.

        Args:
            job_id: Job identifier
            progress_pct: Progress percentage (0-100)
            pages_completed: Number of pages completed
            stage: Current processing stage
        """
        # Update job progress
        self.update_job_progress(job_id, progress_pct, pages_completed, stage)

        # Call callback if registered
        if job_id in self.progress_callbacks:
            try:
                self.progress_callbacks[job_id](progress_pct, pages_completed, stage)
            except Exception as e:
                logger.error(f"Progress callback error for job {job_id}: {e}")

    def cleanup_old_jobs(self, max_jobs: int) -> int:
        """
        Clean up old completed/failed jobs.

        Args:
            max_jobs: Maximum number of jobs to keep

        Returns:
            Number of jobs cleaned up
        """
        with self.job_lock:
            # Sort jobs by creation time
            sorted_jobs = sorted(
                self.jobs.values(),
                key=lambda j: j.created_at,
                reverse=True
            )

            # Keep only completed/failed jobs beyond max
            jobs_to_remove = []
            for job in sorted_jobs[max_jobs:]:
                if job.status in [JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.CANCELLED]:
                    jobs_to_remove.append(job.job_id)

            # Remove jobs
            for job_id in jobs_to_remove:
                del self.jobs[job_id]

            if jobs_to_remove:
                logger.info(f"Cleaned up {len(jobs_to_remove)} old jobs")

            return len(jobs_to_remove)

    def get_queue_stats(self) -> dict:
        """
        Get current queue statistics.

        Returns:
            Dictionary with counts for each job status
        """
        with self.job_lock:
            stats = {
                "queued": 0,
                "processing": 0,
                "completed": 0,
                "failed": 0,
                "cancelled": 0
            }

            for job in self.jobs.values():
                status = job.status.value.lower() if hasattr(job.status, 'value') else str(job.status).lower()
                if status in stats:
                    stats[status] += 1

            return stats
