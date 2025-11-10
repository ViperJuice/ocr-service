"use client";

import { useState } from "react";
import dynamic from "next/dynamic";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import {
  FileText,
  Code,
  List,
  Copy,
  Check,
  Download,
  Maximize2,
} from "lucide-react";
import { OutputFormat } from "@/lib/types";
import { downloadBlob } from "@/lib/utils";

const MonacoEditor = dynamic(() => import("@monaco-editor/react"), {
  ssr: false,
  loading: () => <div className="p-4 text-text-muted">Loading editor...</div>,
});

interface ResultViewerProps {
  content: string;
  format: OutputFormat;
  filename?: string;
  onFormatChange?: (format: OutputFormat) => void;
}

export function ResultViewer({
  content,
  format,
  filename = "result",
  onFormatChange,
}: ResultViewerProps) {
  const [copied, setCopied] = useState(false);
  const [isFullscreen, setIsFullscreen] = useState(false);

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(content);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch (error) {
      console.error("Failed to copy:", error);
    }
  };

  const handleDownload = () => {
    const extensions = {
      markdown: ".md",
      json: ".json",
      text: ".txt",
    };

    const blob = new Blob([content], { type: "text/plain" });
    downloadBlob(blob, `${filename}${extensions[format]}`);
  };

  const formatButtons: { value: OutputFormat; icon: any; label: string }[] = [
    { value: "markdown", icon: FileText, label: "Markdown" },
    { value: "json", icon: Code, label: "JSON" },
    { value: "text", icon: List, label: "Text" },
  ];

  return (
    <div
      className={`flex flex-col bg-background-secondary border border-border rounded-lg overflow-hidden ${
        isFullscreen ? "fixed inset-4 z-50" : "h-full"
      }`}
    >
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-border bg-surface">
        <div className="flex items-center gap-2">
          {formatButtons.map(({ value, icon: Icon, label }) => (
            <button
              key={value}
              onClick={() => onFormatChange?.(value)}
              className={`flex items-center gap-2 px-3 py-1.5 rounded-lg text-sm transition-all ${
                format === value
                  ? "bg-primary text-white"
                  : "bg-background-tertiary text-text-muted hover:text-text-primary hover:bg-surface-hover"
              }`}
              title={label}
            >
              <Icon className="w-4 h-4" />
              <span className="hidden sm:inline">{label}</span>
            </button>
          ))}
        </div>

        <div className="flex items-center gap-2">
          <button
            onClick={handleCopy}
            className="p-2 hover:bg-surface-hover rounded-lg transition-colors"
            title="Copy to clipboard"
          >
            {copied ? (
              <Check className="w-4 h-4 text-success" />
            ) : (
              <Copy className="w-4 h-4 text-text-muted" />
            )}
          </button>

          <button
            onClick={handleDownload}
            className="p-2 hover:bg-surface-hover rounded-lg transition-colors"
            title="Download"
          >
            <Download className="w-4 h-4 text-text-muted" />
          </button>

          <button
            onClick={() => setIsFullscreen(!isFullscreen)}
            className="p-2 hover:bg-surface-hover rounded-lg transition-colors"
            title={isFullscreen ? "Exit fullscreen" : "Fullscreen"}
          >
            <Maximize2 className="w-4 h-4 text-text-muted" />
          </button>
        </div>
      </div>

      {/* Content */}
      <div className="flex-1 overflow-auto">
        {format === "markdown" && (
          <div className="markdown-content p-6">
            <ReactMarkdown remarkPlugins={[remarkGfm]}>{content}</ReactMarkdown>
          </div>
        )}

        {format === "json" && (
          <MonacoEditor
            height="100%"
            language="json"
            theme="vs-dark"
            value={content}
            options={{
              readOnly: true,
              minimap: { enabled: false },
              fontSize: 14,
              lineNumbers: "on",
              scrollBeyondLastLine: false,
              wordWrap: "on",
              folding: true,
            }}
          />
        )}

        {format === "text" && (
          <pre className="p-6 text-sm font-mono text-text-secondary whitespace-pre-wrap leading-relaxed">
            {content}
          </pre>
        )}
      </div>
    </div>
  );
}
