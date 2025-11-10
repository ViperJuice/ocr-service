#!/usr/bin/env python3
"""
Fix attention mask preparation in DeepSeek-OCR modeling_deepseekv2.py
Replaces old _prepare_4d_causal_attention_mask with new create_causal_mask API
"""

import re
import sys
from pathlib import Path

def fix_attention_mask_code(file_path: Path) -> bool:
    """Replace the attention mask preparation code block."""

    with open(file_path, 'r') as f:
        content = f.read()

    # Pattern to match the old attention mask code block
    old_pattern = r'''        past_key_values_length = 0
        if use_cache:
            use_legacy_cache = not isinstance\(past_key_values, Cache\)
            if use_legacy_cache:
                past_key_values = DynamicCache\.from_legacy_cache\(past_key_values\)
            past_key_values_length = past_key_values\.get_seq_length\(\).*?

        if position_ids is None:
            device = input_ids\.device if input_ids is not None else inputs_embeds\.device
            position_ids = torch\.arange\(
                past_key_values_length,
                seq_length \+ past_key_values_length,
                dtype=torch\.long,
                device=device,
            \)
            position_ids = position_ids\.unsqueeze\(0\)

        if inputs_embeds is None:
            inputs_embeds = self\.embed_tokens\(input_ids\)

        if self\._use_flash_attention_2:
            # 2d mask is passed through the layers
            attention_mask = \(
                attention_mask
                if \(attention_mask is not None and 0 in attention_mask\)
                else None
            \)
        else:
            # 4d mask is passed through the layers
            attention_mask = _prepare_4d_causal_attention_mask\(
                attention_mask,
                \(batch_size, seq_length\),
                inputs_embeds,
                past_key_values_length,
            \)'''

    # New code using create_causal_mask
    new_code = '''        # Handle cache for transformers 4.57.1 compatibility
        if use_cache:
            use_legacy_cache = not isinstance(past_key_values, Cache)
            if use_legacy_cache:
                past_key_values = DynamicCache.from_legacy_cache(past_key_values)
        elif use_cache is None:
            use_cache = self.config.use_cache

        if inputs_embeds is None:
            inputs_embeds = self.embed_tokens(input_ids)

        # Compute cache_position for transformers 4.57.1 compatibility
        if cache_position is None:
            past_seen_tokens = past_key_values.get_seq_length() if past_key_values is not None else 0
            cache_position = torch.arange(
                past_seen_tokens,
                past_seen_tokens + inputs_embeds.shape[1],
                device=inputs_embeds.device
            )

        if position_ids is None:
            position_ids = cache_position.unsqueeze(0)

        # Use create_causal_mask instead of _prepare_4d_causal_attention_mask for 4.57.1
        attention_mask = create_causal_mask(
            config=self.config,
            input_embeds=inputs_embeds,
            attention_mask=attention_mask,
            cache_position=cache_position,
            past_key_values=past_key_values,
            position_ids=position_ids,
        )'''

    # Try to replace
    new_content, count = re.subn(old_pattern, new_code, content, flags=re.DOTALL)

    if count == 0:
        print(f"Warning: Pattern not found in {file_path}", file=sys.stderr)
        return False

    # Write back
    with open(file_path, 'w') as f:
        f.write(new_content)

    print(f"✓ Fixed attention mask code in {file_path.name}")
    return True

if __name__ == "__main__":
    model_dir = Path.home() / ".cache/huggingface/modules/transformers_modules/deepseek_hyphen_ai/DeepSeek_hyphen_OCR/9f30c71f441d010e5429c532364a86705536c53a"
    modeling_file = model_dir / "modeling_deepseekv2.py"

    if not modeling_file.exists():
        print(f"Error: {modeling_file} not found", file=sys.stderr)
        sys.exit(1)

    success = fix_attention_mask_code(modeling_file)
    sys.exit(0 if success else 1)
