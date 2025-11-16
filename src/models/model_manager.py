"""Model manager for containerized inference."""
import time
import logging
from typing import Dict, Optional, Literal
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
