"""DeepSeek-OCR model wrapper."""
import time
import torch
from typing import Dict, Any, Optional, Tuple
from PIL import Image
from transformers import AutoModel, AutoTokenizer

from .base import BaseVLModel, OCRResult


class DeepSeekOCRModel(BaseVLModel):
    """Wrapper for DeepSeek-OCR model."""
    
    def __init__(
        self,
        model_id: str,
        config: Dict[str, Any],
        device_map: str = "auto",
        prompts: Optional[Dict[str, str]] = None,
        infer_config: Optional[Dict[str, Any]] = None,
        quantization: Optional[str] = None,
        force_disable_crop: bool = False,
    ):
        """
        Initialize DeepSeek-OCR model.
        
        Args:
            model_id: HuggingFace model ID
            config: Model configuration dict
            device_map: Device mapping strategy
            prompts: Custom prompts for different tasks
            infer_config: Inference configuration (base_size, image_size, crop_mode)
            quantization: Quantization mode ("int8", "int4", or None)
            force_disable_crop: Disable crop mode to reduce memory usage
        """
        super().__init__(model_id, config, device_map)
        self.prompts = prompts or {}
        self.infer_config = infer_config or {}
        self.generation_config = config.get("generation_config", {})
        self.quantization = quantization
        
        # === NEW: Allow disabling crop mode for memory savings ===
        self.force_disable_crop = force_disable_crop
        if force_disable_crop:
            # Override crop_mode in infer_config
            self.infer_config = self.infer_config.copy()  # Don't mutate original
            self.infer_config['crop_mode'] = False
            print("[DeepSeek-OCR] Crop mode disabled (memory saving mode)")
    
    def get_memory_estimate(self, crop_mode: Optional[bool] = None) -> Dict[str, float]:
        """
        Estimate memory usage for current configuration.
        
        Args:
            crop_mode: Override crop_mode setting, or None to use current config
        
        Returns:
            Dictionary with memory estimates:
            - model_weight_gb: Model weights on GPU
            - estimated_inference_gb: Peak memory during inference
            - total_gb: Total peak memory
            - savings_without_crop_gb: Memory saved if crop mode disabled
        """
        # Base model weight
        base_model_gb = 6.0  # DeepSeek-OCR model weights
        
        # Determine crop mode setting
        if crop_mode is None:
            crop_mode = self.infer_config.get('crop_mode', True)
        
        # Estimate inference memory based on crop mode
        if crop_mode:
            # With crops: 8x overhead + full processing pipeline
            inference_gb = 7.5  # From updated calculations at 300 DPI
        else:
            # Without crops: single pass, ~2x less memory
            # Still needs attention, KV cache, but no multiple crops
            inference_gb = 3.5
        
        total_gb = base_model_gb + inference_gb
        savings_gb = 7.5 - 3.5  # Memory saved without crops
        
        return {
            'model_weight_gb': base_model_gb,
            'estimated_inference_gb': inference_gb,
            'total_gb': total_gb,
            'savings_without_crop_gb': savings_gb if crop_mode else 0.0,
            'crop_mode_enabled': crop_mode
        }
    
    def _infer_with_prompt(
        self,
        image: Image.Image,
        prompt: str,
        base_size: int,
        image_size: int,
        crop_mode: bool
    ) -> str:
        """
        Helper method to call DeepSeek-OCR's infer method.
        
        Args:
            image: PIL Image
            prompt: Text prompt
            base_size: Base resolution
            image_size: Image resolution for crops
            crop_mode: Whether to use dynamic resolution
            
        Returns:
            Generated text string
        """
        import tempfile
        import os
        
        # Save image to temporary file
        with tempfile.NamedTemporaryFile(suffix='.jpg', delete=False) as tmp_img:
            image.save(tmp_img.name)
            tmp_img_path = tmp_img.name
        
        try:
            # Clear any cached KV from previous inference
            if hasattr(self.model, 'past_key_values'):
                self.model.past_key_values = None

            # Create temporary output directory
            with tempfile.TemporaryDirectory() as tmp_dir:
                print(f"[DEBUG _infer_with_prompt] Calling model.infer with prompt length: {len(prompt)}")
                output_text = self.model.infer(
                    self.tokenizer,
                    prompt=prompt,
                    image_file=tmp_img_path,
                    output_path=tmp_dir,
                    base_size=base_size,
                    image_size=image_size,
                    crop_mode=crop_mode,
                    save_results=False,
                    test_compress=False,
                    eval_mode=True  # Required to get return value instead of None
                )
                print(f"[DEBUG _infer_with_prompt] Returned: {type(output_text)}, len={len(output_text) if output_text else 0}")

                # Explicitly clear KV cache after inference
                if hasattr(self.model, 'past_key_values'):
                    self.model.past_key_values = None
                torch.cuda.synchronize()
        finally:
            # Clean up temp image
            try:
                os.unlink(tmp_img_path)
            except:
                pass
        
        # Handle None returns from model
        if output_text is None:
            print(f"[DEBUG _infer_with_prompt] output_text is None, returning empty string")
            return ""
        
        print(f"[DEBUG _infer_with_prompt] Returning text with length: {len(output_text)}")
        return output_text
    
    def load(self) -> None:
        """Load DeepSeek-OCR model and tokenizer."""
        if self.is_loaded:
            print(f"Model {self.model_id} is already loaded.")
            return
        
        print(f"Loading DeepSeek-OCR model: {self.model_id}")
        start_time = time.time()
        
        # Extract torch dtype
        dtype_str = self.config.get("torch_dtype", "float16")
        dtype = getattr(torch, dtype_str)
        
        # Load model with flash attention if configured
        attn_implementation = self.config.get("_attn_implementation", None)
        
        load_kwargs = {
            "trust_remote_code": True,
            "torch_dtype": dtype,
            "device_map": self.device_map,
            "low_cpu_mem_usage": True,
            "max_memory": self.config.get("max_memory"),
        }
        
        if attn_implementation:
            load_kwargs["attn_implementation"] = attn_implementation
        
        # Add quantization config if requested
        if self.quantization == "int8":
            load_kwargs["load_in_8bit"] = True
            load_kwargs["llm_int8_threshold"] = 6.0
            print(f"  Using int8 quantization (~50% memory reduction)")
        elif self.quantization == "int4":
            load_kwargs["load_in_4bit"] = True
            load_kwargs["bnb_4bit_compute_dtype"] = dtype
            load_kwargs["bnb_4bit_quant_type"] = "nf4"
            load_kwargs["bnb_4bit_use_double_quant"] = True
            print(f"  Using int4 quantization (~75% memory reduction)")
        
        self.model = AutoModel.from_pretrained(
            self.model_id,
            revision="9f30c71f441d010e5429c532364a86705536c53a",  # Pin revision to prevent re-downloads
            **load_kwargs
        )

        # Load tokenizer
        self.tokenizer = AutoTokenizer.from_pretrained(
            self.model_id,
            revision="9f30c71f441d010e5429c532364a86705536c53a",  # Pin revision
            trust_remote_code=True,
        )
        
        self.model.eval()
        self.is_loaded = True
        self._load_time = time.time() - start_time
        
        print(f"✓ DeepSeek-OCR loaded in {self._load_time:.1f}s")
        print(f"  Memory usage: {self.get_memory_usage()}")
    
    def process_image(
        self,
        image: Image.Image,
        prompt_type: str = "ocr",
        prompts: Optional[Dict[str, str]] = None,
        **generation_kwargs
    ) -> OCRResult:
        """
        Process image with DeepSeek-OCR.

        Args:
            image: PIL Image
            prompt_type: Type of prompt (ocr, markdown, structured)
            prompts: Optional custom prompts to override defaults
            **generation_kwargs: Override generation config

        Returns:
            OCRResult with extracted text
        """
        if not self.is_loaded:
            raise RuntimeError("Model is not loaded. Call load() first.")
        
        start_time = time.time()

        # Use provided prompts or fall back to instance prompts
        active_prompts = prompts if prompts is not None else self.prompts

        # Get prompt template
        prompt = active_prompts.get(
            prompt_type,
            active_prompts.get("ocr", "<image>\nFree OCR. ")
        )
        
        # Prepare inference config
        base_size = self.infer_config.get("base_size", 1024)
        image_size = self.infer_config.get("image_size", 640)
        crop_mode = self.infer_config.get("crop_mode", True)
        
        # Merge generation configs
        gen_config = {**self.generation_config, **generation_kwargs}
        
        # Generate using DeepSeek-OCR's infer method
        output_text = self._infer_with_prompt(
            image, prompt, base_size, image_size, crop_mode
        )
        
        processing_time = time.time() - start_time
        
        # Clear cache to free memory
        self.clear_cache()
        
        return OCRResult(
            text=output_text,
            model_name=self.model_id,
            processing_time=processing_time,
            format=prompt_type,
            metadata={
                "image_size": image.size,
                "infer_config": {
                    "base_size": base_size,
                    "image_size": image_size,
                    "crop_mode": crop_mode,
                },
                "generation_config": gen_config,
                "memory_usage": self.get_memory_usage(),
            }
        )
    
    def merge_texts(
        self,
        image: Image.Image,
        embedded_text: str,
        ocr_text: str,
        prompts: Optional[Dict[str, str]] = None,
        **generation_kwargs
    ) -> OCRResult:
        """
        Use DeepSeek-OCR to intelligently merge embedded and OCR text.

        Args:
            image: Original page image for visual context
            embedded_text: Text extracted from PDF
            ocr_text: Text from OCR
            prompts: Optional custom prompts to override defaults
            **generation_kwargs: Override generation config

        Returns:
            OCRResult with merged text
        """
        if not self.is_loaded:
            raise RuntimeError("Model is not loaded. Call load() first.")

        start_time = time.time()

        # Use provided prompts or fall back to instance prompts
        active_prompts = prompts if prompts is not None else self.prompts

        # Get merge prompt template
        merge_prompt_template = active_prompts.get("merge", "")
        
        # If no specific merge prompt, use a default one
        if not merge_prompt_template:
            merge_prompt = f"""<image>
<|grounding|>Compare these two text versions:

Embedded: {embedded_text}

OCR: {ocr_text}

Merge accurately: """
        else:
            # Format the template with the texts  
            merge_prompt = merge_prompt_template.format(
                embedded_text=embedded_text,
                ocr_text=ocr_text
            )
        
        print(f"[DEBUG MERGE PROMPT] Prompt length: {len(merge_prompt)}")
        print(f"[DEBUG MERGE PROMPT] Prompt start: {repr(merge_prompt[:300])}")
        
        # Prepare inference config
        base_size = self.infer_config.get("base_size", 1024)
        image_size = self.infer_config.get("image_size", 640)
        crop_mode = self.infer_config.get("crop_mode", True)
        
        # Merge generation configs
        gen_config = {**self.generation_config, **generation_kwargs}
        
        # Generate using DeepSeek-OCR's infer method
        output_text = self._infer_with_prompt(
            image, merge_prompt, base_size, image_size, crop_mode
        )
        
        processing_time = time.time() - start_time
        
        print(f"[DEBUG MERGE_TEXTS] Output text from infer: {len(output_text) if output_text else 0} chars")
        print(f"[DEBUG MERGE_TEXTS] First 100 chars: {repr(output_text[:100]) if output_text else 'None'}")
        
        # Clear cache to free memory
        self.clear_cache()
        
        result = OCRResult(
            text=output_text or "",
            model_name=self.model_id,
            processing_time=processing_time,
            format="merge",
            metadata={
                "image_size": image.size,
                "infer_config": {
                    "base_size": base_size,
                    "image_size": image_size,
                    "crop_mode": crop_mode,
                },
                "generation_config": gen_config,
                "memory_usage": self.get_memory_usage(),
                "embedded_text_length": len(embedded_text),
                "ocr_text_length": len(ocr_text),
            }
        )
        print(f"[DEBUG MERGE_TEXTS] Returning OCRResult with text length: {len(result.text)}")
        return result
    
    def merge_texts_with_prompt(
        self,
        image: Image.Image,
        custom_prompt: str,
        **generation_kwargs
    ) -> OCRResult:
        """
        Merge texts using a custom pre-built prompt.
        
        Args:
            image: Page image for visual context
            custom_prompt: Pre-built prompt with spatial hints/examples
            **generation_kwargs: Override generation config
            
        Returns:
            OCRResult with merged text
        """
        if not self.is_loaded:
            raise RuntimeError("Model is not loaded. Call load() first.")
        
        start_time = time.time()
        
        # Prepare inference config
        base_size = self.infer_config.get("base_size", 1024)
        image_size = self.infer_config.get("image_size", 640)
        crop_mode = self.infer_config.get("crop_mode", True)
        
        # Merge generation configs
        gen_config = {**self.generation_config, **generation_kwargs}
        
        # Generate using DeepSeek-OCR's infer method with custom prompt
        output_text = self._infer_with_prompt(
            image, custom_prompt, base_size, image_size, crop_mode
        )
        
        processing_time = time.time() - start_time
        
        # Clear cache to free memory
        self.clear_cache()
        
        return OCRResult(
            text=output_text,
            model_name=self.model_id,
            processing_time=processing_time,
            format="merge_custom",
            metadata={
                "image_size": image.size,
                "infer_config": {
                    "base_size": base_size,
                    "image_size": image_size,
                    "crop_mode": crop_mode,
                },
                "generation_config": gen_config,
                "memory_usage": self.get_memory_usage(),
                "custom_prompt_used": True,
            }
        )
    
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
        Use DeepSeek-OCR to format text using visual verification.

        Args:
            image: Original page image for visual context
            text: Text to format
            target_format: Desired format (text, markdown, json)
            context: Optional document context
            prompts: Optional custom prompts to override defaults
            **generation_kwargs: Override generation config

        Returns:
            OCRResult with formatted text
        """
        if not self.is_loaded:
            raise RuntimeError("Model is not loaded. Call load() first.")
        
        start_time = time.time()

        # Use provided prompts or fall back to instance prompts
        active_prompts = prompts if prompts is not None else self.prompts

        # Get format_visual prompt template
        format_prompt_template = active_prompts.get("format_visual", "")
        
        # If no specific format_visual prompt, use a default one
        if not format_prompt_template:
            format_prompt = f"""<image>
<|grounding|>Context: {context or 'Document page'}

Text to format:
{text}

Convert to {target_format} format by verifying structure against the image. Ensure proper formatting for headings, lists, tables, and layout: """
        else:
            # Format the template with parameters
            format_prompt = format_prompt_template.format(
                context=context or "Document page",
                text=text,
                format=target_format
            )
        
        # Prepare inference config
        base_size = self.infer_config.get("base_size", 1024)
        image_size = self.infer_config.get("image_size", 640)
        crop_mode = self.infer_config.get("crop_mode", True)
        
        # Merge generation configs
        gen_config = {**self.generation_config, **generation_kwargs}
        
        # Generate using DeepSeek-OCR's infer method
        output_text = self._infer_with_prompt(
            image, format_prompt, base_size, image_size, crop_mode
        )
        
        processing_time = time.time() - start_time
        
        # Clear cache to free memory
        self.clear_cache()
        
        return OCRResult(
            text=output_text,
            model_name=self.model_id,
            processing_time=processing_time,
            format=target_format,
            metadata={
                "image_size": image.size,
                "infer_config": {
                    "base_size": base_size,
                    "image_size": image_size,
                    "crop_mode": crop_mode,
                },
                "generation_config": gen_config,
                "memory_usage": self.get_memory_usage(),
                "input_text_length": len(text),
                "target_format": target_format,
                "context": context,
            }
        )

    def validate_extraction(
        self,
        image: Image.Image,
        extracted_text: str,
        **generation_kwargs
    ) -> Tuple[bool, str]:
        """
        Validate extracted text against original image.

        Compares the extracted text to the image to ensure all structural
        elements are properly captured (line numbers, tables, Q&A format, etc.).

        Args:
            image: Original page image for visual comparison
            extracted_text: Extracted markdown/text to validate
            **generation_kwargs: Override generation config (e.g., max_new_tokens)

        Returns:
            Tuple of (is_valid, issue_description):
            - (True, "") if extraction is valid
            - (False, "description of issues") if needs refinement

        Example:
            >>> is_valid, issues = model.validate_extraction(image, text)
            >>> if not is_valid:
            >>>     print(f"Issues found: {issues}")
        """
        if not self.is_loaded:
            raise RuntimeError("Model is not loaded. Call load() first.")

        # Truncate text for validation prompt (2000 chars sufficient for structure check)
        text_sample = extracted_text[:2000]
        if len(extracted_text) > 2000:
            text_sample += "\n[... text truncated for validation ...]"

        validation_prompt = f"""<image>
<|grounding|>Original document above.

Extracted text:
{text_sample}

Task: Compare extracted text to the image. Check if ALL structural elements are captured:
- Line numbers (if present in margins)
- Table columns and alignment
- Headers and sections
- Q&A formatting (questions and answers)
- No missing text regions

Response format (respond with ONLY one of these):
- If extraction is complete and accurate: "VALID"
- If issues exist: "INVALID: [brief description of specific problems]"

Your response:"""

        start_time = time.time()

        # Use constrained generation for speed
        gen_config = {
            "max_new_tokens": 50,  # Keep response brief
            "temperature": 0.0,     # Deterministic
            **generation_kwargs
        }

        output_text = self._infer_with_prompt(
            image,
            validation_prompt,
            base_size=self.infer_config.get("base_size", 1024),
            image_size=self.infer_config.get("image_size", 640),
            crop_mode=self.infer_config.get("crop_mode", True)
        )

        processing_time = time.time() - start_time

        # Parse result
        result = output_text.strip()
        if result.startswith("VALID"):
            return True, ""
        elif result.startswith("INVALID"):
            # Extract description after "INVALID: "
            description = result.replace("INVALID:", "").strip()
            return False, description
        else:
            # Unclear response - err on side of caution
            return False, f"Validation unclear: {result[:100]}"

    def refine_extraction(
        self,
        image: Image.Image,
        initial_text: str,
        issues: str,
        context: Optional[str] = None,
        **generation_kwargs
    ) -> OCRResult:
        """
        Refine extraction based on identified issues.

        Performs targeted re-extraction with specific guidance about what
        problems to fix, based on validation feedback.

        Args:
            image: Original page image
            initial_text: Initial extraction with issues
            issues: Description of identified problems (from validation)
            context: Optional document context (e.g., "Legal deposition transcript")
            **generation_kwargs: Override generation config

        Returns:
            OCRResult with refined text and metadata about issues addressed

        Example:
            >>> result = model.refine_extraction(
            ...     image,
            ...     initial_text,
            ...     issues="Missing line numbers on left margin",
            ...     context="Legal deposition transcript"
            ... )
            >>> print(result.text)  # Refined extraction
        """
        if not self.is_loaded:
            raise RuntimeError("Model is not loaded. Call load() first.")

        start_time = time.time()

        # Truncate initial text for context (keep first 3000 chars)
        text_sample = initial_text[:3000]
        if len(initial_text) > 3000:
            text_sample += "\n[... rest of text truncated ...]"

        refinement_prompt = f"""<image>
<|grounding|>Document above.

Context: {context or "Document page"}

Previous extraction had these issues:
{issues}

Initial extraction:
{text_sample}

Task: Re-extract the document text, paying special attention to the issues mentioned above.
Ensure complete and accurate capture of ALL visible elements, especially those that were missing.

Corrected extraction:"""

        # Prepare inference config
        base_size = self.infer_config.get("base_size", 1024)
        image_size = self.infer_config.get("image_size", 640)
        crop_mode = self.infer_config.get("crop_mode", True)

        # Merge generation configs
        gen_config = {**self.generation_config, **generation_kwargs}

        # Perform refinement
        output_text = self._infer_with_prompt(
            image, refinement_prompt, base_size, image_size, crop_mode
        )

        processing_time = time.time() - start_time

        # Clear cache to free memory
        self.clear_cache()

        return OCRResult(
            text=output_text,
            model_name=self.model_id,
            processing_time=processing_time,
            format="refined",
            metadata={
                "image_size": image.size,
                "infer_config": {
                    "base_size": base_size,
                    "image_size": image_size,
                    "crop_mode": crop_mode,
                },
                "generation_config": gen_config,
                "memory_usage": self.get_memory_usage(),
                "issues_addressed": issues,
                "initial_text_length": len(initial_text),
                "context": context,
            }
        )

    def unload(self) -> None:
        """Unload model from memory."""
        if not self.is_loaded:
            return
        
        print(f"Unloading {self.model_id}...")
        
        del self.model
        del self.tokenizer
        
        self.model = None
        self.tokenizer = None
        self.is_loaded = False
        
        # Clear GPU cache
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
            torch.cuda.synchronize()
        
        print(f"✓ {self.model_id} unloaded")

