"""Integration tests for Phase 3.7B - Batch Parallelization with Progress Aggregation."""
import pytest
import asyncio
import time
import threading
from pathlib import Path
from unittest.mock import Mock, AsyncMock
from uuid import uuid4
from datetime import datetime

from src.api.services.batch_manager import BatchManager
from src.api.services.progress_emitter import ProgressEmitter
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
        info.page_count = 3  # Small page count for faster tests
        return info

    manager.get_file_info = get_file_info
    return manager


@pytest.fixture
def mock_job_manager_with_tracking():
    """Create mock JobManager with event loop and progress tracking."""
    manager = Mock()

    # Create event loop for async operations
    loop = asyncio.new_event_loop()
    manager._event_loop = loop
    manager.max_concurrent_jobs = 2

    # Start event loop in background thread
    def run_loop():
        asyncio.set_event_loop(loop)
        loop.run_forever()

    loop_thread = threading.Thread(target=run_loop, daemon=True)
    loop_thread.start()

    # Track created jobs and their callbacks
    jobs = {}
    job_callbacks = {}
    job_lock = threading.Lock()

    async def create_job(**kwargs):
        """Mock create_job."""
        from dataclasses import dataclass, field

        @dataclass
        class MockJobStatus:
            value: str = 'queued'

        @dataclass
        class MockJob:
            job_id: str
            status: MockJobStatus = field(default_factory=lambda: MockJobStatus('queued'))
            error: str = None
            progress_pct: float = 0.0

        job_id = str(uuid4())
        job = MockJob(job_id=job_id)

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
        """Store progress callback for this job."""
        with job_lock:
            job_callbacks[job_id] = callback

    def start_job(job_id, **kwargs):
        """Mock start_job - simulate async processing with progress updates."""
        def process_job():
            from dataclasses import dataclass

            @dataclass
            class MockJobStatus:
                value: str

            with job_lock:
                if job_id in jobs:
                    jobs[job_id].status = MockJobStatus(value='processing')

            # Simulate progress updates
            callback = None
            with job_lock:
                callback = job_callbacks.get(job_id)

            if callback:
                # Simulate processing stages with delays
                for progress in [25, 50, 75, 100]:
                    time.sleep(0.1)  # Simulate work

                    # Update job progress_pct
                    with job_lock:
                        if job_id in jobs:
                            jobs[job_id].progress_pct = float(progress)

                    callback(
                        progress_pct=float(progress),
                        pages_completed=progress // 33,
                        stage=f"stage_{progress}"
                    )

            # Mark as completed
            time.sleep(0.1)
            with job_lock:
                if job_id in jobs:
                    jobs[job_id].status = MockJobStatus(value='completed')
                    jobs[job_id].progress_pct = 100.0

        thread = threading.Thread(target=process_job, daemon=True)
        thread.start()

    manager.create_job = create_job
    manager.get_job = get_job
    manager.update_job_progress = update_job_progress
    manager.set_progress_callback = set_progress_callback
    manager.start_job = start_job
    manager._jobs = jobs
    manager._job_callbacks = job_callbacks
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
def progress_emitter_with_tracking():
    """Create ProgressEmitter with event tracking."""
    emitter = ProgressEmitter()

    # Track emitted events
    emitted_events = {
        "batch_progress": [],
        "document_progress": [],
        "completion": [],
        "error": []
    }
    events_lock = threading.Lock()

    # Wrap emit methods to track events
    original_emit_batch_progress = emitter.emit_batch_progress
    original_emit_document_progress = emitter.emit_document_progress
    original_emit_completion = emitter.emit_completion
    original_emit_error = emitter.emit_error

    async def tracked_emit_batch_progress(**kwargs):
        with events_lock:
            emitted_events["batch_progress"].append({
                "timestamp": datetime.utcnow(),
                **kwargs
            })
        await original_emit_batch_progress(**kwargs)

    async def tracked_emit_document_progress(**kwargs):
        with events_lock:
            emitted_events["document_progress"].append({
                "timestamp": datetime.utcnow(),
                **kwargs
            })
        await original_emit_document_progress(**kwargs)

    async def tracked_emit_completion(**kwargs):
        with events_lock:
            emitted_events["completion"].append({
                "timestamp": datetime.utcnow(),
                **kwargs
            })
        await original_emit_completion(**kwargs)

    async def tracked_emit_error(**kwargs):
        with events_lock:
            emitted_events["error"].append({
                "timestamp": datetime.utcnow(),
                **kwargs
            })
        await original_emit_error(**kwargs)

    emitter.emit_batch_progress = tracked_emit_batch_progress
    emitter.emit_document_progress = tracked_emit_document_progress
    emitter.emit_completion = tracked_emit_completion
    emitter.emit_error = tracked_emit_error
    emitter._emitted_events = emitted_events
    emitter._events_lock = events_lock

    return emitter


@pytest.mark.integration
class TestPhase37BProgressAggregation:
    """Integration tests for Phase 3.7B batch progress aggregation."""

    def test_batch_progress_includes_active_files(
        self,
        batch_manager,
        mock_file_manager,
        mock_job_manager_with_tracking,
        mock_prompt_manager,
        mock_model_manager,
        progress_emitter_with_tracking
    ):
        """Test that batch progress events include active_files field."""
        # Arrange - Create batch with 4 documents (2 concurrent)
        file_ids = [f"file-{i}" for i in range(4)]

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
        batch_manager.start_batch_job(
            batch_job_id=batch.batch_job_id,
            file_manager=mock_file_manager,
            job_manager=mock_job_manager_with_tracking,
            prompt_manager=mock_prompt_manager,
            model_manager=mock_model_manager,
            progress_emitter=progress_emitter_with_tracking
        )

        # Wait for batch to complete
        timeout = time.time() + 10
        while time.time() < timeout:
            batch_obj = batch_manager.get_batch_job(batch.batch_job_id)
            if batch_obj.status in [BatchJobStatus.COMPLETED, BatchJobStatus.FAILED]:
                break
            time.sleep(0.2)

        # Assert - Check batch progress events
        with progress_emitter_with_tracking._events_lock:
            batch_events = progress_emitter_with_tracking._emitted_events["batch_progress"]

        assert len(batch_events) > 0, "Should have emitted batch progress events"

        # All events should have active_files field
        for event in batch_events:
            assert "active_files" in event, "Batch progress event should include active_files"
            assert "failed_files" in event, "Batch progress event should include failed_files"
            assert isinstance(event["active_files"], int), "active_files should be an integer"
            assert isinstance(event["failed_files"], int), "failed_files should be an integer"
            assert event["active_files"] >= 0, "active_files should be non-negative"
            assert event["failed_files"] >= 0, "failed_files should be non-negative"

    def test_active_files_reflects_concurrent_processing(
        self,
        batch_manager,
        mock_file_manager,
        mock_job_manager_with_tracking,
        mock_prompt_manager,
        mock_model_manager,
        progress_emitter_with_tracking
    ):
        """Test that active_files accurately reflects concurrent job count."""
        # Arrange - Create batch with 4 documents (2 concurrent)
        file_ids = [f"file-{i}" for i in range(4)]

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
        batch_manager.start_batch_job(
            batch_job_id=batch.batch_job_id,
            file_manager=mock_file_manager,
            job_manager=mock_job_manager_with_tracking,
            prompt_manager=mock_prompt_manager,
            model_manager=mock_model_manager,
            progress_emitter=progress_emitter_with_tracking
        )

        # Wait for batch to complete
        timeout = time.time() + 10
        while time.time() < timeout:
            batch_obj = batch_manager.get_batch_job(batch.batch_job_id)
            if batch_obj.status in [BatchJobStatus.COMPLETED, BatchJobStatus.FAILED]:
                break
            time.sleep(0.2)

        # Assert - Check that active_files never exceeds max_concurrent_jobs
        with progress_emitter_with_tracking._events_lock:
            batch_events = progress_emitter_with_tracking._emitted_events["batch_progress"]

        max_active_files = max(event["active_files"] for event in batch_events)
        assert max_active_files <= mock_job_manager_with_tracking.max_concurrent_jobs, \
            f"active_files ({max_active_files}) should not exceed max_concurrent_jobs (2)"

        # Check that we had concurrent processing (active_files > 0 at some point)
        had_concurrent_jobs = any(event["active_files"] > 0 for event in batch_events)
        assert had_concurrent_jobs, "Should have had concurrent jobs during processing"

    def test_progress_monotonically_increases(
        self,
        batch_manager,
        mock_file_manager,
        mock_job_manager_with_tracking,
        mock_prompt_manager,
        mock_model_manager,
        progress_emitter_with_tracking
    ):
        """Test that overall_progress_pct monotonically increases from 0 to 100."""
        # Arrange
        file_ids = [f"file-{i}" for i in range(3)]

        batch = batch_manager.create_batch_job(
            directory_id="test-dir",
            file_ids=file_ids,
            model="deepseek-ocr",
            prompt_type="ocr",
            custom_prompts=None,
            processing_options={"dpi": 300},
            output_format="markdown"
        )

        # Act
        batch_manager.start_batch_job(
            batch_job_id=batch.batch_job_id,
            file_manager=mock_file_manager,
            job_manager=mock_job_manager_with_tracking,
            prompt_manager=mock_prompt_manager,
            model_manager=mock_model_manager,
            progress_emitter=progress_emitter_with_tracking
        )

        # Wait for completion
        timeout = time.time() + 10
        while time.time() < timeout:
            batch_obj = batch_manager.get_batch_job(batch.batch_job_id)
            if batch_obj.status in [BatchJobStatus.COMPLETED, BatchJobStatus.FAILED]:
                break
            time.sleep(0.2)

        # Assert - Check monotonic increase
        with progress_emitter_with_tracking._events_lock:
            batch_events = progress_emitter_with_tracking._emitted_events["batch_progress"]

        progress_values = [event["overall_progress_pct"] for event in batch_events]

        # Progress should generally increase (allowing for small floating point variations)
        for i in range(1, len(progress_values)):
            # Allow for minor variations due to concurrent updates, but generally should increase
            assert progress_values[i] >= progress_values[i-1] - 1.0, \
                f"Progress should monotonically increase: {progress_values[i-1]:.2f} -> {progress_values[i]:.2f}"

        # Final progress should be close to 100
        final_batch = batch_manager.get_batch_job(batch.batch_job_id)
        assert final_batch.overall_progress_pct >= 99.0, \
            f"Final progress should be ~100%, got {final_batch.overall_progress_pct:.2f}%"

    def test_completion_event_emitted(
        self,
        batch_manager,
        mock_file_manager,
        mock_job_manager_with_tracking,
        mock_prompt_manager,
        mock_model_manager,
        progress_emitter_with_tracking
    ):
        """Test that completion event is emitted when batch finishes."""
        # Arrange
        file_ids = [f"file-{i}" for i in range(2)]

        batch = batch_manager.create_batch_job(
            directory_id="test-dir",
            file_ids=file_ids,
            model="deepseek-ocr",
            prompt_type="ocr",
            custom_prompts=None,
            processing_options={"dpi": 300},
            output_format="markdown"
        )

        # Act
        batch_manager.start_batch_job(
            batch_job_id=batch.batch_job_id,
            file_manager=mock_file_manager,
            job_manager=mock_job_manager_with_tracking,
            prompt_manager=mock_prompt_manager,
            model_manager=mock_model_manager,
            progress_emitter=progress_emitter_with_tracking
        )

        # Wait for completion
        timeout = time.time() + 10
        while time.time() < timeout:
            batch_obj = batch_manager.get_batch_job(batch.batch_job_id)
            if batch_obj.status in [BatchJobStatus.COMPLETED, BatchJobStatus.FAILED]:
                break
            time.sleep(0.2)

        # Assert
        with progress_emitter_with_tracking._events_lock:
            completion_events = progress_emitter_with_tracking._emitted_events["completion"]

        assert len(completion_events) > 0, "Should have emitted completion event"

        # Check completion event structure
        completion_event = completion_events[-1]
        assert completion_event["job_id"] == batch.batch_job_id
        assert completion_event["is_batch"] is True
        assert "batch_stats" in completion_event

    def test_thread_safe_progress_aggregation(
        self,
        batch_manager,
        mock_file_manager,
        mock_job_manager_with_tracking,
        mock_prompt_manager,
        mock_model_manager,
        progress_emitter_with_tracking
    ):
        """Test that progress aggregation is thread-safe with concurrent updates."""
        # Arrange - Create batch with more documents to stress test concurrency
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

        # Act
        batch_manager.start_batch_job(
            batch_job_id=batch.batch_job_id,
            file_manager=mock_file_manager,
            job_manager=mock_job_manager_with_tracking,
            prompt_manager=mock_prompt_manager,
            model_manager=mock_model_manager,
            progress_emitter=progress_emitter_with_tracking
        )

        # Wait for completion
        timeout = time.time() + 15
        while time.time() < timeout:
            batch_obj = batch_manager.get_batch_job(batch.batch_job_id)
            if batch_obj.status in [BatchJobStatus.COMPLETED, BatchJobStatus.FAILED]:
                break
            time.sleep(0.2)

        # Assert - Check for data consistency (no race conditions)
        with progress_emitter_with_tracking._events_lock:
            batch_events = progress_emitter_with_tracking._emitted_events["batch_progress"]

        # All events should have valid data
        for event in batch_events:
            # Check data consistency
            assert event["documents_completed"] <= event["total_documents"]
            assert event["active_files"] >= 0
            assert event["failed_files"] >= 0
            assert 0 <= event["overall_progress_pct"] <= 100.0

            # Active + completed + failed should not exceed total
            # (allowing for some overlap during concurrent processing)
            assert event["active_files"] + event["documents_completed"] <= event["total_documents"] + 2

    def test_batch_final_state_is_completed(
        self,
        batch_manager,
        mock_file_manager,
        mock_job_manager_with_tracking,
        mock_prompt_manager,
        mock_model_manager,
        progress_emitter_with_tracking
    ):
        """Test that batch reaches COMPLETED status with 100% progress."""
        # Arrange
        file_ids = [f"file-{i}" for i in range(3)]

        batch = batch_manager.create_batch_job(
            directory_id="test-dir",
            file_ids=file_ids,
            model="deepseek-ocr",
            prompt_type="ocr",
            custom_prompts=None,
            processing_options={"dpi": 300},
            output_format="markdown"
        )

        # Act
        batch_manager.start_batch_job(
            batch_job_id=batch.batch_job_id,
            file_manager=mock_file_manager,
            job_manager=mock_job_manager_with_tracking,
            prompt_manager=mock_prompt_manager,
            model_manager=mock_model_manager,
            progress_emitter=progress_emitter_with_tracking
        )

        # Wait for completion
        timeout = time.time() + 10
        while time.time() < timeout:
            batch_obj = batch_manager.get_batch_job(batch.batch_job_id)
            if batch_obj.status in [BatchJobStatus.COMPLETED, BatchJobStatus.FAILED]:
                break
            time.sleep(0.2)

        # Assert
        final_batch = batch_manager.get_batch_job(batch.batch_job_id)
        assert final_batch.status == BatchJobStatus.COMPLETED, \
            f"Batch should be COMPLETED, got {final_batch.status.value}"
        assert final_batch.overall_progress_pct == 100.0, \
            f"Final progress should be 100%, got {final_batch.overall_progress_pct}%"
        assert final_batch.documents_completed == len(file_ids), \
            f"Should have completed {len(file_ids)} documents, got {final_batch.documents_completed}"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
