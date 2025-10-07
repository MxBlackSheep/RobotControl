import { useState, useEffect, useRef, useCallback } from 'react';
import { schedulingAPI } from '../services/schedulingApi';

interface StatusMonitorConfig {
  refreshInterval?: number; // in milliseconds
  enabled?: boolean;
}

interface QueueStatus {
  queued_jobs: number;
  running_jobs: number;
  completed_jobs: number;
  failed_jobs: number;
  queue_size: number;
}

interface HamiltonStatus {
  is_running: boolean;
  process_count: number;
  availability: string;
  last_check: string;
}

interface SchedulerStatus {
  is_running: boolean;
  active_schedules_count: number;
  running_jobs_count: number;
  max_concurrent_jobs: number;
  check_interval_seconds: number;
  thread_alive: boolean;
  uptime_seconds: number;
}

export const useIntelligentStatusMonitor = (config: StatusMonitorConfig = {}) => {
  const { refreshInterval = 5000, enabled = true } = config; // Default 5 seconds
  
  // Status states
  const [queueStatus, setQueueStatus] = useState<QueueStatus | null>(null);
  const [hamiltonStatus, setHamiltonStatus] = useState<HamiltonStatus | null>(null);
  const [schedulerStatus, setSchedulerStatus] = useState<SchedulerStatus | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [lastUpdate, setLastUpdate] = useState<Date | null>(null);
  
  // Refs to track previous values for change detection
  const previousQueueStatus = useRef<QueueStatus | null>(null);
  const previousHamiltonStatus = useRef<HamiltonStatus | null>(null);
  const previousSchedulerStatus = useRef<SchedulerStatus | null>(null);
  const intervalRef = useRef<number | null>(null);
  
  // Check if status has actually changed
  const hasChanged = useCallback((prev: any, current: any): boolean => {
    if (!prev && current) return true;
    if (prev && !current) return true;
    if (!prev && !current) return false;
    
    return JSON.stringify(prev) !== JSON.stringify(current);
  }, []);
  
  // Fetch all status data
  const fetchStatusData = useCallback(async (silent: boolean = false) => {
    if (!enabled) return;
    
    if (!silent) setLoading(true);
    setError(null);
    
    try {
      // Fetch all status data in parallel
      const [queueResult, schedulerResult] = await Promise.all([
        schedulingAPI.getQueueStatus().catch(err => null),
        schedulingAPI.getSchedulerStatus().catch(err => null)
      ]);
      
      let hasAnyChanges = false;
      
      // Process queue status
      if (queueResult && queueResult.data && queueResult.data.success) {
        const newQueueStatus = queueResult.data.data.queue;
        const newHamiltonStatus = queueResult.data.data.hamilton;
        
        if (hasChanged(previousQueueStatus.current, newQueueStatus)) {
          setQueueStatus(newQueueStatus);
          previousQueueStatus.current = newQueueStatus;
          hasAnyChanges = true;
        }
        
        if (hasChanged(previousHamiltonStatus.current, newHamiltonStatus)) {
          setHamiltonStatus(newHamiltonStatus);
          previousHamiltonStatus.current = newHamiltonStatus;
          hasAnyChanges = true;
        }
      } else if (!queueResult) {
        console.warn('Queue status request failed');
      }
      
      // Process scheduler status
      if (schedulerResult && schedulerResult.data && schedulerResult.data.success) {
        const newSchedulerStatus = schedulerResult.data.data;
        
        if (hasChanged(previousSchedulerStatus.current, newSchedulerStatus)) {
          setSchedulerStatus(newSchedulerStatus);
          previousSchedulerStatus.current = newSchedulerStatus;
          hasAnyChanges = true;
        }
      } else if (!schedulerResult) {
        console.warn('Scheduler status request failed');
      }
      
      // Only update lastUpdate if there were actual changes
      if (hasAnyChanges || !lastUpdate) {
        setLastUpdate(new Date());
      }
      
    } catch (err) {
      const errorMessage = err instanceof Error ? err.message : 'Failed to fetch status';
      setError(errorMessage);
      console.error('Status monitoring error:', err);
    } finally {
      if (!silent) setLoading(false);
    }
  }, [enabled, hasChanged, lastUpdate]);
  
  // Start/stop monitoring
  useEffect(() => {
    if (!enabled) {
      if (intervalRef.current) {
        clearInterval(intervalRef.current);
        intervalRef.current = null;
      }
      return;
    }
    
    // Initial fetch
    fetchStatusData(false);
    
    // Set up interval for silent updates
    intervalRef.current = setInterval(() => {
      fetchStatusData(true); // Silent updates
    }, refreshInterval);
    
    return () => {
      if (intervalRef.current) {
        clearInterval(intervalRef.current);
        intervalRef.current = null;
      }
    };
  }, [enabled, refreshInterval, fetchStatusData]);
  
  // Manual refresh function
  const refreshStatus = useCallback(async () => {
    await fetchStatusData(false);
  }, [fetchStatusData]);
  
  // Clear error function
  const clearError = useCallback(() => {
    setError(null);
  }, []);
  
  return {
    // Status data
    queueStatus,
    hamiltonStatus,
    schedulerStatus,
    
    // State
    loading,
    error,
    lastUpdate,
    
    // Actions
    refreshStatus,
    clearError,
    
    // Configuration
    isMonitoring: enabled && intervalRef.current !== null
  };
};

export default useIntelligentStatusMonitor;