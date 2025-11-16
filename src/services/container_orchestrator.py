"""
Container Orchestrator for Docker-based Model Inference

Manages lifecycle of DeepSeek-OCR and Qwen-VL Docker containers with:
- Async start/stop operations via docker compose
- Health monitoring via /health endpoints
- Configurable behavior (enable/disable orchestration)
- Callback support for lifecycle events
"""

import asyncio
import logging
import time
import httpx
from typing import Optional, Callable, Dict, Any
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

logger = logging.getLogger(__name__)


class ContainerName(Enum):
    """Supported model containers."""
    DEEPSEEK_OCR = "deepseek-ocr"
    QWEN_VL = "qwen-vl"


class ContainerState(Enum):
    """Container lifecycle states."""
    STOPPED = "stopped"
    STARTING = "starting"
    READY = "ready"
    RUNNING = "running"
    STOPPING = "stopping"
    ERROR = "error"


@dataclass
class ContainerConfig:
    """Configuration for a model container."""
    name: str
    health_url: str
    timeout: float = 120.0


@dataclass
class ContainerLifecycleEvent:
    """Event emitted during container lifecycle transitions."""
    container_name: str
    state: ContainerState
    timestamp: float
    metadata: Optional[Dict[str, Any]] = None


class ContainerOrchestrator:
    """
    Manages Docker container lifecycle for model inference.

    Provides async start/stop operations for DeepSeek-OCR and Qwen-VL
    containers with health monitoring and lifecycle callbacks.

    Features:
    - Configurable orchestration (can be disabled for multi-GPU)
    - Docker Compose integration
    - Health endpoint polling
    - Retry logic with exponential backoff
    - Thread-safe async operations
    """

    def __init__(
        self,
        compose_file: str = "/home/jenner/code/ocr-service/docker-compose.yml",
        enabled: bool = True,
        event_loop: Optional[asyncio.AbstractEventLoop] = None
    ):
        """
        Initialize container orchestrator.

        Args:
            compose_file: Path to docker-compose.yml
            enabled: Whether orchestration is enabled (False = containers stay running)
            event_loop: Event loop for async operations
        """
        self.compose_file = Path(compose_file)
        self.enabled = enabled
        self.event_loop = event_loop or asyncio.get_event_loop()

        # Container configurations
        self._configs: Dict[ContainerName, ContainerConfig] = {
            ContainerName.DEEPSEEK_OCR: ContainerConfig(
                name="deepseek",  # Docker compose service name
                health_url="http://localhost:8001/health",
                timeout=120.0
            ),
            ContainerName.QWEN_VL: ContainerConfig(
                name="qwen",  # Docker compose service name
                health_url="http://localhost:8002/health",
                timeout=120.0
            )
        }

        if not enabled:
            logger.info("Container orchestration DISABLED - containers will stay running")
        else:
            logger.info("Container orchestration ENABLED - containers will start/stop per job")

    def is_enabled(self) -> bool:
        """Check if orchestration is enabled."""
        return self.enabled

    async def start_container(
        self,
        container_name: ContainerName,
        on_starting: Optional[Callable[[ContainerLifecycleEvent], None]] = None,
        on_ready: Optional[Callable[[ContainerLifecycleEvent], None]] = None,
        on_error: Optional[Callable[[ContainerLifecycleEvent], None]] = None,
        max_retries: int = 3
    ) -> bool:
        """
        Start a container asynchronously with lifecycle callbacks.

        Args:
            container_name: Which container to start
            on_starting: Callback when container start initiated
            on_ready: Callback when container reports healthy
            on_error: Callback on startup failure
            max_retries: Maximum retry attempts for failures

        Returns:
            True if container started successfully, False otherwise

        Raises:
            RuntimeError: If container fails to start after retries
        """
        if not self.enabled:
            logger.debug(f"Orchestration disabled - skipping start for {container_name.value}")
            return True  # Assume already running

        # Debug logging
        logger.debug(f"Looking up container_name: {container_name} (type: {type(container_name)})")
        logger.debug(f"Available configs: {list(self._configs.keys())}")

        config = self._configs[container_name]
        logger.info(f"Starting container: {container_name.value}")

        for attempt in range(max_retries):
            try:
                # Emit starting event
                if on_starting:
                    event = ContainerLifecycleEvent(
                        container_name=container_name.value,
                        state=ContainerState.STARTING,
                        timestamp=time.time(),
                        metadata={"attempt": attempt + 1, "max_retries": max_retries}
                    )
                    on_starting(event)

                # Execute docker compose up -d
                process = await asyncio.create_subprocess_exec(
                    "docker", "compose", "-f", str(self.compose_file),
                    "up", "-d", config.name,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
                )

                stdout, stderr = await process.communicate()

                if process.returncode != 0:
                    error_msg = stderr.decode().strip()
                    logger.error(f"Docker compose failed for {container_name.value}: {error_msg}")

                    if attempt < max_retries - 1:
                        logger.warning(f"Retry {attempt + 1}/{max_retries} in 5 seconds...")
                        await asyncio.sleep(5.0)
                        continue
                    else:
                        if on_error:
                            event = ContainerLifecycleEvent(
                                container_name=container_name.value,
                                state=ContainerState.ERROR,
                                timestamp=time.time(),
                                metadata={"error": error_msg}
                            )
                            on_error(event)
                        raise RuntimeError(f"Failed to start {container_name.value}: {error_msg}")

                # Wait for container to be ready
                logger.debug(f"Container {container_name.value} started, waiting for health...")
                is_ready = await self.wait_for_ready(container_name, timeout=config.timeout)

                if not is_ready:
                    if attempt < max_retries - 1:
                        logger.warning(f"Health check timeout, retry {attempt + 1}/{max_retries}...")
                        await asyncio.sleep(5.0)
                        continue
                    else:
                        error_msg = f"Health check timeout after {config.timeout}s"
                        if on_error:
                            event = ContainerLifecycleEvent(
                                container_name=container_name.value,
                                state=ContainerState.ERROR,
                                timestamp=time.time(),
                                metadata={"error": error_msg}
                            )
                            on_error(event)
                        raise RuntimeError(f"{container_name.value} {error_msg}")

                # Emit ready event
                if on_ready:
                    event = ContainerLifecycleEvent(
                        container_name=container_name.value,
                        state=ContainerState.READY,
                        timestamp=time.time()
                    )
                    on_ready(event)

                logger.info(f"✓ Container {container_name.value} ready")
                return True

            except Exception as e:
                if attempt < max_retries - 1:
                    logger.warning(f"Start attempt {attempt + 1}/{max_retries} failed: {e}")
                    await asyncio.sleep(5.0)
                else:
                    logger.error(f"Failed to start {container_name.value} after {max_retries} attempts")
                    raise

        return False

    async def stop_container(
        self,
        container_name: ContainerName,
        on_stopping: Optional[Callable[[ContainerLifecycleEvent], None]] = None,
        on_stopped: Optional[Callable[[ContainerLifecycleEvent], None]] = None
    ) -> bool:
        """
        Stop a container gracefully.

        Args:
            container_name: Which container to stop
            on_stopping: Callback when stop initiated
            on_stopped: Callback when container fully stopped

        Returns:
            True if stopped successfully, False otherwise
        """
        if not self.enabled:
            logger.debug(f"Orchestration disabled - skipping stop for {container_name.value}")
            return True

        config = self._configs[container_name]
        logger.info(f"Stopping container: {container_name.value}")

        try:
            # Emit stopping event
            if on_stopping:
                event = ContainerLifecycleEvent(
                    container_name=container_name.value,
                    state=ContainerState.STOPPING,
                    timestamp=time.time()
                )
                on_stopping(event)

            # Execute docker compose stop
            process = await asyncio.create_subprocess_exec(
                "docker", "compose", "-f", str(self.compose_file),
                "stop", config.name,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )

            stdout, stderr = await process.communicate()

            if process.returncode != 0:
                error_msg = stderr.decode().strip()
                logger.error(f"Docker compose stop failed for {container_name.value}: {error_msg}")
                return False

            # Emit stopped event
            if on_stopped:
                event = ContainerLifecycleEvent(
                    container_name=container_name.value,
                    state=ContainerState.STOPPED,
                    timestamp=time.time()
                )
                on_stopped(event)

            logger.info(f"✓ Container {container_name.value} stopped")
            return True

        except Exception as e:
            logger.error(f"Failed to stop {container_name.value}: {e}")
            return False

    async def wait_for_ready(
        self,
        container_name: ContainerName,
        timeout: float = 120.0
    ) -> bool:
        """
        Poll /health endpoint until container reports ready.

        Args:
            container_name: Which container to check
            timeout: Maximum wait time in seconds

        Returns:
            True if container became ready, False on timeout
        """
        config = self._configs[container_name]
        start_time = time.time()

        logger.debug(f"Polling {config.health_url} for readiness...")

        while (time.time() - start_time) < timeout:
            try:
                async with httpx.AsyncClient() as client:
                    response = await client.get(config.health_url, timeout=5.0)

                    if response.status_code == 200:
                        health_data = response.json()
                        status = health_data.get("status")

                        # Accept "ok" or "ready" status
                        if status in ["ok", "ready"]:
                            elapsed = time.time() - start_time
                            logger.debug(f"Container {container_name.value} ready after {elapsed:.1f}s")
                            return True

            except (httpx.HTTPError, httpx.ConnectError, Exception) as e:
                # Container not yet responding, continue polling
                logger.debug(f"Health check failed (expected during startup): {type(e).__name__}")

            # Poll every 2 seconds
            await asyncio.sleep(2.0)

        elapsed = time.time() - start_time
        logger.error(f"Container {container_name.value} health timeout after {elapsed:.1f}s")
        return False

    async def check_container_health(self, container_name: ContainerName) -> ContainerState:
        """
        Check current container health status.

        Args:
            container_name: Which container to check

        Returns:
            Current container state
        """
        config = self._configs[container_name]

        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(config.health_url, timeout=5.0)

                if response.status_code == 200:
                    health_data = response.json()
                    status = health_data.get("status")

                    if status in ["ok", "ready"]:
                        return ContainerState.READY
                    else:
                        return ContainerState.RUNNING

        except (httpx.HTTPError, Exception):
            return ContainerState.STOPPED

    # Convenience methods for specific containers

    async def start_deepseek(self, **kwargs) -> bool:
        """Start DeepSeek-OCR container."""
        return await self.start_container(ContainerName.DEEPSEEK_OCR, **kwargs)

    async def stop_deepseek(self, **kwargs) -> bool:
        """Stop DeepSeek-OCR container."""
        return await self.stop_container(ContainerName.DEEPSEEK_OCR, **kwargs)

    async def start_qwen(self, **kwargs) -> bool:
        """Start Qwen-VL container."""
        return await self.start_container(ContainerName.QWEN_VL, **kwargs)

    async def stop_qwen(self, **kwargs) -> bool:
        """Stop Qwen-VL container."""
        return await self.stop_container(ContainerName.QWEN_VL, **kwargs)

    async def restart_container(
        self,
        container_name: ContainerName,
        on_restarting: Optional[Callable[[ContainerLifecycleEvent], None]] = None,
        on_ready: Optional[Callable[[ContainerLifecycleEvent], None]] = None
    ) -> bool:
        """
        Restart a container (stop then start).

        Useful for clearing file descriptor leaks and other state.

        Args:
            container_name: Which container to restart
            on_restarting: Callback when restart initiated
            on_ready: Callback when container ready after restart

        Returns:
            True if restart successful
        """
        if on_restarting:
            event = ContainerLifecycleEvent(
                container_name=container_name.value,
                state=ContainerState.STOPPING,
                timestamp=time.time(),
                metadata={"operation": "restart"}
            )
            on_restarting(event)

        # Stop then start
        await self.stop_container(container_name)
        return await self.start_container(container_name, on_ready=on_ready)
