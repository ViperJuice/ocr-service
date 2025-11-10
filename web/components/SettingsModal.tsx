"use client";

import { X, Settings } from "lucide-react";

interface SettingsModalProps {
  isOpen: boolean;
  onClose: () => void;
  monitoringEnabled: boolean;
  onMonitoringToggle: (enabled: boolean) => void;
}

export function SettingsModal({
  isOpen,
  onClose,
  monitoringEnabled,
  onMonitoringToggle,
}: SettingsModalProps) {
  if (!isOpen) return null;

  return (
    <>
      {/* Backdrop */}
      <div
        className="fixed inset-0 bg-black/60 z-50 flex items-center justify-center p-4"
        onClick={onClose}
      >
        {/* Modal */}
        <div
          className="bg-gray-900 rounded-lg shadow-2xl max-w-md w-full border border-gray-700"
          onClick={(e) => e.stopPropagation()}
        >
          {/* Header */}
          <div className="flex items-center justify-between p-6 border-b border-gray-700">
            <div className="flex items-center gap-2">
              <Settings className="w-5 h-5 text-gray-400" />
              <h2 className="text-xl font-semibold text-white">Settings</h2>
            </div>
            <button
              onClick={onClose}
              className="p-1 hover:bg-gray-800 rounded transition-colors text-gray-400 hover:text-white"
              aria-label="Close"
            >
              <X className="w-5 h-5" />
            </button>
          </div>

          {/* Content */}
          <div className="p-6 space-y-6">
            {/* System Monitoring Toggle */}
            <div>
              <label className="flex items-center justify-between cursor-pointer">
                <div>
                  <h3 className="font-medium text-white mb-1">System Monitoring</h3>
                  <p className="text-sm text-gray-400">
                    Real-time GPU, CPU, and RAM metrics
                  </p>
                </div>
                <div className="relative">
                  <input
                    type="checkbox"
                    checked={monitoringEnabled}
                    onChange={(e) => onMonitoringToggle(e.target.checked)}
                    className="sr-only peer"
                  />
                  <div className="w-11 h-6 bg-gray-700 peer-focus:outline-none peer-focus:ring-2 peer-focus:ring-blue-500 rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-blue-600"></div>
                </div>
              </label>
            </div>

            <div className="pt-4 border-t border-gray-700 text-xs text-gray-500">
              <p>
                Monitoring data is streamed in real-time from the backend API and
                stored locally for 60 seconds.
              </p>
            </div>
          </div>

          {/* Footer */}
          <div className="flex justify-end p-6 border-t border-gray-700">
            <button
              onClick={onClose}
              className="px-4 py-2 bg-blue-600 hover:bg-blue-700 rounded transition-colors font-medium text-white"
            >
              Done
            </button>
          </div>
        </div>
      </div>
    </>
  );
}
