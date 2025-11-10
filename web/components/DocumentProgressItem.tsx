"use client";

import { DocumentProgress } from "@/lib/types";
import { FileText, CheckCircle, XCircle, Clock, Loader2 } from "lucide-react";

interface DocumentProgressItemProps extends DocumentProgress {
  isCurrent?: boolean;
  isCompact?: boolean;
}

export function DocumentProgressItem({
  filename,
  progress_pct,
  current_page,
  total_pages,
  status,
  stage,
  isCurrent = false,
  isCompact = false,
}: DocumentProgressItemProps) {
  const getStatusIcon = () => {
    switch (status) {
      case "completed":
        return <CheckCircle className="w-4 h-4 text-success" />;
      case "failed":
        return <XCircle className="w-4 h-4 text-error" />;
      case "processing":
        return <Loader2 className="w-4 h-4 text-primary animate-spin" />;
      case "queued":
        return <Clock className="w-4 h-4 text-text-muted" />;
      default:
        return <FileText className="w-4 h-4 text-text-muted" />;
    }
  };

  const getStatusColor = () => {
    switch (status) {
      case "completed":
        return "border-success/30 bg-success/5";
      case "failed":
        return "border-error/30 bg-error/5";
      case "processing":
        return "border-primary/30 bg-primary/5";
      default:
        return "border-border/30 bg-transparent";
    }
  };

  return (
    <div
      className={`document-progress-item ${getStatusColor()} ${
        isCurrent ? "ring-1 ring-primary" : ""
      } ${isCompact ? "py-2" : "p-3"}`}
    >
      <div className="flex items-center gap-2">
        {getStatusIcon()}
        <div className="flex-1 min-w-0">
          <div className="flex items-center justify-between gap-2">
            <span
              className={`${
                isCompact ? "text-xs" : "text-sm"
              } font-medium text-text-primary truncate`}
              title={filename}
            >
              {filename}
            </span>
            {!isCompact && (
              <span className="text-xs text-text-muted whitespace-nowrap">
                {status.toUpperCase()}
              </span>
            )}
          </div>

          {/* Progress bar for processing documents */}
          {status === "processing" && (
            <div className="mt-1.5">
              <div className="flex items-center justify-between text-xs text-text-muted mb-1">
                {current_page !== undefined && total_pages !== undefined ? (
                  <span>
                    Page {current_page} / {total_pages}
                  </span>
                ) : (
                  <span>Processing...</span>
                )}
                <span>{Math.round(progress_pct)}%</span>
              </div>
              <div className="h-1 bg-surface-dark rounded-full overflow-hidden">
                <div
                  className="h-full bg-primary transition-all duration-300"
                  style={{ width: `${Math.min(100, Math.max(0, progress_pct))}%` }}
                />
              </div>
              {stage && (
                <div className="mt-1 text-xs text-text-muted">
                  Stage: {stage.toUpperCase()}
                </div>
              )}
            </div>
          )}

          {/* Completion indicator */}
          {status === "completed" && !isCompact && (
            <div className="mt-1 text-xs text-success">
              Completed successfully
            </div>
          )}

          {/* Failed indicator */}
          {status === "failed" && !isCompact && (
            <div className="mt-1 text-xs text-error">
              Processing failed
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
