"""
Pipeline Coordinator for Container Lifecycle Management

Coordinates container orchestration with pipeline stages via callbacks.
Handles stage transitions: init → OCR → merge → complete

Features:
- Stage-aware container management (DeepSeek for OCR, Qwen for merge)
- Callback-driven lifecycle (on_pipeline_start, on_ocr_complete, etc.)
- Real-time UI updates via ResultEmitter integration
- Configurable orchestration (can be disabled for multi-GPU)
"""

import asyncio
import logging
import time
from typing import Optional, Dict, Any
from dataclasses import dataclass
from enum import Enum

# Import container orchestrator
from ..services.container_orchestrator import (
    ContainerOrchestrator,
    ContainerName,
    ContainerState,
    ContainerLifecycleEvent
)

logger = logging.getLogger(__name__)


class PipelineStage(Enum):
    """Pipeline processing stages"""
    INIT = "init"           # Before OCR starts
    OCR = "ocr"             # OCR in progress
    MERGE = "merge"         # Merge in progress
    COMPLETE = "complete"   # Pipeline finished


@dataclass
class StageTransitionEvent:
    """Event emitted when pipeline transitions between stages"""
    from_stage: Optional[PipelineStage]
    to_stage: PipelineStage
    timestamp: float
    metadata: Optional[Dict[str, Any]] = None


class PipelineCoordinator:
    """
    Coordinates container lifecycle with pipeline stage transitions.

    Manages container start/stop operations based on pipeline flow:
    - INIT → OCR: Start DeepSeek container
    - OCR → MERGE: Stop DeepSeek, start Qwen container
    - MERGE → COMPLETE: Stop Qwen container

    Features:
    - Async callback-driven architecture
    - Real-time UI updates (via ResultEmitter)
    - Configurable orchestration (enable/disable)
    - Error handling and retry logic
    """

    def __init__(
        self,
        container_orchestrator: ContainerOrchestrator,
        job_id: str,
        result_emitter: Optional[Any] = None,  # ResultEmitter from src.utils.result_emitter
        event_loop: Optional[asyncio.AbstractEventLoop] = None
    ):
        """
        Initialize pipeline coordinator.

        Args:
            container_orchestrator: ContainerOrchestrator instance
            job_id: Job identifier for emitting events
            result_emitter: Optional ResultEmitter for UI updates
            event_loop: Event loop for async operations
        """
        self.orchestrator = container_orchestrator
        self.job_id = job_id
        self.result_emitter = result_emitter
        self.event_loop = event_loop or asyncio.get_event_loop()

        # Track current stage
        self.current_stage: Optional[PipelineStage] = None

        # Track container states
        self.deepseek_running = False
        self.qwen_running = False

        logger.info("Pipeline coordinator initialized")

        if not self.orchestrator.is_enabled():
            logger.info("Container orchestration DISABLED - coordinator will be a no-op")

    def _emit_status(self, message: str, metadata: Optional[Dict[str, Any]] = None):
        """
        Emit status update to UI via ResultEmitter.

        Args:
            message: Status message to display
            metadata: Optional metadata for UI
        """
        if self.result_emitter:
            try:
                # Emit as system message
                self.result_emitter.emit_system_message(self.job_id, message, metadata or {})
            except Exception as e:
                logger.warning(f"Failed to emit status update: {e}")

    async def on_pipeline_start(self, event: StageTransitionEvent) -> None:
        """
        Callback when pipeline starts (INIT → OCR transition).

        Actions:
        - Start DeepSeek-OCR container
        - Wait for container to be ready
        - Emit UI updates for progress

        Args:
            event: Stage transition event

        Raises:
            RuntimeError: If container fails to start
        """
        logger.info("Pipeline starting - initializing DeepSeek-OCR container")
        self.current_stage = PipelineStage.INIT

        # Emit status update
        self._emit_status(
            "Starting DeepSeek-OCR container...",
            {"stage": "init", "container": "deepseek-ocr"}
        )

        # Container lifecycle callbacks
        def on_starting(container_event: ContainerLifecycleEvent):
            logger.info(f"DeepSeek container starting (attempt {container_event.metadata.get('attempt', 1)})...")
            self._emit_status(
                f"DeepSeek container starting...",
                {"stage": "init", "state": "starting"}
            )

        def on_ready(container_event: ContainerLifecycleEvent):
            logger.info("✓ DeepSeek container ready")
            self.deepseek_running = True
            self._emit_status(
                "DeepSeek container ready",
                {"stage": "init", "state": "ready"}
            )
            # Emit model ready event so UI knows which model is running
            if self.result_emitter:
                self.result_emitter.emit_model_ready(
                    self.job_id,
                    stage="ocr",
                    model_name="deepseek-ai/DeepSeek-OCR"
                )

        def on_error(container_event: ContainerLifecycleEvent):
            error_msg = container_event.metadata.get("error", "Unknown error")
            logger.error(f"DeepSeek container failed: {error_msg}")
            self._emit_status(
                f"DeepSeek container error: {error_msg}",
                {"stage": "init", "state": "error"}
            )

        # Start DeepSeek container
        try:
            success = await self.orchestrator.start_container(
                ContainerName.DEEPSEEK_OCR,
                on_starting=on_starting,
                on_ready=on_ready,
                on_error=on_error
            )

            if not success:
                raise RuntimeError("Failed to start DeepSeek container")

            logger.info("Pipeline ready for OCR stage")

        except Exception as e:
            logger.error(f"Pipeline start failed: {e}")
            self._emit_status(
                f"Pipeline initialization failed: {e}",
                {"stage": "init", "state": "error"}
            )
            raise

    async def on_ocr_complete(self, event: StageTransitionEvent) -> None:
        """
        Callback when OCR completes (OCR → MERGE transition).

        Actions:
        - Stop DeepSeek-OCR container (free VRAM)
        - Start Qwen-VL container (for merge)
        - Wait for Qwen to be ready
        - Emit UI updates

        Args:
            event: Stage transition event

        Raises:
            RuntimeError: If container operations fail
        """
        logger.info("OCR complete - transitioning to merge stage")
        self.current_stage = PipelineStage.OCR

        # Emit status update
        self._emit_status(
            "OCR complete - preparing merge stage...",
            {"stage": "ocr_complete", "transition": "ocr_to_merge"}
        )

        # Stop DeepSeek container (async, non-blocking)
        async def stop_deepseek():
            def on_stopping(container_event: ContainerLifecycleEvent):
                logger.info("Stopping DeepSeek container (freeing VRAM)...")
                self._emit_status(
                    "Stopping DeepSeek container...",
                    {"stage": "ocr_complete", "action": "stop_deepseek"}
                )

            def on_stopped(container_event: ContainerLifecycleEvent):
                logger.info("✓ DeepSeek container stopped")
                self.deepseek_running = False
                self._emit_status(
                    "DeepSeek container stopped",
                    {"stage": "ocr_complete", "state": "stopped"}
                )

            try:
                await self.orchestrator.stop_container(
                    ContainerName.DEEPSEEK_OCR,
                    on_stopping=on_stopping,
                    on_stopped=on_stopped
                )
            except Exception as e:
                logger.warning(f"Failed to stop DeepSeek container: {e}")

        # Start Qwen container (async, parallel with DeepSeek stop)
        async def start_qwen():
            def on_starting(container_event: ContainerLifecycleEvent):
                logger.info(f"Starting Qwen container (attempt {container_event.metadata.get('attempt', 1)})...")
                self._emit_status(
                    "Starting Qwen container for merge...",
                    {"stage": "ocr_complete", "action": "start_qwen"}
                )

            def on_ready(container_event: ContainerLifecycleEvent):
                logger.info("✓ Qwen container ready")
                self.qwen_running = True
                self._emit_status(
                    "Qwen container ready for merge",
                    {"stage": "merge", "state": "ready"}
                )
                # Emit model ready event so UI knows which model is running
                if self.result_emitter:
                    self.result_emitter.emit_model_ready(
                        self.job_id,
                        stage="merge",
                        model_name="Qwen/Qwen3-VL-8B-Instruct"
                    )

            def on_error(container_event: ContainerLifecycleEvent):
                error_msg = container_event.metadata.get("error", "Unknown error")
                logger.error(f"Qwen container failed: {error_msg}")
                self._emit_status(
                    f"Qwen container error: {error_msg}",
                    {"stage": "merge", "state": "error"}
                )

            try:
                success = await self.orchestrator.start_container(
                    ContainerName.QWEN_VL,
                    on_starting=on_starting,
                    on_ready=on_ready,
                    on_error=on_error
                )

                if not success:
                    raise RuntimeError("Failed to start Qwen container")

            except Exception as e:
                logger.error(f"Failed to start Qwen container: {e}")
                raise

        # Run sequentially to avoid OOM (stop DeepSeek completely before starting Qwen)
        try:
            await stop_deepseek()
            await start_qwen()

            logger.info("✓ Container transition complete (DeepSeek stopped, Qwen ready)")
            self.current_stage = PipelineStage.MERGE

        except Exception as e:
            logger.error(f"Container transition failed: {e}")
            self._emit_status(
                f"Container transition failed: {e}",
                {"stage": "ocr_complete", "state": "error"}
            )
            raise

    async def on_pipeline_complete(self, event: StageTransitionEvent) -> None:
        """
        Callback when pipeline completes (MERGE → COMPLETE transition).

        Actions:
        - Stop Qwen-VL container (free VRAM)
        - Emit completion status
        - Reset coordinator state

        Args:
            event: Stage transition event
        """
        logger.info("Pipeline complete - cleaning up containers")
        self.current_stage = PipelineStage.MERGE

        # Emit status update
        self._emit_status(
            "Pipeline complete - cleaning up...",
            {"stage": "complete", "action": "cleanup"}
        )

        # Stop Qwen container
        def on_stopping(container_event: ContainerLifecycleEvent):
            logger.info("Stopping Qwen container...")
            self._emit_status(
                "Stopping Qwen container...",
                {"stage": "complete", "action": "stop_qwen"}
            )

        def on_stopped(container_event: ContainerLifecycleEvent):
            logger.info("✓ Qwen container stopped")
            self.qwen_running = False
            self._emit_status(
                "Qwen container stopped",
                {"stage": "complete", "state": "stopped"}
            )

        try:
            await self.orchestrator.stop_container(
                ContainerName.QWEN_VL,
                on_stopping=on_stopping,
                on_stopped=on_stopped
            )

            logger.info("✓ Pipeline cleanup complete")
            self.current_stage = PipelineStage.COMPLETE

            self._emit_status(
                "Pipeline cleanup complete",
                {"stage": "complete", "state": "done"}
            )

        except Exception as e:
            logger.warning(f"Failed to stop Qwen container during cleanup: {e}")
            # Don't raise - cleanup is best-effort

    async def on_error(self, error: Exception, current_stage: PipelineStage) -> None:
        """
        Callback when pipeline encounters an error.

        Actions:
        - Stop all running containers (cleanup)
        - Emit error status
        - Reset coordinator state

        Args:
            error: Exception that occurred
            current_stage: Stage where error occurred
        """
        logger.error(f"Pipeline error at stage {current_stage.value}: {error}")

        # Emit error status
        self._emit_status(
            f"Pipeline error: {error}",
            {"stage": current_stage.value, "state": "error"}
        )

        # Stop all running containers (best-effort cleanup)
        cleanup_tasks = []

        if self.deepseek_running:
            logger.info("Emergency cleanup: stopping DeepSeek container")
            cleanup_tasks.append(
                self.orchestrator.stop_container(ContainerName.DEEPSEEK_OCR)
            )

        if self.qwen_running:
            logger.info("Emergency cleanup: stopping Qwen container")
            cleanup_tasks.append(
                self.orchestrator.stop_container(ContainerName.QWEN_VL)
            )

        if cleanup_tasks:
            try:
                await asyncio.gather(*cleanup_tasks, return_exceptions=True)
                logger.info("✓ Emergency cleanup complete")
            except Exception as cleanup_error:
                logger.warning(f"Emergency cleanup failed: {cleanup_error}")

        # Reset state
        self.deepseek_running = False
        self.qwen_running = False
        self.current_stage = None

    def get_container_states(self) -> Dict[str, bool]:
        """
        Get current container running states.

        Returns:
            Dict with keys: deepseek_running, qwen_running
        """
        return {
            "deepseek_running": self.deepseek_running,
            "qwen_running": self.qwen_running
        }

    def get_current_stage(self) -> Optional[PipelineStage]:
        """
        Get current pipeline stage.

        Returns:
            Current stage or None if pipeline not started
        """
        return self.current_stage
