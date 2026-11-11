/**
 * System status readings: PC sample, database connections and live-view slots, polled every
 * 60 s (30 s after a failure). The last reading stays on screen after a failed poll.
 */

import { useState, useCallback } from 'react';
import { isAxiosError } from 'axios';
import { useSerialPolling } from './useSerialPolling';
import { useAuth } from '../context/AuthContext';
import { api } from '@/services/api';

export interface SystemHealth {
  /** When the server took the sample (`sampled_at`). */
  timestamp: string | null;
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
  active_session_count: number;
  max_sessions: number;
}

export interface MonitoringData {
  system_health: SystemHealth | null;
  databases: DatabaseConnections | null;
  streaming_status: StreamingServiceStatus | null;
}

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

export const useMonitoring = () => {
  const [monitoringData, setMonitoringData] = useState<MonitoringData | null>(null);
  // Polling restarts for a different user, not for a renewed access token.
  const { user } = useAuth();

  // Through the shared client, which renews an expired token.
  const fetchMonitoringData = useCallback(async (signal: AbortSignal): Promise<MonitoringData> => {
    const [systemHealthData, streamingStatusData, databasesData] = await Promise.all([
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
    const system = systemHealthData?.data?.system;
    const sampledAt = systemHealthData?.data?.sampled_at;
    return {
      system_health: isRecord(system) ? { ...system, timestamp: typeof sampledAt === 'string' ? sampledAt : null } as SystemHealth : null,
      databases: normalizeDatabases(databasesData?.data),
      streaming_status: isRecord(streamingStatusData?.data?.status) ? streamingStatusData.data.status as StreamingServiceStatus : null,
    };
  }, []);

  const polling = useSerialPolling({
    request: fetchMonitoringData,
    onSuccess: setMonitoringData,
    identity: user?.user_id ?? null,
    enabled: Boolean(user),
    interval: 60000,
    retryInterval: 30000,
  });

  return {
    monitoringData,
    systemHealth: monitoringData?.system_health ?? null,
    databases: monitoringData?.databases ?? null,
    streamingStatus: monitoringData?.streaming_status ?? null,
    isLoading: polling.pending,
    error: polling.error,
    refreshData: polling.refresh,
  };
};

export default useMonitoring;
