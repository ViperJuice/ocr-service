"use client";

import { InlineProgressData } from "@/lib/types";
import { Loader2, FileText, FolderOpen } from "lucide-react";

interface InlineProgressProps extends InlineProgressData {}

export function InlineProgress({
  type,
  progress_pct,
  content,
  currentPage,
  totalPages,
  documentsCompleted,
  totalDocuments,
  currentDocument,
  stage,
}: InlineProgressProps) {
  const getStageColor = (stageName?: string): string => {
    switch (stageName) {
      case "ocr":
        return "text-blue-400";
      case "merge":
        return "text-purple-400";
      case "format":
        return "text-green-400";
      default:
        return "text-primary";
    }
  };

  const getStageIcon = () => {
    if (type === "batch") {
      return <FolderOpen className="w-4 h-4" />;
    }
    if (type === "multi-page") {
      return <FileText className="w-4 h-4" />;
    }
    return <Loader2 className="w-4 h-4 animate-spin" />;
  };

  return (
    <div className="inline-progress-container">
      <div className="flex items-center gap-2 mb-2">
        <div className={getStageColor(stage)}>{getStageIcon()}</div>
        <span className="text-sm text-text-secondary">{content}</span>
      </div>

      {/* Progress bar */}
      <div className="inline-progress-bar">
        <div
          className="inline-progress-fill"
          style={{ width: `${Math.min(100, Math.max(0, progress_pct))}%` }}
        />
      </div>

      {/* Progress details */}
      <div className="mt-2 flex items-center gap-4 text-xs text-text-muted">
        {/* Single page - simple spinner */}
        {type === "single" && (
          <span>{Math.round(progress_pct)}%</span>
        )}

        {/* Multi-page - show page numbers */}
        {type === "multi-page" && currentPage !== undefined && totalPages !== undefined && (
          <>
            <span>
              Page {currentPage} of {totalPages}
            </span>
            <span>{Math.round(progress_pct)}%</span>
            {stage && (
              <span className={getStageColor(stage)}>
                {stage.toUpperCase()}
              </span>
            )}
          </>
        )}

        {/* Batch - hierarchical display */}
        {type === "batch" && documentsCompleted !== undefined && totalDocuments !== undefined && (
          <>
            <span>
              Documents: {documentsCompleted} / {totalDocuments}
            </span>
            {currentDocument && (
              <span className="truncate max-w-[200px]" title={currentDocument}>
                Current: {currentDocument}
              </span>
            )}
            {currentPage !== undefined && totalPages !== undefined && (
              <span>
                Page {currentPage}/{totalPages}
              </span>
            )}
            <span>{Math.round(progress_pct)}%</span>
          </>
        )}
      </div>
    </div>
  );
}
