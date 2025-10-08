/**
 * useMonitoring Hook - Real-time monitoring with WebSocket support
 * Provides experiment tracking, system health monitoring, and real-time updates
 */

import { useState, useEffect, useCallback, useRef } from 'react';
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

export const useMonitoring = (): MonitoringHookReturn => {
  // State
  const [monitoringData, setMonitoringData] = useState<MonitoringData | null>(null);
  const [isConnected, setIsConnected] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [connectionRetries, setConnectionRetries] = useState(0);

  // Refs for polling cleanup
  const pollingIntervalRef = useRef<number | null>(null);

  // Auth context for API calls
  const { token } = useAuth();

  // Create authorization headers
  const getAuthHeaders = useCallback(() => ({
    'Authorization': `Bearer ${token}`,
    'Content-Type': 'application/json',
  }), [token]);

  // Fetch current monitoring data from REST API
  const fetchMonitoringData = useCallback(async (): Promise<MonitoringData | null> => {
    if (!token) {
      console.log('No authentication token available for monitoring');
      throw new Error('Authentication required for monitoring data');
    }

    try {
      const [experimentsRes, systemHealthRes, streamingStatusRes] = await Promise.all([
        fetch(getMonitoringApiUrl('/experiments'), {
          headers: getAuthHeaders(),
        }),
        fetch(getMonitoringApiUrl('/system-health'), {
          headers: getAuthHeaders(),
        }),
        fetch(getStreamingStatusUrl(), {
          headers: getAuthHeaders(),
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
        systemPayload?.timestamp
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

  // Refresh monitoring data
  const refreshData = useCallback(async () => {
    // Allow refresh even without token for basic monitoring data
    
    setIsLoading(true);
    setError(null);
    
    try {
      const data = await fetchMonitoringData();
      setMonitoringData(data);
    } catch (err) {
      const errorMessage = err instanceof Error ? err.message : 'Failed to refresh monitoring data';
      setError(errorMessage);
      console.error('Error refreshing monitoring data:', err);
    } finally {
      setIsLoading(false);
    }
  }, [token, fetchMonitoringData]);

  // Simplified polling function
  const pollMonitoringData = useCallback(async () => {
    // Stop polling if we've exceeded max retries
    if (connectionRetries >= MAX_RETRIES) {
      setError(`Max retry attempts reached (${MAX_RETRIES}). Please refresh the page or check authentication.`);
      setIsConnected(false);
      return;
    }

    try {
      const data = await fetchMonitoringData();
      setMonitoringData(data);
      setIsConnected(true);
      setError(null);
      setConnectionRetries(0);
    } catch (err) {
      const errorMessage = err instanceof Error ? err.message : 'Failed to fetch monitoring data';
      setError(errorMessage);
      setIsConnected(false);
      setConnectionRetries(prev => prev + 1);
      
      // If authentication error, suggest user to login
      if (errorMessage.includes('Authentication required')) {
        setError('Please log in to access monitoring data');
      }
    }
  }, [fetchMonitoringData, connectionRetries]);

  // Start HTTP polling
  const connect = useCallback(() => {
    console.log('Starting HTTP polling for monitoring data');
    
    // Reset retry counter when starting fresh
    setConnectionRetries(0);
    setError(null);
    
    // Stop any existing polling
    if (pollingIntervalRef.current) {
      clearInterval(pollingIntervalRef.current);
    }
    
    // Initial data fetch
    pollMonitoringData();
    
    // Set up 60-second polling
    pollingIntervalRef.current = setInterval(() => {
      // Only continue polling if we haven't exceeded retries
      if (connectionRetries < MAX_RETRIES) {
        pollMonitoringData();
      } else {
        // Stop polling on max retries
        if (pollingIntervalRef.current) {
          clearInterval(pollingIntervalRef.current);
          pollingIntervalRef.current = null;
        }
        console.log('Polling stopped due to max retries reached');
      }
    }, 60000); // Poll every 60 seconds
    
    console.log('HTTP polling started (60-second interval)');
  }, [pollMonitoringData, connectionRetries]);

  // Stop HTTP polling
  const disconnect = useCallback(() => {
    console.log('Stopping HTTP polling');
    
    // Clear polling interval
    if (pollingIntervalRef.current) {
      clearInterval(pollingIntervalRef.current);
      pollingIntervalRef.current = null;
    }

    setIsConnected(false);
    setConnectionRetries(0);
  }, []);

  // Reset error state
  const resetError = useCallback(() => {
    setError(null);
  }, []);

  // Auto-start polling on mount
  useEffect(() => {
    connect();

    // Cleanup on unmount
    return () => {
      disconnect();
    };
  }, [connect, disconnect]);

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
    isConnected,
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
