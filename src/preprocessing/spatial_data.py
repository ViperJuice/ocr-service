"""Spatial data structures (legacy stubs for pdf_handler.py compatibility)."""
from dataclasses import dataclass
from typing import List, Dict, Any, Optional, Tuple


@dataclass
class BoundingBox:
    """Bounding box for text/objects in PDF."""
    x0: float
    y0: float
    x1: float
    y1: float
    page_width: float = 0.0
    page_height: float = 0.0


@dataclass
class TextBlock:
    """Text block with position and metadata."""
    text: str
    bbox: BoundingBox
    block_type: str = "text"
    font_size: float = 0.0
    font_name: str = ""
    is_embedded: bool = False


@dataclass
class PageStructure:
    """Page structure with text blocks and metadata."""
    page_number: int
    blocks: List[TextBlock]
    page_width: float
    page_height: float
    metadata: Dict[str, Any]
    embedded_text: str = ""
    has_embedded_text: bool = False


