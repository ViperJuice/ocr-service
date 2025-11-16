"""Integration tests for batch inference with running containers.

These tests require:
- DeepSeek-OCR container running on http://localhost:8001
- Qwen3-VL container running on http://localhost:8002
- Containers must support /batch_infer endpoint

Run with: pytest tests/integration/test_batch_inference.py -v
"""
import pytest
import time
from PIL import Image
from pathlib import Path

from src.models.model_manager import ModelManager
from src.models.types import OCRResult


@pytest.fixture
def model_configs():
    """Model configurations for testing."""
    return {
        "deepseek-ocr": {
            "infer_config": {
                "base_size": 1024,
                "image_size": 640,
                "crop_mode": True,
                "eval_mode": True
            },
            "prompts": {
                "ocr": "<image>\nFree OCR. "
            }
        },
        "qwen3-vl-8b": {
            "prompts": {
                "ocr": "Extract all text from this image."
            }
        }
    }


@pytest.fixture
async def model_manager(model_configs):
    """Create and initialize ModelManager with container mode."""
    manager = ModelManager(model_configs)
    await manager.initialize_container_mode(
        deepseek_url="http://localhost:8001",
        qwen_url="http://localhost:8002",
        timeout=300.0
    )
    yield manager
    await manager.close_container_mode()


@pytest.fixture
def sample_images():
    """Create sample images with text for OCR testing."""
    images = []

    # Create simple test images with text-like patterns
    for i in range(16):
        # Create a 200x100 white image with a dark rectangle (simulating text)
        img = Image.new('RGB', (200, 100), color='white')
        pixels = img.load()

        # Draw a simple rectangle (simulating text line)
        for x in range(50, 150):
            for y in range(40 + i, 45 + i):
                pixels[x, y] = (0, 0, 0)

        images.append(img)

    return images


@pytest.mark.integration
@pytest.mark.asyncio
class TestDeepSeekBatchInference:
    """Integration tests for DeepSeek batch inference."""

    async def test_deepseek_batch_4_images(self, model_manager, sample_images):
        """Test DeepSeek batch inference with 4 images."""
        images = sample_images[:4]

        # Test batch inference
        results = await model_manager.infer_batch_with_container(
            model_name="deepseek-ocr",
            images=images,
            auto_unload=True
        )

        # Verify results structure
        assert len(results) == 4
        assert all(isinstance(r, OCRResult) for r in results)
        assert all(r.model_name == "deepseek-ocr" for r in results)

        # Verify batch metadata
        assert all(r.metadata.get("batch_mode") is True for r in results)
        assert all(r.metadata.get("batch_size") == 4 for r in results)

        # Verify ordering
        for i, result in enumerate(results):
            assert result.metadata["batch_index"] == i

        # Log results for inspection
        for i, result in enumerate(results):
            print(f"\nImage {i}:")
            print(f"  Text: {result.text[:100] if result.text else '(empty)'}")
            print(f"  Success: {result.metadata.get('success')}")
            print(f"  Processing time: {result.processing_time:.3f}s")

    async def test_deepseek_batch_8_images(self, model_manager, sample_images):
        """Test DeepSeek batch inference with 8 images."""
        images = sample_images[:8]

        results = await model_manager.infer_batch_with_container(
            model_name="deepseek-ocr",
            images=images
        )

        assert len(results) == 8
        assert all(r.metadata["batch_size"] == 8 for r in results)

    async def test_deepseek_batch_16_images(self, model_manager, sample_images):
        """Test DeepSeek batch inference with maximum 16 images."""
        images = sample_images[:16]

        results = await model_manager.infer_batch_with_container(
            model_name="deepseek-ocr",
            images=images
        )

        assert len(results) == 16
        assert all(r.metadata["batch_size"] == 16 for r in results)


@pytest.mark.integration
@pytest.mark.asyncio
class TestQwenBatchInference:
    """Integration tests for Qwen batch inference."""

    async def test_qwen_batch_4_images(self, model_manager, sample_images):
        """Test Qwen batch inference with 4 images."""
        images = sample_images[:4]

        results = await model_manager.infer_batch_with_container(
            model_name="qwen3-vl-8b",
            images=images,
            auto_unload=True
        )

        # Verify results
        assert len(results) == 4
        assert all(isinstance(r, OCRResult) for r in results)
        assert all(r.model_name == "qwen3-vl-8b" for r in results)

        # Verify batch metadata
        assert all(r.metadata.get("batch_mode") is True for r in results)

        # Log results
        for i, result in enumerate(results):
            print(f"\nQwen Image {i}:")
            print(f"  Text: {result.text[:100] if result.text else '(empty)'}")
            print(f"  Success: {result.metadata.get('success')}")


@pytest.mark.integration
@pytest.mark.asyncio
class TestPerformanceComparison:
    """Compare batch vs sequential performance."""

    async def test_batch_vs_sequential_speedup(self, model_manager, sample_images):
        """Measure speedup: batch should be 3-4x faster than sequential."""
        images = sample_images[:8]

        # Test sequential processing
        print("\n=== Sequential Processing ===")
        sequential_start = time.time()
        sequential_results = []
        for i, image in enumerate(images):
            result = await model_manager.infer_with_container(
                model_name="deepseek-ocr",
                image=image,
                auto_unload=False  # Don't unload between images
            )
            sequential_results.append(result)
            print(f"  Image {i+1}/8 processed: {result.processing_time:.3f}s")

        sequential_time = time.time() - sequential_start
        print(f"Total sequential time: {sequential_time:.3f}s")

        # Test batch processing
        print("\n=== Batch Processing ===")
        batch_start = time.time()
        batch_results = await model_manager.infer_batch_with_container(
            model_name="deepseek-ocr",
            images=images,
            auto_unload=True
        )
        batch_time = time.time() - batch_start
        print(f"Total batch time: {batch_time:.3f}s")

        # Calculate speedup
        speedup = sequential_time / batch_time
        print(f"\n=== Performance Results ===")
        print(f"Sequential: {sequential_time:.3f}s")
        print(f"Batch:      {batch_time:.3f}s")
        print(f"Speedup:    {speedup:.2f}x")

        # Verify speedup (should be at least 2x, ideally 3-4x)
        assert speedup >= 2.0, f"Expected at least 2x speedup, got {speedup:.2f}x"

        # Verify both produce same number of results
        assert len(sequential_results) == len(batch_results) == 8

    async def test_batch_sizes_performance(self, model_manager, sample_images):
        """Test performance across different batch sizes."""
        batch_sizes = [1, 4, 8, 16]
        timings = {}

        for batch_size in batch_sizes:
            images = sample_images[:batch_size]

            start = time.time()
            results = await model_manager.infer_batch_with_container(
                model_name="deepseek-ocr",
                images=images,
                auto_unload=True
            )
            elapsed = time.time() - start

            timings[batch_size] = {
                "total_time": elapsed,
                "per_image": elapsed / batch_size
            }

            print(f"\nBatch size {batch_size}:")
            print(f"  Total time: {elapsed:.3f}s")
            print(f"  Per image:  {elapsed/batch_size:.3f}s")

        # Verify that per-image time decreases with larger batches
        # (due to amortized model loading and batched GPU operations)
        assert timings[8]["per_image"] < timings[1]["per_image"]


@pytest.mark.integration
@pytest.mark.asyncio
class TestMixedSuccessFailure:
    """Test handling of mixed success/failure in batch."""

    async def test_mixed_results_handling(self, model_manager, sample_images):
        """Test that both successful and failed items are handled correctly."""
        # Use mix of valid and potentially problematic images
        images = sample_images[:4]

        results = await model_manager.infer_batch_with_container(
            model_name="deepseek-ocr",
            images=images
        )

        # All results should be present (even if some failed)
        assert len(results) == 4

        # Check that success/failure is tracked
        for i, result in enumerate(results):
            success = result.metadata.get("success")
            error = result.metadata.get("error")

            print(f"\nImage {i}:")
            print(f"  Success: {success}")
            print(f"  Error: {error}")
            print(f"  Text length: {len(result.text)}")

            # Each result should have success status
            assert isinstance(success, bool)


@pytest.mark.integration
@pytest.mark.asyncio
class TestFallbackIntegration:
    """Test fallback behavior in real scenarios."""

    async def test_fallback_with_invalid_endpoint(self, model_manager, sample_images):
        """Test that invalid endpoint triggers fallback gracefully.

        Note: This test will only trigger fallback if the container
        doesn't have /batch_infer endpoint implemented.
        """
        images = sample_images[:3]

        # This should either work with batch or fallback to sequential
        results = await model_manager.infer_batch_with_container(
            model_name="deepseek-ocr",
            images=images
        )

        # Either way, we should get 3 results
        assert len(results) == 3
        assert all(isinstance(r, OCRResult) for r in results)

        # Check if fallback was used (lack of batch_mode in metadata)
        if results[0].metadata.get("batch_mode"):
            print("\nBatch endpoint available - batch processing used")
        else:
            print("\nBatch endpoint not available - sequential fallback used")
