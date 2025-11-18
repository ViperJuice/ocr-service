"""Job lifecycle management service."""
import uuid
import threading
import logging
import time
import asyncio
from pathlib import Path
from datetime import datetime, timezone
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
        job_repository=None,
        streaming_repository=None,
        container_orchestrator=None,
        baml_ocr_service=None
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
            streaming_repository: Optional StreamingTokenRepository for Phase 4 streaming
            container_orchestrator: Optional ContainerOrchestrator for lifecycle management
            baml_ocr_service: Optional BAMLOCRService for type-safe OCR operations with streaming
        """
        self.processing_directory = Path(processing_directory)
        self.output_directory = Path(output_directory)
        self.max_concurrent_jobs = max_concurrent_jobs
        self.result_emitter = result_emitter
        self._event_loop = event_loop
        self.job_repository = job_repository
        self.streaming_repository = streaming_repository
        self.container_orchestrator = container_orchestrator
        self.baml_ocr_service = baml_ocr_service

        self.processing_directory.mkdir(parents=True, exist_ok=True)
        self.output_directory.mkdir(parents=True, exist_ok=True)

        # PHASE 4: In-memory state removed - database is single source of truth
        # self.jobs and self.job_lock removed - all job state now in database

        # Processing threads
        self.processing_threads: Dict[str, threading.Thread] = {}

        # Progress callbacks
        # THREAD SAFETY AUDIT (Phase 3.7B):
        # - progress_callbacks dict is modified from worker threads
        # - No lock protection currently, but callbacks are set before job starts
        # - Read-only during job execution, so no race condition
        self.progress_callbacks: Dict[str, Any] = {}

        # Active processing count
        self.active_count = 0

        # Semaphore for enforcing max concurrent jobs
        self.job_semaphore = threading.Semaphore(max_concurrent_jobs)

        logger.info(
            f"JobManager initialized: processing={processing_directory}, "
            f"output={output_directory}, max_concurrent={max_concurrent_jobs}"
        )

    def _dict_to_job(self, db_record: Dict[str, Any]) -> Job:
        """
        Convert database record to Job dataclass.

        Args:
            db_record: Database record dict

        Returns:
            Job dataclass instance
        """
        return Job(
            job_id=str(db_record['job_id']),
            file_id=str(db_record['file_id']),
            filename=db_record['filename'],
            model=db_record['model'],
            prompt_type=db_record['prompt_type'],
            custom_prompts=db_record.get('custom_prompts'),
            processing_options=db_record.get('processing_options', {}),
            output_format=db_record['output_format'],
            status=JobStatus(db_record['status']),
            created_at=datetime.fromisoformat(db_record['created_at']) if isinstance(db_record['created_at'], str) else db_record['created_at'],
            started_at=datetime.fromisoformat(db_record['started_at']) if db_record.get('started_at') and isinstance(db_record['started_at'], str) else db_record.get('started_at'),
            completed_at=datetime.fromisoformat(db_record['completed_at']) if db_record.get('completed_at') and isinstance(db_record['completed_at'], str) else db_record.get('completed_at'),
            total_pages=db_record.get('total_pages'),
            pages_completed=db_record.get('pages_completed', 0),
            current_stage=db_record.get('current_stage'),
            progress_pct=db_record.get('progress_pct', 0.0),
            result_path=Path(db_record['result_path']) if db_record.get('result_path') else None,
            error=db_record.get('error_message'),
            cancel_requested=db_record.get('cancel_requested', False),
            parent_batch_id=str(db_record['parent_batch_id']) if db_record.get('parent_batch_id') else None
        )

    async def create_job(
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

        # PHASE 4: Database-only (no in-memory state)
        if not self.job_repository:
            raise RuntimeError("Job repository required for database-only mode")

        from uuid import UUID

        # Get user_id from processing_options or use dev default
        user_id_str = processing_options.get('user_id', 'a0000000-0000-0000-0000-000000000001')

        # Write to database ONLY
        logger.info(f"Creating job {job_id} in database for file {file_id}")
        db_job = await self.job_repository.create_job(
            job_id=UUID(job_id),
            user_id=UUID(user_id_str),
            file_id=UUID(file_id),
            filename=filename,
            model=model,
            prompt_type=prompt_type,
            custom_prompts=custom_prompts,
            processing_options=processing_options,
            output_format=output_format,
            parent_batch_id=None  # Set via processing_options if needed
        )

        if not db_job:
            raise RuntimeError(f"Failed to create job {job_id} in database")

        logger.info(f"Job created in database: {job_id}")
        return self._dict_to_job(db_job)

    async def get_job(self, job_id: str) -> Job:
        """
        Get job by ID from database.

        Args:
            job_id: Job ID

        Returns:
            Job object

        Raises:
            ValueError: If job not found
        """
        # PHASE 4: Read from database only
        if not self.job_repository:
            raise RuntimeError("Job repository required for database-only mode")

        from uuid import UUID

        db_job = await self.job_repository.get_job(UUID(job_id))

        if not db_job:
            raise ValueError(f"Job not found: {job_id}")

        return self._dict_to_job(db_job)

    async def _check_cancellation_from_db(self, job_id: str) -> bool:
        """
        Check if job cancelled by reading from database.

        Args:
            job_id: Job ID

        Returns:
            True if job is cancelled

        Note:
            This method is called periodically during processing to check cancellation.
        """
        try:
            job = await self.get_job(job_id)
            return job.cancel_requested
        except Exception as e:
            logger.error(f"Failed to check cancellation for {job_id}: {e}")
            return False

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
        # PHASE 4: Database-only - job will be fetched by the processing thread
        if not self.job_repository or not self._event_loop:
            raise RuntimeError("Job repository and event loop required for database-only mode")

        # Create processing thread - it will fetch job from database and update status
        thread = threading.Thread(
            target=self._process_job_async,
            args=(job_id, file_manager, prompt_manager, model_manager),
            daemon=True
        )

        self.processing_threads[job_id] = thread
        thread.start()

        logger.info(f"Job processing thread started: {job_id}")

    def _process_job_async(
        self,
        job_id: str,
        file_manager,
        prompt_manager,
        model_manager
    ) -> None:
        """
        Process job asynchronously (runs in background thread).

        Args:
            job_id: Job ID
            file_manager: FileManager instance
            prompt_manager: PromptManager instance
            model_manager: ModelManager instance
        """
        from uuid import UUID

        # PHASE 4: Fetch job from database at the start of processing
        try:
            future = asyncio.run_coroutine_threadsafe(
                self.get_job(job_id),
                self._event_loop
            )
            job = future.result(timeout=10)
            logger.info(f"Job {job_id} fetched from database successfully")
        except Exception as e:
            logger.error(f"Failed to fetch job {job_id} from database: {e}")
            return

        # Update job status to processing
        started_at = datetime.now(timezone.utc)
        try:
            future = asyncio.run_coroutine_threadsafe(
                self.job_repository.update_job_status(
                    job_id=UUID(job_id),
                    status="processing",
                    started_at=started_at
                ),
                self._event_loop
            )
            future.result(timeout=5)
            logger.info(f"Job {job_id} status updated to 'processing' in database")
        except Exception as e:
            logger.error(f"Failed to update job {job_id} status to 'processing': {e}")
            return

        # Create job_started event (non-critical, continue if fails)
        try:
            future_event = asyncio.run_coroutine_threadsafe(
                self.job_repository.create_job_event(
                    job_id=UUID(job_id),
                    event_type="job_started",
                    event_data={"started_at": started_at.isoformat()}
                ),
                self._event_loop
            )
            future_event.result(timeout=5)
            logger.info(f"Job {job_id} 'job_started' event created")
        except Exception as e:
            logger.warning(f"Failed to create 'job_started' event for job {job_id}: {e} (non-critical, continuing)")

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

            # Create pipeline coordinator for container orchestration
            pipeline_coordinator = None
            if self.container_orchestrator:
                from ...preprocessing.pipeline_coordinator import PipelineCoordinator
                pipeline_coordinator = PipelineCoordinator(
                    container_orchestrator=self.container_orchestrator,
                    job_id=job.job_id,
                    result_emitter=self.result_emitter,
                    event_loop=self._event_loop
                )
                logger.info(f"Pipeline coordinator created for job {job.job_id}")

            # Initialize staged pipeline
            processor = StagedPipelineProcessor(
                model_manager=model_manager,
                pdf_handler=pdf_handler,
                pipeline_coordinator=pipeline_coordinator,
                verbose=False,
                enable_memory_profiling=False,
                enable_system_monitoring=True,
                prefer_quality=job.processing_options.get('prefer_quality', True),
                progress_callback=progress_callback,
                result_emitter=self.result_emitter,
                job_id=job.job_id,
                event_loop=self._event_loop,
                job_repository=self.job_repository,  # Phase 3.7A: For bulk DB inserts
                streaming_repository=self.streaming_repository,  # Phase 4: For token streaming
                baml_ocr_service=self.baml_ocr_service  # Phase 4: For type-safe streaming OCR
            )

            # Extract page range from processing options
            start_page = job.processing_options.get('start_page')
            end_page = job.processing_options.get('end_page')

            # Check for cancellation before starting
            if job.cancel_requested:
                # PHASE 4: Job state managed in database only
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
                # PHASE 4: Job state managed in database only
                logger.info(f"Job cancelled after processing: {job.job_id}")
                return

            # PHASE 4: Job completion tracked in database only (via update below)
            completed_at = datetime.now(timezone.utc)
            total_pages = result.get('total_pages')
            pages_completed = result.get('total_pages', 0)

            # PHASE 4: Update database (database is single source of truth)
            if self.job_repository and self._event_loop:
                try:
                    from uuid import UUID

                    future = asyncio.run_coroutine_threadsafe(
                        self.job_repository.update_job_status(
                            job_id=UUID(job.job_id),
                            status="completed",
                            completed_at=completed_at
                        ),
                        self._event_loop
                    )
                    future.result(timeout=5)

                    # Update result path and progress
                    future_result = asyncio.run_coroutine_threadsafe(
                        self.job_repository.update_job_result(
                            job_id=UUID(job.job_id),
                            result_path=str(output_path)
                        ),
                        self._event_loop
                    )
                    future_result.result(timeout=5)

                    # Update total pages and final progress
                    future_progress = asyncio.run_coroutine_threadsafe(
                        self.job_repository.update_job_progress(
                            job_id=UUID(job.job_id),
                            progress_pct=100.0,
                            pages_completed=pages_completed,
                            current_stage="completed",
                            total_pages=total_pages
                        ),
                        self._event_loop
                    )
                    future_progress.result(timeout=5)

                    # Get started_at from job for processing time calculation
                    future_get_job = asyncio.run_coroutine_threadsafe(
                        self.get_job(job.job_id),
                        self._event_loop
                    )
                    job_from_db = future_get_job.result(timeout=5)
                    processing_time = (completed_at - job_from_db.started_at).total_seconds() if job_from_db and job_from_db.started_at else 0

                    # Log completion event
                    future_event = asyncio.run_coroutine_threadsafe(
                        self.job_repository.create_job_event(
                            job_id=UUID(job.job_id),
                            event_type="job_completed",
                            event_data={
                                "total_pages": total_pages,
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

            # PHASE 4: Job failure tracked in database only
            failed_at = datetime.now(timezone.utc)

            # Update database (database is single source of truth)
            if self.job_repository and self._event_loop:
                try:
                    from uuid import UUID

                    future = asyncio.run_coroutine_threadsafe(
                        self.job_repository.update_job_status(
                            job_id=UUID(job.job_id),
                            status="failed",
                            error_message=str(e),
                            completed_at=failed_at
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
            # GPU memory management in container mode:
            # Models are automatically unloaded by containers after each inference
            # via auto_unload=True flag passed through BAML service and HTTP client.
            # No explicit cleanup needed here - containers manage their own lifecycle.
            logger.info(f"Job {job.job_id} cleanup complete (GPU managed by containers)")

            # Release semaphore
            self.job_semaphore.release()
            logger.info(f"Job {job.job_id} released processing slot")

            # Cleanup thread reference
            # PHASE 4: Thread cleanup doesn't need lock (dict operations are atomic for single key)
            if job.job_id in self.processing_threads:
                del self.processing_threads[job.job_id]

    async def cancel_job(self, job_id: str) -> bool:
        """
        Cancel a running job by writing to database.

        Args:
            job_id: Job ID

        Returns:
            True if cancelled successfully

        Raises:
            ValueError: If job not found or already completed
        """
        # PHASE 4: Read from database
        job = await self.get_job(job_id)

        if job.status == JobStatus.COMPLETED:
            raise ValueError("Cannot cancel completed job")

        if job.status == JobStatus.FAILED:
            raise ValueError("Cannot cancel failed job")

        if job.status == JobStatus.CANCELLED:
            return True  # Already cancelled

        # Wait for thread to finish (with timeout)
        if job_id in self.processing_threads:
            thread = self.processing_threads[job_id]
            thread.join(timeout=10)

            if thread.is_alive():
                logger.warning(f"Job thread did not terminate cleanly: {job_id}")

        # PHASE 4: Write cancellation to database only
        if not self.job_repository:
            raise RuntimeError("Job repository required for database-only mode")

        from uuid import UUID

        await self.job_repository.update_job_status(
            job_id=UUID(job_id),
            status="cancelled",
            completed_at=datetime.now(timezone.utc)
        )

        # Log cancellation event
        await self.job_repository.create_job_event(
            job_id=UUID(job_id),
            event_type="job_cancelled",
            event_data={"cancelled_at": datetime.now(timezone.utc).isoformat()}
        )

        logger.info(f"Job cancelled in database: {job_id}")
        return True

    async def get_job_result(self, job_id: str) -> Dict[str, Any]:
        """
        Get job result.

        Args:
            job_id: Job ID

        Returns:
            Result dict with content and metadata

        Raises:
            ValueError: If job not found or not completed
        """
        job = await self.get_job(job_id)

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
        # PHASE 4: Database-only mode - no in-memory state to update

        # Update database (database is single source of truth)
        if self.job_repository and self._event_loop:
            try:
                from uuid import UUID

                # Get total pages from database if needed
                future_get = asyncio.run_coroutine_threadsafe(
                    self.get_job(job_id),
                    self._event_loop
                )
                job = future_get.result(timeout=5)
                total_pages = job.total_pages if job else None

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
        # PHASE 4: Database-only mode - no in-memory jobs to clean up
        # This method is now a no-op as cleanup should be handled at the database level
        # Consider implementing database-level archival/cleanup if needed
        logger.info("cleanup_old_jobs called in database-only mode - no action taken")
        return 0

    def get_queue_stats(self) -> dict:
        """
        Get current queue statistics.

        Returns:
            Dictionary with counts for each job status
        """
        # PHASE 4: Database-only mode - no in-memory jobs to count
        # This method should query the database for stats
        # For now, return empty stats with a warning
        logger.warning("get_queue_stats called in database-only mode - returning empty stats")
        stats = {
            "queued": 0,
            "processing": 0,
            "completed": 0,
            "failed": 0,
            "cancelled": 0
        }
        return stats

    async def wait_for_active_jobs(self) -> None:
        """
        Wait for all active processing jobs to complete.

        Used during graceful shutdown to ensure jobs finish before cleanup.
        Polls every 0.5 seconds until no active jobs remain.
        """
        # PHASE 4: Database-only mode - query database for active jobs
        if not self.job_repository:
            logger.warning("wait_for_active_jobs called without job_repository - cannot check active jobs")
            return

        while True:
            # Query database for active jobs
            # Note: This would require adding a method to job_repository to count active jobs
            # For now, just check if we have any processing threads
            active_threads = len(self.processing_threads)

            if active_threads == 0:
                logger.info("No active job threads remaining")
                break

            logger.info(f"Waiting for {active_threads} active job thread(s) to complete...")
            await asyncio.sleep(0.5)
