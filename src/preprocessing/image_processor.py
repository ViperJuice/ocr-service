"""Image preprocessing utilities."""
from typing import Tuple, Optional
from PIL import Image, ImageOps, ImageEnhance
import numpy as np


class ImageProcessor:
    """Image preprocessing for OCR optimization."""
    
    def __init__(
        self,
        max_size: int = 4096,
        auto_rotate: bool = True,
        auto_contrast: bool = False,
        enhance_contrast: float = 1.0,
    ):
        """
        Initialize image processor.
        
        Args:
            max_size: Maximum dimension (width or height)
            auto_rotate: Auto-correct image orientation
            auto_contrast: Apply auto-contrast enhancement
            enhance_contrast: Contrast enhancement factor (1.0 = no change)
        """
        self.max_size = max_size
        self.auto_rotate = auto_rotate
        self.auto_contrast = auto_contrast
        self.enhance_contrast = enhance_contrast
    
    def process(self, image: Image.Image) -> Image.Image:
        """
        Process image with configured settings.
        
        Args:
            image: Input PIL Image
            
        Returns:
            Processed PIL Image
        """
        # Convert to RGB if needed
        if image.mode not in ("RGB", "L"):
            image = image.convert("RGB")
        
        # Auto-rotate based on EXIF
        if self.auto_rotate:
            image = ImageOps.exif_transpose(image)
        
        # Resize if too large
        if max(image.size) > self.max_size:
            image = self._resize_image(image, self.max_size)
        
        # Apply auto-contrast
        if self.auto_contrast:
            image = ImageOps.autocontrast(image)
        
        # Apply contrast enhancement
        if self.enhance_contrast != 1.0:
            enhancer = ImageEnhance.Contrast(image)
            image = enhancer.enhance(self.enhance_contrast)
        
        return image
    
    @staticmethod
    def _resize_image(image: Image.Image, max_size: int) -> Image.Image:
        """
        Resize image maintaining aspect ratio.
        
        Args:
            image: Input image
            max_size: Maximum dimension
            
        Returns:
            Resized image
        """
        width, height = image.size
        
        if width > height:
            new_width = max_size
            new_height = int((max_size / width) * height)
        else:
            new_height = max_size
            new_width = int((max_size / height) * width)
        
        return image.resize((new_width, new_height), Image.Resampling.LANCZOS)
    
    @staticmethod
    def get_image_stats(image: Image.Image) -> dict:
        """
        Get image statistics.
        
        Args:
            image: PIL Image
            
        Returns:
            Dict with image statistics
        """
        arr = np.array(image)
        
        stats = {
            "size": image.size,
            "mode": image.mode,
            "format": image.format,
            "width": image.width,
            "height": image.height,
            "aspect_ratio": round(image.width / image.height, 2),
        }
        
        # Add array stats if possible
        if arr.size > 0:
            stats.update({
                "mean_intensity": float(arr.mean()),
                "std_intensity": float(arr.std()),
            })
        
        return stats


def preprocess_image(
    image: Image.Image,
    max_size: int = 4096,
    auto_rotate: bool = True,
    auto_contrast: bool = False,
    enhance_contrast: float = 1.0,
) -> Image.Image:
    """
    Preprocess a single image with default settings.
    
    Args:
        image: Input PIL Image
        max_size: Maximum dimension
        auto_rotate: Auto-correct orientation
        auto_contrast: Apply auto-contrast
        enhance_contrast: Contrast enhancement factor
        
    Returns:
        Processed PIL Image
    """
    processor = ImageProcessor(
        max_size=max_size,
        auto_rotate=auto_rotate,
        auto_contrast=auto_contrast,
        enhance_contrast=enhance_contrast,
    )
    return processor.process(image)

