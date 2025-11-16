"""Centralized SSE progress emission service."""
import asyncio
import json
import logging
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)


class ProgressEmitter:
    """Centralized SSE progress emission."""

    def __init__(self):
        """Initialize progress emitter with active connections."""
        self.connections: Dict[str, asyncio.Queue] = {}
        self.lock = asyncio.Lock()
        logger.info("ProgressEmitter initialized")

    async def register_connection(self, connection_id: str) -> asyncio.Queue:
        """
        Register a new SSE connection.

        Args:
            connection_id: Unique connection identifier

        Returns:
            Queue for this connection to receive events
        """
        async with self.lock:
            queue = asyncio.Queue()
            self.connections[connection_id] = queue
            logger.info(f"SSE connection registered: {connection_id}")
            return queue

    async def unregister_connection(self, connection_id: str) -> None:
        """
        Unregister an SSE connection.

        Args:
            connection_id: Connection identifier to remove
        """
        async with self.lock:
            if connection_id in self.connections:
                del self.connections[connection_id]
                logger.info(f"SSE connection unregistered: {connection_id}")

    async def emit_job_progress(
        self,
        job_id: str,
        progress_pct: float,
        current_stage: str,
        pages_completed: int,
        total_pages: Optional[int] = None,
        parent_batch_id: Optional[str] = None
    ) -> None:
        """
        Emit progress update for a single job.

        Args:
            job_id: Job identifier
            progress_pct: Progress percentage (0-100)
            current_stage: Current processing stage
            pages_completed: Number of pages completed
            total_pages: Total number of pages (optional)
            parent_batch_id: Parent batch job ID if applicable
        """
        event_data = {
            "job_id": job_id,
            "status": "processing",
            "progress_pct": progress_pct,
            "current_page": pages_completed,
            "total_pages": total_pages,
            "stage": current_stage,
            "pages_completed": pages_completed,
            "parent_batch_id": parent_batch_id
        }

        await self._broadcast_event("job_progress", event_data)

    async def emit_batch_progress(
        self,
        batch_job_id: str,
        overall_progress_pct: float,
        documents_completed: int,
        total_documents: int,
        current_document_id: Optional[str] = None,
        current_document_progress: Optional[Dict[str, Any]] = None,
        active_files: Optional[int] = None,
        failed_files: Optional[int] = None
    ) -> None:
        """
        Emit progress update for a batch job.

        Event Schema (Phase 3.7B - IF-1-3.7B):
            {
                "batch_job_id": str,
                "status": "processing",
                "overall_progress_pct": float,
                "documents_completed": int,
                "total_documents": int,
                "active_files": int,  # Number of documents currently processing
                "failed_files": int,
                "current_document": dict (optional)
            }

        Progress Calculation:
            overall_progress_pct = (documents_completed / total_documents) * 100
            active_files = count of jobs in "processing" state for this batch

        Thread Safety:
            - Uses batch_manager.batch_lock for safe batch state access
            - Uses job_manager.job_lock for safe job state access

        Args:
            batch_job_id: Batch job identifier
            overall_progress_pct: Overall batch progress percentage
            documents_completed: Number of documents completed
            total_documents: Total number of documents in batch
            current_document_id: Currently processing document ID
            current_document_progress: Current document progress details
            active_files: Number of documents currently processing (Phase 3.7B)
            failed_files: Number of documents that failed (Phase 3.7B)
        """
        event_data = {
            "batch_job_id": batch_job_id,
            "status": "processing",
            "overall_progress_pct": overall_progress_pct,
            "documents_completed": documents_completed,
            "total_documents": total_documents,
            "active_files": active_files if active_files is not None else 0,
            "failed_files": failed_files if failed_files is not None else 0,
        }

        if current_document_progress:
            event_data["current_document"] = current_document_progress

        await self._broadcast_event("batch_progress", event_data)

    async def emit_document_progress(
        self,
        batch_job_id: str,
        job_id: str,
        filename: str,
        progress_pct: float,
        current_page: int,
        total_pages: int,
        stage: str
    ) -> None:
        """
        Emit progress update for a document within a batch.

        Args:
            batch_job_id: Parent batch job identifier
            job_id: Document job identifier
            filename: Document filename
            progress_pct: Document progress percentage
            current_page: Current page number
            total_pages: Total pages in document
            stage: Current processing stage
        """
        event_data = {
            "batch_job_id": batch_job_id,
            "job_id": job_id,
            "filename": filename,
            "progress_pct": progress_pct,
            "current_page": current_page,
            "total_pages": total_pages,
            "stage": stage,
            "status": "processing"
        }

        await self._broadcast_event("document_progress", event_data)

    async def emit_error(
        self,
        job_id: str,
        error_message: str,
        is_batch: bool = False,
        batch_job_id: Optional[str] = None
    ) -> None:
        """
        Emit error event.

        Args:
            job_id: Job identifier (can be None for batch-level errors)
            error_message: Error message
            is_batch: Whether this is a batch-level error
            batch_job_id: Batch job ID if applicable
        """
        event_data = {
            "job_id": job_id if not is_batch else None,
            "batch_job_id": batch_job_id,
            "error_message": error_message,
            "error_type": "batch_error" if is_batch else "processing_error",
            "recoverable": False
        }

        await self._broadcast_event("error", event_data)

    async def emit_completion(
        self,
        job_id: str,
        is_batch: bool = False,
        batch_stats: Optional[Dict[str, Any]] = None
    ) -> None:
        """
        Emit completion event.

        Args:
            job_id: Job or batch job identifier
            is_batch: Whether this is a batch completion
            batch_stats: Batch statistics if applicable
        """
        if is_batch and batch_stats:
            event_data = {
                "batch_job_id": job_id,
                **batch_stats
            }
            await self._broadcast_event("batch_complete", event_data)
        else:
            event_data = {
                "job_id": job_id,
                "status": "completed"
            }
            await self._broadcast_event("job_complete", event_data)

    async def _broadcast_event(self, event_type: str, data: Dict[str, Any]) -> None:
        """
        Broadcast event to all connected clients.

        Args:
            event_type: Type of event
            data: Event data
        """
        async with self.lock:
            # Create SSE formatted message
            message = {
                "event": event_type,
                "data": data
            }

            # Send to all connected clients
            dead_connections = []
            for conn_id, queue in self.connections.items():
                try:
                    # Non-blocking put with timeout
                    await asyncio.wait_for(
                        queue.put(message),
                        timeout=0.1
                    )
                except asyncio.TimeoutError:
                    logger.warning(f"Connection {conn_id} queue full, skipping event")
                except Exception as e:
                    logger.error(f"Error sending to connection {conn_id}: {e}")
                    dead_connections.append(conn_id)

            # Remove dead connections
            for conn_id in dead_connections:
                del self.connections[conn_id]
                logger.info(f"Removed dead connection: {conn_id}")
