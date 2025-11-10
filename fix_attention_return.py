#!/usr/bin/env python3
"""
Fix attention return value unpacking in DeepSeek-OCR modeling_deepseekv2.py
Handle both MLA (3 values) and MHA (2 values in transformers 4.57.1)
"""

import re
import sys
from pathlib import Path

def fix_attention_return(file_path: Path) -> bool:
    """Fix the attention output unpacking to handle both 2 and 3 return values."""

    with open(file_path, 'r') as f:
        content = f.read()

    # Pattern to match the attention call and unpacking
    old_pattern = r'''        # Self Attention
        hidden_states, self_attn_weights, present_key_value = self\.self_attn\(
            hidden_states=hidden_states,
            attention_mask=attention_mask,
            position_ids=position_ids,
            past_key_value=past_key_value,
            output_attentions=output_attentions,
            use_cache=use_cache,
            position_embeddings=position_embeddings,
            \*\*kwargs,
        \)
        hidden_states = residual \+ hidden_states'''

    # New code that handles both return formats
    new_code = '''        # Self Attention
        # In transformers 4.57.1, when using LlamaAttention (MHA mode), only 2 values are returned
        # Cache is managed in-place via past_key_value object
        attn_output = self.self_attn(
            hidden_states=hidden_states,
            attention_mask=attention_mask,
            position_ids=position_ids,
            past_key_value=past_key_value,
            output_attentions=output_attentions,
            use_cache=use_cache,
            position_embeddings=position_embeddings,
            **kwargs,
        )

        # Handle different return formats (MLA returns 3, MHA returns 2 in transformers 4.57.1)
        if len(attn_output) == 3:
            hidden_states, self_attn_weights, present_key_value = attn_output
        else:
            hidden_states, self_attn_weights = attn_output
            present_key_value = past_key_value  # Cache updated in-place

        hidden_states = residual + hidden_states'''

    # Try to replace
    new_content, count = re.subn(old_pattern, new_code, content, flags=re.DOTALL)

    if count == 0:
        print(f"Warning: Pattern not found in {file_path}", file=sys.stderr)
        return False

    # Write back
    with open(file_path, 'w') as f:
        f.write(new_content)

    print(f"✓ Fixed attention return value unpacking in {file_path.name}")
    return True

if __name__ == "__main__":
    model_dir = Path.home() / ".cache/huggingface/modules/transformers_modules/deepseek_hyphen_ai/DeepSeek_hyphen_OCR/9f30c71f441d010e5429c532364a86705536c53a"
    modeling_file = model_dir / "modeling_deepseekv2.py"

    if not modeling_file.exists():
        print(f"Error: {modeling_file} not found", file=sys.stderr)
        sys.exit(1)

    success = fix_attention_return(modeling_file)
    sys.exit(0 if success else 1)
