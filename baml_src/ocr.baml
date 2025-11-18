// BAML OCR Functions
// Defines functions for OCR extraction, text merging, and visual formatting

// ==================== OCR Extraction ====================

function ExtractTextOCR(page_image: image, custom_prompt: string?) -> string {
  client DeepSeekOCR
  prompt #"
    {{ _.role("user") }}

    {% if custom_prompt %}
      {{ custom_prompt }}
    {% else %}
      Extract all text from this image with high accuracy.
      Use Markdown to preserve the original layout and formatting as much as possible.
      Include all visible text, numbers, symbols, and special characters.
      Maintain line breaks and spacing.
    {% endif %}

    {{ page_image }}
  "#
}

// ==================== Text Merging ====================

function MergeTexts(
  page_image: image,
  embedded_text: string,
  ocr_text: string,
  custom_prompt: string?
) -> string {
  client QWEN3VL8B
  prompt #"
    {{ _.role("user") }}

    {% if custom_prompt %}
      {{ custom_prompt }}
    {% else %}
      You are an expert text, image and formatting merger. Compare and merge these two text versions with the image from the same document page:

      **Embedded Text (from PDF):**
      ```
      {{ embedded_text }}
      ```

      **OCR Text (from image):**
      ```
      {{ ocr_text }}
      ```

      Your task:
      1. Compare both versions carefully alongside the image.
      2. Use the embedded text as the base (it's usually more accurate for standard text)
      3. Use the OCR text to fill in missing content (formulas, special symbols, tables)
      4. Fix any obvious OCR errors by cross-referencing with the embedded text
      5. Use markdown to preserve the original layout and formatting based on the image
      6. Include all content from both text sources and the image
      7. Only include the original text and formatting and figure references
      8. Do not include any additional comments or dialog

      Provide the most accurate merged version. Return only the final merged text.
    {% endif %}

    Reference image:
    {{ page_image }}
  "#
}

// ==================== Streaming Merge ====================

function MergeTextsStreaming(
  page_image: image,
  embedded_text: string,
  ocr_text: string
) -> string {
  client QWEN3VL8B
  prompt #"
    {{ _.role("user") }}

    Compare and merge these two text versions from the same document page.
    Use embedded text as base, fill in gaps with OCR text, and fix OCR errors.

    **Embedded Text:**
    {{ embedded_text }}

    **OCR Text:**
    {{ ocr_text }}

    Return the merged text immediately:
    {{ page_image }}
  "#
}

// ==================== Visual Formatting ====================

function ExtractVisualFormatting(
  page_image: image,
  base_text: string,
  spatial_data: PageStructure,
  custom_prompt: string?
) -> OCRResult {
  client QWEN3VL8B
  prompt #"
    {{ _.role("user") }}

    {% if custom_prompt %}
      {{ custom_prompt }}
    {% else %}
      You are an expert at understanding document layout and structure.

      **Base Text (without formatting):**
      ```
      {{ base_text }}
      ```

      **Spatial Information:**
      - Page size: {{ spatial_data.width }}x{{ spatial_data.height }} points
      - Text blocks: {{ spatial_data.text_blocks | length }}
      - Has tables: {{ spatial_data.has_tables }}
      - Has images: {{ spatial_data.has_images }}
      {% if spatial_data.column_count %}
      - Columns: {{ spatial_data.column_count }}
      {% endif %}

      **Your task:**
      1. Analyze the visual structure of this document page
      2. Apply appropriate formatting (headings, lists, tables, columns)
      3. Preserve reading order and hierarchy
      4. Use markdown for structure (headings, bold, italic, lists, tables)
      5. Maintain proper spacing and layout

      Return the formatted text with proper structure and markdown:
    {% endif %}

    {{ page_image }}

    {{ ctx.output_format }}
  "#
}

// ==================== Batch OCR (Fallback) ====================

function ExtractTextOCRFallback(page_image: image, custom_prompt: string?) -> OCRResult {
  client OCRFallback
  prompt #"
    {{ _.role("user") }}

    {% if custom_prompt %}
      {{ custom_prompt }}
    {% else %}
      Free OCR. Extract all text from this image with high accuracy.
      Preserve the original layout and formatting as much as possible.
    {% endif %}

    {{ page_image }}

    {{ ctx.output_format }}
  "#
}

// ==================== Health Check Function ====================

function CheckContainerHealth() -> string {
  client DeepSeekOCR
  prompt #"
    {{ _.role("user") }}
    Respond with 'OK' if you can process this request.
  "#
}
