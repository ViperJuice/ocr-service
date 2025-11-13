# DeepSeek-OCR Patches - Quick Reference

**TL;DR:** DeepSeek-OCR needs patches for transformers 4.57.1+. Patches apply automatically on first load. See [docs/DEEPSEEK_OCR_PATCHES.md](docs/DEEPSEEK_OCR_PATCHES.md) for full details.

## 🆕 Latest Update (2025-01-12)

**Vision Embedding Position IDs Extension** - Fixed critical dimension mismatch error (116 vs 115) that occurred when processing images with text. The patch now automatically extends `position_ids` to match `hidden_states` sequence length when vision embeddings are inserted.

## Why Patches?

- Qwen3-VL requires transformers >= 4.57.0 (cannot downgrade)
- DeepSeek-OCR was built for transformers 4.40.x
- 6 breaking API changes in transformers 4.57.1

## What Gets Patched?

| Change | Old API | New API |
|--------|---------|---------|
| Attention mask | `_prepare_4d_causal_attention_mask()` | `create_causal_mask()` |
| Cache length | `past_key_values.seen_tokens` | `past_key_values.get_seq_length()` |
| Cache max | `past_key_values.get_max_length()` | `past_key_values.get_max_cache_shape()` |
| Flash Attention | `LlamaFlashAttention2` | `LlamaAttention` |
| Attention returns | 3 values | 2 values (MHA mode) |
| Position IDs | Fixed length | Dynamic extension for vision embeddings |

## Quick Commands

```bash
# Automatic patching (first DeepSeek-OCR load)
ocr image.jpg --model deepseek-ocr

# Manual patching (if needed)
chmod +x patch_deepseek_model.sh
./patch_deepseek_model.sh

# Test patches work
uv run python test_deepseek_ocr.py

# Test Qwen3-VL still works
uv run python test_qwen3.py
```

## Patch Files

- [`patch_deepseek_model.sh`](patch_deepseek_model.sh) - Main patch script (bash + sed)
- [`fix_attention_mask.py`](fix_attention_mask.py) - Attention mask API replacement
- [`fix_attention_return.py`](fix_attention_return.py) - Return value handling

## Performance Impact

**RoPE Position Embeddings: IMPROVED ⚡**
- Old: Computed 40+ times per forward pass (per layer)
- New: Computed once per forward pass (shared across layers)
- Result: More efficient than original!

## New Server Setup

1. Install transformers 4.57.1+: `uv pip install transformers>=4.57.1`
2. Clone repo (patches included)
3. Load DeepSeek-OCR (patches auto-apply)
4. Verify: `uv run python test_deepseek_ocr.py`

## Troubleshooting

| Error | Solution |
|-------|----------|
| `_prepare_4d_causal_attention_mask not found` | Run `./patch_deepseek_model.sh` |
| Size mismatch (116 vs 115, 277 vs 278, etc.) | Run `./patch_deepseek_model.sh` (latest patches include position_ids extension) |
| Not enough values to unpack (expected 3, got 2) | Run `./patch_deepseek_model.sh` |
| Patches get overwritten | We use revision pinning to prevent this |

## Documentation

- **Full details:** [docs/DEEPSEEK_OCR_PATCHES.md](docs/DEEPSEEK_OCR_PATCHES.md)
- **Installation:** [docs/INSTALLATION.md](docs/INSTALLATION.md)
- **Main README:** [README.md](README.md)

## Status

✅ **Production Ready**
- Tested with real PDFs
- Validated accuracy (identical to original)
- Performance improved (RoPE efficiency)
- Both models work: Qwen3-VL + DeepSeek-OCR
