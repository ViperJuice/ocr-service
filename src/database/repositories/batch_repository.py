"""Repository for batch job database operations."""
from typing import Any, Dict, List, Optional
from uuid import UUID
from datetime import datetime
from supabase import Client
from .base_repository import BaseRepository
import logging

logger = logging.getLogger(__name__)


class BatchRepository(BaseRepository):
    """Repository for batch_jobs table."""

    def __init__(self, client: Client):
        """Initialize batch repository.

        Args:
            client: Supabase client instance
        """
        super().__init__(client, "batch_jobs")

    async def create_batch_job(
        self,
        user_id: UUID,
        name: Optional[str],
        total_documents: int,
        model: str,
        prompt_type: str,
        custom_prompts: Optional[Dict[str, Any]],
        processing_options: Dict[str, Any],
        output_format: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Create a new batch job.

        Args:
            user_id: User ID
            name: Optional batch name
            total_documents: Total number of documents in batch
            model: Model to use
            prompt_type: Prompt type
            custom_prompts: Optional custom prompts
            processing_options: Processing options
            output_format: Output format
            metadata: Optional metadata

        Returns:
            Created batch job record
        """
        data = {
            "user_id": str(user_id),
            "name": name,
            "total_documents": total_documents,
            "model": model,
            "prompt_type": prompt_type,
            "custom_prompts": custom_prompts,
            "processing_options": processing_options,
            "output_format": output_format,
            "status": "queued",
            "metadata": metadata or {},
        }
        return await self.create(data)

    async def get_batch_job(self, batch_job_id: UUID) -> Optional[Dict[str, Any]]:
        """Get batch job by ID.

        Args:
            batch_job_id: Batch job ID

        Returns:
            Batch job record or None
        """
        return await self.get_by_id("batch_job_id", str(batch_job_id))

    async def update_batch_status(
        self,
        batch_job_id: UUID,
        status: str,
        error_message: Optional[str] = None,
        started_at: Optional[datetime] = None,
        completed_at: Optional[datetime] = None,
    ) -> Optional[Dict[str, Any]]:
        """Update batch job status.

        Args:
            batch_job_id: Batch job ID
            status: New status
            error_message: Optional error message
            started_at: Optional start timestamp
            completed_at: Optional completion timestamp

        Returns:
            Updated batch job record
        """
        data = {"status": status}
        if error_message is not None:
            data["error_message"] = error_message
        if started_at is not None:
            data["started_at"] = started_at.isoformat()
        if completed_at is not None:
            data["completed_at"] = completed_at.isoformat()

        return await self.update("batch_job_id", str(batch_job_id), data)

    async def update_batch_progress(
        self,
        batch_job_id: UUID,
        documents_completed: int,
        overall_progress_pct: float,
    ) -> Optional[Dict[str, Any]]:
        """Update batch job progress.

        Args:
            batch_job_id: Batch job ID
            documents_completed: Number of documents completed
            overall_progress_pct: Overall progress percentage (0-100)

        Returns:
            Updated batch job record
        """
        data = {
            "documents_completed": documents_completed,
            "overall_progress_pct": overall_progress_pct,
        }
        return await self.update("batch_job_id", str(batch_job_id), data)

    async def list_batch_jobs_by_user(
        self, user_id: UUID, limit: int = 100
    ) -> List[Dict[str, Any]]:
        """List batch jobs for a user.

        Args:
            user_id: User ID
            limit: Maximum number of batch jobs to return

        Returns:
            List of batch job records
        """
        return await self.list_all({"user_id": str(user_id)}, limit)

    async def get_batch_jobs_by_status(
        self, status: str, limit: int = 100
    ) -> List[Dict[str, Any]]:
        """Get batch jobs by status.

        Args:
            status: Status to filter by
            limit: Maximum number to return

        Returns:
            List of batch job records
        """
        return await self.list_all({"status": status}, limit)
