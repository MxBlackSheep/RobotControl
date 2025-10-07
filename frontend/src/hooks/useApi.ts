/**
 * useApi Hook - Consistent API call handling with loading states and error management
 * 
 * Provides standardized loading, error, and success states for API calls
 * Includes automatic retry functionality and consistent error handling
 */

import { useState, useCallback, useRef } from 'react';

export interface ApiState<T> {
  data: T | null;
  loading: boolean;
  error: string | null;
  success: boolean;
}

export interface UseApiOptions {
  /** Initial data value */
  initialData?: any;
  /** Automatically clear errors after specified milliseconds */
  errorTimeout?: number;
  /** Enable automatic retry on failure */
  retryOnError?: boolean;
  /** Maximum number of retry attempts */
  maxRetries?: number;
  /** Retry delay in milliseconds */
  retryDelay?: number;
}

export interface UseApiReturn<T> extends ApiState<T> {
  /** Execute API call */
  execute: (apiCall: () => Promise<T>) => Promise<T | null>;
  /** Clear current error */
  clearError: () => void;
  /** Clear all state and reset to initial */
  reset: () => void;
  /** Set loading state manually */
  setLoading: (loading: boolean) => void;
  /** Set error manually */
  setError: (error: string | null) => void;
}

/**
 * Custom hook for handling API calls with consistent loading and error states
 */
export const useApi = <T = any>(options: UseApiOptions = {}): UseApiReturn<T> => {
  const {
    initialData = null,
    errorTimeout = 0,
    retryOnError = false,
    maxRetries = 3,
    retryDelay = 1000
  } = options;

  const [state, setState] = useState<ApiState<T>>({
    data: initialData,
    loading: false,
    error: null,
    success: false
  });

  const retryCountRef = useRef(0);
  const errorTimeoutRef = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);

  const clearError = useCallback(() => {
    setState(prev => ({ ...prev, error: null }));
    if (errorTimeoutRef.current) {
      clearTimeout(errorTimeoutRef.current);
    }
  }, []);

  const setError = useCallback((error: string | null) => {
    setState(prev => ({ ...prev, error, loading: false }));
    
    if (error && errorTimeout > 0) {
      if (errorTimeoutRef.current) {
        clearTimeout(errorTimeoutRef.current);
      }
      errorTimeoutRef.current = setTimeout(() => {
        clearError();
      }, errorTimeout);
    }
  }, [errorTimeout, clearError]);

  const setLoading = useCallback((loading: boolean) => {
    setState(prev => ({ ...prev, loading }));
  }, []);

  const reset = useCallback(() => {
    setState({
      data: initialData,
      loading: false,
      error: null,
      success: false
    });
    retryCountRef.current = 0;
    if (errorTimeoutRef.current) {
      clearTimeout(errorTimeoutRef.current);
    }
  }, [initialData]);

  const executeWithRetry = useCallback(async (apiCall: () => Promise<T>): Promise<T | null> => {
    try {
      const result = await apiCall();
      setState(prev => ({ 
        ...prev, 
        data: result, 
        loading: false, 
        error: null, 
        success: true 
      }));
      retryCountRef.current = 0;
      return result;
    } catch (err: any) {
      const errorMessage = err.response?.data?.detail || err.message || 'An error occurred';
      
      // Retry logic
      if (retryOnError && retryCountRef.current < maxRetries) {
        retryCountRef.current++;
        console.warn(`API call failed, retrying (${retryCountRef.current}/${maxRetries}):`, errorMessage);
        
        await new Promise(resolve => setTimeout(resolve, retryDelay));
        return executeWithRetry(apiCall);
      }
      
      setError(errorMessage);
      retryCountRef.current = 0;
      return null;
    }
  }, [retryOnError, maxRetries, retryDelay, setError]);

  const execute = useCallback(async (apiCall: () => Promise<T>): Promise<T | null> => {
    setState(prev => ({ 
      ...prev, 
      loading: true, 
      error: null, 
      success: false 
    }));
    
    return executeWithRetry(apiCall);
  }, [executeWithRetry]);

  return {
    ...state,
    execute,
    clearError,
    reset,
    setLoading,
    setError
  };
};

/**
 * Specialized hook for API calls that return lists/arrays
 */
export const useApiList = <T = any>(options: UseApiOptions = {}) => {
  return useApi<T[]>({ initialData: [], ...options });
};

/**
 * Hook for paginated API calls
 */
export const usePaginatedApi = <T = any>(options: UseApiOptions = {}) => {
  const [pagination, setPagination] = useState({
    page: 1,
    pageSize: 10,
    total: 0,
    hasNext: false,
    hasPrev: false
  });

  const api = useApiList<T>(options);

  const updatePagination = useCallback((paginationData: Partial<typeof pagination>) => {
    setPagination(prev => ({ ...prev, ...paginationData }));
  }, []);

  const nextPage = useCallback(() => {
    if (pagination.hasNext) {
      setPagination(prev => ({ ...prev, page: prev.page + 1 }));
    }
  }, [pagination.hasNext]);

  const prevPage = useCallback(() => {
    if (pagination.hasPrev) {
      setPagination(prev => ({ ...prev, page: prev.page - 1 }));
    }
  }, [pagination.hasPrev]);

  const goToPage = useCallback((page: number) => {
    if (page >= 1 && page <= Math.ceil(pagination.total / pagination.pageSize)) {
      setPagination(prev => ({ ...prev, page }));
    }
  }, [pagination.total, pagination.pageSize]);

  return {
    ...api,
    pagination,
    updatePagination,
    nextPage,
    prevPage,
    goToPage
  };
};