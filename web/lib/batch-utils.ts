/**
 * Utility functions for batch processing operations.
 */

import JSZip from "jszip";

/**
 * Detect the type of upload based on the files provided.
 */
export function detectUploadType(files: FileList): "single" | "batch" | "zip" | null {
  if (!files || files.length === 0) return null;

  // Single file check
  if (files.length === 1) {
    const file = files[0];
    if (file.type === "application/zip" || file.name.toLowerCase().endsWith(".zip")) {
      return "zip";
    }
    return "single";
  }

  // Multiple files = batch
  return "batch";
}

/**
 * Validate that all files in a batch are PDFs.
 */
export function validatePdfBatch(files: FileList): string[] {
  const errors: string[] = [];

  Array.from(files).forEach((file) => {
    if (!file.name) {
      errors.push("File has no name");
      return;
    }

    const mimeType = file.type;
    const isNamePdf = file.name.toLowerCase().endsWith(".pdf");

    if (mimeType !== "application/pdf" && !isNamePdf) {
      errors.push(`${file.name}: Not a PDF file (type: ${mimeType || "unknown"})`);
    }
  });

  return errors;
}

/**
 * Convert File[] to FileList (for compatibility).
 */
export function createFileList(files: File[]): FileList {
  const dataTransfer = new DataTransfer();
  files.forEach((file) => dataTransfer.items.add(file));
  return dataTransfer.files;
}

/**
 * Extract PDF files from a ZIP archive.
 */
export async function extractZipFile(zipFile: File): Promise<File[]> {
  try {
    const zip = new JSZip();
    const zipData = await zip.loadAsync(zipFile);
    const pdfFiles: File[] = [];

    // Iterate through all files in the ZIP
    for (const [filename, file] of Object.entries(zipData.files)) {
      // Skip directories and non-PDF files
      if (file.dir) continue;
      if (!filename.toLowerCase().endsWith(".pdf")) continue;

      // Extract file content
      const blob = await file.async("blob");
      const extractedFile = new File([blob], filename, { type: "application/pdf" });
      pdfFiles.push(extractedFile);
    }

    return pdfFiles;
  } catch (error) {
    console.error("Failed to extract ZIP file:", error);
    throw new Error(`Failed to extract ZIP file: ${error instanceof Error ? error.message : String(error)}`);
  }
}

/**
 * Calculate overall batch progress from document progresses.
 */
export function calculateBatchProgress(
  documentsCompleted: number,
  totalDocuments: number,
  currentDocumentProgress?: number
): number {
  if (totalDocuments === 0) return 0;

  const completedWeight = documentsCompleted / totalDocuments;
  const currentWeight = currentDocumentProgress
    ? (currentDocumentProgress / 100) / totalDocuments
    : 0;

  return (completedWeight + currentWeight) * 100;
}

/**
 * Format batch status for display.
 */
export function formatBatchStatus(
  status: string,
  documentsCompleted: number,
  totalDocuments: number
): string {
  switch (status) {
    case "queued":
      return "Queued";
    case "processing":
      return `Processing (${documentsCompleted}/${totalDocuments})`;
    case "completed":
      return "Completed";
    case "failed":
      return "Failed";
    case "cancelled":
      return "Cancelled";
    default:
      return status;
  }
}

/**
 * Group batch results by document.
 */
export function groupResultsByDocument(results: any[]): Map<string, any[]> {
  const grouped = new Map<string, any[]>();

  results.forEach((result) => {
    const filename = result.filename || "unknown";
    if (!grouped.has(filename)) {
      grouped.set(filename, []);
    }
    grouped.get(filename)!.push(result);
  });

  return grouped;
}
