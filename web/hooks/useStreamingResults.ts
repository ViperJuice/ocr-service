/**
 * DEPRECATED (Phase 4): SSE-based streaming replaced by Supabase Realtime.
 *
 * This hook will be removed in Phase 5.
 *
 * Migration:
 * - Use {@link useRealtimeJob} or {@link useRealtimeBatch} instead
 * - SSE endpoints are deprecated and return 410 status
 *
 * See: specs/PHASE_4_IMPLEMENTATION_PLAN.md
 */

import { useState, useEffect, useRef } from "react";
import { StreamResultEvent } from "@/lib/types";

interface ModelLoadingState {
  isLoading: boolean;
  progress: number;
  currentStage: string;
  estimatedTime: number;
  gpuAllocation: any;
}

interface StreamingResults {
  ocrPages: Map<number, string>;
  mergePages: Map<number, string>;
  ocrComplete: boolean;
  mergeComplete: boolean;
  jobComplete: boolean;
  deepseekLoading: ModelLoadingState;
  qwenLoading: ModelLoadingState;
  ocrModel: string | null;
  mergeModel: string | null;
}

/**
 * Hook to consume SSE stream of OCR and merge results as they complete.
 *
 * @deprecated Use {@link useRealtimeJob} or {@link useRealtimeBatch} instead
 *             SSE endpoints deprecated in Phase 4, will be removed in Phase 5
 *
 * @param jobId - Job ID to stream results for
 * @param enabled - Whether to start streaming (default: true)
 * @returns Streaming results state
 */
const initialLoadingState: ModelLoadingState = {
  isLoading: false,
  progress: 0,
  currentStage: "",
  estimatedTime: 0,
  gpuAllocation: null,
};

export function useStreamingResults(jobId: string | null, enabled: boolean = true) {
  console.warn(
    'useStreamingResults is deprecated and will be removed in Phase 5. ' +
    'Use useRealtimeJob or useRealtimeBatch instead. ' +
    'SSE endpoints return 410 Gone.'
  );

  const [ocrPages, setOcrPages] = useState<Map<number, string>>(new Map());
  const [mergePages, setMergePages] = useState<Map<number, string>>(new Map());
  const [ocrComplete, setOcrComplete] = useState(false);
  const [mergeComplete, setMergeComplete] = useState(false);
  const [jobComplete, setJobComplete] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [deepseekLoading, setDeepseekLoading] = useState<ModelLoadingState>(initialLoadingState);
  const [qwenLoading, setQwenLoading] = useState<ModelLoadingState>(initialLoadingState);
  const [ocrModel, setOcrModel] = useState<string | null>(null);
  const [mergeModel, setMergeModel] = useState<string | null>(null);

  const eventSourceRef = useRef<EventSource | null>(null);

  useEffect(() => {
    if (!jobId || !enabled) {
      return;
    }

    // Reset state when job changes
    setOcrPages(new Map());
    setMergePages(new Map());
    setOcrComplete(false);
    setMergeComplete(false);
    setJobComplete(false);
    setError(null);
    setDeepseekLoading(initialLoadingState);
    setQwenLoading(initialLoadingState);
    setOcrModel(null);
    setMergeModel(null);

    // Connect to SSE stream
    const url = `${process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000"}/api/v1/process/jobs/${jobId}/stream-results`;
    const eventSource = new EventSource(url);
    eventSourceRef.current = eventSource;

    eventSource.addEventListener("ocr_page_complete", (event: MessageEvent) => {
      try {
        const data = JSON.parse(event.data);
        setOcrPages((prev) => {
          const next = new Map(prev);
          next.set(data.page_num, data.text);
          return next;
        });
        // Capture model information from first page
        if (data.model && !ocrModel) {
          setOcrModel(data.model);
        }
      } catch (err) {
        console.error("Failed to parse ocr_page_complete event:", err);
      }
    });

    eventSource.addEventListener("merge_page_complete", (event: MessageEvent) => {
      try {
        const data = JSON.parse(event.data);
        setMergePages((prev) => {
          const next = new Map(prev);
          next.set(data.page_num, data.text);
          return next;
        });
        // Capture model information from first page
        if (data.model && !mergeModel) {
          setMergeModel(data.model);
        }
      } catch (err) {
        console.error("Failed to parse merge_page_complete event:", err);
      }
    });

    eventSource.addEventListener("stage_complete", (event: MessageEvent) => {
      try {
        const data = JSON.parse(event.data);
        if (data.stage === "ocr") {
          setOcrComplete(true);
        } else if (data.stage === "merge") {
          setMergeComplete(true);
        }
      } catch (err) {
        console.error("Failed to parse stage_complete event:", err);
      }
    });

    // Model loading event listeners
    eventSource.addEventListener("model_loading_start", (event: MessageEvent) => {
      try {
        const data = JSON.parse(event.data);
        const setLoading = data.stage === "deepseek" ? setDeepseekLoading : setQwenLoading;
        setLoading({
          isLoading: true,
          progress: 0,
          currentStage: "starting",
          estimatedTime: data.estimated_time_seconds,
          gpuAllocation: null,
        });
      } catch (err) {
        console.error("Failed to parse model_loading_start event:", err);
      }
    });

    eventSource.addEventListener("model_loading_progress", (event: MessageEvent) => {
      try {
        const data = JSON.parse(event.data);
        const setLoading = data.stage === "deepseek" ? setDeepseekLoading : setQwenLoading;
        setLoading((prev) => ({
          ...prev,
          progress: data.progress_pct,
          currentStage: data.current_stage,
        }));
      } catch (err) {
        console.error("Failed to parse model_loading_progress event:", err);
      }
    });

    eventSource.addEventListener("model_loading_complete", (event: MessageEvent) => {
      try {
        const data = JSON.parse(event.data);
        const setLoading = data.stage === "deepseek" ? setDeepseekLoading : setQwenLoading;
        setLoading({
          isLoading: false,
          progress: 100,
          currentStage: "complete",
          estimatedTime: data.actual_time_seconds,
          gpuAllocation: data.gpu_allocation,
        });
      } catch (err) {
        console.error("Failed to parse model_loading_complete event:", err);
      }
    });

    eventSource.addEventListener("model_ready", (event: MessageEvent) => {
      try {
        const data = JSON.parse(event.data);
        if (data.stage === "ocr") {
          setOcrModel(data.model);
        } else if (data.stage === "merge") {
          setMergeModel(data.model);
        }
      } catch (err) {
        console.error("Failed to parse model_ready event:", err);
      }
    });

    eventSource.addEventListener("inference_start", (event: MessageEvent) => {
      try {
        const data = JSON.parse(event.data);
        console.log(`Inference started for ${data.stage} page ${data.page_num}`);
      } catch (err) {
        console.error("Failed to parse inference_start event:", err);
      }
    });

    eventSource.addEventListener("inference_complete", (event: MessageEvent) => {
      try {
        const data = JSON.parse(event.data);
        console.log(`Inference completed for ${data.stage} page ${data.page_num} in ${data.duration_seconds.toFixed(2)}s`);
      } catch (err) {
        console.error("Failed to parse inference_complete event:", err);
      }
    });

    eventSource.addEventListener("job_complete", () => {
      setJobComplete(true);
      // Close connection when job is complete
      eventSource.close();
    });

    eventSource.addEventListener("error", (event: MessageEvent) => {
      try {
        const data = JSON.parse(event.data);
        setError(data.error || "Stream error occurred");
      } catch (err) {
        setError("Connection error");
      }
      eventSource.close();
    });

    eventSource.onerror = () => {
      // Connection error (network failure, server down, etc.)
      setError("Failed to connect to result stream");
      eventSource.close();
    };

    // Cleanup on unmount or job change
    return () => {
      eventSource.close();
    };
  }, [jobId, enabled]);

  // Helper function to get concatenated text from pages
  const getFullOcrText = (): string => {
    const sortedPages = Array.from(ocrPages.entries()).sort((a, b) => a[0] - b[0]);
    return sortedPages.map(([pageNum, text]) => `--- Page ${pageNum} ---\n${text}`).join("\n\n");
  };

  const getFullMergeText = (): string => {
    const sortedPages = Array.from(mergePages.entries()).sort((a, b) => a[0] - b[0]);
    return sortedPages.map(([pageNum, text]) => `--- Page ${pageNum} ---\n${text}`).join("\n\n");
  };

  return {
    ocrPages,
    mergePages,
    ocrComplete,
    mergeComplete,
    jobComplete,
    error,
    deepseekLoading,
    qwenLoading,
    ocrModel,
    mergeModel,
    getFullOcrText,
    getFullMergeText,
  };
}
