"""File management API routes."""
import logging
from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form

from .models import FileMetadataResponse, FileDeleteResponse, DirectoryUploadResponse
from .services import FileManager

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/files", tags=["files"])


# Dependency injection
_file_manager: Optional[FileManager] = None


def set_file_manager(file_manager: FileManager):
    """Set file manager instance (called from main.py)."""
    global _file_manager
    _file_manager = file_manager


def get_file_manager() -> FileManager:
    """Get file manager instance."""
    if _file_manager is None:
        raise HTTPException(status_code=500, detail="FileManager not initialized")
    return _file_manager


@router.get("/{file_id}", response_model=FileMetadataResponse)
async def get_file_metadata(
    file_id: str,
    file_manager: FileManager = Depends(get_file_manager)
):
    """
    Get file metadata.

    Args:
        file_id: File ID

    Returns:
        FileMetadataResponse with file information
    """
    metadata = file_manager.get_file_info(file_id)

    return FileMetadataResponse(
        file_id=metadata.file_id,
        filename=metadata.filename,
        size_bytes=metadata.size_bytes,
        mime_type=metadata.mime_type,
        uploaded_at=metadata.uploaded_at,
        expires_at=metadata.expires_at,
        page_count=metadata.page_count,
    )


@router.delete("/{file_id}", response_model=FileDeleteResponse)
async def delete_file(
    file_id: str,
    file_manager: FileManager = Depends(get_file_manager)
):
    """
    Delete an uploaded file.

    Args:
        file_id: File ID

    Returns:
        FileDeleteResponse confirming deletion
    """
    # TODO: Check if file is being processed
    # For now, we just delete it
    file_manager.delete_file(file_id)

    return FileDeleteResponse(
        file_id=file_id,
        deleted=True
    )


@router.post("/directories/upload", response_model=DirectoryUploadResponse)
async def upload_directory(
    files: List[UploadFile] = File(...),
    directory_name: str = Form(...),
    file_manager: FileManager = Depends(get_file_manager)
):
    """
    Upload a directory of PDF files.

    Args:
        files: List of PDF files to upload
        directory_name: Name of the directory
        file_manager: FileManager instance

    Returns:
        DirectoryUploadResponse with directory information
    """
    try:
        # Upload directory
        directory_id, file_ids = await file_manager.upload_directory(files, directory_name)

        # Get directory info
        directory_info = file_manager.get_directory_info(directory_id)
        file_list = file_manager.get_directory_files(directory_id)

        return DirectoryUploadResponse(
            directory_id=directory_id,
            name=directory_info.name,
            file_count=len(file_list),
            total_size=directory_info.total_size,
            files=file_list
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to upload directory: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to upload directory: {str(e)}")
