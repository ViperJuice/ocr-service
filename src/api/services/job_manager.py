"""Job lifecycle management service."""
import uuid
import threading
import logging
import time
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
        gpu_tracker=None,
        system_capability: Optional[Dict] = None
    ):
        """
        Initialize job manager.

        Args:
            processing_directory: Directory for active processing
            output_directory: Directory for completed results
            max_concurrent_jobs: Maximum concurrent processing jobs
            gpu_tracker: Optional GPUResourceTracker for VRAM management
            system_capability: System capability info from CapabilityDetector
        """
        self.processing_directory = Path(processing_directory)
        self.output_directory = Path(output_directory)
        self.max_concurrent_jobs = max_concurrent_jobs
        self.gpu_tracker = gpu_tracker
        self.system_capability = system_capability

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

        tier_msg = ""
        if system_capability:
            tier_msg = f", system_tier={system_capability['max_tier']}"

        logger.info(
            f"JobManager initialized: processing={processing_directory}, "
            f"output={output_directory}, max_concurrent={max_concurrent_jobs}, "
            f"gpu_tracking={'enabled' if gpu_tracker else 'disabled'}{tier_msg}"
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

        vram_acquired = False

        try:
            # Reserve GPU resources if tracker is available
            if self.gpu_tracker and self.system_capability:
                # Get VRAM requirements based on system capability tier
                tier_info = self.system_capability.get("tier_info", {})
                vram_requirements = tier_info.get("vram_requirements", {})

                if not vram_requirements:
                    logger.warning(
                        f"Job {job.job_id}: No VRAM requirements found in tier info. "
                        f"Using fallback default."
                    )
                    # Fallback: assume 14GB per GPU (Tier 1 estimate)
                    gpu_count = self.system_capability.get("gpu_count", 2)
                    vram_requirements = {gpu_id: 14.0 for gpu_id in range(gpu_count)}

                tier = self.system_capability.get("max_tier", 1)
                logger.info(
                    f"Job {job.job_id} requesting VRAM for Tier {tier}: {vram_requirements}"
                )

                # Try to acquire VRAM with retry (wait for resources to become available)
                max_wait_seconds = 600  # 10 minutes max wait
                retry_interval = 5  # Check every 5 seconds
                waited = 0

                while waited < max_wait_seconds:
                    vram_acquired = self.gpu_tracker.acquire(vram_requirements, job.job_id)

                    if vram_acquired:
                        logger.info(
                            f"Job {job.job_id} acquired VRAM successfully at Tier {tier} "
                            f"(waited {waited}s)"
                        )
                        break

                    if waited == 0:
                        logger.info(
                            f"Job {job.job_id} waiting for VRAM (Tier {tier}). "
                            f"GPU status: {self.gpu_tracker.get_status()}"
                        )

                    time.sleep(retry_interval)
                    waited += retry_interval

                    # Check for cancellation while waiting
                    if job.cancel_requested:
                        logger.info(f"Job {job.job_id} cancelled while waiting for VRAM")
                        self.job_semaphore.release()
                        with self.job_lock:
                            job.status = JobStatus.CANCELLED
                            job.completed_at = datetime.utcnow()
                        return

                if not vram_acquired:
                    # Timeout after max wait
                    logger.error(
                        f"Job {job.job_id} timed out waiting for VRAM after {max_wait_seconds}s"
                    )
                    self.job_semaphore.release()
                    with self.job_lock:
                        job.status = JobStatus.FAILED
                        job.completed_at = datetime.utcnow()
                        job.error = f"Timed out waiting for GPU resources ({max_wait_seconds}s)"
                    return

            logger.info(f"Job {job.job_id} starting processing...")
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
                progress_callback=progress_callback
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

            logger.info(f"Job completed successfully: {job.job_id}")

        except Exception as e:
            logger.error(f"Job processing failed: {job.job_id}: {e}", exc_info=True)

            # Update job status to failed
            with self.job_lock:
                job.status = JobStatus.FAILED
                job.completed_at = datetime.utcnow()
                job.error = str(e)

        finally:
            # Release GPU resources if acquired
            if vram_acquired and self.gpu_tracker:
                self.gpu_tracker.release(job.job_id)
                logger.info(f"Job {job.job_id} released VRAM")

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

        return {
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
        with self.job_lock:
            if job_id in self.jobs:
                job = self.jobs[job_id]
                job.progress_pct = progress_pct
                job.pages_completed = pages_completed
                job.current_stage = stage

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
