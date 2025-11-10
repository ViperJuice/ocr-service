// ============================================================================
// RETRY POLICIES
// ============================================================================

retry_policy StandardRetry {
  max_retries 3
  strategy {
    type exponential_backoff
    delay_ms 200
    multiplier 1.5
    max_delay_ms 10000
  }
}

retry_policy AggressiveRetry {
  max_retries 5
  strategy {
    type exponential_backoff
    delay_ms 100
    multiplier 2.0
    max_delay_ms 30000
  }
}

// ============================================================================
// BASE CLIENTS
// ============================================================================

client<llm> O4MiniBase {
  provider openai
  retry_policy StandardRetry
  options {
    model "o4-mini"
    api_key env.OPENAI_API_KEY
    max_tokens 2048
    temperature 0.1
  }
}

client<llm> ClaudeHaiku45Base {
  provider anthropic
  retry_policy StandardRetry
  options {
    model "claude-haiku-4-5-20251001"
    api_key env.ANTHROPIC_API_KEY
    max_tokens 1024
    temperature 0.0
  }
}

client<llm> GPT4oMiniBase {
  provider openai
  retry_policy StandardRetry
  options {
    model "gpt-4o-mini"
    api_key env.OPENAI_API_KEY
    max_tokens 512
    temperature 0.0
  }
}

client<llm> ClaudeSonnet45Base {
  provider anthropic
  retry_policy AggressiveRetry
  options {
    model "claude-sonnet-4-5-20250929"
    api_key env.ANTHROPIC_API_KEY
    max_tokens 2048
    temperature 0.1
  }
}

// ============================================================================
// FALLBACK CLIENTS
// ============================================================================

client<llm> ReasoningClient {
  provider fallback
  retry_policy StandardRetry
  options {
    strategy [
      O4MiniBase
      ClaudeSonnet45Base
    ]
  }
}

client<llm> FastStructuredClient {
  provider fallback
  retry_policy StandardRetry
  options {
    strategy [
      ClaudeHaiku45Base
      GPT4oMiniBase
    ]
  }
}

client<llm> ValidationClient {
  provider fallback
  retry_policy StandardRetry
  options {
    strategy [
      GPT4oMiniBase
      ClaudeHaiku45Base
    ]
  }
}

// ============================================================================
// DATA TYPES
// ============================================================================

enum UserIntent {
  UPLOAD_DOCUMENT
  START_OCR_JOB
  CHECK_STATUS
  GET_RESULTS
  ADJUST_SETTINGS
  REPROCESS_WITH_CHANGES
  UNKNOWN
}

class PageRange {
  start_page int
  end_page int
  description string?
}

class FormatReference {
  reference_page int
  apply_to_pages PageRange
  user_instruction string
}

// Backend API Schema: Matches src/api/models/requests.py exactly
class ProcessingOptions {
  dpi int?                    // 72-600, default: 300
  method string?              // "auto" | "extract" | "ocr" | "hybrid", default: "auto"
  start_page int?             // >= 1, null = all pages from start
  end_page int?               // >= start_page, null = all pages to end
  staged_pipeline bool?       // default: true
  prefer_quality bool?        // default: true
}

class OCRJobParameters {
  file_id string?                           // REQUIRED for job submission
  model string?                             // "deepseek-ocr" | "qwen3-vl-8b" | "qwen3-vl-4b" | "qwen3-vl-2b"
  prompt_type string?                       // "markdown" | "ocr" | "structured", default: "markdown"
  custom_prompts map<string, string>?       // Keys: "ocr", "merge", "format_markdown"
  processing_options ProcessingOptions?     // Processing configuration
  output_format string?                     // "markdown" | "text" | "json", default: "markdown"
  format_references FormatReference[]?      // For cross-page formatting
}

class RefactoredPrompts {
  ocr_prompt string? @stream.with_state
  merge_prompt string? @stream.with_state
  format_prompt string? @stream.with_state
  reasoning string @stream.done
  confidence string @stream.done
}

class ToolCall {
  endpoint string
  method string
  parameters map<string, string>
  body map<string, string>?
  description string
  sequence_order int
}

class ToolCallSequence {
  calls ToolCall[]
  requires_page_fetch bool
  page_to_fetch int?
  reasoning string
}

class ValidationResult {
  is_valid bool
  errors string[]
  warnings string[]
}

class OrchestrationResult {
  intent UserIntent
  parameters OCRJobParameters
  refactored_prompts RefactoredPrompts?
  tool_calls ToolCallSequence
  validation ValidationResult
  user_message string  // Plain English response to user explaining what will be done
}

// ============================================================================
// CORE FUNCTIONS
// ============================================================================

function ClassifyUserIntent(user_message: string) -> UserIntent {
  client FastStructuredClient
  
  prompt #"
    {{ _.role("system") }}
    You are an intent classifier for an OCR service API.
    Classify user requests into one of these intents.
    
    {{ _.role("user") }}
    {{ user_message }}
    
    {{ ctx.output_format }}
  "#
}

function ExtractJobParameters(
  user_message: string,
  current_config: string,
  job_context: string?
) -> OCRJobParameters {
  client FastStructuredClient

  prompt #"
    {{ _.role("system") }}
    You extract OCR job parameters from natural language requests to match the backend API schema.

    Available models:
    - "deepseek-ocr" (DEFAULT, OCR-specialized, 6-7GB VRAM, ~7s load)
    - "qwen3-vl-8b" (highest quality, 14-15GB VRAM, ~150s load)
    - "qwen3-vl-4b" (intermediate, 8-9GB VRAM, ~90s load)
    - "qwen3-vl-2b" (fast, 4-5GB VRAM, ~40s load)

    Available DPI: 72-600 (default: 300, recommended: 150, 300, 600)

    Available output formats: "markdown" (default), "text", "json"

    Available processing methods: "auto" (default), "extract", "ocr", "hybrid"

    PAGE RANGE EXTRACTION - IMPORTANT:
    Extract processing_options.start_page and end_page from user request:
    - "first page" → processing_options: { start_page: 1, end_page: 1 }
    - "page 5" → processing_options: { start_page: 5, end_page: 5 }
    - "pages 3-7" → processing_options: { start_page: 3, end_page: 7 }
    - "pages 10 to 15" → processing_options: { start_page: 10, end_page: 15 }
    - "whole document" → processing_options: { start_page: null, end_page: null }
    - "all pages" → processing_options: { start_page: null, end_page: null }
    - No mention → processing_options: { start_page: null, end_page: null }

    CUSTOM PROMPTS:
    Map to custom_prompts object with keys:
    - "ocr": OCR extraction instructions
    - "merge": Merging embedded+OCR text instructions
    - "format_markdown": Markdown formatting instructions

    FORMAT REFERENCES:
    Include format_references if they mention formatting based on specific pages.

    Leave fields null if not mentioned. Return ONLY the parameter extraction.

    {{ _.role("user") }}
    User request: {{ user_message }}

    Current configuration: {{ current_config }}
    {% if job_context %}
    Job context: {{ job_context }}
    {% endif %}

    {{ ctx.output_format }}
  "#
}

function RefactorUserPromptForOCR(
  user_instructions: string,
  document_context: string?,
  target_stage: string,
  format_references: FormatReference[]?,
  job_id: string?
) -> RefactoredPrompts {
  client ReasoningClient
  
  prompt #"
    {{ _.role("system") }}
    You are an expert at crafting OCR steering prompts for vision-language models.
    
    EXAMPLE TRANSFORMATIONS:
    
    1. Cross-page formatting:
       User: "Refer to page 3 for how to format pages 8-20"
       Reasoning: Need consistency, page 3 is template, identify patterns
       OCR Prompt: "Extract text preserving exact formatting: heading levels, 
       list indentation, table layouts, spacing. Match reference page style."
    
    2. Selective extraction:
       User: "Focus on tables, ignore headers and footers"
       Reasoning: Prioritize tables, filter headers/footers, preserve structure
       OCR Prompt: "Extract tabular data with column alignment. Use spaces/tabs 
       for columns. Ignore header/footer text. Focus on main content tables."
    
    3. Domain accuracy:
       User: "Financial doc with numbers. Decimals must be accurate."
       Reasoning: Numerical accuracy critical, decimal precision, financial context
       OCR Prompt: "Extract with special attention to numerical accuracy. Preserve 
       decimals, commas, currency symbols, percentages exactly. Double-check digits."
    
    STAGE GUIDELINES:
    - OCR: Extraction accuracy, layout preservation
    - Merge: Combining sources, fixing errors, consistency
    - Format: Output structure, markdown/json formatting
    
    {{ _.role("user") }}
    User instructions: {{ user_instructions }}
    
    {% if document_context %}
    Document context: {{ document_context }}
    {% endif %}
    
    Target stage: {{ target_stage }}
    
    {% if format_references %}
    Format references: {{ format_references }}
    {% endif %}
    
    {% if job_id %}
    Job ID: {{ job_id }}
    {% endif %}
    
    {{ ctx.output_format(prefix="Return your analysis with reasoning, prompts, and confidence (high/medium/low):\n") }}
  "#
}

function GenerateToolCallSequence(
  intent: UserIntent,
  parameters: OCRJobParameters,
  current_job_id: string?,
  has_format_references: bool
) -> ToolCallSequence {
  client FastStructuredClient
  
  prompt #"
    {{ _.role("system") }}
    Generate API call sequences to fulfill user requests.
    
    Available endpoints:
    - POST /api/v1/upload
    - POST /api/v1/process (body: file_id, model, dpi, format, custom_prompts)
    - GET /api/v1/status/{job_id}
    - GET /api/v1/results/{job_id}
    - GET /api/v1/results/{job_id}/page/{page_num}
    - GET /api/v1/config
    - PUT /api/v1/config
    
    If has_format_references is true:
    1. First GET the reference page
    2. Then refactor prompts
    3. Then POST process with custom prompts
    
    {{ _.role("user") }}
    Intent: {{ intent }}
    Parameters: {{ parameters }}
    Current job ID: {{ current_job_id if current_job_id else "none" }}
    Needs page fetch: {{ has_format_references }}
    
    {{ ctx.output_format }}
  "#
}

function ValidateJobParameters(parameters: OCRJobParameters) -> ValidationResult {
  client ValidationClient
  
  prompt #"
    {{ _.role("system") }}
    Validate OCR job parameters.
    
    Rules:
    - model: qwen3-vl-8b, qwen3-vl-4b, qwen3-vl-2b, deepseek-ocr, or tesseract
    - dpi: 150, 300, or 600
    - format: text, markdown, or json
    - prompts: not empty, <1000 chars
    - format_references: valid pages and ranges
    
    {{ _.role("user") }}
    {{ parameters }}
    
    {{ ctx.output_format }}
  "#
}

function HandleUserMessage(
  user_message: string,
  current_job_id: string?,
  current_config: string,
  job_context: string?
) -> OrchestrationResult {
  client FastStructuredClient

  prompt #"
    {{ _.role("system") }}
    You orchestrate the OCR service workflow and generate user-facing responses.

    BACKEND API DOCUMENTATION:

    Endpoint: POST /api/v1/process/jobs
    Request Body:
    {
      "file_id": string (REQUIRED),
      "model": "deepseek-ocr" | "qwen3-vl-8b" | "qwen3-vl-4b" | "qwen3-vl-2b" | null,
      "prompt_type": "markdown" | "ocr" | "structured" | null,
      "custom_prompts": {
        "ocr": string,
        "merge": string,
        "format_markdown": string
      } | null,
      "processing_options": {
        "dpi": int (72-600, default: 300),
        "method": "auto" | "extract" | "ocr" | "hybrid" (default: "auto"),
        "start_page": int | null (>= 1, null = from start),
        "end_page": int | null (>= start_page, null = to end),
        "staged_pipeline": bool (default: true),
        "prefer_quality": bool (default: true)
      } | null,
      "output_format": "markdown" | "text" | "json" (default: "markdown")
    }

    WORKFLOW:
    1. Classify user intent (UPLOAD_DOCUMENT, START_OCR_JOB, CHECK_STATUS, GET_RESULTS, etc.)
    2. Extract parameters matching backend API schema exactly
    3. Determine if prompt refactoring needed (if format_references present)
    4. Generate tool call sequence
    5. Validate parameters
    6. Generate user_message: Plain English response explaining what will be done

    USER MESSAGE EXAMPLES:
    - "I'll parse page 1 of your document using DeepSeek-OCR in markdown format."
    - "I'll process pages 3-7 of your document using Qwen3-VL-8B at 600 DPI."
    - "I'll parse the entire document using DeepSeek-OCR with hybrid processing."
    - "Your job is currently processing. I'll check the status for you."
    - "I don't understand that request. Could you please specify what you'd like me to do with your document?"

    Return structured orchestration data with user_message field.

    {{ _.role("user") }}
    User message: {{ user_message }}

    {% if current_job_id %}
    Current job ID: {{ current_job_id }}
    {% endif %}

    Current config: {{ current_config }}

    {% if job_context %}
    Job context: {{ job_context }}
    {% endif %}

    {{ ctx.output_format(prefix="Return the complete orchestration plan with user_message:\n") }}
  "#
}
