# Quick Start Guide

Get up and running with OCR Service in 5 minutes!

## 🚀 Installation (10-15 minutes)

```bash
cd ~/code/ocr-service
./scripts/setup.sh
```

Wait for installation to complete (Flash-Attention compilation takes ~10 minutes).

## ✅ Verify Installation

```bash
source .venv/bin/activate
python scripts/verify_installation.py
```

You should see all checks pass with ✓ marks.

### Optional: FlashAttention 2 (Recommended)

FlashAttention 2 reduces VRAM usage by 30-40% and improves speed by 20-30%.

**Check prerequisites:**
```bash
python scripts/verify_flash_attention.py --check-prereqs
```

**Install (if prerequisites pass):**
```bash
./scripts/install_flash_attention.sh
```

Installation takes 5-10 minutes. If it fails or your GPU doesn't support it, the models will fall back to standard attention automatically.

For detailed information, see [specs/flash-attention-setup.md](specs/flash-attention-setup.md).

## 🎯 First OCR Test

### 1. Activate Environment

```bash
source scripts/quick_start.sh
```

### 2. Check GPU Status

```bash
ocr gpu
```

You should see your dual RTX 4090s listed.

### 3. List Available Models

```bash
ocr models
```

Output:
```
Available OCR Models

┏━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━┳━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓
┃ Model              ┃ VRAM       ┃ Load Time     ┃ Description                            ┃
┡━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━╇━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┩
│ qwen2-vl-7b        │ 13-14GB    │ ~143s         │ Highest quality, best for production   │
│ qwen2-vl-2b        │ 3GB        │ ~37s          │ Fast and efficient, high-throughput    │
│ deepseek-ocr       │ 6-7GB      │ ~7s           │ OCR-specialized, excellent for docs    │
└────────────────────┴────────────┴───────────────┴────────────────────────────────────────┘
```

### 4. Run Your First OCR

```bash
# Use an existing image from your DeepSeek-OCR tests
ocr /home/jenner/code/DeepSeek-OCR/sample_doc.jpg
```

Or test all three models:

```bash
python examples/test_models.py
```

## 📝 Common Usage Examples

### Simple Text Extraction

```bash
ocr image.jpg
```

### Save to File

```bash
ocr document.png --output result.txt
```

### Use Fastest Model

```bash
ocr scan.jpg --model qwen2-vl-2b
```

### Markdown Output

```bash
ocr document.jpg --format markdown --output result.md
```

### Process PDF (Hybrid Mode)

```bash
# Automatic intelligent processing (extracts embedded text + OCR + AI merge)
ocr pdf document.pdf --output result.txt

# Show detailed per-page processing info
ocr pdf document.pdf --output result.txt --verbose
```

### Process First 5 Pages Only

```bash
ocr pdf large.pdf --max-pages 5 --output result.txt
```

### PDF Processing Methods

```bash
# Hybrid: Best accuracy (AI merges embedded text + OCR)
ocr pdf document.pdf -o result.txt --method hybrid

# Extract only: Fastest (embedded text only, no OCR)
ocr pdf document.pdf -o result.txt --method extract

# OCR only: For scanned PDFs
ocr pdf scan.pdf -o result.txt --method ocr

# Force OCR even if text exists
ocr pdf document.pdf -o result.txt --force-ocr
```

### Low Memory PDF Processing

```bash
# Use lower DPI to reduce memory usage
ocr pdf document.pdf -o result.txt --dpi 100 --model qwen2-vl-2b
```

## 🔍 Troubleshooting Quick Fixes

### Models Not Loading

```bash
# Check transformers version (must be 4.46.3)
python -c "import transformers; print(transformers.__version__)"

# If wrong, reinstall
uv pip uninstall transformers
uv pip install transformers==4.46.3
```

### Flash-Attention Errors

```bash
# Rebuild from source
uv pip uninstall flash-attn
uv pip install flash-attn --no-build-isolation
```

### Out of Memory

```bash
# Use smaller model
ocr image.jpg --model qwen2-vl-2b
```

### Environment Not Set

```bash
# Always run before using
source scripts/quick_start.sh
```

## 📊 Performance Expectations

On dual RTX 4090s (48GB total VRAM):

| Model | VRAM Used | Processing Time | Use Case |
|-------|-----------|-----------------|----------|
| Qwen2-VL-7B | ~13GB | ~2s per image | Production quality |
| Qwen2-VL-2B | ~3GB | ~1s per image | High throughput |
| DeepSeek-OCR | ~6GB | ~1.5s per image | Document specialized |

## 🎓 Next Steps

1. **Try the examples**:
   ```bash
   python examples/basic_usage.py
   python examples/test_models.py
   ```

2. **Process your own documents**:
   ```bash
   ocr /path/to/your/document.jpg --model qwen2-vl-7b
   ```

3. **Batch process multiple files**:
   ```bash
   for img in *.jpg; do
       ocr "$img" --output "${img%.jpg}.txt"
   done
   ```

4. **Read the full documentation**:
   - `README.md` - Complete feature list
   - `INSTALLATION.md` - Detailed installation guide
   - `config/model_configs.yaml` - Model configurations

## 💡 Pro Tips

1. **Use the fast model for testing**:
   ```bash
   ocr test.jpg --model qwen2-vl-2b
   ```
   It loads in 37s vs 143s for the 7B model.

2. **Set default model in .env**:
   ```bash
   DEFAULT_MODEL=qwen2-vl-2b  # or qwen2-vl-7b, deepseek-ocr
   ```

3. **Check memory before loading large models**:
   ```bash
   ocr gpu
   ```

4. **Preprocess images for better results**:
   Images are automatically preprocessed unless you use `--no-preprocess`

5. **Test with known good image**:
   Use the sample from DeepSeek-OCR testing:
   ```bash
   ocr /home/jenner/code/DeepSeek-OCR/sample_doc.jpg
   ```

## ❓ Need Help?

- Run verification: `python scripts/verify_installation.py`
- Check system info: `ocr info`
- Check GPU status: `ocr gpu`
- View logs: `tail -f logs/ocr-service.log` (after first run)

---

**Happy OCR-ing! 🎉**

