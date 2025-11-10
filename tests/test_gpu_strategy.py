"""Unit tests for GPU strategy with mocked hardware."""
import pytest
from unittest.mock import Mock, patch
from src.models.gpu_memory_analyzer import (
    GPUMemoryAnalyzer, GPUInfo, ModelMemoryRequirement
)
from src.models.gpu_strategy_manager import GPUStrategyManager


class TestGPUMemoryAnalyzer:
    """Test GPU memory analysis with mocked GPUs."""
    
    @patch('torch.cuda.is_available', return_value=True)
    @patch('torch.cuda.device_count', return_value=2)
    @patch('torch.cuda.get_device_properties')
    @patch('torch.cuda.memory_allocated')
    def test_detect_dual_gpus(self, mock_allocated, mock_props, mock_count, mock_available):
        """Test detection of 2 GPUs with sufficient VRAM."""
        # Mock GPU properties
        mock_prop_gpu0 = Mock()
        mock_prop_gpu0.name = "RTX 4090"
        mock_prop_gpu0.total_memory = 24 * (1024**3)  # 24GB
        mock_prop_gpu0.major = 8
        mock_prop_gpu0.minor = 9
        
        mock_prop_gpu1 = Mock()
        mock_prop_gpu1.name = "RTX 4090"
        mock_prop_gpu1.total_memory = 24 * (1024**3)
        mock_prop_gpu1.major = 8
        mock_prop_gpu1.minor = 9
        
        mock_props.side_effect = [mock_prop_gpu0, mock_prop_gpu1]
        mock_allocated.side_effect = [1 * (1024**3), 1 * (1024**3)]  # 1GB used each
        
        analyzer = GPUMemoryAnalyzer()
        
        assert len(analyzer.gpus) == 2
        assert analyzer.gpus[0].total_memory_gb == 24
        assert analyzer.gpus[0].free_memory_gb == 23
    
    def test_single_gpu_fits_both_models(self):
        """Test that both models fit on a single large GPU."""
        analyzer = GPUMemoryAnalyzer(dpi=300)
        analyzer.gpus = [
            GPUInfo(0, "Large GPU", 24, 1, 23, (8, 9))
        ]
        
        runtime_overhead = analyzer.runtime_overhead_gb
        models = [
            ModelMemoryRequirement("deepseek-ocr", 7.0, runtime_overhead_gb=runtime_overhead),
            ModelMemoryRequirement("qwen2-vl-2b", 3.0, runtime_overhead_gb=runtime_overhead * 0.5)
        ]
        
        # Total: ~7 + 0.9 + 3 + 0.45 = ~11.35GB
        # Available: 23GB - 2GB buffer = 21GB -> fits!
        gpu_id = analyzer.can_fit_all_on_single_gpu(models)
        
        assert gpu_id == 0
    
    def test_runtime_overhead_scales_with_dpi(self):
        """Test that runtime overhead scales correctly with DPI."""
        analyzer_150 = GPUMemoryAnalyzer(dpi=150)
        analyzer_300 = GPUMemoryAnalyzer(dpi=300)
        analyzer_600 = GPUMemoryAnalyzer(dpi=600)
        
        # 300 DPI should be 4x the memory of 150 DPI
        assert analyzer_300.runtime_overhead_gb / analyzer_150.runtime_overhead_gb == pytest.approx(4.0, rel=0.1)
        
        # 600 DPI should be 4x the memory of 300 DPI
        assert analyzer_600.runtime_overhead_gb / analyzer_300.runtime_overhead_gb == pytest.approx(4.0, rel=0.1)
    
    def test_can_fit_on_separate_gpus(self):
        """Test fitting two models on separate GPUs."""
        analyzer = GPUMemoryAnalyzer()
        analyzer.gpus = [
            GPUInfo(0, "GPU0", 24, 1, 23, (8, 9)),
            GPUInfo(1, "GPU1", 24, 1, 23, (8, 9))
        ]
        
        models = [
            ModelMemoryRequirement("deepseek-ocr", 7.0),
            ModelMemoryRequirement("qwen2-vl-2b", 3.0)
        ]
        
        assignment = analyzer.can_fit_models_on_separate_gpus(models)
        
        assert assignment is not None
        assert len(assignment) == 2
        assert "deepseek-ocr" in assignment
        assert "qwen2-vl-2b" in assignment
    
    def test_insufficient_vram_returns_none(self):
        """Test that insufficient VRAM returns None."""
        analyzer = GPUMemoryAnalyzer()
        analyzer.gpus = [
            GPUInfo(0, "Small GPU", 4, 1, 3, (7, 5))
        ]
        
        models = [
            ModelMemoryRequirement("large-model", 10.0)
        ]
        
        result = analyzer.can_fit_all_on_single_gpu(models)
        assert result is None
    
    def test_quantization_reduces_vram(self):
        """Test that quantization reduces estimated VRAM."""
        model_fp16 = ModelMemoryRequirement("model", 8.0, quantization=None)
        model_int8 = ModelMemoryRequirement("model", 8.0, quantization="int8")
        model_int4 = ModelMemoryRequirement("model", 8.0, quantization="int4")
        
        assert model_fp16.estimated_vram_gb() == 8.0
        assert model_int8.estimated_vram_gb() == 4.0
        assert model_int4.estimated_vram_gb() == 2.0


class TestGPUStrategyManager:
    """Test GPU strategy manager logic."""
    
    def test_auto_selects_single_gpu_persistent_when_both_fit(self):
        """Test that auto mode selects single-GPU persistent when both models fit (PRIORITY 1)."""
        mock_manager = Mock()
        mock_manager.model_configs = {
            "deepseek-ocr": {"vram_requirement": "7GB"},
            "qwen2-vl-2b": {"vram_requirement": "3GB"}
        }
        
        with patch.object(GPUMemoryAnalyzer, '_detect_gpus') as mock_detect:
            # Single large GPU that fits both models + runtime overhead
            mock_detect.return_value = [
                GPUInfo(0, "Large GPU", 24, 1, 23, (8, 9))
            ]
            
            manager = GPUStrategyManager(mock_manager, strategy_preference="auto", verbose=True)
            
            # Include runtime overhead in requirements
            requirements = [
                ModelMemoryRequirement("deepseek-ocr", 7.0, runtime_overhead_gb=0.9),
                ModelMemoryRequirement("qwen2-vl-2b", 3.0, runtime_overhead_gb=0.45)
            ]
            strategy = manager._auto_detect_strategy(requirements)
            
            # Should select single GPU persistent (Priority 1)
            # Total: 7 + 0.9 + 3 + 0.45 = 11.35 GB < 21 GB available
            assert strategy.name() == "single_gpu_persistent"
            assert strategy.gpu_id == 0
    
    def test_auto_selects_dual_gpu_when_models_dont_fit_together(self):
        """Test that auto mode selects dual-GPU when models don't fit on one GPU."""
        mock_manager = Mock()
        mock_manager.model_configs = {
            "deepseek-ocr": {"vram_requirement": "7GB"},
            "qwen2-vl-2b": {"vram_requirement": "3GB"}
        }
        
        with patch.object(GPUMemoryAnalyzer, '_detect_gpus') as mock_detect:
            # Two medium GPUs - each fits one model + overhead, but not both together
            mock_detect.return_value = [
                GPUInfo(0, "GPU0", 12, 1, 11, (8, 9)),  # 11GB free - 2GB buffer = 9GB available
                GPUInfo(1, "GPU1", 12, 1, 11, (8, 9))   # 11GB free - 2GB buffer = 9GB available
            ]
            
            manager = GPUStrategyManager(mock_manager, strategy_preference="auto", verbose=True)
            
            requirements = [
                ModelMemoryRequirement("deepseek-ocr", 7.0, runtime_overhead_gb=0.9),  # Total: 7.9 GB
                ModelMemoryRequirement("qwen2-vl-2b", 3.0, runtime_overhead_gb=0.45)   # Total: 3.45 GB
            ]
            strategy = manager._auto_detect_strategy(requirements)
            
            # Total: 11.35 GB > 9GB available on single GPU
            # But each fits separately (7.9 < 9 and 3.45 < 9)
            # Should select dual GPU (Priority 2)
            assert strategy.name() == "dual_gpu_persistent"
    
    def test_fallback_to_sequential_on_single_small_gpu(self):
        """Test fallback to sequential on single GPU with limited VRAM."""
        mock_manager = Mock()
        mock_manager.model_configs = {
            "deepseek-ocr": {"vram_requirement": "7GB"},
            "qwen2-vl-2b": {"vram_requirement": "3GB"}
        }
        
        with patch.object(GPUMemoryAnalyzer, '_detect_gpus') as mock_detect:
            mock_detect.return_value = [
                GPUInfo(0, "Small GPU", 10, 1, 9, (7, 5))  # 9GB - 2GB buffer = 7GB available
            ]
            
            manager = GPUStrategyManager(mock_manager, strategy_preference="auto")
            
            requirements = [
                ModelMemoryRequirement("deepseek-ocr", 7.0, runtime_overhead_gb=0.9),  # Total: 7.9 GB
                ModelMemoryRequirement("qwen2-vl-2b", 3.0, runtime_overhead_gb=0.45)   # Total: 3.45 GB
            ]
            strategy = manager._auto_detect_strategy(requirements)
            
            # Total: 11.35 GB > 7GB available
            # Can't fit both together, need sequential
            assert strategy.name() == "single_gpu_sequential"

