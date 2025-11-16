"""Model manager for containerized inference."""
import time
import logging
import io
import base64
from typing import Dict, Optional, Literal, List
from PIL import Image

from .types import OCRResult

logger = logging.getLogger(__name__)

ModelName = Literal["qwen3-vl-8b", "qwen3-vl-4b", "qwen3-vl-2b", "deepseek-ocr"]


class ModelManager:
    """Manage containerized model inference via HTTP."""

    def __init__(self, model_configs: Dict[str, Dict]):
        """
        Initialize model manager for container mode.

        Args:
            model_configs: Dictionary of model configurations from YAML
        """
        self.model_configs = model_configs
        self.http_client_manager = None
        logger.info("ModelManager initialized in CONTAINER mode")

    async def initialize_container_mode(
        self,
        deepseek_url: str = "http://localhost:8001",
        qwen_url: str = "http://localhost:8002",
        timeout: float = 300.0
    ) -> None:
        """
        Initialize HTTP client manager for container mode.

        Args:
            deepseek_url: DeepSeek container base URL
            qwen_url: Qwen container base URL
            timeout: Request timeout in seconds

        Raises:
            RuntimeError: If initialization fails
        """
        from .http_client_manager import HTTPClientManager

        logger.info("Initializing container mode...")
        self.http_client_manager = HTTPClientManager()
        await self.http_client_manager.initialize(
            deepseek_url=deepseek_url,
            qwen_url=qwen_url,
            timeout=timeout
        )
        logger.info("✓ Container mode initialized")

    async def infer_with_container(
        self,
        model_name: str,
        image: Image.Image,
        prompt: Optional[str] = None,
        messages: Optional[list] = None,
        prompt_type: str = "ocr",
        auto_unload: bool = True,
        **kwargs
    ) -> OCRResult:
        """
        Perform inference using containerized model.

        Args:
            model_name: Model name ("deepseek-ocr", "qwen3-vl-8b", etc.)
            image: PIL Image to process
            prompt: Text prompt (for DeepSeek)
            messages: Chat messages (for Qwen)
            prompt_type: Prompt type for result metadata
            auto_unload: Whether to unload model after inference (default: True)
            **kwargs: Additional model-specific parameters

        Returns:
            OCRResult with inference results

        Raises:
            RuntimeError: If container unavailable or inference fails
        """
        if self.http_client_manager is None:
            raise RuntimeError("Container mode not initialized. Call initialize_container_mode() first")

        from .http_client_manager import ModelType
        import io
        import base64
        import httpx

        start_time = time.time()

        # Convert image to base64
        buffer = io.BytesIO()
        image.save(buffer, format='PNG')
        image_b64 = base64.b64encode(buffer.getvalue()).decode('utf-8')

        # Get container URLs from http_client_manager config
        deepseek_url = self.http_client_manager.configs[ModelType.DEEPSEEK_OCR].base_url
        qwen_url = self.http_client_manager.configs[ModelType.QWEN_VL].base_url
        default_timeout = self.http_client_manager.configs[ModelType.DEEPSEEK_OCR].timeout

        # Route to appropriate container
        if "deepseek" in model_name.lower():
            # Get DeepSeek config
            config = self.model_configs.get(model_name, {}).get("infer_config", {})
            prompts_config = self.model_configs.get(model_name, {}).get("prompts", {})

            # Use provided prompt or get from config
            if prompt is None:
                prompt = prompts_config.get(prompt_type, "<image>\nFree OCR. ")

            # Build request
            request_data = {
                "image_base64": image_b64,
                "prompt": prompt,
                "base_size": config.get("base_size", 1024),
                "image_size": config.get("image_size", 640),
                "crop_mode": config.get("crop_mode", True),
                "auto_unload": auto_unload
            }

            # Call container with fresh client (thread-safe)
            logger.info(f"Calling DeepSeek container for {model_name}")
            async with httpx.AsyncClient(timeout=kwargs.get("timeout", default_timeout)) as client:
                response = await client.post(f"{deepseek_url}/infer", json=request_data)
                response.raise_for_status()
                result = response.json()

                if not result.get("success", False):
                    raise RuntimeError(f"Inference failed: {result.get('error', 'Unknown error')}")

        elif "qwen" in model_name.lower():
            # Get Qwen config
            prompts_config = self.model_configs.get(model_name, {}).get("prompts", {})

            # Use provided messages or build from prompt
            if messages is None:
                prompt_text = prompts_config.get(prompt_type, "Extract all text from this image.")
                messages = [
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": prompt_text}
                        ]
                    }
                ]

            # Build request
            request_data = {
                "image_base64": image_b64,
                "messages": messages,
                "auto_unload": auto_unload
            }

            # Call container with fresh client (thread-safe)
            logger.info(f"Calling Qwen container for {model_name}")
            async with httpx.AsyncClient(timeout=kwargs.get("timeout", default_timeout)) as client:
                response = await client.post(f"{qwen_url}/infer", json=request_data)
                response.raise_for_status()
                result = response.json()

                if not result.get("success", False):
                    raise RuntimeError(f"Inference failed: {result.get('error', 'Unknown error')}")

        else:
            raise ValueError(f"Unknown model type: {model_name}")

        processing_time = time.time() - start_time

        # Convert container response to OCRResult
        return OCRResult(
            text=result.get("text", ""),
            model_name=model_name,
            processing_time=processing_time,
            format=prompt_type,
            metadata={
                "container_mode": True,
                "image_size": image.size,
                "success": result.get("success", False),
                "error": result.get("error"),
                "actual_model": result.get("model", model_name)  # Actual model variant used
            }
        )

    def _image_to_base64(self, image: Image.Image) -> str:
        """
        Convert PIL Image to base64 string.

        Args:
            image: PIL Image to convert

        Returns:
            Base64-encoded string
        """
        buffer = io.BytesIO()
        image.save(buffer, format='PNG')
        return base64.b64encode(buffer.getvalue()).decode('utf-8')

    async def infer_batch_with_container(
        self,
        model_name: str,
        images: List[Image.Image],
        prompt: Optional[str] = None,
        messages: Optional[list] = None,
        prompt_type: str = "ocr",
        auto_unload: bool = True,
        **kwargs
    ) -> List[OCRResult]:
        """
        Batch inference: send multiple images in single request.

        Args:
            model_name: "deepseek-ocr" or "qwen3-vl-*"
            images: List of PIL Images (1-16 recommended, 4-8 optimal)
            prompt: Shared prompt for all images
            messages: Optional messages (for Qwen)
            prompt_type: Prompt type for result metadata
            auto_unload: Whether to unload model after inference
            **kwargs: Additional model-specific parameters

        Returns:
            List of OCRResult (one per image, same order as input)

        Raises:
            RuntimeError: If container not initialized or doesn't support batch
            ValueError: If images list is empty or exceeds max batch size
        """
        if self.http_client_manager is None:
            raise RuntimeError("Container mode not initialized. Call initialize_container_mode() first")

        # Validate input
        if not images:
            raise ValueError("Images list cannot be empty")
        if len(images) > 16:
            raise ValueError(f"Batch size too large: {len(images)}. Maximum is 16 images")

        import httpx
        from .http_client_manager import ModelType

        start_time = time.time()

        # Get container URLs from http_client_manager config
        deepseek_url = self.http_client_manager.configs[ModelType.DEEPSEEK_OCR].base_url
        qwen_url = self.http_client_manager.configs[ModelType.QWEN_VL].base_url
        default_timeout = self.http_client_manager.configs[ModelType.DEEPSEEK_OCR].timeout

        # Determine if DeepSeek or Qwen
        is_deepseek = "deepseek" in model_name.lower()
        is_qwen = "qwen" in model_name.lower()

        if not is_deepseek and not is_qwen:
            raise ValueError(f"Unknown model type: {model_name}")

        # Try batch inference first
        try:
            if is_deepseek:
                # Get DeepSeek config
                config = self.model_configs.get(model_name, {}).get("infer_config", {})
                prompts_config = self.model_configs.get(model_name, {}).get("prompts", {})

                # Use provided prompt or get from config
                if prompt is None:
                    prompt = prompts_config.get(prompt_type, "<image>\nFree OCR. ")

                # Build batch request items
                items = []
                for image in images:
                    items.append({
                        "image_base64": self._image_to_base64(image),
                        "prompt": prompt,
                        "base_size": config.get("base_size", 1024),
                        "image_size": config.get("image_size", 640),
                        "crop_mode": config.get("crop_mode", True),
                        "eval_mode": config.get("eval_mode", True)
                    })

                # Build request
                request_data = {
                    "items": items,
                    "gpu_ids": None,
                    "auto_unload": auto_unload
                }

                # Call container batch endpoint
                logger.info(f"Calling DeepSeek batch_infer for {len(images)} images")
                async with httpx.AsyncClient(timeout=kwargs.get("timeout", default_timeout)) as client:
                    response = await client.post(f"{deepseek_url}/batch_infer", json=request_data)
                    response.raise_for_status()
                    result = response.json()

            elif is_qwen:
                # Get Qwen config
                prompts_config = self.model_configs.get(model_name, {}).get("prompts", {})

                # Use provided messages or build from prompt
                if messages is None:
                    prompt_text = prompts_config.get(prompt_type, "Extract all text from this image.")
                    messages = [
                        {
                            "role": "user",
                            "content": [
                                {"type": "text", "text": prompt_text}
                            ]
                        }
                    ]

                # Build batch request items
                items = []
                for image in images:
                    items.append({
                        "image_base64": self._image_to_base64(image),
                        "messages": messages
                    })

                # Build request
                request_data = {
                    "items": items,
                    "gpu_ids": None,
                    "auto_unload": auto_unload
                }

                # Call container batch endpoint
                logger.info(f"Calling Qwen batch_infer for {len(images)} images")
                async with httpx.AsyncClient(timeout=kwargs.get("timeout", default_timeout)) as client:
                    response = await client.post(f"{qwen_url}/batch_infer", json=request_data)
                    response.raise_for_status()
                    result = response.json()

            # Parse batch response
            results = []
            batch_results = result.get("results", [])

            for idx, image in enumerate(images):
                item_result = batch_results[idx] if idx < len(batch_results) else {}

                # Calculate per-image processing time (estimate)
                processing_time = (time.time() - start_time) / len(images)

                results.append(OCRResult(
                    text=item_result.get("text", ""),
                    model_name=model_name,
                    processing_time=processing_time,
                    format=prompt_type,
                    metadata={
                        "container_mode": True,
                        "batch_mode": True,
                        "batch_size": len(images),
                        "batch_index": idx,
                        "image_size": image.size,
                        "success": item_result.get("success", False),
                        "error": item_result.get("error"),
                        "batch_success": result.get("batch_success", False)
                    }
                ))

            return results

        except httpx.HTTPStatusError as e:
            # Check if 404 - endpoint not supported
            if e.response.status_code == 404:
                logger.warning(
                    f"Batch inference not supported for {model_name}, "
                    f"falling back to sequential processing"
                )

                # Fallback to sequential processing
                results = []
                for idx, image in enumerate(images):
                    logger.debug(f"Processing image {idx + 1}/{len(images)} sequentially")
                    result = await self.infer_with_container(
                        model_name=model_name,
                        image=image,
                        prompt=prompt,
                        messages=messages,
                        prompt_type=prompt_type,
                        auto_unload=auto_unload if idx == len(images) - 1 else False,  # Only unload on last
                        **kwargs
                    )
                    results.append(result)

                return results
            else:
                # Re-raise other HTTP errors
                raise

    async def check_container_health(self) -> Dict[str, bool]:
        """
        Check health of all containers.

        Returns:
            Dict mapping model type to health status

        Raises:
            RuntimeError: If container mode not initialized
        """
        if self.http_client_manager is None:
            raise RuntimeError("Container mode not initialized")

        from .http_client_manager import ModelType

        return {
            "deepseek": (await self.http_client_manager.check_health(ModelType.DEEPSEEK_OCR)).get("status") in ["ok", "ready"],
            "qwen": (await self.http_client_manager.check_health(ModelType.QWEN_VL)).get("status") in ["ok", "ready"]
        }

    async def close_container_mode(self) -> None:
        """Close HTTP client manager connections."""
        if self.http_client_manager:
            await self.http_client_manager.close()
            self.http_client_manager = None
            logger.info("Container mode closed")
