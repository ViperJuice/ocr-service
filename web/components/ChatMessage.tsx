"use client";

import { ChatMessage as ChatMessageType } from "@/lib/types";
import { formatTimestamp } from "@/lib/utils";
import { User, Bot } from "lucide-react";
import { InlineProgress } from "./InlineProgress";

interface ChatMessageProps {
  message: ChatMessageType;
}

export function ChatMessage({ message }: ChatMessageProps) {
  const isUser = message.role === "user";

  return (
    <div className={`flex gap-3 ${isUser ? "flex-row-reverse" : "flex-row"} animate-slide-up`}>
      {/* Avatar */}
      <div
        className={`flex-shrink-0 w-8 h-8 rounded-full flex items-center justify-center ${
          isUser ? "bg-primary/20" : "bg-surface"
        }`}
      >
        {isUser ? (
          <User className="w-4 h-4 text-primary" />
        ) : (
          <Bot className="w-4 h-4 text-accent-cyan" />
        )}
      </div>

      {/* Message content */}
      <div className={`flex-1 max-w-[80%] ${isUser ? "items-end" : "items-start"} flex flex-col`}>
        <div
          className={`${
            isUser ? "chat-bubble-user" : "chat-bubble-system"
          } whitespace-pre-wrap`}
        >
          <p className="text-sm leading-relaxed">{message.content}</p>

          {/* Inline progress rendering */}
          {message.inlineProgress && (
            <InlineProgress {...message.inlineProgress} />
          )}
        </div>

        {/* Timestamp */}
        <span className="text-xs text-text-muted mt-1 px-2">
          {formatTimestamp(message.timestamp)}
        </span>
      </div>
    </div>
  );
}
