"""File upload and storage management service."""
import uuid
import shutil
import json
import logging
import mimetypes
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional
from dataclasses import dataclass, asdict

from fastapi import UploadFile, HTTPException

logger = logging.getLogger(__name__)


@dataclass
class FileMetadata:
    """Metadata for uploaded file."""
    file_id: str
    filename: str
    size_bytes: int
    mime_type: str
    uploaded_at: datetime
    expires_at: datetime
    storage_path: Path
    page_count: Optional[int] = None

    def to_dict(self):
        """Convert to dictionary with Path as string."""
        data = asdict(self)
        data['storage_path'] = str(data['storage_path'])
        data['uploaded_at'] = data['uploaded_at'].isoformat()
        data['expires_at'] = data['expires_at'].isoformat()
        return data

    @classmethod
    def from_dict(cls, data: dict):
        """Create from dictionary."""
        data = data.copy()
        data['storage_path'] = Path(data['storage_path'])
        data['uploaded_at'] = datetime.fromisoformat(data['uploaded_at'])
        data['expires_at'] = datetime.fromisoformat(data['expires_at'])
        return cls(**data)


@dataclass
class Directory:
    """Directory metadata."""
    directory_id: str
    name: str
    file_ids: list
    total_size: int
    uploaded_at: datetime

    def to_dict(self):
        """Convert to dictionary."""
        data = asdict(self)
        data['uploaded_at'] = data['uploaded_at'].isoformat()
        return data

    @classmethod
    def from_dict(cls, data: dict):
        """Create from dictionary."""
        data = data.copy()
        data['uploaded_at'] = datetime.fromisoformat(data['uploaded_at'])
        return cls(**data)


class FileManager:
    """Manage file uploads and temporary storage."""

    def __init__(self, temp_directory: str, expiry_hours: int = 6):
        """
        Initialize file manager.

        Args:
            temp_directory: Directory for temporary file storage
            expiry_hours: Hours until files expire
        """
        self.temp_directory = Path(temp_directory)
        self.expiry_hours = expiry_hours
        self.temp_directory.mkdir(parents=True, exist_ok=True)

        # In-memory directory registry
        self.directories: dict = {}

        logger.info(f"FileManager initialized: {self.temp_directory}")

    async def save_upload(self, file: UploadFile) -> FileMetadata:
        """
        Save uploaded file to temporary storage.

        Args:
            file: FastAPI UploadFile object

        Returns:
            FileMetadata object with file information

        Raises:
            HTTPException: If file is invalid or save fails
        """
        # Generate unique file ID
        file_id = str(uuid.uuid4())

        # Validate file type
        if not file.filename:
            raise HTTPException(status_code=400, detail="Filename is required")

        mime_type = file.content_type or mimetypes.guess_type(file.filename)[0] or "application/octet-stream"

        # Validate allowed types (PDF and images)
        allowed_types = [
            "application/pdf",
            "image/png",
            "image/jpeg",
            "image/jpg",
            "image/tiff",
            "image/bmp",
        ]

        if mime_type not in allowed_types:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid file type: {mime_type}. Allowed types: PDF, PNG, JPEG, TIFF, BMP"
            )

        # Create file-specific directory
        file_dir = self.temp_directory / file_id
        file_dir.mkdir(parents=True, exist_ok=True)

        # Save original file
        storage_path = file_dir / "original"
        try:
            with open(storage_path, "wb") as f:
                content = await file.read()
                f.write(content)
                size_bytes = len(content)
        except Exception as e:
            logger.error(f"Failed to save file {file_id}: {e}")
            # Cleanup on error
            if file_dir.exists():
                shutil.rmtree(file_dir)
            raise HTTPException(status_code=500, detail=f"Failed to save file: {e}")

        # Calculate timestamps
        uploaded_at = datetime.utcnow()
        expires_at = uploaded_at + timedelta(hours=self.expiry_hours)

        # Get page count for PDFs
        page_count = None
        if mime_type == "application/pdf":
            try:
                page_count = self._get_pdf_page_count(storage_path)
            except Exception as e:
                logger.warning(f"Failed to get page count for {file_id}: {e}")

        # Create metadata
        metadata = FileMetadata(
            file_id=file_id,
            filename=file.filename,
            size_bytes=size_bytes,
            mime_type=mime_type,
            uploaded_at=uploaded_at,
            expires_at=expires_at,
            storage_path=storage_path,
            page_count=page_count,
        )

        # Save metadata to file
        metadata_path = file_dir / "metadata.json"
        with open(metadata_path, "w") as f:
            json.dump(metadata.to_dict(), f, indent=2)

        logger.info(f"File uploaded: {file_id} ({file.filename}, {size_bytes} bytes)")
        return metadata

    def get_file_info(self, file_id: str) -> FileMetadata:
        """
        Retrieve file metadata.

        Args:
            file_id: File ID

        Returns:
            FileMetadata object

        Raises:
            HTTPException: If file not found
        """
        file_dir = self.temp_directory / file_id
        metadata_path = file_dir / "metadata.json"

        if not metadata_path.exists():
            raise HTTPException(status_code=404, detail=f"File not found: {file_id}")

        try:
            with open(metadata_path, "r") as f:
                data = json.load(f)
            metadata = FileMetadata.from_dict(data)

            # Check if file has expired
            if datetime.utcnow() > metadata.expires_at:
                logger.info(f"File expired: {file_id}")
                raise HTTPException(status_code=404, detail=f"File expired: {file_id}")

            # Verify file still exists
            if not metadata.storage_path.exists():
                raise HTTPException(status_code=404, detail=f"File data missing: {file_id}")

            return metadata
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse metadata for {file_id}: {e}")
            raise HTTPException(status_code=500, detail="Invalid metadata")

    def get_file_path(self, file_id: str) -> Path:
        """
        Get absolute path to uploaded file.

        Args:
            file_id: File ID

        Returns:
            Path to file

        Raises:
            HTTPException: If file not found
        """
        metadata = self.get_file_info(file_id)
        return metadata.storage_path

    def delete_file(self, file_id: str) -> bool:
        """
        Delete uploaded file and metadata.

        Args:
            file_id: File ID

        Returns:
            True if deleted successfully

        Raises:
            HTTPException: If file not found or deletion fails
        """
        file_dir = self.temp_directory / file_id

        if not file_dir.exists():
            raise HTTPException(status_code=404, detail=f"File not found: {file_id}")

        try:
            shutil.rmtree(file_dir)
            logger.info(f"File deleted: {file_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to delete file {file_id}: {e}")
            raise HTTPException(status_code=500, detail=f"Failed to delete file: {e}")

    def cleanup_expired_files(self) -> int:
        """
        Remove expired files from temporary storage.

        Returns:
            Count of files deleted
        """
        deleted_count = 0
        now = datetime.utcnow()

        for file_dir in self.temp_directory.iterdir():
            if not file_dir.is_dir():
                continue

            metadata_path = file_dir / "metadata.json"
            if not metadata_path.exists():
                continue

            try:
                with open(metadata_path, "r") as f:
                    data = json.load(f)
                metadata = FileMetadata.from_dict(data)

                if now > metadata.expires_at:
                    shutil.rmtree(file_dir)
                    deleted_count += 1
                    logger.info(f"Cleaned up expired file: {metadata.file_id}")
            except Exception as e:
                logger.error(f"Error cleaning up {file_dir}: {e}")

        if deleted_count > 0:
            logger.info(f"Cleanup complete: {deleted_count} expired files deleted")

        return deleted_count

    def _get_pdf_page_count(self, pdf_path: Path) -> int:
        """
        Get page count from PDF file.

        Args:
            pdf_path: Path to PDF file

        Returns:
            Number of pages
        """
        try:
            import fitz  # PyMuPDF
            with fitz.open(pdf_path) as doc:
                return len(doc)
        except Exception as e:
            logger.warning(f"Failed to get PDF page count: {e}")
            return 0

    async def upload_directory(
        self,
        files: list,
        directory_name: str
    ) -> tuple:
        """
        Upload a directory of PDF files.

        Args:
            files: List of UploadFile objects
            directory_name: Name of the directory

        Returns:
            Tuple of (directory_id, list of file_ids)

        Raises:
            HTTPException: If validation fails or upload fails
        """
        # Validate all files are PDFs
        validation_errors = self.validate_pdf_batch(files)
        if validation_errors:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid files in batch: {'; '.join(validation_errors)}"
            )

        # Generate directory ID
        directory_id = str(uuid.uuid4())

        # Upload all files
        file_ids = []
        total_size = 0

        for file in files:
            try:
                metadata = await self.save_upload(file)
                file_ids.append(metadata.file_id)
                total_size += metadata.size_bytes
            except Exception as e:
                # Cleanup already uploaded files on error
                for fid in file_ids:
                    try:
                        self.delete_file(fid)
                    except:
                        pass
                raise HTTPException(
                    status_code=500,
                    detail=f"Failed to upload directory: {e}"
                )

        # Create directory metadata
        directory = Directory(
            directory_id=directory_id,
            name=directory_name,
            file_ids=file_ids,
            total_size=total_size,
            uploaded_at=datetime.utcnow()
        )

        self.directories[directory_id] = directory

        logger.info(f"Directory uploaded: {directory_id} ({len(file_ids)} files, {total_size} bytes)")
        return directory_id, file_ids

    def get_directory_files(self, directory_id: str) -> list:
        """
        Get all files in a directory.

        Args:
            directory_id: Directory identifier

        Returns:
            List of file metadata dictionaries

        Raises:
            HTTPException: If directory not found
        """
        if directory_id not in self.directories:
            raise HTTPException(status_code=404, detail=f"Directory not found: {directory_id}")

        directory = self.directories[directory_id]
        files = []

        for file_id in directory.file_ids:
            try:
                metadata = self.get_file_info(file_id)
                files.append({
                    "file_id": metadata.file_id,
                    "filename": metadata.filename,
                    "size": metadata.size_bytes,
                    "page_count": metadata.page_count
                })
            except HTTPException:
                logger.warning(f"File in directory not found: {file_id}")
                continue

        return files

    def validate_pdf_batch(self, files: list) -> list:
        """
        Validate that all files are valid PDFs.

        Args:
            files: List of UploadFile objects

        Returns:
            List of error messages (empty if all valid)
        """
        errors = []

        for file in files:
            if not file.filename:
                errors.append(f"File has no filename")
                continue

            mime_type = file.content_type or mimetypes.guess_type(file.filename)[0]

            if mime_type != "application/pdf" and not file.filename.lower().endswith('.pdf'):
                errors.append(f"{file.filename}: Not a PDF file (type: {mime_type})")

        return errors

    def get_directory_info(self, directory_id: str) -> Directory:
        """
        Get directory metadata.

        Args:
            directory_id: Directory identifier

        Returns:
            Directory object

        Raises:
            HTTPException: If directory not found
        """
        if directory_id not in self.directories:
            raise HTTPException(status_code=404, detail=f"Directory not found: {directory_id}")

        return self.directories[directory_id]
