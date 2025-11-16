"use client";

import { useState, useEffect, useRef } from "react";
import { Document, Page, pdfjs } from "react-pdf";
import "react-pdf/dist/Page/AnnotationLayer.css";
import "react-pdf/dist/Page/TextLayer.css";
import { useStreamingResults } from "@/hooks/useStreamingResults";
import { apiClient } from "@/lib/api-client";

// Configure PDF.js worker - use local copy to avoid CDN issues
pdfjs.GlobalWorkerOptions.workerSrc = '/pdf.worker.min.mjs';

interface ReadingPanesViewProps {
  jobId: string | null;
  enableStreaming?: boolean;
}

export default function ReadingPanesView({
  jobId,
  enableStreaming = true,
}: ReadingPanesViewProps) {
  const {
    ocrPages,
    mergePages,
    ocrComplete,
    mergeComplete,
    jobComplete,
    error: streamError,
    deepseekLoading,
    qwenLoading,
    ocrModel,
    mergeModel,
    getFullOcrText,
    getFullMergeText,
  } = useStreamingResults(jobId, enableStreaming);

  const [numPages, setNumPages] = useState<number | null>(null);
  const [pdfUrl, setPdfUrl] = useState<string | null>(null);
  const [pdfError, setPdfError] = useState<string | null>(null);

  const ocrTextRef = useRef<HTMLTextAreaElement>(null);
  const mergeTextRef = useRef<HTMLTextAreaElement>(null);

  // Auto-scroll text areas to bottom as new content arrives
  useEffect(() => {
    if (ocrTextRef.current) {
      ocrTextRef.current.scrollTop = ocrTextRef.current.scrollHeight;
    }
  }, [ocrPages]);

  useEffect(() => {
    if (mergeTextRef.current) {
      mergeTextRef.current.scrollTop = mergeTextRef.current.scrollHeight;
    }
  }, [mergePages]);

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
              {ocrModel && <span className="text-xs text-gray-400 font-normal ml-2">({ocrModel})</span>}
            </span>
            {deepseekLoading.isLoading && (
              <div className="flex items-center gap-2 text-xs text-blue-400">
                <svg className="animate-spin h-4 w-4" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
                  <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
                  <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                </svg>
                <span>Loading model... {deepseekLoading.progress}%</span>
              </div>
            )}
          </div>
          <div className="flex items-center gap-3">
            {deepseekLoading.isLoading && deepseekLoading.gpuAllocation && (
              <span className="text-xs text-purple-400">
                {deepseekLoading.gpuAllocation.single_gpu
                  ? `GPU ${deepseekLoading.gpuAllocation.primary_device?.replace('cuda:', '') || '0'}`
                  : `GPUs ${deepseekLoading.gpuAllocation.devices?.map((d: string) => d.replace('cuda:', '')).join(', ') || '0,1'}`
                }
              </span>
            )}
            <span className="text-xs text-gray-400">
              {ocrComplete ? "Complete" : `${ocrPages.size} pages`}
            </span>
          </div>
        </div>
        <textarea
          ref={ocrTextRef}
          className="flex-1 p-3 font-mono text-sm resize-none focus:outline-none bg-gray-800 text-gray-100 border-0"
          value={getFullOcrText()}
          readOnly
          placeholder="OCR output will appear here as pages complete..."
        />
      </div>

      {/* Merged Output Pane */}
      <div className="flex-1 flex flex-col border border-gray-700 rounded bg-gray-800 min-h-0">
        <div className="px-3 py-2 border-b border-gray-700 bg-gray-900 font-medium text-sm flex items-center justify-between text-gray-200">
          <div className="flex items-center gap-2">
            <span>
              Merged Output (Stage 2 - Qwen3-VL)
              {mergeModel && <span className="text-xs text-gray-400 font-normal ml-2">({mergeModel})</span>}
            </span>
            {qwenLoading.isLoading && (
              <div className="flex items-center gap-2 text-xs text-blue-400">
                <svg className="animate-spin h-4 w-4" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
                  <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
                  <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                </svg>
                <span>Loading model... {qwenLoading.progress}%</span>
              </div>
            )}
          </div>
          <div className="flex items-center gap-3">
            {qwenLoading.isLoading && qwenLoading.gpuAllocation && (
              <span className="text-xs text-purple-400">
                {qwenLoading.gpuAllocation.single_gpu
                  ? `GPU ${qwenLoading.gpuAllocation.primary_device?.replace('cuda:', '') || '0'}`
                  : `GPUs ${qwenLoading.gpuAllocation.devices?.map((d: string) => d.replace('cuda:', '')).join(', ') || '0,1'}`
                }
              </span>
            )}
            <span className="text-xs text-gray-400">
              {mergeComplete ? "Complete" : `${mergePages.size} pages`}
            </span>
          </div>
        </div>
        <textarea
          ref={mergeTextRef}
          className="flex-1 p-3 font-mono text-sm resize-none focus:outline-none bg-gray-800 text-gray-100 border-0"
          value={getFullMergeText()}
          readOnly
          placeholder="Merged output will appear here as pages complete..."
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
      {streamError && (
        <div className="px-4 py-2 bg-red-900/50 border border-red-700 rounded text-red-300 text-sm">
          Stream error: {streamError}
        </div>
      )}
    </div>
  );
}
