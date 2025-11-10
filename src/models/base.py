"""Base class for vision-language models."""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional, Dict, Any, List
from pathlib import Path
from PIL import Image
import time


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


class BaseVLModel(ABC):
    """Abstract base class for vision-language models."""
    
    def __init__(
        self,
        model_id: str,
        config: Dict[str, Any],
        device_map: str = "auto",
    ):
        """
        Initialize the model.
        
        Args:
            model_id: HuggingFace model ID
            config: Model configuration dict
            device_map: Device mapping strategy
        """
        self.model_id = model_id
        self.config = config
        self.device_map = device_map
        self.model = None
        self.processor = None
        self.tokenizer = None
        self.is_loaded = False
        self._load_time: Optional[float] = None
    
    @abstractmethod
    def load(self) -> None:
        """Load the model and processor."""
        pass
    
    @abstractmethod
    def process_image(
        self,
        image: Image.Image,
        prompt_type: str = "ocr",
        prompts: Optional[Dict[str, str]] = None,
        **generation_kwargs
    ) -> OCRResult:
        """
        Process an image and extract text.

        Args:
            image: PIL Image
            prompt_type: Type of prompt to use (ocr, markdown, structured)
            prompts: Optional custom prompts to override defaults
            **generation_kwargs: Additional generation arguments

        Returns:
            OCRResult with extracted text and metadata
        """
        pass
    
    @abstractmethod
    def merge_texts(
        self,
        image: Image.Image,
        embedded_text: str,
        ocr_text: str,
        prompts: Optional[Dict[str, str]] = None,
        **generation_kwargs
    ) -> OCRResult:
        """
        Compare and merge embedded text and OCR text using the model.

        Uses the vision-language model to intelligently combine text extracted
        from PDF with OCR text from the rendered image, producing the most
        accurate result.

        Args:
            image: Original page image for context
            embedded_text: Text extracted directly from PDF
            ocr_text: Text extracted via OCR from image
            prompts: Optional custom prompts to override defaults
            **generation_kwargs: Additional generation arguments

        Returns:
            OCRResult with merged text and metadata
        """
        pass
    
    @abstractmethod
    def merge_texts_with_prompt(
        self,
        image: Image.Image,
        custom_prompt: str,
        **generation_kwargs
    ) -> OCRResult:
        """
        Merge texts using a custom pre-built prompt.
        
        This allows for enhanced prompts with spatial hints and few-shot examples.
        
        Args:
            image: Page image for visual context
            custom_prompt: Pre-built prompt (may include spatial analysis, examples, etc.)
            **generation_kwargs: Additional generation arguments
            
        Returns:
            OCRResult with merged text and metadata
        """
        pass
    
    @abstractmethod
    def format_with_visual(
        self,
        image: Image.Image,
        text: str,
        target_format: str,
        context: Optional[str] = None,
        prompts: Optional[Dict[str, str]] = None,
        **generation_kwargs
    ) -> OCRResult:
        """
        Use visual modality to validate and format text appropriately.

        Args:
            image: Original page image for visual verification
            text: Already-merged text content to format
            target_format: Desired format (text, markdown, json)
            context: Optional document context/description
            prompts: Optional custom prompts to override defaults
            **generation_kwargs: Additional generation arguments

        Returns:
            OCRResult with properly formatted text
        """
        pass
    
    @abstractmethod
    def unload(self) -> None:
        """Unload the model from memory."""
        pass
    
    def get_memory_usage(self) -> Dict[str, float]:
        """
        Get current GPU memory usage.
        
        Returns:
            Dict mapping device to memory in GB
        """
        import torch
        
        if not torch.cuda.is_available():
            return {}
        
        memory_usage = {}
        for i in range(torch.cuda.device_count()):
            allocated = torch.cuda.memory_allocated(i) / 1024**3
            memory_usage[f"cuda:{i}"] = round(allocated, 2)
        
        return memory_usage
    
    def clear_cache(self) -> None:
        """
        Clear GPU cache to free memory.
        
        This should be called between inference passes to reduce
        memory fragmentation and free up VRAM.
        """
        import torch
        import gc
        
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
            torch.cuda.synchronize()
        gc.collect()
    
    @property
    def load_time(self) -> Optional[float]:
        """Get model load time in seconds."""
        return self._load_time
    
    def __repr__(self) -> str:
        """String representation."""
        status = "loaded" if self.is_loaded else "not loaded"
        return f"{self.__class__.__name__}(model_id='{self.model_id}', status='{status}')"

