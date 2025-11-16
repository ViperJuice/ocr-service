"""Integration tests for Phase 3.7B - Batch Parallelization."""
import pytest
import asyncio
import threading
import time
from pathlib import Path
from unittest.mock import Mock, MagicMock, AsyncMock
from typing import List, Dict, Any

from src.api.services.batch_manager import BatchManager, _count_active_jobs_for_batch
from src.api.services.job_manager import JobManager, JobStatus
from src.api.services.progress_emitter import ProgressEmitter
from src.api.models.batch import BatchJobStatus


@pytest.fixture
def temp_dirs(tmp_path):
    """Create temporary directories for testing."""
    processing_dir = tmp_path / "processing"
    output_dir = tmp_path / "output"
    processing_dir.mkdir()
    output_dir.mkdir()
    return processing_dir, output_dir


@pytest.fixture
def mock_file_manager():
    """Create mock file manager for testing."""
    file_manager = Mock()

    # Mock file info
    def get_file_info(file_id):
        file_info = Mock()
        file_info.filename = f"{file_id}.pdf"
        file_info.page_count = 10
        return file_info

    file_manager.get_file_info = get_file_info
    file_manager.get_file_path = lambda file_id: Path(f"/tmp/{file_id}.pdf")

    return file_manager


@pytest.fixture
def mock_prompt_manager():
    """Create mock prompt manager for testing."""
    prompt_manager = Mock()
    prompt_manager.get_default_prompts = lambda model: {"system": "test"}
    prompt_manager.merge_prompts = lambda defaults, custom: defaults
    return prompt_manager


@pytest.fixture
def mock_model_manager():
    """Create mock model manager for testing."""
    return Mock()


@pytest.fixture
def progress_emitter():
    """Create real progress emitter for testing."""
    return ProgressEmitter()


@pytest.fixture
def job_manager_with_loop(temp_dirs):
    """Create job manager with event loop for async operations."""
    processing_dir, output_dir = temp_dirs

    # Create event loop for job manager
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    job_manager = JobManager(
        processing_directory=str(processing_dir),
        output_directory=str(output_dir),
        max_concurrent_jobs=2,
        event_loop=loop
    )

    yield job_manager

    # Cleanup - just close the loop, don't wait for jobs (tests don't start actual processing)
    try:
        # Cancel any pending tasks
        pending = asyncio.all_tasks(loop)
        for task in pending:
            task.cancel()
        # Give tasks a chance to cancel
        if pending:
            loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
    except Exception:
        pass
    finally:
        loop.close()


class TestConcurrentBatchProcessing:
    """Tests for concurrent batch processing (IF-0-3.7B)."""

    def test_count_active_jobs_for_batch(self, temp_dirs, job_manager_with_loop):
        """Test _count_active_jobs_for_batch helper function."""
        processing_dir, output_dir = temp_dirs
        job_manager = job_manager_with_loop

        batch_id = "batch_123"

        # Create mock jobs with different states
        async def create_test_jobs():
            # Job 1: processing, belongs to batch
            job1 = await job_manager.create_job(
                file_id="file_1",
                filename="file_1.pdf",
                model="test-model",
                prompt_type="default",
                custom_prompts=None,
                processing_options={},
                output_format="json",
                estimated_pages=10
            )
            job1.parent_batch_id = batch_id
            with job_manager.job_lock:
                job1.status = JobStatus.PROCESSING

            # Job 2: processing, belongs to batch
            job2 = await job_manager.create_job(
                file_id="file_2",
                filename="file_2.pdf",
                model="test-model",
                prompt_type="default",
                custom_prompts=None,
                processing_options={},
                output_format="json",
                estimated_pages=10
            )
            job2.parent_batch_id = batch_id
            with job_manager.job_lock:
                job2.status = JobStatus.PROCESSING

            # Job 3: completed, belongs to batch (should not be counted)
            job3 = await job_manager.create_job(
                file_id="file_3",
                filename="file_3.pdf",
                model="test-model",
                prompt_type="default",
                custom_prompts=None,
                processing_options={},
                output_format="json",
                estimated_pages=10
            )
            job3.parent_batch_id = batch_id
            with job_manager.job_lock:
                job3.status = JobStatus.COMPLETED

            # Job 4: processing, different batch (should not be counted)
            job4 = await job_manager.create_job(
                file_id="file_4",
                filename="file_4.pdf",
                model="test-model",
                prompt_type="default",
                custom_prompts=None,
                processing_options={},
                output_format="json",
                estimated_pages=10
            )
            job4.parent_batch_id = "different_batch"
            with job_manager.job_lock:
                job4.status = JobStatus.PROCESSING

        # Run async job creation using the job_manager's event loop
        job_manager._event_loop.run_until_complete(create_test_jobs())

        # Count active jobs for our batch
        active_count = _count_active_jobs_for_batch(batch_id, job_manager)

        # Should count only job1 and job2 (processing + correct batch)
        assert active_count == 2

    def test_count_active_jobs_empty_batch(self, temp_dirs, job_manager_with_loop):
        """Test counting active jobs for non-existent batch."""
        job_manager = job_manager_with_loop

        active_count = _count_active_jobs_for_batch("nonexistent_batch", job_manager)

        assert active_count == 0


class TestProgressAggregation:
    """Tests for progress aggregation with active_files (IF-1-3.7B)."""

    @pytest.mark.asyncio
    async def test_progress_event_schema(self, progress_emitter):
        """Test that progress events have correct schema with active_files."""
        # Register a connection to capture events
        connection_id = "test_conn"
        queue = await progress_emitter.register_connection(connection_id)

        # Emit batch progress with active_files
        await progress_emitter.emit_batch_progress(
            batch_job_id="batch_123",
            overall_progress_pct=50.0,
            documents_completed=5,
            total_documents=10,
            active_files=2,
            failed_files=1
        )

        # Get the event from queue
        event = await asyncio.wait_for(queue.get(), timeout=1.0)

        # Verify event schema (IF-1-3.7B)
        assert event["event"] == "batch_progress"
        data = event["data"]

        assert data["batch_job_id"] == "batch_123"
        assert data["overall_progress_pct"] == 50.0
        assert data["documents_completed"] == 5
        assert data["total_documents"] == 10
        assert data["active_files"] == 2  # NEW in Phase 3.7B
        assert data["failed_files"] == 1
        assert data["status"] == "processing"

        # Cleanup
        await progress_emitter.unregister_connection(connection_id)

    @pytest.mark.asyncio
    async def test_progress_event_defaults(self, progress_emitter):
        """Test that active_files and failed_files default to 0 if not provided."""
        connection_id = "test_conn"
        queue = await progress_emitter.register_connection(connection_id)

        # Emit without active_files/failed_files
        await progress_emitter.emit_batch_progress(
            batch_job_id="batch_123",
            overall_progress_pct=25.0,
            documents_completed=2,
            total_documents=10
        )

        event = await asyncio.wait_for(queue.get(), timeout=1.0)
        data = event["data"]

        # Should default to 0
        assert data["active_files"] == 0
        assert data["failed_files"] == 0

        await progress_emitter.unregister_connection(connection_id)

    @pytest.mark.asyncio
    async def test_progress_percent_monotonic(self, progress_emitter):
        """Test that progress_percent increases monotonically."""
        connection_id = "test_conn"
        queue = await progress_emitter.register_connection(connection_id)

        # Emit multiple progress updates
        progress_values = []

        for i in range(1, 11):
            await progress_emitter.emit_batch_progress(
                batch_job_id="batch_123",
                overall_progress_pct=i * 10.0,
                documents_completed=i,
                total_documents=10,
                active_files=1,
                failed_files=0
            )

            event = await asyncio.wait_for(queue.get(), timeout=1.0)
            progress_values.append(event["data"]["overall_progress_pct"])

        # Verify monotonically increasing
        for i in range(1, len(progress_values)):
            assert progress_values[i] >= progress_values[i-1], \
                f"Progress decreased: {progress_values[i-1]} -> {progress_values[i]}"

        # Verify reaches 100%
        assert progress_values[-1] == 100.0

        await progress_emitter.unregister_connection(connection_id)


class TestThreadSafety:
    """Tests for thread-safe progress aggregation."""

    def test_concurrent_progress_updates(self, temp_dirs, job_manager_with_loop, progress_emitter):
        """Test that concurrent progress updates are thread-safe."""
        processing_dir, output_dir = temp_dirs
        job_manager = job_manager_with_loop

        batch_manager = BatchManager(
            processing_directory=str(processing_dir),
            output_directory=str(output_dir),
            max_concurrent_batches=1
        )

        # Create a batch
        batch = batch_manager.create_batch_job(
            directory_id="test_dir",
            file_ids=[f"file_{i}" for i in range(20)],
            model="test-model",
            prompt_type="default",
            custom_prompts=None,
            processing_options={},
            output_format="json"
        )

        errors = []
        progress_updates = []

        def update_progress_worker(thread_id):
            """Worker thread that updates progress."""
            try:
                for i in range(10):
                    # Thread-safe read of batch state
                    with batch_manager.batch_lock:
                        batch.documents_completed += 1
                        completed = batch.documents_completed
                        total = batch.total_documents
                        progress_pct = (completed / total * 100) if total > 0 else 0

                    # Count active jobs (thread-safe)
                    active_count = _count_active_jobs_for_batch(batch.batch_job_id, job_manager)

                    progress_updates.append({
                        "thread_id": thread_id,
                        "iteration": i,
                        "completed": completed,
                        "progress_pct": progress_pct,
                        "active_count": active_count
                    })

                    time.sleep(0.001)  # Small delay to encourage race conditions
            except Exception as e:
                errors.append((thread_id, e))

        # Start multiple threads updating progress
        threads = []
        for i in range(5):
            t = threading.Thread(target=update_progress_worker, args=(i,))
            threads.append(t)
            t.start()

        # Wait for all threads
        for t in threads:
            t.join(timeout=10)

        # Verify no errors
        assert len(errors) == 0, f"Errors occurred: {errors}"

        # Verify we got updates from all threads
        assert len(progress_updates) == 50  # 5 threads * 10 iterations

        # Verify final state is consistent
        with batch_manager.batch_lock:
            assert batch.documents_completed == 50

    def test_concurrent_active_job_counting(self, temp_dirs, job_manager_with_loop):
        """Test that counting active jobs is thread-safe."""
        job_manager = job_manager_with_loop
        batch_id = "batch_concurrent"

        # Create some jobs
        async def create_jobs():
            jobs = []
            for i in range(10):
                job = await job_manager.create_job(
                    file_id=f"file_{i}",
                    filename=f"file_{i}.pdf",
                    model="test-model",
                    prompt_type="default",
                    custom_prompts=None,
                    processing_options={},
                    output_format="json",
                    estimated_pages=10
                )
                job.parent_batch_id = batch_id
                with job_manager.job_lock:
                    job.status = JobStatus.PROCESSING
                jobs.append(job)
            return jobs

        jobs = job_manager._event_loop.run_until_complete(create_jobs())

        errors = []
        counts = []

        def count_worker(thread_id):
            """Worker that counts active jobs."""
            try:
                for i in range(20):
                    count = _count_active_jobs_for_batch(batch_id, job_manager)
                    counts.append(count)
                    time.sleep(0.001)
            except Exception as e:
                errors.append((thread_id, e))

        # Start multiple threads counting
        threads = []
        for i in range(5):
            t = threading.Thread(target=count_worker, args=(i,))
            threads.append(t)
            t.start()

        # Wait for all threads
        for t in threads:
            t.join(timeout=10)

        # Verify no errors
        assert len(errors) == 0, f"Errors occurred: {errors}"

        # All counts should be 10 (all jobs are processing)
        for count in counts:
            assert count == 10


class TestBatchCompletionScenarios:
    """Tests for various batch completion scenarios."""

    @pytest.mark.asyncio
    async def test_final_progress_event(self, progress_emitter):
        """Test that final progress event shows 100% completion."""
        connection_id = "test_conn"
        queue = await progress_emitter.register_connection(connection_id)

        # Emit final progress
        await progress_emitter.emit_batch_progress(
            batch_job_id="batch_final",
            overall_progress_pct=100.0,
            documents_completed=10,
            total_documents=10,
            active_files=0,
            failed_files=0
        )

        event = await asyncio.wait_for(queue.get(), timeout=1.0)
        data = event["data"]

        assert data["overall_progress_pct"] == 100.0
        assert data["documents_completed"] == 10
        assert data["total_documents"] == 10
        assert data["active_files"] == 0
        assert data["failed_files"] == 0

        await progress_emitter.unregister_connection(connection_id)

    @pytest.mark.asyncio
    async def test_progress_with_failures(self, progress_emitter):
        """Test progress events when some documents fail."""
        connection_id = "test_conn"
        queue = await progress_emitter.register_connection(connection_id)

        # 10 total, 7 completed, 2 active, 1 failed
        await progress_emitter.emit_batch_progress(
            batch_job_id="batch_with_failures",
            overall_progress_pct=70.0,
            documents_completed=7,
            total_documents=10,
            active_files=2,
            failed_files=1
        )

        event = await asyncio.wait_for(queue.get(), timeout=1.0)
        data = event["data"]

        assert data["documents_completed"] == 7
        assert data["active_files"] == 2
        assert data["failed_files"] == 1
        assert data["documents_completed"] + data["active_files"] + data["failed_files"] == data["total_documents"]

        await progress_emitter.unregister_connection(connection_id)


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
