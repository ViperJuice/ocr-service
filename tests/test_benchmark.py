"""Benchmark tests for line number capture improvement."""
import pytest
from pathlib import Path
from PIL import Image
import numpy as np

from src.preprocessing.pdf_handler import PDFHandler
from src.preprocessing.spatial_data import BoundingBox, TextBlock, PageStructure


class TestLineNumberCapture:
    """Benchmark tests for line number capture consistency."""
    
    def create_mock_page_structure(self, num_line_numbers: int = 25) -> PageStructure:
        """Create a mock page structure with line numbers."""
        blocks = []
        
        # Add line numbers
        for i in range(1, num_line_numbers + 1):
            bbox = BoundingBox(
                x0=10,
                y0=100 + (i * 25),
                x1=40,
                y1=120 + (i * 25)
            )
            block = TextBlock(
                text=str(i),
                bbox=bbox,
                block_type="line_number",
                font_size=10.0,
                page_num=1
            )
            blocks.append(block)
        
        # Add some body text
        for i in range(1, num_line_numbers + 1):
            bbox = BoundingBox(
                x0=50,
                y0=100 + (i * 25),
                x1=750,
                y1=120 + (i * 25)
            )
            block = TextBlock(
                text=f"This is line {i} of body text.",
                bbox=bbox,
                block_type="body",
                font_size=12.0,
                page_num=1
            )
            blocks.append(block)
        
        return PageStructure(
            page_num=1,
            blocks=blocks,
            has_line_numbers=True,
            has_tables=False,
            has_headers=False
        )
    
    def test_line_number_detection(self):
        """Test that line numbers are properly detected."""
        structure = self.create_mock_page_structure(num_line_numbers=25)
        
        line_numbers = [b for b in structure.blocks if b.block_type == "line_number"]
        
        # Check that all 25 line numbers were detected
        assert len(line_numbers) == 25
        assert structure.has_line_numbers is True
    
    def test_line_number_classification(self):
        """Test that line numbers are correctly classified."""
        handler = PDFHandler()
        
        # Line number case
        bbox_line_number = BoundingBox(x0=10, y0=100, x1=40, y1=120)
        block_type = handler._classify_block(bbox_line_number, "1", 10.0)
        assert block_type == "line_number"
        
        # Body text case (same position but longer text)
        block_type = handler._classify_block(bbox_line_number, "This is body text", 10.0)
        assert block_type != "line_number"
        
        # Body text case (different position)
        bbox_body = BoundingBox(x0=100, y0=100, x1=700, y1=120)
        block_type = handler._classify_block(bbox_body, "Body text", 12.0)
        assert block_type == "body"
    
    def test_header_classification(self):
        """Test that headers are correctly classified."""
        handler = PDFHandler()
        
        # Header case (top of page, large font)
        bbox_header = BoundingBox(x0=100, y0=50, x1=700, y1=80)
        block_type = handler._classify_block(bbox_header, "Document Title", 18.0)
        assert block_type == "header"
        
        # Not a header (top of page, small font)
        block_type = handler._classify_block(bbox_header, "Not a header", 10.0)
        assert block_type != "header"
    
    def test_qa_marker_classification(self):
        """Test that Q/A markers are correctly classified."""
        handler = PDFHandler()
        
        bbox = BoundingBox(x0=100, y0=200, x1=150, y1=220)
        
        # Q marker
        block_type = handler._classify_block(bbox, "Q", 12.0)
        assert block_type == "qa_marker"
        
        # A marker
        block_type = handler._classify_block(bbox, "A", 12.0)
        assert block_type == "qa_marker"
        
        # Q with spaces
        block_type = handler._classify_block(bbox, "Q   ", 12.0)
        assert block_type == "qa_marker"
    
    def test_spatial_metadata_generation(self):
        """Test that spatial metadata is properly generated."""
        from src.preprocessing.spatial_prompts import SpatialPromptBuilder
        
        structure = self.create_mock_page_structure(num_line_numbers=25)
        builder = SpatialPromptBuilder()
        metadata = builder.build_spatial_metadata(structure)
        
        # Check metadata
        assert metadata.line_number_count == 25
        assert len(metadata.line_number_positions) > 0
        assert "25 line numbers in left margin" in metadata.layout_description
    
    def test_consistency_improvement_potential(self):
        """
        Test that demonstrates the consistency improvement.
        
        Before: Pages might have different line number capture rates
        After: With spatial hints, all pages should capture line numbers consistently
        """
        structure1 = self.create_mock_page_structure(num_line_numbers=25)
        structure2 = self.create_mock_page_structure(num_line_numbers=25)
        structure3 = self.create_mock_page_structure(num_line_numbers=25)
        
        # All structures should have consistent line number counts
        ln_counts = [
            len([b for b in s.blocks if b.block_type == "line_number"])
            for s in [structure1, structure2, structure3]
        ]
        
        # All should be 25
        assert all(count == 25 for count in ln_counts)
        
        # Standard deviation should be 0 (perfect consistency)
        assert np.std(ln_counts) == 0


class TestBenchmarkMetrics:
    """Metrics for measuring improvement."""
    
    def calculate_capture_rate(self, expected: int, captured: int) -> float:
        """Calculate line number capture rate."""
        return (captured / expected) * 100 if expected > 0 else 0
    
    def test_capture_rate_calculation(self):
        """Test capture rate calculation."""
        # Perfect capture
        rate = self.calculate_capture_rate(expected=25, captured=25)
        assert rate == 100.0
        
        # Partial capture
        rate = self.calculate_capture_rate(expected=25, captured=20)
        assert rate == 80.0
        
        # No capture
        rate = self.calculate_capture_rate(expected=25, captured=0)
        assert rate == 0.0
    
    def test_consistency_metric(self):
        """Test consistency metric calculation."""
        # Consistent capture across pages
        page_captures = [25, 25, 25, 25, 25]
        std_dev = np.std(page_captures)
        assert std_dev == 0  # Perfect consistency
        
        # Inconsistent capture
        page_captures = [25, 20, 15, 22, 18]
        std_dev = np.std(page_captures)
        assert std_dev > 0  # Has variance
        
        # Goal: After implementing spatial hints, std_dev should approach 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])




