import { SavedPrompt, ChatMessage } from "./types";

const PROMPTS_KEY = "ocr_saved_prompts";
const CHAT_HISTORY_KEY = "ocr_chat_history";

export const storage = {
  // Saved prompts
  getPrompts(): SavedPrompt[] {
    if (typeof window === "undefined") return [];

    try {
      const stored = localStorage.getItem(PROMPTS_KEY);
      return stored ? JSON.parse(stored) : getDefaultPrompts();
    } catch (error) {
      console.error("Failed to load prompts:", error);
      return getDefaultPrompts();
    }
  },

  savePrompts(prompts: SavedPrompt[]): void {
    if (typeof window === "undefined") return;

    try {
      localStorage.setItem(PROMPTS_KEY, JSON.stringify(prompts));
    } catch (error) {
      console.error("Failed to save prompts:", error);
    }
  },

  addPrompt(prompt: SavedPrompt): void {
    const prompts = this.getPrompts();
    prompts.push(prompt);
    this.savePrompts(prompts);
  },

  updatePrompt(id: string, updates: Partial<SavedPrompt>): void {
    const prompts = this.getPrompts();
    const index = prompts.findIndex((p) => p.id === id);

    if (index !== -1) {
      prompts[index] = { ...prompts[index], ...updates, updatedAt: Date.now() };
      this.savePrompts(prompts);
    }
  },

  deletePrompt(id: string): void {
    const prompts = this.getPrompts().filter((p) => p.id !== id);
    this.savePrompts(prompts);
  },

  // Chat history
  getChatHistory(): ChatMessage[] {
    if (typeof window === "undefined") return [];

    try {
      const stored = localStorage.getItem(CHAT_HISTORY_KEY);
      return stored ? JSON.parse(stored) : [];
    } catch (error) {
      console.error("Failed to load chat history:", error);
      return [];
    }
  },

  saveChatHistory(messages: ChatMessage[]): void {
    if (typeof window === "undefined") return;

    try {
      // Keep only last 100 messages to avoid storage limits
      const trimmed = messages.slice(-100);
      localStorage.setItem(CHAT_HISTORY_KEY, JSON.stringify(trimmed));
    } catch (error) {
      console.error("Failed to save chat history:", error);
    }
  },

  clearChatHistory(): void {
    if (typeof window === "undefined") return;
    localStorage.removeItem(CHAT_HISTORY_KEY);
  },

  // Export/Import
  exportPrompts(): string {
    const prompts = this.getPrompts();
    return JSON.stringify(prompts, null, 2);
  },

  importPrompts(jsonString: string): boolean {
    try {
      const prompts = JSON.parse(jsonString) as SavedPrompt[];

      // Validate structure
      if (!Array.isArray(prompts)) {
        throw new Error("Invalid format: not an array");
      }

      // Merge with existing prompts (avoid duplicates by name)
      const existing = this.getPrompts();
      const existingNames = new Set(existing.map((p) => p.name));

      const newPrompts = prompts.filter((p) => !existingNames.has(p.name));
      this.savePrompts([...existing, ...newPrompts]);

      return true;
    } catch (error) {
      console.error("Failed to import prompts:", error);
      return false;
    }
  },
};

function getDefaultPrompts(): SavedPrompt[] {
  return [
    {
      id: "default-standard",
      name: "Standard Document",
      category: "Standard",
      description: "General-purpose OCR for standard documents",
      prompts: {},
      createdAt: Date.now(),
      updatedAt: Date.now(),
    },
    {
      id: "default-legal",
      name: "Legal Document",
      category: "Legal",
      description: "Optimized for legal documents with citations",
      prompts: {
        merge: `You are a legal document specialist. Carefully merge these texts while preserving legal terminology, citations, and formatting:

Embedded text: {embedded_text}
OCR text: {ocr_text}

Ensure all section numbers, citations, and legal references are accurately preserved.`,
      },
      createdAt: Date.now(),
      updatedAt: Date.now(),
    },
    {
      id: "default-technical",
      name: "Technical Manual",
      category: "Technical",
      description: "For technical documentation with diagrams and code",
      prompts: {
        merge: `You are processing a technical manual. Merge these texts while preserving:
- Code snippets and formatting
- Technical terminology
- Diagram references
- Section numbering

Embedded text: {embedded_text}
OCR text: {ocr_text}`,
      },
      createdAt: Date.now(),
      updatedAt: Date.now(),
    },
    {
      id: "default-medical",
      name: "Medical Record",
      category: "Medical",
      description: "For medical records and clinical documents",
      prompts: {
        merge: `You are processing medical documentation. Merge these texts while maintaining:
- Medical terminology accuracy
- Patient information formatting
- Date and time stamps
- Dosage and measurement precision

Embedded text: {embedded_text}
OCR text: {ocr_text}`,
      },
      createdAt: Date.now(),
      updatedAt: Date.now(),
    },
  ];
}
