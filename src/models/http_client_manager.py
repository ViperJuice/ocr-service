"""
HTTP Client Manager for Containerized Model Inference

Manages HTTP connections to DeepSeek-OCR and Qwen3-VL Docker containers.
Provides connection pooling, health checks, and request routing.
"""

import asyncio
import logging
import json
from typing import Dict, Any, Optional, List, AsyncIterator, Union
from dataclasses import dataclass
import httpx
from enum import Enum

logger = logging.getLogger(__name__)


class ModelType(Enum):
    """Model types supported by containers"""
    DEEPSEEK_OCR = "deepseek"
    QWEN_VL = "qwen"


@dataclass
class ContainerConfig:
    """Configuration for a model container"""
    model_type: ModelType
    base_url: str
    timeout: float = 120.0  # 2 minutes default for model inference
    max_retries: int = 3

    @property
    def health_url(self) -> str:
        return f"{self.base_url}/health"

    @property
    def info_url(self) -> str:
        return f"{self.base_url}/info"

    @property
    def infer_url(self) -> str:
        return f"{self.base_url}/infer"


class HTTPClientManager:
    """
    Manages HTTP clients for containerized model inference

    Features:
    - Connection pooling via httpx.AsyncClient
    - Health checks for container availability
    - Automatic retry with exponential backoff
    - Request timeout management
    """

    def __init__(self):
        self.clients: Dict[ModelType, httpx.AsyncClient] = {}
        self.configs: Dict[ModelType, ContainerConfig] = {}
        self._initialized = False

    async def initialize(
        self,
        deepseek_url: str = "http://localhost:8001",
        qwen_url: str = "http://localhost:8002",
        timeout: float = 120.0
    ):
        """
        Initialize HTTP clients for both model containers

        Args:
            deepseek_url: Base URL for DeepSeek-OCR container
            qwen_url: Base URL for Qwen3-VL container
            timeout: Default timeout for inference requests (seconds)
        """
        logger.info("Initializing HTTP client manager...")

        # Configure containers
        self.configs[ModelType.DEEPSEEK_OCR] = ContainerConfig(
            model_type=ModelType.DEEPSEEK_OCR,
            base_url=deepseek_url,
            timeout=timeout
        )

        self.configs[ModelType.QWEN_VL] = ContainerConfig(
            model_type=ModelType.QWEN_VL,
            base_url=qwen_url,
            timeout=timeout
        )

        # Create async HTTP clients with connection pooling
        for model_type, config in self.configs.items():
            self.clients[model_type] = httpx.AsyncClient(
                base_url=config.base_url,
                timeout=httpx.Timeout(timeout, connect=10.0),
                limits=httpx.Limits(
                    max_connections=10,
                    max_keepalive_connections=5
                )
            )
            logger.info(f"Created HTTP client for {model_type.value} at {config.base_url}")

        # Verify containers are healthy
        await self.check_all_health(_skip_init_check=True)

        self._initialized = True
        logger.info("✓ HTTP client manager initialized")

    async def check_health(self, model_type: ModelType, _skip_init_check: bool = False) -> Dict[str, Any]:
        """
        Check health of a specific container

        Args:
            model_type: Which model container to check
            _skip_init_check: Internal flag to skip initialization check (used during initialization)

        Returns:
            Health status dict with keys: status, model_loaded, etc.

        Raises:
            httpx.HTTPError: If container is unreachable or unhealthy
        """
        if not _skip_init_check and not self._initialized:
            raise RuntimeError("HTTPClientManager not initialized. Call initialize() first.")

        client = self.clients[model_type]
        config = self.configs[model_type]

        try:
            response = await client.get("/health", timeout=5.0)
            response.raise_for_status()
            health_data = response.json()

            logger.debug(f"{model_type.value} health: {health_data}")
            return health_data

        except httpx.HTTPError as e:
            logger.error(f"Health check failed for {model_type.value}: {e}")
            raise

    async def check_all_health(self, _skip_init_check: bool = False) -> Dict[ModelType, Dict[str, Any]]:
        """
        Check health of all containers in parallel

        Args:
            _skip_init_check: Internal flag to skip initialization check (used during initialization)

        Returns:
            Dict mapping model types to their health status

        Raises:
            RuntimeError: If any container is unhealthy
        """
        logger.info("Checking health of all containers...")

        results = {}
        errors = []

        # Check all containers in parallel
        health_checks = {
            model_type: self.check_health(model_type, _skip_init_check=_skip_init_check)
            for model_type in ModelType
        }

        for model_type, health_future in health_checks.items():
            try:
                results[model_type] = await health_future

                # Check if container is responsive (model_loaded can be false with auto_unload)
                status = results[model_type].get("status")
                if status in ["ok", "ready"]:
                    model_loaded = results[model_type].get("model_loaded", False)
                    if model_loaded:
                        logger.info(f"✓ {model_type.value} container healthy (model loaded)")
                    else:
                        logger.info(f"✓ {model_type.value} container healthy (model unloaded - will load on demand)")
                else:
                    errors.append(f"{model_type.value}: Status '{status}' not OK")

            except Exception as e:
                errors.append(f"{model_type.value}: {str(e)}")

        if errors:
            error_msg = "Container health check failed:\n  " + "\n  ".join(errors)
            logger.error(error_msg)
            raise RuntimeError(error_msg)

        logger.info("✓ All containers healthy")
        return results

    async def get_model_info(self, model_type: ModelType) -> Dict[str, Any]:
        """
        Get detailed information about a model container

        Args:
            model_type: Which model to query

        Returns:
            Info dict with keys: model, transformers_version, device, dtype
        """
        if not self._initialized:
            raise RuntimeError("HTTPClientManager not initialized. Call initialize() first.")

        client = self.clients[model_type]

        try:
            response = await client.get("/info", timeout=5.0)
            response.raise_for_status()
            return response.json()

        except httpx.HTTPError as e:
            logger.error(f"Failed to get info for {model_type.value}: {e}")
            raise

    async def infer(
        self,
        model_type: ModelType,
        request_data: Dict[str, Any],
        timeout: Optional[float] = None
    ) -> Dict[str, Any]:
        """
        Send inference request to a model container

        Args:
            model_type: Which model to use
            request_data: Request payload (image_base64, prompt/messages, etc.)
            timeout: Optional override for request timeout

        Returns:
            Response dict with keys: text, success, error (optional)

        Raises:
            httpx.HTTPError: If request fails
        """
        if not self._initialized:
            raise RuntimeError("HTTPClientManager not initialized. Call initialize() first.")

        client = self.clients[model_type]
        config = self.configs[model_type]
        request_timeout = timeout if timeout is not None else config.timeout

        logger.debug(f"Sending inference request to {model_type.value}")

        try:
            response = await client.post(
                "/infer",
                json=request_data,
                timeout=request_timeout
            )
            response.raise_for_status()
            result = response.json()

            if not result.get("success", False):
                error_msg = result.get("error", "Unknown error")
                logger.error(f"{model_type.value} inference failed: {error_msg}")
                raise RuntimeError(f"Inference failed: {error_msg}")

            logger.debug(f"{model_type.value} inference successful")
            return result

        except httpx.HTTPError as e:
            logger.error(f"HTTP error during {model_type.value} inference: {e}")
            raise

    async def list_models(self, model_type: ModelType) -> Dict[str, Any]:
        """
        Get list of available models from container (OpenAI-compatible)

        Args:
            model_type: Which container to query

        Returns:
            OpenAI-compatible models list

        Raises:
            httpx.HTTPError: If request fails
        """
        if not self._initialized:
            raise RuntimeError("HTTPClientManager not initialized. Call initialize() first.")

        client = self.clients[model_type]

        try:
            response = await client.get("/v1/models", timeout=5.0)
            response.raise_for_status()
            return response.json()

        except httpx.HTTPError as e:
            logger.error(f"Failed to list models for {model_type.value}: {e}")
            raise

    async def chat_completion(
        self,
        model_type: ModelType,
        messages: List[Dict[str, Any]],
        stream: bool = False,
        max_tokens: int = 2048,
        temperature: float = 0.0,
        timeout: Optional[float] = None,
        **kwargs  # Container-specific parameters (base_size, image_size, etc.)
    ) -> Union[Dict[str, Any], AsyncIterator[Dict[str, Any]]]:
        """
        Send OpenAI-compatible chat completion request

        Args:
            model_type: Which model to use
            messages: OpenAI format messages with text and image_url content
            stream: Whether to stream response (SSE)
            max_tokens: Maximum tokens to generate
            temperature: Sampling temperature
            timeout: Optional timeout override
            **kwargs: Additional container-specific parameters

        Returns:
            Dict for non-streaming, AsyncIterator for streaming

        Raises:
            httpx.HTTPError: If request fails
        """
        if not self._initialized:
            raise RuntimeError("HTTPClientManager not initialized. Call initialize() first.")

        client = self.clients[model_type]
        config = self.configs[model_type]
        request_timeout = timeout if timeout is not None else config.timeout

        # Build request payload
        request_data = {
            "model": "deepseek" if model_type == ModelType.DEEPSEEK_OCR else "qwen",
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "stream": stream,
            **kwargs  # Include container-specific parameters
        }

        logger.debug(f"Sending chat completion request to {model_type.value} (stream={stream})")

        if stream:
            # Streaming response with SSE parsing
            async def stream_chunks():
                try:
                    async with client.stream(
                        "POST",
                        "/v1/chat/completions",
                        json=request_data,
                        timeout=request_timeout
                    ) as response:
                        response.raise_for_status()

                        async for line in response.aiter_lines():
                            if line.startswith("data: "):
                                data = line[6:]  # Remove "data: " prefix
                                if data == "[DONE]":
                                    break
                                try:
                                    chunk = json.loads(data)
                                    yield chunk
                                except json.JSONDecodeError as e:
                                    logger.warning(f"Failed to parse SSE chunk: {e}")
                                    continue

                except httpx.HTTPError as e:
                    logger.error(f"HTTP error during streaming chat completion: {e}")
                    raise

            return stream_chunks()

        else:
            # Non-streaming response
            try:
                response = await client.post(
                    "/v1/chat/completions",
                    json=request_data,
                    timeout=request_timeout
                )
                response.raise_for_status()
                result = response.json()

                logger.debug(f"{model_type.value} chat completion successful")
                return result

            except httpx.HTTPError as e:
                logger.error(f"HTTP error during {model_type.value} chat completion: {e}")
                raise

    async def close(self):
        """Close all HTTP client connections"""
        logger.info("Closing HTTP clients...")

        for model_type, client in self.clients.items():
            await client.aclose()
            logger.debug(f"Closed {model_type.value} client")

        self.clients.clear()
        self._initialized = False
        logger.info("✓ HTTP clients closed")

    async def __aenter__(self):
        """Async context manager entry"""
        if not self._initialized:
            await self.initialize()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit"""
        await self.close()


# Singleton instance for application-wide use
_client_manager: Optional[HTTPClientManager] = None


async def get_client_manager() -> HTTPClientManager:
    """
    Get or create the global HTTPClientManager instance

    Returns:
        Initialized HTTPClientManager singleton
    """
    global _client_manager

    if _client_manager is None:
        _client_manager = HTTPClientManager()
        await _client_manager.initialize()

    return _client_manager


async def close_client_manager():
    """Close the global HTTPClientManager instance"""
    global _client_manager

    if _client_manager is not None:
        await _client_manager.close()
        _client_manager = None
