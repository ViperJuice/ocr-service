#!/usr/bin/env python3
"""
Basic OCR usage example.

This example shows the simplest way to use the OCR service programmatically.
"""
from pathlib import Path
from PIL import Image
import sys

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from config.settings import get_settings
from src.models import ModelManager
from src.preprocessing import preprocess_image


def main():
    """Run basic OCR example."""
    print("=" * 80)
    print("Basic OCR Usage Example")
    print("=" * 80)
    print()
    
    # 1. Load settings and model configs
    print("Step 1: Loading configuration...")
    settings = get_settings()
    model_configs = settings.load_model_configs()
    print(f"  Default model: {settings.default_model}")
    print()
    
    # 2. Initialize model manager
    print("Step 2: Initializing model manager...")
    manager = ModelManager(model_configs["models"])
    print()
    
    # 3. Load a model
    print("Step 3: Loading model...")
    model_name = "qwen2-vl-2b"  # Fast model for demo
    model = manager.load_model(model_name)
    print(f"  Model loaded: {model}")
    print(f"  Memory usage: {model.get_memory_usage()}")
    print()
    
    # 4. Load and preprocess an image
    # For this example, create a simple test image if no sample exists
    image_path = Path(__file__).parent.parent / "data" / "input" / "sample.jpg"
    
    if not image_path.exists():
        print(f"  Sample image not found at {image_path}")
        print("  Please provide an image file to test with.")
        
        # Create a simple test image
        from PIL import ImageDraw, ImageFont
        img = Image.new('RGB', (800, 400), color='white')
        draw = ImageDraw.Draw(img)
        draw.text((50, 50), "OCR Test Document\n\nThis is a test image.\n\nHello World!", fill='black')
        
        image_path.parent.mkdir(parents=True, exist_ok=True)
        img.save(image_path)
        print(f"  Created sample image at {image_path}")
    
    print("Step 4: Loading image...")
    image = Image.open(image_path)
    print(f"  Image size: {image.size}")
    print()
    
    print("Step 5: Preprocessing image...")
    image = preprocess_image(image, max_size=4096)
    print(f"  Preprocessed size: {image.size}")
    print()
    
    # 5. Run OCR
    print("Step 6: Running OCR...")
    result = model.process_image(image, prompt_type="ocr")
    print()
    
    # 6. Display results
    print("=" * 80)
    print("OCR Results")
    print("=" * 80)
    print(f"Model: {result.model_name}")
    print(f"Processing time: {result.processing_time:.2f}s")
    print(f"Memory usage: {result.metadata.get('memory_usage', {})}")
    print()
    print("Extracted Text:")
    print("-" * 80)
    print(result.text)
    print("-" * 80)
    print()
    
    # 7. Clean up
    print("Step 7: Cleaning up...")
    manager.unload_all()
    print("  Models unloaded")
    print()
    
    print("=" * 80)
    print("Example Complete!")
    print("=" * 80)


if __name__ == "__main__":
    main()

