"use client";

import { SystemMetrics } from "@/lib/types";
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
  ReferenceLine,
} from "recharts";

interface MetricsTimelineProps {
  history: SystemMetrics[];
  metricType: "gpu_memory" | "gpu_temp" | "cpu" | "ram";
  gpuId?: number;
}

export function MetricsTimeline({
  history,
  metricType,
  gpuId = 0,
}: MetricsTimelineProps) {
  if (history.length === 0) {
    return (
      <div className="h-[200px] flex items-center justify-center text-gray-500 text-sm">
        Waiting for data...
      </div>
    );
  }

  // Transform data for recharts
  const data = history.map((metrics, index) => {
    const point: any = {
      index,
      timestamp: new Date(metrics.timestamp).toLocaleTimeString(),
    };

    switch (metricType) {
      case "gpu_memory":
        if (metrics.gpus[gpuId]) {
          point.value = (metrics.gpus[gpuId].memory_percent * 100).toFixed(1);
        }
        break;
      case "gpu_temp":
        if (metrics.gpus[gpuId]) {
          point.value = metrics.gpus[gpuId].temperature_c;
        }
        break;
      case "cpu":
        point.value = metrics.cpu_percent.toFixed(1);
        break;
      case "ram":
        point.value = metrics.ram_percent.toFixed(1);
        break;
    }

    return point;
  });

  // Filter out entries without values
  const filteredData = data.filter((d) => d.value !== undefined);

  if (filteredData.length === 0) {
    return (
      <div className="h-[200px] flex items-center justify-center text-gray-500 text-sm">
        No data available for this metric
      </div>
    );
  }

  // Configuration based on metric type
  const config: Record<
    string,
    { label: string; unit: string; color: string; thresholds?: number[] }
  > = {
    gpu_memory: {
      label: `GPU ${gpuId} Memory`,
      unit: "%",
      color: "#8B5CF6",
      thresholds: [85, 95],
    },
    gpu_temp: {
      label: `GPU ${gpuId} Temperature`,
      unit: "°C",
      color: "#EF4444",
      thresholds: [80, 90],
    },
    cpu: { label: "CPU Usage", unit: "%", color: "#3B82F6", thresholds: [85, 95] },
    ram: { label: "RAM Usage", unit: "%", color: "#10B981", thresholds: [85, 95] },
  };

  const { label, unit, color, thresholds } = config[metricType];

  return (
    <div className="w-full h-[200px]">
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={filteredData} margin={{ top: 5, right: 20, bottom: 5, left: 0 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#374151" />
          <XAxis
            dataKey="timestamp"
            stroke="#9CA3AF"
            fontSize={10}
            interval="preserveStartEnd"
          />
          <YAxis
            stroke="#9CA3AF"
            fontSize={12}
            domain={[0, metricType.includes("temp") ? 100 : 100]}
          />
          <Tooltip
            contentStyle={{
              backgroundColor: "#1F2937",
              border: "1px solid #374151",
              borderRadius: "6px",
            }}
            labelStyle={{ color: "#F3F4F6" }}
            formatter={(value: any) => [`${value}${unit}`, label]}
          />
          <Legend />

          {/* Threshold lines */}
          {thresholds &&
            thresholds.map((threshold, i) => (
              <ReferenceLine
                key={threshold}
                y={threshold}
                stroke={i === 0 ? "#F59E0B" : "#EF4444"}
                strokeDasharray="3 3"
                strokeOpacity={0.5}
              />
            ))}

          <Line
            type="monotone"
            dataKey="value"
            stroke={color}
            strokeWidth={2}
            dot={false}
            name={label}
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
