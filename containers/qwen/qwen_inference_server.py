"""
Qwen3-VL Inference Server

Minimal FastAPI server that wraps Qwen3-VL model for containerized execution.
Uses transformers>=4.57.0 from source with official Qwen3-VL support.

Features:
- Lazy loading: Model loads only on first inference request
- Resource assessment: Checks GPU memory before loading
- Multi-GPU support: Can distribute across available GPUs
- Explicit unload: /unload endpoint to free GPU memory
"""

from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from transformers import Qwen3VLForConditionalGeneration, AutoProcessor, TextIteratorStreamer
from qwen_vl_utils import process_vision_info
from PIL import Image
import torch
import base64
import io
import logging
from typing import Optional, Dict, Any, List, Union
import uuid
import time
import json
import asyncio
from threading import Thread
import os

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Qwen3-VL Inference Server", version="1.0.0")

# Global model storage
model = None
processor = None
model_device = None


class InferenceRequest(BaseModel):
    """Request model for single inference"""
    image_base64: str
    messages: List[Dict[str, Any]]  # Qwen chat format
    max_new_tokens: int = 2048
    gpu_ids: Optional[List[int]] = None  # Optional: specify which GPU(s) to use
    auto_unload: bool = True  # Automatically unload model after inference completes


class InferenceResponse(BaseModel):
    """Response model for single inference"""
    text: str
    success: bool
    error: Optional[str] = None
    model_unloaded: bool = False  # Indicates if model was unloaded after inference


class BatchInferenceItem(BaseModel):
    """Single item in batch inference request"""
    image_base64: str
    messages: List[Dict[str, Any]]  # Qwen chat format
    max_new_tokens: int = 2048


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
    model: str = "Qwen/Qwen3-VL-8B-Instruct"
    messages: List[ChatMessage]
    max_tokens: int = 2048
    temperature: float = 0.0
    stream: bool = False
    # Container-specific extensions
    gpu_ids: Optional[List[int]] = None
    auto_unload: bool = True  # Automatically unload model after completion


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


def select_gpu(required_memory_mb: int = 17000, gpu_ids: Optional[List[int]] = None) -> int:
    """
    Select best GPU for model loading

    Args:
        required_memory_mb: Minimum free memory needed (default 17GB for Qwen3-VL)
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

    Uses Hugging Face device_map="auto" for intelligent GPU placement.
    HF transformers will automatically:
    - Select best GPU(s) based on available memory
    - Shard model across GPUs if beneficial for accuracy
    - Optimize tensor placement for performance

    Args:
        gpu_ids: Optional list of GPU IDs to use (for device_map filtering)
    """
    global model, processor, model_device

    if model is not None:
        logger.info("Model already loaded")
        return

    logger.info("Loading Qwen3-VL model...")

    # Log GPU memory status before loading
    gpus = get_gpu_memory()
    logger.info("GPU memory status before loading:")
    for gpu in gpus:
        logger.info(f"  GPU {gpu['id']} ({gpu['name']}): {gpu['free']}MB free / {gpu['total']}MB total")

    try:
        # Load processor first (CPU, minimal memory)
        processor = AutoProcessor.from_pretrained("Qwen/Qwen3-VL-8B-Instruct")
        logger.info("✓ Processor loaded")

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

        # Load model with HF-managed device placement
        # Using official Qwen3-VL model class
        try:
            model = Qwen3VLForConditionalGeneration.from_pretrained(
                "Qwen/Qwen3-VL-8B-Instruct",
                torch_dtype=torch.bfloat16,
                device_map=device_map,
                attn_implementation="flash_attention_2"  # Recommended for performance
            )
            logger.info("✓ Using flash_attention_2 for acceleration")
        except Exception as e:
            logger.warning(f"flash_attention_2 not available: {e}")
            logger.info("Falling back to eager attention")
            model = Qwen3VLForConditionalGeneration.from_pretrained(
                "Qwen/Qwen3-VL-8B-Instruct",
                torch_dtype=torch.bfloat16,
                device_map=device_map,
                attn_implementation="eager"
            )

        # Determine which device(s) the model is on
        if hasattr(model, 'hf_device_map'):
            model_device = str(model.hf_device_map)
            logger.info(f"  HF device map: {model.hf_device_map}")
        else:
            model_device = str(device_map)

        logger.info("✓ Qwen3-VL model loaded successfully")
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
        processor = None
        model_device = None
        raise


def parse_openai_message_to_qwen(messages: List[ChatMessage]) -> List[Dict[str, Any]]:
    """
    Convert OpenAI message format to Qwen format.

    OpenAI format:
    [{"role": "user", "content": [
        {"type": "text", "text": "..."},
        {"type": "image_url", "image_url": {"url": "data:image/..."}}
    ]}]

    Qwen format:
    [{"role": "user", "content": [
        {"type": "text", "text": "..."},
        {"type": "image", "image": <PIL.Image>}
    ]}]

    Args:
        messages: List of OpenAI-format ChatMessage objects

    Returns:
        List of Qwen-format message dicts
    """
    qwen_messages = []

    for message in messages:
        qwen_content = []

        if isinstance(message.content, str):
            # Simple string content
            qwen_content.append({"type": "text", "text": message.content})
        elif isinstance(message.content, list):
            # Structured content with text and images
            for item in message.content:
                if item["type"] == "text":
                    qwen_content.append({"type": "text", "text": item["text"]})
                elif item["type"] == "image_url":
                    # Extract and decode image from URL
                    url = item["image_url"]["url"]
                    if url.startswith("data:image"):
                        # Data URL format: data:image/png;base64,...
                        image_base64 = url.split(",", 1)[1]
                        image_bytes = base64.b64decode(image_base64)
                        image = Image.open(io.BytesIO(image_bytes))
                        qwen_content.append({"type": "image", "image": image})
                    else:
                        # External URL (not implemented yet)
                        logger.warning(f"External image URLs not supported: {url}")

        qwen_messages.append({
            "role": message.role,
            "content": qwen_content
        })

    return qwen_messages


def unload_model():
    """Unload model from GPU to free memory"""
    global model, processor, model_device

    if model is None:
        logger.info("Model not loaded, nothing to unload")
        return

    logger.info("Unloading Qwen3-VL model...")

    # Delete model and clear cache
    del model
    del processor
    model = None
    processor = None
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
        "processor_loaded": processor is not None,
        "device": model_device if model is not None else None
    }


@app.get("/info")
async def info():
    """Model information endpoint"""
    gpu_memory = get_gpu_memory()

    return {
        "model": "Qwen/Qwen3-VL-8B-Instruct",
        "transformers_version": "4.57.0+",
        "model_loaded": model is not None,
        "device": model_device if model is not None else None,
        "dtype": "torch.bfloat16" if model is not None else None,
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
    Run vision-language inference

    Model will be loaded automatically if not already loaded.

    Args:
        request: InferenceRequest containing base64-encoded image and chat messages

    Returns:
        InferenceResponse with model output or error
    """
    try:
        # Load model if needed (lazy loading)
        load_model_if_needed(gpu_ids=request.gpu_ids)

        if model is None or processor is None:
            raise HTTPException(status_code=503, detail="Failed to load model")

        # Decode base64 image
        logger.info(f"Decoding image (base64 length: {len(request.image_base64)})")
        image_bytes = base64.b64decode(request.image_base64)
        image = Image.open(io.BytesIO(image_bytes))
        logger.info(f"  Image size: {image.size}, mode: {image.mode}")

        # Format messages with image (replace <image> token with actual image object)
        messages_with_image = []
        for msg in request.messages:
            if "<image>" in str(msg.get("content", "")):
                content_parts = []
                content_parts.append({"type": "image", "image": image})
                text_content = str(msg["content"]).replace("<image>", "").strip()
                if text_content:
                    content_parts.append({"type": "text", "text": text_content})
                messages_with_image.append({
                    "role": msg["role"],
                    "content": content_parts
                })
            else:
                messages_with_image.append(msg)

        logger.info(f"Running inference with {len(messages_with_image)} messages")

        # Prepare inputs
        text = processor.apply_chat_template(
            messages_with_image,
            tokenize=False,
            add_generation_prompt=True
        )
        image_inputs, video_inputs = process_vision_info(messages_with_image)
        inputs = processor(
            text=[text],
            images=image_inputs,
            videos=video_inputs,
            padding=True,
            return_tensors="pt"
        )
        inputs = inputs.to(model.device)

        # Generate
        output_ids = model.generate(**inputs, max_new_tokens=request.max_new_tokens)
        output_text = processor.batch_decode(
            output_ids,
            skip_special_tokens=True,
            clean_up_tokenization_spaces=False
        )[0]

        logger.info(f"✓ Inference complete (output length: {len(output_text)} chars)")

        # Auto-unload if requested (default: True)
        model_unloaded = False
        if request.auto_unload:
            logger.info("Auto-unloading model after inference completion")
            unload_model()
            model_unloaded = True

        return InferenceResponse(text=output_text, success=True, model_unloaded=model_unloaded)

    except Exception as e:
        logger.error(f"Inference failed: {e}", exc_info=True)
        return InferenceResponse(text="", success=False, error=str(e))


@app.post("/batch_infer", response_model=BatchInferenceResponse)
async def batch_infer(request: BatchInferenceRequest):
    """
    Run vision-language inference on multiple images in a batch

    Model will be loaded automatically if not already loaded, and will stay loaded
    for the entire batch. Optionally auto-unloads after batch completes.

    Args:
        request: BatchInferenceRequest containing list of images and messages

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

        if model is None or processor is None:
            raise HTTPException(status_code=503, detail="Failed to load model")

        # Process each item in the batch
        for idx, item in enumerate(request.items):
            try:
                logger.info(f"Processing batch item {idx + 1}/{len(request.items)}")

                # Decode base64 image
                image_bytes = base64.b64decode(item.image_base64)
                image = Image.open(io.BytesIO(image_bytes))
                logger.debug(f"  Image {idx}: {image.size}, mode: {image.mode}")

                # Format messages with image
                messages_with_image = []
                for msg in item.messages:
                    if "<image>" in str(msg.get("content", "")):
                        content_parts = []
                        content_parts.append({"type": "image", "image": image})
                        text_content = str(msg["content"]).replace("<image>", "").strip()
                        if text_content:
                            content_parts.append({"type": "text", "text": text_content})
                        messages_with_image.append({
                            "role": msg["role"],
                            "content": content_parts
                        })
                    else:
                        messages_with_image.append(msg)

                # Prepare inputs
                text = processor.apply_chat_template(
                    messages_with_image,
                    tokenize=False,
                    add_generation_prompt=True
                )
                image_inputs, video_inputs = process_vision_info(messages_with_image)
                inputs = processor(
                    text=[text],
                    images=image_inputs,
                    videos=video_inputs,
                    padding=True,
                    return_tensors="pt"
                )
                inputs = inputs.to(model.device)

                # Generate
                output_ids = model.generate(**inputs, max_new_tokens=item.max_new_tokens)
                output_text = processor.batch_decode(
                    output_ids,
                    skip_special_tokens=True,
                    clean_up_tokenization_spaces=False
                )[0]

                # Append successful result
                results.append(BatchInferenceResultItem(
                    text=output_text,
                    success=True,
                    error=None,
                    index=idx
                ))
                successful_count += 1
                logger.info(f"✓ Item {idx + 1} complete ({len(output_text)} chars)")

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
            "id": "Qwen/Qwen3-VL-8B-Instruct",
            "object": "model",
            "created": 1234567890,
            "owned_by": "Qwen"
        }]
    }


@app.post("/v1/chat/completions")
async def chat_completions(request: ChatCompletionRequest):
    """
    OpenAI-compatible chat completions endpoint with streaming support

    Supports OpenAI vision message format with text and image_url content types.
    Model will be loaded automatically if not already loaded.

    Args:
        request: ChatCompletionRequest in OpenAI format

    Returns:
        ChatCompletionResponse in OpenAI format (streaming or non-streaming)
    """
    try:
        # Load model if needed (lazy loading)
        load_model_if_needed(gpu_ids=request.gpu_ids)

        if model is None or processor is None:
            raise HTTPException(status_code=503, detail="Failed to load model")

        # Convert OpenAI format to Qwen format
        logger.info(f"Converting {len(request.messages)} OpenAI messages to Qwen format")
        qwen_messages = parse_openai_message_to_qwen(request.messages)

        # Prepare inputs (same as /infer endpoint)
        text = processor.apply_chat_template(
            qwen_messages,
            tokenize=False,
            add_generation_prompt=True
        )
        image_inputs, video_inputs = process_vision_info(qwen_messages)
        inputs = processor(
            text=[text],
            images=image_inputs,
            videos=video_inputs,
            padding=True,
            return_tensors="pt"
        )
        inputs = inputs.to(model.device)

        if request.stream:
            # STREAMING RESPONSE
            logger.info("Running streaming inference...")

            async def stream_generator():
                completion_id = f"chatcmpl-{uuid.uuid4()}"
                created = int(time.time())

                try:
                    # Create streamer
                    streamer = TextIteratorStreamer(
                        processor.tokenizer,
                        skip_special_tokens=True,
                        skip_prompt=True
                    )

                    generation_kwargs = {
                        **inputs,
                        "max_new_tokens": request.max_tokens,
                        "temperature": request.temperature if request.temperature > 0 else None,
                        "do_sample": request.temperature > 0,
                        "streamer": streamer,
                    }

                    # Run generation in background thread
                    thread = Thread(target=model.generate, kwargs=generation_kwargs)
                    thread.start()

                    # Stream tokens as they're generated
                    for text_chunk in streamer:
                        chunk = {
                            "id": completion_id,
                            "object": "chat.completion.chunk",
                            "created": created,
                            "model": request.model,
                            "choices": [{
                                "index": 0,
                                "delta": {"content": text_chunk},
                                "finish_reason": None
                            }]
                        }
                        yield f"data: {json.dumps(chunk)}\n\n"
                        await asyncio.sleep(0)  # Allow other tasks to run

                    # Send final chunk
                    final_chunk = {
                        "id": completion_id,
                        "object": "chat.completion.chunk",
                        "created": created,
                        "model": request.model,
                        "choices": [{
                            "index": 0,
                            "delta": {},
                            "finish_reason": "stop"
                        }]
                    }
                    yield f"data: {json.dumps(final_chunk)}\n\n"
                    yield "data: [DONE]\n\n"

                    # Wait for thread to complete
                    thread.join()
                    logger.info("✓ Streaming inference complete")

                    # Auto-unload if requested (default: True)
                    if request.auto_unload:
                        logger.info("Auto-unloading model after streaming completion")
                        unload_model()

                except Exception as e:
                    logger.error(f"Streaming inference failed: {e}", exc_info=True)
                    error_chunk = {
                        "id": completion_id,
                        "object": "error",
                        "created": created,
                        "error": {"message": str(e), "type": "internal_error"}
                    }
                    yield f"data: {json.dumps(error_chunk)}\n\n"

            return StreamingResponse(
                stream_generator(),
                media_type="text/event-stream",
                headers={
                    "Cache-Control": "no-cache",
                    "Connection": "keep-alive",
                    "X-Accel-Buffering": "no"
                }
            )

        else:
            # NON-STREAMING RESPONSE
            logger.info("Running non-streaming inference...")

            output_ids = model.generate(
                **inputs,
                max_new_tokens=request.max_tokens,
                temperature=request.temperature if request.temperature > 0 else None,
                do_sample=request.temperature > 0
            )
            output_text = processor.batch_decode(
                output_ids,
                skip_special_tokens=True,
                clean_up_tokenization_spaces=False
            )[0]

            logger.info(f"✓ Inference complete (output length: {len(output_text)} chars)")

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
                        "content": output_text
                    },
                    "finish_reason": "stop"
                }],
                "usage": {
                    "prompt_tokens": 0,  # Not available from model
                    "completion_tokens": 0,
                    "total_tokens": 0
                }
            }

    except Exception as e:
        logger.error(f"Chat completion failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8002)
