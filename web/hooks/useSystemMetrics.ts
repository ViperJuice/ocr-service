import { useState, useEffect, useCallback, useRef } from "react";
import { apiClient } from "@/lib/api-client";
import { SystemMetrics, Alert, AlertType, AlertMetric } from "@/lib/types";

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
  metrics.gpus.forEach((gpu) => {
    if (gpu.memory_percent >= 0.95) {
      alerts.push({
        type: "critical",
        metric: "gpu_memory",
        message: `GPU ${gpu.id} memory critical: ${(gpu.memory_percent * 100).toFixed(1)}%`,
        value: gpu.memory_percent * 100,
        gpuId: gpu.id,
      });
    } else if (gpu.memory_percent >= 0.85) {
      alerts.push({
        type: "warning",
        metric: "gpu_memory",
        message: `GPU ${gpu.id} memory high: ${(gpu.memory_percent * 100).toFixed(1)}%`,
        value: gpu.memory_percent * 100,
        gpuId: gpu.id,
      });
    }

    // GPU temperature alerts (80°C warning, 90°C critical)
    if (gpu.temperature_c >= 90) {
      alerts.push({
        type: "critical",
        metric: "gpu_temperature",
        message: `GPU ${gpu.id} temperature critical: ${gpu.temperature_c}°C`,
        value: gpu.temperature_c,
        gpuId: gpu.id,
      });
    } else if (gpu.temperature_c >= 80) {
      alerts.push({
        type: "warning",
        metric: "gpu_temperature",
        message: `GPU ${gpu.id} temperature high: ${gpu.temperature_c}°C`,
        value: gpu.temperature_c,
        gpuId: gpu.id,
      });
    }
  });

  // CPU alerts (85% warning, 95% critical)
  if (metrics.cpu_percent >= 95) {
    alerts.push({
      type: "critical",
      metric: "cpu",
      message: `CPU usage critical: ${metrics.cpu_percent.toFixed(1)}%`,
      value: metrics.cpu_percent,
    });
  } else if (metrics.cpu_percent >= 85) {
    alerts.push({
      type: "warning",
      metric: "cpu",
      message: `CPU usage high: ${metrics.cpu_percent.toFixed(1)}%`,
      value: metrics.cpu_percent,
    });
  }

  // RAM alerts (85% warning, 95% critical)
  if (metrics.ram_percent >= 95) {
    alerts.push({
      type: "critical",
      metric: "ram",
      message: `RAM usage critical: ${metrics.ram_percent.toFixed(1)}%`,
      value: metrics.ram_percent,
    });
  } else if (metrics.ram_percent >= 85) {
    alerts.push({
      type: "warning",
      metric: "ram",
      message: `RAM usage high: ${metrics.ram_percent.toFixed(1)}%`,
      value: metrics.ram_percent,
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
      const eventSource = apiClient.createSystemMetricsStream(interval);
      eventSourceRef.current = eventSource;

      eventSource.onopen = () => {
        setIsConnected(true);
        setError(null);
      };

      eventSource.onmessage = (event) => {
        try {
          const metrics: SystemMetrics = JSON.parse(event.data);

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
