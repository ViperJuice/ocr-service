#!/bin/bash
# Patch DeepSeek-OCR model for transformers 4.57.1 compatibility
#
# This script patches DeepSeek-OCR to work with transformers 4.57.1+
# Required because Qwen3-VL needs transformers >= 4.57.0 (cannot downgrade)
#
# Breaking changes fixed:
# 1. Attention mask API: _prepare_4d_causal_attention_mask → create_causal_mask
# 2. DynamicCache API: seen_tokens, get_max_length, get_usable_length
# 3. LlamaFlashAttention2 → LlamaAttention (class removed in 4.57.1)
# 4. Attention return values: 3 values → 2 values (MHA mode)
# 5. RoPE position embeddings: Added model-level computation
#
# Usage:
#   chmod +x patch_deepseek_model.sh
#   ./patch_deepseek_model.sh
#
# Safe to run multiple times (idempotent)
# See docs/DEEPSEEK_OCR_PATCHES.md for detailed documentation

set -e

MODEL_DIR="$HOME/.cache/huggingface/modules/transformers_modules/deepseek_hyphen_ai/DeepSeek_hyphen_OCR/9f30c71f441d010e5429c532364a86705536c53a"

echo "Patching DeepSeek-OCR model files for transformers 4.57.1 compatibility..."

# Patch modeling_deepseekv2.py
echo "Patching modeling_deepseekv2.py..."

# Fix import: replace _prepare_4d_causal_attention_mask with create_causal_mask
sed -i 's/from transformers\.modeling_attn_mask_utils import _prepare_4d_causal_attention_mask$/from transformers.masking_utils import create_causal_mask  # Updated for transformers 4.57.1/' "$MODEL_DIR/modeling_deepseekv2.py"

# Fix torch.fx.wrap call to use create_causal_mask instead of _prepare_4d_causal_attention_mask
sed -i 's/_prepare_4d_causal_attention_mask = torch\.fx\.wrap(_prepare_4d_causal_attention_mask)/# Removed: _prepare_4d_causal_attention_mask (replaced with create_causal_mask for transformers 4.57.1)\n    create_causal_mask = torch.fx.wrap(create_causal_mask)/' "$MODEL_DIR/modeling_deepseekv2.py"

# Fix LlamaFlashAttention2 references
sed -i 's/    LlamaFlashAttention2$/    # LlamaFlashAttention2  # Removed - not available in transformers 4.57.1/' "$MODEL_DIR/modeling_deepseekv2.py"
sed -i 's/"mha_flash_attention_2": LlamaFlashAttention2/"mha_flash_attention_2": LlamaAttention  # Use LlamaAttention (LlamaFlashAttention2 not available in transformers 4.57.1)/' "$MODEL_DIR/modeling_deepseekv2.py"
sed -i 's/# Copied from transformers\.models\.llama\.modeling_llama\.LlamaFlashAttention2 with Llama->DeepseekV2/# Based on transformers Flash Attention implementation with Llama->DeepseekV2/' "$MODEL_DIR/modeling_deepseekv2.py"

# Fix DynamicCache API changes
sed -i 's/past_length = past_key_values\.seen_tokens$/past_length = past_key_values.get_seq_length()  # Fixed: seen_tokens -> get_seq_length()/' "$MODEL_DIR/modeling_deepseekv2.py"
sed -i 's/max_cache_length = past_key_values\.get_max_length()$/max_cache_length = past_key_values.get_max_cache_shape()  # Fixed: get_max_length() -> get_max_cache_shape()/' "$MODEL_DIR/modeling_deepseekv2.py"
sed -i 's/past_key_value\.get_usable_length(kv_seq_len, self\.layer_idx)/past_key_value.get_seq_length()  # Fixed: get_usable_length() -> get_seq_length()/g' "$MODEL_DIR/modeling_deepseekv2.py"
sed -i 's/past_key_values\.get_usable_length(seq_length)/past_key_values.get_seq_length()  # Fixed: get_usable_length() -> get_seq_length()/g' "$MODEL_DIR/modeling_deepseekv2.py"

# Fix attention mask preparation code (use create_causal_mask instead of _prepare_4d_causal_attention_mask)
echo "Fixing attention mask preparation for transformers 4.57.1..."
python3 /home/jenner/code/ocr-service/fix_attention_mask.py

# Fix attention return value unpacking (handle both MLA 3-value and MHA 2-value returns)
echo "Fixing attention return value unpacking..."
python3 /home/jenner/code/ocr-service/fix_attention_return.py

# Add RoPE support to DeepseekV2Model for LlamaAttention compatibility
echo "Adding RoPE position embeddings support to DeepseekV2Model..."

# Add import for LlamaRotaryEmbedding and fix the import block
# First, add LlamaRotaryEmbedding after LlamaAttention
sed -i '/from transformers\.models\.llama\.modeling_llama import ($/,/)$/{
    /LlamaAttention,$/a\
    LlamaRotaryEmbedding,  # Added for transformers 4.57.1 compatibility
}' "$MODEL_DIR/modeling_deepseekv2.py"

# Add rotary_emb initialization in DeepseekV2Model.__init__ after self.embed_tokens
# Find the line after the closing paren of nn.Embedding and insert the rotary_emb code
sed -i '/self\.embed_tokens = nn\.Embedding(/,/^        )$/{
    /^        )$/a\
\
        # Add rotary embeddings for LlamaAttention compatibility (transformers 4.57.1)\
        # Only needed when use_mla=False (MHA mode with LlamaAttention)\
        if not config.use_mla:\
            self.rotary_emb = LlamaRotaryEmbedding(config=config)
}' "$MODEL_DIR/modeling_deepseekv2.py"

# Compute position_embeddings in DeepseekV2Model.forward() before the layer loop
# Insert after "hidden_states = inputs_embeds" line
sed -i '/# embed positions$/a\
        hidden_states = inputs_embeds\
        \n        # Compute position embeddings for LlamaAttention (transformers 4.57.1 compatibility)\
        # LlamaAttention requires position_embeddings as a required parameter\
        position_embeddings = None\
        if not self.config.use_mla:\
            position_embeddings = self.rotary_emb(hidden_states, position_ids)' "$MODEL_DIR/modeling_deepseekv2.py"

# Remove the duplicate "hidden_states = inputs_embeds" that we just added after
sed -i '/# Compute position embeddings for LlamaAttention/,+3{
    /^        hidden_states = inputs_embeds$/d
}' "$MODEL_DIR/modeling_deepseekv2.py"

# Pass position_embeddings to decoder layers in DeepseekV2Model.forward()
# Update the layer_outputs = decoder_layer( call to include position_embeddings
sed -i '/layer_outputs = decoder_layer(/,/^                )$/{
    /use_cache=use_cache,$/a\
                    position_embeddings=position_embeddings,
}' "$MODEL_DIR/modeling_deepseekv2.py"

# Update DeepseekV2DecoderLayer.forward() to accept and pass position_embeddings
# Add position_embeddings parameter to forward signature
sed -i '/def forward(/,/^    ) -> Tuple\[$/{
    /use_cache: Optional\[bool\] = False,$/a\
        position_embeddings: Optional[Tuple[torch.Tensor, torch.Tensor]] = None,
}' "$MODEL_DIR/modeling_deepseekv2.py"

# Pass position_embeddings to self_attn in DeepseekV2DecoderLayer
sed -i '/hidden_states, self_attn_weights, present_key_value = self\.self_attn(/,/\*\*kwargs,$/{
    /use_cache=use_cache,$/a\
            position_embeddings=position_embeddings,
}' "$MODEL_DIR/modeling_deepseekv2.py"

# Fix gradient checkpointing to pass position_embeddings as positional arg
sed -i '/self\._gradient_checkpointing_func(/,/)$/{
    /use_cache,$/a\
                    position_embeddings,
}' "$MODEL_DIR/modeling_deepseekv2.py"

# Remove duplicate "hidden_states = inputs_embeds" line after position_embeddings computation
sed -i '/position_embeddings = self\.rotary_emb(hidden_states, position_ids)$/,+2{
    /^        hidden_states = inputs_embeds$/d
}' "$MODEL_DIR/modeling_deepseekv2.py"

# Patch modeling_deepseekocr.py
echo "Patching modeling_deepseekocr.py..."
sed -i 's/past_length = past_key_values\.seen_tokens$/past_length = past_key_values.get_seq_length()  # Fixed: seen_tokens -> get_seq_length()/' "$MODEL_DIR/modeling_deepseekocr.py"
sed -i 's/max_cache_length = past_key_values\.get_max_length()$/max_cache_length = past_key_values.get_max_cache_shape()  # Fixed: get_max_length() -> get_max_cache_shape()/' "$MODEL_DIR/modeling_deepseekocr.py"

# Clear bytecode cache
echo "Clearing Python bytecode cache..."
find "$MODEL_DIR" -name "*.pyc" -delete 2>/dev/null || true
find "$MODEL_DIR" -name "__pycache__" -type d -exec rm -rf {} + 2>/dev/null || true

echo "✓ Patches applied successfully!"
echo "  - Fixed attention mask: create_causal_mask API (transformers 4.57.1)"
echo "  - Fixed LlamaFlashAttention2 import"
echo "  - Fixed DynamicCache API: seen_tokens, get_max_length, get_usable_length"
echo "  - Added RoPE position embeddings support to DeepseekV2Model"
echo "  - Added position_embeddings parameter threading through decoder layers"
echo "  - Added cache_position computation"
