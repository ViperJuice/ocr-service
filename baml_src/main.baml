// BAML Client Definitions
// Defines OpenAI-compatible clients for containerized models

// Generator configuration for Python and TypeScript
generator python_target {
  output_type "python/pydantic"
  output_dir "../baml_client_py"
  default_client_mode "async"
  version "0.213.0"
}

generator typescript_target {
  output_type "typescript"
  output_dir "../baml_client"
  default_client_mode "async"
  version "0.213.0"
  module_format "esm"
}

// ==================== Container Clients ====================

// DeepSeek-OCR Container (OpenAI-compatible)
// Specialized for high-quality OCR extraction
client<llm> DeepSeekOCR {
  provider "openai-generic"
  options {
    base_url env.DEEPSEEK_URL
    model "deepseek-ocr"
    api_key ""
    max_tokens 4096
    temperature 0.0
  }
}

// QWEN3-VL 8B Container (OpenAI-compatible)
// Used for merging and visual formatting with streaming support
client<llm> QWEN3VL8B {
  provider "openai-generic"
  options {
    base_url env.QWEN_URL
    model "qwen3-vl-8b"
    api_key ""
    max_tokens 4096
    temperature 0.0
  }
}

// QWEN3-VL 4B Container (Optional - for lower memory usage)
client<llm> QWEN3VL4B {
  provider "openai-generic"
  options {
    base_url env.QWEN_URL
    model "qwen3-vl-4b"
    api_key ""
    max_tokens 4096
    temperature 0.0
  }
}

// QWEN3-VL 2B Container (Optional - for fastest processing)
client<llm> QWEN3VL2B {
  provider "openai-generic"
  options {
    base_url env.QWEN_URL
    model "qwen3-vl-2b"
    api_key ""
    max_tokens 4096
    temperature 0.0
  }
}

// ==================== Fallback Strategies ====================

// OCR Fallback: Try DeepSeek first, fall back to QWEN if needed
client<llm> OCRFallback {
  provider fallback
  options {
    strategy [DeepSeekOCR, QWEN3VL8B]
  }
}

// Merge Fallback: Try QWEN models in order of size (quality first)
client<llm> MergeFallback {
  provider fallback
  options {
    strategy [QWEN3VL8B, QWEN3VL4B, QWEN3VL2B]
  }
}

// ==================== Retry Clients ====================

// DeepSeek with automatic retry on CUDA errors
retry_policy DeepSeekRetry {
  max_retries 2
  strategy {
    type "exponential_backoff"
    delay_ms 1000
    multiplier 2.0
  }
}

client<llm> DeepSeekOCRRetry {
  provider "openai-generic"
  retry_policy DeepSeekRetry
  options {
    base_url env.DEEPSEEK_URL
    model "deepseek-ocr"
    api_key ""
    max_tokens 4096
    temperature 0.0
  }
}

// QWEN with automatic retry on CUDA errors
retry_policy QWENRetry {
  max_retries 2
  strategy {
    type "exponential_backoff"
    delay_ms 1000
    multiplier 2.0
  }
}

client<llm> QWEN3VL8BRetry {
  provider "openai-generic"
  retry_policy QWENRetry
  options {
    base_url env.QWEN_URL
    model "qwen3-vl-8b"
    api_key ""
    max_tokens 4096
    temperature 0.0
  }
}
