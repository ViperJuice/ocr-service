"""Qwen3-VL model wrapper."""
import time
import torch
import logging
from typing import Dict, Any, Optional, Tuple
from PIL import Image
from transformers import AutoModelForImageTextToText, AutoProcessor
from qwen_vl_utils import process_vision_info

from .base import BaseVLModel, OCRResult

logger = logging.getLogger(__name__)


class QwenVLModel(BaseVLModel):
    """Wrapper for Qwen3-VL models (2B, 4B, and 8B variants)."""
    
    def __init__(
        self,
        model_id: str,
        config: Dict[str, Any],
        device_map: str = "auto",
        prompts: Optional[Dict[str, str]] = None,
        quantization: Optional[str] = None,
    ):
        """
        Initialize Qwen3-VL model.
        
        Args:
            model_id: HuggingFace model ID
            config: Model configuration dict
            device_map: Device mapping strategy
            prompts: Custom prompts for different tasks
            quantization: Quantization mode ("int8", "int4", or None)
        """
        super().__init__(model_id, config, device_map)
        self.prompts = prompts or {}
        self.generation_config = config.get("generation_config", {})
        self.quantization = quantization
    
    def load(self) -> None:
        """Load Qwen3-VL model and processor."""
        if self.is_loaded:
            print(f"Model {self.model_id} is already loaded.")
            return
        
        print(f"Loading Qwen3-VL model: {self.model_id}")
        start_time = time.time()
        
        # Extract torch dtype
        dtype_str = self.config.get("torch_dtype", "float16")
        dtype = getattr(torch, dtype_str)
        
        # Prepare loading kwargs
        load_kwargs = {
            "torch_dtype": dtype,
            "device_map": self.device_map,
            "low_cpu_mem_usage": True,
            "trust_remote_code": True,
            "max_memory": self.config.get("config", {}).get("max_memory"),
        }

        # Add attention implementation if specified (Flash Attention 2 for memory efficiency)
        if "_attn_implementation" in self.config.get("config", {}):
            load_kwargs["attn_implementation"] = self.config["config"]["_attn_implementation"]
            print(f"  Attention implementation: {load_kwargs['attn_implementation']}")

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
        
        # Load model
        self.model = AutoModelForImageTextToText.from_pretrained(
            self.model_id,
            **load_kwargs
        )
        
        # Load processor
        self.processor = AutoProcessor.from_pretrained(
            self.model_id,
            trust_remote_code=True,
        )

        # Apply processor config if specified (for memory optimization)
        # Note: Qwen3-VL uses image_patch_size=16 (vs 14 for Qwen2.5-VL)
        # Compression ratio is 32 for Qwen3-VL
        processor_config = {
            "min_pixels": 65536,  # 256x256
            "max_pixels": 640000,  # ~800x800 (aggressive memory saving for high-res images)
        }
        if processor_config and hasattr(self.processor, 'image_processor'):
            if "min_pixels" in processor_config:
                self.processor.image_processor.min_pixels = processor_config["min_pixels"]
                self.processor.image_processor.size["min_pixels"] = processor_config["min_pixels"]
            if "max_pixels" in processor_config:
                self.processor.image_processor.max_pixels = processor_config["max_pixels"]
                self.processor.image_processor.size["max_pixels"] = processor_config["max_pixels"]
            print(f"  Processor config: min_pixels={self.processor.image_processor.min_pixels}, max_pixels={self.processor.image_processor.max_pixels}")

        self.model.eval()
        self.is_loaded = True
        self._load_time = time.time() - start_time

        # Verify Flash Attention 2 is active
        if hasattr(self.model.config, '_attn_implementation'):
            actual_attn = self.model.config._attn_implementation
            print(f"  ✓ Attention implementation verified: {actual_attn}")
            if actual_attn != "flash_attention_2":
                logger.warning(f"Expected flash_attention_2 but got {actual_attn} - may use more memory")

        print(f"✓ Qwen3-VL loaded in {self._load_time:.1f}s")
        print(f"  Memory usage: {self.get_memory_usage()}")
    
    def process_image(
        self,
        image: Image.Image,
        prompt_type: str = "ocr",
        prompts: Optional[Dict[str, str]] = None,
        **generation_kwargs
    ) -> OCRResult:
        """
        Process image with Qwen3-VL.

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
        prompt_template = active_prompts.get(
            prompt_type,
            active_prompts.get("ocr", "Extract all text from this image.")
        )

        # Prepare messages for Qwen3-VL format
        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "image", "image": image},
                    {"type": "text", "text": prompt_template},
                ],
            }
        ]

        # Apply chat template
        text_prompt = self.processor.apply_chat_template(
            messages,
            tokenize=False,
            add_generation_prompt=True,
        )

        # Process vision info
        image_inputs, video_inputs = process_vision_info(messages)

        # Prepare inputs
        inputs = self.processor(
            text=[text_prompt],
            images=image_inputs,
            videos=video_inputs,
            padding=True,
            return_tensors="pt",
        )

        # Move to device (handle sharded models correctly)
        if hasattr(self.model, 'hf_device_map') and self.model.hf_device_map:
            # Check if model is truly sharded across multiple devices
            devices_used = set(self.model.hf_device_map.values()) if isinstance(self.model.hf_device_map, dict) else {self.model.hf_device_map}

            if len(devices_used) > 1:
                # Multi-device sharding detected
                # Move inputs to first GPU device, HF will handle inter-device routing
                first_device = f"cuda:{min(d for d in devices_used if isinstance(d, int))}"
                logger.warning(
                    f"Model is sharded across {len(devices_used)} devices: {devices_used}. "
                    f"Moving inputs to first device: {first_device}. "
                    f"Note: Sharding adds significant overhead and may cause instability."
                )
                print(f"⚠️  Model sharded across {devices_used} - inputs to {first_device}")

                # Move all tensor inputs to first device for HF's automatic routing
                inputs = {k: v.to(first_device) if isinstance(v, torch.Tensor) else v
                          for k, v in inputs.items()}
            else:
                # Single device (device_map='auto' but not actually sharded)
                target_device = next(iter(devices_used))
                logger.debug(f"Model on single device: {target_device}")
                inputs = {k: v.to(target_device) if isinstance(v, torch.Tensor) else v
                          for k, v in inputs.items()}
        else:
            # No device_map - use model's device
            logger.debug(f"Model on single device: {self.model.device}")
            inputs = inputs.to(self.model.device)
        
        # Merge generation configs
        gen_config = {**self.generation_config, **generation_kwargs}

        # Clear any cached KV from previous inference
        if hasattr(self.model, 'past_key_values'):
            self.model.past_key_values = None

        # Generate with automatic mixed precision (FP16 activations for memory efficiency)
        with torch.no_grad(), torch.amp.autocast('cuda', dtype=torch.float16):
            output_ids = self.model.generate(
                **inputs,
                max_new_tokens=gen_config.get("max_new_tokens", 2048),
                temperature=gen_config.get("temperature", 0.1),
                top_p=gen_config.get("top_p", 0.9),
                do_sample=gen_config.get("do_sample", False),
                use_cache=True,  # Explicitly enable cache for generation
            )

        # Decode
        # Handle both dict and BatchEncoding formats
        input_ids_list = inputs["input_ids"] if isinstance(inputs, dict) else inputs.input_ids
        generated_ids = [
            output_ids[len(input_ids):]
            for input_ids, output_ids in zip(input_ids_list, output_ids)
        ]

        output_text = self.processor.batch_decode(
            generated_ids,
            skip_special_tokens=True,
            clean_up_tokenization_spaces=True,
        )[0]

        processing_time = time.time() - start_time

        # Explicitly clear KV cache and tensors
        del output_ids
        del generated_ids
        if hasattr(self.model, 'past_key_values'):
            self.model.past_key_values = None
        del inputs
        torch.cuda.synchronize()

        # Clear cache to free memory
        self.clear_cache()
        
        return OCRResult(
            text=output_text,
            model_name=self.model_id,
            processing_time=processing_time,
            format=prompt_type,
            metadata={
                "image_size": image.size,
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
        Use Qwen3-VL to intelligently merge embedded and OCR text.

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
            merge_prompt = f"""You are comparing two versions of text from the same document page.

Embedded Text (from PDF):
{embedded_text}

OCR Text (from image):
{ocr_text}

Task: Provide the most accurate version by:
1. Comparing both versions
2. Fixing any OCR errors using the embedded text
3. Preserving layout and formatting
4. Filling in any missing content

Return only the final merged text, no explanations."""
        else:
            # Format the template with the texts
            merge_prompt = merge_prompt_template.format(
                embedded_text=embedded_text,
                ocr_text=ocr_text
            )

        # Prepare messages for Qwen3-VL format
        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "image", "image": image},
                    {"type": "text", "text": merge_prompt},
                ],
            }
        ]

        # Apply chat template
        text_prompt = self.processor.apply_chat_template(
            messages,
            tokenize=False,
            add_generation_prompt=True,
        )

        # Process vision info
        image_inputs, video_inputs = process_vision_info(messages)

        # Prepare inputs
        inputs = self.processor(
            text=[text_prompt],
            images=image_inputs,
            videos=video_inputs,
            padding=True,
            return_tensors="pt",
        )

        # Move to device (handle sharded models correctly)
        if hasattr(self.model, 'hf_device_map') and self.model.hf_device_map:
            # Check if model is truly sharded across multiple devices
            devices_used = set(self.model.hf_device_map.values()) if isinstance(self.model.hf_device_map, dict) else {self.model.hf_device_map}

            if len(devices_used) > 1:
                # Multi-device sharding detected
                # Move inputs to first GPU device, HF will handle inter-device routing
                first_device = f"cuda:{min(d for d in devices_used if isinstance(d, int))}"
                logger.warning(
                    f"Model is sharded across {len(devices_used)} devices: {devices_used}. "
                    f"Moving inputs to first device: {first_device}. "
                    f"Note: Sharding adds significant overhead and may cause instability."
                )
                print(f"⚠️  Model sharded across {devices_used} - inputs to {first_device}")

                # Move all tensor inputs to first device for HF's automatic routing
                inputs = {k: v.to(first_device) if isinstance(v, torch.Tensor) else v
                          for k, v in inputs.items()}
            else:
                # Single device (device_map='auto' but not actually sharded)
                target_device = next(iter(devices_used))
                logger.debug(f"Model on single device: {target_device}")
                inputs = {k: v.to(target_device) if isinstance(v, torch.Tensor) else v
                          for k, v in inputs.items()}
        else:
            # No device_map - use model's device
            logger.debug(f"Model on single device: {self.model.device}")
            inputs = inputs.to(self.model.device)
        
        # Merge generation configs
        gen_config = {**self.generation_config, **generation_kwargs}

        # Clear any cached KV from previous inference
        if hasattr(self.model, 'past_key_values'):
            self.model.past_key_values = None

        # Generate with automatic mixed precision (FP16 activations for memory efficiency)
        with torch.no_grad(), torch.amp.autocast('cuda', dtype=torch.float16):
            output_ids = self.model.generate(
                **inputs,
                max_new_tokens=gen_config.get("max_new_tokens", 2048),
                temperature=gen_config.get("temperature", 0.1),
                top_p=gen_config.get("top_p", 0.9),
                do_sample=gen_config.get("do_sample", False),
                use_cache=True,  # Explicitly enable cache for generation
            )

        # Decode
        # Handle both dict and BatchEncoding formats
        input_ids_list = inputs["input_ids"] if isinstance(inputs, dict) else inputs.input_ids
        generated_ids = [
            output_ids[len(input_ids):]
            for input_ids, output_ids in zip(input_ids_list, output_ids)
        ]

        output_text = self.processor.batch_decode(
            generated_ids,
            skip_special_tokens=True,
            clean_up_tokenization_spaces=True,
        )[0]

        processing_time = time.time() - start_time

        # Explicitly clear KV cache and tensors
        del output_ids
        del generated_ids
        if hasattr(self.model, 'past_key_values'):
            self.model.past_key_values = None
        del inputs
        torch.cuda.synchronize()

        # Clear cache to free memory
        self.clear_cache()
        
        return OCRResult(
            text=output_text,
            model_name=self.model_id,
            processing_time=processing_time,
            format="merge",
            metadata={
                "image_size": image.size,
                "generation_config": gen_config,
                "memory_usage": self.get_memory_usage(),
                "embedded_text_length": len(embedded_text),
                "ocr_text_length": len(ocr_text),
            }
        )
    
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

        # Prepare messages for Qwen3-VL format with custom prompt
        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "image", "image": image},
                    {"type": "text", "text": custom_prompt},
                ],
            }
        ]

        # Apply chat template
        text_prompt = self.processor.apply_chat_template(
            messages,
            tokenize=False,
            add_generation_prompt=True,
        )

        # Process vision info
        image_inputs, video_inputs = process_vision_info(messages)

        # Prepare inputs
        inputs = self.processor(
            text=[text_prompt],
            images=image_inputs,
            videos=video_inputs,
            padding=True,
            return_tensors="pt",
        )

        # Move to device (handle sharded models correctly)
        if hasattr(self.model, 'hf_device_map') and self.model.hf_device_map:
            # Check if model is truly sharded across multiple devices
            devices_used = set(self.model.hf_device_map.values()) if isinstance(self.model.hf_device_map, dict) else {self.model.hf_device_map}

            if len(devices_used) > 1:
                # Multi-device sharding detected
                # Move inputs to first GPU device, HF will handle inter-device routing
                first_device = f"cuda:{min(d for d in devices_used if isinstance(d, int))}"
                logger.warning(
                    f"Model is sharded across {len(devices_used)} devices: {devices_used}. "
                    f"Moving inputs to first device: {first_device}. "
                    f"Note: Sharding adds significant overhead and may cause instability."
                )
                print(f"⚠️  Model sharded across {devices_used} - inputs to {first_device}")

                # Move all tensor inputs to first device for HF's automatic routing
                inputs = {k: v.to(first_device) if isinstance(v, torch.Tensor) else v
                          for k, v in inputs.items()}
            else:
                # Single device (device_map='auto' but not actually sharded)
                target_device = next(iter(devices_used))
                logger.debug(f"Model on single device: {target_device}")
                inputs = {k: v.to(target_device) if isinstance(v, torch.Tensor) else v
                          for k, v in inputs.items()}
        else:
            # No device_map - use model's device
            logger.debug(f"Model on single device: {self.model.device}")
            inputs = inputs.to(self.model.device)
        
        # Merge generation configs
        gen_config = {**self.generation_config, **generation_kwargs}

        # Clear any cached KV from previous inference
        if hasattr(self.model, 'past_key_values'):
            self.model.past_key_values = None

        # Generate with automatic mixed precision (FP16 activations for memory efficiency)
        with torch.no_grad(), torch.amp.autocast('cuda', dtype=torch.float16):
            output_ids = self.model.generate(
                **inputs,
                max_new_tokens=gen_config.get("max_new_tokens", 2048),
                temperature=gen_config.get("temperature", 0.1),
                top_p=gen_config.get("top_p", 0.9),
                do_sample=gen_config.get("do_sample", False),
                use_cache=True,  # Explicitly enable cache for generation
            )

        # Decode
        # Handle both dict and BatchEncoding formats
        input_ids_list = inputs["input_ids"] if isinstance(inputs, dict) else inputs.input_ids
        generated_ids = [
            output_ids[len(input_ids):]
            for input_ids, output_ids in zip(input_ids_list, output_ids)
        ]

        output_text = self.processor.batch_decode(
            generated_ids,
            skip_special_tokens=True,
            clean_up_tokenization_spaces=True,
        )[0]

        processing_time = time.time() - start_time

        # Explicitly clear KV cache and tensors
        del output_ids
        del generated_ids
        if hasattr(self.model, 'past_key_values'):
            self.model.past_key_values = None
        del inputs
        torch.cuda.synchronize()

        # Clear cache to free memory
        self.clear_cache()
        
        return OCRResult(
            text=output_text,
            model_name=self.model_id,
            processing_time=processing_time,
            format="merge_custom",
            metadata={
                "image_size": image.size,
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
        Use Qwen3-VL to format text using visual verification.

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
            format_prompt = f"""Looking at this image, convert the following text to proper {target_format} format.

Context: {context or 'Document page'}

Text to format:
{text}

Verify the formatting against the image to ensure:
- Correct heading levels
- Proper list formatting
- Table structure
- Line numbers (if present)
- Speaker attributions (if dialogue)

Return only the formatted {target_format} output."""
        else:
            # Format the template with parameters
            format_prompt = format_prompt_template.format(
                context=context or "Document page",
                text=text,
                format=target_format
            )

        # Prepare messages for Qwen3-VL format
        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "image", "image": image},
                    {"type": "text", "text": format_prompt},
                ],
            }
        ]

        # Apply chat template
        text_prompt = self.processor.apply_chat_template(
            messages,
            tokenize=False,
            add_generation_prompt=True,
        )

        # Process vision info
        image_inputs, video_inputs = process_vision_info(messages)

        # Prepare inputs
        inputs = self.processor(
            text=[text_prompt],
            images=image_inputs,
            videos=video_inputs,
            padding=True,
            return_tensors="pt",
        )

        # Move to device (handle sharded models correctly)
        if hasattr(self.model, 'hf_device_map') and self.model.hf_device_map:
            # Check if model is truly sharded across multiple devices
            devices_used = set(self.model.hf_device_map.values()) if isinstance(self.model.hf_device_map, dict) else {self.model.hf_device_map}

            if len(devices_used) > 1:
                # Multi-device sharding detected
                # Move inputs to first GPU device, HF will handle inter-device routing
                first_device = f"cuda:{min(d for d in devices_used if isinstance(d, int))}"
                logger.warning(
                    f"Model is sharded across {len(devices_used)} devices: {devices_used}. "
                    f"Moving inputs to first device: {first_device}. "
                    f"Note: Sharding adds significant overhead and may cause instability."
                )
                print(f"⚠️  Model sharded across {devices_used} - inputs to {first_device}")

                # Move all tensor inputs to first device for HF's automatic routing
                inputs = {k: v.to(first_device) if isinstance(v, torch.Tensor) else v
                          for k, v in inputs.items()}
            else:
                # Single device (device_map='auto' but not actually sharded)
                target_device = next(iter(devices_used))
                logger.debug(f"Model on single device: {target_device}")
                inputs = {k: v.to(target_device) if isinstance(v, torch.Tensor) else v
                          for k, v in inputs.items()}
        else:
            # No device_map - use model's device
            logger.debug(f"Model on single device: {self.model.device}")
            inputs = inputs.to(self.model.device)
        
        # Merge generation configs
        gen_config = {**self.generation_config, **generation_kwargs}

        # Clear any cached KV from previous inference
        if hasattr(self.model, 'past_key_values'):
            self.model.past_key_values = None

        # Generate with automatic mixed precision (FP16 activations for memory efficiency)
        with torch.no_grad(), torch.amp.autocast('cuda', dtype=torch.float16):
            output_ids = self.model.generate(
                **inputs,
                max_new_tokens=gen_config.get("max_new_tokens", 2048),
                temperature=gen_config.get("temperature", 0.1),
                top_p=gen_config.get("top_p", 0.9),
                do_sample=gen_config.get("do_sample", False),
                use_cache=True,  # Explicitly enable cache for generation
            )

        # Decode
        # Handle both dict and BatchEncoding formats
        input_ids_list = inputs["input_ids"] if isinstance(inputs, dict) else inputs.input_ids
        generated_ids = [
            output_ids[len(input_ids):]
            for input_ids, output_ids in zip(input_ids_list, output_ids)
        ]

        output_text = self.processor.batch_decode(
            generated_ids,
            skip_special_tokens=True,
            clean_up_tokenization_spaces=True,
        )[0]

        processing_time = time.time() - start_time

        # Explicitly clear KV cache and tensors
        del output_ids
        del generated_ids
        if hasattr(self.model, 'past_key_values'):
            self.model.past_key_values = None
        del inputs
        torch.cuda.synchronize()

        # Clear cache to free memory
        self.clear_cache()
        
        return OCRResult(
            text=output_text,
            model_name=self.model_id,
            processing_time=processing_time,
            format=target_format,
            metadata={
                "image_size": image.size,
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

        start_time = time.time()

        # Truncate text
        text_sample = extracted_text[:2000]
        if len(extracted_text) > 2000:
            text_sample += "\n[... text truncated for validation ...]"

        validation_prompt = f"""Original document above.

Extracted text:
{text_sample}

Task: Compare extracted text to the image. Check if ALL structural elements captured:
- Line numbers (if present in margins)
- Table columns and alignment
- Headers and sections
- Q&A formatting
- No missing text regions

Response (one line only):
- "VALID" if complete and accurate
- "INVALID: [brief description of issues]" if problems exist

Your response:"""

        # Prepare messages for Qwen3-VL format
        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "image", "image": image},
                    {"type": "text", "text": validation_prompt},
                ],
            }
        ]

        # Apply chat template
        text_prompt = self.processor.apply_chat_template(
            messages, tokenize=False, add_generation_prompt=True
        )

        # Prepare inputs
        image_inputs, video_inputs = process_vision_info(messages)
        inputs = self.processor(
            text=[text_prompt],
            images=image_inputs,
            videos=video_inputs,
            padding=True,
            return_tensors="pt",
        )

        # Move to device (handle sharded models correctly)
        if hasattr(self.model, 'hf_device_map') and self.model.hf_device_map:
            # Check if model is truly sharded across multiple devices
            devices_used = set(self.model.hf_device_map.values()) if isinstance(self.model.hf_device_map, dict) else {self.model.hf_device_map}

            if len(devices_used) > 1:
                # Multi-device sharding detected
                # Move inputs to first GPU device, HF will handle inter-device routing
                first_device = f"cuda:{min(d for d in devices_used if isinstance(d, int))}"
                logger.warning(
                    f"Model is sharded across {len(devices_used)} devices: {devices_used}. "
                    f"Moving inputs to first device: {first_device}. "
                    f"Note: Sharding adds significant overhead and may cause instability."
                )
                print(f"⚠️  Model sharded across {devices_used} - inputs to {first_device}")

                # Move all tensor inputs to first device for HF's automatic routing
                inputs = {k: v.to(first_device) if isinstance(v, torch.Tensor) else v
                          for k, v in inputs.items()}
            else:
                # Single device (device_map='auto' but not actually sharded)
                target_device = next(iter(devices_used))
                logger.debug(f"Model on single device: {target_device}")
                inputs = {k: v.to(target_device) if isinstance(v, torch.Tensor) else v
                          for k, v in inputs.items()}
        else:
            # No device_map - use model's device
            logger.debug(f"Model on single device: {self.model.device}")
            inputs = inputs.to(self.model.device)

        # Generate with constraints
        gen_config = {
            "max_new_tokens": 50,
            "temperature": 0.0,
            **generation_kwargs
        }

        # Generate with automatic mixed precision (FP16 activations for memory efficiency)
        with torch.no_grad(), torch.amp.autocast('cuda', dtype=torch.float16):
            outputs = self.model.generate(
                **inputs,
                **gen_config
            )

        # Decode output
        output_text = self.processor.batch_decode(
            outputs, skip_special_tokens=True, clean_up_tokenization_spaces=False
        )[0]

        # Remove input prompt from output
        if text_prompt in output_text:
            output_text = output_text.replace(text_prompt, "").strip()

        processing_time = time.time() - start_time

        # Clear cache
        self.clear_cache()

        # Parse result
        result = output_text.strip()
        if result.startswith("VALID"):
            return True, ""
        elif result.startswith("INVALID"):
            description = result.replace("INVALID:", "").strip()
            return False, description
        else:
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

        # Truncate initial text
        text_sample = initial_text[:3000]
        if len(initial_text) > 3000:
            text_sample += "\n[... rest truncated ...]"

        refinement_prompt = f"""Context: {context or "Document page"}

Previous extraction had these issues:
{issues}

Initial extraction:
{text_sample}

Task: Re-extract the document text, paying special attention to the issues mentioned.
Ensure complete and accurate capture of ALL visible elements.

Corrected extraction:"""

        # Prepare messages
        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "image", "image": image},
                    {"type": "text", "text": refinement_prompt},
                ],
            }
        ]

        # Apply chat template
        text_prompt = self.processor.apply_chat_template(
            messages, tokenize=False, add_generation_prompt=True
        )

        # Prepare inputs
        image_inputs, video_inputs = process_vision_info(messages)
        inputs = self.processor(
            text=[text_prompt],
            images=image_inputs,
            videos=video_inputs,
            padding=True,
            return_tensors="pt",
        )

        # Move to device (handle sharded models correctly)
        if hasattr(self.model, 'hf_device_map') and self.model.hf_device_map:
            # Check if model is truly sharded across multiple devices
            devices_used = set(self.model.hf_device_map.values()) if isinstance(self.model.hf_device_map, dict) else {self.model.hf_device_map}

            if len(devices_used) > 1:
                # Multi-device sharding detected
                # Move inputs to first GPU device, HF will handle inter-device routing
                first_device = f"cuda:{min(d for d in devices_used if isinstance(d, int))}"
                logger.warning(
                    f"Model is sharded across {len(devices_used)} devices: {devices_used}. "
                    f"Moving inputs to first device: {first_device}. "
                    f"Note: Sharding adds significant overhead and may cause instability."
                )
                print(f"⚠️  Model sharded across {devices_used} - inputs to {first_device}")

                # Move all tensor inputs to first device for HF's automatic routing
                inputs = {k: v.to(first_device) if isinstance(v, torch.Tensor) else v
                          for k, v in inputs.items()}
            else:
                # Single device (device_map='auto' but not actually sharded)
                target_device = next(iter(devices_used))
                logger.debug(f"Model on single device: {target_device}")
                inputs = {k: v.to(target_device) if isinstance(v, torch.Tensor) else v
                          for k, v in inputs.items()}
        else:
            # No device_map - use model's device
            logger.debug(f"Model on single device: {self.model.device}")
            inputs = inputs.to(self.model.device)

        # Merge generation configs
        gen_config = {**self.generation_config, **generation_kwargs}

        # Generate with automatic mixed precision (FP16 activations for memory efficiency)
        with torch.no_grad(), torch.amp.autocast('cuda', dtype=torch.float16):
            outputs = self.model.generate(
                **inputs,
                **gen_config
            )

        # Decode
        output_text = self.processor.batch_decode(
            outputs, skip_special_tokens=True, clean_up_tokenization_spaces=False
        )[0]

        # Remove input prompt
        if text_prompt in output_text:
            output_text = output_text.replace(text_prompt, "").strip()

        processing_time = time.time() - start_time

        # Clear cache
        self.clear_cache()

        return OCRResult(
            text=output_text,
            model_name=self.model_id,
            processing_time=processing_time,
            format="refined",
            metadata={
                "image_size": image.size,
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
        del self.processor
        
        self.model = None
        self.processor = None
        self.is_loaded = False
        
        # Clear GPU cache
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
            torch.cuda.synchronize()
        
        print(f"✓ {self.model_id} unloaded")

