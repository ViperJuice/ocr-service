"use client";

import { useEffect, useState, useCallback, useRef } from "react";

/**
 * MergeChunk represents a single chunk of streamed merge text for a page.
 *
 * Phase 3.6: Merge Streaming Enhancement
 * This type matches the backend's merge_chunk SSE event structure.
 */
export interface MergeChunk {
  page_num: number;
  chunk: string;
  is_final: boolean;
  timestamp: string;
}

/**
 * React hook for streaming merge results in real-time via SSE.
 *
 * Phase 3.6: Merge Streaming Enhancement
 * Provides real-time accumulation of merge text chunks as they stream from the backend.
 *
 * Features:
 * - Listens to SSE merge_chunk events from /api/v1/process/jobs/{jobId}/stream-results
 * - Accumulates chunks per page in arrival order
 * - Tracks streaming status per page (active until is_final=true)
 * - Multiple pages can stream independently
 * - Auto-resets state when jobId changes
 * - Cleans up EventSource on unmount
 *
 * @param jobId - Job ID to stream merge results for (null to skip streaming)
 * @returns Object containing mergeChunks Map, isStreamingActive Map, and clearChunks function
 *
 * @example
 * ```tsx
 * const { mergeChunks, isStreamingActive, clearChunks } = useMergeStreaming(jobId);
 *
 * // Get accumulated text for page 1
 * const page1Text = mergeChunks.get(1) || "";
 *
 * // Check if page 1 is still streaming
 * const page1Streaming = isStreamingActive.get(1) || false;
 *
 * // Reset all state
 * clearChunks();
 * ```
 */
export function useMergeStreaming(jobId: string | null) {
  // Map of page_num -> accumulated text
  const [mergeChunks, setMergeChunks] = useState<Map<number, string>>(new Map());

  // Map of page_num -> is currently streaming
  const [isStreamingActive, setIsStreamingActive] = useState<Map<number, boolean>>(new Map());

  // Reference to EventSource for cleanup
  const eventSourceRef = useRef<EventSource | null>(null);

  // Clear all state
  const clearChunks = useCallback(() => {
    setMergeChunks(new Map());
    setIsStreamingActive(new Map());
  }, []);

  // SSE connection for merge_chunk events
  useEffect(() => {
    // Clear state and skip connection if no jobId
    if (!jobId) {
      clearChunks();
      return;
    }

    // Reset state when jobId changes
    clearChunks();

    // Connect to SSE stream
    const url = `${process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000"}/api/v1/process/jobs/${jobId}/stream-results`;
    const eventSource = new EventSource(url);
    eventSourceRef.current = eventSource;

    // Listen for merge_chunk events
    eventSource.addEventListener("merge_chunk", (event: MessageEvent) => {
      try {
        const data = JSON.parse(event.data) as MergeChunk;
        const { page_num, chunk, is_final } = data;

        // Accumulate chunk
        setMergeChunks((prev) => {
          const newMap = new Map(prev);
          const current = newMap.get(page_num) || "";
          newMap.set(page_num, current + chunk);
          return newMap;
        });

        // Update streaming status
        setIsStreamingActive((prev) => {
          const newMap = new Map(prev);
          newMap.set(page_num, !is_final);
          return newMap;
        });

      } catch (error) {
        console.error("Error processing merge_chunk event:", error);
      }
    });

    // Handle connection errors
    eventSource.onerror = (error) => {
      console.error("EventSource connection error:", error);
      // EventSource will automatically attempt to reconnect
      // Only close if we want to stop trying
    };

    // Cleanup on unmount or jobId change
    return () => {
      if (eventSourceRef.current) {
        eventSourceRef.current.close();
        eventSourceRef.current = null;
      }
    };
  }, [jobId, clearChunks]);

  return {
    mergeChunks,
    isStreamingActive,
    clearChunks,
  };
}
