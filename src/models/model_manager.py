"""Model manager for loading and switching between models."""
import gc
import time
from typing import Dict, Optional, Literal
import torch

from .base import BaseVLModel
from .qwen_vl import QwenVLModel
from .deepseek_ocr import DeepSeekOCRModel


ModelName = Literal["qwen3-vl-8b", "qwen3-vl-4b", "qwen3-vl-2b", "deepseek-ocr"]


class ModelManager:
    """Manage multiple vision-language models with lazy loading."""
    
    def __init__(self, model_configs: Dict[str, Dict]):
        """
        Initialize model manager.
        
        Args:
            model_configs: Dictionary of model configurations from YAML
        """
        self.model_configs = model_configs
        self.loaded_models: Dict[str, BaseVLModel] = {}
        self.current_model_name: Optional[str] = None
    
    def _clear_gpu_cache(self) -> None:
        """
        Aggressively clear GPU cache before model loading.
        
        This performs three levels of cleanup:
        1. Empty CUDA cache (free unused cached memory)
        2. Synchronize all CUDA operations (ensure completion)
        3. Python garbage collection (clean up Python objects)
        """
        if torch.cuda.is_available():
            # Empty the CUDA cache
            torch.cuda.empty_cache()
            
            # Ensure all CUDA operations complete
            torch.cuda.synchronize()
            
            # Force Python garbage collection
            gc.collect()
    
    def _detect_display_gpu(self) -> Optional[int]:
        """
        Attempt to detect which GPU is used for display/desktop.
        
        Uses heuristic: GPU with highest initial memory allocation
        is likely the display GPU (due to desktop compositor, X server, etc).
        
        Returns:
            GPU ID to avoid (likely display GPU), or None if:
            - Only 1 GPU available
            - Can't determine (allocation difference < 1GB)
            - CUDA not available
        """
        if not torch.cuda.is_available():
            return None
        
        gpu_count = torch.cuda.device_count()
        if gpu_count < 2:
            return None
        
        # Get initial allocations for all GPUs
        allocations = []
        for i in range(gpu_count):
            allocated_gb = torch.cuda.memory_allocated(i) / (1024**3)
            allocations.append((i, allocated_gb))
        
        # Sort by allocation (highest first)
        allocations.sort(key=lambda x: x[1], reverse=True)
        
        # If highest allocation is >1GB more than second highest,
        # it's likely the display GPU
        if len(allocations) >= 2:
            highest_gpu, highest_alloc = allocations[0]
            second_gpu, second_alloc = allocations[1]
            
            if highest_alloc - second_alloc > 1.0:
                return highest_gpu
        
        return None
    
    def load_model(
        self, 
        model_name: ModelName, 
        force_reload: bool = False,
        quantization: Optional[str] = None,
        enable_cache_clearing: bool = True,
        prefer_non_display_gpu: bool = True,
        force_disable_crop: bool = False
    ) -> BaseVLModel:
        """
        Load a model by name.
        
        Args:
            model_name: Name of the model to load
            force_reload: Force reload even if already loaded
            quantization: Quantization mode ("int8", "int4", or None)
            enable_cache_clearing: Whether to clear GPU cache before loading
            prefer_non_display_gpu: Try to avoid display GPU if detected
            force_disable_crop: Disable crop mode in DeepSeek models
            
        Returns:
            Loaded model instance
            
        Raises:
            ValueError: If model name is not found in configs
        """
        if model_name not in self.model_configs:
            available = ", ".join(self.model_configs.keys())
            raise ValueError(
                f"Model '{model_name}' not found. Available models: {available}"
            )
        
        # Return existing model if already loaded
        if model_name in self.loaded_models and not force_reload:
            print(f"Model '{model_name}' is already loaded.")
            return self.loaded_models[model_name]
        
        # Unload if forcing reload
        if force_reload and model_name in self.loaded_models:
            self.unload_model(model_name)
        
        # === NEW: Clear GPU cache before loading ===
        if enable_cache_clearing:
            self._clear_gpu_cache()
        
        # Get model config
        config = self.model_configs[model_name]
        model_id = config["model_id"]

        # Deep copy to prevent mutation of original config
        import copy
        model_config = copy.deepcopy(config.get("config", {}))
        prompts = config.get("prompts", {})

        # DEBUG: Check if max_memory is present
        if 'max_memory' in model_config:
            print(f"[DEBUG] max_memory found in config: {model_config['max_memory']}")
        if model_config.get('device_map') == 'auto':
            print(f"[DEBUG] device_map is 'auto', max_memory present: {'max_memory' in model_config}")

        # === NEW: Detect and avoid display GPU ===
        if prefer_non_display_gpu:
            display_gpu = self._detect_display_gpu()
            if display_gpu is not None:
                # Only modify if device_map is 'auto' AND not using sharding
                # If max_memory is configured, it means sharding is intended - don't override
                if model_config.get('device_map') == 'auto' and 'max_memory' not in model_config:
                    # Get list of non-display GPUs
                    non_display_gpus = [
                        i for i in range(torch.cuda.device_count())
                        if i != display_gpu
                    ]

                    if non_display_gpus:
                        # Force to first non-display GPU
                        preferred_gpu = non_display_gpus[0]
                        model_config['device_map'] = f"cuda:{preferred_gpu}"

                        print(f"  Avoiding display GPU {display_gpu}, using GPU {preferred_gpu}")
        
        # Create appropriate model instance
        if "qwen" in model_name.lower():
            model = QwenVLModel(
                model_id=model_id,
                config=model_config,
                prompts=prompts,
                quantization=quantization,
            )
        elif "deepseek" in model_name.lower():
            infer_config = config.get("infer_config", {})
            model = DeepSeekOCRModel(
                model_id=model_id,
                config=model_config,
                prompts=prompts,
                infer_config=infer_config,
                quantization=quantization,
                force_disable_crop=force_disable_crop,
            )
        else:
            raise ValueError(f"Unknown model type for '{model_name}'")
        
        # Load the model
        print(f"Loading {model.__class__.__name__} model: {model_id}")
        model.load()
        
        # Store the model
        self.loaded_models[model_name] = model
        self.current_model_name = model_name
        
        return model
    
    def unload_model(self, model_name: ModelName, defragment: bool = True) -> None:
        """
        Unload a model from memory.
        
        Args:
            model_name: Name of the model to unload
            defragment: Whether to perform memory defragmentation
        """
        if model_name not in self.loaded_models:
            print(f"Model '{model_name}' is not loaded.")
            return
        
        model = self.loaded_models[model_name]
        model.unload()
        
        del self.loaded_models[model_name]
        
        # If this was the current model, clear it
        if self.current_model_name == model_name:
            self.current_model_name = None
        
        # Force garbage collection
        gc.collect()
        
        # === NEW: Memory defragmentation ===
        if defragment and torch.cuda.is_available():
            # Empty CUDA cache to release fragmented memory
            torch.cuda.empty_cache()
            
            # Synchronize to ensure all operations complete
            torch.cuda.synchronize()
            
            # Brief pause to allow memory defragmentation
            # This is a workaround for PyTorch's memory allocator
            time.sleep(0.5)
    
    def switch_model(self, model_name: ModelName, unload_previous: bool = True) -> BaseVLModel:
        """
        Switch to a different model.
        
        Args:
            model_name: Name of the model to switch to
            unload_previous: Whether to unload the previous model
            
        Returns:
            Newly loaded model
        """
        previous_model = self.current_model_name
        
        # Load new model
        model = self.load_model(model_name)
        
        # Unload previous if requested and different
        if unload_previous and previous_model and previous_model != model_name:
            print(f"Unloading previous model: {previous_model}")
            self.unload_model(previous_model)
        
        return model
    
    def get_current_model(self) -> Optional[BaseVLModel]:
        """
        Get the current active model.
        
        Returns:
            Current model instance or None
        """
        if self.current_model_name:
            return self.loaded_models.get(self.current_model_name)
        return None
    
    def list_loaded_models(self) -> Dict[str, Dict]:
        """
        List all currently loaded models with their status.
        
        Returns:
            Dict mapping model names to status info
        """
        status = {}
        for name, model in self.loaded_models.items():
            status[name] = {
                "model_id": model.model_id,
                "is_loaded": model.is_loaded,
                "load_time": model.load_time,
                "memory_usage": model.get_memory_usage(),
                "is_current": name == self.current_model_name,
            }
        return status
    
    def get_memory_usage(self) -> Dict[str, float]:
        """
        Get total GPU memory usage across all loaded models.
        
        Returns:
            Dict mapping device to total memory in GB
        """
        if not torch.cuda.is_available():
            return {}
        
        total_usage = {}
        for i in range(torch.cuda.device_count()):
            allocated = torch.cuda.memory_allocated(i) / 1024**3
            total_usage[f"cuda:{i}"] = round(allocated, 2)
        
        return total_usage
    
    def unload_all(self) -> None:
        """Unload all models from memory."""
        model_names = list(self.loaded_models.keys())
        for name in model_names:
            self.unload_model(name)
        
        print("All models unloaded.")
    
    def clear_all_cache(self) -> None:
        """
        Clear GPU cache for all devices.
        
        This can help free up fragmented memory even without
        unloading models.
        """
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
            for i in range(torch.cuda.device_count()):
                torch.cuda.synchronize(i)
        gc.collect()

