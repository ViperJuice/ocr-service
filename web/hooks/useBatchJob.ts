import { useState, useCallback, useEffect } from "react";
import { apiClient } from "@/lib/api-client";
import {
  DirectoryInfo,
  BatchJobStatus,
  BatchResultResponse,
  CustomPrompts,
  ProcessingOptions,
  OutputFormat,
} from "@/lib/types";
import { useRealtimeBatch } from "./useRealtimeBatch";

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

  // PHASE 3.5: Realtime subscription for dual-subscription pattern
  const {
    batch: realtimeBatchJob,
    isConnected: isRealtimeConnected,
    latency: realtimeLatency
  } = useRealtimeBatch(currentBatchJob?.batch_job_id ?? null);

  // Log comparison between SSE and Realtime updates
  useEffect(() => {
    if (realtimeBatchJob && currentBatchJob) {
      console.log('[PHASE 3.5] Batch dual-subscription comparison:', {
        batchJobId: currentBatchJob.batch_job_id,
        realtimeConnected: isRealtimeConnected,
        realtimeStatus: realtimeBatchJob.status,
        realtimeProgress: `${realtimeBatchJob.documents_completed}/${realtimeBatchJob.total_documents}`,
        realtimeLatency: realtimeLatency ? `${realtimeLatency}ms` : 'N/A',
      });
    }
  }, [realtimeBatchJob, currentBatchJob, isRealtimeConnected, realtimeLatency]);

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

    // PHASE 3.5: Realtime state
    realtimeBatchJob,
    isRealtimeConnected,
    realtimeLatency,
  };
}
