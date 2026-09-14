/**
 * useMonitoring Hook - Real-time monitoring with WebSocket support
 * Provides experiment tracking, system health monitoring, and real-time updates
 */

import { useState, useCallback } from 'react';
import { useSerialPolling } from './useSerialPolling';
import { useAuth } from '../context/AuthContext';
import { buildApiUrl, buildWsUrl } from '@/utils/apiBase';

// Types for monitoring data
export interface ExperimentData {
  id: string;
  method_name: string;
  start_time: string;
  end_time?: string;
  status: 'RUNNING' | 'COMPLETED' | 'FAILED' | 'PENDING';
  progress?: number;
  plate_ids?: string[];
}

export interface SystemHealth {
  timestamp: string;
  cpu_percent: number;
  memory_percent: number;
  memory_used_gb: number;
  memory_total_gb: number;
  disk_percent: number;
  disk_used_gb: number;
  disk_total_gb: number;
}

export interface DatabaseStatus {
  is_connected: boolean;
  mode: 'primary' | 'secondary' | 'mock';
  database_name: string;
  server_name: string;
  error_message?: string;
}

export interface StreamingServiceStatus {
  enabled: boolean;
  active_session_count: number;
  max_sessions: number;
  total_bandwidth_mbps: number;
  resource_usage_percent: number;
  [key: string]: any;
}

export interface MonitoringData {
  experiments: ExperimentData[];
  system_health: SystemHealth;
  database_status: DatabaseStatus;
  websocket_connections: number;
  last_updated: string;
  streaming_status?: StreamingServiceStatus | null;
}

export interface WebSocketMessage {
  type: 'connection' | 'current_data' | 'experiments_update' | 'system_health' | 'database_performance' | 'ping' | 'pong';
  data?: any;
  timestamp: string;
  status?: string;
  channel?: string;
}

export interface MonitoringHookReturn {
  // Data
  monitoringData: MonitoringData | null;
  experiments: ExperimentData[];
  systemHealth: SystemHealth | null;
  databaseStatus: DatabaseStatus | null;
  streamingStatus: StreamingServiceStatus | null;
  
  // State
  isConnected: boolean;
  isLoading: boolean;
  error: string | null;
  connectionRetries: number;
  
  // Actions
  connect: () => void;
  disconnect: () => void;
  refreshData: () => Promise<void>;
  resetError: () => void;
}

const getWebSocketUrl = () => buildWsUrl('/api/monitoring/ws/general');
const getMonitoringApiUrl = (path: string) => buildApiUrl(`/api/monitoring${path}`);
const getStreamingStatusUrl = () => buildApiUrl('/api/camera/streaming/status');
const MAX_RETRIES = 5;
const RETRY_DELAY = 2000;

export const useMonitoring = (options: { autoRetry?: boolean; retryInterval?: number } = {}): MonitoringHookReturn => {
  // State
  const [monitoringData, setMonitoringData] = useState<MonitoringData | null>(null);
  // Auth context for API calls
  const { token } = useAuth();

  // Create authorization headers
  const getAuthHeaders = useCallback(() => ({
    'Authorization': `Bearer ${token}`,
    'Content-Type': 'application/json',
  }), [token]);

  // Fetch current monitoring data from REST API
  const fetchMonitoringData = useCallback(async (signal: AbortSignal): Promise<MonitoringData | null> => {
    if (!token) {
      console.log('No authentication token available for monitoring');
      throw new Error('Authentication required for monitoring data');
    }

    try {
      const [experimentsRes, systemHealthRes, streamingStatusRes] = await Promise.all([
        fetch(getMonitoringApiUrl('/experiments'), {
          headers: getAuthHeaders(), signal,
        }),
        fetch(getMonitoringApiUrl('/system-health'), {
          headers: getAuthHeaders(), signal,
        }),
        fetch(getStreamingStatusUrl(), {
          headers: getAuthHeaders(), signal,
        }),
      ]);

      if (!experimentsRes.ok || !systemHealthRes.ok) {
        throw new Error('Failed to fetch monitoring data');
      }

      const [experimentsData, systemHealthData] = await Promise.all([
        experimentsRes.json(),
        systemHealthRes.json(),
      ]);

      let streamingStatus: StreamingServiceStatus | null = null;
      if (streamingStatusRes.ok) {
        try {
          const streamingStatusData = await streamingStatusRes.json();
          streamingStatus =
            streamingStatusData?.data?.status ??
            streamingStatusData?.data ??
            null;
        } catch (streamingError) {
          console.warn('Failed to parse streaming status response:', streamingError);
        }
      }

      const experimentsPayload = experimentsData?.data;
      const experimentsList = Array.isArray(experimentsPayload)
        ? experimentsPayload
        : Array.isArray(experimentsPayload?.experiments)
          ? experimentsPayload.experiments
          : [];

      const normalizedExperiments: ExperimentData[] = experimentsList.map((raw, index) => {
        const statusValue = raw?.Status ?? raw?.status ?? 'UNKNOWN';
        const progressValue = raw?.Progress ?? raw?.progress ?? 0;
        const plateValue = raw?.PlateID ?? raw?.plate_id ?? raw?.plateIds ?? raw?.plate_ids;
        const startTime = raw?.StartTime ?? raw?.start_time;
        const endTime = raw?.EndTime ?? raw?.end_time;

        const plateIds = Array.isArray(plateValue)
          ? plateValue.map((plate) => (plate != null ? String(plate) : plate)).filter(Boolean)
          : plateValue != null
            ? [String(plateValue)]
            : undefined;

        return {
          id: raw?.ExperimentID?.toString()
            ?? raw?.ExperimentId?.toString()
            ?? raw?.run_guid?.toString()
            ?? raw?.id?.toString()
            ?? `experiment-${index}`,
          method_name: raw?.MethodName ?? raw?.method_name ?? 'Unknown Experiment',
          start_time: startTime ?? new Date().toISOString(),
          end_time: endTime ?? undefined,
          status: statusValue?.toString() ?? 'UNKNOWN',
          progress: typeof progressValue === 'number' ? progressValue : Number(progressValue) || 0,
          plate_ids: plateIds,
        };
      });

      const systemPayload = systemHealthData?.data || {};
      const systemTimestamp =
        systemPayload?.sampled_at
        ?? systemPayload?.timestamp
        ?? systemHealthData?.metadata?.timestamp
        ?? new Date().toISOString();
      const systemMetrics = systemPayload.system
        ? { ...systemPayload.system, timestamp: systemTimestamp }
        : null;

      return {
        experiments: normalizedExperiments,
        system_health: systemMetrics,
        database_status: systemPayload.database || null,
        websocket_connections:
          systemPayload.connections?.active
          ?? systemPayload.websockets?.total_connections
          ?? 0,
        last_updated: systemHealthData?.metadata?.timestamp || new Date().toISOString(),
        streaming_status: streamingStatus,
      };
    } catch (err) {
      console.error('Error fetching monitoring data:', err);
      throw err;
    }
  }, [token, getAuthHeaders]);

  const polling = useSerialPolling({
    request: fetchMonitoringData,
    onSuccess: setMonitoringData,
    identity: token,
    enabled: Boolean(token),
    interval: 60000,
    retryInterval: options.autoRetry === false ? 60000 : (options.retryInterval ?? 30) * 1000,
    maxRetries: options.autoRetry === false ? MAX_RETRIES : undefined,
  });
  const connect = polling.start;
  const disconnect = polling.stop;
  const refreshData = polling.refresh;
  const resetError = polling.resetError;
  const isLoading = polling.pending;
  const error = polling.error;
  const connectionRetries = polling.retries;

  // Derived state
  const experiments = monitoringData?.experiments || [];
  const systemHealth = monitoringData?.system_health || null;
  const databaseStatus = monitoringData?.database_status || null;
  const streamingStatus = monitoringData?.streaming_status || null;

  return {
    // Data
    monitoringData,
    experiments,
    systemHealth,
    databaseStatus,
    streamingStatus,
    
    // State
    isConnected: polling.active && !error && Boolean(monitoringData) && Boolean(token),
    isLoading,
    error,
    connectionRetries,
    
    // Actions
    connect,
    disconnect,
    refreshData,
    resetError,
  };
};

export default useMonitoring;
