/**
 * usePerformance Hook - Performance monitoring and optimization utilities
 * 
 * Provides React performance metrics, memory usage tracking, and optimization helpers
 * Includes render tracking, component performance analysis, and memory leak detection
 */

import { useEffect, useRef, useCallback, useState } from 'react';

export interface PerformanceMetrics {
  renderCount: number;
  renderTime: number;
  lastRenderTime: number;
  averageRenderTime: number;
  memoryUsage?: number;
  componentName?: string;
}

export interface UsePerformanceOptions {
  /** Enable performance tracking */
  enabled?: boolean;
  /** Component name for identification */
  componentName?: string;
  /** Track memory usage */
  trackMemory?: boolean;
  /** Warning threshold for render time (ms) */
  renderTimeWarning?: number;
  /** Maximum render history to keep */
  maxHistory?: number;
}

/**
 * Custom hook for component performance monitoring
 */
export const usePerformance = (options: UsePerformanceOptions = {}): PerformanceMetrics => {
  const {
    enabled = import.meta.env.DEV,
    componentName = 'Component',
    trackMemory = false,
    renderTimeWarning = 100,
    maxHistory = 50
  } = options;

  const renderCountRef = useRef(0);
  const renderTimesRef = useRef<number[]>([]);
  const lastRenderStartRef = useRef<number>(0);
  const [metrics, setMetrics] = useState<PerformanceMetrics>({
    renderCount: 0,
    renderTime: 0,
    lastRenderTime: 0,
    averageRenderTime: 0,
    componentName
  });

  // Track render start
  useEffect(() => {
    if (!enabled) return;
    
    lastRenderStartRef.current = performance.now();
  });

  // Track render completion and update metrics
  useEffect(() => {
    if (!enabled) return;

    const renderEndTime = performance.now();
    const renderTime = renderEndTime - lastRenderStartRef.current;
    
    renderCountRef.current += 1;
    renderTimesRef.current.push(renderTime);
    
    // Limit history size
    if (renderTimesRef.current.length > maxHistory) {
      renderTimesRef.current = renderTimesRef.current.slice(-maxHistory);
    }
    
    const averageRenderTime = renderTimesRef.current.reduce((sum, time) => sum + time, 0) / renderTimesRef.current.length;
    
    // Get memory usage if tracking is enabled
    let memoryUsage: number | undefined;
    if (trackMemory && 'memory' in performance) {
      memoryUsage = (performance as any).memory?.usedJSHeapSize || 0;
    }
    
    setMetrics({
      renderCount: renderCountRef.current,
      renderTime,
      lastRenderTime: renderTime,
      averageRenderTime,
      memoryUsage,
      componentName
    });
    
    // Warn about slow renders
    if (renderTime > renderTimeWarning) {
      console.warn(
        `Slow render detected in ${componentName}: ${renderTime.toFixed(2)}ms (threshold: ${renderTimeWarning}ms)`
      );
    }
  });

  return metrics;
};

/**
 * Hook for measuring async operation performance
 */
export const useAsyncPerformance = () => {
  const [operations, setOperations] = useState<Record<string, {
    count: number;
    totalTime: number;
    averageTime: number;
    lastTime: number;
  }>>({});

  const measureAsync = useCallback(async <T>(
    operationName: string,
    asyncOperation: () => Promise<T>
  ): Promise<T> => {
    const startTime = performance.now();
    
    try {
      const result = await asyncOperation();
      const endTime = performance.now();
      const duration = endTime - startTime;
      
      setOperations(prev => {
        const existing = prev[operationName] || { count: 0, totalTime: 0, averageTime: 0, lastTime: 0 };
        const newCount = existing.count + 1;
        const newTotalTime = existing.totalTime + duration;
        
        return {
          ...prev,
          [operationName]: {
            count: newCount,
            totalTime: newTotalTime,
            averageTime: newTotalTime / newCount,
            lastTime: duration
          }
        };
      });
      
      return result;
    } catch (error) {
      const endTime = performance.now();
      const duration = endTime - startTime;
      
      // Track failed operations too
      setOperations(prev => {
        const existing = prev[`${operationName}_failed`] || { count: 0, totalTime: 0, averageTime: 0, lastTime: 0 };
        const newCount = existing.count + 1;
        const newTotalTime = existing.totalTime + duration;
        
        return {
          ...prev,
          [`${operationName}_failed`]: {
            count: newCount,
            totalTime: newTotalTime,
            averageTime: newTotalTime / newCount,
            lastTime: duration
          }
        };
      });
      
      throw error;
    }
  }, []);

  const clearMetrics = useCallback(() => {
    setOperations({});
  }, []);

  return {
    operations,
    measureAsync,
    clearMetrics
  };
};

/**
 * Hook for memory leak detection and monitoring
 */
export const useMemoryMonitor = (options: {
  enabled?: boolean;
  warningThreshold?: number; // MB
  checkInterval?: number; // ms
} = {}) => {
  const {
    enabled = import.meta.env.DEV,
    warningThreshold = 100, // 100MB
    checkInterval = 5000 // 5 seconds
  } = options;

  const [memoryInfo, setMemoryInfo] = useState<{
    usedJSHeapSize: number;
    totalJSHeapSize: number;
    jsHeapSizeLimit: number;
    usedMB: number;
    totalMB: number;
    limitMB: number;
  } | null>(null);

  useEffect(() => {
    if (!enabled || !('memory' in performance)) return;

    const checkMemory = () => {
      const memory = (performance as any).memory;
      
      const info = {
        usedJSHeapSize: memory.usedJSHeapSize,
        totalJSHeapSize: memory.totalJSHeapSize,
        jsHeapSizeLimit: memory.jsHeapSizeLimit,
        usedMB: memory.usedJSHeapSize / 1024 / 1024,
        totalMB: memory.totalJSHeapSize / 1024 / 1024,
        limitMB: memory.jsHeapSizeLimit / 1024 / 1024
      };

      setMemoryInfo(info);

      // Warn about high memory usage
      if (info.usedMB > warningThreshold) {
        console.warn(
          `High memory usage detected: ${info.usedMB.toFixed(2)}MB (threshold: ${warningThreshold}MB)`
        );
      }
    };

    checkMemory();
    const interval = setInterval(checkMemory, checkInterval);

    return () => clearInterval(interval);
  }, [enabled, warningThreshold, checkInterval]);

  return memoryInfo;
};

/**
 * Hook for debouncing expensive operations
 */
export const useDebounce = <T>(value: T, delay: number): T => {
  const [debouncedValue, setDebouncedValue] = useState<T>(value);

  useEffect(() => {
    const handler = setTimeout(() => {
      setDebouncedValue(value);
    }, delay);

    return () => {
      clearTimeout(handler);
    };
  }, [value, delay]);

  return debouncedValue;
};

/**
 * Hook for throttling function calls
 */
export const useThrottle = <T extends (...args: any[]) => any>(
  callback: T,
  delay: number
): T => {
  const lastCallRef = useRef<number>(0);
  const timeoutRef = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);

  return useCallback((...args: Parameters<T>) => {
    const now = performance.now();

    if (now - lastCallRef.current >= delay) {
      lastCallRef.current = now;
      return callback(...args);
    } else {
      if (timeoutRef.current) {
        clearTimeout(timeoutRef.current);
      }
      
      timeoutRef.current = setTimeout(() => {
        lastCallRef.current = performance.now();
        callback(...args);
      }, delay - (now - lastCallRef.current));
    }
  }, [callback, delay]) as T;
};

/**
 * Hook for measuring component lifecycle performance
 */
export const useLifecyclePerformance = (componentName: string = 'Component') => {
  const mountTimeRef = useRef<number>(0);
  const [lifecycleMetrics, setLifecycleMetrics] = useState({
    mountTime: 0,
    isFirstRender: true,
    componentName
  });

  // Measure mount time
  useEffect(() => {
    mountTimeRef.current = performance.now();
  }, []);

  // Measure time to first meaningful render
  useEffect(() => {
    const mountDuration = performance.now() - mountTimeRef.current;
    
    setLifecycleMetrics(prev => ({
      ...prev,
      mountTime: mountDuration,
      isFirstRender: false
    }));

    if (import.meta.env.DEV) {
      console.log(`${componentName} mount time: ${mountDuration.toFixed(2)}ms`);
    }
  }, [componentName]);

  return lifecycleMetrics;
};

/**
 * Performance monitoring context for complex components
 */
export const usePerformanceProfiler = (profileName: string) => {
  const startTimeRef = useRef<Map<string, number>>(new Map());
  
  const startProfiling = useCallback((label: string = 'default') => {
    startTimeRef.current.set(label, performance.now());
  }, []);

  const endProfiling = useCallback((label: string = 'default') => {
    const startTime = startTimeRef.current.get(label);
    if (startTime === undefined) {
      console.warn(`No profiling start time found for label: ${label}`);
      return 0;
    }

    const duration = performance.now() - startTime;
    startTimeRef.current.delete(label);

    if (import.meta.env.DEV) {
      console.log(`${profileName} - ${label}: ${duration.toFixed(2)}ms`);
    }

    return duration;
  }, [profileName]);

  return {
    startProfiling,
    endProfiling
  };
};