"use client";

import { useState } from "react";
import { SystemMetrics, Alert } from "@/lib/types";
import { AlertBanner } from "./AlertBanner";
import { MetricsTimeline } from "./MetricsTimeline";
import { Cpu, MemoryStick, Thermometer, Activity, Download } from "lucide-react";

interface SystemMonitorProps {
  current: SystemMetrics | null;
  history: SystemMetrics[];
  alerts: Alert[];
  isConnected: boolean;
}

export function SystemMonitor({
  current,
  history,
  alerts,
  isConnected,
}: SystemMonitorProps) {
  const [selectedMetric, setSelectedMetric] = useState<
    "gpu_memory" | "gpu_temp" | "cpu" | "ram"
  >("gpu_memory");
  const [selectedGpu, setSelectedGpu] = useState(0);

  if (!current) {
    return (
      <div className="p-6 text-center text-gray-500">
        <Activity className="w-8 h-8 mx-auto mb-2 animate-pulse" />
        <p>Loading metrics...</p>
      </div>
    );
  }

  const handleExportMetrics = () => {
    const exportData = {
      timestamp: new Date().toISOString(),
      current_metrics: current,
      history: history,
      alerts: alerts,
      summary: {
        total_gpus: current.gpus.length,
        avg_cpu: (
          history.reduce((sum, m) => sum + m.cpu_percent, 0) / history.length
        ).toFixed(1),
        avg_ram: (
          history.reduce((sum, m) => sum + m.ram_percent, 0) / history.length
        ).toFixed(1),
      },
    };

    const blob = new Blob([JSON.stringify(exportData, null, 2)], {
      type: "application/json",
    });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `system-metrics-${Date.now()}.json`;
    a.click();
    URL.revokeObjectURL(url);
  };

  return (
    <div className="space-y-4">
      {/* Connection status */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <div
            className={`w-2 h-2 rounded-full ${
              isConnected ? "bg-green-500" : "bg-red-500"
            }`}
          />
          <span className="text-sm text-gray-400">
            {isConnected ? "Connected" : "Disconnected"}
          </span>
        </div>
        <button
          onClick={handleExportMetrics}
          className="flex items-center gap-1 px-3 py-1 text-xs bg-gray-700 hover:bg-gray-600 rounded transition-colors"
        >
          <Download className="w-3 h-3" />
          Export
        </button>
      </div>

      {/* Alerts */}
      <AlertBanner alerts={alerts} />

      {/* GPU Cards */}
      <div className="space-y-3">
        <h3 className="text-sm font-semibold text-gray-300">GPU Metrics</h3>
        {current.gpus.map((gpu) => (
          <div
            key={gpu.id}
            className="bg-gray-800 rounded-lg p-4 border border-gray-700"
          >
            <div className="flex items-center justify-between mb-3">
              <div>
                <h4 className="font-medium text-sm">GPU {gpu.id}</h4>
                <p className="text-xs text-gray-400">{gpu.name}</p>
              </div>
              <div className="flex items-center gap-1 text-sm">
                <Thermometer className="w-4 h-4 text-orange-400" />
                <span>{gpu.temperature_c}°C</span>
              </div>
            </div>

            {/* Memory bar */}
            <div className="space-y-1 mb-2">
              <div className="flex justify-between text-xs">
                <span className="text-gray-400">Memory</span>
                <span>
                  {gpu.memory_used_mb.toFixed(0)} / {gpu.memory_total_mb.toFixed(0)}{" "}
                  MB
                </span>
              </div>
              <div className="w-full bg-gray-700 rounded-full h-2 overflow-hidden">
                <div
                  className={`h-full transition-all duration-300 ${
                    gpu.memory_percent >= 0.95
                      ? "bg-red-500"
                      : gpu.memory_percent >= 0.85
                      ? "bg-yellow-500"
                      : "bg-blue-500"
                  }`}
                  style={{ width: `${gpu.memory_percent * 100}%` }}
                />
              </div>
              <div className="text-right text-xs text-gray-400">
                {(gpu.memory_percent * 100).toFixed(1)}%
              </div>
            </div>

            {/* Utilization bar */}
            <div className="space-y-1">
              <div className="flex justify-between text-xs">
                <span className="text-gray-400">Utilization</span>
                <span>{gpu.utilization_percent}%</span>
              </div>
              <div className="w-full bg-gray-700 rounded-full h-2 overflow-hidden">
                <div
                  className="h-full bg-purple-500 transition-all duration-300"
                  style={{ width: `${gpu.utilization_percent}%` }}
                />
              </div>
            </div>
          </div>
        ))}
      </div>

      {/* CPU & RAM */}
      <div className="grid grid-cols-2 gap-3">
        <div className="bg-gray-800 rounded-lg p-4 border border-gray-700">
          <div className="flex items-center gap-2 mb-2">
            <Cpu className="w-4 h-4 text-blue-400" />
            <span className="text-sm font-medium">CPU</span>
          </div>
          <div className="text-2xl font-bold">{current.cpu_percent.toFixed(1)}%</div>
          <div className="w-full bg-gray-700 rounded-full h-1.5 mt-2">
            <div
              className="h-full bg-blue-500 transition-all duration-300"
              style={{ width: `${current.cpu_percent}%` }}
            />
          </div>
        </div>

        <div className="bg-gray-800 rounded-lg p-4 border border-gray-700">
          <div className="flex items-center gap-2 mb-2">
            <MemoryStick className="w-4 h-4 text-green-400" />
            <span className="text-sm font-medium">RAM</span>
          </div>
          <div className="text-2xl font-bold">{current.ram_percent.toFixed(1)}%</div>
          <div className="text-xs text-gray-400 mt-1">
            {current.ram_used_gb.toFixed(1)} / {current.ram_total_gb.toFixed(1)} GB
          </div>
          <div className="w-full bg-gray-700 rounded-full h-1.5 mt-2">
            <div
              className="h-full bg-green-500 transition-all duration-300"
              style={{ width: `${current.ram_percent}%` }}
            />
          </div>
        </div>
      </div>

      {/* Queue Stats */}
      {current.queue && (
        <div className="bg-gray-800 rounded-lg p-4 border border-gray-700">
          <h3 className="text-sm font-semibold text-gray-300 mb-3">Queue Status</h3>
          <div className="grid grid-cols-5 gap-2 text-xs">
            <div>
              <div className="text-gray-400">Queued</div>
              <div className="text-lg font-semibold">{current.queue.queued}</div>
            </div>
            <div>
              <div className="text-gray-400">Processing</div>
              <div className="text-lg font-semibold text-blue-400">
                {current.queue.processing}
              </div>
            </div>
            <div>
              <div className="text-gray-400">Completed</div>
              <div className="text-lg font-semibold text-green-400">
                {current.queue.completed}
              </div>
            </div>
            <div>
              <div className="text-gray-400">Failed</div>
              <div className="text-lg font-semibold text-red-400">
                {current.queue.failed}
              </div>
            </div>
            <div>
              <div className="text-gray-400">Cancelled</div>
              <div className="text-lg font-semibold text-gray-400">
                {current.queue.cancelled}
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Active Model Info */}
      {current.active_model && (
        <div className="bg-gray-800 rounded-lg p-4 border border-gray-700">
          <h3 className="text-sm font-semibold text-gray-300 mb-2">Active Model</h3>
          <div className="text-sm">
            <div className="text-gray-400">Model ID:</div>
            <div className="font-mono text-xs">{current.active_model.model_id}</div>
          </div>
          <div className="grid grid-cols-2 gap-2 mt-2 text-xs">
            <div>
              <div className="text-gray-400">Load Time</div>
              <div>{current.active_model.load_time_seconds.toFixed(1)}s</div>
            </div>
            <div>
              <div className="text-gray-400">Memory</div>
              <div>{current.active_model.memory_footprint_gb.toFixed(2)} GB</div>
            </div>
          </div>
        </div>
      )}

      {/* Timeline Chart */}
      <div className="bg-gray-800 rounded-lg p-4 border border-gray-700">
        <div className="flex items-center justify-between mb-3">
          <h3 className="text-sm font-semibold text-gray-300">Timeline (60s)</h3>
          <div className="flex gap-2">
            <select
              value={selectedMetric}
              onChange={(e) =>
                setSelectedMetric(
                  e.target.value as "gpu_memory" | "gpu_temp" | "cpu" | "ram"
                )
              }
              className="text-xs bg-gray-700 border border-gray-600 rounded px-2 py-1"
            >
              <option value="gpu_memory">GPU Memory</option>
              <option value="gpu_temp">GPU Temp</option>
              <option value="cpu">CPU</option>
              <option value="ram">RAM</option>
            </select>
            {selectedMetric.startsWith("gpu") && current.gpus.length > 1 && (
              <select
                value={selectedGpu}
                onChange={(e) => setSelectedGpu(Number(e.target.value))}
                className="text-xs bg-gray-700 border border-gray-600 rounded px-2 py-1"
              >
                {current.gpus.map((gpu) => (
                  <option key={gpu.id} value={gpu.id}>
                    GPU {gpu.id}
                  </option>
                ))}
              </select>
            )}
          </div>
        </div>
        <MetricsTimeline
          history={history}
          metricType={selectedMetric}
          gpuId={selectedGpu}
        />
      </div>
    </div>
  );
}
