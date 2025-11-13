import { Alert } from "@/lib/types";
import { AlertTriangle, AlertCircle } from "lucide-react";

interface AlertBannerProps {
  alerts: Alert[];
}

export function AlertBanner({ alerts }: AlertBannerProps) {
  if (alerts.length === 0) return null;

  // Sort alerts: error first
  const sortedAlerts = [...alerts].sort((a, b) => {
    if (a.type === "error" && b.type !== "error") return -1;
    if (a.type !== "error" && b.type === "error") return 1;
    return 0;
  });

  return (
    <div className="space-y-2">
      {sortedAlerts.map((alert, index) => {
        const isError = alert.type === "error";
        const bgColor = isError ? "bg-red-500" : "bg-yellow-500";
        const textColor = isError ? "text-white" : "text-gray-900";
        const Icon = isError ? AlertCircle : AlertTriangle;

        return (
          <div
            key={`${alert.id}-${index}`}
            className={`
              ${bgColor} ${textColor}
              rounded px-3 py-2 flex items-center gap-2 text-sm font-medium
              ${isError ? "animate-pulse" : ""}
            `}
          >
            <Icon className="w-4 h-4 flex-shrink-0" />
            <span>{alert.message}</span>
          </div>
        );
      })}
    </div>
  );
}
