"""Integration tests on real hardware."""
import pytest
import torch
from pathlib import Path
from src.models import ModelManager
from src.models.gpu_strategy_manager import GPUStrategyManager
from src.preprocessing import HybridPDFProcessor, PDFHandler
from config.settings import get_settings


@pytest.mark.integration
class TestSingleGPUPersistent:
    """Integration tests for single-GPU persistent strategy."""
    
    def test_single_gpu_loads_both_models(self):
        """Test that single-GPU persistent loads both models on same device."""
        settings = get_settings()
        model_configs = settings.load_model_configs()
        
        manager = ModelManager(model_configs["models"])
        strategy_manager = GPUStrategyManager(
            manager,
            strategy_preference="auto",  # Should auto-select single-GPU if both fit
            verbose=True
        )
        
        strategy_manager.initialize_for_hybrid_processing()
        
        # Verify both models loaded
        ocr_model = strategy_manager.get_model_for_task("ocr")
        merge_model = strategy_manager.get_model_for_task("merge")
        
        assert ocr_model is not None
        assert merge_model is not None
        
        # Check they're on the SAME device
        ocr_device = next(ocr_model.model.parameters()).device
        merge_device = next(merge_model.model.parameters()).device
        
        assert ocr_device == merge_device
        assert "cuda" in str(ocr_device)


@pytest.mark.integration
@pytest.mark.skipif(torch.cuda.device_count() < 2, reason="Requires 2 GPUs")
class TestDualGPUIntegration:
    """Integration tests for dual-GPU strategy on real hardware."""
    
    def test_dual_gpu_loads_models_on_separate_devices(self):
        """Test that dual-GPU strategy actually loads on separate devices."""
        settings = get_settings()
        model_configs = settings.load_model_configs()
        
        manager = ModelManager(model_configs["models"])
        strategy_manager = GPUStrategyManager(
            manager,
            strategy_preference="dual",  # Force dual-GPU
            verbose=True
        )
        
        strategy_manager.initialize_for_hybrid_processing()
        
        # Verify models are on different GPUs
        ocr_model = strategy_manager.get_model_for_task("ocr")
        merge_model = strategy_manager.get_model_for_task("merge")
        
        assert ocr_model is not None
        assert merge_model is not None
        
        # Check they're on different devices
        ocr_device = next(ocr_model.model.parameters()).device
        merge_device = next(merge_model.model.parameters()).device
        
        assert ocr_device != merge_device
        assert "cuda:0" in str(ocr_device) or "cuda:1" in str(ocr_device)
        assert "cuda:0" in str(merge_device) or "cuda:1" in str(merge_device)
    
    def test_end_to_end_pdf_processing_with_auto_strategy(self):
        """Test complete PDF processing with auto strategy selection."""
        settings = get_settings()
        model_configs = settings.load_model_configs()
        
        manager = ModelManager(model_configs["models"])
        pdf_handler = PDFHandler(dpi=300)
        
        processor = HybridPDFProcessor(
            model_manager=manager,
            pdf_handler=pdf_handler,
            method="hybrid",
            verbose=True,
            gpu_strategy="auto"  # Let it auto-detect
        )
        
        # Process a test PDF
        test_pdf = Path("data/input/Bodine-D22.pdf")
        if test_pdf.exists():
            results = processor.process_pdf(test_pdf, max_pages=2)
            
            assert len(results) > 0
            assert results[0].text is not None
            assert results[0].method in ["ocr", "hybrid"]


@pytest.mark.integration
class TestSequentialStrategy:
    """Integration tests for sequential strategy."""
    
    def test_sequential_unloads_between_tasks(self):
        """Test that sequential strategy unloads models between tasks."""
        settings = get_settings()
        model_configs = settings.load_model_configs()
        
        manager = ModelManager(model_configs["models"])
        strategy_manager = GPUStrategyManager(
            manager,
            strategy_preference="sequential",
            verbose=True
        )
        
        strategy_manager.initialize_for_hybrid_processing()
        
        # Get OCR model
        ocr_model = strategy_manager.get_model_for_task("ocr")
        assert ocr_model is not None
        assert manager.current_model_name == "deepseek-ocr"
        
        # Get merge model (should unload OCR first)
        merge_model = strategy_manager.get_model_for_task("merge")
        assert merge_model is not None
        assert manager.current_model_name == "qwen2-vl-2b"

