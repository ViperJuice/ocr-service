"""
BAML OCR Service

Provides type-safe OCR operations using BAML for:
- Type consistency between Python backend and TypeScript frontend
- Versioned prompts stored in .baml files
- Automatic client routing and fallback
- Streaming support

This service wraps the existing HTTPClientManager with BAML's type safety.
"""
import logging
import os
import time
from typing import Optional, AsyncIterator
from PIL import Image
from pydantic import BaseModel, Field

from src.models.http_client_manager import HTTPClientManager, ModelType

logger = logging.getLogger(__name__)


# ==================== BAML-Compatible Types ====================
# These mirror the types defined in baml_src/types.baml

class OCRMetadata(BaseModel):
    """Metadata about OCR processing"""
    container_mode: bool = True
    openai_compatible: bool = True
    image_width: Optional[int] = None
    image_height: Optional[int] = None
    char_count: Optional[int] = None
    word_count: Optional[int] = None
    has_visual_elements: Optional[bool] = None


class OCRResult(BaseModel):
    """Result from OCR extraction or text merging"""
    text: str = Field(..., description="Extracted text content")
    model_name: str = Field(..., description="Model used for extraction")
    processing_time: float = Field(..., description="Time taken in seconds")
    format: str = Field(..., description="Processing format/type")
    metadata: Optional[OCRMetadata] = None


class PageMetadata(BaseModel):
    """Metadata about page processing"""
    embedded_text_length: Optional[int] = None
    ocr_text_length: Optional[int] = None
    merge_strategy: Optional[str] = None
    visual_formatting_applied: Optional[bool] = None
    spatial_blocks_count: Optional[int] = None
    has_tables: Optional[bool] = None
    has_images: Optional[bool] = None
    dpi: Optional[int] = None


class PageResult(BaseModel):
    """Result for a single page"""
    page_num: int
    text: str
    processing_method: str
    processing_time: float
    char_count: int
    word_count: int
    has_visual_elements: bool
    metadata: Optional[PageMetadata] = None


# ==================== BAML OCR Service ====================

class BAMLOCRService:
    """
    OCR service using BAML-compatible types and prompts.

    This service provides the benefits of BAML (type safety, versioned prompts)
    while using our existing container infrastructure via HTTPClientManager.
    """

    def __init__(
        self,
        deepseek_url: Optional[str] = None,
        qwen_url: Optional[str] = None,
        timeout: float = 300.0
    ):
        """
        Initialize BAML OCR service.

        Args:
            deepseek_url: DeepSeek container URL (default: env.DEEPSEEK_URL or http://localhost:8001)
            qwen_url: QWEN container URL (default: env.QWEN_URL or http://localhost:8002)
            timeout: Request timeout in seconds
        """
        self.deepseek_url = deepseek_url or os.getenv("DEEPSEEK_URL", "http://localhost:8001")
        self.qwen_url = qwen_url or os.getenv("QWEN_URL", "http://localhost:8002")
        self.timeout = timeout

        # Initialize HTTP client manager for container communication
        self.http_client_manager: Optional[HTTPClientManager] = None

        # Load prompts from BAML files
        # For now, we'll use inline prompts that match baml_src/ocr.baml
        # In production, these would be loaded from the BAML runtime
        self.prompts = {
            "ocr": (
                "Free OCR. Extract all text from this image with high accuracy.\n"
                "Preserve the original layout and formatting as much as possible.\n"
                "Include all visible text, numbers, symbols, and special characters.\n"
                "Maintain line breaks and spacing where appropriate."
            ),
            "merge": (
                "You are an expert text merger. Compare and merge these two text versions from the same document page:\n\n"
                "**Embedded Text (from PDF):**\n```\n{embedded_text}\n```\n\n"
                "**OCR Text (from image):**\n```\n{ocr_text}\n```\n\n"
                "Your task:\n"
                "1. Compare both versions carefully\n"
                "2. Use the embedded text as the base (it's usually more accurate for standard text)\n"
                "3. Use the OCR text to fill in missing content (formulas, special symbols, tables)\n"
                "4. Fix any obvious OCR errors by cross-referencing with the embedded text\n"
                "5. Preserve the original layout and formatting\n"
                "6. Include all content from both sources\n\n"
                "Provide the most accurate merged version. Return only the final merged text."
            )
        }

        logger.info(f"BAMLOCRService initialized (DeepSeek: {self.deepseek_url}, QWEN: {self.qwen_url})")

    async def initialize(self):
        """Initialize HTTP client manager"""
        self.http_client_manager = HTTPClientManager()
        await self.http_client_manager.initialize(
            deepseek_url=self.deepseek_url,
            qwen_url=self.qwen_url,
            timeout=self.timeout
        )
        logger.info("BAML OCR Service initialized")

    async def extract_text_ocr(
        self,
        image: Image.Image,
        custom_prompt: Optional[str] = None
    ) -> OCRResult:
        """
        Extract text from image using DeepSeek-OCR.

        Corresponds to BAML function: ExtractTextOCR

        Args:
            image: PIL Image to process
            custom_prompt: Optional custom prompt (overrides default)

        Returns:
            OCRResult with extracted text and metadata
        """
        if self.http_client_manager is None:
            raise RuntimeError("Service not initialized. Call initialize() first")

        import io
        import base64

        start_time = time.time()

        # Convert image to base64 data URL
        buffer = io.BytesIO()
        image.save(buffer, format='PNG')
        image_b64 = base64.b64encode(buffer.getvalue()).decode('utf-8')
        image_data_url = f"data:image/png;base64,{image_b64}"

        # Build prompt
        prompt = custom_prompt if custom_prompt else self.prompts["ocr"]

        # Build OpenAI-format messages
        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "image_url", "image_url": {"url": image_data_url}},
                    {"type": "text", "text": prompt}
                ]
            }
        ]

        # Call DeepSeek container
        response = await self.http_client_manager.chat_completion(
            model_type=ModelType.DEEPSEEK_OCR,
            messages=messages,
            stream=False,
            max_tokens=4096,
            temperature=0.0,
            auto_unload=True
        )

        # Extract text from response
        text = response.get("choices", [{}])[0].get("message", {}).get("content", "")
        processing_time = time.time() - start_time

        # Build metadata
        metadata = OCRMetadata(
            image_width=image.size[0],
            image_height=image.size[1],
            char_count=len(text),
            word_count=len(text.split())
        )

        return OCRResult(
            text=text,
            model_name="deepseek-ocr",
            processing_time=processing_time,
            format="ocr",
            metadata=metadata
        )

    async def merge_texts(
        self,
        image: Image.Image,
        embedded_text: str,
        ocr_text: str,
        custom_prompt: Optional[str] = None
    ) -> OCRResult:
        """
        Merge embedded and OCR text using QWEN3-VL.

        Corresponds to BAML function: MergeTexts

        Args:
            image: PIL Image (reference for visual context)
            embedded_text: Text embedded in PDF
            ocr_text: Text extracted via OCR
            custom_prompt: Optional custom prompt (overrides default)

        Returns:
            OCRResult with merged text and metadata
        """
        if self.http_client_manager is None:
            raise RuntimeError("Service not initialized. Call initialize() first")

        import io
        import base64

        start_time = time.time()

        # Convert image to base64 data URL
        buffer = io.BytesIO()
        image.save(buffer, format='PNG')
        image_b64 = base64.b64encode(buffer.getvalue()).decode('utf-8')
        image_data_url = f"data:image/png;base64,{image_b64}"

        # Build prompt with text substitutions
        if custom_prompt:
            prompt = custom_prompt
        else:
            prompt = self.prompts["merge"].format(
                embedded_text=embedded_text,
                ocr_text=ocr_text
            )

        # Build OpenAI-format messages
        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "image_url", "image_url": {"url": image_data_url}},
                    {"type": "text", "text": prompt}
                ]
            }
        ]

        # Call QWEN container
        response = await self.http_client_manager.chat_completion(
            model_type=ModelType.QWEN_VL,
            messages=messages,
            stream=False,
            max_tokens=4096,
            temperature=0.0,
            auto_unload=True
        )

        # Extract text from response
        text = response.get("choices", [{}])[0].get("message", {}).get("content", "")
        processing_time = time.time() - start_time

        # Build metadata
        metadata = OCRMetadata(
            image_width=image.size[0],
            image_height=image.size[1],
            char_count=len(text),
            word_count=len(text.split())
        )

        return OCRResult(
            text=text,
            model_name="qwen3-vl-8b",
            processing_time=processing_time,
            format="merge",
            metadata=metadata
        )

    async def merge_texts_streaming(
        self,
        image: Image.Image,
        embedded_text: str,
        ocr_text: str
    ) -> AsyncIterator[str]:
        """
        Stream merged text token-by-token using QWEN3-VL.

        Corresponds to BAML function: MergeTextsStreaming

        Args:
            image: PIL Image
            embedded_text: Text embedded in PDF
            ocr_text: Text extracted via OCR

        Yields:
            Text chunks as they're generated
        """
        if self.http_client_manager is None:
            raise RuntimeError("Service not initialized. Call initialize() first")

        import io
        import base64

        # Convert image to base64 data URL
        buffer = io.BytesIO()
        image.save(buffer, format='PNG')
        image_b64 = base64.b64encode(buffer.getvalue()).decode('utf-8')
        image_data_url = f"data:image/png;base64,{image_b64}"

        # Build simplified streaming prompt
        prompt = (
            f"Compare and merge these two text versions from the same document page.\n"
            f"Use embedded text as base, fill in gaps with OCR text, and fix OCR errors.\n\n"
            f"**Embedded Text:**\n{embedded_text}\n\n"
            f"**OCR Text:**\n{ocr_text}\n\n"
            f"Return the merged text immediately:"
        )

        # Build OpenAI-format messages
        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "image_url", "image_url": {"url": image_data_url}},
                    {"type": "text", "text": prompt}
                ]
            }
        ]

        # Stream from QWEN container
        stream = await self.http_client_manager.chat_completion(
            model_type=ModelType.QWEN_VL,
            messages=messages,
            stream=True,
            max_tokens=4096,
            temperature=0.0,
            auto_unload=True
        )

        # Yield chunks
        async for chunk in stream:
            # Extract delta content from OpenAI chunk format
            delta = chunk.get("choices", [{}])[0].get("delta", {})
            content = delta.get("content", "")
            if content:
                yield content

    async def close(self):
        """Close HTTP client manager connections"""
        if self.http_client_manager:
            await self.http_client_manager.close()
            self.http_client_manager = None
            logger.info("BAML OCR Service closed")
