"""Result emitter for streaming OCR results via SSE."""
import asyncio
import logging
from typing import Dict, List, Any, Optional
from datetime import datetime

logger = logging.getLogger(__name__)


class ResultEmitter:
    """
    Singleton service to broadcast real-time page results to SSE clients.

    Manages client connections per job_id and broadcasts page completion events
    as they occur during OCR and merge stages.
    """

    _instance: Optional['ResultEmitter'] = None
    _lock = asyncio.Lock()

    def __new__(cls):
        """Ensure singleton pattern."""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self, event_loop=None):
        """
        Initialize result emitter.

        Args:
            event_loop: The main asyncio event loop (required for thread-safe operations)
        """
        if self._initialized:
            return

        self._clients: Dict[str, List[asyncio.Queue]] = {}
        self._client_lock = asyncio.Lock()
        self._event_loop = event_loop  # Store reference to main event loop
        self._initialized = True
        logger.info("ResultEmitter initialized")

    async def register_client(self, job_id: str, queue: asyncio.Queue) -> None:
        """
        Register a new SSE client for a job.

        Args:
            job_id: Job identifier
            queue: asyncio.Queue for sending events to this client
        """
        async with self._client_lock:
            if job_id not in self._clients:
                self._clients[job_id] = []
            self._clients[job_id].append(queue)
            logger.info(f"Client registered for job {job_id} (total: {len(self._clients[job_id])})")

    async def unregister_client(self, job_id: str, queue: asyncio.Queue) -> None:
        """
        Unregister an SSE client.

        Args:
            job_id: Job identifier
            queue: Client queue to remove
        """
        async with self._client_lock:
            if job_id in self._clients:
                try:
                    self._clients[job_id].remove(queue)
                    logger.info(f"Client unregistered for job {job_id} (remaining: {len(self._clients[job_id])})")

                    # Clean up empty job entries
                    if not self._clients[job_id]:
                        del self._clients[job_id]
                        logger.info(f"No more clients for job {job_id}, cleaned up")
                except ValueError:
                    pass  # Queue not in list

    def emit_ocr_page(self, job_id: str, page_num: int, text: str) -> None:
        """
        Emit OCR page completion event (called from worker thread).

        Args:
            job_id: Job identifier
            page_num: Page number (1-indexed)
            text: OCR text for this page
        """
        event = {
            "event": "ocr_page_complete",
            "data": {
                "page_num": page_num,
                "text": text,
                "timestamp": datetime.utcnow().isoformat() + 'Z'
            }
        }

        # Schedule broadcast in the main event loop from worker thread
        try:
            if self._event_loop is None:
                logger.error(f"Event loop not set - cannot emit OCR page {page_num} for job {job_id}")
                return
            asyncio.run_coroutine_threadsafe(self._broadcast(job_id, event), self._event_loop)
        except Exception as e:
            logger.error(f"Failed to emit OCR page {page_num} for job {job_id}: {e}")

    def emit_merge_page(
        self,
        job_id: str,
        page_num: int,
        text: str,
        processing_time: Optional[float] = None,
        total_pages: Optional[int] = None
    ) -> None:
        """
        Emit merge page completion event (called from worker thread).

        Args:
            job_id: Job identifier
            page_num: Page number (1-indexed)
            text: Merged text for this page
            processing_time: Optional processing time in seconds
            total_pages: Optional total pages in job
        """
        event_data = {
            "page_num": page_num,
            "text": text,
            "timestamp": datetime.utcnow().isoformat() + 'Z'
        }

        # Add optional metadata
        if processing_time is not None:
            event_data["processing_time"] = processing_time
        if total_pages is not None:
            event_data["total_pages"] = total_pages

        event = {
            "event": "merge_page_complete",
            "data": event_data
        }

        # Schedule broadcast in the main event loop from worker thread
        try:
            if self._event_loop is None:
                logger.error(f"Event loop not set - cannot emit merge page {page_num} for job {job_id}")
                return
            asyncio.run_coroutine_threadsafe(self._broadcast(job_id, event), self._event_loop)
        except Exception as e:
            logger.error(f"Failed to emit merge page {page_num} for job {job_id}: {e}")

    def emit_stage_complete(self, job_id: str, stage: str) -> None:
        """
        Emit stage completion event.

        Args:
            job_id: Job identifier
            stage: Stage name ("ocr" or "merge")
        """
        event = {
            "event": "stage_complete",
            "data": {
                "stage": stage,
                "timestamp": datetime.utcnow().isoformat() + 'Z'
            }
        }

        try:
            if self._event_loop is None:
                logger.error(f"Event loop not set - cannot emit stage complete {stage} for job {job_id}")
                return
            asyncio.run_coroutine_threadsafe(self._broadcast(job_id, event), self._event_loop)
        except Exception as e:
            logger.error(f"Failed to emit stage complete {stage} for job {job_id}: {e}")

    def emit_job_complete(self, job_id: str) -> None:
        """
        Emit job completion event.

        Args:
            job_id: Job identifier
        """
        event = {
            "event": "job_complete",
            "data": {
                "timestamp": datetime.utcnow().isoformat() + 'Z'
            }
        }

        try:
            if self._event_loop is None:
                logger.error(f"Event loop not set - cannot emit job complete for job {job_id}")
                return
            asyncio.run_coroutine_threadsafe(self._broadcast(job_id, event), self._event_loop)
        except Exception as e:
            logger.error(f"Failed to emit job complete for job {job_id}: {e}")

    def emit_model_loading_start(self, job_id: str, model_name: str, estimated_time: float, stage: str) -> None:
        """
        Emit model loading start event (called from worker thread).

        Args:
            job_id: Job identifier
            model_name: Name of the model being loaded
            estimated_time: Estimated loading time in seconds
            stage: Stage identifier ("deepseek" or "qwen")
        """
        logger.info(f"[DEBUG] emit_model_loading_start called: job_id={job_id}, model={model_name}, stage={stage}")
        event = {
            "event": "model_loading_start",
            "data": {
                "model_name": model_name,
                "estimated_time_seconds": estimated_time,
                "stage": stage,
                "timestamp": datetime.utcnow().isoformat() + 'Z'
            }
        }

        try:
            if self._event_loop is None:
                logger.error(f"Event loop not set - cannot emit model loading start for job {job_id}")
                return
            logger.info(f"[DEBUG] Scheduling broadcast for model_loading_start event using stored event loop")
            asyncio.run_coroutine_threadsafe(self._broadcast(job_id, event), self._event_loop)
            logger.info(f"[DEBUG] Broadcast scheduled successfully")
        except Exception as e:
            logger.error(f"Failed to emit model loading start for job {job_id}: {e}")

    def emit_model_loading_progress(self, job_id: str, progress_pct: float, current_stage: str, stage: str) -> None:
        """
        Emit model loading progress update (called from worker thread).

        Args:
            job_id: Job identifier
            progress_pct: Progress percentage (0-100)
            current_stage: Current loading stage description
            stage: Stage identifier ("deepseek" or "qwen")
        """
        event = {
            "event": "model_loading_progress",
            "data": {
                "progress_pct": progress_pct,
                "current_stage": current_stage,
                "stage": stage,
                "timestamp": datetime.utcnow().isoformat() + 'Z'
            }
        }

        try:
            if self._event_loop is None:
                logger.error(f"Event loop not set - cannot emit model loading progress for job {job_id}")
                return
            asyncio.run_coroutine_threadsafe(self._broadcast(job_id, event), self._event_loop)
        except Exception as e:
            logger.error(f"Failed to emit model loading progress for job {job_id}: {e}")

    def emit_model_loading_complete(self, job_id: str, actual_time: float, gpu_allocation: Dict[str, Any], stage: str) -> None:
        """
        Emit model loading completion event (called from worker thread).

        Args:
            job_id: Job identifier
            actual_time: Actual loading time in seconds
            gpu_allocation: GPU allocation information
            stage: Stage identifier ("deepseek" or "qwen")
        """
        event = {
            "event": "model_loading_complete",
            "data": {
                "actual_time_seconds": actual_time,
                "gpu_allocation": gpu_allocation,
                "stage": stage,
                "timestamp": datetime.utcnow().isoformat() + 'Z'
            }
        }

        try:
            if self._event_loop is None:
                logger.error(f"Event loop not set - cannot emit model loading complete for job {job_id}")
                return
            asyncio.run_coroutine_threadsafe(self._broadcast(job_id, event), self._event_loop)
        except Exception as e:
            logger.error(f"Failed to emit model loading complete for job {job_id}: {e}")

    async def _broadcast(self, job_id: str, event: Dict[str, Any]) -> None:
        """
        Broadcast event to all registered clients for a job.

        Args:
            job_id: Job identifier
            event: Event dictionary to broadcast
        """
        logger.info(f"[DEBUG _broadcast] Broadcasting event '{event.get('event')}' for job {job_id}")

        async with self._client_lock:
            if job_id not in self._clients:
                logger.info(f"[DEBUG _broadcast] No clients registered for job {job_id}")
                return

            # Send to all clients (copy list to avoid modification during iteration)
            clients = self._clients[job_id].copy()
            logger.info(f"[DEBUG _broadcast] Found {len(clients)} clients for job {job_id}")

        for queue in clients:
            try:
                await queue.put(event)
                logger.info(f"[DEBUG _broadcast] Event '{event.get('event')}' queued successfully")
            except Exception as e:
                logger.error(f"Failed to send event to client for job {job_id}: {e}")


# Singleton accessor
_emitter_instance: Optional[ResultEmitter] = None


def get_result_emitter() -> ResultEmitter:
    """Get or create the ResultEmitter singleton."""
    global _emitter_instance
    if _emitter_instance is None:
        _emitter_instance = ResultEmitter()
    return _emitter_instance
