"use client";

import { useEffect, useState } from "react";
import { Loader2, CheckCircle, XCircle, AlertTriangle } from "lucide-react";
import { JobStatus } from "@/lib/types";
import { useRealtimeJob } from "@/hooks/useRealtimeJob";

interface ProgressMonitorProps {
  jobId: string;
  filename?: string;
  onComplete?: () => void;
  onError?: (error: string) => void;
}

export function ProgressMonitor({ jobId, filename, onComplete, onError }: ProgressMonitorProps) {
  // PHASE 4: Use Realtime job subscription instead of SSE
  const { job, isConnected, error: realtimeError } = useRealtimeJob(jobId);

  const [error, setError] = useState<string | null>(null);

  // Handle job status changes
  useEffect(() => {
    if (!job) return;

    if (job.status === "completed") {
      onComplete?.();
    } else if (job.status === "failed") {
      const errorMsg = job.error_message || "Job failed";
      setError(errorMsg);
      onError?.(errorMsg);
    }
  }, [job?.status, job?.error_message, onComplete, onError]);

  // Handle Realtime connection errors
  useEffect(() => {
    if (realtimeError) {
      setError(realtimeError.message);
    }
  }, [realtimeError]);

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

  if (job?.status === "completed") {
    const pageInfo = job.total_pages && job.total_pages > 1
      ? `${job.total_pages} pages processed`
      : "1 page processed";
    const displayFilename = filename || job.filename || "Document";

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

  if (job?.status === "cancelled") {
    return (
      <div className="flex items-center gap-3 px-4 py-3 bg-warning/10 border border-warning/20 rounded-lg">
        <AlertTriangle className="w-5 h-5 text-warning flex-shrink-0" />
        <div className="flex-1">
          <p className="text-sm font-medium text-warning">Job cancelled</p>
        </div>
      </div>
    );
  }

  const progress = job?.progress_pct || 0;
  const stage = job?.current_stage || "queuing";
  const currentPage = job?.pages_completed || 0;
  const totalPages = job?.total_pages || 0;

  // Stage descriptions
  const getStageLabel = () => {
    if (job?.status === "queued") return "Waiting to start...";
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

      {/* PHASE 4: Merge streaming preview removed - SSE deprecated */}

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
