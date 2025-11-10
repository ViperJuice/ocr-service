"""PDF processing utilities."""
from typing import List, Optional, Tuple
from pathlib import Path
from PIL import Image
import fitz  # PyMuPDF

from .spatial_data import BoundingBox, TextBlock, PageStructure


class PDFHandler:
    """Handle PDF to image conversion and hybrid text extraction."""
    
    def __init__(
        self, 
        dpi: int = 300, 
        image_format: str = "PNG", 
        min_text_chars: int = 10,
        enable_dpi_fallback: bool = True,
        min_dpi: int = 72
    ):
        """
        Initialize PDF handler.
        
        Args:
            dpi: Resolution for image extraction
            image_format: Output image format
            min_text_chars: Minimum characters to consider page as having text
            enable_dpi_fallback: Enable automatic DPI reduction on OOM
            min_dpi: Minimum DPI for fallback (72 is PDF native)
        """
        self.dpi = dpi
        self.image_format = image_format
        self.min_text_chars = min_text_chars
        self.enable_dpi_fallback = enable_dpi_fallback
        self.min_dpi = min_dpi
    
    def extract_images(
        self,
        pdf_path: Path,
        max_pages: Optional[int] = None,
    ) -> List[Image.Image]:
        """
        Extract images from PDF pages.
        
        Args:
            pdf_path: Path to PDF file
            max_pages: Maximum number of pages to extract (None = all)
            
        Returns:
            List of PIL Images
        """
        images = []
        
        # Open PDF
        pdf_document = fitz.open(pdf_path)
        
        # Determine page range
        num_pages = len(pdf_document)
        pages_to_process = min(num_pages, max_pages) if max_pages else num_pages
        
        print(f"Extracting {pages_to_process} pages from PDF...")
        
        # Extract each page as image
        for page_num in range(pages_to_process):
            page = pdf_document[page_num]
            
            # Calculate zoom for desired DPI
            zoom = self.dpi / 72  # PDF default is 72 DPI
            mat = fitz.Matrix(zoom, zoom)
            
            # Render page to pixmap
            pix = page.get_pixmap(matrix=mat, alpha=False)
            
            # Convert to PIL Image
            img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
            images.append(img)
        
        pdf_document.close()
        
        print(f"✓ Extracted {len(images)} images from PDF")
        return images
    
    def get_pdf_info(self, pdf_path: Path) -> dict:
        """
        Get PDF metadata.
        
        Args:
            pdf_path: Path to PDF file
            
        Returns:
            Dict with PDF info
        """
        pdf_document = fitz.open(pdf_path)
        
        info = {
            "page_count": len(pdf_document),
            "metadata": pdf_document.metadata,
            "is_encrypted": pdf_document.is_encrypted,
            "is_pdf": pdf_document.is_pdf,
        }
        
        pdf_document.close()
        return info
    
    def has_embedded_text(self, page: fitz.Page, min_chars: Optional[int] = None) -> bool:
        """
        Check if page has embedded text.
        
        Args:
            page: PyMuPDF page object
            min_chars: Minimum characters (uses self.min_text_chars if None)
            
        Returns:
            True if page has sufficient embedded text
        """
        min_chars = min_chars if min_chars is not None else self.min_text_chars
        text = page.get_text().strip()
        return len(text) >= min_chars
    
    def extract_text_from_page(self, page: fitz.Page) -> str:
        """
        Extract embedded text from a page.
        
        Args:
            page: PyMuPDF page object
            
        Returns:
            Extracted text as string
        """
        return page.get_text()
    
    def process_page_hybrid(
        self, 
        page: fitz.Page, 
        page_num: int,
        dpi: Optional[int] = None
    ) -> Tuple[str, Image.Image, bool]:
        """
        Process a single page and return both text and image.
        
        Args:
            page: PyMuPDF page object
            page_num: Page number (for logging)
            dpi: DPI for image extraction (uses self.dpi if None)
            
        Returns:
            Tuple of (embedded_text, page_image, has_text)
        """
        dpi = dpi if dpi is not None else self.dpi
        
        # Check for embedded text
        has_text = self.has_embedded_text(page)
        embedded_text = self.extract_text_from_page(page) if has_text else ""
        
        # Always extract image for OCR
        zoom = dpi / 72  # PDF default is 72 DPI
        mat = fitz.Matrix(zoom, zoom)
        pix = page.get_pixmap(matrix=mat, alpha=False)
        image = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
        
        return embedded_text, image, has_text
    
    def extract_hybrid_data(
        self,
        pdf_path: Path,
        max_pages: Optional[int] = None,
        dpi: Optional[int] = None,
        start_page: Optional[int] = None,
        end_page: Optional[int] = None
    ) -> List[Tuple[str, Image.Image, bool]]:
        """
        Extract both embedded text and images from PDF pages.

        Args:
            pdf_path: Path to PDF file
            max_pages: Maximum number of pages to extract (None = all)
            dpi: DPI for image extraction (uses self.dpi if None)
            start_page: Starting page number (1-indexed, None = first page)
            end_page: Ending page number (1-indexed, None = last page)

        Returns:
            List of tuples: (embedded_text, page_image, has_text)
        """
        dpi = dpi if dpi is not None else self.dpi
        results = []

        # Open PDF
        pdf_document = fitz.open(pdf_path)

        # Determine page range
        num_pages = len(pdf_document)

        # Handle page range parameters (convert to 0-indexed)
        if start_page is not None and end_page is not None:
            # Use specified page range (convert from 1-indexed to 0-indexed)
            first_page = max(0, start_page - 1)
            last_page = min(num_pages - 1, end_page - 1)
            pages_to_process = range(first_page, last_page + 1)
            print(f"Extracting pages {start_page}-{end_page} (hybrid mode)...")
        elif max_pages is not None:
            # Use max_pages (legacy behavior)
            pages_count = min(num_pages, max_pages)
            pages_to_process = range(pages_count)
            print(f"Extracting {pages_count} pages (hybrid mode)...")
        else:
            # Process all pages
            pages_to_process = range(num_pages)
            print(f"Extracting {num_pages} pages (hybrid mode)...")

        # Process each page
        for page_num in pages_to_process:
            page = pdf_document[page_num]
            page_data = self.process_page_hybrid(page, page_num + 1, dpi)
            results.append(page_data)

        pdf_document.close()

        print(f"✓ Extracted {len(results)} pages with hybrid data")
        return results
    
    def resize_image_by_factor(
        self, 
        image: Image.Image, 
        scale_factor: float
    ) -> Image.Image:
        """
        Resize image by scale factor to reduce memory usage.
        
        Args:
            image: PIL Image to resize
            scale_factor: Scale factor (e.g., 0.5 for 50% size)
            
        Returns:
            Resized PIL Image
        """
        new_width = int(image.width * scale_factor)
        new_height = int(image.height * scale_factor)
        return image.resize((new_width, new_height), Image.LANCZOS)
    
    def get_fallback_dpi_sequence(self, start_dpi: int) -> List[int]:
        """
        Generate DPI fallback sequence for OOM recovery.
        
        Args:
            start_dpi: Starting DPI value
            
        Returns:
            List of DPI values in descending order
        """
        # Common DPI values for fallback
        standard_dpis = [300, 200, 150, 100, 72]
        
        # Filter to values <= start_dpi and >= min_dpi
        fallback_sequence = [
            dpi for dpi in standard_dpis 
            if dpi <= start_dpi and dpi >= self.min_dpi
        ]
        
        # Always include min_dpi as last resort
        if self.min_dpi not in fallback_sequence:
            fallback_sequence.append(self.min_dpi)
        
        return fallback_sequence
    
    def extract_structured_text(
        self, 
        page: fitz.Page, 
        image: Image.Image,
        page_num: int
    ) -> PageStructure:
        """
        Extract structured text with full spatial metadata.
        
        Uses PyMuPDF's get_text("dict") for complete structure.
        
        Args:
            page: PyMuPDF page object
            image: Rendered page image
            page_num: Page number
            
        Returns:
            PageStructure with classified blocks and metadata
        """
        # Get full structured data
        text_dict = page.get_text("dict")
        
        # Parse and classify blocks
        blocks = []
        for block in text_dict["blocks"]:
            if "lines" in block:
                for line in block["lines"]:
                    # Extract text and metadata
                    text = " ".join([span["text"] for span in line["spans"]])
                    bbox_pdf = line["bbox"]
                    
                    # Scale PDF coordinates to image coordinates
                    bbox_img = self._scale_bbox_to_image(bbox_pdf, page, image)
                    
                    # Get font info
                    font_size = line["spans"][0]["size"] if line["spans"] else 12.0
                    font_name = line["spans"][0]["font"] if line["spans"] else ""
                    
                    # Classify block type
                    block_type = self._classify_block(bbox_img, text, font_size)
                    
                    blocks.append(TextBlock(
                        text=text,
                        bbox=bbox_img,
                        block_type=block_type,
                        font_size=font_size,
                        font_name=font_name,
                        page_num=page_num
                    ))
        
        # Analyze structure
        structure = self._analyze_page_structure(blocks, page_num)
        structure.raw_digital_text = page.get_text()
        structure.image = image
        
        return structure
    
    def _scale_bbox_to_image(
        self, 
        pdf_bbox: Tuple[float, float, float, float],
        page: fitz.Page,
        image: Image.Image
    ) -> BoundingBox:
        """Scale PDF coordinates to image pixel coordinates."""
        page_rect = page.rect
        scale_x = image.width / page_rect.width
        scale_y = image.height / page_rect.height
        
        return BoundingBox(
            x0=pdf_bbox[0] * scale_x,
            y0=pdf_bbox[1] * scale_y,
            x1=pdf_bbox[2] * scale_x,
            y1=pdf_bbox[3] * scale_y
        )
    
    def _classify_block(
        self, 
        bbox: BoundingBox, 
        text: str, 
        font_size: float
    ) -> str:
        """Classify block type based on position and content."""
        # Left margin, short, numeric = line number
        if bbox.x0 < 50 and len(text.strip()) < 4 and text.strip().isdigit():
            try:
                num = int(text.strip())
                if 1 <= num <= 25:
                    return "line_number"
            except ValueError:
                pass
        
        # Top of page, large font = header
        if bbox.y0 < 100 and font_size > 14:
            return "header"
        
        # Q/A markers
        if text.strip() in ["Q", "A"] or text.startswith("Q   ") or text.startswith("A   "):
            return "qa_marker"
        
        # Footer indicators
        if bbox.y1 > 700:  # Near bottom
            return "footer"
        
        return "body"
    
    def _analyze_page_structure(
        self, 
        blocks: List[TextBlock], 
        page_num: int
    ) -> PageStructure:
        """Analyze overall page structure."""
        line_numbers = [b for b in blocks if b.block_type == "line_number"]
        headers = [b for b in blocks if b.block_type == "header"]
        
        return PageStructure(
            page_num=page_num,
            blocks=blocks,
            has_line_numbers=len(line_numbers) > 0,
            has_tables=False,  # TODO: Table detection
            has_headers=len(headers) > 0,
        )
    
    def extract_hybrid_data_structured(
        self,
        pdf_path: Path,
        max_pages: Optional[int] = None,
        dpi: Optional[int] = None
    ) -> List[PageStructure]:
        """
        Extract hybrid data with full structural information.
        
        Args:
            pdf_path: Path to PDF file
            max_pages: Maximum number of pages to extract (None = all)
            dpi: DPI for image extraction (uses self.dpi if None)
            
        Returns:
            List of PageStructure objects with full metadata
        """
        dpi = dpi if dpi is not None else self.dpi
        results = []
        
        pdf_document = fitz.open(pdf_path)
        num_pages = len(pdf_document)
        pages_to_process = min(num_pages, max_pages) if max_pages else num_pages
        
        print(f"Extracting {pages_to_process} pages (structured mode)...")
        
        for page_num in range(pages_to_process):
            page = pdf_document[page_num]
            
            # Render image
            zoom = dpi / 72
            mat = fitz.Matrix(zoom, zoom)
            pix = page.get_pixmap(matrix=mat, alpha=False)
            image = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
            
            # Extract structured data
            structure = self.extract_structured_text(page, image, page_num + 1)
            results.append(structure)
        
        pdf_document.close()
        
        print(f"✓ Extracted {len(results)} pages with structural data")
        return results


def extract_images_from_pdf(
    pdf_path: Path,
    dpi: int = 300,
    max_pages: Optional[int] = None,
) -> List[Image.Image]:
    """
    Extract images from PDF (convenience function).
    
    Args:
        pdf_path: Path to PDF file
        dpi: Resolution for extraction
        max_pages: Maximum pages to extract
        
    Returns:
        List of PIL Images
    """
    handler = PDFHandler(dpi=dpi)
    return handler.extract_images(pdf_path, max_pages=max_pages)

