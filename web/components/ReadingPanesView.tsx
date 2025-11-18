"use client";

import { useState, useEffect, useRef } from "react";
import { Document, Page, pdfjs } from "react-pdf";
import "react-pdf/dist/Page/AnnotationLayer.css";
import "react-pdf/dist/Page/TextLayer.css";
import { useRealtimeJob } from "@/hooks/useRealtimeJob";
import { useRealtimeStreamingTokens } from "@/hooks/useRealtimeStreamingTokens";
import { apiClient } from "@/lib/api-client";
import type { JobResult } from "@/lib/types";

// Configure PDF.js worker - use local copy to avoid CDN issues
pdfjs.GlobalWorkerOptions.workerSrc = '/pdf.worker.min.mjs';

interface ReadingPanesViewProps {
  jobId: string | null;
  enableStreaming?: boolean; // Deprecated, kept for compatibility
}

export default function ReadingPanesView({
  jobId,
  enableStreaming = true, // Ignored - Phase 4 always uses Realtime + result fetch
}: ReadingPanesViewProps) {
  // PHASE 4: Use Realtime job subscription
  const { job, isConnected, error: realtimeError } = useRealtimeJob(jobId);

  // PHASE 4: Use Realtime streaming tokens subscription
  const { pageTexts: streamingPageTexts, tokenCount, isConnected: streamingConnected } = useRealtimeStreamingTokens(jobId);

  // Result state
  const [result, setResult] = useState<JobResult | null>(null);
  const [resultError, setResultError] = useState<string | null>(null);
  const [isLoadingResult, setIsLoadingResult] = useState(false);

  const [numPages, setNumPages] = useState<number | null>(null);
  const [pdfUrl, setPdfUrl] = useState<string | null>(null);
  const [pdfError, setPdfError] = useState<string | null>(null);

  const ocrTextRef = useRef<HTMLTextAreaElement>(null);
  const mergeTextRef = useRef<HTMLTextAreaElement>(null);

  // PHASE 4: Fetch results when job completes
  useEffect(() => {
    if (!job || !jobId) return;

    if (job.status === "completed" && !result && !isLoadingResult) {
      setIsLoadingResult(true);
      setResultError(null);

      apiClient.getJobResult(jobId)
        .then((fetchedResult) => {
          console.log("[ReadingPanesView] Fetched result:", fetchedResult);
          setResult(fetchedResult);
        })
        .catch((error) => {
          console.error("[ReadingPanesView] Failed to fetch result:", error);
          setResultError(error.message || "Failed to load results");
        })
        .finally(() => {
          setIsLoadingResult(false);
        });
    }

    // Reset result when job changes or is cancelled/failed
    if (job.status === "cancelled" || job.status === "failed") {
      setResult(null);
      setResultError(job.status === "failed" ? job.error_message || "Job failed" : null);
    }
  }, [job, jobId, result, isLoadingResult]);

  // Load original file URL when job ID changes
  useEffect(() => {
    if (jobId) {
      const url = apiClient.getOriginalFileUrl(jobId);
      setPdfUrl(url);
    } else {
      setPdfUrl(null);
      setNumPages(null);
    }
  }, [jobId]);

  function onDocumentLoadSuccess({ numPages }: { numPages: number }) {
    setNumPages(numPages);
    setPdfError(null);
  }

  function onDocumentLoadError(error: Error) {
    console.error("PDF load error:", error);
    setPdfError("Unable to load original document");
  }

  if (!jobId) {
    return (
      <div className="flex items-center justify-center h-full text-gray-500">
        No job selected
      </div>
    );
  }

  return (
    <div className="h-full flex flex-col gap-2 p-2 bg-gray-900">
      {/* DeepSeek-OCR Output Pane */}
      <div className="flex-1 flex flex-col border border-gray-700 rounded bg-gray-800 min-h-0">
        <div className="px-3 py-2 border-b border-gray-700 bg-gray-900 font-medium text-sm flex items-center justify-between text-gray-200">
          <div className="flex items-center gap-2">
            <span>
              DeepSeek-OCR Output (Stage 1)
              {result?.result.model_used && (
                <span className="text-xs text-gray-400 font-normal ml-2">({result.result.model_used})</span>
              )}
            </span>
            {job?.status === "processing" && job?.current_stage === "ocr" && (
              <div className="flex items-center gap-2 text-xs text-blue-400">
                <svg className="animate-spin h-4 w-4" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
                  <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
                  <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                </svg>
                <span>Processing OCR...</span>
              </div>
            )}
            {isLoadingResult && (
              <div className="flex items-center gap-2 text-xs text-blue-400">
                <svg className="animate-spin h-4 w-4" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
                  <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
                  <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                </svg>
                <span>Loading results...</span>
              </div>
            )}
          </div>
          <div className="flex items-center gap-3">
            <span className="text-xs text-gray-400">
              {result ? "Complete" : job?.status === "completed" ? "Loading..." : "Waiting"}
            </span>
          </div>
        </div>
        <textarea
          ref={ocrTextRef}
          className="flex-1 p-3 font-mono text-sm resize-none focus:outline-none bg-gray-800 text-gray-100 border-0"
          value={result?.result.deepseek_ocr_content || ""}
          readOnly
          placeholder="OCR output will appear here after processing completes..."
        />
      </div>

      {/* Merged Output Pane */}
      <div className="flex-1 flex flex-col border border-gray-700 rounded bg-gray-800 min-h-0">
        <div className="px-3 py-2 border-b border-gray-700 bg-gray-900 font-medium text-sm flex items-center justify-between text-gray-200">
          <div className="flex items-center gap-2">
            <span>
              Merged Output (Stage 2)
              {result?.result.model_used && (
                <span className="text-xs text-gray-400 font-normal ml-2">({result.result.model_used})</span>
              )}
            </span>
            {job?.status === "processing" && job?.current_stage === "merge" && (
              <div className="flex items-center gap-2 text-xs text-blue-400">
                <svg className="animate-spin h-4 w-4" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
                  <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
                  <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                </svg>
                <span>Streaming... ({tokenCount} tokens)</span>
              </div>
            )}
          </div>
          <div className="flex items-center gap-3">
            <span className="text-xs text-gray-400">
              {result ? "Complete" : job?.status === "completed" ? "Loading..." : job?.status === "processing" && job?.current_stage === "merge" ? "Streaming" : "Waiting"}
            </span>
          </div>
        </div>
        <textarea
          ref={mergeTextRef}
          className="flex-1 p-3 font-mono text-sm resize-none focus:outline-none bg-gray-800 text-gray-100 border-0"
          value={
            // Show streaming tokens during merge stage, otherwise show final result
            job?.status === "processing" && job?.current_stage === "merge"
              ? Array.from(streamingPageTexts.values()).join("\n\n")
              : result?.result.content || ""
          }
          readOnly
          placeholder="Merged output will appear here during processing..."
        />
      </div>

      {/* Original Document Pane */}
      <div className="flex-1 flex flex-col border border-gray-700 rounded bg-gray-800 overflow-hidden min-h-0">
        <div className="px-3 py-2 border-b border-gray-700 bg-gray-900 font-medium text-sm flex items-center justify-between text-gray-200">
          <span>Original Document</span>
          {numPages && (
            <span className="text-xs text-gray-400">{numPages} pages</span>
          )}
        </div>
        <div className="flex-1 overflow-auto bg-gray-700 p-4">
          {pdfError ? (
            <div className="flex items-center justify-center h-full text-gray-400">
              <div className="text-center">
                <p>{pdfError}</p>
                <p className="text-xs mt-2 text-gray-500">
                  Backend may need restart to enable PDF viewing
                </p>
              </div>
            </div>
          ) : pdfUrl ? (
            <Document
              file={pdfUrl}
              onLoadSuccess={onDocumentLoadSuccess}
              onLoadError={onDocumentLoadError}
              className="flex flex-col items-center gap-4"
            >
              {numPages &&
                Array.from(new Array(numPages), (_, index) => (
                  <Page
                    key={`page_${index + 1}`}
                    pageNumber={index + 1}
                    className="shadow-lg"
                    renderTextLayer={true}
                    renderAnnotationLayer={true}
                  />
                ))}
            </Document>
          ) : (
            <div className="flex items-center justify-center h-full text-gray-400">
              Loading document...
            </div>
          )}
        </div>
      </div>

      {/* Error Display */}
      {(realtimeError || resultError) && (
        <div className="px-4 py-2 bg-red-900/50 border border-red-700 rounded text-red-300 text-sm">
          {realtimeError && <div>Realtime error: {realtimeError.message}</div>}
          {resultError && <div>Result error: {resultError}</div>}
        </div>
      )}
    </div>
  );
}
