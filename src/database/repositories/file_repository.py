"""Repository for file-related database operations."""
from typing import Any, Dict, List, Optional
from uuid import UUID
from datetime import datetime, timedelta
from supabase import Client
from .base_repository import BaseRepository
import logging

logger = logging.getLogger(__name__)


class FileRepository(BaseRepository):
    """Repository for files table."""

    def __init__(self, client: Client):
        """Initialize file repository.

        Args:
            client: Supabase client instance
        """
        super().__init__(client, "files")

    async def create_file(
        self,
        user_id: UUID,
        filename: str,
        content_type: str,
        size_bytes: int,
        storage_bucket: str,
        storage_path: str,
        file_id: Optional[UUID] = None,
        page_count: Optional[int] = None,
        expires_hours: int = 6,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Create a new file record.

        Args:
            user_id: User ID
            filename: Original filename
            content_type: MIME type
            size_bytes: File size in bytes
            storage_bucket: Supabase storage bucket name
            storage_path: Path within storage bucket
            file_id: Optional file_id (if not provided, database generates one)
            page_count: Number of pages (for PDFs)
            expires_hours: Hours until file expires
            metadata: Optional metadata dict

        Returns:
            Created file record
        """
        expires_at = datetime.now() + timedelta(hours=expires_hours)

        data = {
            "user_id": str(user_id),
            "filename": filename,
            "content_type": content_type,
            "size_bytes": size_bytes,
            "storage_bucket": storage_bucket,
            "storage_path": storage_path,
            "page_count": page_count,
            "expires_at": expires_at.isoformat(),
            "metadata": metadata or {},
        }

        # Include file_id if provided (for dual-write pattern)
        if file_id:
            data["file_id"] = str(file_id)

        return await self.create(data)

    async def get_file(self, file_id: UUID) -> Optional[Dict[str, Any]]:
        """Get file by ID.

        Args:
            file_id: File ID

        Returns:
            File record or None
        """
        return await self.get_by_id("file_id", str(file_id))

    async def get_file_by_storage_path(
        self, storage_path: str
    ) -> Optional[Dict[str, Any]]:
        """Get file by storage path.

        Args:
            storage_path: Storage path

        Returns:
            File record or None
        """
        result = (
            self.client.table(self.table_name)
            .select("*")
            .eq("storage_path", storage_path)
            .execute()
        )
        return result.data[0] if result.data else None

    async def soft_delete_file(self, file_id: UUID) -> Optional[Dict[str, Any]]:
        """Soft delete a file (set deleted_at timestamp).

        Args:
            file_id: File ID

        Returns:
            Updated file record
        """
        return await self.update(
            "file_id", str(file_id), {"deleted_at": datetime.now().isoformat()}
        )

    async def list_expired_files(self, limit: int = 100) -> List[Dict[str, Any]]:
        """List expired files for cleanup.

        Args:
            limit: Maximum number of files to return

        Returns:
            List of expired file records
        """
        result = (
            self.client.table(self.table_name)
            .select("*")
            .lt("expires_at", datetime.now().isoformat())
            .is_("deleted_at", "null")
            .limit(limit)
            .execute()
        )
        return result.data

    async def list_files_by_user(
        self, user_id: UUID, limit: int = 100
    ) -> List[Dict[str, Any]]:
        """List files for a user (non-deleted only).

        Args:
            user_id: User ID
            limit: Maximum number of files to return

        Returns:
            List of file records
        """
        result = (
            self.client.table(self.table_name)
            .select("*")
            .eq("user_id", str(user_id))
            .is_("deleted_at", "null")
            .order("uploaded_at", desc=True)
            .limit(limit)
            .execute()
        )
        return result.data
