"""Test what model.infer() actually returns"""

import torch
from transformers import AutoModel, AutoTokenizer
from PIL import Image
import tempfile
import os

# Load model
print("Loading model...")
tokenizer = AutoTokenizer.from_pretrained("deepseek-ai/DeepSeek-OCR", trust_remote_code=True)
model = AutoModel.from_pretrained(
    "deepseek-ai/DeepSeek-OCR",
    trust_remote_code=True,
    device_map="auto",
    torch_dtype=torch.bfloat16
)
model = model.eval()
print("Model loaded")

# Create a simple test image
print("\nCreating test image...")
img = Image.new('RGB', (800, 400), color='white')
with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as tmp_file:
    tmp_path = tmp_file.name
    img.save(tmp_path, format='PNG')

tmp_output_dir = tempfile.mkdtemp()

# Test with different prompts and parameters
test_configs = [
    {
        "name": "Free OCR",
        "prompt": "<image>\nFree OCR.",
        "save_results": False,
        "test_compress": False
    },
    {
        "name": "Free OCR with save",
        "prompt": "<image>\nFree OCR.",
        "save_results": True,
        "test_compress": False
    },
    {
        "name": "Free OCR with save and compress",
        "prompt": "<image>\nFree OCR.",
        "save_results": True,
        "test_compress": True
    },
    {
        "name": "Grounding markdown",
        "prompt": "<image>\n<|grounding|>Convert the document to markdown.",
        "save_results": True,
        "test_compress": True
    }
]

for config in test_configs:
    print(f"\n{'='*80}")
    print(f"Testing: {config['name']}")
    print(f"Prompt: {config['prompt']}")
    print(f"save_results: {config['save_results']}, test_compress: {config['test_compress']}")
    print('='*80)

    result = model.infer(
        tokenizer,
        prompt=config['prompt'],
        image_file=tmp_path,
        output_path=tmp_output_dir,
        base_size=1024,
        image_size=640,
        crop_mode=True,
        save_results=config['save_results'],
        test_compress=config['test_compress']
    )

    print(f"Result type: {type(result)}")
    print(f"Result value: {result}")
    print(f"Result bool: {bool(result)}")

    # Check output directory
    output_contents = os.listdir(tmp_output_dir)
    print(f"Output dir contents: {output_contents}")

    # Look for any files
    for root, dirs, files in os.walk(tmp_output_dir):
        if files:
            print(f"  Found files in {root}: {files}")
            for fname in files:
                fpath = os.path.join(root, fname)
                print(f"    {fname}: {os.path.getsize(fpath)} bytes")
                if fname.endswith('.txt'):
                    with open(fpath, 'r', encoding='utf-8') as f:
                        content = f.read()
                        print(f"    Content: {content[:200]}...")

# Cleanup
os.unlink(tmp_path)
import shutil
shutil.rmtree(tmp_output_dir)

print("\n\nDone!")
