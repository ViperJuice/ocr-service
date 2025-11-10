"""Checkpoint manager for PDF processing with resume capability."""

import json
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict, Any
import logging

logger = logging.getLogger(__name__)


class CheckpointManager:
    """Manages checkpoints for resumable PDF processing with stage support."""

    def __init__(self, output_path: Path, pdf_path: Path, processing_params: Dict[str, Any]):
        """
        Initialize checkpoint manager.

        Args:
            output_path: Path to the output file
            pdf_path: Path to the input PDF
            processing_params: Dict of processing parameters (dpi, method, model, etc.)
        """
        self.output_path = Path(output_path)
        self.pdf_path = Path(pdf_path)
        self.processing_params = processing_params
        self.checkpoint_path = self.output_path.with_suffix('.checkpoint.json')
        self.start_time = datetime.utcnow().isoformat() + 'Z'
        self._checkpoint_data: Optional[Dict[str, Any]] = None

    def load(self) -> Optional[Dict[str, Any]]:
        """
        Load existing checkpoint if it exists and is valid.

        Returns:
            Checkpoint data dict if valid checkpoint exists, None otherwise
        """
        if not self.checkpoint_path.exists():
            return None

        try:
            with open(self.checkpoint_path, 'r') as f:
                checkpoint = json.load(f)

            # Validate checkpoint
            if not self._validate_checkpoint(checkpoint):
                logger.warning(f"Invalid checkpoint found at {self.checkpoint_path}, ignoring")
                return None

            # Log appropriate message based on checkpoint type
            if 'current_stage' in checkpoint:
                # Staged checkpoint
                stage = checkpoint['current_stage']
                logger.info(f"Loaded staged checkpoint: current stage={stage}")
            elif 'last_completed_page' in checkpoint:
                # Legacy checkpoint
                logger.info(f"Loaded checkpoint: {checkpoint['last_completed_page']} pages completed")
            else:
                logger.info("Loaded checkpoint")

            return checkpoint

        except (json.JSONDecodeError, IOError) as e:
            logger.warning(f"Failed to load checkpoint: {e}")
            return None
        except KeyError as e:
            logger.warning(f"Checkpoint missing expected field: {e}")
            return None

    def _validate_checkpoint(self, checkpoint: Dict[str, Any]) -> bool:
        """
        Validate that checkpoint is compatible with current processing.

        Args:
            checkpoint: Checkpoint data dict

        Returns:
            True if checkpoint is valid and compatible
        """
        # Check for staged pipeline format
        is_staged = 'current_stage' in checkpoint or 'stage_progress' in checkpoint

        if is_staged:
            # Validate staged checkpoint format
            required_fields = ['pdf_path', 'output_path', 'current_stage', 'stage_progress', 'processing_params']
            if not all(field in checkpoint for field in required_fields):
                logger.warning("Staged checkpoint missing required fields")
                return False

            # Validate current_stage value
            valid_stages = ['ocr', 'merge', 'completed']
            if checkpoint['current_stage'] not in valid_stages:
                logger.warning(f"Invalid current_stage: {checkpoint['current_stage']}")
                return False

            # Validate stage_progress structure
            if not isinstance(checkpoint['stage_progress'], dict):
                logger.warning("stage_progress must be a dict")
                return False

            # If resuming merge stage, check OCR cache exists
            if checkpoint['current_stage'] == 'merge':
                if 'intermediate_cache' in checkpoint:
                    cache_dir = Path(checkpoint['intermediate_cache'].get('ocr_results_dir', ''))
                    if not cache_dir.exists():
                        logger.warning(f"OCR cache directory not found: {cache_dir}")
                        return False
        else:
            # Validate legacy checkpoint format
            required_fields = ['pdf_path', 'output_path', 'last_completed_page', 'processing_params']
            if not all(field in checkpoint for field in required_fields):
                logger.warning("Checkpoint missing required fields")
                return False

            # Check that partial output file exists for legacy checkpoints
            if not self.output_path.exists():
                logger.warning(f"Checkpoint exists but output file not found: {self.output_path}")
                return False

        # Check PDF path matches
        if checkpoint['pdf_path'] != str(self.pdf_path):
            logger.warning(f"Checkpoint PDF path mismatch: {checkpoint['pdf_path']} != {self.pdf_path}")
            return False

        # Check output path matches
        if checkpoint['output_path'] != str(self.output_path):
            logger.warning(f"Checkpoint output path mismatch: {checkpoint['output_path']} != {self.output_path}")
            return False

        # Check critical processing params match
        critical_params = ['dpi', 'method', 'format']
        for param in critical_params:
            if param in checkpoint['processing_params'] and param in self.processing_params:
                if checkpoint['processing_params'][param] != self.processing_params[param]:
                    logger.warning(f"Processing parameter mismatch: {param}")
                    return False

        return True

    def save(self, last_completed_page: int, total_pages: Optional[int] = None) -> None:
        """
        Save checkpoint after completing a page.

        Args:
            last_completed_page: Zero-indexed page number just completed
            total_pages: Total number of pages (optional)
        """
        checkpoint_data = {
            'pdf_path': str(self.pdf_path),
            'output_path': str(self.output_path),
            'total_pages': total_pages,
            'last_completed_page': last_completed_page,
            'start_time': self.start_time,
            'last_update': datetime.utcnow().isoformat() + 'Z',
            'processing_params': self.processing_params
        }

        try:
            # Write atomically using temp file
            temp_path = self.checkpoint_path.with_suffix('.checkpoint.tmp')
            with open(temp_path, 'w') as f:
                json.dump(checkpoint_data, f, indent=2)
                f.flush()

            # Atomic rename
            temp_path.replace(self.checkpoint_path)

        except IOError as e:
            logger.error(f"Failed to save checkpoint: {e}")

    def clear(self) -> None:
        """Delete checkpoint file on successful completion."""
        if self.checkpoint_path.exists():
            try:
                self.checkpoint_path.unlink()
                logger.info(f"Checkpoint cleared: {self.checkpoint_path}")
            except IOError as e:
                logger.warning(f"Failed to delete checkpoint: {e}")

    def get_resume_page(self) -> int:
        """
        Get the page number to resume from.

        Returns:
            Page number to start processing (0 = start from beginning)
        """
        checkpoint = self.load()
        if checkpoint is None:
            return 0

        # Resume from next page after last completed
        return checkpoint['last_completed_page'] + 1

    # ========== Stage-Aware Methods (New) ==========

    def save_stage_progress(
        self,
        stage_name: str,
        last_completed_page: int,
        total_pages: int,
        stage_metadata: Optional[Dict] = None
    ) -> None:
        """
        Save progress for a specific stage.

        Args:
            stage_name: "ocr" or "merge"
            last_completed_page: Zero-indexed page just completed
            total_pages: Total pages in document
            stage_metadata: Optional metadata (model_used, resolution_mode, etc.)
        """
        # Load existing checkpoint or create new
        if self._checkpoint_data is None:
            self._checkpoint_data = self.load()

        if self._checkpoint_data is None:
            # Initialize new staged checkpoint
            self._checkpoint_data = {
                'pdf_path': str(self.pdf_path),
                'output_path': str(self.output_path),
                'total_pages': total_pages,
                'current_stage': stage_name,
                'completed_stages': [],
                'stage_progress': {},
                'intermediate_cache': {},
                'start_time': self.start_time,
                'processing_params': self.processing_params
            }

        # Update stage progress
        if stage_name not in self._checkpoint_data['stage_progress']:
            self._checkpoint_data['stage_progress'][stage_name] = {
                'last_completed_page': -1,
                'total_pages': total_pages,
                'started_at': datetime.utcnow().isoformat() + 'Z',
                'completed_at': None
            }

        stage_data = self._checkpoint_data['stage_progress'][stage_name]
        stage_data['last_completed_page'] = last_completed_page
        stage_data['total_pages'] = total_pages

        # Add metadata if provided
        if stage_metadata:
            stage_data.update(stage_metadata)

        # Update current stage and last update time
        self._checkpoint_data['current_stage'] = stage_name
        self._checkpoint_data['last_update'] = datetime.utcnow().isoformat() + 'Z'

        # Write to disk
        self._write_checkpoint(self._checkpoint_data)

    def complete_stage(self, stage_name: str) -> None:
        """
        Mark a stage as completed.

        Args:
            stage_name: "ocr" or "merge"
        """
        if self._checkpoint_data is None:
            self._checkpoint_data = self.load()

        if self._checkpoint_data is None:
            logger.warning(f"Cannot complete stage {stage_name}: no checkpoint data")
            return

        # Mark stage as completed
        if stage_name in self._checkpoint_data['stage_progress']:
            self._checkpoint_data['stage_progress'][stage_name]['completed_at'] = \
                datetime.utcnow().isoformat() + 'Z'

        # Add to completed stages list
        if stage_name not in self._checkpoint_data['completed_stages']:
            self._checkpoint_data['completed_stages'].append(stage_name)

        # Update current stage to next stage
        if stage_name == 'ocr':
            self._checkpoint_data['current_stage'] = 'merge'
        elif stage_name == 'merge':
            self._checkpoint_data['current_stage'] = 'completed'

        self._checkpoint_data['last_update'] = datetime.utcnow().isoformat() + 'Z'

        # Write to disk
        self._write_checkpoint(self._checkpoint_data)

    def get_current_stage(self) -> str:
        """
        Get the current stage to process.

        Returns:
            "ocr", "merge", or "completed"
        """
        checkpoint = self.load()
        if checkpoint is None:
            return "ocr"  # Start from beginning

        # Check for staged checkpoint
        if 'current_stage' in checkpoint:
            return checkpoint['current_stage']

        # Legacy checkpoint - already completed or in progress
        return "ocr"

    def get_stage_resume_page(self, stage_name: str) -> int:
        """
        Get page number to resume from for a specific stage.

        Args:
            stage_name: "ocr" or "merge"

        Returns:
            Page number to start (0 = start from beginning)
        """
        checkpoint = self.load()
        if checkpoint is None:
            return 0

        # Check for staged checkpoint
        if 'stage_progress' not in checkpoint:
            return 0

        stage_data = checkpoint['stage_progress'].get(stage_name)
        if stage_data is None:
            return 0

        # Resume from next page after last completed
        last_completed = stage_data.get('last_completed_page', -1)
        return last_completed + 1

    def set_intermediate_cache_dir(self, cache_dir: Path) -> None:
        """
        Set directory for intermediate stage results.

        Args:
            cache_dir: Path to cache directory
        """
        if self._checkpoint_data is None:
            self._checkpoint_data = self.load()

        if self._checkpoint_data is None:
            # Initialize minimal checkpoint data
            self._checkpoint_data = {
                'pdf_path': str(self.pdf_path),
                'output_path': str(self.output_path),
                'current_stage': 'ocr',
                'completed_stages': [],
                'stage_progress': {},
                'intermediate_cache': {},
                'start_time': self.start_time,
                'processing_params': self.processing_params
            }

        self._checkpoint_data['intermediate_cache'] = {
            'ocr_results_dir': str(cache_dir),
            'format': 'json'
        }

    def get_intermediate_cache_dir(self) -> Optional[Path]:
        """
        Get directory for intermediate stage results.

        Returns:
            Path to cache directory or None
        """
        checkpoint = self.load()
        if checkpoint is None:
            return None

        cache_info = checkpoint.get('intermediate_cache')
        if cache_info is None:
            return None

        cache_dir = cache_info.get('ocr_results_dir')
        if cache_dir is None:
            return None

        return Path(cache_dir)

    def _write_checkpoint(self, data: Dict[str, Any]) -> None:
        """
        Write checkpoint data to disk atomically.

        Args:
            data: Checkpoint data to write
        """
        try:
            # Write atomically using temp file
            temp_path = self.checkpoint_path.with_suffix('.checkpoint.tmp')
            with open(temp_path, 'w') as f:
                json.dump(data, f, indent=2)
                f.flush()

            # Atomic rename
            temp_path.replace(self.checkpoint_path)

        except IOError as e:
            logger.error(f"Failed to write checkpoint: {e}")
