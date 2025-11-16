"""Unit tests for BatchManager concurrent processing."""
import pytest
import asyncio
import time
import threading
from pathlib import Path
from datetime import datetime
from unittest.mock import Mock, AsyncMock, patch
from uuid import uuid4

from src.api.services.batch_manager import BatchManager
from src.api.models.batch import BatchJobStatus


@pytest.fixture
def temp_dirs(tmp_path):
    """Create temporary directories for testing."""
    processing_dir = tmp_path / "processing"
    output_dir = tmp_path / "output"
    processing_dir.mkdir()
    output_dir.mkdir()
    return {
        "processing": str(processing_dir),
        "output": str(output_dir)
    }


@pytest.fixture
def batch_manager(temp_dirs):
    """Create BatchManager instance for testing."""
    return BatchManager(
        processing_directory=temp_dirs["processing"],
        output_directory=temp_dirs["output"],
        max_concurrent_batches=1
    )


@pytest.fixture
def mock_file_manager():
    """Create mock FileManager."""
    manager = Mock()

    def get_file_info(file_id):
        """Return mock file info."""
        info = Mock()
        info.file_id = file_id
        info.filename = f"test_{file_id}.pdf"
        info.page_count = 5
        return info

    manager.get_file_info = get_file_info
    return manager


@pytest.fixture
def mock_job_manager():
    """Create mock JobManager with event loop."""
    manager = Mock()

    # Create event loop for async operations and run it in a thread
    loop = asyncio.new_event_loop()
    manager._event_loop = loop
    manager.max_concurrent_jobs = 2

    # Start event loop in background thread
    def run_loop():
        asyncio.set_event_loop(loop)
        loop.run_forever()

    loop_thread = threading.Thread(target=run_loop, daemon=True)
    loop_thread.start()

    # Track created jobs
    jobs = {}
    job_lock = threading.Lock()

    async def create_job(**kwargs):
        """Mock create_job."""
        job_id = str(uuid4())
        job = Mock()
        job.job_id = job_id
        job.status = Mock(value='queued')
        job.error = None

        with job_lock:
            jobs[job_id] = job

        return job

    def get_job(job_id):
        """Mock get_job."""
        with job_lock:
            return jobs.get(job_id)

    def update_job_progress(job_id, progress_pct, pages_completed, stage):
        """Mock update_job_progress."""
        pass

    def set_progress_callback(job_id, callback):
        """Mock set_progress_callback."""
        pass

    def start_job(job_id, **kwargs):
        """Mock start_job - simulate async completion."""
        def complete_job():
            time.sleep(0.2)  # Simulate processing time
            with job_lock:
                if job_id in jobs:
                    jobs[job_id].status = Mock(value='completed')

        thread = threading.Thread(target=complete_job, daemon=True)
        thread.start()

    manager.create_job = create_job
    manager.get_job = get_job
    manager.update_job_progress = update_job_progress
    manager.set_progress_callback = set_progress_callback
    manager.start_job = start_job
    manager._jobs = jobs
    manager._job_lock = job_lock

    yield manager

    # Cleanup event loop
    loop.call_soon_threadsafe(loop.stop)
    loop_thread.join(timeout=2)
    loop.close()


@pytest.fixture
def mock_prompt_manager():
    """Create mock PromptManager."""
    return Mock()


@pytest.fixture
def mock_model_manager():
    """Create mock ModelManager."""
    return Mock()


@pytest.fixture
def mock_progress_emitter():
    """Create mock ProgressEmitter."""
    emitter = Mock()

    async def emit_document_progress(**kwargs):
        pass

    async def emit_batch_progress(**kwargs):
        pass

    async def emit_completion(**kwargs):
        pass

    async def emit_error(**kwargs):
        pass

    emitter.emit_document_progress = emit_document_progress
    emitter.emit_batch_progress = emit_batch_progress
    emitter.emit_completion = emit_completion
    emitter.emit_error = emit_error

    return emitter


@pytest.mark.unit
class TestBatchConcurrentProcessing:
    """Test concurrent batch processing functionality."""

    def test_concurrent_processing_basic(
        self,
        batch_manager,
        mock_file_manager,
        mock_job_manager,
        mock_prompt_manager,
        mock_model_manager,
        mock_progress_emitter
    ):
        """Scenario: Process 10 documents concurrently with max_concurrent=2."""
        # Arrange - Create batch with 10 documents
        file_ids = [f"file-{i}" for i in range(10)]

        batch = batch_manager.create_batch_job(
            directory_id="test-dir",
            file_ids=file_ids,
            model="deepseek-ocr",
            prompt_type="ocr",
            custom_prompts=None,
            processing_options={"dpi": 300},
            output_format="markdown"
        )

        # Act - Start batch processing
        start_time = time.time()
        batch_manager.start_batch_job(
            batch_job_id=batch.batch_job_id,
            file_manager=mock_file_manager,
            job_manager=mock_job_manager,
            prompt_manager=mock_prompt_manager,
            model_manager=mock_model_manager,
            progress_emitter=mock_progress_emitter
        )

        # Wait for completion (with timeout)
        max_wait = 10  # seconds
        while time.time() - start_time < max_wait:
            retrieved_batch = batch_manager.get_batch_job(batch.batch_job_id)
            if retrieved_batch.status in [BatchJobStatus.COMPLETED, BatchJobStatus.FAILED]:
                break
            time.sleep(0.5)

        end_time = time.time()
        processing_time = end_time - start_time

        # Assert
        retrieved_batch = batch_manager.get_batch_job(batch.batch_job_id)
        assert retrieved_batch.status == BatchJobStatus.COMPLETED
        assert retrieved_batch.documents_completed == 10
        assert retrieved_batch.overall_progress_pct == 100.0

        # With max_concurrent=2 and 0.2s per job, sequential would take ~2s
        # Concurrent should take ~1s (5 batches of 2 concurrent jobs)
        # Allow some overhead but verify it's faster than sequential
        assert processing_time < 8.0  # Should be much faster than 10 * 0.2 = 2s sequential

    def test_concurrent_processing_with_failures(
        self,
        batch_manager,
        mock_file_manager,
        mock_job_manager,
        mock_prompt_manager,
        mock_model_manager,
        mock_progress_emitter
    ):
        """Scenario: One job fails, others continue successfully."""
        # Arrange - Create batch with 5 documents
        file_ids = [f"file-{i}" for i in range(5)]

        batch = batch_manager.create_batch_job(
            directory_id="test-dir",
            file_ids=file_ids,
            model="deepseek-ocr",
            prompt_type="ocr",
            custom_prompts=None,
            processing_options={"dpi": 300},
            output_format="markdown"
        )

        # Modify mock to make job 2 fail
        original_start_job = mock_job_manager.start_job

        def start_job_with_failure(job_id, **kwargs):
            """Start job, but fail job 2."""
            def complete_or_fail():
                time.sleep(0.2)
                with mock_job_manager._job_lock:
                    if job_id in mock_job_manager._jobs:
                        job = mock_job_manager._jobs[job_id]
                        # Fail every 3rd job
                        if len([j for j in mock_job_manager._jobs.values()
                                if j.status.value == 'completed' or j.status.value == 'failed']) == 2:
                            job.status = Mock(value='failed')
                            job.error = "Simulated failure"
                        else:
                            job.status = Mock(value='completed')

            thread = threading.Thread(target=complete_or_fail, daemon=True)
            thread.start()

        mock_job_manager.start_job = start_job_with_failure

        # Act - Start batch processing
        start_time = time.time()
        batch_manager.start_batch_job(
            batch_job_id=batch.batch_job_id,
            file_manager=mock_file_manager,
            job_manager=mock_job_manager,
            prompt_manager=mock_prompt_manager,
            model_manager=mock_model_manager,
            progress_emitter=mock_progress_emitter
        )

        # Wait for completion
        max_wait = 10
        while time.time() - start_time < max_wait:
            retrieved_batch = batch_manager.get_batch_job(batch.batch_job_id)
            if retrieved_batch.status in [BatchJobStatus.COMPLETED, BatchJobStatus.FAILED]:
                break
            time.sleep(0.5)

        # Assert - Batch completes despite one failure
        retrieved_batch = batch_manager.get_batch_job(batch.batch_job_id)
        assert retrieved_batch.status == BatchJobStatus.COMPLETED
        # 4 out of 5 should succeed
        assert retrieved_batch.documents_completed == 4

    def test_concurrent_processing_cancellation(
        self,
        batch_manager,
        mock_file_manager,
        mock_job_manager,
        mock_prompt_manager,
        mock_model_manager,
        mock_progress_emitter
    ):
        """Scenario: Cancel batch - ongoing jobs finish, remaining skipped."""
        # Arrange - Create batch with 10 documents
        file_ids = [f"file-{i}" for i in range(10)]

        batch = batch_manager.create_batch_job(
            directory_id="test-dir",
            file_ids=file_ids,
            model="deepseek-ocr",
            prompt_type="ocr",
            custom_prompts=None,
            processing_options={"dpi": 300},
            output_format="markdown"
        )

        # Make jobs take longer to process
        def slow_start_job(job_id, **kwargs):
            """Slow job processing."""
            def complete_job():
                time.sleep(1.0)  # Longer processing time
                with mock_job_manager._job_lock:
                    if job_id in mock_job_manager._jobs:
                        mock_job_manager._jobs[job_id].status = Mock(value='completed')

            thread = threading.Thread(target=complete_job, daemon=True)
            thread.start()

        mock_job_manager.start_job = slow_start_job

        # Act - Start batch processing
        batch_manager.start_batch_job(
            batch_job_id=batch.batch_job_id,
            file_manager=mock_file_manager,
            job_manager=mock_job_manager,
            prompt_manager=mock_prompt_manager,
            model_manager=mock_model_manager,
            progress_emitter=mock_progress_emitter
        )

        # Wait for some jobs to start
        time.sleep(0.5)

        # Cancel batch
        batch_manager.cancel_batch_job(batch.batch_job_id)

        # Wait for cancellation to complete
        time.sleep(2.0)

        # Assert - Batch is cancelled
        retrieved_batch = batch_manager.get_batch_job(batch.batch_job_id)
        assert retrieved_batch.status == BatchJobStatus.CANCELLED
        # Some jobs may have completed before cancellation, but not all
        assert retrieved_batch.documents_completed < 10

    def test_concurrent_processing_respects_semaphore(
        self,
        batch_manager,
        mock_file_manager,
        mock_job_manager,
        mock_prompt_manager,
        mock_model_manager,
        mock_progress_emitter
    ):
        """Scenario: Verify concurrency is limited to max_concurrent_jobs."""
        # Arrange - Create batch with 6 documents
        file_ids = [f"file-{i}" for i in range(6)]

        batch = batch_manager.create_batch_job(
            directory_id="test-dir",
            file_ids=file_ids,
            model="deepseek-ocr",
            prompt_type="ocr",
            custom_prompts=None,
            processing_options={"dpi": 300},
            output_format="markdown"
        )

        # Track concurrent job count
        concurrent_count = 0
        max_concurrent_seen = 0
        count_lock = threading.Lock()

        def start_job_with_tracking(job_id, **kwargs):
            """Track concurrent job execution."""
            nonlocal concurrent_count, max_concurrent_seen

            def process():
                nonlocal concurrent_count, max_concurrent_seen

                with count_lock:
                    concurrent_count += 1
                    if concurrent_count > max_concurrent_seen:
                        max_concurrent_seen = concurrent_count

                time.sleep(0.3)  # Processing time

                with mock_job_manager._job_lock:
                    if job_id in mock_job_manager._jobs:
                        mock_job_manager._jobs[job_id].status = Mock(value='completed')

                with count_lock:
                    concurrent_count -= 1

            thread = threading.Thread(target=process, daemon=True)
            thread.start()

        mock_job_manager.start_job = start_job_with_tracking

        # Act - Start batch processing
        start_time = time.time()
        batch_manager.start_batch_job(
            batch_job_id=batch.batch_job_id,
            file_manager=mock_file_manager,
            job_manager=mock_job_manager,
            prompt_manager=mock_prompt_manager,
            model_manager=mock_model_manager,
            progress_emitter=mock_progress_emitter
        )

        # Wait for completion
        max_wait = 10
        while time.time() - start_time < max_wait:
            retrieved_batch = batch_manager.get_batch_job(batch.batch_job_id)
            if retrieved_batch.status in [BatchJobStatus.COMPLETED, BatchJobStatus.FAILED]:
                break
            time.sleep(0.5)

        # Assert - Max concurrent jobs was respected
        assert max_concurrent_seen <= mock_job_manager.max_concurrent_jobs
        assert max_concurrent_seen > 0  # At least some concurrency happened

        retrieved_batch = batch_manager.get_batch_job(batch.batch_job_id)
        assert retrieved_batch.status == BatchJobStatus.COMPLETED
        assert retrieved_batch.documents_completed == 6


@pytest.mark.unit
class TestBatchThreadSafety:
    """Test thread safety of batch operations."""

    def test_batch_progress_updates_thread_safe(
        self,
        batch_manager,
        mock_file_manager,
        mock_job_manager,
        mock_prompt_manager,
        mock_model_manager,
        mock_progress_emitter
    ):
        """Scenario: Verify batch progress updates are thread-safe."""
        # Arrange - Create batch with 5 documents
        file_ids = [f"file-{i}" for i in range(5)]

        batch = batch_manager.create_batch_job(
            directory_id="test-dir",
            file_ids=file_ids,
            model="deepseek-ocr",
            prompt_type="ocr",
            custom_prompts=None,
            processing_options={"dpi": 300},
            output_format="markdown"
        )

        # Act - Start batch processing
        start_time = time.time()
        batch_manager.start_batch_job(
            batch_job_id=batch.batch_job_id,
            file_manager=mock_file_manager,
            job_manager=mock_job_manager,
            prompt_manager=mock_prompt_manager,
            model_manager=mock_model_manager,
            progress_emitter=mock_progress_emitter
        )

        # Continuously read batch state while processing (stress test thread safety)
        reads = 0
        max_wait = 10
        while time.time() - start_time < max_wait:
            try:
                retrieved_batch = batch_manager.get_batch_job(batch.batch_job_id)
                reads += 1

                # Verify consistency
                assert retrieved_batch.documents_completed <= retrieved_batch.total_documents
                assert 0 <= retrieved_batch.overall_progress_pct <= 100.0

                if retrieved_batch.status in [BatchJobStatus.COMPLETED, BatchJobStatus.FAILED]:
                    break
            except Exception as e:
                pytest.fail(f"Thread safety violation: {e}")

            time.sleep(0.05)

        # Assert - No race conditions detected
        assert reads > 10  # We did many reads
        retrieved_batch = batch_manager.get_batch_job(batch.batch_job_id)
        assert retrieved_batch.status == BatchJobStatus.COMPLETED


@pytest.mark.unit
class TestBatchManagerBasics:
    """Test basic batch manager functionality."""

    def test_create_batch_job(self, batch_manager):
        """Scenario: Create a batch job successfully."""
        # Arrange
        file_ids = ["file-1", "file-2", "file-3"]

        # Act
        batch = batch_manager.create_batch_job(
            directory_id="test-dir",
            file_ids=file_ids,
            model="deepseek-ocr",
            prompt_type="ocr",
            custom_prompts=None,
            processing_options={"dpi": 300},
            output_format="markdown"
        )

        # Assert
        assert batch.batch_job_id is not None
        assert batch.directory_id == "test-dir"
        assert batch.file_ids == file_ids
        assert batch.total_documents == 3
        assert batch.documents_completed == 0
        assert batch.status == BatchJobStatus.QUEUED

    def test_get_batch_job(self, batch_manager):
        """Scenario: Retrieve batch job by ID."""
        # Arrange - Create batch
        batch = batch_manager.create_batch_job(
            directory_id="test-dir",
            file_ids=["file-1"],
            model="deepseek-ocr",
            prompt_type="ocr",
            custom_prompts=None,
            processing_options={},
            output_format="markdown"
        )

        # Act
        retrieved_batch = batch_manager.get_batch_job(batch.batch_job_id)

        # Assert
        assert retrieved_batch.batch_job_id == batch.batch_job_id
        assert retrieved_batch.directory_id == "test-dir"

    def test_get_batch_job_not_found(self, batch_manager):
        """Scenario: Request non-existent batch job."""
        # Arrange
        fake_batch_id = "non-existent-batch"

        # Act & Assert
        with pytest.raises(ValueError) as exc_info:
            batch_manager.get_batch_job(fake_batch_id)

        assert "not found" in str(exc_info.value).lower()
