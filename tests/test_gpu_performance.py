"""Performance benchmarks for different GPU strategies."""
import pytest
import time
import torch
from pathlib import Path
from src.models import ModelManager
from src.preprocessing import HybridPDFProcessor, PDFHandler
from config.settings import get_settings


@pytest.mark.benchmark
class TestPerformanceComparison:
    """Compare performance of different strategies."""
    
    def test_compare_strategies(self):
        """Compare processing time across all available strategies."""
        settings = get_settings()
        model_configs = settings.load_model_configs()
        test_pdf = Path("data/input/Bodine-D22.pdf")
        
        if not test_pdf.exists():
            pytest.skip("Test PDF not available")
        
        results = {}
        strategies = ["auto"]
        
        # Add dual if we have 2 GPUs
        if torch.cuda.device_count() >= 2:
            strategies.append("dual")
        
        strategies.append("sequential")
        
        for strategy in strategies:
            manager = ModelManager(model_configs["models"])
            pdf_handler = PDFHandler(dpi=300)
            
            processor = HybridPDFProcessor(
                model_manager=manager,
                pdf_handler=pdf_handler,
                method="hybrid",
                verbose=False,
                gpu_strategy=strategy
            )
            
            start = time.time()
            processor.process_pdf(test_pdf, max_pages=3)
            elapsed = time.time() - start
            
            results[strategy] = elapsed
            
            # Cleanup
            manager.unload_all()
        
        print(f"\nPerformance Results (3 pages):")
        for strategy, elapsed in sorted(results.items(), key=lambda x: x[1]):
            print(f"  {strategy}: {elapsed:.2f}s")
        
        if "sequential" in results and "auto" in results:
            speedup = results["sequential"] / results["auto"]
            print(f"  Auto speedup vs Sequential: {speedup:.2f}x")

