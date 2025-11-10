"use client";

import { useState, useCallback } from "react";
import { MessageList } from "@/components/MessageList";
import { ChatInput } from "@/components/ChatInput";
import { ResultViewer } from "@/components/ResultViewer";
import { ProgressMonitor } from "@/components/ProgressMonitor";
import { SystemMonitorWidget } from "@/components/SystemMonitorWidget";
import { SettingsModal } from "@/components/SettingsModal";
import { useOcrJob } from "@/hooks/useOcrJob";
import { useBatchJob } from "@/hooks/useBatchJob";
import { ChatMessage, OutputFormat } from "@/lib/types";
import { generateId } from "@/lib/utils";
import { parseCommand } from "@/lib/command-parser";
import { orchestrateUserMessage, refactorPromptWithStreaming } from "@/app/actions/baml-actions";
import {
  detectUploadType,
  validatePdfBatch,
  createFileList,
  extractZipFile,
} from "@/lib/batch-utils";
import { FileText, Settings } from "lucide-react";

export default function Home() {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [outputFormat, setOutputFormat] = useState<OutputFormat>("markdown");
  const [isProcessing, setIsProcessing] = useState(false);
  const [isSettingsOpen, setIsSettingsOpen] = useState(false);
  const [monitoringEnabled, setMonitoringEnabled] = useState(false);
  const [droppedFiles, setDroppedFiles] = useState<File[]>([]);
  const [uploadType, setUploadType] = useState<"single" | "batch" | "zip" | null>(null);

  const {
    currentFile,
    currentJob,
    jobResult,
    uploadFile,
    submitJob,
    fetchResult,
    reset,
    isUploading,
  } = useOcrJob();

  const {
    currentDirectory,
    currentBatchJob,
    batchResult,
    uploadDirectory,
    submitBatchJob,
    fetchBatchResult,
    reset: resetBatch,
    isUploading: isUploadingBatch,
  } = useBatchJob();

  // Add message to chat
  const addMessage = useCallback((role: "user" | "system", content: string, metadata?: any) => {
    const message: ChatMessage = {
      id: generateId(),
      role,
      content,
      timestamp: Date.now(),
      metadata,
    };
    setMessages((prev) => [...prev, message]);
  }, []);

  // Handle files dropped into chat
  const handleFilesDropped = useCallback(
    async (files: File[]) => {
      const type = detectUploadType(createFileList(files));
      setUploadType(type);
      setDroppedFiles(files);

      if (type === "single") {
        addMessage("system", `Uploading ${files[0].name}...`);
        try {
          await uploadFile(files[0]);
          addMessage("system", `File uploaded! What would you like to do?`);
          setDroppedFiles([]);
        } catch (error: any) {
          addMessage("system", `Upload failed: ${error.message}`);
        }
      } else if (type === "batch") {
        // Validate files
        const errors = validatePdfBatch(createFileList(files));
        if (errors.length > 0) {
          addMessage("system", `Validation errors: ${errors.join(", ")}`);
          return;
        }

        addMessage("system", `Uploading ${files.length} files...`);
        try {
          const fileList = createFileList(files);
          const directory = await uploadDirectory(fileList, `batch_${Date.now()}`);
          addMessage(
            "system",
            `Uploaded ${directory.file_count} files. Type "parse the whole directory" to process.`
          );
          setDroppedFiles([]);
        } catch (error: any) {
          addMessage("system", `Upload failed: ${error.message}`);
        }
      } else if (type === "zip") {
        addMessage("system", `ZIP file detected. Extracting PDFs...`);
        try {
          const extractedFiles = await extractZipFile(files[0]);
          if (extractedFiles.length === 0) {
            addMessage("system", `No PDF files found in ZIP archive.`);
            return;
          }

          addMessage("system", `Extracted ${extractedFiles.length} PDF file(s). Uploading...`);
          const fileList = createFileList(extractedFiles);
          const directory = await uploadDirectory(fileList, `zip_${Date.now()}`);
          addMessage(
            "system",
            `Uploaded ${directory.file_count} files. Type "parse the whole directory" to process.`
          );
          setDroppedFiles([]);
        } catch (error: any) {
          addMessage("system", `ZIP extraction failed: ${error.message}`);
        }
      }
    },
    [uploadFile, uploadDirectory, addMessage]
  );

  // Handle chat command
  const handleCommand = useCallback(
    async (userInput: string) => {
      addMessage("user", userInput);

      // First, try BAML orchestration for intelligent command parsing
      try {
        // Build job context
        const jobContext = currentFile
          ? `File: ${currentFile.filename}, Pages: ${currentFile.page_count || "unknown"}`
          : currentDirectory
          ? `Directory: ${currentDirectory.file_count} files`
          : undefined;

        // Get config context
        const config = JSON.stringify({
          outputFormat,
          currentFile: currentFile ? { id: currentFile.file_id, name: currentFile.filename } : null,
          currentDirectory: currentDirectory ? { id: currentDirectory.directory_id, fileCount: currentDirectory.file_count } : null,
        });

        // Orchestrate with BAML
        const orchestration = await orchestrateUserMessage(
          userInput,
          currentJob?.job_id,
          config,
          jobContext
        );

        // LOG: BAML orchestration result
        console.log("=== BAML ORCHESTRATION RESULT ===");
        console.log("User Input:", userInput);
        console.log("Intent:", orchestration.intent);
        console.log("Parameters:", JSON.stringify(orchestration.parameters, null, 2));
        console.log("User Message:", orchestration.user_message);
        console.log("Validation:", orchestration.validation);
        console.log("=================================");

        // Display user-facing message from BAML
        if (orchestration.user_message) {
          addMessage("assistant", orchestration.user_message);
        }

        // Handle based on intent
        switch (orchestration.intent) {
          case "START_OCR_JOB": {
            if (!currentFile) {
              addMessage("system", "Please upload a file first.");
              return;
            }

            setIsProcessing(true);

            // Check if complex prompt refactoring is needed
            if (orchestration.parameters.format_references && orchestration.parameters.format_references.length > 0) {
              addMessage("system", "Analyzing formatting requirements...");

              // Refactor prompt with streaming (note: callback not supported in server actions)
              const refactored = await refactorPromptWithStreaming(
                userInput,
                jobContext || "",
                "ocr",
                orchestration.parameters.format_references,
                currentJob?.job_id
              );

              addMessage("system", `Starting OCR with custom formatting instructions (confidence: ${refactored.confidence})...`);

              // BAML parameters now match backend API exactly - pass through directly
              submitJob({
                file_id: currentFile.file_id,
                model: orchestration.parameters.model,
                prompt_type: orchestration.parameters.prompt_type,
                output_format: orchestration.parameters.output_format || outputFormat,
                processing_options: orchestration.parameters.processing_options,
                custom_prompts: {
                  ...orchestration.parameters.custom_prompts,
                  ocr: refactored.ocr_prompt || undefined,
                  merge: refactored.merge_prompt || undefined,
                },
              });
            } else {
              // Simple job submission - BAML parameters match backend API exactly
              // Remove null values to avoid Pydantic validation errors
              const cleanParams = Object.fromEntries(
                Object.entries(orchestration.parameters).filter(([_, v]) => v !== null)
              );

              // Clean nested processing_options
              if (cleanParams.processing_options) {
                cleanParams.processing_options = Object.fromEntries(
                  Object.entries(cleanParams.processing_options).filter(([_, v]) => v !== null)
                );
                // Remove empty processing_options object
                if (Object.keys(cleanParams.processing_options).length === 0) {
                  delete cleanParams.processing_options;
                }
              }

              // Clean custom_prompts
              if (cleanParams.custom_prompts) {
                cleanParams.custom_prompts = Object.fromEntries(
                  Object.entries(cleanParams.custom_prompts).filter(([_, v]) => v !== null)
                );
                if (Object.keys(cleanParams.custom_prompts).length === 0) {
                  delete cleanParams.custom_prompts;
                }
              }

              const jobRequest = {
                file_id: currentFile.file_id,
                ...cleanParams,
              };

              // LOG: What we're sending to backend API
              console.log("=== SENDING TO BACKEND API ===");
              console.log("Endpoint: POST /api/v1/process/jobs");
              console.log("Request Body:", JSON.stringify(jobRequest, null, 2));
              console.log("===============================");

              submitJob(jobRequest);
            }

            setIsProcessing(false);
            break;
          }

          case "ADJUST_SETTINGS": {
            if (orchestration.parameters.output_format) {
              setOutputFormat(orchestration.parameters.output_format as OutputFormat);
              addMessage("system", `Output format changed to ${orchestration.parameters.output_format}.`);
            }
            break;
          }

          case "CHECK_STATUS": {
            if (currentJob) {
              addMessage("system", `Job ${currentJob.job_id} is currently processing...`);
            } else {
              addMessage("system", "No active job at the moment.");
            }
            break;
          }

          case "GET_RESULTS": {
            if (jobResult) {
              addMessage("system", "Results are already displayed on the right panel.");
            } else {
              addMessage("system", "No results available yet. Please wait for processing to complete.");
            }
            break;
          }

          case "UNKNOWN":
          default: {
            // Fall back to regex-based command parsing for legacy support
            const command = parseCommand(userInput);

            // Handle batch directory command
            if (command.type === "parse_directory") {
              if (!currentDirectory) {
                addMessage("system", "Please upload a directory of files first.");
                return;
              }

              const systemMsg: ChatMessage = {
                id: generateId(),
                role: "system",
                content: "Starting batch processing...",
                timestamp: Date.now(),
                metadata: {},
              };
              setMessages((prev) => [...prev, systemMsg]);

              try {
                const batch = await submitBatchJob({
                  output_format: outputFormat,
                  processing_options: { prefer_quality: true },
                });

                setMessages((prev) =>
                  prev.map((m) =>
                    m.id === systemMsg.id
                      ? { ...m, metadata: { ...m.metadata, batchJobId: batch.batch_job_id } }
                      : m
                  )
                );
              } catch (error: any) {
                addMessage("system", `Batch job failed: ${error.message}`);
              }
              return;
            }

            // Legacy single-document handling
            if (!currentFile) {
              addMessage("system", "Please upload a file first.");
              return;
            }

            setIsProcessing(true);

            try {
              switch (command.type) {
                case "parse_all":
                  addMessage("system", "Starting to parse the entire document...");
                  submitJob({
                    file_id: currentFile.file_id,
                    output_format: outputFormat,
                    processing_options: { prefer_quality: true },
                  });
                  break;

                case "parse_page":
                  if (command.params.pageNumber) {
                    addMessage("system", `Parsing page ${command.params.pageNumber}...`);
                    submitJob({
                      file_id: currentFile.file_id,
                      output_format: outputFormat,
                      processing_options: {
                        start_page: command.params.pageNumber,
                        end_page: command.params.pageNumber,
                        prefer_quality: true,
                      },
                    });
                  }
                  break;

                case "parse_range":
                  if (command.params.startPage && command.params.endPage) {
                    addMessage("system", `Parsing pages ${command.params.startPage}-${command.params.endPage}...`);
                    submitJob({
                      file_id: currentFile.file_id,
                      output_format: outputFormat,
                      processing_options: {
                        start_page: command.params.startPage,
                        end_page: command.params.endPage,
                        prefer_quality: true,
                      },
                    });
                  }
                  break;

                case "change_format":
                  if (command.params.format) {
                    setOutputFormat(command.params.format as OutputFormat);
                    addMessage("system", `Output format changed to ${command.params.format}.`);
                  }
                  break;

                default:
                  addMessage("system", "I didn't understand that command. Try 'Parse the whole document' or 'Parse page 5'.");
              }
            } catch (error: any) {
              addMessage("system", `Error: ${error.message}`);
            } finally {
              setIsProcessing(false);
            }
            break;
          }
        }
      } catch (error: any) {
        console.error("BAML orchestration error:", error);
        addMessage("system", `Error processing command: ${error.message}`);
        setIsProcessing(false);
      }
    },
    [currentFile, currentDirectory, currentJob, jobResult, outputFormat, submitJob, submitBatchJob, addMessage]
  );

  // Handle job completion
  const handleJobComplete = useCallback(async () => {
    if (!currentJob) return;

    try {
      const result = await fetchResult(currentJob.job_id);

      // Build detailed completion message with filename and page count
      const filename = currentFile?.filename || "Document";
      const pageCount = result.result.metadata?.pages_processed || 1;
      const pageText = pageCount > 1 ? `${pageCount} pages` : "1 page";

      addMessage("system", `Parsing complete: ${filename} - ${pageText} processed`, {
        jobId: currentJob.job_id,
        status: "completed",
      });
    } catch (error: any) {
      addMessage("system", `Failed to retrieve result: ${error.message}`, {
        status: "failed",
      });
    }
  }, [currentJob, currentFile, fetchResult, addMessage]);

  // Handle job error
  const handleJobError = useCallback(
    (error: string) => {
      addMessage("system", `Processing failed: ${error}`, {
        status: "failed",
      });
    },
    [addMessage]
  );

  // Dynamic width classes based on monitoring sidebar state
  const [monitoringExpanded, setMonitoringExpanded] = useState(false);

  const chatWidthClass = monitoringEnabled && monitoringExpanded
    ? "w-[20%]"
    : "w-1/3";

  const documentWidthClass = monitoringEnabled && monitoringExpanded
    ? "w-[55%]"
    : "w-2/3";

  return (
    <div className="h-screen flex flex-col bg-background">
      {/* Header */}
      <header className="flex items-center justify-between px-6 py-4 border-b border-border bg-surface">
        <div className="flex items-center gap-3">
          <div className="p-2 bg-primary/20 rounded-lg">
            <FileText className="w-6 h-6 text-primary" />
          </div>
          <div>
            <h1 className="text-xl font-bold text-text-primary">OCR Service</h1>
            <p className="text-xs text-text-muted">AI-powered document processing</p>
          </div>
        </div>

        <button
          onClick={() => setIsSettingsOpen(true)}
          className="p-2 hover:bg-surface-hover rounded-lg transition-colors"
        >
          <Settings className="w-5 h-5 text-text-muted" />
        </button>
      </header>

      {/* Settings Modal */}
      <SettingsModal
        isOpen={isSettingsOpen}
        onClose={() => setIsSettingsOpen(false)}
        monitoringEnabled={monitoringEnabled}
        onMonitoringToggle={setMonitoringEnabled}
      />

      {/* Main content - now includes monitoring sidebar in flex layout */}
      <div className="flex-1 flex overflow-hidden">
        {/* Left panel - Chat */}
        <div className={`${chatWidthClass} flex flex-col border-r border-border transition-all duration-300`}>
          {/* Progress monitor */}
          {currentJob && !jobResult && (
            <div className="p-4 border-b border-border">
              <ProgressMonitor
                jobId={currentJob.job_id}
                filename={currentFile?.filename}
                onComplete={handleJobComplete}
                onError={handleJobError}
              />
            </div>
          )}

          {/* Chat messages */}
          <MessageList messages={messages} />

          {/* Chat input */}
          <ChatInput
            onSend={handleCommand}
            onFilesDropped={handleFilesDropped}
            onClearFiles={() => setDroppedFiles([])}
            droppedFiles={droppedFiles}
            disabled={isUploading || isUploadingBatch}
            isProcessing={isProcessing}
            placeholder={
              currentDirectory
                ? `${currentDirectory.file_count} files ready. Type "parse the whole directory" to begin.`
                : currentFile
                ? `File ready: ${currentFile.filename}. What would you like to do?`
                : "Type a message or drop PDF files here..."
            }
          />
        </div>

        {/* Right panel - Result viewer */}
        <div className={`${documentWidthClass} flex flex-col transition-all duration-300`}>
          {jobResult ? (
            <ResultViewer
              content={jobResult.result.content}
              format={outputFormat}
              filename={currentFile?.filename || "result"}
              onFormatChange={setOutputFormat}
            />
          ) : (
            <div className="flex-1 flex items-center justify-center text-center px-8">
              <div className="max-w-md">
                <div className="w-20 h-20 mx-auto mb-6 bg-surface rounded-full flex items-center justify-center">
                  <FileText className="w-10 h-10 text-text-muted" />
                </div>
                <h2 className="text-xl font-semibold text-text-primary mb-2">
                  No results yet
                </h2>
                <p className="text-text-muted">
                  Upload a document and start processing to see results here.
                </p>
              </div>
            </div>
          )}
        </div>

        {/* System Monitoring Widget - now part of flex layout */}
        <SystemMonitorWidget
          enabled={monitoringEnabled}
          isExpanded={monitoringExpanded}
          onToggle={setMonitoringExpanded}
        />
      </div>
    </div>
  );
}
