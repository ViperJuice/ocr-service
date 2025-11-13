"""Shared types for OCR models and processing."""
from dataclasses import dataclass, field
from typing import Optional, Dict, Any


@dataclass
class OCRResult:
    """OCR result with metadata."""

    text: str
    model_name: str
    processing_time: float
    format: str = "text"
    confidence: Optional[float] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "text": self.text,
            "model_name": self.model_name,
            "processing_time": self.processing_time,
            "format": self.format,
            "confidence": self.confidence,
            "metadata": self.metadata,
        }
