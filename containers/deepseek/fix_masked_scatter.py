#!/usr/bin/env python3
"""
Minimal patch for DeepSeek-OCR masked_scatter CUDA bug
Replaces buggy masked_scatter_ with safe row-wise assignment (like MPS path)
"""

import sys
from pathlib import Path

# Model file location in container
MODEL_FILE = Path("/root/.cache/huggingface/modules/transformers_modules/deepseek-ai/DeepSeek-OCR/1e3401a3d4603e9e71ea0ec850bfead602191ec4/modeling_deepseekocr.py")

def apply_patch():
    """Replace CUDA masked_scatter_ with row-wise assignment"""

    if not MODEL_FILE.exists():
        print(f"Model file not found: {MODEL_FILE}")
        print("Model will be downloaded on first inference")
        return False

    print(f"Patching {MODEL_FILE}...")

    # Read the file
    content = MODEL_FILE.read_text()

    # Check if already patched
    if "# PATCHED: Use row-wise assignment for CUDA too" in content:
        print("✓ Already patched")
        return True

    # Find and replace the problematic CUDA path
    old_code = """                    else:
                        # Original CUDA path (unchanged)
                        inputs_embeds[idx].masked_scatter_(images_seq_mask[idx].unsqueeze(-1).cuda(), images_in_this_batch)"""

    new_code = """                    else:
                        # PATCHED: Use row-wise assignment for CUDA too (same as MPS)
                        mask = images_seq_mask[idx].to(self.device)
                        feats = images_in_this_batch.to(dtype=inputs_embeds.dtype, device=self.device)
                        if mask.sum().item() != feats.shape[0]:
                            raise RuntimeError(
                                f"image token count mismatch: mask={mask.sum().item()} vs feats={feats.shape[0]}"
                            )
                        feats = torch.nan_to_num(feats)
                        inputs_embeds[idx][mask] = feats"""

    if old_code in content:
        content = content.replace(old_code, new_code)
        MODEL_FILE.write_text(content)
        print("✓ Patch applied successfully")
        return True
    else:
        print("⚠ Could not find code to patch (model may have changed)")
        return False

if __name__ == "__main__":
    success = apply_patch()
    sys.exit(0 if success else 1)
