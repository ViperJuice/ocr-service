"""Model loading strategies for different GPU configurations."""
from abc import ABC, abstractmethod
from typing import List, Dict, Optional, Any
from dataclasses import dataclass
import psutil  # For system RAM detection
import logging

logger = logging.getLogger(__name__)


@dataclass
class LoadedModelInfo:
    """Information about a loaded model."""
    model_name: str
    model_instance: Any  # BaseVLModel
    device_ids: List[int]
    quantization: Optional[str]
    vram_used_gb: float


class ModelLoadingStrategy(ABC):
    """Abstract base class for model loading strategies."""
    
    @abstractmethod
    def name(self) -> str:
        """Strategy name for logging."""
        pass
    
    @abstractmethod
    def load_models(
        self,
        model_manager,
        model_names: List[str],
        model_configs: Dict[str, Dict],
        force_disable_crop: bool = False
    ) -> Dict[str, LoadedModelInfo]:
        """
        Load models according to this strategy.
        
        Args:
            force_disable_crop: Disable crop mode in DeepSeek models
        
        Returns:
            Dict mapping model_name -> LoadedModelInfo
        """
        pass
    
    @abstractmethod
    def get_model_for_task(
        self,
        task_type: str,
        loaded_models: Dict[str, LoadedModelInfo]
    ) -> Any:
        """Get the appropriate model for a task type (ocr, merge, format)."""
        pass
    
    @abstractmethod
    def cleanup(self, model_manager):
        """Clean up resources used by this strategy."""
        pass


class SingleGPUPersistentStrategy(ModelLoadingStrategy):
    """Load all models on a single GPU and keep them loaded (PRIORITY 1 - Best Performance)."""

    def __init__(self, gpu_id: int, task_to_model_mapping: Optional[Dict[str, str]] = None):
        """
        Args:
            gpu_id: GPU device ID to use
            task_to_model_mapping: Optional task-to-model mapping
        """
        self.gpu_id = gpu_id
        self.task_to_model = task_to_model_mapping or self._default_mapping()
    
    def name(self) -> str:
        return "single_gpu_persistent"
    
    def load_models(self, model_manager, model_names, model_configs, force_disable_crop=False):
        loaded = {}
        
        for model_name in model_names:
            # Modify config to pin to specific GPU
            config = model_configs[model_name].copy()
            config["config"]["device_map"] = f"cuda:{self.gpu_id}"
            
            # Update model_manager's config temporarily
            original_config = model_manager.model_configs[model_name]
            model_manager.model_configs[model_name] = config
            
            # Load model
            model_instance = model_manager.load_model(
                model_name, 
                quantization=None,
                force_disable_crop=force_disable_crop
            )
            
            # Restore original config
            model_manager.model_configs[model_name] = original_config
            
            loaded[model_name] = LoadedModelInfo(
                model_name=model_name,
                model_instance=model_instance,
                device_ids=[self.gpu_id],
                quantization=None,
                vram_used_gb=self._estimate_vram(config)
            )
        
        return loaded

    def _default_mapping(self) -> Dict[str, str]:
        """Default task-to-model mapping for backward compatibility."""
        return {
            "ocr": "deepseek-ocr",
            "merge": "qwen3-vl-2b",
            "format": "qwen3-vl-2b"
        }

    def get_model_for_task(self, task_type, loaded_models):
        model_name = self.task_to_model.get(task_type)
        if model_name and model_name in loaded_models:
            return loaded_models[model_name].model_instance
        return None

    def cleanup(self, model_manager):
        # Models stay loaded, no cleanup needed
        pass

    def _estimate_vram(self, config):
        vram_str = config.get("vram_requirement", "6GB")
        return float(vram_str.replace("GB", "").split("-")[0])


class DualGPUPersistentStrategy(ModelLoadingStrategy):
    """Load models on separate GPUs and keep them loaded (PRIORITY 2)."""

    def __init__(self, gpu_assignment: Dict[str, int], task_to_model_mapping: Optional[Dict[str, str]] = None):
        """
        Args:
            gpu_assignment: Dict mapping model_name -> gpu_id
            task_to_model_mapping: Optional task-to-model mapping
        """
        self.gpu_assignment = gpu_assignment
        self.task_to_model = task_to_model_mapping or self._default_mapping()
    
    def name(self) -> str:
        return "dual_gpu_persistent"
    
    def load_models(self, model_manager, model_names, model_configs, force_disable_crop=False):
        loaded = {}
        
        for model_name in model_names:
            gpu_id = self.gpu_assignment[model_name]
            
            # Modify config to pin to specific GPU
            config = model_configs[model_name].copy()
            config["config"]["device_map"] = f"cuda:{gpu_id}"
            
            # Update model_manager's config temporarily
            original_config = model_manager.model_configs[model_name]
            model_manager.model_configs[model_name] = config
            
            # Load model
            model_instance = model_manager.load_model(
                model_name, 
                quantization=None,
                force_disable_crop=force_disable_crop
            )
            
            # Restore original config
            model_manager.model_configs[model_name] = original_config
            
            loaded[model_name] = LoadedModelInfo(
                model_name=model_name,
                model_instance=model_instance,
                device_ids=[gpu_id],
                quantization=None,
                vram_used_gb=self._estimate_vram(config)
            )

        return loaded

    def _default_mapping(self) -> Dict[str, str]:
        """Default task-to-model mapping for backward compatibility."""
        return {
            "ocr": "deepseek-ocr",
            "merge": "qwen3-vl-2b",
            "format": "qwen3-vl-2b"
        }

    def get_model_for_task(self, task_type, loaded_models):
        model_name = self.task_to_model.get(task_type)
        if model_name and model_name in loaded_models:
            return loaded_models[model_name].model_instance
        return None

    def cleanup(self, model_manager):
        # Models stay loaded, no cleanup needed
        pass

    def _estimate_vram(self, config):
        vram_str = config.get("vram_requirement", "6GB")
        return float(vram_str.replace("GB", "").split("-")[0])


class SingleGPUSequentialStrategy(ModelLoadingStrategy):
    """Load models one at a time on single GPU, unloading between tasks (PRIORITY 3)."""

    def __init__(self, gpu_id: int, task_to_model_mapping: Optional[Dict[str, str]] = None):
        self.gpu_id = gpu_id
        self.task_to_model = task_to_model_mapping or self._default_mapping()
    
    def name(self) -> str:
        return "single_gpu_sequential"
    
    def load_models(self, model_manager, model_names, model_configs, force_disable_crop=False):
        # Don't load all at once, just store configs
        self.model_names = model_names
        self.model_manager = model_manager
        self.force_disable_crop = force_disable_crop
        return {}

    def _default_mapping(self) -> Dict[str, str]:
        """Default task-to-model mapping for backward compatibility."""
        return {
            "ocr": "deepseek-ocr",
            "merge": "qwen3-vl-2b",
            "format": "qwen3-vl-2b"
        }

    def get_model_for_task(self, task_type, loaded_models):
        model_name = self.task_to_model.get(task_type)

        if not model_name:
            return None

        # Unload any currently loaded model
        if self.model_manager.current_model_name and \
           self.model_manager.current_model_name != model_name:
            self.model_manager.unload_model(self.model_manager.current_model_name)

        # Load the needed model
        return self.model_manager.load_model(
            model_name,
            force_disable_crop=self.force_disable_crop
        )

    def cleanup(self, model_manager):
        if model_manager.current_model_name:
            model_manager.unload_model(model_manager.current_model_name)


class QuantizedFallbackStrategy(ModelLoadingStrategy):
    """Fallback strategy using quantization (int8 -> int4) (LAST RESORT)."""

    def __init__(self, gpu_id: int, quantization: str, task_to_model_mapping: Optional[Dict[str, str]] = None):
        self.gpu_id = gpu_id
        self.quantization = quantization  # "int8" or "int4"
        self.task_to_model = task_to_model_mapping or self._default_mapping()
    
    def name(self) -> str:
        return f"quantized_fallback_{self.quantization}"
    
    def load_models(self, model_manager, model_names, model_configs, force_disable_crop=False):
        loaded = {}
        
        for model_name in model_names:
            model_instance = model_manager.load_model(
                model_name, 
                quantization=self.quantization,
                force_disable_crop=force_disable_crop
            )
            
            loaded[model_name] = LoadedModelInfo(
                model_name=model_name,
                model_instance=model_instance,
                device_ids=[self.gpu_id],
                quantization=self.quantization,
                vram_used_gb=self._estimate_vram_quantized(model_configs[model_name])
            )
        
        return loaded

    def _default_mapping(self) -> Dict[str, str]:
        """Default task-to-model mapping for backward compatibility."""
        return {
            "ocr": "deepseek-ocr",
            "merge": "qwen3-vl-2b",
            "format": "qwen3-vl-2b"
        }

    def get_model_for_task(self, task_type, loaded_models):
        model_name = self.task_to_model.get(task_type)
        if model_name and model_name in loaded_models:
            return loaded_models[model_name].model_instance
        return None

    def cleanup(self, model_manager):
        pass

    def _estimate_vram_quantized(self, config):
        vram_str = config.get("vram_requirement", "6GB")
        base = float(vram_str.replace("GB", "").split("-")[0])
        return base * 0.5 if self.quantization == "int8" else base * 0.25

