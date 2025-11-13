"use client";

import { useState } from "react";
import { useSystemMetrics } from "@/hooks/useSystemMetrics";
import { SystemMonitor } from "./SystemMonitor";
import { Activity, X } from "lucide-react";

interface SystemMonitorWidgetProps {
  enabled: boolean;
  isExpanded: boolean;
  onToggle: (expanded: boolean) => void;
}

export function SystemMonitorWidget({ enabled, isExpanded, onToggle }: SystemMonitorWidgetProps) {
  const { current, history, alerts, isConnected, error } = useSystemMetrics({
    enabled,
    interval: 1,
    historySize: 60,
  });

  if (!enabled) return null;

  // Determine badge color based on alerts
  const badgeColor = alerts.some((a) => a.type === "error")
    ? "bg-red-500 hover:bg-red-600"
    : alerts.some((a) => a.type === "warning")
    ? "bg-yellow-500 hover:bg-yellow-600"
    : "bg-green-500 hover:bg-green-600";

  // Get primary GPU memory for badge
  const gpuMemory = current?.gpus?.[0]
    ? ((current.gpus[0].memory_used_mb / current.gpus[0].memory_total_mb) * 100).toFixed(0)
    : "--";

  return (
    <>
      {/* Toggle button - positioned outside collapsed container */}
      {!isExpanded && (
        <button
          onClick={() => onToggle(true)}
          className={`
            fixed top-20 right-4 z-50
            ${badgeColor}
            text-white rounded-full p-3
            shadow-lg transition-all duration-200
            flex items-center justify-center
            hover:scale-110
          `}
          aria-label="Open system monitor"
          title={`GPU ${gpuMemory}%${!isConnected ? ' (offline)' : ''}`}
        >
          <Activity className="w-5 h-5" />
        </button>
      )}

      {/* Expandable sidebar */}
      <div
        className={`
          flex flex-col border-l border-border
          bg-gray-900 text-white
          overflow-y-auto
          transition-all duration-300 ease-in-out
          ${isExpanded ? 'flex-1' : 'w-0'}
        `}
      >
        {/* Header - shows when expanded */}
        {isExpanded && (
          <>
            <div className="sticky top-0 bg-gray-900 border-b border-gray-700 p-4 flex items-center justify-between z-10">
              <div className="flex items-center gap-2">
                <Activity className={`w-5 h-5 ${badgeColor.includes('red') ? 'text-red-500' : badgeColor.includes('yellow') ? 'text-yellow-500' : 'text-green-500'}`} />
                <h2 className="text-lg font-semibold">System Monitor</h2>
                {!isConnected && <span className="text-xs text-gray-400">(offline)</span>}
              </div>
              <button
                onClick={() => onToggle(false)}
                className="p-1 hover:bg-gray-800 rounded transition-colors"
                aria-label="Close"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            {/* Content */}
            <div className="p-4">
              {error && (
                <div className="bg-red-900/50 border border-red-700 rounded p-3 mb-4 text-sm">
                  {error}
                </div>
              )}

              <SystemMonitor
                current={current}
                history={history}
                alerts={alerts}
                isConnected={isConnected}
              />
            </div>
          </>
        )}
      </div>
    </>
  );
}
