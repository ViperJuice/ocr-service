// BAML wrapper for OCR Service prompting
import { b } from "../baml_client";
import { CustomPrompts } from "./types";
import type {
  OrchestrationResult,
  UserIntent,
  OCRJobParameters,
  ToolCallSequence,
  RefactoredPrompts,
  ValidationResult,
  FormatReference,
} from "../baml_client/types";

export const bamlPrompts = {
  /**
   * Main orchestration - converts user message into structured plan
   */
  async orchestrateUserMessage(
    message: string,
    jobId?: string,
    config?: string,
    jobContext?: string
  ): Promise<OrchestrationResult> {
    try {
      // LOG: What we're sending to BAML/LLM
      console.log("=== BAML INPUT (TO LLM) ===");
      console.log("Function: HandleUserMessage");
      console.log("User Message:", message);
      console.log("Job ID:", jobId ?? "null");
      console.log("Config:", config ?? "{}");
      console.log("Job Context:", jobContext ?? "null");
      console.log("===========================");

      const result = await b.HandleUserMessage(
        message,
        jobId ?? null,
        config ?? "{}",
        jobContext ?? null
      );

      // LOG: What we got back from BAML/LLM
      console.log("=== BAML OUTPUT (FROM LLM) ===");
      console.log("Intent:", result.intent);
      console.log("Parameters:", JSON.stringify(result.parameters, null, 2));
      console.log("User Message:", result.user_message);
      console.log("==============================");

      return result;
    } catch (error) {
      console.error("BAML HandleUserMessage error:", error);
      // Return fallback orchestration
      return {
        intent: "UNKNOWN" as UserIntent,
        parameters: {},
        refactored_prompts: null,
        tool_calls: {
          calls: [],
          requires_page_fetch: false,
          page_to_fetch: null,
          reasoning: "Error during orchestration",
        },
        validation: {
          is_valid: false,
          errors: [(error as Error).message],
          warnings: [],
        },
        user_message: "I don't understand that request. Could you please restate it?",
      };
    }
  },

  /**
   * Streaming prompt refactoring for complex instructions
   */
  async refactorPromptWithStreaming(
    userInstructions: string,
    documentContext: string,
    targetStage: string,
    formatReferences: FormatReference[],
    jobId?: string,
    onProgress?: (partial: any) => void
  ): Promise<RefactoredPrompts> {
    try {
      if (onProgress) {
        // Use streaming API
        const stream = b.stream.RefactorUserPromptForOCR(
          userInstructions,
          documentContext ?? null,
          targetStage,
          formatReferences ?? null,
          jobId ?? null
        );

        let finalResult: RefactoredPrompts | null = null;
        for await (const partial of stream) {
          onProgress(partial);
          if (partial) {
            finalResult = partial as RefactoredPrompts;
          }
        }

        return finalResult ?? {
          ocr_prompt: null,
          merge_prompt: null,
          format_prompt: null,
          reasoning: "",
          confidence: "low",
        };
      } else {
        // Non-streaming
        return await b.RefactorUserPromptForOCR(
          userInstructions,
          documentContext ?? null,
          targetStage,
          formatReferences ?? null,
          jobId ?? null
        );
      }
    } catch (error) {
      console.error("BAML RefactorUserPromptForOCR error:", error);
      return {
        ocr_prompt: null,
        merge_prompt: null,
        format_prompt: null,
        reasoning: `Error: ${(error as Error).message}`,
        confidence: "low",
      };
    }
  },

  /**
   * Classify user intent quickly
   */
  async classifyIntent(message: string): Promise<UserIntent> {
    try {
      return await b.ClassifyUserIntent(message);
    } catch (error) {
      console.error("BAML ClassifyUserIntent error:", error);
      return "UNKNOWN" as UserIntent;
    }
  },

  /**
   * Extract parameters from user message
   */
  async extractParameters(
    message: string,
    config: string,
    context?: string
  ): Promise<OCRJobParameters> {
    try {
      return await b.ExtractJobParameters(
        message,
        config,
        context ?? null
      );
    } catch (error) {
      console.error("BAML ExtractJobParameters error:", error);
      return {};
    }
  },

  /**
   * Generate tool call sequence
   */
  async generateToolCalls(
    intent: UserIntent,
    params: OCRJobParameters,
    jobId?: string,
    hasReferences?: boolean
  ): Promise<ToolCallSequence> {
    try {
      return await b.GenerateToolCallSequence(
        intent,
        params,
        jobId ?? null,
        hasReferences ?? false
      );
    } catch (error) {
      console.error("BAML GenerateToolCallSequence error:", error);
      return {
        calls: [],
        requires_page_fetch: false,
        page_to_fetch: null,
        reasoning: `Error: ${(error as Error).message}`,
      };
    }
  },

  /**
   * Validate parameters
   */
  async validateParameters(params: OCRJobParameters): Promise<ValidationResult> {
    try {
      return await b.ValidateJobParameters(params);
    } catch (error) {
      console.error("BAML ValidateJobParameters error:", error);
      return {
        is_valid: false,
        errors: [(error as Error).message],
        warnings: [],
      };
    }
  },

  /**
   * Parse user command from chat input (legacy support)
   * DEPRECATED: This function is no longer used. Use command-parser.ts instead.
   */
  // async parseCommand(userMessage: string, availablePages?: number) {
  //   try {
  //     return await b.ParseUserCommand(userMessage, availablePages ?? null);
  //   } catch (error) {
  //     console.error("BAML ParseUserCommand error:", error);
  //     return {
  //       action: "unknown",
  //       page_number: null,
  //       start_page: null,
  //       end_page: null,
  //       format: null,
  //       special_instructions: userMessage,
  //     };
  //   }
  // },

  /**
   * Generate chat response based on processing status
   * DEPRECATED: This function is no longer used.
   */
  // async generateChatResponse(
  //   userCommand: string,
  //   processingStatus: string,
  //   resultPreview?: string
  // ): Promise<string> {
  //   try {
  //     return await b.GenerateChatResponse(
  //       userCommand,
  //       processingStatus,
  //       resultPreview ?? null
  //     );
  //   } catch (error) {
  //     console.error("BAML GenerateChatResponse error:", error);
  //     return `Processing your request: ${processingStatus}`;
  //   }
  // },

  /**
   * Extract front matter metadata from a page
   * DEPRECATED: This function is no longer used.
   */
  // async extractFrontMatter(pageText: string) {
  //   try {
  //     return await b.ExtractFrontMatter(pageText);
  //   } catch (error) {
  //     console.error("BAML ExtractFrontMatter error:", error);
  //     return {
  //       title: null,
  //       author: null,
  //       date: null,
  //       document_type: null,
  //       page_count: null,
  //     };
  //   }
  // },

  /**
   * Get specialized prompts for different document types
   */
  getDocumentTypePrompts(documentType: "legal" | "technical" | "medical" | "standard"): CustomPrompts {
    // These reference the BAML functions defined in main.baml
    switch (documentType) {
      case "legal":
        return {
          // The merge prompt will use MergeLegalDocument BAML function
          merge: "baml://MergeLegalDocument",
        };
      case "technical":
        return {
          merge: "baml://MergeTechnicalDocument",
        };
      case "medical":
        return {
          merge: "baml://MergeMedicalDocument",
        };
      default:
        return {
          merge: "baml://MergeText",
        };
    }
  },

  /**
   * Format text as markdown using BAML
   * DEPRECATED: This function is no longer used.
   */
  // async formatAsMarkdown(rawText: string, context?: string): Promise<string> {
  //   try {
  //     return await b.FormatAsMarkdown(rawText, context ?? null);
  //   } catch (error) {
  //     console.error("BAML FormatAsMarkdown error:", error);
  //     return rawText;
  //   }
  // },

  /**
   * Extract OCR text using BAML
   * DEPRECATED: This function is no longer used.
   */
  // async extractOcr(imageData: string): Promise<string> {
  //   try {
  //     return await b.OcrExtract(imageData);
  //   } catch (error) {
  //     console.error("BAML OcrExtract error:", error);
  //     throw error;
  //   }
  // },

  /**
   * Merge embedded and OCR text using BAML
   * DEPRECATED: This function is no longer used.
   */
  // async mergeText(embeddedText: string, ocrText: string): Promise<string> {
  //   try {
  //     return await b.MergeText(embeddedText, ocrText);
  //   } catch (error) {
  //     console.error("BAML MergeText error:", error);
  //     return ocrText || embeddedText;
  //   }
  // },
};

/**
 * Create custom BAML prompts for the prompt library
 */
export async function createCustomBAMLPrompt(
  name: string,
  category: string,
  mergePromptTemplate: string
) {
  return {
    id: `custom-${Date.now()}`,
    name,
    category,
    description: `Custom ${category} prompt`,
    prompts: {
      merge: mergePromptTemplate,
    },
    createdAt: Date.now(),
    updatedAt: Date.now(),
  };
}
