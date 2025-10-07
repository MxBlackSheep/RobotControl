/**
 * PerformanceMonitor Utility for PyRobot Optimization
 * 
 * Comprehensive performance tracking and reporting system using the Performance API
 * Tracks page load times, component render times, user interactions, and API calls
 * Integrates with existing logging infrastructure for performance analysis
 */

import React from 'react';

export interface PerformanceMetric {
  name: string;
  value: number;
  timestamp: number;
  type: 'navigation' | 'render' | 'interaction' | 'api' | 'custom';
  metadata?: Record<string, any>;
}

export interface PerformanceThresholds {
  pageLoad: number;      // ms - Target: 2000ms
  apiResponse: number;   // ms - Target: 500ms  
  renderTime: number;    // ms - Target: 16ms (60fps)
  interaction: number;   // ms - Target: 100ms
}

export interface PerformanceReport {
  timestamp: number;
  metrics: PerformanceMetric[];
  summary: {
    averagePageLoad: number;
    averageApiResponse: number;
    averageRenderTime: number;
    slowestOperations: PerformanceMetric[];
    thresholdViolations: PerformanceMetric[];
  };
  bundleInfo: {
    initialBundleSize: number;
    totalChunks: number;
    lazyLoadedChunks: number;
  };
}

class PerformanceMonitorClass {
  private metrics: PerformanceMetric[] = [];
  private thresholds: PerformanceThresholds = {
    pageLoad: 2000,
    apiResponse: 500,
    renderTime: 16,
    interaction: 100,
  };
  private isEnabled = true;
  private maxMetrics = 1000; // Prevent memory leaks

  constructor() {
    this.initializeNavigationTracking();
    this.initializeResourceTracking();
    this.initializeLongTaskTracking();
  }

  /**
   * Initialize navigation performance tracking
   */
  private initializeNavigationTracking(): void {
    if (typeof window === 'undefined' || !window.performance) return;

    // Track initial page load
    window.addEventListener('load', () => {
      setTimeout(() => {
        const navigation = performance.getEntriesByType('navigation')[0] as PerformanceNavigationTiming;
        if (navigation) {
          this.trackMetric({
            name: 'page_load',
            value: navigation.loadEventEnd - navigation.fetchStart,
            type: 'navigation',
            metadata: {
              domContentLoaded: navigation.domContentLoadedEventEnd - navigation.fetchStart,
              firstPaint: this.getFirstPaint(),
              firstContentfulPaint: this.getFirstContentfulPaint(),
            }
          });
        }
      }, 0);
    });

    // Track route changes (for SPA)
    this.trackRouteChanges();
  }

  /**
   * Initialize resource loading tracking
   */
  private initializeResourceTracking(): void {
    if (typeof window === 'undefined' || !window.performance) return;

    const observer = new PerformanceObserver((list) => {
      for (const entry of list.getEntries()) {
        if (entry.entryType === 'resource') {
          const resource = entry as PerformanceResourceTiming;
          
          // Track bundle loading
          if (resource.name.includes('.js') || resource.name.includes('.css')) {
            this.trackMetric({
              name: 'bundle_load',
              value: resource.responseEnd - resource.startTime,
              type: 'render',
              metadata: {
                url: resource.name,
                size: resource.transferSize,
                cached: resource.transferSize === 0,
              }
            });
          }
        }
      }
    });

    try {
      observer.observe({ entryTypes: ['resource'] });
    } catch (error) {
      console.warn('Resource performance tracking not supported:', error);
    }
  }

  /**
   * Initialize long task tracking for performance bottlenecks
   */
  private initializeLongTaskTracking(): void {
    if (typeof window === 'undefined' || !window.PerformanceObserver) return;

    const observer = new PerformanceObserver((list) => {
      for (const entry of list.getEntries()) {
        this.trackMetric({
          name: 'long_task',
          value: entry.duration,
          type: 'render',
          metadata: {
            startTime: entry.startTime,
            attribution: (entry as any).attribution,
          }
        });
      }
    });

    try {
      observer.observe({ entryTypes: ['longtask'] });
    } catch (error) {
      console.warn('Long task tracking not supported:', error);
    }
  }

  /**
   * Track route changes for SPA performance
   */
  private trackRouteChanges(): void {
    let currentPath = window.location.pathname;
    let routeStartTime = performance.now();

    const trackRouteChange = () => {
      const newPath = window.location.pathname;
      if (newPath !== currentPath) {
        const routeTime = performance.now() - routeStartTime;
        
        this.trackMetric({
          name: 'route_change',
          value: routeTime,
          type: 'navigation',
          metadata: {
            from: currentPath,
            to: newPath,
          }
        });

        currentPath = newPath;
        routeStartTime = performance.now();
      }
    };

    // Listen for route changes
    window.addEventListener('popstate', trackRouteChange);
    
    // Track programmatic route changes (for React Router)
    const originalPushState = history.pushState;
    const originalReplaceState = history.replaceState;
    
    history.pushState = function(...args) {
      originalPushState.apply(history, args);
      trackRouteChange();
    };
    
    history.replaceState = function(...args) {
      originalReplaceState.apply(history, args);
      trackRouteChange();
    };
  }

  /**
   * Track a custom performance metric
   */
  trackMetric(metric: Omit<PerformanceMetric, 'timestamp'>): void {
    if (!this.isEnabled) return;

    const fullMetric: PerformanceMetric = {
      ...metric,
      timestamp: Date.now(),
    };

    this.metrics.push(fullMetric);

    // Check thresholds and log violations
    this.checkThresholds(fullMetric);

    // Prevent memory leaks by limiting stored metrics
    if (this.metrics.length > this.maxMetrics) {
      this.metrics = this.metrics.slice(-this.maxMetrics / 2);
    }

    // Log performance data in development
    if (import.meta.env?.DEV) {
      console.log(`[Performance] ${metric.name}: ${metric.value.toFixed(2)}ms`, metric.metadata);
    }
  }

  /**
   * Track component render performance
   */
  trackRender(componentName: string, renderTime: number, metadata?: Record<string, any>): void {
    this.trackMetric({
      name: `render_${componentName}`,
      value: renderTime,
      type: 'render',
      metadata: {
        component: componentName,
        ...metadata,
      }
    });
  }

  /**
   * Track API call performance
   */
  trackApiCall(endpoint: string, duration: number, metadata?: Record<string, any>): void {
    this.trackMetric({
      name: `api_${endpoint.replace(/[^a-zA-Z0-9]/g, '_')}`,
      value: duration,
      type: 'api',
      metadata: {
        endpoint,
        ...metadata,
      }
    });
  }

  /**
   * Track user interaction performance
   */
  trackInteraction(action: string, duration: number, metadata?: Record<string, any>): void {
    this.trackMetric({
      name: `interaction_${action}`,
      value: duration,
      type: 'interaction',
      metadata: {
        action,
        ...metadata,
      }
    });
  }

  /**
   * Check if metric violates performance thresholds
   */
  private checkThresholds(metric: PerformanceMetric): void {
    const threshold = this.getThresholdForMetric(metric);
    if (threshold && metric.value > threshold) {
      console.warn(
        `[Performance Warning] ${metric.name} exceeded threshold: ${metric.value.toFixed(2)}ms > ${threshold}ms`,
        metric.metadata
      );
      
      // Could integrate with error reporting service here
      this.reportThresholdViolation(metric, threshold);
    }
  }

  /**
   * Get appropriate threshold for a metric
   */
  private getThresholdForMetric(metric: PerformanceMetric): number | null {
    switch (metric.type) {
      case 'navigation':
        return metric.name.includes('page_load') ? this.thresholds.pageLoad : null;
      case 'api':
        return this.thresholds.apiResponse;
      case 'render':
        return this.thresholds.renderTime;
      case 'interaction':
        return this.thresholds.interaction;
      default:
        return null;
    }
  }

  /**
   * Report threshold violation (could integrate with monitoring service)
   */
  private reportThresholdViolation(metric: PerformanceMetric, threshold: number): void {
    // In production, this could send data to monitoring service
    if (import.meta.env?.PROD) {
      // Example: sendToMonitoringService({ metric, threshold, violation: true });
    }
  }

  /**
   * Get First Paint timing
   */
  private getFirstPaint(): number | null {
    const paints = performance.getEntriesByType('paint');
    const firstPaint = paints.find(p => p.name === 'first-paint');
    return firstPaint ? firstPaint.startTime : null;
  }

  /**
   * Get First Contentful Paint timing
   */
  private getFirstContentfulPaint(): number | null {
    const paints = performance.getEntriesByType('paint');
    const fcp = paints.find(p => p.name === 'first-contentful-paint');
    return fcp ? fcp.startTime : null;
  }

  /**
   * Generate comprehensive performance report
   */
  generateReport(): PerformanceReport {
    const now = Date.now();
    const recentMetrics = this.metrics.filter(m => now - m.timestamp < 5 * 60 * 1000); // Last 5 minutes

    const pageLoadMetrics = recentMetrics.filter(m => m.type === 'navigation');
    const apiMetrics = recentMetrics.filter(m => m.type === 'api');
    const renderMetrics = recentMetrics.filter(m => m.type === 'render');

    const slowestOperations = [...recentMetrics]
      .sort((a, b) => b.value - a.value)
      .slice(0, 10);

    const thresholdViolations = recentMetrics.filter(m => {
      const threshold = this.getThresholdForMetric(m);
      return threshold && m.value > threshold;
    });

    return {
      timestamp: now,
      metrics: recentMetrics,
      summary: {
        averagePageLoad: this.calculateAverage(pageLoadMetrics),
        averageApiResponse: this.calculateAverage(apiMetrics),
        averageRenderTime: this.calculateAverage(renderMetrics),
        slowestOperations,
        thresholdViolations,
      },
      bundleInfo: this.getBundleInfo(),
    };
  }

  /**
   * Calculate average value from metrics
   */
  private calculateAverage(metrics: PerformanceMetric[]): number {
    if (metrics.length === 0) return 0;
    return metrics.reduce((sum, m) => sum + m.value, 0) / metrics.length;
  }

  /**
   * Get bundle information from performance entries
   */
  private getBundleInfo(): PerformanceReport['bundleInfo'] {
    const resources = performance.getEntriesByType('resource') as PerformanceResourceTiming[];
    const jsResources = resources.filter(r => r.name.includes('.js'));
    
    return {
      initialBundleSize: jsResources.reduce((sum, r) => sum + (r.transferSize || 0), 0),
      totalChunks: jsResources.length,
      lazyLoadedChunks: jsResources.filter(r => r.name.includes('lazy') || r.name.includes('chunk')).length,
    };
  }

  /**
   * Export performance data as CSV
   */
  exportToCSV(): string {
    const headers = ['Timestamp', 'Name', 'Value (ms)', 'Type', 'Metadata'];
    const rows = this.metrics.map(m => [
      new Date(m.timestamp).toISOString(),
      m.name,
      m.value.toString(),
      m.type,
      JSON.stringify(m.metadata || {}),
    ]);

    return [headers, ...rows].map(row => row.map(cell => `"${cell}"`).join(',')).join('\n');
  }

  /**
   * Clear all stored metrics
   */
  clear(): void {
    this.metrics = [];
  }

  /**
   * Enable/disable performance monitoring
   */
  setEnabled(enabled: boolean): void {
    this.isEnabled = enabled;
  }

  /**
   * Update performance thresholds
   */
  updateThresholds(thresholds: Partial<PerformanceThresholds>): void {
    this.thresholds = { ...this.thresholds, ...thresholds };
  }

  /**
   * Get current metrics
   */
  getMetrics(): PerformanceMetric[] {
    return [...this.metrics];
  }

  /**
   * Log current performance summary to console
   */
  logSummary(): void {
    const report = this.generateReport();
    
    console.group('🔍 Performance Summary');
    console.log('📊 Metrics collected:', report.metrics.length);
    console.log('⏱️  Average page load:', `${report.summary.averagePageLoad.toFixed(2)}ms`);
    console.log('🌐 Average API response:', `${report.summary.averageApiResponse.toFixed(2)}ms`);
    console.log('🎨 Average render time:', `${report.summary.averageRenderTime.toFixed(2)}ms`);
    console.log('📦 Bundle size:', `${(report.bundleInfo.initialBundleSize / 1024).toFixed(2)} KB`);
    console.log('🧩 Total chunks:', report.bundleInfo.totalChunks);
    
    if (report.summary.thresholdViolations.length > 0) {
      console.warn('⚠️  Threshold violations:', report.summary.thresholdViolations.length);
    }
    
    if (report.summary.slowestOperations.length > 0) {
      console.log('🐌 Slowest operations:', report.summary.slowestOperations.slice(0, 3));
    }
    
    console.groupEnd();
  }
}

// Create singleton instance
export const PerformanceMonitor = new PerformanceMonitorClass();

// Export utilities for React integration
export const usePerformanceTracking = () => {
  return {
    trackRender: PerformanceMonitor.trackRender.bind(PerformanceMonitor),
    trackInteraction: PerformanceMonitor.trackInteraction.bind(PerformanceMonitor),
    trackApiCall: PerformanceMonitor.trackApiCall.bind(PerformanceMonitor),
  };
};

// Higher-order component for automatic render tracking
export function withPerformanceTracking<P extends object>(
  WrappedComponent: React.ComponentType<P>,
  componentName?: string
) {
  const displayName = componentName || WrappedComponent.displayName || WrappedComponent.name || 'Component';
  
  const EnhancedComponent: React.FC<P> = (props) => {
    const renderStart = performance.now();
    
    React.useEffect(() => {
      const renderTime = performance.now() - renderStart;
      PerformanceMonitor.trackRender(displayName, renderTime);
    });

    return React.createElement(WrappedComponent, props);
  };

  EnhancedComponent.displayName = `withPerformanceTracking(${displayName})`;
  return EnhancedComponent;
}

export default PerformanceMonitor;