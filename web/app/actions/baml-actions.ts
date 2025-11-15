'use server';

import { bamlPrompts } from "@/lib/baml-wrapper";
import type {
  OrchestrationResult,
  RefactoredPrompts,
  FormatReference,
} from "@/lib/baml-wrapper";

export async function orchestrateUserMessage(
  message: string,
  jobId?: string,
  config?: string,
  jobContext?: string
): Promise<OrchestrationResult> {
  return await bamlPrompts.orchestrateUserMessage(message, jobId, config, jobContext);
}

export async function refactorPromptWithStreaming(
  userInstructions: string,
  documentContext: string,
  targetStage: string,
  formatReferences: FormatReference[],
  jobId?: string
): Promise<RefactoredPrompts> {
  return await bamlPrompts.refactorPromptWithStreaming(
    userInstructions,
    documentContext,
    targetStage,
    formatReferences,
    jobId
  );
}
