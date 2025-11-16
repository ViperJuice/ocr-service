"""
DeepSeek-OCR Inference Server

Minimal FastAPI server that wraps DeepSeek-OCR model for containerized execution.
Uses official transformers==4.46.3 with NO patches.

Features:
- Lazy loading: Model loads only on first inference request
- Resource assessment: Checks GPU memory before loading
- Multi-GPU support: Can distribute across available GPUs
- Explicit unload: /unload endpoint to free GPU memory
"""

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from transformers import AutoModel, AutoTokenizer
from PIL import Image
import torch
import base64
import io
import logging
from typing import Optional, List, Dict, Any, Union
import uuid
import time
import tempfile
import os
import shutil

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="DeepSeek-OCR Inference Server", version="1.0.0")

# Global model storage
model = None
tokenizer = None
model_device = None


class InferenceRequest(BaseModel):
    """Request model for single inference"""
    image_base64: str
    prompt: str
    base_size: int = 1024
    image_size: int = 640
    crop_mode: bool = True
    eval_mode: bool = True
    gpu_ids: Optional[List[int]] = None  # Optional: specify which GPU(s) to use
    auto_unload: bool = True  # Automatically unload model after inference completes


class InferenceResponse(BaseModel):
    """Response model for single inference"""
    text: str
    success: bool
    error: Optional[str] = None
    model_unloaded: bool = False  # Indicates if model was unloaded after inference
    model: str = "deepseek-ai/DeepSeek-OCR"  # Model identifier


class BatchInferenceItem(BaseModel):
    """Single item in batch inference request"""
    image_base64: str
    prompt: str
    base_size: int = 1024
    image_size: int = 640
    crop_mode: bool = True
    eval_mode: bool = True


class BatchInferenceRequest(BaseModel):
    """Request model for batch inference"""
    items: List[BatchInferenceItem]
    gpu_ids: Optional[List[int]] = None  # Optional: specify which GPU(s) to use
    auto_unload: bool = True  # Automatically unload model after batch completes


class BatchInferenceResultItem(BaseModel):
    """Single result item in batch inference response"""
    text: str
    success: bool
    error: Optional[str] = None
    index: int  # Index in original batch


class BatchInferenceResponse(BaseModel):
    """Response model for batch inference"""
    results: List[BatchInferenceResultItem]
    total_items: int
    successful_items: int
    failed_items: int
    batch_success: bool
    model_unloaded: bool  # Whether model was auto-unloaded after batch


class UnloadResponse(BaseModel):
    """Response model for unload"""
    success: bool
    message: str


# OpenAI-Compatible Models

class ChatMessage(BaseModel):
    """OpenAI-compatible chat message"""
    role: str
    content: Union[str, List[Dict[str, Any]]]


class ChatCompletionRequest(BaseModel):
    """OpenAI-compatible chat completion request"""
    model: str = "deepseek-ai/DeepSeek-OCR"
    messages: List[ChatMessage]
    max_tokens: int = 2048
    temperature: float = 0.0
    stream: bool = False
    # Container-specific extensions
    gpu_ids: Optional[List[int]] = None
    auto_unload: bool = True  # Automatically unload model after completion
    # DeepSeek-specific parameters
    base_size: int = 1024
    image_size: int = 640
    crop_mode: bool = True


class ChatCompletionResponse(BaseModel):
    """OpenAI-compatible chat completion response"""
    id: str
    object: str = "chat.completion"
    created: int
    model: str
    choices: List[Dict[str, Any]]
    usage: Dict[str, int]


def get_gpu_memory() -> List[dict]:
    """
    Get available memory for each GPU

    Returns:
        List of dicts with keys: id, total, used, free (all in MB)
    """
    if not torch.cuda.is_available():
        return []

    gpus = []
    for i in range(torch.cuda.device_count()):
        total = torch.cuda.get_device_properties(i).total_memory / (1024**2)
        allocated = torch.cuda.memory_allocated(i) / (1024**2)
        reserved = torch.cuda.memory_reserved(i) / (1024**2)
        free = total - reserved

        gpus.append({
            "id": i,
            "name": torch.cuda.get_device_name(i),
            "total": int(total),
            "used": int(allocated),
            "reserved": int(reserved),
            "free": int(free)
        })

    return gpus


def select_gpu(required_memory_mb: int = 14000, gpu_ids: Optional[List[int]] = None) -> int:
    """
    Select best GPU for model loading

    Args:
        required_memory_mb: Minimum free memory needed (default 14GB for DeepSeek-OCR)
        gpu_ids: Optional list of GPU IDs to consider (if None, considers all)

    Returns:
        GPU ID to use

    Raises:
        RuntimeError: If no suitable GPU found
    """
    gpus = get_gpu_memory()

    if not gpus:
        raise RuntimeError("No GPUs available")

    # Filter by specified GPU IDs if provided
    if gpu_ids is not None:
        gpus = [g for g in gpus if g["id"] in gpu_ids]
        if not gpus:
            raise RuntimeError(f"None of specified GPUs {gpu_ids} available")

    # Find GPU with most free memory
    gpus_sorted = sorted(gpus, key=lambda g: g["free"], reverse=True)
    best_gpu = gpus_sorted[0]

    logger.info(f"GPU memory status:")
    for gpu in gpus_sorted:
        logger.info(f"  GPU {gpu['id']} ({gpu['name']}): {gpu['free']}MB free / {gpu['total']}MB total")

    if best_gpu["free"] < required_memory_mb:
        raise RuntimeError(
            f"Insufficient GPU memory. Need {required_memory_mb}MB, "
            f"best GPU has {best_gpu['free']}MB free"
        )

    logger.info(f"Selected GPU {best_gpu['id']} with {best_gpu['free']}MB free")
    return best_gpu["id"]


def load_model_if_needed(gpu_ids: Optional[List[int]] = None):
    """
    Load model if not already loaded

    Uses Hugging Face AutoModel with device_map="auto" for intelligent GPU placement.

    Args:
        gpu_ids: Optional list of GPU IDs to use (for device_map filtering)
    """
    global model, tokenizer, model_device

    if model is not None:
        logger.info("Model already loaded")
        return

    logger.info("Loading DeepSeek-OCR model...")

    # Log GPU memory status before loading
    gpus = get_gpu_memory()
    logger.info("GPU memory status before loading:")
    for gpu in gpus:
        logger.info(f"  GPU {gpu['id']} ({gpu['name']}): {gpu['free']}MB free / {gpu['total']}MB total")

    try:
        # Load tokenizer first (CPU, minimal memory)
        # Use revision with masked_scatter fix (commit 1e3401a)
        tokenizer = AutoTokenizer.from_pretrained(
            "deepseek-ai/DeepSeek-OCR",
            revision="1e3401a3d4603e9e71ea0ec850bfead602191ec4",
            trust_remote_code=True
        )
        logger.info("✓ Tokenizer loaded")

        # Prepare device_map for HF transformers
        # If gpu_ids specified, create custom device map
        # Otherwise, use "auto" for HF's intelligent placement
        if gpu_ids is not None and len(gpu_ids) > 1:
            # Enable automatic sharding across specified GPUs
            device_map = "auto"
            os.environ["CUDA_VISIBLE_DEVICES"] = ",".join(map(str, gpu_ids))
            logger.info(f"Enabling model sharding across GPUs: {gpu_ids}")
        elif gpu_ids is not None and len(gpu_ids) == 1:
            # Single GPU specified
            device_map = f"cuda:{gpu_ids[0]}"
            logger.info(f"Using single GPU: {gpu_ids[0]}")
        else:
            # Let HF transformers decide optimal placement
            device_map = "auto"
            logger.info("Using device_map='auto' for HF-managed GPU placement")

        # Load model following official example
        # Use revision with masked_scatter fix (commit 1e3401a)
        try:
            model = AutoModel.from_pretrained(
                "deepseek-ai/DeepSeek-OCR",
                revision="1e3401a3d4603e9e71ea0ec850bfead602191ec4",
                trust_remote_code=True,
                _attn_implementation='flash_attention_2',
                use_safetensors=True
            )
            logger.info("Using flash_attention_2")
        except Exception as e:
            logger.warning(f"flash_attention_2 not available: {e}")
            logger.info("Falling back to eager attention")
            model = AutoModel.from_pretrained(
                "deepseek-ai/DeepSeek-OCR",
                revision="1e3401a3d4603e9e71ea0ec850bfead602191ec4",
                trust_remote_code=True,
                _attn_implementation='eager',
                use_safetensors=True
            )

        # Set eval mode and move to GPU (following official example)
        model = model.eval().cuda().to(torch.bfloat16)

        # Determine which device(s) the model is on
        if hasattr(model, 'hf_device_map'):
            model_device = str(model.hf_device_map)
            logger.info(f"  HF device map: {model.hf_device_map}")
        else:
            model_device = str(device_map)

        logger.info("✓ DeepSeek-OCR model loaded successfully")
        logger.info(f"  Device map: {model_device}")
        logger.info(f"  Dtype: torch.bfloat16")

        # Log final memory usage
        final_memory = get_gpu_memory()
        logger.info("GPU memory status after loading:")
        for gpu in final_memory:
            logger.info(f"  GPU {gpu['id']}: {gpu['used']}MB used, {gpu['free']}MB free")

    except Exception as e:
        logger.error(f"Failed to load model: {e}")
        model = None
        tokenizer = None
        model_device = None
        raise


def parse_openai_message_to_deepseek(messages: List[ChatMessage]) -> tuple[str, str]:
    """
    Extract image base64 and text prompt from OpenAI message format.

    OpenAI format:
    [{"role": "user", "content": [
        {"type": "text", "text": "..."},
        {"type": "image_url", "image_url": {"url": "data:image/..."}}
    ]}]

    DeepSeek format:
    (image_base64, prompt)

    Args:
        messages: List of OpenAI-format ChatMessage objects

    Returns:
        Tuple of (image_base64, prompt)
    """
    image_base64 = None
    prompt_parts = []

    for message in messages:
        if isinstance(message.content, str):
            # Simple string content
            prompt_parts.append(message.content)
        elif isinstance(message.content, list):
            # Structured content with text and images
            for item in message.content:
                if item["type"] == "text":
                    prompt_parts.append(item["text"])
                elif item["type"] == "image_url":
                    # Extract base64 from data URL
                    url = item["image_url"]["url"]
                    if url.startswith("data:image"):
                        # Data URL format: data:image/png;base64,...
                        image_base64 = url.split(",", 1)[1]
                    else:
                        # External URL (not implemented yet)
                        logger.warning(f"External image URLs not supported: {url}")

    prompt = " ".join(prompt_parts)
    return image_base64, prompt


def unload_model():
    """Unload model from GPU to free memory"""
    global model, tokenizer, model_device

    if model is None:
        logger.info("Model not loaded, nothing to unload")
        return

    logger.info("Unloading DeepSeek-OCR model...")

    # Delete model and clear cache
    del model
    del tokenizer
    model = None
    tokenizer = None
    model_device = None

    # Clear GPU cache on all available GPUs
    if torch.cuda.is_available():
        for i in range(torch.cuda.device_count()):
            with torch.cuda.device(i):
                torch.cuda.empty_cache()

    logger.info("✓ Model unloaded")

    # Log freed memory for all GPUs
    gpus = get_gpu_memory()
    for gpu in gpus:
        logger.info(f"  GPU {gpu['id']} memory: {gpu['used']}MB used, {gpu['free']}MB free")


@app.get("/health")
async def health():
    """Health check endpoint"""
    return {
        "status": "ready",
        "model_loaded": model is not None,
        "device": model_device if model is not None else None
    }


@app.get("/info")
async def info():
    """Model information endpoint"""
    gpu_memory = get_gpu_memory()

    return {
        "model": "deepseek-ai/DeepSeek-OCR",
        "transformers_version": "4.46.3",
        "model_loaded": model is not None,
        "device": model_device if model is not None else None,
        "dtype": str(model.dtype) if model is not None else None,
        "gpu_memory": gpu_memory
    }


@app.post("/unload", response_model=UnloadResponse)
async def unload():
    """
    Unload model from GPU

    Returns:
        UnloadResponse indicating success
    """
    try:
        unload_model()
        return UnloadResponse(success=True, message="Model unloaded successfully")
    except Exception as e:
        logger.error(f"Failed to unload model: {e}")
        return UnloadResponse(success=False, message=str(e))


@app.post("/infer", response_model=InferenceResponse)
async def infer(request: InferenceRequest):
    """
    Run OCR inference on an image

    Model will be loaded automatically if not already loaded.

    Args:
        request: InferenceRequest containing base64-encoded image and parameters

    Returns:
        InferenceResponse with extracted text or error
    """
    try:
        # Load model if needed (lazy loading)
        load_model_if_needed(gpu_ids=request.gpu_ids)

        if model is None or tokenizer is None:
            raise HTTPException(status_code=503, detail="Failed to load model")

        # Decode base64 image
        logger.info(f"Decoding image (base64 length: {len(request.image_base64)})")
        image_bytes = base64.b64decode(request.image_base64)
        image = Image.open(io.BytesIO(image_bytes))
        logger.info(f"  Image size: {image.size}, mode: {image.mode}")

        # Save image to temporary file (required by model.infer())
        with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as tmp_file:
            tmp_path = tmp_file.name
            image.save(tmp_path, format='PNG')

        # Create temporary output directory
        tmp_output_dir = tempfile.mkdtemp()

        # Format prompt with <image> token prefix
        formatted_prompt = request.prompt
        if not formatted_prompt.startswith('<image>'):
            formatted_prompt = f"<image>\n{formatted_prompt}"

        # Run inference using model.infer()
        logger.info(f"Running model.infer() with prompt: '{formatted_prompt[:50]}...'")
        result = model.infer(
            tokenizer,
            prompt=formatted_prompt,
            image_file=tmp_path,
            output_path=tmp_output_dir,
            base_size=request.base_size,
            image_size=request.image_size,
            crop_mode=request.crop_mode,
            eval_mode=True,  # CRITICAL: Required to return text
            save_results=False,
            test_compress=False
        )

        # Cleanup temporary files
        os.unlink(tmp_path)
        shutil.rmtree(tmp_output_dir)

        logger.info(f"✓ Inference complete (output length: {len(result) if result else 0} chars)")

        # Auto-unload if requested (default: True)
        model_unloaded = False
        if request.auto_unload:
            logger.info("Auto-unloading model after inference completion")
            unload_model()
            model_unloaded = True

        return InferenceResponse(text=result or "", success=True, model_unloaded=model_unloaded)

    except Exception as e:
        logger.error(f"Inference failed: {e}", exc_info=True)
        return InferenceResponse(text="", success=False, error=str(e))


@app.post("/batch_infer", response_model=BatchInferenceResponse)
async def batch_infer(request: BatchInferenceRequest):
    """
    Run OCR inference on multiple images in a batch

    Model will be loaded automatically if not already loaded, and will stay loaded
    for the entire batch. Optionally auto-unloads after batch completes.

    Args:
        request: BatchInferenceRequest containing list of images and parameters

    Returns:
        BatchInferenceResponse with results for each item
    """
    results = []
    successful_count = 0
    failed_count = 0

    try:
        # Load model once for entire batch (lazy loading)
        logger.info(f"Starting batch inference for {len(request.items)} items")
        load_model_if_needed(gpu_ids=request.gpu_ids)

        if model is None or tokenizer is None:
            raise HTTPException(status_code=503, detail="Failed to load model")

        # Process each item in the batch
        for idx, item in enumerate(request.items):
            try:
                logger.info(f"Processing batch item {idx + 1}/{len(request.items)}")

                # Decode base64 image
                image_bytes = base64.b64decode(item.image_base64)
                image = Image.open(io.BytesIO(image_bytes))
                logger.debug(f"  Image {idx}: {image.size}, mode: {image.mode}")

                # Save image to temporary file (required by model.infer())
                with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as tmp_file:
                    tmp_path = tmp_file.name
                    image.save(tmp_path, format='PNG')

                # Create temporary output directory
                tmp_output_dir = tempfile.mkdtemp()

                # Format prompt with <image> token prefix
                formatted_prompt = item.prompt
                if not formatted_prompt.startswith('<image>'):
                    formatted_prompt = f"<image>\n{formatted_prompt}"

                # Run inference using model.infer() with eval_mode=True
                result = model.infer(
                    tokenizer,
                    prompt=formatted_prompt,
                    image_file=tmp_path,
                    output_path=tmp_output_dir,
                    base_size=item.base_size,
                    image_size=item.image_size,
                    crop_mode=item.crop_mode,
                    eval_mode=True,  # CRITICAL: Required for return value
                    save_results=False,
                    test_compress=False
                )

                # Cleanup temporary files
                os.unlink(tmp_path)
                shutil.rmtree(tmp_output_dir)

                # Append successful result
                results.append(BatchInferenceResultItem(
                    text=result or "",
                    success=True,
                    error=None,
                    index=idx
                ))
                successful_count += 1
                logger.info(f"✓ Item {idx + 1} complete ({len(result)} chars)")

            except Exception as e:
                # Append failed result but continue processing batch
                logger.error(f"✗ Item {idx + 1} failed: {e}")
                results.append(BatchInferenceResultItem(
                    text="",
                    success=False,
                    error=str(e),
                    index=idx
                ))
                failed_count += 1

        # Auto-unload if requested
        model_unloaded = False
        if request.auto_unload:
            logger.info("Auto-unloading model after batch completion")
            unload_model()
            model_unloaded = True

        logger.info(f"✓ Batch complete: {successful_count} succeeded, {failed_count} failed")

        return BatchInferenceResponse(
            results=results,
            total_items=len(request.items),
            successful_items=successful_count,
            failed_items=failed_count,
            batch_success=(failed_count == 0),
            model_unloaded=model_unloaded
        )

    except Exception as e:
        logger.error(f"Batch inference failed: {e}", exc_info=True)
        # Return partial results if any were processed
        return BatchInferenceResponse(
            results=results,
            total_items=len(request.items),
            successful_items=successful_count,
            failed_items=len(request.items) - successful_count,
            batch_success=False,
            model_unloaded=False
        )


# OpenAI-Compatible Endpoints

@app.get("/v1/models")
async def list_models():
    """
    OpenAI-compatible models list endpoint

    Returns:
        List of available models in OpenAI format
    """
    return {
        "object": "list",
        "data": [{
            "id": "deepseek-ai/DeepSeek-OCR",
            "object": "model",
            "created": 1234567890,
            "owned_by": "deepseek-ai"
        }]
    }


@app.post("/v1/chat/completions")
async def chat_completions(request: ChatCompletionRequest):
    """
    OpenAI-compatible chat completions endpoint (non-streaming)

    Supports OpenAI vision message format with text and image_url content types.
    Model will be loaded automatically if not already loaded.

    Args:
        request: ChatCompletionRequest in OpenAI format

    Returns:
        ChatCompletionResponse in OpenAI format
    """
    try:
        # Load model if needed (lazy loading)
        load_model_if_needed(gpu_ids=request.gpu_ids)

        if model is None or tokenizer is None:
            raise HTTPException(status_code=503, detail="Failed to load model")

        # Convert OpenAI format to DeepSeek format
        logger.info(f"Converting {len(request.messages)} OpenAI messages to DeepSeek format")
        image_base64, prompt = parse_openai_message_to_deepseek(request.messages)

        if not image_base64:
            raise HTTPException(status_code=400, detail="No image provided in messages")

        # Decode image
        logger.info(f"Decoding image (base64 length: {len(image_base64)})")
        image_bytes = base64.b64decode(image_base64)
        image = Image.open(io.BytesIO(image_bytes))
        logger.info(f"  Image size: {image.size}, mode: {image.mode}")

        # Save image to temporary file (required by model.infer())
        with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as tmp_file:
            tmp_path = tmp_file.name
            image.save(tmp_path, format='PNG')

        # Create temporary output directory
        tmp_output_dir = tempfile.mkdtemp()

        # Format prompt with <image> token prefix
        formatted_prompt = prompt
        if not formatted_prompt.startswith('<image>'):
            formatted_prompt = f"<image>\n{formatted_prompt}"

        # Run inference using model.infer() with eval_mode=True
        logger.info(f"Running model.infer() with prompt: '{formatted_prompt[:50]}...'")
        result = model.infer(
            tokenizer,
            prompt=formatted_prompt,
            image_file=tmp_path,
            output_path=tmp_output_dir,
            base_size=1024,
            image_size=640,  # Official parameter (NOT 1024)
            crop_mode=True,
            eval_mode=True,  # CRITICAL: Required for return value
            save_results=False,
            test_compress=False
        )

        # Cleanup temporary files
        os.unlink(tmp_path)
        shutil.rmtree(tmp_output_dir)

        logger.info(f"✓ Inference complete (output length: {len(result) if result else 0} chars)")
        logger.info(f"  Result preview: {result[:200] if result else 'None'}...")

        # Auto-unload if requested (default: True)
        if request.auto_unload:
            logger.info("Auto-unloading model after chat completion")
            unload_model()

        # Format as OpenAI response
        return {
            "id": f"chatcmpl-{uuid.uuid4()}",
            "object": "chat.completion",
            "created": int(time.time()),
            "model": request.model,
            "choices": [{
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": result
                },
                "finish_reason": "stop"
            }],
            "usage": {
                "prompt_tokens": 0,  # Not available from DeepSeek
                "completion_tokens": 0,
                "total_tokens": 0
            }
        }

    except Exception as e:
        logger.error(f"Chat completion failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)
