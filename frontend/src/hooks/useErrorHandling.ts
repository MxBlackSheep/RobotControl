/**
 * useErrorHandling Hook - Centralized error management and reporting
 * 
 * Provides consistent error handling, categorization, and user-friendly messaging
 * Integrates with ErrorAlert component for display and retry functionality
 */

import { useState, useCallback, useRef } from 'react';
import { ErrorCategory } from '../components/ErrorAlert';

export interface ErrorInfo {
  message: string;
  category: ErrorCategory;
  severity: 'error' | 'warning' | 'info';
  timestamp: Date;
  context?: string;
  retryable?: boolean;
  retryCount?: number;
  originalError?: any;
}

export interface UseErrorHandlingOptions {
  /** Maximum number of errors to keep in history */
  maxErrorHistory?: number;
  /** Automatically categorize errors based on content */
  autoCategorize?: boolean;
  /** Enable error reporting/logging */
  enableReporting?: boolean;
  /** Context prefix for error messages */
  contextPrefix?: string;
}

/**
 * Custom hook for centralized error handling and management
 */
export const useErrorHandling = (options: UseErrorHandlingOptions = {}) => {
  const {
    maxErrorHistory = 10,
    autoCategorize = true,
    enableReporting = true,
    contextPrefix = ''
  } = options;

  const [currentError, setCurrentError] = useState<ErrorInfo | null>(null);
  const [errorHistory, setErrorHistory] = useState<ErrorInfo[]>([]);
  const errorIdRef = useRef(0);

  // Auto-categorize errors based on content and HTTP status
  const categorizeError = useCallback((error: any): ErrorCategory => {
    if (!autoCategorize) return 'unknown';

    const errorMessage = error?.message?.toLowerCase() || '';
    const status = error?.response?.status || error?.status;

    // HTTP status-based categorization
    if (status) {
      if (status === 401) return 'authentication';
      if (status === 403) return 'authorization';
      if (status === 404) return 'client';
      if (status === 408) return 'timeout';
      if (status >= 500) return 'server';
      if (status >= 400) return 'client';
    }

    // Message content-based categorization
    if (errorMessage.includes('network') || errorMessage.includes('connection')) {
      return 'network';
    }
    if (errorMessage.includes('timeout') || errorMessage.includes('timed out')) {
      return 'timeout';
    }
    if (errorMessage.includes('unauthorized') || errorMessage.includes('login')) {
      return 'authentication';
    }
    if (errorMessage.includes('forbidden') || errorMessage.includes('permission')) {
      return 'authorization';
    }
    if (errorMessage.includes('validation') || errorMessage.includes('invalid')) {
      return 'validation';
    }
    if (errorMessage.includes('server error') || errorMessage.includes('internal')) {
      return 'server';
    }

    return 'unknown';
  }, [autoCategorize]);

  // Determine error severity
  const determineSeverity = useCallback((category: ErrorCategory): ErrorInfo['severity'] => {
    switch (category) {
      case 'authentication':
      case 'authorization':
        return 'warning';
      case 'validation':
        return 'info';
      case 'network':
      case 'server':
      case 'timeout':
      default:
        return 'error';
    }
  }, []);

  // Check if error is retryable
  const isRetryable = useCallback((category: ErrorCategory, status?: number): boolean => {
    if (status === 401 || status === 403) return false;
    
    return ['network', 'server', 'timeout', 'unknown'].includes(category);
  }, []);

  // Format user-friendly error message
  const formatErrorMessage = useCallback((error: any, context?: string): string => {
    const baseContext = contextPrefix ? `${contextPrefix}: ` : '';
    const fullContext = context ? `${baseContext}${context} - ` : baseContext;

    // Extract meaningful message from different error formats
    let message = '';
    
    if (error?.response?.data?.detail) {
      message = error.response.data.detail;
    } else if (error?.response?.data?.message) {
      message = error.response.data.message;
    } else if (error?.message) {
      message = error.message;
    } else if (typeof error === 'string') {
      message = error;
    } else {
      message = 'An unexpected error occurred';
    }

    return `${fullContext}${message}`;
  }, [contextPrefix]);

  // Report error (for analytics/logging)
  const reportError = useCallback((errorInfo: ErrorInfo) => {
    if (!enableReporting) return;

    // In production, this could send to error reporting service
    console.error('Error reported:', {
      id: errorIdRef.current,
      message: errorInfo.message,
      category: errorInfo.category,
      severity: errorInfo.severity,
      timestamp: errorInfo.timestamp,
      context: errorInfo.context,
      originalError: errorInfo.originalError
    });
  }, [enableReporting]);

  // Handle new error
  const handleError = useCallback((
    error: any,
    context?: string,
    overrides?: Partial<Omit<ErrorInfo, 'message' | 'timestamp'>>
  ): ErrorInfo => {
    const category = overrides?.category || categorizeError(error);
    const severity = overrides?.severity || determineSeverity(category);
    const retryable = overrides?.retryable ?? isRetryable(category, error?.response?.status);
    
    const errorInfo: ErrorInfo = {
      message: formatErrorMessage(error, context),
      category,
      severity,
      timestamp: new Date(),
      context,
      retryable,
      retryCount: 0,
      originalError: error,
      ...overrides
    };

    setCurrentError(errorInfo);
    
    // Add to error history
    setErrorHistory(prev => {
      const newHistory = [errorInfo, ...prev].slice(0, maxErrorHistory);
      return newHistory;
    });

    // Report error
    reportError(errorInfo);
    errorIdRef.current++;

    return errorInfo;
  }, [categorizeError, determineSeverity, isRetryable, formatErrorMessage, maxErrorHistory, reportError]);

  // Clear current error
  const clearError = useCallback(() => {
    setCurrentError(null);
  }, []);

  // Clear all errors
  const clearAllErrors = useCallback(() => {
    setCurrentError(null);
    setErrorHistory([]);
  }, []);

  // Retry with error tracking
  const handleRetry = useCallback((retryFn: () => Promise<any> | void): Promise<void> => {
    if (!currentError?.retryable) {
      return Promise.reject(new Error('Current error is not retryable'));
    }

    const updatedError = {
      ...currentError,
      retryCount: (currentError.retryCount || 0) + 1
    };
    setCurrentError(updatedError);

    return Promise.resolve(retryFn()).catch((error) => {
      // Handle retry failure
      handleError(error, `Retry attempt ${updatedError.retryCount} failed`);
    });
  }, [currentError, handleError]);

  // Get errors by category
  const getErrorsByCategory = useCallback((category: ErrorCategory): ErrorInfo[] => {
    return errorHistory.filter(error => error.category === category);
  }, [errorHistory]);

  // Get recent errors
  const getRecentErrors = useCallback((limit: number = 5): ErrorInfo[] => {
    return errorHistory.slice(0, limit);
  }, [errorHistory]);

  return {
    // Current state
    currentError,
    errorHistory,
    hasError: currentError !== null,
    
    // Actions
    handleError,
    clearError,
    clearAllErrors,
    handleRetry,
    
    // Utilities
    getErrorsByCategory,
    getRecentErrors,
    categorizeError,
    formatErrorMessage,
    
    // Stats
    errorCount: errorHistory.length,
    hasRetryableError: currentError?.retryable || false
  };
};

/**
 * Specialized hook for API error handling
 */
export const useApiErrorHandling = (contextPrefix?: string) => {
  return useErrorHandling({
    contextPrefix: contextPrefix || 'API Error',
    autoCategorize: true,
    enableReporting: true,
    maxErrorHistory: 20
  });
};

/**
 * Hook for global error boundary integration
 */
export const useGlobalErrorHandler = () => {
  const errorHandler = useErrorHandling({
    contextPrefix: 'Application Error',
    maxErrorHistory: 50,
    enableReporting: true
  });

  // Global error handler for unhandled errors
  const handleGlobalError = useCallback((error: ErrorEvent) => {
    errorHandler.handleError(error.error || error.message, 'Unhandled Error');
  }, [errorHandler]);

  // Global promise rejection handler
  const handleUnhandledRejection = useCallback((event: PromiseRejectionEvent) => {
    errorHandler.handleError(event.reason, 'Unhandled Promise Rejection');
  }, [errorHandler]);

  return {
    ...errorHandler,
    handleGlobalError,
    handleUnhandledRejection
  };
};