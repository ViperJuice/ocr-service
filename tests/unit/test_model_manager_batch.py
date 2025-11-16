"""Unit tests for ModelManager batch inference."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from PIL import Image
import httpx

from src.models.model_manager import ModelManager
from src.models.types import OCRResult
from src.models.http_client_manager import HTTPClientManager, ModelType, ContainerConfig


@pytest.fixture
def model_configs():
    """Mock model configurations."""
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
def model_manager(model_configs):
    """Create ModelManager instance with mock config."""
    manager = ModelManager(model_configs)

    # Mock HTTP client manager
    manager.http_client_manager = MagicMock(spec=HTTPClientManager)
    manager.http_client_manager.configs = {
        ModelType.DEEPSEEK_OCR: ContainerConfig(
            model_type=ModelType.DEEPSEEK_OCR,
            base_url="http://localhost:8001",
            timeout=120.0
        ),
        ModelType.QWEN_VL: ContainerConfig(
            model_type=ModelType.QWEN_VL,
            base_url="http://localhost:8002",
            timeout=120.0
        )
    }

    return manager


@pytest.fixture
def sample_images():
    """Create sample PIL images for testing."""
    images = []
    for i in range(16):
        # Create a simple 100x100 RGB image
        img = Image.new('RGB', (100, 100), color=(i * 15, i * 15, i * 15))
        images.append(img)
    return images


class TestImageToBase64:
    """Test the _image_to_base64 helper method."""

    def test_converts_image_to_base64(self, model_manager, sample_images):
        """Test that image is correctly converted to base64."""
        image = sample_images[0]
        result = model_manager._image_to_base64(image)

        # Check it's a string
        assert isinstance(result, str)

        # Check it's valid base64 (should not raise exception)
        import base64
        decoded = base64.b64decode(result)
        assert len(decoded) > 0


class TestBatchInferenceValidation:
    """Test input validation for batch inference."""

    @pytest.mark.asyncio
    async def test_empty_images_list_raises_error(self, model_manager):
        """Test that empty images list raises ValueError."""
        with pytest.raises(ValueError, match="Images list cannot be empty"):
            await model_manager.infer_batch_with_container(
                model_name="deepseek-ocr",
                images=[]
            )

    @pytest.mark.asyncio
    async def test_too_many_images_raises_error(self, model_manager, sample_images):
        """Test that >16 images raises ValueError."""
        # Create 17 images
        too_many = sample_images[:16] + [sample_images[0]]

        with pytest.raises(ValueError, match="Batch size too large.*Maximum is 16"):
            await model_manager.infer_batch_with_container(
                model_name="deepseek-ocr",
                images=too_many
            )

    @pytest.mark.asyncio
    async def test_uninitialized_container_raises_error(self, model_configs):
        """Test that uninitialized container mode raises RuntimeError."""
        manager = ModelManager(model_configs)
        # Don't initialize http_client_manager

        with pytest.raises(RuntimeError, match="Container mode not initialized"):
            await manager.infer_batch_with_container(
                model_name="deepseek-ocr",
                images=[Image.new('RGB', (100, 100))]
            )


class TestDeepSeekBatchInference:
    """Test DeepSeek batch inference."""

    @pytest.mark.asyncio
    async def test_batch_inference_4_images(self, model_manager, sample_images):
        """Test batch inference with 4 images."""
        images = sample_images[:4]

        # Mock HTTP response
        mock_response = {
            "results": [
                {"text": f"OCR text {i}", "success": True, "error": None, "index": i}
                for i in range(4)
            ],
            "total_items": 4,
            "successful_items": 4,
            "failed_items": 0,
            "batch_success": True,
            "model_unloaded": False
        }

        with patch('httpx.AsyncClient') as mock_client_class:
            mock_client = AsyncMock()
            mock_client_class.return_value.__aenter__.return_value = mock_client

            mock_http_response = MagicMock()
            mock_http_response.json = MagicMock(return_value=mock_response)
            mock_http_response.raise_for_status = MagicMock()
            mock_client.post = AsyncMock(return_value=mock_http_response)

            results = await model_manager.infer_batch_with_container(
                model_name="deepseek-ocr",
                images=images
            )

        # Verify results
        assert len(results) == 4
        assert all(isinstance(r, OCRResult) for r in results)
        assert results[0].text == "OCR text 0"
        assert results[3].text == "OCR text 3"

        # Verify metadata
        assert results[0].metadata["batch_mode"] is True
        assert results[0].metadata["batch_size"] == 4
        assert results[0].metadata["batch_index"] == 0
        assert results[3].metadata["batch_index"] == 3

    @pytest.mark.asyncio
    async def test_batch_inference_8_images(self, model_manager, sample_images):
        """Test batch inference with 8 images."""
        images = sample_images[:8]

        mock_response = {
            "results": [
                {"text": f"Text {i}", "success": True, "error": None, "index": i}
                for i in range(8)
            ],
            "total_items": 8,
            "successful_items": 8,
            "failed_items": 0,
            "batch_success": True
        }

        with patch('httpx.AsyncClient') as mock_client_class:
            mock_client = AsyncMock()
            mock_client_class.return_value.__aenter__.return_value = mock_client

            mock_http_response = MagicMock()
            mock_http_response.json = MagicMock(return_value=mock_response)
            mock_http_response.raise_for_status = MagicMock()
            mock_client.post = AsyncMock(return_value=mock_http_response)

            results = await model_manager.infer_batch_with_container(
                model_name="deepseek-ocr",
                images=images
            )

        assert len(results) == 8
        assert all(r.metadata["batch_size"] == 8 for r in results)

    @pytest.mark.asyncio
    async def test_batch_inference_16_images(self, model_manager, sample_images):
        """Test batch inference with maximum 16 images."""
        images = sample_images[:16]

        mock_response = {
            "results": [
                {"text": f"Text {i}", "success": True, "error": None, "index": i}
                for i in range(16)
            ],
            "total_items": 16,
            "successful_items": 16,
            "failed_items": 0,
            "batch_success": True
        }

        with patch('httpx.AsyncClient') as mock_client_class:
            mock_client = AsyncMock()
            mock_client_class.return_value.__aenter__.return_value = mock_client

            mock_http_response = MagicMock()
            mock_http_response.json = MagicMock(return_value=mock_response)
            mock_http_response.raise_for_status = MagicMock()
            mock_client.post = AsyncMock(return_value=mock_http_response)

            results = await model_manager.infer_batch_with_container(
                model_name="deepseek-ocr",
                images=images
            )

        assert len(results) == 16
        assert results[0].metadata["batch_index"] == 0
        assert results[15].metadata["batch_index"] == 15


class TestQwenBatchInference:
    """Test Qwen batch inference."""

    @pytest.mark.asyncio
    async def test_qwen_batch_inference(self, model_manager, sample_images):
        """Test Qwen batch inference with messages format."""
        images = sample_images[:4]

        mock_response = {
            "results": [
                {"text": f"Qwen text {i}", "success": True, "error": None, "index": i}
                for i in range(4)
            ],
            "total_items": 4,
            "successful_items": 4,
            "failed_items": 0,
            "batch_success": True
        }

        with patch('httpx.AsyncClient') as mock_client_class:
            mock_client = AsyncMock()
            mock_client_class.return_value.__aenter__.return_value = mock_client

            mock_http_response = MagicMock()
            mock_http_response.json = MagicMock(return_value=mock_response)
            mock_http_response.raise_for_status = MagicMock()
            mock_client.post = AsyncMock(return_value=mock_http_response)

            results = await model_manager.infer_batch_with_container(
                model_name="qwen3-vl-8b",
                images=images
            )

        assert len(results) == 4
        assert results[0].text == "Qwen text 0"
        assert results[0].model_name == "qwen3-vl-8b"


class TestResultOrdering:
    """Test that results maintain input order."""

    @pytest.mark.asyncio
    async def test_results_match_input_order(self, model_manager, sample_images):
        """Test that results are in the same order as input images."""
        images = sample_images[:5]

        # Create response with mixed order indices (container should maintain order)
        mock_response = {
            "results": [
                {"text": f"Result-{i}", "success": True, "error": None, "index": i}
                for i in range(5)
            ],
            "total_items": 5,
            "successful_items": 5,
            "failed_items": 0,
            "batch_success": True
        }

        with patch('httpx.AsyncClient') as mock_client_class:
            mock_client = AsyncMock()
            mock_client_class.return_value.__aenter__.return_value = mock_client

            mock_http_response = MagicMock()
            mock_http_response.json = MagicMock(return_value=mock_response)
            mock_http_response.raise_for_status = MagicMock()
            mock_client.post = AsyncMock(return_value=mock_http_response)

            results = await model_manager.infer_batch_with_container(
                model_name="deepseek-ocr",
                images=images
            )

        # Verify order
        for i, result in enumerate(results):
            assert result.text == f"Result-{i}"
            assert result.metadata["batch_index"] == i


class TestFallbackToSequential:
    """Test fallback to sequential processing on 404."""

    @pytest.mark.asyncio
    async def test_fallback_on_404(self, model_manager, sample_images):
        """Test that 404 triggers fallback to sequential processing."""
        images = sample_images[:3]

        with patch('httpx.AsyncClient') as mock_client_class:
            mock_client = AsyncMock()
            mock_client_class.return_value.__aenter__.return_value = mock_client

            # First call: batch endpoint returns 404
            mock_404_response = MagicMock()
            mock_404_response.status_code = 404

            async def raise_404(*args, **kwargs):
                raise httpx.HTTPStatusError(
                    "Not Found",
                    request=MagicMock(),
                    response=mock_404_response
                )

            mock_client.post = AsyncMock(side_effect=raise_404)

            # Mock the infer_with_container method for sequential fallback
            sequential_results = [
                OCRResult(
                    text=f"Sequential {i}",
                    model_name="deepseek-ocr",
                    processing_time=1.0,
                    format="ocr",
                    metadata={"container_mode": True}
                )
                for i in range(3)
            ]

            with patch.object(model_manager, 'infer_with_container', new=AsyncMock()) as mock_infer:
                mock_infer.side_effect = sequential_results

                results = await model_manager.infer_batch_with_container(
                    model_name="deepseek-ocr",
                    images=images
                )

        # Verify sequential processing was used
        assert len(results) == 3
        assert all(r.text.startswith("Sequential") for r in results)


class TestErrorHandling:
    """Test error handling for partial batch failures."""

    @pytest.mark.asyncio
    async def test_partial_batch_failure(self, model_manager, sample_images):
        """Test handling of partial batch failures."""
        images = sample_images[:4]

        # Mock response with one failure
        mock_response = {
            "results": [
                {"text": "Success 0", "success": True, "error": None, "index": 0},
                {"text": "Success 1", "success": True, "error": None, "index": 1},
                {"text": "", "success": False, "error": "Processing failed", "index": 2},
                {"text": "Success 3", "success": True, "error": None, "index": 3}
            ],
            "total_items": 4,
            "successful_items": 3,
            "failed_items": 1,
            "batch_success": False
        }

        with patch('httpx.AsyncClient') as mock_client_class:
            mock_client = AsyncMock()
            mock_client_class.return_value.__aenter__.return_value = mock_client

            mock_http_response = MagicMock()
            mock_http_response.json = MagicMock(return_value=mock_response)
            mock_http_response.raise_for_status = MagicMock()
            mock_client.post = AsyncMock(return_value=mock_http_response)

            results = await model_manager.infer_batch_with_container(
                model_name="deepseek-ocr",
                images=images
            )

        # Verify all results returned (including failed one)
        assert len(results) == 4

        # Check success/failure status
        assert results[0].metadata["success"] is True
        assert results[1].metadata["success"] is True
        assert results[2].metadata["success"] is False
        assert results[2].metadata["error"] == "Processing failed"
        assert results[3].metadata["success"] is True

        # Batch success should be False
        assert all(r.metadata["batch_success"] is False for r in results)
