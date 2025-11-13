import { useState, useEffect, useCallback, useRef } from "react";
import { apiClient } from "@/lib/api-client";
import { SystemMetrics, Alert } from "@/lib/types";

interface UseSystemMetricsOptions {
  enabled?: boolean;
  interval?: number;
  historySize?: number;
}

interface UseSystemMetricsReturn {
  current: SystemMetrics | null;
  history: SystemMetrics[];
  alerts: Alert[];
  isConnected: boolean;
  error: string | null;
}

function detectAlerts(metrics: SystemMetrics): Alert[] {
  const alerts: Alert[] = [];

  // GPU memory alerts (85% warning, 95% critical)
  metrics.gpus?.forEach((gpu) => {
    const memoryPercent = (gpu.memory_used_mb / gpu.memory_total_mb) * 100;
    if (memoryPercent >= 95) {
      alerts.push({
        id: `gpu-memory-${gpu.id}-${Date.now()}`,
        type: "error",
        message: `GPU ${gpu.id} memory critical: ${memoryPercent.toFixed(1)}%`,
      });
    } else if (memoryPercent >= 85) {
      alerts.push({
        id: `gpu-memory-${gpu.id}-${Date.now()}`,
        type: "warning",
        message: `GPU ${gpu.id} memory high: ${memoryPercent.toFixed(1)}%`,
      });
    }

    // GPU temperature alerts (80°C warning, 90°C critical)
    if (gpu.temperature_c && gpu.temperature_c >= 90) {
      alerts.push({
        id: `gpu-temp-${gpu.id}-${Date.now()}`,
        type: "error",
        message: `GPU ${gpu.id} temperature critical: ${gpu.temperature_c}°C`,
      });
    } else if (gpu.temperature_c && gpu.temperature_c >= 80) {
      alerts.push({
        id: `gpu-temp-${gpu.id}-${Date.now()}`,
        type: "warning",
        message: `GPU ${gpu.id} temperature high: ${gpu.temperature_c}°C`,
      });
    }
  });

  // CPU alerts (85% warning, 95% critical)
  if (metrics.cpu_percent >= 95) {
    alerts.push({
      id: `cpu-${Date.now()}`,
      type: "error",
      message: `CPU usage critical: ${metrics.cpu_percent.toFixed(1)}%`,
    });
  } else if (metrics.cpu_percent >= 85) {
    alerts.push({
      id: `cpu-${Date.now()}`,
      type: "warning",
      message: `CPU usage high: ${metrics.cpu_percent.toFixed(1)}%`,
    });
  }

  // RAM alerts (85% warning, 95% critical)
  if (metrics.memory_percent >= 95) {
    alerts.push({
      id: `ram-${Date.now()}`,
      type: "error",
      message: `RAM usage critical: ${metrics.memory_percent.toFixed(1)}%`,
    });
  } else if (metrics.memory_percent >= 85) {
    alerts.push({
      id: `ram-${Date.now()}`,
      type: "warning",
      message: `RAM usage high: ${metrics.memory_percent.toFixed(1)}%`,
    });
  }

  return alerts;
}

export function useSystemMetrics(
  options: UseSystemMetricsOptions = {}
): UseSystemMetricsReturn {
  const { enabled = false, interval = 1, historySize = 60 } = options;

  const [current, setCurrent] = useState<SystemMetrics | null>(null);
  const [history, setHistory] = useState<SystemMetrics[]>([]);
  const [alerts, setAlerts] = useState<Alert[]>([]);
  const [isConnected, setIsConnected] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const eventSourceRef = useRef<EventSource | null>(null);

  useEffect(() => {
    if (!enabled) {
      // Cleanup if monitoring disabled
      if (eventSourceRef.current) {
        eventSourceRef.current.close();
        eventSourceRef.current = null;
      }
      setIsConnected(false);
      return;
    }

    // Create SSE connection
    try {
      const eventSource = apiClient.createMonitoringStream();
      eventSourceRef.current = eventSource;

      eventSource.onopen = () => {
        setIsConnected(true);
        setError(null);
      };

      eventSource.onmessage = (event) => {
        try {
          const rawData = JSON.parse(event.data);

          // Transform backend format to SystemMetrics format
          // Backend sends: { timestamp, system: {cpu_percent, ram_percent}, gpus: [...], active_jobs, queued_jobs }
          // We need: { timestamp, cpu_percent, memory_percent, gpus, active_jobs, queued_jobs }
          const metrics: SystemMetrics = {
            timestamp: rawData.timestamp,
            cpu_percent: rawData.system?.cpu_percent ?? 0,
            memory_percent: rawData.system?.ram_percent ?? 0,
            gpus: rawData.gpus,
            active_jobs: rawData.active_jobs ?? 0,
            queued_jobs: rawData.queued_jobs ?? 0,
          };

          // Update current metrics
          setCurrent(metrics);

          // Update history buffer (keep last historySize entries)
          setHistory((prev) => {
            const newHistory = [...prev, metrics];
            return newHistory.slice(-historySize);
          });

          // Detect and update alerts
          const newAlerts = detectAlerts(metrics);
          setAlerts(newAlerts);
        } catch (err) {
          console.error("Failed to parse metrics:", err);
          setError("Failed to parse metrics data");
        }
      };

      eventSource.onerror = (err) => {
        console.error("SSE connection error:", err);
        setIsConnected(false);
        setError("Connection lost. Reconnecting...");

        // EventSource will automatically try to reconnect
      };

      return () => {
        eventSource.close();
      };
    } catch (err) {
      setError("Failed to connect to monitoring stream");
      console.error("Failed to create EventSource:", err);
    }
  }, [enabled, interval, historySize]);

  return {
    current,
    history,
    alerts,
    isConnected,
    error,
  };
}
