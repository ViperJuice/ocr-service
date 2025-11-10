"use client";

import { useEffect, useRef, useState, useCallback } from "react";
import { ChatMessage as ChatMessageType, InlineProgressData } from "@/lib/types";
import { ChatMessage } from "./ChatMessage";
import { apiClient } from "@/lib/api-client";

interface MessageListProps {
  messages: ChatMessageType[];
  onMessageUpdate?: (messageId: string, progressData: InlineProgressData | null) => void;
}

export function MessageList({ messages, onMessageUpdate }: MessageListProps) {
  const bottomRef = useRef<HTMLDivElement>(null);
  const [progressMap, setProgressMap] = useState<Map<string, InlineProgressData>>(new Map());

  // Merge progress data with messages
  const messagesWithProgress = messages.map((msg) => ({
    ...msg,
    inlineProgress: progressMap.get(msg.id) || msg.inlineProgress,
  }));

  useEffect(() => {
    // Auto-scroll to bottom when new messages arrive
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  // SSE subscription for progress updates
  useEffect(() => {
    const eventSource = apiClient.createBatchProgressStream();

    // Job progress (single/multi-page documents)
    eventSource.addEventListener("job_progress", (e) => {
      const data = JSON.parse(e.data);

      // Find message associated with this job
      const message = messages.find((m) => m.metadata?.jobId === data.job_id);
      if (!message) return;

      // Determine progress type
      const progressType =
        data.total_pages && data.total_pages > 1 ? "multi-page" : "single";

      // Update progress map
      setProgressMap((prev) => {
        const newMap = new Map(prev);
        newMap.set(message.id, {
          type: progressType,
          progress_pct: data.progress_pct || 0,
          content: `${data.stage || "Processing"}: ${data.pages_completed || 0}/${
            data.total_pages || "?"
          } pages`,
          currentPage: data.current_page,
          totalPages: data.total_pages,
          stage: data.stage,
        });
        return newMap;
      });

      // Notify parent if callback provided
      if (onMessageUpdate) {
        onMessageUpdate(message.id, {
          type: progressType,
          progress_pct: data.progress_pct || 0,
          content: `${data.stage || "Processing"}: ${data.pages_completed || 0}/${
            data.total_pages || "?"
          } pages`,
          currentPage: data.current_page,
          totalPages: data.total_pages,
          stage: data.stage,
        });
      }
    });

    // Batch progress
    eventSource.addEventListener("batch_progress", (e) => {
      const data = JSON.parse(e.data);

      // Find message associated with this batch
      const message = messages.find(
        (m) => m.metadata?.batchJobId === data.batch_job_id
      );
      if (!message) return;

      // Update progress map
      setProgressMap((prev) => {
        const newMap = new Map(prev);
        newMap.set(message.id, {
          type: "batch",
          progress_pct: data.overall_progress_pct || 0,
          content: `Processing batch: ${data.documents_completed || 0}/${
            data.total_documents || 0
          } documents`,
          documentsCompleted: data.documents_completed,
          totalDocuments: data.total_documents,
          currentDocument: data.current_document?.filename,
          currentPage: data.current_document?.current_page,
          totalPages: data.current_document?.total_pages,
          stage: data.current_document?.stage,
        });
        return newMap;
      });

      // Notify parent if callback provided
      if (onMessageUpdate) {
        onMessageUpdate(message.id, {
          type: "batch",
          progress_pct: data.overall_progress_pct || 0,
          content: `Processing batch: ${data.documents_completed || 0}/${
            data.total_documents || 0
          } documents`,
          documentsCompleted: data.documents_completed,
          totalDocuments: data.total_documents,
          currentDocument: data.current_document?.filename,
          currentPage: data.current_document?.current_page,
          totalPages: data.current_document?.total_pages,
          stage: data.current_document?.stage,
        });
      }
    });

    // Document progress (within batch)
    eventSource.addEventListener("document_progress", (e) => {
      const data = JSON.parse(e.data);

      // Find message associated with this batch
      const message = messages.find(
        (m) => m.metadata?.batchJobId === data.batch_job_id
      );
      if (!message) return;

      // Update batch progress to reflect current document
      setProgressMap((prev) => {
        const existing = prev.get(message.id);
        if (!existing || existing.type !== "batch") return prev;

        const newMap = new Map(prev);
        newMap.set(message.id, {
          ...existing,
          currentDocument: data.filename,
          currentPage: data.current_page,
          totalPages: data.total_pages,
          stage: data.stage,
        });
        return newMap;
      });
    });

    // Job/batch completion
    eventSource.addEventListener("job_complete", (e) => {
      const data = JSON.parse(e.data);
      const message = messages.find((m) => m.metadata?.jobId === data.job_id);
      if (message) {
        // Remove progress data on completion
        setProgressMap((prev) => {
          const newMap = new Map(prev);
          newMap.delete(message.id);
          return newMap;
        });
        if (onMessageUpdate) {
          onMessageUpdate(message.id, null);
        }
      }
    });

    eventSource.addEventListener("batch_complete", (e) => {
      const data = JSON.parse(e.data);
      const message = messages.find(
        (m) => m.metadata?.batchJobId === data.batch_job_id
      );
      if (message) {
        // Remove progress data on completion
        setProgressMap((prev) => {
          const newMap = new Map(prev);
          newMap.delete(message.id);
          return newMap;
        });
        if (onMessageUpdate) {
          onMessageUpdate(message.id, null);
        }
      }
    });

    // Error handling
    eventSource.addEventListener("error", (e) => {
      console.error("SSE error:", e);
    });

    return () => {
      eventSource.close();
    };
  }, [messages, onMessageUpdate]);

  if (messages.length === 0) {
    return (
      <div className="flex-1 flex items-center justify-center text-center px-4">
        <div className="max-w-md">
          <div className="w-16 h-16 mx-auto mb-4 bg-surface rounded-full flex items-center justify-center">
            <svg
              className="w-8 h-8 text-text-muted"
              fill="none"
              viewBox="0 0 24 24"
              stroke="currentColor"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M8 10h.01M12 10h.01M16 10h.01M9 16H5a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v8a2 2 0 01-2 2h-5l-5 5v-5z"
              />
            </svg>
          </div>
          <h3 className="text-lg font-semibold text-text-primary mb-2">
            Start a conversation
          </h3>
          <p className="text-sm text-text-muted">
            Upload a file or directory and tell me what you'd like to do with it. For example:
          </p>
          <ul className="mt-3 text-sm text-text-secondary space-y-1">
            <li>"Parse the whole document"</li>
            <li>"Parse page 5"</li>
            <li>"Parse the whole directory"</li>
            <li>"Show as JSON"</li>
          </ul>
        </div>
      </div>
    );
  }

  return (
    <div className="flex-1 overflow-y-auto px-4 py-6 space-y-4">
      {messagesWithProgress.map((message) => (
        <ChatMessage key={message.id} message={message} />
      ))}
      <div ref={bottomRef} />
    </div>
  );
}
