import { useState, useCallback } from "react";
import { apiClient } from "@/lib/api-client";
import {
  DirectoryInfo,
  BatchJobStatus,
  BatchResultResponse,
  CustomPrompts,
  ProcessingOptions,
  OutputFormat,
} from "@/lib/types";

interface BatchJobOptions {
  output_format?: OutputFormat;
  processing_options?: ProcessingOptions;
  model?: string;
  prompt_type?: string;
  custom_prompts?: CustomPrompts;
}

export function useBatchJob() {
  const [currentDirectory, setCurrentDirectory] = useState<DirectoryInfo | null>(null);
  const [currentBatchJob, setCurrentBatchJob] = useState<BatchJobStatus | null>(null);
  const [batchResult, setBatchResult] = useState<BatchResultResponse | null>(null);
  const [isUploading, setIsUploading] = useState(false);

  const uploadDirectory = useCallback(async (files: FileList, name: string) => {
    setIsUploading(true);
    try {
      const directory = await apiClient.uploadDirectory(files, name);
      setCurrentDirectory(directory);
      return directory;
    } finally {
      setIsUploading(false);
    }
  }, []);

  const submitBatchJob = useCallback(
    async (options: BatchJobOptions) => {
      if (!currentDirectory) {
        throw new Error("No directory uploaded");
      }

      const batch = await apiClient.submitBatchJob({
        directory_id: currentDirectory.directory_id,
        ...options,
      });
      setCurrentBatchJob(batch);
      return batch;
    },
    [currentDirectory]
  );

  const fetchBatchResult = useCallback(async (batchJobId: string) => {
    const result = await apiClient.getBatchResult(batchJobId);
    setBatchResult(result);
    return result;
  }, []);

  const reset = useCallback(() => {
    setCurrentDirectory(null);
    setCurrentBatchJob(null);
    setBatchResult(null);
  }, []);

  return {
    currentDirectory,
    currentBatchJob,
    batchResult,
    isUploading,
    uploadDirectory,
    submitBatchJob,
    fetchBatchResult,
    reset,
  };
}
