# System Monitoring Frontend Specification

## Document Information
- **Version**: 1.0.0
- **Date**: 2025-01-09
- **Author**: Frontend Architecture
- **Status**: Ready for Implementation

## Table of Contents
1. [Overview](#overview)
2. [Prerequisites](#prerequisites)
3. [Architecture](#architecture)
4. [Type Definitions](#type-definitions)
5. [API Client](#api-client)
6. [Hooks](#hooks)
7. [Components](#components)
8. [Integration](#integration)
9. [Styling](#styling)
10. [Testing](#testing)
11. [Accessibility](#accessibility)
12. [Common Pitfalls](#common-pitfalls)

---

## Overview

### Purpose
Build a collapsible system monitoring dashboard that displays real-time GPU, CPU, RAM metrics, queue statistics, and model information with 60-second scrollable timeline graphs.

### Goals
- Real-time metrics via SSE with 1-second updates
- Collapsible sidebar widget (collapsed: badge, expanded: full dashboard)
- Timeline graphs for last 60 seconds of data
- Alert system (yellow at 85%, red at 95%)
- Export metrics functionality
- Settings modal integration
- Dark theme consistency

### Tech Stack
- **Framework**: Next.js 14+ (App Router)
- **Language**: TypeScript
- **Styling**: TailwindCSS
- **State**: TanStack React Query + useState
- **Animations**: Framer Motion (already installed)
- **Charts**: Recharts (needs installation)
- **Icons**: Lucide React (already installed)

---

## Prerequisites

### Required Knowledge
- React 19 functional components and hooks
- TypeScript interfaces and generics
- TanStack React Query (useQuery, useMutation)
- Server-Sent Events (EventSource API)
- Tailwind CSS utility classes
- Framer Motion animations

### Existing Files to Understand
1. `/home/jenner/code/ocr-service/web/lib/api-client.ts` - API patterns
2. `/home/jenner/code/ocr-service/web/lib/types.ts` - Type definitions
3. `/home/jenner/code/ocr-service/web/hooks/useOcrJob.ts` - Hook patterns
4. `/home/jenner/code/ocr-service/web/components/ProgressMonitor.tsx` - Existing monitoring
5. `/home/jenner/code/ocr-service/web/app/page.tsx` - Main layout
6. `/home/jenner/code/ocr-service/web/app/globals.css` - Styling patterns

### Dependencies
**Already Installed**:
- `next@^16.0.1`
- `react@^19.2.0`
- `@tanstack/react-query@^5.90.7`
- `framer-motion@^12.23.24`
- `lucide-react@^0.553.0`
- `zustand@^5.0.8`

**To Install**:
- `recharts` - Lightweight charting library

---

## Architecture

### Component Hierarchy
```
<SystemMonitorWidget enabled={boolean}>
  └─ (Collapsed State)
     <motion.button> (floating badge)
       └─ GPU: 75% + alert indicator

  └─ (Expanded State)
     <motion.div> (sidebar)
       └─ <SystemMonitor>
            ├─ <AlertBanner alerts={Alert[]} />
            ├─ GPU Cards (per GPU)
            │  ├─ Digital readouts
            │  ├─ Progress bars
            │  └─ Metrics
            ├─ <MetricsTimeline metric="gpu_memory" />
            ├─ CPU/RAM Card
            ├─ Queue Status Card
            ├─ Active Model Card
            ├─ DeepSeek Params Card
            └─ Export Button
```

### Data Flow
```
1. User enables monitoring in settings
2. <SystemMonitorWidget enabled={true}>
3. useSystemMetrics(true) hook activated
4. EventSource connects to /api/monitoring/system/stream
5. SSE messages received every 1 second
6. Hook updates state: current metrics + history buffer
7. Alert detection runs on new metrics
8. Components re-render with new data
9. Timeline graph animates new data points
10. User can export metrics as JSON
```

### State Management
```typescript
// Local component state (useState)
- isExpanded: boolean (widget collapsed/expanded)
- selectedMetric: 'gpu_memory' | 'gpu_temp' | 'cpu' | 'ram'
- showSettings: boolean

// Hook state (useSystemMetrics)
- current: SystemMetrics | null (latest snapshot)
- history: SystemMetrics[] (last 60 seconds)
- alerts: Alert[] (detected warnings/criticals)
- isConnected: boolean (SSE connection status)

// Global state (React Query cache)
- System metrics (fallback polling)
```

---

## Type Definitions

### File: `/home/jenner/code/ocr-service/web/lib/types.ts`

**Location**: Add after existing `MonitoringMetrics` interface (line 130)

**Code**:
```typescript
// GPU Metrics (per device)
export interface GpuMetrics {
  id: number;
  name: string;
  memory_used_mb: number;
  memory_total_mb: number;
  memory_percent: number;
  utilization_percent: number;
  temperature_c: number;
}

// Job Queue Statistics
export interface QueueStats {
  queued: number;
  processing: number;
  completed: number;
  failed: number;
  cancelled: number;
}

// Active Model Information
export interface ActiveModelInfo {
  model_id: string;
  load_time_seconds: number;
  memory_footprint_gb: number;
}

// DeepSeek OCR Parameters
export interface DeepSeekParams {
  dpi: number;
  resolution_mode: string;
  image_width: number;
  image_height: number;
}

// Complete System Metrics Snapshot
export interface SystemMetrics {
  timestamp: string;
  cpu_percent: number;
  ram_used_gb: number;
  ram_total_gb: number;
  ram_percent: number;
  gpus: GpuMetrics[];
  queue: QueueStats;
  active_model?: ActiveModelInfo;
  deepseek_params?: DeepSeekParams;
}

// System Metrics History Response
export interface SystemMetricsHistory {
  metrics: SystemMetrics[];
  time_range: {
    start: string | null;
    end: string | null;
    duration_seconds: number;
  };
}

// Alert Types
export type AlertType = 'warning' | 'critical';
export type AlertMetric = 'gpu_memory' | 'gpu_temp' | 'cpu' | 'ram';

export interface Alert {
  id: string;
  type: AlertType;
  metric: AlertMetric;
  message: string;
  value: number;
  gpu_id?: number;
  timestamp: string;
}

// Alert Thresholds
export interface AlertThresholds {
  gpu_memory_warning: number;
  gpu_memory_critical: number;
  gpu_temp_warning: number;
  gpu_temp_critical: number;
}
```

---

## API Client

### File: `/home/jenner/code/ocr-service/web/lib/api-client.ts`

**Location**: Add after existing monitoring methods (line 163)

**Code**:
```typescript
// System-wide monitoring methods
async getSystemMetrics(): Promise<SystemMetrics> {
  const res = await fetch(`${this.baseUrl}/api/monitoring/system/current`);
  if (!res.ok) {
    throw new ApiError('Failed to fetch system metrics', res.status);
  }
  return res.json();
},

async getSystemMetricsHistory(seconds: number = 60): Promise<SystemMetricsHistory> {
  const res = await fetch(
    `${this.baseUrl}/api/monitoring/system/history?seconds=${seconds}`
  );
  if (!res.ok) {
    throw new ApiError('Failed to fetch system metrics history', res.status);
  }
  return res.json();
},

createSystemMetricsStream(intervalSeconds: number = 1): EventSource {
  const url = `${this.baseUrl}/api/monitoring/system/stream?interval=${intervalSeconds}`;
  return new EventSource(url);
},
```

**Update Imports** (top of file):
```typescript
import type {
  // ... existing imports ...
  SystemMetrics,
  SystemMetricsHistory,
} from './types';
```

---

## Hooks

### File: `/home/jenner/code/ocr-service/web/hooks/useSystemMetrics.ts` (NEW)

**Purpose**: Manage SSE connection, metrics state, and alert detection

**Complete Implementation**:
```typescript
'use client';

import { useState, useEffect, useMemo } from 'react';
import { useQuery } from '@tanstack/react-query';
import { apiClient } from '@/lib/api-client';
import type { SystemMetrics, Alert, AlertType, AlertMetric } from '@/lib/types';

interface UseSystemMetricsOptions {
  enabled?: boolean;
  interval?: number;
}

interface UseSystemMetricsReturn {
  current: SystemMetrics | null;
  history: SystemMetrics[];
  alerts: Alert[];
  isConnected: boolean;
  isLoading: boolean;
  error: Error | null;
}

export function useSystemMetrics(
  options: UseSystemMetricsOptions = {}
): UseSystemMetricsReturn {
  const { enabled = true, interval = 1 } = options;

  const [liveMetrics, setLiveMetrics] = useState<SystemMetrics | null>(null);
  const [history, setHistory] = useState<SystemMetrics[]>([]);
  const [isConnected, setIsConnected] = useState(false);
  const [error, setError] = useState<Error | null>(null);

  // Fallback polling (if SSE not connected or fails)
  const { data: polledMetrics, isLoading } = useQuery({
    queryKey: ['system-metrics'],
    queryFn: () => apiClient.getSystemMetrics(),
    enabled: enabled && !isConnected,
    refetchInterval: 5000, // Poll every 5 seconds as fallback
    retry: 3,
  });

  // SSE real-time stream
  useEffect(() => {
    if (!enabled) {
      setIsConnected(false);
      setLiveMetrics(null);
      setHistory([]);
      return;
    }

    let eventSource: EventSource | null = null;

    try {
      eventSource = apiClient.createSystemMetricsStream(interval);

      eventSource.onopen = () => {
        console.log('System metrics SSE connected');
        setIsConnected(true);
        setError(null);
      };

      eventSource.onmessage = (event) => {
        try {
          const metrics: SystemMetrics = JSON.parse(event.data);
          setLiveMetrics(metrics);
          setHistory((prev) => {
            const updated = [...prev, metrics];
            // Keep only last 60 entries
            return updated.slice(-60);
          });
        } catch (err) {
          console.error('Failed to parse SSE message:', err);
        }
      };

      eventSource.onerror = (err) => {
        console.error('SSE connection error:', err);
        setIsConnected(false);
        setError(new Error('SSE connection failed'));
        eventSource?.close();
      };
    } catch (err) {
      console.error('Failed to create SSE connection:', err);
      setError(err as Error);
    }

    // Cleanup
    return () => {
      if (eventSource) {
        console.log('Closing system metrics SSE connection');
        eventSource.close();
        setIsConnected(false);
      }
    };
  }, [enabled, interval]);

  // Detect alerts from current metrics
  const alerts = useMemo(() => {
    const currentMetrics = liveMetrics || polledMetrics;
    if (!currentMetrics) return [];

    return detectAlerts(currentMetrics);
  }, [liveMetrics, polledMetrics]);

  return {
    current: liveMetrics || polledMetrics || null,
    history,
    alerts,
    isConnected,
    isLoading: !isConnected && isLoading,
    error,
  };
}

// Alert Detection Logic
function detectAlerts(metrics: SystemMetrics): Alert[] {
  const alerts: Alert[] = [];

  // GPU alerts
  metrics.gpus.forEach((gpu) => {
    // Memory alerts
    if (gpu.memory_percent > 0.95) {
      alerts.push({
        id: `gpu${gpu.id}-mem-crit-${Date.now()}`,
        type: 'critical',
        metric: 'gpu_memory',
        message: `GPU ${gpu.id} memory critical`,
        value: gpu.memory_percent,
        gpu_id: gpu.id,
        timestamp: metrics.timestamp,
      });
    } else if (gpu.memory_percent > 0.85) {
      alerts.push({
        id: `gpu${gpu.id}-mem-warn-${Date.now()}`,
        type: 'warning',
        metric: 'gpu_memory',
        message: `GPU ${gpu.id} memory high`,
        value: gpu.memory_percent,
        gpu_id: gpu.id,
        timestamp: metrics.timestamp,
      });
    }

    // Temperature alerts
    if (gpu.temperature_c > 90) {
      alerts.push({
        id: `gpu${gpu.id}-temp-crit-${Date.now()}`,
        type: 'critical',
        metric: 'gpu_temp',
        message: `GPU ${gpu.id} temperature critical`,
        value: gpu.temperature_c,
        gpu_id: gpu.id,
        timestamp: metrics.timestamp,
      });
    } else if (gpu.temperature_c > 80) {
      alerts.push({
        id: `gpu${gpu.id}-temp-warn-${Date.now()}`,
        type: 'warning',
        metric: 'gpu_temp',
        message: `GPU ${gpu.id} temperature high`,
        value: gpu.temperature_c,
        gpu_id: gpu.id,
        timestamp: metrics.timestamp,
      });
    }
  });

  // CPU alert (optional, >90%)
  if (metrics.cpu_percent > 90) {
    alerts.push({
      id: `cpu-warn-${Date.now()}`,
      type: 'warning',
      metric: 'cpu',
      message: 'CPU usage very high',
      value: metrics.cpu_percent,
      timestamp: metrics.timestamp,
    });
  }

  // RAM alert (optional, >90%)
  if (metrics.ram_percent > 90) {
    alerts.push({
      id: `ram-warn-${Date.now()}`,
      type: 'warning',
      metric: 'ram',
      message: 'RAM usage very high',
      value: metrics.ram_percent,
      timestamp: metrics.timestamp,
    });
  }

  return alerts;
}
```

---

## Components

### Component 1: AlertBanner

**File**: `/home/jenner/code/ocr-service/web/components/AlertBanner.tsx` (NEW)

**Purpose**: Display warning and critical alerts with color coding

**Implementation**:
```typescript
'use client';

import type { Alert } from '@/lib/types';

interface AlertBannerProps {
  alerts: Alert[];
}

export function AlertBanner({ alerts }: AlertBannerProps) {
  if (alerts.length === 0) return null;

  const critical = alerts.filter((a) => a.type === 'critical');
  const warnings = alerts.filter((a) => a.type === 'warning');

  return (
    <div className="space-y-2">
      {/* Critical Alerts */}
      {critical.map((alert) => (
        <div
          key={alert.id}
          className="bg-red-500/10 border border-red-500 rounded-lg p-3 flex items-center gap-3 animate-pulse"
        >
          <span className="text-red-500 text-xl">⚠️</span>
          <div className="flex-1">
            <p className="text-sm font-medium text-red-300">{alert.message}</p>
            <p className="text-xs text-red-400/80">
              {formatAlertValue(alert)}
            </p>
          </div>
        </div>
      ))}

      {/* Warning Alerts */}
      {warnings.map((alert) => (
        <div
          key={alert.id}
          className="bg-yellow-500/10 border border-yellow-500/50 rounded-lg p-3 flex items-center gap-3"
        >
          <span className="text-yellow-500 text-xl">⚠️</span>
          <div className="flex-1">
            <p className="text-sm font-medium text-yellow-300">{alert.message}</p>
            <p className="text-xs text-yellow-400/80">
              {formatAlertValue(alert)}
            </p>
          </div>
        </div>
      ))}
    </div>
  );
}

function formatAlertValue(alert: Alert): string {
  switch (alert.metric) {
    case 'gpu_memory':
      return `${(alert.value * 100).toFixed(1)}% memory used`;
    case 'gpu_temp':
      return `${alert.value}°C`;
    case 'cpu':
      return `${alert.value.toFixed(1)}% CPU usage`;
    case 'ram':
      return `${alert.value.toFixed(1)}% RAM usage`;
    default:
      return String(alert.value);
  }
}
```

---

### Component 2: MetricsTimeline

**File**: `/home/jenner/code/ocr-service/web/components/MetricsTimeline.tsx` (NEW)

**Purpose**: Recharts-based timeline graph for 60-second metrics

**Implementation**:
```typescript
'use client';

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
} from 'recharts';
import type { SystemMetrics } from '@/lib/types';

type MetricType = 'gpu_memory' | 'gpu_temp' | 'cpu' | 'ram';

interface MetricsTimelineProps {
  data: SystemMetrics[];
  metric: MetricType;
  height?: number;
}

export function MetricsTimeline({
  data,
  metric,
  height = 200,
}: MetricsTimelineProps) {
  // Transform data for charting
  const chartData = data.map((m) => {
    const time = new Date(m.timestamp).toLocaleTimeString('en-US', {
      hour12: false,
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
    });

    return {
      time,
      ...getMetricValues(m, metric),
    };
  });

  if (chartData.length === 0) {
    return (
      <div
        className="flex items-center justify-center text-gray-500"
        style={{ height }}
      >
        <p className="text-sm">No data available</p>
      </div>
    );
  }

  const showThresholds = metric === 'gpu_memory' || metric === 'gpu_temp';

  return (
    <ResponsiveContainer width="100%" height={height}>
      <LineChart data={chartData}>
        <CartesianGrid strokeDasharray="3 3" stroke="#374151" />
        <XAxis
          dataKey="time"
          stroke="#9CA3AF"
          tick={{ fill: '#9CA3AF', fontSize: 10 }}
          minTickGap={30}
        />
        <YAxis
          stroke="#9CA3AF"
          tick={{ fill: '#9CA3AF', fontSize: 10 }}
          domain={metric === 'gpu_temp' ? [0, 100] : [0, 100]}
        />
        <Tooltip
          contentStyle={{
            backgroundColor: '#1F2937',
            border: '1px solid #374151',
            borderRadius: '8px',
            color: '#F3F4F6',
          }}
          labelStyle={{ color: '#9CA3AF' }}
        />
        <Legend
          wrapperStyle={{ fontSize: '12px' }}
          iconType="line"
        />

        {/* Threshold lines for GPU metrics */}
        {showThresholds && (
          <>
            <ReferenceLine
              y={85}
              stroke="#F59E0B"
              strokeDasharray="3 3"
              label={{ value: '85%', fill: '#F59E0B', fontSize: 10 }}
            />
            <ReferenceLine
              y={95}
              stroke="#EF4444"
              strokeDasharray="3 3"
              label={{ value: '95%', fill: '#EF4444', fontSize: 10 }}
            />
          </>
        )}

        {/* Data lines */}
        {Object.keys(chartData[0] || {})
          .filter((key) => key !== 'time')
          .map((key, index) => (
            <Line
              key={key}
              type="monotone"
              dataKey={key}
              stroke={getLineColor(index)}
              strokeWidth={2}
              dot={false}
              isAnimationActive={false}
              name={key}
            />
          ))}
      </LineChart>
    </ResponsiveContainer>
  );
}

function getMetricValues(metrics: SystemMetrics, metric: MetricType): Record<string, number> {
  switch (metric) {
    case 'gpu_memory':
      return metrics.gpus.reduce((acc, gpu) => ({
        ...acc,
        [`GPU ${gpu.id}`]: gpu.memory_percent * 100,
      }), {});
    case 'gpu_temp':
      return metrics.gpus.reduce((acc, gpu) => ({
        ...acc,
        [`GPU ${gpu.id}`]: gpu.temperature_c,
      }), {});
    case 'cpu':
      return { CPU: metrics.cpu_percent };
    case 'ram':
      return { RAM: metrics.ram_percent };
    default:
      return {};
  }
}

function getLineColor(index: number): string {
  const colors = ['#10B981', '#3B82F6', '#8B5CF6', '#F59E0B', '#EF4444'];
  return colors[index % colors.length];
}
```

---

### Component 3: SystemMonitor (Main Dashboard)

**File**: `/home/jenner/code/ocr-service/web/components/SystemMonitor.tsx` (NEW)

**Purpose**: Complete monitoring dashboard with all metrics

**Implementation**: (This is a large file - showing key sections)

```typescript
'use client';

import { useState } from 'react';
import { Download, X } from 'lucide-react';
import { AlertBanner } from './AlertBanner';
import { MetricsTimeline } from './MetricsTimeline';
import type { SystemMetrics, Alert } from '@/lib/types';

type MetricType = 'gpu_memory' | 'gpu_temp' | 'cpu' | 'ram';

interface SystemMonitorProps {
  metrics: SystemMetrics | null;
  history: SystemMetrics[];
  alerts: Alert[];
  onClose: () => void;
}

export function SystemMonitor({
  metrics,
  history,
  alerts,
  onClose,
}: SystemMonitorProps) {
  const [selectedMetric, setSelectedMetric] = useState<MetricType>('gpu_memory');

  if (!metrics) {
    return (
      <div className="h-full flex items-center justify-center bg-[#0A0E1A]">
        <div className="text-center">
          <p className="text-gray-400 mb-2">No metrics available</p>
          <p className="text-gray-500 text-sm">Waiting for data...</p>
        </div>
      </div>
    );
  }

  const handleExport = () => {
    const data = {
      exported_at: new Date().toISOString(),
      current: metrics,
      history: history,
      summary: {
        avg_gpu_memory:
          history.reduce((sum, m) => sum + (m.gpus[0]?.memory_percent || 0), 0) /
          history.length || 0,
        max_gpu_temp: Math.max(
          ...history.flatMap((m) => m.gpus.map((g) => g.temperature_c))
        ),
        avg_cpu: history.reduce((sum, m) => sum + m.cpu_percent, 0) / history.length || 0,
      },
    };

    const blob = new Blob([JSON.stringify(data, null, 2)], {
      type: 'application/json',
    });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `system-metrics-${Date.now()}.json`;
    a.click();
    URL.revokeObjectURL(url);
  };

  return (
    <div className="h-full flex flex-col bg-[#0A0E1A] border-l border-gray-800">
      {/* Header */}
      <div className="flex items-center justify-between p-4 border-b border-gray-800">
        <h2 className="text-lg font-semibold text-white">System Monitor</h2>
        <button
          onClick={onClose}
          className="p-2 hover:bg-gray-800 rounded-lg transition-colors"
          aria-label="Close system monitor"
        >
          <X className="w-5 h-5 text-gray-400" />
        </button>
      </div>

      {/* Content */}
      <div className="flex-1 overflow-y-auto p-4 space-y-4">
        {/* Alerts */}
        <AlertBanner alerts={alerts} />

        {/* GPU Cards */}
        {metrics.gpus.map((gpu) => (
          <div
            key={gpu.id}
            className="bg-gray-900/50 rounded-lg p-4 space-y-3 border border-gray-800"
          >
            <h3 className="text-sm font-medium text-gray-300">
              {gpu.name} (GPU {gpu.id})
            </h3>

            {/* Memory */}
            <div>
              <div className="flex justify-between text-sm mb-1">
                <span className="text-gray-400">Memory</span>
                <span className="font-mono text-white">
                  {(gpu.memory_used_mb / 1024).toFixed(1)} /{' '}
                  {(gpu.memory_total_mb / 1024).toFixed(1)} GB (
                  {(gpu.memory_percent * 100).toFixed(1)}%)
                </span>
              </div>
              <div className="h-2 bg-gray-800 rounded-full overflow-hidden">
                <div
                  className={`h-full transition-all ${getMemoryColor(
                    gpu.memory_percent
                  )}`}
                  style={{ width: `${gpu.memory_percent * 100}%` }}
                />
              </div>
            </div>

            {/* Temperature & Utilization */}
            <div className="grid grid-cols-2 gap-4 text-sm">
              <div>
                <span className="text-gray-400 block mb-1">Temperature</span>
                <p
                  className={`font-mono text-lg ${getTempColor(
                    gpu.temperature_c
                  )}`}
                >
                  {gpu.temperature_c}°C
                </p>
              </div>
              <div>
                <span className="text-gray-400 block mb-1">Utilization</span>
                <p className="font-mono text-lg text-white">
                  {gpu.utilization_percent}%
                </p>
              </div>
            </div>
          </div>
        ))}

        {/* CPU & RAM */}
        <div className="bg-gray-900/50 rounded-lg p-4 space-y-3 border border-gray-800">
          <h3 className="text-sm font-medium text-gray-300">System Resources</h3>
          <div className="grid grid-cols-2 gap-4 text-sm">
            <div>
              <span className="text-gray-400 block mb-1">CPU</span>
              <p className="font-mono text-lg text-white">
                {metrics.cpu_percent.toFixed(1)}%
              </p>
            </div>
            <div>
              <span className="text-gray-400 block mb-1">RAM</span>
              <p className="font-mono text-lg text-white">
                {metrics.ram_used_gb.toFixed(1)} / {metrics.ram_total_gb.toFixed(1)}{' '}
                GB
              </p>
              <p className="text-xs text-gray-500 font-mono">
                {metrics.ram_percent.toFixed(1)}%
              </p>
            </div>
          </div>
        </div>

        {/* Queue Status */}
        <div className="bg-gray-900/50 rounded-lg p-4 border border-gray-800">
          <h3 className="text-sm font-medium text-gray-300 mb-3">
            Queue Status
          </h3>
          <div className="grid grid-cols-2 gap-2 text-sm">
            <div className="flex justify-between">
              <span className="text-gray-400">Processing</span>
              <span className="font-mono text-green-400">
                {metrics.queue.processing}
              </span>
            </div>
            <div className="flex justify-between">
              <span className="text-gray-400">Queued</span>
              <span className="font-mono text-yellow-400">
                {metrics.queue.queued}
              </span>
            </div>
            <div className="flex justify-between">
              <span className="text-gray-400">Completed</span>
              <span className="font-mono text-blue-400">
                {metrics.queue.completed}
              </span>
            </div>
            <div className="flex justify-between">
              <span className="text-gray-400">Failed</span>
              <span className="font-mono text-red-400">
                {metrics.queue.failed}
              </span>
            </div>
          </div>
        </div>

        {/* Active Model */}
        {metrics.active_model && (
          <div className="bg-gray-900/50 rounded-lg p-4 border border-gray-800">
            <h3 className="text-sm font-medium text-gray-300 mb-2">
              Active Model
            </h3>
            <p className="text-white font-mono mb-2">
              {metrics.active_model.model_id}
            </p>
            <div className="text-sm text-gray-400 space-y-1">
              <div>
                Load time: {metrics.active_model.load_time_seconds.toFixed(1)}s
              </div>
              <div>
                Memory: {metrics.active_model.memory_footprint_gb.toFixed(2)} GB
              </div>
            </div>
          </div>
        )}

        {/* DeepSeek OCR Params */}
        {metrics.deepseek_params && (
          <div className="bg-gray-900/50 rounded-lg p-4 border border-gray-800">
            <h3 className="text-sm font-medium text-gray-300 mb-2">
              DeepSeek OCR Parameters
            </h3>
            <div className="text-sm text-gray-400 space-y-1">
              <div>DPI: {metrics.deepseek_params.dpi}</div>
              <div>Mode: {metrics.deepseek_params.resolution_mode}</div>
              <div>
                Image: {metrics.deepseek_params.image_width} ×{' '}
                {metrics.deepseek_params.image_height} px
              </div>
            </div>
          </div>
        )}

        {/* Timeline Chart */}
        {history.length > 0 && (
          <div className="bg-gray-900/50 rounded-lg p-4 border border-gray-800">
            <div className="flex items-center justify-between mb-3">
              <h3 className="text-sm font-medium text-gray-300">
                Last 60 Seconds
              </h3>
              <div className="flex gap-2">
                {(['gpu_memory', 'gpu_temp', 'cpu', 'ram'] as const).map(
                  (metric) => (
                    <button
                      key={metric}
                      onClick={() => setSelectedMetric(metric)}
                      className={`px-2 py-1 text-xs rounded transition-colors ${
                        selectedMetric === metric
                          ? 'bg-blue-500 text-white'
                          : 'bg-gray-800 text-gray-400 hover:bg-gray-700'
                      }`}
                    >
                      {metric.toUpperCase().replace('_', ' ')}
                    </button>
                  )
                )}
              </div>
            </div>
            <MetricsTimeline
              data={history}
              metric={selectedMetric}
              height={180}
            />
          </div>
        )}
      </div>

      {/* Footer */}
      <div className="p-4 border-t border-gray-800">
        <button
          onClick={handleExport}
          className="w-full flex items-center justify-center gap-2 px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-lg transition-colors"
        >
          <Download className="w-4 h-4" />
          Export Metrics
        </button>
      </div>
    </div>
  );
}

// Helper Functions
function getMemoryColor(percent: number): string {
  if (percent > 0.95) return 'bg-red-500';
  if (percent > 0.85) return 'bg-yellow-500';
  return 'bg-green-500';
}

function getTempColor(temp: number): string {
  if (temp > 90) return 'text-red-500';
  if (temp > 80) return 'text-yellow-500';
  return 'text-green-500';
}
```

---

### Component 4: SystemMonitorWidget (Collapsible Wrapper)

**File**: `/home/jenner/code/ocr-service/web/components/SystemMonitorWidget.tsx` (NEW)

**Purpose**: Collapsible widget with floating badge and sidebar

**Implementation**:
```typescript
'use client';

import { useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Activity } from 'lucide-react';
import { SystemMonitor } from './SystemMonitor';
import { useSystemMetrics } from '@/hooks/useSystemMetrics';

interface SystemMonitorWidgetProps {
  enabled: boolean;
}

export function SystemMonitorWidget({ enabled }: SystemMonitorWidgetProps) {
  const [isExpanded, setIsExpanded] = useState(false);

  // Only fetch metrics when enabled and expanded (or when enabled for badge)
  const { current, history, alerts, isConnected } = useSystemMetrics({
    enabled: enabled && (isExpanded || true), // Always fetch for badge when enabled
    interval: 1,
  });

  const gpuMemoryPercent = current?.gpus[0]?.memory_percent || 0;
  const hasAlerts = alerts.length > 0;
  const hasCriticalAlerts = alerts.some((a) => a.type === 'critical');

  if (!enabled) return null;

  return (
    <>
      {/* Floating Badge (Collapsed State) */}
      {!isExpanded && (
        <motion.button
          initial={{ opacity: 0, scale: 0.8 }}
          animate={{ opacity: 1, scale: 1 }}
          onClick={() => setIsExpanded(true)}
          className={`fixed top-4 right-4 z-50 px-4 py-2 rounded-lg shadow-lg flex items-center gap-2 transition-colors ${
            hasCriticalAlerts
              ? 'bg-red-500 text-white animate-pulse'
              : gpuMemoryPercent > 0.85
              ? 'bg-yellow-500 text-white'
              : 'bg-gray-800 text-gray-200 hover:bg-gray-700'
          }`}
          aria-label="Open system monitor"
        >
          <Activity className="w-4 h-4" />
          <span className="font-mono text-sm">
            GPU: {(gpuMemoryPercent * 100).toFixed(0)}%
          </span>
          {hasAlerts && (
            <span className="relative flex h-2 w-2">
              <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-white opacity-75" />
              <span className="relative inline-flex rounded-full h-2 w-2 bg-white" />
            </span>
          )}
          {isConnected && (
            <span className="w-2 h-2 rounded-full bg-green-400" title="Connected" />
          )}
        </motion.button>
      )}

      {/* Sidebar (Expanded State) */}
      <AnimatePresence>
        {isExpanded && (
          <>
            {/* Backdrop */}
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              onClick={() => setIsExpanded(false)}
              className="fixed inset-0 bg-black/20 z-40 lg:hidden"
            />

            {/* Sidebar */}
            <motion.div
              initial={{ x: 400 }}
              animate={{ x: 0 }}
              exit={{ x: 400 }}
              transition={{ type: 'spring', damping: 25, stiffness: 200 }}
              className="fixed right-0 top-0 bottom-0 w-full sm:w-96 z-50 shadow-2xl"
            >
              <SystemMonitor
                metrics={current}
                history={history}
                alerts={alerts}
                onClose={() => setIsExpanded(false)}
              />
            </motion.div>
          </>
        )}
      </AnimatePresence>
    </>
  );
}
```

---

### Component 5: SettingsModal

**File**: `/home/jenner/code/ocr-service/web/components/SettingsModal.tsx` (NEW)

**Purpose**: Settings modal with monitoring toggle

**Implementation**:
```typescript
'use client';

import { X } from 'lucide-react';
import { motion, AnimatePresence } from 'framer-motion';

interface SettingsModalProps {
  isOpen: boolean;
  onClose: () => void;
  monitoringEnabled: boolean;
  onToggleMonitoring: (enabled: boolean) => void;
}

export function SettingsModal({
  isOpen,
  onClose,
  monitoringEnabled,
  onToggleMonitoring,
}: SettingsModalProps) {
  return (
    <AnimatePresence>
      {isOpen && (
        <>
          {/* Backdrop */}
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            onClick={onClose}
            className="fixed inset-0 bg-black/50 z-40"
          />

          {/* Modal */}
          <motion.div
            initial={{ opacity: 0, scale: 0.95 }}
            animate={{ opacity: 1, scale: 1 }}
            exit={{ opacity: 0, scale: 0.95 }}
            className="fixed inset-0 flex items-center justify-center z-50 p-4"
          >
            <div className="bg-gray-900 rounded-lg shadow-xl max-w-md w-full p-6 border border-gray-800">
              {/* Header */}
              <div className="flex items-center justify-between mb-6">
                <h2 className="text-xl font-semibold text-white">Settings</h2>
                <button
                  onClick={onClose}
                  className="p-2 hover:bg-gray-800 rounded-lg transition-colors"
                  aria-label="Close settings"
                >
                  <X className="w-5 h-5 text-gray-400" />
                </button>
              </div>

              {/* Content */}
              <div className="space-y-4">
                <label className="flex items-center justify-between p-4 bg-gray-800/50 rounded-lg cursor-pointer hover:bg-gray-800 transition-colors">
                  <div>
                    <p className="text-white font-medium">System Monitoring</p>
                    <p className="text-sm text-gray-400">
                      Enable real-time system metrics dashboard
                    </p>
                  </div>
                  <input
                    type="checkbox"
                    checked={monitoringEnabled}
                    onChange={(e) => onToggleMonitoring(e.target.checked)}
                    className="w-5 h-5 rounded border-gray-600 text-blue-600 focus:ring-blue-500 focus:ring-offset-gray-900"
                  />
                </label>
              </div>
            </div>
          </motion.div>
        </>
      )}
    </AnimatePresence>
  );
}
```

---

## Integration

### Main Page Integration

**File**: `/home/jenner/code/ocr-service/web/app/page.tsx`

**Step 1: Add Imports** (top of file):
```typescript
import { SystemMonitorWidget } from '@/components/SystemMonitorWidget';
import { SettingsModal } from '@/components/SettingsModal';
```

**Step 2: Add State** (around line 30):
```typescript
const [monitoringEnabled, setMonitoringEnabled] = useState(false);
const [showSettings, setShowSettings] = useState(false);
```

**Step 3: Connect Settings Button** (replace existing settings button around line 180):
```typescript
<button
  onClick={() => setShowSettings(true)}
  className="p-2 hover:bg-surface-hover rounded-lg transition-colors"
  aria-label="Settings"
>
  <Settings className="w-5 h-5" />
</button>
```

**Step 4: Add Components** (before closing main div):
```typescript
{/* System Monitor Widget */}
<SystemMonitorWidget enabled={monitoringEnabled} />

{/* Settings Modal */}
<SettingsModal
  isOpen={showSettings}
  onClose={() => setShowSettings(false)}
  monitoringEnabled={monitoringEnabled}
  onToggleMonitoring={setMonitoringEnabled}
/>
```

---

## Styling

### Color Scheme (Already Defined in globals.css)

**Use Existing Colors**:
- Success: `#10B981` (green-500) - Use for normal state
- Warning: `#F59E0B` (yellow-500) - Use for 85-95%
- Error: `#EF4444` (red-500) - Use for >95%
- Background: `#0A0E1A` - Dark background
- Surface: `#1F2937` (gray-800) - Card backgrounds
- Border: `#374151` (gray-700) - Borders

**Tailwind Classes**:
```css
/* Normal State */
.bg-green-500, .text-green-400

/* Warning State */
.bg-yellow-500, .text-yellow-400, .border-yellow-500

/* Critical State */
.bg-red-500, .text-red-400, .border-red-500, .animate-pulse

/* Dark Theme Surfaces */
.bg-gray-900, .bg-gray-800, .border-gray-800, .border-gray-700
```

### Animations (Use Framer Motion)

**Sidebar Slide-in**:
```typescript
<motion.div
  initial={{ x: 400 }}
  animate={{ x: 0 }}
  exit={{ x: 400 }}
  transition={{ type: 'spring', damping: 25, stiffness: 200 }}
>
```

**Badge Fade-in**:
```typescript
<motion.button
  initial={{ opacity: 0, scale: 0.8 }}
  animate={{ opacity: 1, scale: 1 }}
>
```

**Alert Pulse** (Tailwind):
```html
<div className="animate-pulse">
```

---

## Testing

### Unit Tests (Jest + React Testing Library)

Create `/home/jenner/code/ocr-service/web/__tests__/useSystemMetrics.test.ts`:

```typescript
import { renderHook, waitFor } from '@testing-library/react';
import { useSystemMetrics } from '@/hooks/useSystemMetrics';

describe('useSystemMetrics', () => {
  it('should initialize with null metrics', () => {
    const { result } = renderHook(() => useSystemMetrics({ enabled: false }));
    expect(result.current.current).toBeNull();
    expect(result.current.history).toEqual([]);
  });

  it('should detect critical alerts', async () => {
    const mockMetrics = {
      gpus: [{ id: 0, memory_percent: 0.96, temperature_c: 75 }],
      // ... other fields
    };

    // Mock SSE connection
    // ... test alert detection
  });
});
```

### Component Tests

```typescript
import { render, screen } from '@testing-library/react';
import { AlertBanner } from '@/components/AlertBanner';

describe('AlertBanner', () => {
  it('renders critical alerts with red styling', () => {
    const alerts = [
      {
        id: '1',
        type: 'critical',
        message: 'GPU 0 memory critical',
        value: 0.96,
      },
    ];

    render(<AlertBanner alerts={alerts} />);
    expect(screen.getByText(/GPU 0 memory critical/)).toBeInTheDocument();
  });
});
```

### Manual Testing Checklist

- [ ] Install recharts: `npm install recharts`
- [ ] Badge appears when monitoring enabled
- [ ] Badge shows correct GPU memory %
- [ ] Badge changes color (green → yellow → red)
- [ ] Click badge opens sidebar
- [ ] Sidebar slides in smoothly
- [ ] Metrics update every 1 second
- [ ] Timeline graph shows last 60 seconds
- [ ] Alert banners appear/disappear correctly
- [ ] Export button downloads valid JSON
- [ ] Close button closes sidebar
- [ ] Settings modal toggles monitoring
- [ ] SSE reconnects on disconnect
- [ ] No console errors
- [ ] Responsive on mobile

---

## Accessibility

### Requirements

1. **Keyboard Navigation**:
   - Tab to badge → Enter to open
   - Tab through sidebar controls
   - Escape to close sidebar

2. **ARIA Labels**:
```typescript
<button aria-label="Open system monitor">
<button aria-label="Close system monitor">
<div role="alert" aria-live="polite"> {/* For alerts */}
```

3. **Screen Reader Support**:
   - Metric values announced
   - Alert messages readable
   - Graph data accessible via table fallback

4. **Focus Management**:
   - Focus sidebar on open
   - Return focus to badge on close
   - Trap focus within sidebar when open

---

## Common Pitfalls

### Pitfall 1: SSE Connection Leaks
**Problem**: EventSource not closed on unmount
**Solution**: Always return cleanup function

```typescript
useEffect(() => {
  const eventSource = apiClient.createSystemMetricsStream(1);
  return () => {
    eventSource.close(); // CRITICAL
  };
}, []);
```

### Pitfall 2: Recharts Animation Lag
**Problem**: Chart animations cause jank with real-time data
**Solution**: Disable animations

```typescript
<Line isAnimationActive={false} />
```

### Pitfall 3: Memory Leak from History Buffer
**Problem**: Unbounded history array
**Solution**: Slice to max 60 entries

```typescript
setHistory(prev => [...prev, metrics].slice(-60));
```

### Pitfall 4: Framer Motion Layout Shift
**Problem**: Sidebar causes layout jump
**Solution**: Use fixed positioning

```typescript
<motion.div className="fixed right-0 top-0 bottom-0">
```

### Pitfall 5: Missing Null Checks
**Problem**: Crash when metrics is null
**Solution**: Always check before rendering

```typescript
if (!metrics) return <LoadingState />;
```

---

## Success Criteria

### Functional
- ✅ Badge displays GPU memory %
- ✅ Sidebar opens/closes smoothly
- ✅ Metrics update every 1 second
- ✅ Timeline shows 60-second history
- ✅ Alerts trigger at correct thresholds
- ✅ Export downloads valid JSON
- ✅ Settings modal toggles monitoring
- ✅ SSE reconnects on failure

### Visual
- ✅ Consistent dark theme
- ✅ Color-coded alerts (yellow/red)
- ✅ Smooth animations
- ✅ Responsive layout
- ✅ Readable typography

### Performance
- ✅ No jank/lag during updates
- ✅ Smooth 60fps animations
- ✅ < 100ms render time
- ✅ No memory leaks

### Accessibility
- ✅ Keyboard accessible
- ✅ Screen reader compatible
- ✅ ARIA labels present
- ✅ Focus management working

---

## Installation Steps

### 1. Install Recharts
```bash
cd /home/jenner/code/ocr-service/web
npm install recharts
```

### 2. Create Files in Order
1. Types (`lib/types.ts`)
2. API Client (`lib/api-client.ts`)
3. Hook (`hooks/useSystemMetrics.ts`)
4. AlertBanner (`components/AlertBanner.tsx`)
5. MetricsTimeline (`components/MetricsTimeline.tsx`)
6. SystemMonitor (`components/SystemMonitor.tsx`)
7. SystemMonitorWidget (`components/SystemMonitorWidget.tsx`)
8. SettingsModal (`components/SettingsModal.tsx`)
9. Integrate into `app/page.tsx`

### 3. Test
```bash
npm run dev
# Open http://localhost:3000
# Enable monitoring in settings
# Verify metrics appear
```

---

## Appendix

### File Checklist

Files to modify:
- [ ] `/home/jenner/code/ocr-service/web/lib/types.ts`
- [ ] `/home/jenner/code/ocr-service/web/lib/api-client.ts`
- [ ] `/home/jenner/code/ocr-service/web/app/page.tsx`

Files to create:
- [ ] `/home/jenner/code/ocr-service/web/hooks/useSystemMetrics.ts`
- [ ] `/home/jenner/code/ocr-service/web/components/AlertBanner.tsx`
- [ ] `/home/jenner/code/ocr-service/web/components/MetricsTimeline.tsx`
- [ ] `/home/jenner/code/ocr-service/web/components/SystemMonitor.tsx`
- [ ] `/home/jenner/code/ocr-service/web/components/SystemMonitorWidget.tsx`
- [ ] `/home/jenner/code/ocr-service/web/components/SettingsModal.tsx`

### Quick Start

**Total Time**: 4-5 hours

1. Install recharts (5 min)
2. Add types (15 min)
3. Add API methods (15 min)
4. Create useSystemMetrics hook (30 min)
5. Create AlertBanner (20 min)
6. Create MetricsTimeline (30 min)
7. Create SystemMonitor (60 min)
8. Create SystemMonitorWidget (30 min)
9. Create SettingsModal (20 min)
10. Integrate into page.tsx (20 min)
11. Test (30 min)

---

**End of Frontend Specification**
