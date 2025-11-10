"""Pytest fixtures for API tests."""
import pytest
from pathlib import Path
from unittest.mock import Mock, AsyncMock
from httpx import AsyncClient
from typing import Dict, Any
import tempfile
import shutil
import io

from fastapi import UploadFile

from src.api.services.file_manager import FileManager
from src.api.services.prompt_manager import PromptManager
from src.api.services.job_manager import JobManager
# Don't import ModelManager directly to avoid heavy ML dependencies in tests
# from src.models.model_manager import ModelManager


@pytest.fixture
async def test_client(file_manager, prompt_manager, job_manager, mock_model_manager) -> AsyncClient:
    """Create FastAPI test client with mocked dependencies."""
    from httpx import ASGITransport
    from src.api.main import app
    from src.api import processing_routes, config_routes, file_routes

    # Set the managers in the route modules (simulating what lifespan does)
    processing_routes.set_managers(file_manager, prompt_manager, job_manager, mock_model_manager)
    config_routes.set_prompt_manager(prompt_manager)
    file_routes.set_file_manager(file_manager)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client


@pytest.fixture
def temp_storage_dir():
    """Create temporary storage directory for tests."""
    temp_dir = tempfile.mkdtemp()
    yield Path(temp_dir)
    shutil.rmtree(temp_dir)


@pytest.fixture
def file_manager(temp_storage_dir: Path) -> FileManager:
    """Create FileManager instance with temporary storage."""
    return FileManager(
        temp_directory=str(temp_storage_dir / "temp"),
        expiry_hours=6  # Longer expiry for testing
    )


@pytest.fixture
def prompt_manager() -> PromptManager:
    """Create PromptManager instance."""
    # Use the actual config path
    config_path = Path(__file__).parent.parent.parent / "config" / "model_configs.yaml"
    return PromptManager(model_configs_path=config_path)


@pytest.fixture
def job_manager(temp_storage_dir: Path) -> JobManager:
    """Create JobManager instance."""
    return JobManager(
        processing_directory=str(temp_storage_dir / "processing"),
        output_directory=str(temp_storage_dir / "output"),
        max_concurrent_jobs=2
    )


@pytest.fixture
def mock_model_manager():
    """Create mock ModelManager for testing without loading actual models."""
    mock = Mock()  # Don't use spec= to avoid importing ModelManager

    # Mock model_configs
    mock.model_configs = {
        "deepseek-ocr": {
            "model_id": "deepseek-ocr",
            "name": "DeepSeek-OCR",
            "capabilities": ["ocr"],
            "default": True
        },
        "qwen2-vl-7b": {
            "model_id": "qwen2-vl-7b",
            "name": "Qwen2-VL 7B",
            "capabilities": ["ocr", "markdown", "merge"],
            "default": False
        }
    }

    # Mock get_model method
    mock_model = Mock()
    mock_model.process_image = AsyncMock(return_value=Mock(
        ocr_text="Sample OCR text",
        confidence=0.95,
        processing_time=1.5
    ))
    mock_model.merge_texts = AsyncMock(return_value=Mock(
        ocr_text="Merged text",
        confidence=0.96,
        processing_time=2.0
    ))
    mock.get_model = Mock(return_value=mock_model)

    return mock


@pytest.fixture
def sample_file_metadata() -> Dict[str, Any]:
    """Sample file metadata for testing."""
    return {
        "file_id": "test-file-123",
        "filename": "sample.pdf",
        "size_bytes": 102400,
        "mime_type": "application/pdf",
        "page_count": 5,
        "uploaded_at": "2025-01-08T12:00:00Z",
        "expires_at": "2025-01-08T18:00:00Z"
    }


@pytest.fixture
def sample_job_data() -> Dict[str, Any]:
    """Sample job data for testing."""
    return {
        "file_id": "test-file-123",
        "model": "deepseek-ocr",
        "output_format": "markdown",
        "processing_options": {
            "dpi": 300,
            "method": "auto",
            "prefer_quality": True
        }
    }


def create_mock_upload_file(content: bytes, filename: str, content_type: str) -> UploadFile:
    """Helper to create mock UploadFile for testing."""
    from starlette.datastructures import Headers
    headers = Headers({"content-type": content_type})
    upload_file = UploadFile(
        file=io.BytesIO(content),
        filename=filename,
        headers=headers
    )
    # FastAPI also expects content_type attribute
    return upload_file


@pytest.fixture
async def uploaded_file_id(test_client, sample_pdf_path) -> str:
    """Upload a file and return its file_id for testing."""
    with open(sample_pdf_path, 'rb') as f:
        response = await test_client.post(
            "/api/v1/process/upload",
            files={"file": ("test.pdf", f, "application/pdf")}
        )
    assert response.status_code == 201
    return response.json()["file_id"]


@pytest.fixture
async def queued_job_id(test_client, uploaded_file_id) -> str:
    """Submit a job and return its job_id for testing."""
    response = await test_client.post(
        "/api/v1/process/jobs",
        json={
            "file_id": uploaded_file_id,
            "model": "deepseek-ocr",
            "output_format": "markdown"
        }
    )
    assert response.status_code == 202
    return response.json()["job_id"]
