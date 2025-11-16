"use client";

import { useEffect, useState } from "react";
import { Loader2, CheckCircle, XCircle, AlertTriangle } from "lucide-react";
import { MonitoringMetrics, JobStatus } from "@/lib/types";
import { formatDuration } from "@/lib/utils";
import { apiClient } from "@/lib/api-client";
import { useMergeStreaming } from "@/hooks/useMergeStreaming";

interface ProgressMonitorProps {
  jobId: string;
  filename?: string;
  onComplete?: () => void;
  onError?: (error: string) => void;
}

export function ProgressMonitor({ jobId, filename, onComplete, onError }: ProgressMonitorProps) {
  const [metrics, setMetrics] = useState<MonitoringMetrics | null>(null);
  const [status, setStatus] = useState<JobStatus>("queued");
  const [error, setError] = useState<string | null>(null);
  const [totalPagesProcessed, setTotalPagesProcessed] = useState<number>(0);

  // Phase 3.6: Integrate merge streaming hook
  const { mergeChunks, isStreamingActive, clearChunks } = useMergeStreaming(jobId);

  useEffect(() => {
    // Create SSE connection for real-time monitoring
    const eventSource = apiClient.createMonitoringStream(jobId);

    eventSource.onmessage = (event) => {
      try {
        const data: MonitoringMetrics = JSON.parse(event.data);
        setMetrics(data);

        // Track total pages processed
        if (data.stage_total_pages > 0) {
          setTotalPagesProcessed(data.stage_total_pages);
        }

        // Check if completed
        if (data.overall_progress_pct >= 100) {
          eventSource.close();
          setStatus("completed");
          onComplete?.();
        }
      } catch (err) {
        console.error("Failed to parse SSE message:", err);
      }
    };

    eventSource.onerror = (err) => {
      console.error("SSE connection error:", err);
      eventSource.close();

      // Fallback to polling
      checkJobStatus();
    };

    // Poll job status as fallback
    const pollInterval = setInterval(checkJobStatus, 3000);

    async function checkJobStatus() {
      try {
        const jobStatus = await apiClient.getJobStatus(jobId);
        setStatus(jobStatus.status);

        if (jobStatus.status === "completed") {
          clearInterval(pollInterval);
          eventSource.close();
          onComplete?.();
        } else if (jobStatus.status === "failed") {
          clearInterval(pollInterval);
          eventSource.close();
          const errorMsg = jobStatus.error || "Job failed";
          setError(errorMsg);
          onError?.(errorMsg);
        } else if (jobStatus.status === "cancelled") {
          clearInterval(pollInterval);
          eventSource.close();
        }
      } catch (err) {
        // Silently continue polling
      }
    }

    return () => {
      eventSource.close();
      clearInterval(pollInterval);
    };
  }, [jobId, onComplete, onError]);

  if (error) {
    return (
      <div className="flex items-center gap-3 px-4 py-3 bg-error/10 border border-error/20 rounded-lg">
        <XCircle className="w-5 h-5 text-error flex-shrink-0" />
        <div className="flex-1">
          <p className="text-sm font-medium text-error">Processing failed</p>
          <p className="text-xs text-error/80 mt-0.5">{error}</p>
        </div>
      </div>
    );
  }

  if (status === "completed") {
    const pageInfo = totalPagesProcessed > 1
      ? `${totalPagesProcessed} pages processed`
      : "1 page processed";
    const displayFilename = filename || "Document";

    return (
      <div className="flex items-center gap-3 px-4 py-3 bg-success/10 border border-success/20 rounded-lg">
        <CheckCircle className="w-5 h-5 text-success flex-shrink-0" />
        <div className="flex-1">
          <p className="text-sm font-medium text-success">Parsing complete: {displayFilename}</p>
          <p className="text-xs text-text-muted mt-0.5">{pageInfo}</p>
        </div>
      </div>
    );
  }

  if (status === "cancelled") {
    return (
      <div className="flex items-center gap-3 px-4 py-3 bg-warning/10 border border-warning/20 rounded-lg">
        <AlertTriangle className="w-5 h-5 text-warning flex-shrink-0" />
        <div className="flex-1">
          <p className="text-sm font-medium text-warning">Job cancelled</p>
        </div>
      </div>
    );
  }

  const progress = metrics?.overall_progress_pct || 0;
  const stage = metrics?.active_stage || "queuing";
  const currentPage = metrics?.stage_page || 0;
  const totalPages = metrics?.stage_total_pages || 0;

  // Stage descriptions
  const getStageLabel = () => {
    if (status === "queued") return "Waiting to start...";
    switch (stage) {
      case "ocr": return "Parsing document";
      case "merge": return "Merging pages";
      case "format": return "Formatting output";
      default: return "Processing";
    }
  };

  // Single page case: show simple spinner message
  const isSinglePage = totalPages === 1 || (totalPages === 0 && progress > 0 && progress < 100);

  return (
    <div className="space-y-3 px-4 py-3 bg-surface border border-border rounded-lg">
      {/* Status header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Loader2 className="w-4 h-4 text-primary animate-spin" />
          <span className="text-sm font-medium text-text-primary">
            {getStageLabel()}
          </span>
        </div>
        {!isSinglePage && progress > 0 && (
          <span className="text-sm font-mono text-text-muted">{progress.toFixed(0)}%</span>
        )}
      </div>

      {/* Progress bar - only show for multi-page or when progress is available */}
      {!isSinglePage && progress > 0 && (
        <div className="progress-bar">
          <div
            className="progress-fill"
            style={{ width: `${progress}%` }}
          />
        </div>
      )}

      {/* Phase 3.6: Streaming merge text preview with typewriter effect */}
      {stage === "merge" && currentPage > 0 && mergeChunks.has(currentPage) && (
        <div className="mt-3 p-3 bg-primary/5 border border-primary/20 rounded-md" role="status" aria-live="polite" aria-label="Merge streaming preview">
          <div className="text-xs text-text-muted mb-1.5 font-medium">
            Live merge preview (Page {currentPage}):
          </div>
          <div className="text-sm text-text-secondary font-mono leading-relaxed max-h-24 overflow-y-auto">
            <span className="streaming-text">
              {mergeChunks.get(currentPage)}
            </span>
            {isStreamingActive.get(currentPage) && (
              <span className="streaming-cursor" aria-hidden="true">|</span>
            )}
          </div>
        </div>
      )}

      {/* Details */}
      {totalPages > 1 && (
        <div className="flex items-center justify-between text-xs text-text-muted">
          <span>
            Page {currentPage} of {totalPages} ({((currentPage / totalPages) * 100).toFixed(0)}% complete)
          </span>
          <span className="capitalize">{stage}</span>
        </div>
      )}

      {isSinglePage && progress > 0 && progress < 100 && (
        <div className="text-xs text-text-muted">
          Processing single page...
        </div>
      )}
    </div>
  );
}
