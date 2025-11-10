"""Input validation utilities."""
from pathlib import Path
from typing import Tuple
from PIL import Image


class ValidationError(Exception):
    """Custom exception for validation errors."""
    pass


def validate_image(
    image: Image.Image,
    max_size: int = 4096,
    min_size: int = 32,
    allowed_modes: Tuple[str, ...] = ("RGB", "RGBA", "L", "P"),
) -> None:
    """
    Validate image meets requirements.
    
    Args:
        image: PIL Image to validate
        max_size: Maximum dimension allowed
        min_size: Minimum dimension allowed
        allowed_modes: Allowed image modes
        
    Raises:
        ValidationError: If validation fails
    """
    width, height = image.size
    
    # Check dimensions
    if width < min_size or height < min_size:
        raise ValidationError(
            f"Image too small: {width}x{height}. Minimum size is {min_size}x{min_size}"
        )
    
    if width > max_size or height > max_size:
        raise ValidationError(
            f"Image too large: {width}x{height}. Maximum size is {max_size}x{max_size}"
        )
    
    # Check mode
    if image.mode not in allowed_modes:
        raise ValidationError(
            f"Unsupported image mode: {image.mode}. Allowed modes: {allowed_modes}"
        )


def validate_file_size(
    file_path: Path,
    max_size_mb: int = 50,
) -> None:
    """
    Validate file size.
    
    Args:
        file_path: Path to file
        max_size_mb: Maximum file size in MB
        
    Raises:
        ValidationError: If file is too large
    """
    if not file_path.exists():
        raise ValidationError(f"File not found: {file_path}")
    
    size_mb = file_path.stat().st_size / (1024 * 1024)
    
    if size_mb > max_size_mb:
        raise ValidationError(
            f"File too large: {size_mb:.1f}MB. Maximum size is {max_size_mb}MB"
        )


def validate_file_extension(
    file_path: Path,
    allowed_extensions: Tuple[str, ...] = (".jpg", ".jpeg", ".png", ".pdf", ".tiff", ".tif"),
) -> None:
    """
    Validate file extension.
    
    Args:
        file_path: Path to file
        allowed_extensions: Allowed file extensions
        
    Raises:
        ValidationError: If extension not allowed
    """
    ext = file_path.suffix.lower()
    
    if ext not in allowed_extensions:
        raise ValidationError(
            f"Unsupported file type: {ext}. Allowed types: {allowed_extensions}"
        )

