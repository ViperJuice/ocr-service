"use client";

import { DocumentProgress } from "@/lib/types";
import { FolderOpen, ChevronDown, ChevronUp } from "lucide-react";
import { useState } from "react";
import { DocumentProgressItem } from "./DocumentProgressItem";

interface BatchProgressCardProps {
  batchJobId: string;
  totalDocuments: number;
  documentsCompleted: number;
  currentDocument: DocumentProgress | null;
  overallProgressPct: number;
  documentList?: DocumentProgress[];
}

export function BatchProgressCard({
  batchJobId,
  totalDocuments,
  documentsCompleted,
  currentDocument,
  overallProgressPct,
  documentList = [],
}: BatchProgressCardProps) {
  const [isExpanded, setIsExpanded] = useState(false);

  return (
    <div className="batch-progress-card">
      {/* Header */}
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2">
          <FolderOpen className="w-5 h-5 text-purple-400" />
          <h3 className="text-sm font-semibold text-text-primary">
            Batch Processing
          </h3>
        </div>
        <span className="text-xs text-text-muted font-mono">
          {batchJobId.substring(0, 8)}
        </span>
      </div>

      {/* Overall Progress */}
      <div className="mb-3">
        <div className="flex items-center justify-between text-xs text-text-secondary mb-1">
          <span>
            Overall Progress: {documentsCompleted} / {totalDocuments} documents
          </span>
          <span>{Math.round(overallProgressPct)}%</span>
        </div>
        <div className="h-2 bg-surface-dark rounded-full overflow-hidden">
          <div
            className="h-full bg-gradient-to-r from-purple-500 to-purple-400 transition-all duration-300"
            style={{ width: `${Math.min(100, Math.max(0, overallProgressPct))}%` }}
          />
        </div>
      </div>

      {/* Current Document */}
      {currentDocument && (
        <div className="mb-3">
          <h4 className="text-xs font-medium text-text-secondary mb-2">
            Currently Processing:
          </h4>
          <DocumentProgressItem {...currentDocument} isCurrent />
        </div>
      )}

      {/* Document List (Expandable) */}
      {documentList.length > 0 && (
        <div className="mt-3 pt-3 border-t border-border/30">
          <button
            onClick={() => setIsExpanded(!isExpanded)}
            className="flex items-center justify-between w-full text-xs text-text-secondary hover:text-text-primary transition-colors"
          >
            <span>Document List ({documentList.length})</span>
            {isExpanded ? (
              <ChevronUp className="w-4 h-4" />
            ) : (
              <ChevronDown className="w-4 h-4" />
            )}
          </button>

          {isExpanded && (
            <div className="mt-2 space-y-1 max-h-64 overflow-y-auto">
              {documentList.map((doc) => (
                <DocumentProgressItem
                  key={doc.job_id}
                  {...doc}
                  isCompact
                />
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
