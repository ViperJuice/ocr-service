"""Intermediate result caching for staged pipeline."""
from pathlib import Path
from typing import Optional, Dict, Any, List
import json
from dataclasses import dataclass, asdict
import logging

logger = logging.getLogger(__name__)


@dataclass
class OCRPageResult:
    """OCR result for a single page."""
    page_num: int
    ocr_text: str
    method: str  # "embedded", "ocr", "hybrid"
    processing_time: float
    metadata: Dict[str, Any]  # model_used, resolution_mode, crop_mode, etc.


class IntermediateCache:
    """Manages intermediate results between pipeline stages."""

    def __init__(self, cache_dir: Path):
        """
        Initialize intermediate cache.

        Args:
            cache_dir: Directory to store intermediate results
        """
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def save_ocr_result(self, page_num: int, result: OCRPageResult) -> None:
        """
        Save OCR result for a single page.

        Args:
            page_num: Page number (0-indexed)
            result: OCR result object
        """
        page_file = self.cache_dir / f"page_{page_num:04d}.json"

        data = {
            'page_num': result.page_num,
            'ocr_text': result.ocr_text,
            'method': result.method,
            'processing_time': result.processing_time,
            'metadata': result.metadata
        }

        # Atomic write
        temp_file = page_file.with_suffix('.tmp')
        try:
            with open(temp_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2)
                f.flush()

            temp_file.replace(page_file)
        except IOError as e:
            logger.error(f"Failed to save OCR result for page {page_num}: {e}")
            if temp_file.exists():
                temp_file.unlink()

    def load_ocr_result(self, page_num: int) -> Optional[OCRPageResult]:
        """
        Load OCR result for a single page.

        Args:
            page_num: Page number (0-indexed)

        Returns:
            OCRPageResult or None if not found
        """
        page_file = self.cache_dir / f"page_{page_num:04d}.json"

        if not page_file.exists():
            return None

        try:
            with open(page_file, 'r', encoding='utf-8') as f:
                data = json.load(f)

            return OCRPageResult(
                page_num=data['page_num'],
                ocr_text=data['ocr_text'],
                method=data['method'],
                processing_time=data['processing_time'],
                metadata=data['metadata']
            )
        except (json.JSONDecodeError, KeyError, IOError) as e:
            logger.warning(f"Failed to load OCR result for page {page_num}: {e}")
            return None

    def list_completed_pages(self) -> List[int]:
        """
        List all page numbers with cached results.

        Returns:
            List of page numbers (0-indexed)
        """
        page_files = sorted(self.cache_dir.glob("page_*.json"))
        page_nums = []

        for page_file in page_files:
            # Extract page number from filename: page_0042.json -> 42
            try:
                page_num = int(page_file.stem.split('_')[1])
                page_nums.append(page_num)
            except (ValueError, IndexError):
                continue

        return page_nums

    def clear(self) -> None:
        """Delete all cached results."""
        import shutil
        if self.cache_dir.exists():
            try:
                shutil.rmtree(self.cache_dir)
                logger.info(f"Cleared intermediate cache: {self.cache_dir}")
            except OSError as e:
                logger.warning(f"Failed to clear cache: {e}")
