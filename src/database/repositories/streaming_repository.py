"""
Phase 4: Repository for single mutable row streaming.

Replaces append-only streaming_tokens with single mutable streams table.
Each (job_id, page_num) has exactly one row that gets updated in-place.
"""
import logging
from typing import Optional
from uuid import UUID

from supabase import AsyncClient

logger = logging.getLogger(__name__)


class StreamingRepository:
    """Repository for managing single mutable row streams in the database."""

    def __init__(self, supabase_client: AsyncClient):
        """
        Initialize repository.

        Args:
            supabase_client: Async Supabase client
        """
        self.supabase = supabase_client

    async def create_stream(
        self,
        job_id: UUID,
        page_num: int,
        stage: str = 'ocr'
    ) -> None:
        """
        Create initial stream row for a page.

        Args:
            job_id: Job UUID
            page_num: Page number (1-indexed)
            stage: Initial stage (default: 'ocr')

        Raises:
            Exception: If database write fails
        """
        try:
            await self.supabase.rpc(
                'mark_stream_stage',
                {
                    'p_job_id': str(job_id),
                    'p_page_num': page_num,
                    'p_stage': stage
                }
            ).execute()

            logger.debug(f"Created stream: job_id={job_id}, page={page_num}, stage={stage}")

        except Exception as e:
            logger.error(
                f"Failed to create stream: job_id={job_id}, page={page_num}, error={e}"
            )
            raise

    async def write_snapshot(
        self,
        job_id: UUID,
        page_num: int,
        snapshot_text: str,
        stage: str = 'merge',
        is_final: bool = False
    ) -> int:
        """
        Update stream with new snapshot text (throttled writes).

        Uses PostgreSQL function for atomic seq increment.

        Args:
            job_id: Job UUID
            page_num: Page number (1-indexed)
            snapshot_text: Accumulated text snapshot
            stage: Current stage (default: 'merge')
            is_final: Whether this is the final snapshot

        Returns:
            New sequence number

        Raises:
            Exception: If database write fails
        """
        try:
            response = await self.supabase.rpc(
                'update_stream_snapshot',
                {
                    'p_job_id': str(job_id),
                    'p_page_num': page_num,
                    'p_snapshot_text': snapshot_text,
                    'p_stage': stage,
                    'p_is_final': is_final
                }
            ).execute()

            # Extract seq from response
            seq = response.data if response.data else 0

            logger.debug(
                f"Updated stream snapshot: job_id={job_id}, page={page_num}, "
                f"seq={seq}, stage={stage}, is_final={is_final}, "
                f"text_length={len(snapshot_text)}"
            )

            return seq

        except Exception as e:
            logger.error(
                f"Failed to write snapshot: job_id={job_id}, page={page_num}, error={e}"
            )
            # Don't raise - streaming is non-critical
            # Job should continue even if snapshot write fails
            return 0

    async def mark_stage(
        self,
        job_id: UUID,
        page_num: int,
        stage: str
    ) -> None:
        """
        Transition stream to new stage without updating snapshot.

        Args:
            job_id: Job UUID
            page_num: Page number (1-indexed)
            stage: New stage ('ocr' | 'merge' | 'complete' | 'failed')

        Raises:
            Exception: If database write fails
        """
        try:
            await self.supabase.rpc(
                'mark_stream_stage',
                {
                    'p_job_id': str(job_id),
                    'p_page_num': page_num,
                    'p_stage': stage
                }
            ).execute()

            logger.debug(f"Marked stream stage: job_id={job_id}, page={page_num}, stage={stage}")

        except Exception as e:
            logger.error(
                f"Failed to mark stage: job_id={job_id}, page={page_num}, stage={stage}, error={e}"
            )
            # Don't raise - streaming is non-critical

    async def mark_complete(
        self,
        job_id: UUID,
        page_num: int,
        final_text: str
    ) -> None:
        """
        Mark stream as complete with final text.

        Args:
            job_id: Job UUID
            page_num: Page number (1-indexed)
            final_text: Final accumulated text

        Raises:
            Exception: If database write fails
        """
        try:
            await self.supabase.rpc(
                'mark_stream_complete',
                {
                    'p_job_id': str(job_id),
                    'p_page_num': page_num,
                    'p_final_text': final_text
                }
            ).execute()

            logger.debug(
                f"Marked stream complete: job_id={job_id}, page={page_num}, "
                f"text_length={len(final_text)}"
            )

        except Exception as e:
            logger.error(
                f"Failed to mark complete: job_id={job_id}, page={page_num}, error={e}"
            )
            # Don't raise - streaming is non-critical

    async def mark_failed(
        self,
        job_id: UUID,
        page_num: int,
        error: dict
    ) -> None:
        """
        Mark stream as failed with error details.

        Args:
            job_id: Job UUID
            page_num: Page number (1-indexed)
            error: Error details as dict (will be stored as JSONB)

        Raises:
            Exception: If database write fails
        """
        try:
            await self.supabase.rpc(
                'mark_stream_failed',
                {
                    'p_job_id': str(job_id),
                    'p_page_num': page_num,
                    'p_error': error
                }
            ).execute()

            logger.debug(
                f"Marked stream failed: job_id={job_id}, page={page_num}, error={error}"
            )

        except Exception as e:
            logger.error(
                f"Failed to mark failed: job_id={job_id}, page={page_num}, error={e}"
            )
            # Don't raise - streaming is non-critical

    async def get_stream(
        self,
        job_id: UUID,
        page_num: int
    ) -> Optional[dict]:
        """
        Get stream state for a specific page.

        Args:
            job_id: Job UUID
            page_num: Page number

        Returns:
            Stream record dict or None if not found
        """
        try:
            response = await self.supabase.table("streams") \
                .select("*") \
                .eq("job_id", str(job_id)) \
                .eq("page_num", page_num) \
                .maybe_single() \
                .execute()

            return response.data if response.data else None

        except Exception as e:
            logger.error(
                f"Failed to get stream: job_id={job_id}, page={page_num}, error={e}"
            )
            return None

    async def clear_job_streams(self, job_id: UUID) -> int:
        """
        Clear all streams for a job (cleanup on job completion).

        Args:
            job_id: Job UUID

        Returns:
            Number of streams deleted
        """
        try:
            response = await self.supabase.table("streams") \
                .delete() \
                .eq("job_id", str(job_id)) \
                .execute()

            count = len(response.data) if response.data else 0
            logger.info(f"Cleared {count} streams for job {job_id}")
            return count

        except Exception as e:
            logger.error(f"Failed to clear streams for job {job_id}: {e}")
            return 0
