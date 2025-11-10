"use client";

import { useCallback, useState } from "react";
import { useDropzone } from "react-dropzone";
import { Upload, File, X, AlertCircle } from "lucide-react";
import { formatBytes } from "@/lib/utils";
import { FileMetadata } from "@/lib/types";

const MAX_FILE_SIZE = 50 * 1024 * 1024; // 50MB
const ACCEPTED_TYPES = {
  "application/pdf": [".pdf"],
  "image/png": [".png"],
  "image/jpeg": [".jpg", ".jpeg"],
  "image/tiff": [".tiff", ".tif"],
  "image/bmp": [".bmp"],
};

interface FileDropZoneProps {
  onFileSelect: (file: File) => void;
  uploadedFile?: FileMetadata | null;
  isUploading?: boolean;
  onClear?: () => void;
}

export function FileDropZone({
  onFileSelect,
  uploadedFile,
  isUploading = false,
  onClear,
}: FileDropZoneProps) {
  const [error, setError] = useState<string | null>(null);

  const onDrop = useCallback(
    (acceptedFiles: File[], rejectedFiles: any[]) => {
      setError(null);

      if (rejectedFiles.length > 0) {
        const rejection = rejectedFiles[0];
        if (rejection.file.size > MAX_FILE_SIZE) {
          setError("File too large. Maximum size is 50MB.");
        } else {
          setError("Invalid file type. Please upload PDF or image files.");
        }
        return;
      }

      if (acceptedFiles.length > 0) {
        const file = acceptedFiles[0];

        if (file.size > MAX_FILE_SIZE) {
          setError("File too large. Maximum size is 50MB.");
          return;
        }

        onFileSelect(file);
      }
    },
    [onFileSelect]
  );

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    accept: ACCEPTED_TYPES,
    maxFiles: 1,
    maxSize: MAX_FILE_SIZE,
    disabled: isUploading || !!uploadedFile,
  });

  if (uploadedFile) {
    return (
      <div className="border border-border rounded-lg p-6 bg-surface">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="p-2 bg-primary/20 rounded-lg">
              <File className="w-5 h-5 text-primary" />
            </div>
            <div>
              <p className="font-medium text-text-primary">{uploadedFile.filename}</p>
              <div className="flex items-center gap-3 text-sm text-text-muted">
                <span>{formatBytes(uploadedFile.size_bytes)}</span>
                {uploadedFile.page_count && (
                  <span>• {uploadedFile.page_count} pages</span>
                )}
                <span>• {uploadedFile.mime_type.split("/")[1].toUpperCase()}</span>
              </div>
            </div>
          </div>
          {onClear && (
            <button
              onClick={onClear}
              className="p-2 hover:bg-surface-hover rounded-lg transition-colors"
              title="Remove file"
            >
              <X className="w-5 h-5 text-text-muted hover:text-text-primary" />
            </button>
          )}
        </div>
      </div>
    );
  }

  return (
    <div>
      <div
        {...getRootProps()}
        className={`drop-zone ${isDragActive ? "drop-zone-active" : ""} ${
          isUploading ? "opacity-50 cursor-not-allowed" : "cursor-pointer"
        }`}
      >
        <input {...getInputProps()} />

        <div className="flex flex-col items-center gap-4 text-center">
          <div className={`p-4 rounded-full ${isDragActive ? "bg-primary/20" : "bg-surface"}`}>
            <Upload className={`w-8 h-8 ${isDragActive ? "text-primary" : "text-text-muted"}`} />
          </div>

          <div>
            <p className="text-lg font-medium text-text-primary mb-1">
              {isDragActive ? "Drop your file here" : "Drop file or click to upload"}
            </p>
            <p className="text-sm text-text-muted">
              PDF, PNG, JPEG, TIFF, or BMP • Max 50MB
            </p>
          </div>

          {isUploading && (
            <div className="flex items-center gap-2 text-primary">
              <div className="w-4 h-4 border-2 border-primary border-t-transparent rounded-full animate-spin" />
              <span className="text-sm">Uploading...</span>
            </div>
          )}
        </div>
      </div>

      {error && (
        <div className="mt-3 flex items-center gap-2 text-error text-sm bg-error/10 border border-error/20 rounded-lg px-4 py-2">
          <AlertCircle className="w-4 h-4 flex-shrink-0" />
          <span>{error}</span>
        </div>
      )}
    </div>
  );
}
