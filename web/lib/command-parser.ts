/**
 * Command parser for chat-based OCR commands.
 *
 * Provides regex-based parsing for user commands as a fallback
 * when BAML orchestration is not available or fails.
 */

export interface ParsedCommand {
  type: string;
  params: Record<string, any>;
  originalText: string;
}

/**
 * Parse a user command into a structured format.
 */
export function parseCommand(input: string): ParsedCommand {
  const normalized = input.toLowerCase().trim();

  // Parse directory/batch commands
  if (normalized.match(/parse (the )?(whole |entire )?(directory|batch|all files)/)) {
    return {
      type: "parse_directory",
      params: {},
      originalText: input,
    };
  }

  // Parse all pages
  if (normalized.match(/parse (the )?(whole |entire )?(document|file|pdf)/)) {
    return {
      type: "parse_all",
      params: {},
      originalText: input,
    };
  }

  // Parse specific page
  const pageMatch = normalized.match(/parse page (\d+)/);
  if (pageMatch) {
    return {
      type: "parse_page",
      params: {
        pageNumber: parseInt(pageMatch[1], 10),
      },
      originalText: input,
    };
  }

  // Parse page range
  const rangeMatch = normalized.match(/parse pages? (\d+)[-\s]?(?:to|through)?\s?(\d+)/);
  if (rangeMatch) {
    return {
      type: "parse_range",
      params: {
        startPage: parseInt(rangeMatch[1], 10),
        endPage: parseInt(rangeMatch[2], 10),
      },
      originalText: input,
    };
  }

  // Change output format
  const formatMatch = normalized.match(/(?:show|output|format) (?:as |in )?(\w+)/);
  if (formatMatch) {
    const format = formatMatch[1];
    if (["markdown", "text", "json"].includes(format)) {
      return {
        type: "change_format",
        params: {
          format,
        },
        originalText: input,
      };
    }
  }

  // Check status
  if (normalized.match(/(check |get |show )?(status|progress)/)) {
    return {
      type: "check_status",
      params: {},
      originalText: input,
    };
  }

  // Get results
  if (normalized.match(/(get|show|display) (the )?results?/)) {
    return {
      type: "get_results",
      params: {},
      originalText: input,
    };
  }

  // Cancel job
  if (normalized.match(/cancel|stop/)) {
    return {
      type: "cancel",
      params: {},
      originalText: input,
    };
  }

  // Unknown command
  return {
    type: "unknown",
    params: {},
    originalText: input,
  };
}

/**
 * Get command suggestions based on input.
 */
export function getSuggestions(input: string): string[] {
  const normalized = input.toLowerCase().trim();

  const allSuggestions = [
    "Parse the whole document",
    "Parse page 5",
    "Parse pages 1 to 10",
    "Parse the whole directory",
    "Parse directory",
    "Show as JSON",
    "Show as markdown",
    "Show as text",
    "Check status",
    "Get results",
  ];

  // If input is empty, return all suggestions
  if (!normalized) {
    return allSuggestions;
  }

  // Filter suggestions that match the input
  return allSuggestions.filter((suggestion) =>
    suggestion.toLowerCase().includes(normalized)
  );
}

/**
 * Validate a parsed command.
 */
export function validateCommand(command: ParsedCommand): {
  valid: boolean;
  error?: string;
} {
  switch (command.type) {
    case "parse_page":
      if (!command.params.pageNumber || command.params.pageNumber < 1) {
        return {
          valid: false,
          error: "Page number must be a positive integer",
        };
      }
      break;

    case "parse_range":
      if (
        !command.params.startPage ||
        !command.params.endPage ||
        command.params.startPage < 1 ||
        command.params.endPage < 1
      ) {
        return {
          valid: false,
          error: "Page numbers must be positive integers",
        };
      }
      if (command.params.startPage > command.params.endPage) {
        return {
          valid: false,
          error: "Start page must be less than or equal to end page",
        };
      }
      break;

    case "change_format":
      if (!["markdown", "text", "json"].includes(command.params.format)) {
        return {
          valid: false,
          error: "Format must be one of: markdown, text, json",
        };
      }
      break;
  }

  return { valid: true };
}
