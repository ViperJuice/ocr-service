/**
 * BAML Integration Wrapper
 *
 * Single source of truth for BAML-generated types and client functions.
 * All BAML imports should go through this module.
 */

import { b } from "@/baml_client";
import {
  UserIntent,
} from "@/baml_client/types";
import type {
  PageRange,
  FormatReference,
  ProcessingOptions,
  OCRJobParameters,
  RefactoredPrompts,
  ToolCall,
  ToolCallSequence,
  ValidationResult,
  OrchestrationResult,
} from "@/baml_client/types";

// ============================================================================
// Re-export BAML Types
// ============================================================================

export type {
  UserIntent,
  PageRange,
  FormatReference,
  ProcessingOptions,
  OCRJobParameters,
  RefactoredPrompts,
  ToolCall,
  ToolCallSequence,
  ValidationResult,
  OrchestrationResult,
};

// Export enum values for runtime checks
export { UserIntent as UserIntentEnum };

// ============================================================================
// BAML Client Wrapper Functions
// ============================================================================

export const bamlPrompts = {
  /**
   * Orchestrate user message and return structured workflow
   *
   * @param message - User's natural language request
   * @param jobId - Current job ID (if exists)
   * @param config - Current system config as JSON string
   * @param jobContext - Job context information
   * @returns Complete orchestration with intent, parameters, tool calls, validation
   */
  async orchestrateUserMessage(
    message: string,
    jobId?: string,
    config?: string,
    jobContext?: string
  ): Promise<OrchestrationResult> {
    return await b.HandleUserMessage(
      message,
      jobId || null,
      config || "{}",
      jobContext || null
    );
  },

  /**
   * Refactor user prompt into OCR steering prompts
   *
   * @param userInstructions - User's prompt instructions
   * @param documentContext - Context about the document
   * @param targetStage - Pipeline stage ("ocr" | "merge" | "format")
   * @param formatReferences - Cross-page format references
   * @param jobId - Job ID for context
   * @returns Refactored prompts with reasoning and confidence
   */
  async refactorPromptWithStreaming(
    userInstructions: string,
    documentContext: string,
    targetStage: string,
    formatReferences: FormatReference[],
    jobId?: string
  ): Promise<RefactoredPrompts> {
    return await b.RefactorUserPromptForOCR(
      userInstructions,
      documentContext || null,
      targetStage,
      formatReferences.length > 0 ? formatReferences : null,
      jobId || null
    );
  },

  /**
   * Extract job parameters from natural language
   */
  async extractJobParameters(
    userMessage: string,
    currentConfig: string,
    jobContext?: string
  ): Promise<OCRJobParameters> {
    return await b.ExtractJobParameters(
      userMessage,
      currentConfig,
      jobContext || null
    );
  },

  /**
   * Classify user intent
   */
  async classifyUserIntent(userMessage: string): Promise<UserIntent> {
    return await b.ClassifyUserIntent(userMessage);
  },

  /**
   * Validate job parameters
   */
  async validateJobParameters(
    parameters: OCRJobParameters
  ): Promise<ValidationResult> {
    return await b.ValidateJobParameters(parameters);
  },

  /**
   * Generate API tool call sequence
   */
  async generateToolCallSequence(
    intent: UserIntent,
    parameters: OCRJobParameters,
    currentJobId: string | null,
    hasFormatReferences: boolean
  ): Promise<ToolCallSequence> {
    return await b.GenerateToolCallSequence(
      intent,
      parameters,
      currentJobId,
      hasFormatReferences
    );
  },
};

// ============================================================================
// Type Guards
// ============================================================================

export function isUserIntent(value: unknown): value is UserIntent {
  return Object.values(UserIntent).includes(value as UserIntent);
}

export function isValidProcessingOptions(
  opts: unknown
): opts is ProcessingOptions {
  if (!opts || typeof opts !== "object") return false;
  const o = opts as Partial<ProcessingOptions>;

  if (o.dpi !== undefined && o.dpi !== null && (typeof o.dpi !== "number" || o.dpi < 72 || o.dpi > 600)) {
    return false;
  }

  if (o.method !== undefined && o.method !== null && !["auto", "extract", "ocr", "hybrid"].includes(o.method)) {
    return false;
  }

  return true;
}
