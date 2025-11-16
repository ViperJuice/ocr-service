"""Unit tests for BatchManager concurrent processing (Phase 3.7B)."""
import pytest
import threading
import time
from pathlib import Path

from src.api.services.batch_manager import BatchManager
from src.api.models.batch import BatchJobStatus


@pytest.fixture
def temp_dirs(tmp_path):
    """Create temporary directories for testing."""
    processing_dir = tmp_path / "processing"
    output_dir = tmp_path / "output"
    processing_dir.mkdir()
    output_dir.mkdir()
    return processing_dir, output_dir


def test_batch_manager_initialization(temp_dirs):
    """Test that BatchManager initializes correctly."""
    processing_dir, output_dir = temp_dirs

    batch_manager = BatchManager(
        processing_directory=str(processing_dir),
        output_directory=str(output_dir),
        max_concurrent_batches=1
    )

    assert batch_manager.processing_directory == processing_dir
    assert batch_manager.output_directory == output_dir
    assert batch_manager.max_concurrent_batches == 1
    assert len(batch_manager.batches) == 0
    assert batch_manager.batch_lock is not None


def test_create_batch_job(temp_dirs):
    """Test batch job creation."""
    processing_dir, output_dir = temp_dirs

    batch_manager = BatchManager(
        processing_directory=str(processing_dir),
        output_directory=str(output_dir)
    )

    file_ids = [f"file_{i}" for i in range(5)]
    batch = batch_manager.create_batch_job(
        directory_id="test_dir",
        file_ids=file_ids,
        model="test-model",
        prompt_type="default",
        custom_prompts=None,
        processing_options={},
        output_format="json"
    )

    assert batch is not None
    assert batch.total_documents == 5
    assert batch.documents_completed == 0
    assert batch.status == BatchJobStatus.QUEUED
    assert len(batch.file_ids) == 5
    assert batch.batch_job_id in batch_manager.batches


def test_get_batch_job(temp_dirs):
    """Test retrieving a batch job."""
    processing_dir, output_dir = temp_dirs

    batch_manager = BatchManager(
        processing_directory=str(processing_dir),
        output_directory=str(output_dir)
    )

    batch = batch_manager.create_batch_job(
        directory_id="test_dir",
        file_ids=["file_1", "file_2"],
        model="test-model",
        prompt_type="default",
        custom_prompts=None,
        processing_options={},
        output_format="json"
    )

    retrieved_batch = batch_manager.get_batch_job(batch.batch_job_id)
    assert retrieved_batch.batch_job_id == batch.batch_job_id
    assert retrieved_batch.total_documents == 2


def test_get_batch_job_not_found(temp_dirs):
    """Test error handling for missing batch job."""
    processing_dir, output_dir = temp_dirs

    batch_manager = BatchManager(
        processing_directory=str(processing_dir),
        output_directory=str(output_dir)
    )

    with pytest.raises(ValueError, match="Batch job not found"):
        batch_manager.get_batch_job("nonexistent_id")


def test_thread_safety_batch_lock(temp_dirs):
    """Test that batch_lock properly protects shared state."""
    processing_dir, output_dir = temp_dirs

    batch_manager = BatchManager(
        processing_directory=str(processing_dir),
        output_directory=str(output_dir)
    )

    # Create a batch
    batch = batch_manager.create_batch_job(
        directory_id="test_dir",
        file_ids=["file_1", "file_2"],
        model="test-model",
        prompt_type="default",
        custom_prompts=None,
        processing_options={},
        output_format="json"
    )

    # Test concurrent updates to batch progress
    errors = []
    updates_completed = []

    def update_progress(thread_id):
        """Simulate concurrent progress updates."""
        try:
            for i in range(50):
                with batch_manager.batch_lock:
                    batch.overall_progress_pct += 0.1
                time.sleep(0.001)
            updates_completed.append(thread_id)
        except Exception as e:
            errors.append((thread_id, e))

    # Start multiple threads updating progress
    threads = []
    for i in range(5):
        t = threading.Thread(target=update_progress, args=(i,))
        threads.append(t)
        t.start()

    # Wait for all threads to complete
    for t in threads:
        t.join(timeout=10)

    # Verify no errors occurred
    assert len(errors) == 0, f"Errors occurred: {errors}"

    # Verify all threads completed
    assert len(updates_completed) == 5

    # Verify progress was updated (should be 5 threads * 50 iterations * 0.1)
    # Allow some floating point tolerance
    expected_progress = 5 * 50 * 0.1
    assert abs(batch.overall_progress_pct - expected_progress) < 0.1


def test_concurrent_batch_method_exists(temp_dirs):
    """Test that _process_batch_concurrent method exists and is properly defined."""
    processing_dir, output_dir = temp_dirs

    batch_manager = BatchManager(
        processing_directory=str(processing_dir),
        output_directory=str(output_dir)
    )

    # Verify the method exists
    assert hasattr(batch_manager, '_process_batch_concurrent')
    assert callable(getattr(batch_manager, '_process_batch_concurrent'))

    # Verify the async helper exists
    assert hasattr(batch_manager, '_process_batch_concurrent_async')
    assert callable(getattr(batch_manager, '_process_batch_concurrent_async'))


def test_batch_manager_interface_frozen_comment(temp_dirs):
    """Test that the interface is marked as frozen in the code."""
    import inspect
    processing_dir, output_dir = temp_dirs

    batch_manager = BatchManager(
        processing_directory=str(processing_dir),
        output_directory=str(output_dir)
    )

    # Get the docstring of the method
    method = getattr(batch_manager, '_process_batch_concurrent')
    docstring = inspect.getdoc(method)

    # Verify interface is documented as frozen
    assert "INTERFACE FROZEN" in docstring
    assert "IF-0-3.7B" in docstring
    assert "Concurrent Batch Processing" in docstring


def test_cleanup_old_batches(temp_dirs):
    """Test cleanup of old batch jobs."""
    processing_dir, output_dir = temp_dirs

    batch_manager = BatchManager(
        processing_directory=str(processing_dir),
        output_directory=str(output_dir)
    )

    # Create 5 batches
    batches = []
    for i in range(5):
        batch = batch_manager.create_batch_job(
            directory_id=f"dir_{i}",
            file_ids=[f"file_{i}"],
            model="test-model",
            prompt_type="default",
            custom_prompts=None,
            processing_options={},
            output_format="json"
        )
        # Mark as completed
        with batch_manager.batch_lock:
            batch.status = BatchJobStatus.COMPLETED
        batches.append(batch)

    assert len(batch_manager.batches) == 5

    # Keep only 3 batches
    cleaned = batch_manager.cleanup_old_batches(max_batches=3)

    assert cleaned == 2
    assert len(batch_manager.batches) == 3


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
