"use client";

import { useState, useCallback } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { apiClient, ApiError } from "@/lib/api-client";
import {
  FileMetadata,
  JobCreatedResponse,
  JobStatusResponse,
  JobResult,
  JobSubmitRequest,
  OutputFormat,
} from "@/lib/types";
import { useRealtimeJob } from "./useRealtimeJob";

export function useOcrJob() {
  const [currentFile, setCurrentFile] = useState<FileMetadata | null>(null);
  const [currentJob, setCurrentJob] = useState<JobCreatedResponse | null>(null);
  const [jobResult, setJobResult] = useState<JobResult | null>(null);

  // PHASE 4: Realtime subscription (exclusive data source)
  const {
    job: currentJobData,
    isConnected
  } = useRealtimeJob(currentJob?.job_id ?? null);

  // Upload file mutation
  const uploadMutation = useMutation({
    mutationFn: (file: File) => apiClient.uploadFile(file),
    onSuccess: (data) => {
      setCurrentFile(data);
    },
    onError: (error: ApiError) => {
      console.error("Upload failed:", error.message);
    },
  });

  // Submit job mutation
  const submitJobMutation = useMutation({
    mutationFn: (request: JobSubmitRequest) => apiClient.submitJob(request),
    onSuccess: (data) => {
      setCurrentJob(data);
    },
    onError: (error: ApiError) => {
      console.error("Job submission failed:", error.message);
      // Re-throw to propagate to caller when using mutateAsync
      throw error;
    },
  });

  // Get job result
  const fetchResult = useCallback(async (jobId: string) => {
    try {
      const result = await apiClient.getJobResult(jobId);
      setJobResult(result);
      return result;
    } catch (error) {
      console.error("Failed to fetch result:", error);
      throw error;
    }
  }, []);

  // Cancel job
  const cancelJob = useCallback(async (jobId: string) => {
    try {
      await apiClient.cancelJob(jobId);
      setCurrentJob(null);
    } catch (error) {
      console.error("Failed to cancel job:", error);
      throw error;
    }
  }, []);

  // Download result
  const downloadResult = useCallback(async (jobId: string, filename: string) => {
    try {
      const blob = await apiClient.downloadResult(jobId);
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = filename;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      window.URL.revokeObjectURL(url);
    } catch (error) {
      console.error("Failed to download result:", error);
      throw error;
    }
  }, []);

  // Clear current state
  const reset = useCallback(() => {
    setCurrentFile(null);
    setCurrentJob(null);
    setJobResult(null);
  }, []);

  return {
    // State (Realtime data as primary source)
    currentFile,
    currentJob: currentJobData ?? currentJob,
    jobResult,

    // Actions
    uploadFile: uploadMutation.mutateAsync,
    submitJob: submitJobMutation.mutateAsync,
    fetchResult,
    cancelJob,
    downloadResult,
    reset,

    // Status
    isUploading: uploadMutation.isPending,
    isSubmitting: submitJobMutation.isPending,
    uploadError: uploadMutation.error,
    submitError: submitJobMutation.error,

    // PHASE 4: Realtime connection status
    isConnected,
  };
}

// Hook for querying job status
export function useJobStatus(jobId: string | null, enabled: boolean = true) {
  return useQuery({
    queryKey: ["job-status", jobId],
    queryFn: () => apiClient.getJobStatus(jobId!),
    enabled: enabled && !!jobId,
    // PHASE 4: No polling needed with Realtime
  });
}
