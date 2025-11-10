"""Root-level pytest fixtures shared across all test suites."""
import pytest
from pathlib import Path


@pytest.fixture(scope="session")
def test_data_dir() -> Path:
    """Path to test data directory."""
    return Path(__file__).parent / "api" / "fixtures"


@pytest.fixture(scope="session")
def sample_pdf_path(test_data_dir: Path) -> Path:
    """Path to sample PDF for testing."""
    return test_data_dir / "sample.pdf"


@pytest.fixture(scope="session")
def sample_image_path(test_data_dir: Path) -> Path:
    """Path to sample image for testing."""
    return test_data_dir / "sample.jpg"
