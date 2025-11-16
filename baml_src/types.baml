// BAML Type Definitions
// Single source of truth for Python (Pydantic) and TypeScript types

// ==================== Core OCR Types ====================

class OCRResult {
  text string @description("Extracted text content")
  model_name string @description("Model used for extraction (e.g., 'deepseek-ocr', 'qwen3-vl-8b')")
  processing_time float @description("Time taken to process in seconds")
  format string @description("Processing format/type (e.g., 'ocr', 'merge', 'visual')")
  metadata OCRMetadata? @description("Optional metadata about the OCR result")
}

class OCRMetadata {
  container_mode bool @description("Whether processing used container mode")
  openai_compatible bool @description("Whether OpenAI-compatible API was used")
  image_width int? @description("Width of processed image in pixels")
  image_height int? @description("Height of processed image in pixels")
  char_count int? @description("Number of characters in extracted text")
  word_count int? @description("Number of words in extracted text")
  has_visual_elements bool? @description("Whether visual formatting was applied")
}

// ==================== Page Processing Types ====================

class PageResult {
  page_num int @description("Page number (0-indexed)")
  text string @description("Extracted/merged text content")
  processing_method string @description("Method used: 'embedded', 'ocr', 'hybrid', 'visual'")
  processing_time float @description("Time taken to process this page in seconds")
  char_count int @description("Number of characters in text")
  word_count int @description("Number of words in text")
  has_visual_elements bool @description("Whether page contains visual elements (tables, images)")
  metadata PageMetadata? @description("Optional page metadata")
}

class PageMetadata {
  embedded_text_length int? @description("Length of embedded PDF text")
  ocr_text_length int? @description("Length of OCR-extracted text")
  merge_strategy string? @description("Strategy used for merging (e.g., 'llm-merge', 'fallback')")
  visual_formatting_applied bool? @description("Whether visual formatting stage was applied")
  spatial_blocks_count int? @description("Number of spatial text blocks detected")
  has_tables bool? @description("Whether page contains tables")
  has_images bool? @description("Whether page contains images")
  dpi int? @description("DPI used for image rendering")
}

// ==================== Spatial/Visual Types ====================

class BoundingBox {
  x0 float @description("Left coordinate")
  y0 float @description("Top coordinate")
  x1 float @description("Right coordinate")
  y1 float @description("Bottom coordinate")
  page_width float @description("Total page width (for normalization)")
  page_height float @description("Total page height (for normalization)")
}

class TextBlock {
  text string @description("Text content of the block")
  bbox BoundingBox @description("Bounding box coordinates")
  font_size float? @description("Font size in points")
  font_name string? @description("Font name/family")
  block_type string @description("Type: 'paragraph', 'heading', 'list', 'table', 'caption'")
  confidence float? @description("Confidence score (0.0-1.0)")
}

class PageStructure {
  page_num int @description("Page number (0-indexed)")
  width float @description("Page width in points")
  height float @description("Page height in points")
  text_blocks TextBlock[] @description("List of text blocks with spatial information")
  has_tables bool @description("Whether page contains tables")
  has_images bool @description("Whether page contains images")
  column_count int? @description("Number of columns detected (1, 2, 3, etc.)")
  reading_order int[]? @description("Suggested reading order (indices into text_blocks)")
}

// ==================== Job/Processing Types ====================

enum JobStatus {
  Queued @description("Job is queued for processing")
  Processing @description("Job is currently being processed")
  Completed @description("Job completed successfully")
  Failed @description("Job failed with error")
  Cancelled @description("Job was cancelled by user")
}

class ProcessingOptions {
  method string? @description("Processing method: 'embedded', 'ocr', 'hybrid', 'visual'")
  enable_visual_formatting bool? @description("Enable visual formatting stage")
  spatial_awareness bool? @description("Enable spatial/layout awareness")
  table_detection bool? @description("Enable table detection")
  min_text_chars int? @description("Minimum characters to consider page valid")
  dpi int? @description("DPI for image rendering (default: 300)")
  custom_prompts CustomPrompts? @description("Custom prompts for LLM stages")
}

class CustomPrompts {
  ocr string? @description("Custom prompt for OCR stage")
  merge string? @description("Custom prompt for merge stage")
  visual string? @description("Custom prompt for visual formatting stage")
}

// ==================== Batch Processing Types ====================

class BatchResult {
  job_id string @description("Unique job identifier")
  status JobStatus @description("Current job status")
  total_pages int @description("Total number of pages")
  pages_completed int @description("Number of pages completed")
  progress_pct float @description("Progress percentage (0.0-100.0)")
  page_results PageResult[] @description("Results for completed pages")
  error_message string? @description("Error message if job failed")
  started_at string? @description("ISO timestamp when job started")
  completed_at string? @description("ISO timestamp when job completed")
}

// ==================== Container Health Types ====================

class ContainerHealth {
  status string @description("Health status: 'ok', 'ready', 'error'")
  model_loaded bool @description("Whether model is currently loaded in VRAM")
  gpu_available bool @description("Whether GPU is accessible")
  memory_used_mb float? @description("GPU memory used in MB")
  memory_total_mb float? @description("Total GPU memory in MB")
}

class SystemHealth {
  deepseek ContainerHealth @description("DeepSeek-OCR container health")
  qwen ContainerHealth @description("QWEN3-VL container health")
  timestamp string @description("ISO timestamp of health check")
}
