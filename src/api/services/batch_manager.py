"""Batch job lifecycle management service."""
import uuid
import threading
import logging
import asyncio
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional, Any

from ..models.batch import BatchJob, BatchJobStatus, BatchProgress

logger = logging.getLogger(__name__)


def _count_active_jobs_for_batch(batch_job_id: str, job_manager) -> int:
    """
    Count jobs currently in 'processing' state for this batch.

    PHASE 4: Database-only mode - queries database for active jobs.

    Args:
        batch_job_id: Batch job identifier
        job_manager: JobManager instance

    Returns:
        Number of jobs in 'processing' state
    """
    # PHASE 4: Database-only mode
    # For now, use thread count as a proxy for active jobs
    # TODO: Implement proper database query for active jobs by batch_id
    active_count = 0
    # Count processing threads that might belong to this batch
    # This is a conservative estimate until we implement proper DB queries
    active_count = len(job_manager.processing_threads)
    return active_count


def _run_async_in_thread(coro):
    """
    Safely run async coroutine from a thread.

    Creates a new event loop for the thread to avoid conflicts.

    Args:
        coro: Coroutine to run
    """
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


class BatchManager:
    """Manage batch job lifecycle and processing."""

    def __init__(
        self,
        processing_directory: str,
        output_directory: str,
        max_concurrent_batches: int = 1,
        batch_repository=None,
        event_loop=None
    ):
        """
        Initialize batch manager.

        Args:
            processing_directory: Directory for active processing
            output_directory: Directory for completed results
            max_concurrent_batches: Maximum concurrent batch jobs
            batch_repository: Optional BatchRepository for database writes (Phase 2)
            event_loop: Optional event loop for thread-safe async operations (Phase 2)
        """
        self.processing_directory = Path(processing_directory)
        self.output_directory = Path(output_directory)
        self.max_concurrent_batches = max_concurrent_batches

        self.processing_directory.mkdir(parents=True, exist_ok=True)
        self.output_directory.mkdir(parents=True, exist_ok=True)

        # In-memory batch registry
        self.batches: Dict[str, BatchJob] = {}
        self.batch_lock = threading.Lock()

        # Processing threads
        self.processing_threads: Dict[str, threading.Thread] = {}

        # Database integration (Phase 2)
        self.batch_repository = batch_repository
        self._event_loop = event_loop

        logger.info(f"BatchManager initialized: processing={processing_directory}, output={output_directory}")

    def create_batch_job(
        self,
        directory_id: str,
        file_ids: List[str],
        model: str,
        prompt_type: str,
        custom_prompts: Optional[Dict[str, str]],
        processing_options: Dict[str, Any],
        output_format: str
    ) -> BatchJob:
        """
        Create a new batch job for directory processing.

        Args:
            directory_id: Directory identifier
            file_ids: List of file IDs to process
            model: Model to use
            prompt_type: Prompt type
            custom_prompts: Optional custom prompts
            processing_options: Processing options
            output_format: Output format

        Returns:
            BatchJob object
        """
        batch_job_id = str(uuid.uuid4())

        with self.batch_lock:
            batch = BatchJob(
                batch_job_id=batch_job_id,
                directory_id=directory_id,
                file_ids=file_ids,
                document_jobs={},
                total_documents=len(file_ids),
                documents_completed=0,
                overall_progress_pct=0.0,
                status=BatchJobStatus.QUEUED,
                created_at=datetime.utcnow(),
                model=model,
                prompt_type=prompt_type,
                custom_prompts=custom_prompts,
                processing_options=processing_options,
                output_format=output_format
            )
            self.batches[batch_job_id] = batch

        logger.info(f"Batch job created: {batch_job_id} with {len(file_ids)} documents")

        # Write to database (Phase 2: dual-write)
        if self.batch_repository and self._event_loop:
            try:
                from uuid import UUID
                import asyncio

                # Use dev user for now (Phase 3+ will use real user)
                dev_user_id = "a0000000-0000-0000-0000-000000000001"

                future = asyncio.run_coroutine_threadsafe(
                    self.batch_repository.create_batch_job(
                        user_id=UUID(dev_user_id),
                        name=None,  # Could add name parameter to create_batch_job
                        total_documents=len(file_ids),
                        model=model,
                        prompt_type=prompt_type,
                        custom_prompts=custom_prompts,
                        processing_options=processing_options,
                        output_format=output_format
                    ),
                    self._event_loop
                )

                db_batch = future.result(timeout=5)
                logger.info(f"Batch {batch_job_id} written to database")

            except Exception as e:
                logger.error(f"Failed to write batch {batch_job_id} to database: {e}")

        return batch

    def start_batch_job(
        self,
        batch_job_id: str,
        file_manager,
        job_manager,
        prompt_manager,
        model_manager,
        progress_emitter
    ) -> None:
        """
        Start processing a batch job asynchronously.

        Args:
            batch_job_id: Batch job identifier
            file_manager: FileManager instance
            job_manager: JobManager instance
            prompt_manager: PromptManager instance
            model_manager: ModelManager instance
            progress_emitter: ProgressEmitter instance
        """
        batch = self.get_batch_job(batch_job_id)

        # Update status
        with self.batch_lock:
            batch.status = BatchJobStatus.PROCESSING
            batch.started_at = datetime.utcnow()

        # Create processing thread
        thread = threading.Thread(
            target=self._process_batch_concurrent,
            args=(batch, file_manager, job_manager, prompt_manager, model_manager, progress_emitter),
            daemon=True
        )

        self.processing_threads[batch_job_id] = thread
        thread.start()

        logger.info(f"Batch job processing started: {batch_job_id}")

    def _process_batch_concurrent(
        self,
        batch: BatchJob,
        file_manager,
        job_manager,
        prompt_manager,
        model_manager,
        progress_emitter
    ) -> None:
        """
        Process batch job concurrently (runs in background thread).

        INTERFACE FROZEN: IF-0-3.7B - Concurrent Batch Processing

        Concurrency:
        - Max concurrent jobs: job_manager.max_concurrent_jobs (default: 2)
        - Uses asyncio.gather() + Semaphore
        - Jobs processed in FIFO order (within concurrency limit)

        Progress Tracking:
        - Emits progress after each document completes
        - Progress = (completed_files / total_files) * 100
        - Thread-safe: Uses batch_lock for progress updates

        Error Handling:
        - Individual job failures don't stop batch
        - Failed jobs logged, batch continues
        - Batch status = FAILED if ALL jobs fail
        - Batch status = PARTIAL_SUCCESS if SOME jobs fail
        - Batch status = COMPLETED if all jobs succeed

        Cancellation:
        - Checks batch.cancel_requested before each job
        - Ongoing jobs finish, remaining jobs skipped
        - Batch status = CANCELLED

        Args:
            batch: BatchJob object
            file_manager: FileManager instance
            job_manager: JobManager instance
            prompt_manager: PromptManager instance
            model_manager: ModelManager instance
            progress_emitter: ProgressEmitter instance
        """
        try:
            logger.info(f"Starting concurrent batch processing: {batch.batch_job_id}")

            # Run concurrent processing using asyncio
            _run_async_in_thread(
                self._process_batch_concurrent_async(
                    batch,
                    file_manager,
                    job_manager,
                    prompt_manager,
                    model_manager,
                    progress_emitter
                )
            )

        except Exception as e:
            logger.error(f"Batch job processing failed: {batch.batch_job_id}: {e}", exc_info=True)

            # Update batch status to failed
            with self.batch_lock:
                batch.status = BatchJobStatus.FAILED
                batch.completed_at = datetime.utcnow()
                batch.error = str(e)

            # Update database (Phase 2: dual-write)
            if self.batch_repository and self._event_loop:
                try:
                    from uuid import UUID

                    future = asyncio.run_coroutine_threadsafe(
                        self.batch_repository.update_batch_status(
                            batch_job_id=UUID(batch.batch_job_id),
                            status="failed",
                            error_message=str(e),
                            completed_at=batch.completed_at
                        ),
                        self._event_loop
                    )
                    future.result(timeout=5)

                except Exception as db_error:
                    logger.error(f"Failed to update batch {batch.batch_job_id} failure: {db_error}")

            # Emit error
            _run_async_in_thread(
                progress_emitter.emit_error(
                    job_id=batch.batch_job_id,
                    error_message=str(e),
                    is_batch=True,
                    batch_job_id=batch.batch_job_id
                )
            )

        finally:
            # Cleanup thread reference
            with self.batch_lock:
                if batch.batch_job_id in self.processing_threads:
                    del self.processing_threads[batch.batch_job_id]

    async def _process_batch_concurrent_async(
        self,
        batch: BatchJob,
        file_manager,
        job_manager,
        prompt_manager,
        model_manager,
        progress_emitter
    ) -> None:
        """
        Async implementation of concurrent batch processing.

        This runs in its own event loop created by _run_async_in_thread.
        Uses asyncio.gather() and Semaphore for concurrent job processing.

        Args:
            batch: BatchJob object
            file_manager: FileManager instance
            job_manager: JobManager instance
            prompt_manager: PromptManager instance
            model_manager: ModelManager instance
            progress_emitter: ProgressEmitter instance
        """
        # Get concurrency limit from job_manager
        max_concurrent = job_manager.max_concurrent_jobs
        semaphore = asyncio.Semaphore(max_concurrent)

        logger.info(f"Batch {batch.batch_job_id}: Processing {len(batch.file_ids)} documents with concurrency={max_concurrent}")

        # Track results for status determination
        job_results = []
        documents_completed_count = 0

        async def process_one_document(file_id: str, idx: int) -> Dict[str, Any]:
            """Process a single document with semaphore-controlled concurrency."""
            nonlocal documents_completed_count

            async with semaphore:
                # Check cancellation before starting
                if batch.cancel_requested:
                    logger.info(f"Batch {batch.batch_job_id}: Document {idx + 1} skipped (cancelled)")
                    return {"status": "cancelled", "file_id": file_id, "idx": idx}

                try:
                    # Get file info
                    file_info = file_manager.get_file_info(file_id)
                    logger.info(f"Batch {batch.batch_job_id}: Starting document {idx + 1}/{batch.total_documents}: {file_info.filename}")

                    # Create individual job for this document
                    if job_manager._event_loop:
                        future = asyncio.run_coroutine_threadsafe(
                            job_manager.create_job(
                                file_id=file_id,
                                filename=file_info.filename,
                                model=batch.model,
                                prompt_type=batch.prompt_type,
                                custom_prompts=batch.custom_prompts,
                                processing_options=batch.processing_options,
                                output_format=batch.output_format,
                                estimated_pages=file_info.page_count
                            ),
                            job_manager._event_loop
                        )
                        job = future.result(timeout=10)
                    else:
                        raise RuntimeError("Event loop not available for batch job creation")

                    # Set parent batch ID for tracking (Phase 3.7B)
                    job.parent_batch_id = batch.batch_job_id

                    # Add job to batch's document jobs (thread-safe)
                    with self.batch_lock:
                        batch.document_jobs[job.job_id] = job

                    # Set up progress callback for this job
                    def progress_callback(progress_pct: float, pages_completed: int, stage: str):
                        """Progress callback for individual document processing."""
                        # Update job progress
                        job_manager.update_job_progress(job.job_id, progress_pct, pages_completed, stage)

                        # Emit document progress
                        _run_async_in_thread(
                            progress_emitter.emit_document_progress(
                                batch_job_id=batch.batch_job_id,
                                job_id=job.job_id,
                                filename=file_info.filename,
                                progress_pct=progress_pct,
                                current_page=pages_completed,
                                total_pages=file_info.page_count or 1,
                                stage=stage
                            )
                        )

                        # Calculate and emit batch progress (thread-safe)
                        with self.batch_lock:
                            batch_progress_pct = ((documents_completed_count + (progress_pct / 100.0)) / batch.total_documents) * 100.0
                            batch.overall_progress_pct = batch_progress_pct

                        # Update database progress (Phase 2: dual-write)
                        if self.batch_repository and self._event_loop:
                            try:
                                from uuid import UUID

                                future_db = asyncio.run_coroutine_threadsafe(
                                    self.batch_repository.update_batch_progress(
                                        batch_job_id=UUID(batch.batch_job_id),
                                        documents_completed=documents_completed_count,
                                        overall_progress_pct=batch_progress_pct
                                    ),
                                    self._event_loop
                                )
                                future_db.result(timeout=5)

                            except Exception as e:
                                logger.error(f"Failed to update batch {batch.batch_job_id} progress: {e}")

                        current_doc_progress = {
                            "job_id": job.job_id,
                            "filename": file_info.filename,
                            "progress_pct": progress_pct,
                            "current_page": pages_completed,
                            "total_pages": file_info.page_count or 1,
                            "stage": stage
                        }

                        # Count active jobs for this batch (Phase 3.7B: IF-1-3.7B)
                        active_files_count = _count_active_jobs_for_batch(batch.batch_job_id, job_manager)

                        # Calculate failed files (total - completed - active)
                        failed_files_count = max(0, batch.total_documents - documents_completed_count - active_files_count)

                        _run_async_in_thread(
                            progress_emitter.emit_batch_progress(
                                batch_job_id=batch.batch_job_id,
                                overall_progress_pct=batch_progress_pct,
                                documents_completed=documents_completed_count,
                                total_documents=batch.total_documents,
                                current_document_id=job.job_id,
                                current_document_progress=current_doc_progress,
                                active_files=active_files_count,
                                failed_files=failed_files_count
                            )
                        )

                    # Set progress callback in job manager
                    job_manager.set_progress_callback(job.job_id, progress_callback)

                    # Start processing this document
                    job_manager.start_job(
                        job_id=job.job_id,
                        file_manager=file_manager,
                        prompt_manager=prompt_manager,
                        model_manager=model_manager
                    )

                    # Wait for document to complete (async polling)
                    while True:
                        job = await job_manager.get_job(job.job_id)
                        if job.status.value in ['completed', 'failed', 'cancelled']:
                            break
                        await asyncio.sleep(1)  # Async sleep instead of blocking

                    # Update batch completion count (thread-safe)
                    job_status = job.status.value
                    with self.batch_lock:
                        if job_status == 'completed':
                            batch.documents_completed += 1
                            documents_completed_count += 1
                        elif job_status == 'failed':
                            logger.error(f"Document failed in batch: {file_info.filename}: {job.error}")

                    logger.info(f"Batch {batch.batch_job_id}: Document completed: {file_info.filename} ({documents_completed_count}/{batch.total_documents})")

                    return {
                        "status": job_status,
                        "file_id": file_id,
                        "idx": idx,
                        "filename": file_info.filename
                    }

                except Exception as e:
                    logger.error(f"Batch {batch.batch_job_id}: Error processing document {idx + 1} (file_id={file_id}): {e}", exc_info=True)
                    return {
                        "status": "failed",
                        "file_id": file_id,
                        "idx": idx,
                        "error": str(e)
                    }

        # Create tasks for all documents (FIFO order maintained by enumerate)
        tasks = [
            process_one_document(file_id, idx)
            for idx, file_id in enumerate(batch.file_ids)
        ]

        # Execute all tasks concurrently with return_exceptions=True
        # This ensures one failure doesn't stop the batch
        job_results = await asyncio.gather(*tasks, return_exceptions=True)

        # Check for cancellation
        if batch.cancel_requested:
            with self.batch_lock:
                batch.status = BatchJobStatus.CANCELLED
                batch.completed_at = datetime.utcnow()
            logger.info(f"Batch job cancelled: {batch.batch_job_id}")
            return

        # Analyze results to determine final batch status
        completed_count = sum(1 for r in job_results if isinstance(r, dict) and r.get("status") == "completed")
        failed_count = sum(1 for r in job_results if isinstance(r, dict) and r.get("status") == "failed")
        exception_count = sum(1 for r in job_results if isinstance(r, Exception))

        total_failed = failed_count + exception_count

        # Determine final batch status
        with self.batch_lock:
            if completed_count == len(batch.file_ids):
                # All succeeded
                batch.status = BatchJobStatus.COMPLETED
            elif completed_count == 0:
                # All failed
                batch.status = BatchJobStatus.FAILED
                batch.error = f"{total_failed} of {len(batch.file_ids)} documents failed"
            else:
                # Partial success - some succeeded, some failed
                # Use COMPLETED status but log the partial success
                batch.status = BatchJobStatus.COMPLETED
                logger.warning(
                    f"Batch {batch.batch_job_id} completed with partial success: "
                    f"{completed_count} succeeded, {total_failed} failed"
                )

            batch.completed_at = datetime.utcnow()
            batch.overall_progress_pct = 100.0

        # Update database (Phase 2: dual-write)
        if self.batch_repository and self._event_loop:
            try:
                from uuid import UUID

                future = asyncio.run_coroutine_threadsafe(
                    self.batch_repository.update_batch_status(
                        batch_job_id=UUID(batch.batch_job_id),
                        status=batch.status.value,
                        completed_at=batch.completed_at
                    ),
                    self._event_loop
                )
                future.result(timeout=5)

            except Exception as e:
                logger.error(f"Failed to update batch {batch.batch_job_id} status in database: {e}")

        # Emit completion event
        processing_time = 0.0
        if batch.started_at and batch.completed_at:
            processing_time = (batch.completed_at - batch.started_at).total_seconds()

        batch_stats = {
            "total_documents": batch.total_documents,
            "documents_completed": batch.documents_completed,
            "documents_failed": batch.total_documents - batch.documents_completed,
            "overall_processing_time_seconds": processing_time
        }

        _run_async_in_thread(
            progress_emitter.emit_completion(
                job_id=batch.batch_job_id,
                is_batch=True,
                batch_stats=batch_stats
            )
        )

        logger.info(f"Batch job completed: {batch.batch_job_id} (status={batch.status.value})")

    def get_batch_job(self, batch_job_id: str) -> BatchJob:
        """
        Get batch job by ID.

        Args:
            batch_job_id: Batch job identifier

        Returns:
            BatchJob object

        Raises:
            ValueError: If batch job not found
        """
        with self.batch_lock:
            if batch_job_id not in self.batches:
                raise ValueError(f"Batch job not found: {batch_job_id}")
            return self.batches[batch_job_id]

    def cancel_batch_job(self, batch_job_id: str) -> bool:
        """
        Cancel a running batch job.

        Args:
            batch_job_id: Batch job identifier

        Returns:
            True if cancelled successfully

        Raises:
            ValueError: If batch job not found or already completed
        """
        batch = self.get_batch_job(batch_job_id)

        if batch.status == BatchJobStatus.COMPLETED:
            raise ValueError("Cannot cancel completed batch job")

        if batch.status == BatchJobStatus.FAILED:
            raise ValueError("Cannot cancel failed batch job")

        if batch.status == BatchJobStatus.CANCELLED:
            return True  # Already cancelled

        # Set cancellation flag
        with self.batch_lock:
            batch.cancel_requested = True

        # Wait for thread to finish (with timeout)
        if batch_job_id in self.processing_threads:
            thread = self.processing_threads[batch_job_id]
            thread.join(timeout=10)

            if thread.is_alive():
                logger.warning(f"Batch job thread did not terminate cleanly: {batch_job_id}")

        # Update status if not already updated by thread
        with self.batch_lock:
            if batch.status != BatchJobStatus.CANCELLED:
                batch.status = BatchJobStatus.CANCELLED
                batch.completed_at = datetime.utcnow()

        logger.info(f"Batch job cancelled: {batch_job_id}")
        return True

    def get_batch_result(self, batch_job_id: str) -> Dict[str, Any]:
        """
        Get batch job results (all document results).

        Args:
            batch_job_id: Batch job identifier

        Returns:
            Result dict with all document results

        Raises:
            ValueError: If batch job not found or not completed
        """
        batch = self.get_batch_job(batch_job_id)

        if batch.status != BatchJobStatus.COMPLETED:
            raise ValueError(f"Batch job not completed: {batch.status.value}")

        # Collect results from all document jobs
        results = []
        for job_id, job in batch.document_jobs.items():
            if job.status.value == 'completed' and job.result_path and job.result_path.exists():
                # Read result file
                with open(job.result_path, 'r', encoding='utf-8') as f:
                    content = f.read()

                results.append({
                    "job_id": job_id,
                    "filename": job.filename,
                    "format": job.output_format,
                    "content": content,
                    "total_pages": job.total_pages,
                    "status": "completed"
                })
            elif job.status.value == 'failed':
                results.append({
                    "job_id": job_id,
                    "filename": job.filename,
                    "status": "failed",
                    "error": job.error
                })

        # Calculate processing time
        processing_time = 0.0
        if batch.started_at and batch.completed_at:
            processing_time = (batch.completed_at - batch.started_at).total_seconds()

        return {
            "batch_job_id": batch_job_id,
            "total_documents": batch.total_documents,
            "documents_completed": batch.documents_completed,
            "results": results,
            "overall_processing_time_seconds": processing_time
        }

    def cleanup_old_batches(self, max_batches: int) -> int:
        """
        Clean up old completed/failed batch jobs.

        Args:
            max_batches: Maximum number of batch jobs to keep

        Returns:
            Number of batches cleaned up
        """
        with self.batch_lock:
            # Sort batches by creation time
            sorted_batches = sorted(
                self.batches.values(),
                key=lambda b: b.created_at,
                reverse=True
            )

            # Keep only completed/failed batches beyond max
            batches_to_remove = []
            for batch in sorted_batches[max_batches:]:
                if batch.status in [BatchJobStatus.COMPLETED, BatchJobStatus.FAILED, BatchJobStatus.CANCELLED]:
                    batches_to_remove.append(batch.batch_job_id)

            # Remove batches
            for batch_id in batches_to_remove:
                del self.batches[batch_id]

            if batches_to_remove:
                logger.info(f"Cleaned up {len(batches_to_remove)} old batch jobs")

            return len(batches_to_remove)
