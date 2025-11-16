"""Repository for job-related database operations."""
from typing import Any, Dict, List, Optional
from uuid import UUID
from datetime import datetime
from supabase import Client
from .base_repository import BaseRepository
import asyncio
import logging

logger = logging.getLogger(__name__)


class JobRepository(BaseRepository):
    """Repository for jobs, page_results, and job_events tables."""

    def __init__(self, client: Client):
        """Initialize job repository.

        Args:
            client: Supabase client instance
        """
        super().__init__(client, "jobs")

    # ============================================
    # Jobs
    # ============================================

    async def create_job(
        self,
        job_id: UUID,
        user_id: UUID,
        file_id: UUID,
        filename: str,
        model: str,
        prompt_type: str,
        custom_prompts: Optional[Dict[str, Any]],
        processing_options: Dict[str, Any],
        output_format: str,
        parent_batch_id: Optional[UUID] = None,
    ) -> Dict[str, Any]:
        """Create a new job.

        Args:
            job_id: Job ID (must match in-memory job ID)
            user_id: User ID
            file_id: File ID
            filename: Original filename
            model: Model to use (deepseek-ocr, qwen3-vl, etc.)
            prompt_type: Prompt type (markdown, text, etc.)
            custom_prompts: Optional custom prompts dict
            processing_options: Processing options
            output_format: Output format
            parent_batch_id: Optional parent batch job ID

        Returns:
            Created job record
        """
        data = {
            "job_id": str(job_id),
            "user_id": str(user_id),
            "file_id": str(file_id),
            "filename": filename,
            "model": model,
            "prompt_type": prompt_type,
            "custom_prompts": custom_prompts,
            "processing_options": processing_options,
            "output_format": output_format,
            "status": "queued",
            "parent_batch_id": str(parent_batch_id) if parent_batch_id else None,
        }
        return await self.create(data)

    async def get_job(self, job_id: UUID) -> Optional[Dict[str, Any]]:
        """Get job by ID.

        Args:
            job_id: Job ID

        Returns:
            Job record or None
        """
        return await self.get_by_id("job_id", str(job_id))

    async def update_job_status(
        self,
        job_id: UUID,
        status: str,
        error_message: Optional[str] = None,
        started_at: Optional[datetime] = None,
        completed_at: Optional[datetime] = None,
    ) -> Optional[Dict[str, Any]]:
        """Update job status.

        Args:
            job_id: Job ID
            status: New status
            error_message: Optional error message
            started_at: Optional start timestamp
            completed_at: Optional completion timestamp

        Returns:
            Updated job record
        """
        data = {"status": status}
        if error_message is not None:
            data["error_message"] = error_message
        if started_at is not None:
            data["started_at"] = started_at.isoformat()
        if completed_at is not None:
            data["completed_at"] = completed_at.isoformat()

        return await self.update("job_id", str(job_id), data)

    async def update_job_progress(
        self,
        job_id: UUID,
        progress_pct: float,
        pages_completed: int,
        current_stage: Optional[str] = None,
        total_pages: Optional[int] = None,
    ) -> Optional[Dict[str, Any]]:
        """Update job progress.

        Args:
            job_id: Job ID
            progress_pct: Progress percentage (0-100)
            pages_completed: Number of pages completed
            current_stage: Current processing stage ('ocr' or 'merge')
            total_pages: Total number of pages

        Returns:
            Updated job record
        """
        data = {
            "progress_pct": progress_pct,
            "pages_completed": pages_completed,
        }
        if current_stage is not None:
            data["current_stage"] = current_stage
        if total_pages is not None:
            data["total_pages"] = total_pages

        return await self.update("job_id", str(job_id), data)

    async def update_job_result(
        self, job_id: UUID, result_path: str
    ) -> Optional[Dict[str, Any]]:
        """Update job result path.

        Args:
            job_id: Job ID
            result_path: Path to result file

        Returns:
            Updated job record
        """
        return await self.update("job_id", str(job_id), {"result_path": result_path})

    async def list_jobs_by_user(
        self, user_id: UUID, limit: int = 100
    ) -> List[Dict[str, Any]]:
        """List jobs for a user.

        Args:
            user_id: User ID
            limit: Maximum number of jobs to return

        Returns:
            List of job records
        """
        return await self.list_all({"user_id": str(user_id)}, limit)

    # ============================================
    # Page Results
    # ============================================

    async def create_page_result(
        self,
        job_id: UUID,
        page_num: int,
        ocr_text: Optional[str] = None,
        ocr_processing_time: Optional[float] = None,
        merge_text: Optional[str] = None,
        merge_processing_time: Optional[float] = None,
    ) -> Dict[str, Any]:
        """Create or update page result (upsert).

        Args:
            job_id: Job ID
            page_num: Page number (1-indexed)
            ocr_text: OCR extracted text
            ocr_processing_time: OCR processing time in seconds
            merge_text: Merge refined text
            merge_processing_time: Merge processing time in seconds

        Returns:
            Created/updated page result record
        """
        data = {
            "job_id": str(job_id),
            "page_num": page_num,
        }

        if ocr_text is not None:
            data["ocr_text"] = ocr_text
            data["ocr_completed_at"] = datetime.now().isoformat()
        if ocr_processing_time is not None:
            data["ocr_processing_time"] = ocr_processing_time

        if merge_text is not None:
            data["merge_text"] = merge_text
            data["merge_completed_at"] = datetime.now().isoformat()
        if merge_processing_time is not None:
            data["merge_processing_time"] = merge_processing_time

        # Upsert: update if exists, insert if not
        # Run blocking Supabase call in thread pool to avoid blocking event loop
        result = await asyncio.to_thread(
            lambda: (
                self.client.table("page_results")
                .upsert(data, on_conflict="job_id,page_num")
                .execute()
            )
        )
        return result.data[0] if result.data else None

    async def get_page_results(self, job_id: UUID) -> List[Dict[str, Any]]:
        """Get all page results for a job.

        Args:
            job_id: Job ID

        Returns:
            List of page result records ordered by page_num
        """
        # Run blocking Supabase call in thread pool to avoid blocking event loop
        result = await asyncio.to_thread(
            lambda: (
                self.client.table("page_results")
                .select("*")
                .eq("job_id", str(job_id))
                .order("page_num")
                .execute()
            )
        )
        return result.data

    # ============================================
    # Job Events
    # ============================================

    async def create_job_event(
        self,
        job_id: UUID,
        event_type: str,
        event_data: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Create a job event for audit trail.

        Args:
            job_id: Job ID
            event_type: Event type (e.g., 'job_created', 'ocr_page_completed')
            event_data: Event data as JSON

        Returns:
            Created event record

        Raises:
            Exception: If event creation fails (database error, FK violation, etc.)
        """
        data = {
            "job_id": str(job_id),
            "event_type": event_type,
            "event_data": event_data,
        }
        # Run blocking Supabase call in thread pool to avoid blocking event loop
        result = await asyncio.to_thread(
            lambda: self.client.table("job_events").insert(data).execute()
        )

        if not result.data:
            raise RuntimeError(f"Job event creation returned no data for job {job_id}, event {event_type}")

        return result.data[0]

    async def get_job_events(
        self, job_id: UUID, limit: int = 100
    ) -> List[Dict[str, Any]]:
        """Get job events for audit trail.

        Args:
            job_id: Job ID
            limit: Maximum number of events to return

        Returns:
            List of event records ordered by created_at
        """
        # Run blocking Supabase call in thread pool to avoid blocking event loop
        result = await asyncio.to_thread(
            lambda: (
                self.client.table("job_events")
                .select("*")
                .eq("job_id", str(job_id))
                .order("created_at", desc=False)
                .limit(limit)
                .execute()
            )
        )
        return result.data
