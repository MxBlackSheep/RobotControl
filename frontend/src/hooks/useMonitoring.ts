/**
 * useMonitoring Hook - Real-time monitoring with WebSocket support
 * Provides experiment tracking, system health monitoring, and real-time updates
 */

import { useState, useCallback } from 'react';
import { isAxiosError } from 'axios';
import { useSerialPolling } from './useSerialPolling';
import { useAuth } from '../context/AuthContext';
import { api } from '@/services/api';

// Types for monitoring data
export interface ExperimentData {
  id: string;
  method_name: string;
  /** Null when the server does not report a start time. */
  start_time: string | null;
  end_time?: string;
  status: 'RUNNING' | 'COMPLETED' | 'FAILED' | 'PENDING';
  progress?: number;
  plate_ids?: string[];
}

export interface SystemHealth {
  timestamp: string;
  cpu_percent: number;
  /** RobotControl and its child processes, % of the whole machine; null until known. */
  robotcontrol_cpu_percent?: number | null;
  memory_percent: number;
  memory_used_gb: number;
  memory_total_gb: number;
  disk_percent: number;
  disk_used_gb: number;
  disk_total_gb: number;
}

/** One SQL Server connection RobotControl depends on (GET /api/monitoring/databases). */
export interface DatabaseConnection {
  id: string;
  name: string;
  server?: string | null;
  database?: string | null;
  access: 'built-in' | 'read' | 'operation' | string;
  uses: string[];
  /** 'connected' or 'failed'; anything else is shown as unknown. */
  state: string;
  message?: string | null;
}

export interface DatabaseConnections {
  built_in: DatabaseConnection | null;
  /** Null when the saved connections could not be listed. */
  connections: DatabaseConnection[] | null;
  checked_at: string | null;
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
  databases: DatabaseConnections | null;
  last_updated: string;
  streaming_status?: StreamingServiceStatus | null;
}
export interface MonitoringHookReturn {
  // Data
  monitoringData: MonitoringData | null;
  experiments: ExperimentData[];
  systemHealth: SystemHealth | null;
  databases: DatabaseConnections | null;
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

const MAX_RETRIES = 5;

const isRecord = (value: unknown): value is Record<string, any> => typeof value === 'object' && value !== null && !Array.isArray(value);

const normalizeConnection = (raw: Record<string, any>): DatabaseConnection => ({
  id: String(raw.id ?? raw.name ?? ''), name: String(raw.name ?? 'Unnamed connection'),
  server: typeof raw.server === 'string' ? raw.server : null, database: typeof raw.database === 'string' ? raw.database : null,
  access: String(raw.access ?? ''), uses: Array.isArray(raw.uses) ? raw.uses.map(String) : [],
  // Only an explicit 'connected' or 'failed' is believed; anything else shows as unknown.
  state: raw.state === 'connected' || raw.state === 'failed' ? raw.state : 'unknown',
  message: typeof raw.message === 'string' ? raw.message : null,
});

/** An incomplete reply is unavailable as a whole, never an empty "all connected" list. */
const normalizeDatabases = (raw: unknown): DatabaseConnections | null => {
  if (!isRecord(raw) || !('built_in' in raw) || !('connections' in raw)) return null;
  if (raw.built_in !== null && !isRecord(raw.built_in)) return null;
  if (raw.connections !== null && !Array.isArray(raw.connections)) return null;
  return {
    built_in: raw.built_in ? normalizeConnection(raw.built_in) : null,
    connections: raw.connections ? raw.connections.filter(isRecord).map(normalizeConnection) : null,
    checked_at: typeof raw.checked_at === 'string' ? raw.checked_at : null,
  };
};

export const useMonitoring = (options: { autoRetry?: boolean; retryInterval?: number } = {}): MonitoringHookReturn => {
  // State
  const [monitoringData, setMonitoringData] = useState<MonitoringData | null>(null);
  // Polling restarts for a different user, not for a renewed access token.
  const { token, user } = useAuth();

  // Fetch current monitoring data through the shared client, which renews an expired token.
  const fetchMonitoringData = useCallback(async (signal: AbortSignal): Promise<MonitoringData | null> => {
    if (!token) {
      console.log('No authentication token available for monitoring');
      throw new Error('Authentication required for monitoring data');
    }

    try {
      const [experimentsData, systemHealthData, streamingStatusData, databasesData] = await Promise.all([
        api.get('/api/monitoring/experiments', { signal }).then(response => response.data),
        api.get('/api/monitoring/system-health', { signal }).then(response => response.data),
        // Live-view status is optional here; its failure shows as "unavailable".
        api.get('/api/camera/streaming/status', { signal }).then(response => response.data, () => null),
        // Connection checks are optional too; a failure leaves the Databases card unavailable.
        api.get('/api/monitoring/databases', { signal }).then(response => response.data, () => null),
      ]).catch(cause => {
        // Timeouts and network errors keep their own message ("Request timed out").
        if (signal.aborted || !isAxiosError(cause) || !cause.response) throw cause;
        throw new Error('Failed to fetch monitoring data');
      });

      const streamingStatus: StreamingServiceStatus | null =
        streamingStatusData?.data?.status ??
        streamingStatusData?.data ??
        null;

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
          start_time: startTime ?? null,
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
        databases: normalizeDatabases(databasesData?.data),
        last_updated: systemHealthData?.metadata?.timestamp || new Date().toISOString(),
        streaming_status: streamingStatus,
      };
    } catch (err) {
      console.error('Error fetching monitoring data:', err);
      throw err;
    }
  }, [token]);

  const polling = useSerialPolling({
    request: fetchMonitoringData,
    onSuccess: setMonitoringData,
    identity: user?.user_id ?? null,
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
  const databases = monitoringData?.databases || null;
  const streamingStatus = monitoringData?.streaming_status || null;

  return {
    // Data
    monitoringData,
    experiments,
    systemHealth,
    databases,
    streamingStatus,
    
    // State
    isConnected: polling.active && polling.succeeded && Boolean(token),
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
