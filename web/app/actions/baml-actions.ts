'use server';

import { bamlPrompts } from "@/lib/baml-wrapper";

export async function orchestrateUserMessage(
  message: string,
  jobId?: string,
  config?: string,
  jobContext?: string
) {
  return await bamlPrompts.orchestrateUserMessage(message, jobId, config, jobContext);
}

export async function refactorPromptWithStreaming(
  userInstructions: string,
  documentContext: string,
  targetStage: string,
  formatReferences: any[],
  jobId?: string
) {
  return await bamlPrompts.refactorPromptWithStreaming(
    userInstructions,
    documentContext,
    targetStage,
    formatReferences,
    jobId
  );
}
