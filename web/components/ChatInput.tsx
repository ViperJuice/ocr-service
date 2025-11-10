"use client";

import { useState, useRef, KeyboardEvent } from "react";
import { Send, Loader2, FileText, X } from "lucide-react";
import { getSuggestions } from "@/lib/command-parser";

interface ChatInputProps {
  onSend: (message: string) => void;
  onFilesDropped?: (files: File[]) => void;
  disabled?: boolean;
  isProcessing?: boolean;
  placeholder?: string;
  droppedFiles?: File[];
  onClearFiles?: () => void;
}

export function ChatInput({
  onSend,
  onFilesDropped,
  disabled = false,
  isProcessing = false,
  placeholder = "Type a command or question...",
  droppedFiles = [],
  onClearFiles,
}: ChatInputProps) {
  const [input, setInput] = useState("");
  const [showSuggestions, setShowSuggestions] = useState(false);
  const [suggestions, setSuggestions] = useState<string[]>([]);
  const [isDragging, setIsDragging] = useState(false);
  const [localDroppedFiles, setLocalDroppedFiles] = useState<File[]>([]);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  // Use external files if provided, otherwise use local state
  const files = droppedFiles.length > 0 ? droppedFiles : localDroppedFiles;

  const handleSend = () => {
    const trimmed = input.trim();
    if (trimmed && !disabled && !isProcessing) {
      onSend(trimmed);
      setInput("");
      setShowSuggestions(false);
      inputRef.current?.focus();
    }
  };

  const handleKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  const handleInputChange = (value: string) => {
    setInput(value);

    // Update suggestions
    const newSuggestions = getSuggestions(value);
    setSuggestions(newSuggestions);
    setShowSuggestions(value.length > 0 && newSuggestions.length > 0);
  };

  const selectSuggestion = (suggestion: string) => {
    setInput(suggestion);
    setShowSuggestions(false);
    inputRef.current?.focus();
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);
    const files = Array.from(e.dataTransfer.files);

    // Filter only PDF files
    const pdfFiles = files.filter((f) => f.type === "application/pdf" || f.name.endsWith(".zip"));

    if (pdfFiles.length > 0) {
      if (onFilesDropped) {
        onFilesDropped(pdfFiles);
      } else {
        setLocalDroppedFiles(pdfFiles);
      }
    }
  };

  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(true);
  };

  const handleDragLeave = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);
  };

  const clearFiles = () => {
    setLocalDroppedFiles([]);
    if (onClearFiles) {
      onClearFiles();
    }
  };

  return (
    <div
      className="chat-input-container relative border-t border-border bg-background-secondary"
      onDrop={handleDrop}
      onDragOver={handleDragOver}
      onDragLeave={handleDragLeave}
    >
      {/* Drag overlay */}
      {isDragging && (
        <div className="drag-overlay">
          <span className="drag-overlay-text">Drop PDF files here</span>
        </div>
      )}

      {/* Suggestions dropdown */}
      {showSuggestions && suggestions.length > 0 && (
        <div className="absolute bottom-full left-0 right-0 mb-2 mx-4 bg-surface border border-border rounded-lg shadow-lg max-h-48 overflow-y-auto">
          {suggestions.slice(0, 5).map((suggestion, index) => (
            <button
              key={index}
              onClick={() => selectSuggestion(suggestion)}
              className="w-full text-left px-4 py-2 text-sm hover:bg-surface-hover transition-colors first:rounded-t-lg last:rounded-b-lg"
            >
              {suggestion}
            </button>
          ))}
        </div>
      )}

      {/* Input area */}
      <div className="flex flex-col gap-2 p-4">
        {/* File preview */}
        {files.length > 0 && (
          <div
            className={`file-preview ${
              files.length > 1 ? "file-preview-batch" : "file-preview-single"
            }`}
          >
            <FileText className="w-4 h-4" />
            <span className="file-preview-item">
              {files.length === 1
                ? files[0].name
                : `${files.length} files ready`}
            </span>
            <button onClick={clearFiles} className="ml-auto hover:opacity-70 transition-opacity">
              <X className="w-4 h-4" />
            </button>
          </div>
        )}

        <div className="flex items-end gap-2">
        <textarea
          ref={inputRef}
          value={input}
          onChange={(e) => handleInputChange(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder={placeholder}
          disabled={disabled || isProcessing}
          rows={1}
          className="flex-1 bg-surface border border-border rounded-lg px-4 py-3 text-sm text-text-primary placeholder-text-muted resize-none focus:outline-none focus:ring-2 focus:ring-primary focus:border-transparent disabled:opacity-50 disabled:cursor-not-allowed max-h-32"
          style={{
            minHeight: "44px",
            height: "auto",
          }}
          onInput={(e) => {
            const target = e.target as HTMLTextAreaElement;
            target.style.height = "auto";
            target.style.height = `${Math.min(target.scrollHeight, 128)}px`;
          }}
        />

          <button
            onClick={handleSend}
            disabled={!input.trim() || disabled || isProcessing}
            className="flex-shrink-0 p-3 bg-primary hover:bg-primary-hover disabled:bg-surface disabled:cursor-not-allowed rounded-lg transition-all glow-on-hover disabled:shadow-none"
            title="Send message"
          >
            {isProcessing ? (
              <Loader2 className="w-5 h-5 animate-spin text-white" />
            ) : (
              <Send className="w-5 h-5 text-white" />
            )}
          </button>
        </div>
      </div>
    </div>
  );
}
