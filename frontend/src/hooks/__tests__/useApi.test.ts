/**
 * useApi Hook Tests
 * 
 * Tests for the custom API handling hook
 * Validates loading states, error handling, and retry functionality
 */

import { renderHook, act, waitFor } from '@testing-library/react';
import { useApi, useApiList, usePaginatedApi } from '../useApi';

// Mock async API call
const mockApiCall = jest.fn();
const mockSuccessResponse = { data: 'test data' };
const mockErrorResponse = new Error('API call failed');

describe('useApi', () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  describe('Basic functionality', () => {
    it('initializes with correct default state', () => {
      const { result } = renderHook(() => useApi());
      
      expect(result.current.data).toBeNull();
      expect(result.current.loading).toBe(false);
      expect(result.current.error).toBeNull();
      expect(result.current.success).toBe(false);
    });

    it('initializes with custom initial data', () => {
      const initialData = { test: 'data' };
      const { result } = renderHook(() => useApi({ initialData }));
      
      expect(result.current.data).toEqual(initialData);
    });

    it('sets loading state during API call', async () => {
      mockApiCall.mockImplementation(() => new Promise(resolve => 
        setTimeout(() => resolve(mockSuccessResponse), 100)
      ));
      
      const { result } = renderHook(() => useApi());
      
      act(() => {
        result.current.execute(mockApiCall);
      });
      
      expect(result.current.loading).toBe(true);
      expect(result.current.error).toBeNull();
      expect(result.current.success).toBe(false);
    });

    it('handles successful API call', async () => {
      mockApiCall.mockResolvedValue(mockSuccessResponse);
      
      const { result } = renderHook(() => useApi());
      
      let response;
      await act(async () => {
        response = await result.current.execute(mockApiCall);
      });
      
      expect(response).toEqual(mockSuccessResponse);
      expect(result.current.data).toEqual(mockSuccessResponse);
      expect(result.current.loading).toBe(false);
      expect(result.current.error).toBeNull();
      expect(result.current.success).toBe(true);
    });

    it('handles API call error', async () => {
      mockApiCall.mockRejectedValue(mockErrorResponse);
      
      const { result } = renderHook(() => useApi());
      
      let response;
      await act(async () => {
        response = await result.current.execute(mockApiCall);
      });
      
      expect(response).toBeNull();
      expect(result.current.data).toBeNull();
      expect(result.current.loading).toBe(false);
      expect(result.current.error).toBe('API call failed');
      expect(result.current.success).toBe(false);
    });
  });

  describe('Error handling', () => {
    it('extracts error message from response object', async () => {
      const errorWithResponse = {
        response: {
          data: {
            detail: 'Server validation error'
          }
        }
      };
      mockApiCall.mockRejectedValue(errorWithResponse);
      
      const { result } = renderHook(() => useApi());
      
      await act(async () => {
        await result.current.execute(mockApiCall);
      });
      
      expect(result.current.error).toBe('Server validation error');
    });

    it('handles errors without message', async () => {
      mockApiCall.mockRejectedValue({});
      
      const { result } = renderHook(() => useApi());
      
      await act(async () => {
        await result.current.execute(mockApiCall);
      });
      
      expect(result.current.error).toBe('An error occurred');
    });

    it('clears error when clearError is called', () => {
      const { result } = renderHook(() => useApi());
      
      act(() => {
        result.current.setError('Test error');
      });
      
      expect(result.current.error).toBe('Test error');
      
      act(() => {
        result.current.clearError();
      });
      
      expect(result.current.error).toBeNull();
    });

    it('auto-clears error after timeout', async () => {
      jest.useFakeTimers();
      
      const { result } = renderHook(() => useApi({ errorTimeout: 5000 }));
      
      act(() => {
        result.current.setError('Test error');
      });
      
      expect(result.current.error).toBe('Test error');
      
      act(() => {
        jest.advanceTimersByTime(5000);
      });
      
      await waitFor(() => {
        expect(result.current.error).toBeNull();
      });
      
      jest.useRealTimers();
    });
  });

  describe('Retry functionality', () => {
    it('retries failed requests when enabled', async () => {
      mockApiCall
        .mockRejectedValueOnce(mockErrorResponse)
        .mockResolvedValueOnce(mockSuccessResponse);
      
      const { result } = renderHook(() => useApi({ 
        retryOnError: true, 
        maxRetries: 1,
        retryDelay: 100
      }));
      
      let response;
      await act(async () => {
        response = await result.current.execute(mockApiCall);
      });
      
      expect(mockApiCall).toHaveBeenCalledTimes(2);
      expect(response).toEqual(mockSuccessResponse);
      expect(result.current.success).toBe(true);
    });

    it('stops retrying after max attempts', async () => {
      mockApiCall.mockRejectedValue(mockErrorResponse);
      
      const { result } = renderHook(() => useApi({ 
        retryOnError: true, 
        maxRetries: 2,
        retryDelay: 10
      }));
      
      await act(async () => {
        await result.current.execute(mockApiCall);
      });
      
      expect(mockApiCall).toHaveBeenCalledTimes(3); // Initial + 2 retries
      expect(result.current.error).toBe('API call failed');
    });

    it('waits for retry delay between attempts', async () => {
      jest.useFakeTimers();
      mockApiCall.mockRejectedValue(mockErrorResponse);
      
      const { result } = renderHook(() => useApi({ 
        retryOnError: true, 
        maxRetries: 1,
        retryDelay: 1000
      }));
      
      const executePromise = act(async () => {
        return result.current.execute(mockApiCall);
      });
      
      // Fast-forward time to trigger retry
      act(() => {
        jest.advanceTimersByTime(1000);
      });
      
      await executePromise;
      
      expect(mockApiCall).toHaveBeenCalledTimes(2);
      jest.useRealTimers();
    });
  });

  describe('State management', () => {
    it('resets to initial state', () => {
      const initialData = { initial: 'data' };
      const { result } = renderHook(() => useApi({ initialData }));
      
      // Change state
      act(() => {
        result.current.setError('Test error');
        result.current.setLoading(true);
      });
      
      expect(result.current.error).toBe('Test error');
      expect(result.current.loading).toBe(true);
      
      // Reset
      act(() => {
        result.current.reset();
      });
      
      expect(result.current.data).toEqual(initialData);
      expect(result.current.loading).toBe(false);
      expect(result.current.error).toBeNull();
      expect(result.current.success).toBe(false);
    });

    it('manually sets loading state', () => {
      const { result } = renderHook(() => useApi());
      
      act(() => {
        result.current.setLoading(true);
      });
      
      expect(result.current.loading).toBe(true);
      
      act(() => {
        result.current.setLoading(false);
      });
      
      expect(result.current.loading).toBe(false);
    });
  });
});

describe('useApiList', () => {
  it('initializes with empty array', () => {
    const { result } = renderHook(() => useApiList());
    
    expect(result.current.data).toEqual([]);
  });

  it('handles array responses', async () => {
    const arrayData = [{ id: 1 }, { id: 2 }];
    mockApiCall.mockResolvedValue(arrayData);
    
    const { result } = renderHook(() => useApiList());
    
    await act(async () => {
      await result.current.execute(mockApiCall);
    });
    
    expect(result.current.data).toEqual(arrayData);
  });
});

describe('usePaginatedApi', () => {
  it('initializes with default pagination state', () => {
    const { result } = renderHook(() => usePaginatedApi());
    
    expect(result.current.pagination.page).toBe(1);
    expect(result.current.pagination.pageSize).toBe(10);
    expect(result.current.pagination.total).toBe(0);
    expect(result.current.pagination.hasNext).toBe(false);
    expect(result.current.pagination.hasPrev).toBe(false);
  });

  it('updates pagination data', () => {
    const { result } = renderHook(() => usePaginatedApi());
    
    act(() => {
      result.current.updatePagination({
        total: 100,
        hasNext: true,
        hasPrev: false
      });
    });
    
    expect(result.current.pagination.total).toBe(100);
    expect(result.current.pagination.hasNext).toBe(true);
    expect(result.current.pagination.hasPrev).toBe(false);
  });

  it('navigates to next page when available', () => {
    const { result } = renderHook(() => usePaginatedApi());
    
    act(() => {
      result.current.updatePagination({ hasNext: true });
    });
    
    act(() => {
      result.current.nextPage();
    });
    
    expect(result.current.pagination.page).toBe(2);
  });

  it('does not navigate to next page when unavailable', () => {
    const { result } = renderHook(() => usePaginatedApi());
    
    // hasNext is false by default
    act(() => {
      result.current.nextPage();
    });
    
    expect(result.current.pagination.page).toBe(1);
  });

  it('navigates to previous page when available', () => {
    const { result } = renderHook(() => usePaginatedApi());
    
    act(() => {
      result.current.updatePagination({ page: 2, hasPrev: true });
    });
    
    act(() => {
      result.current.prevPage();
    });
    
    expect(result.current.pagination.page).toBe(1);
  });

  it('navigates to specific page within bounds', () => {
    const { result } = renderHook(() => usePaginatedApi());
    
    act(() => {
      result.current.updatePagination({ 
        total: 100, 
        pageSize: 10 // 10 pages total
      });
    });
    
    act(() => {
      result.current.goToPage(5);
    });
    
    expect(result.current.pagination.page).toBe(5);
  });

  it('does not navigate to page outside bounds', () => {
    const { result } = renderHook(() => usePaginatedApi());
    
    act(() => {
      result.current.updatePagination({ 
        total: 50, 
        pageSize: 10 // 5 pages total
      });
    });
    
    // Try to go to page 10 (out of bounds)
    act(() => {
      result.current.goToPage(10);
    });
    
    expect(result.current.pagination.page).toBe(1); // Should remain unchanged
  });
});

describe('Edge cases', () => {
  it('handles concurrent API calls correctly', async () => {
    const slowCall = () => new Promise(resolve => 
      setTimeout(() => resolve('slow'), 200)
    );
    const fastCall = () => new Promise(resolve => 
      setTimeout(() => resolve('fast'), 100)
    );
    
    const { result } = renderHook(() => useApi());
    
    // Start both calls
    const slowPromise = act(async () => {
      return result.current.execute(slowCall);
    });
    
    const fastPromise = act(async () => {
      return result.current.execute(fastCall);
    });
    
    const [slowResult, fastResult] = await Promise.all([slowPromise, fastPromise]);
    
    // The last call should win
    expect(result.current.data).toBe('fast');
  });

  it('handles API call cancellation gracefully', async () => {
    let resolveFn: (value: any) => void;
    mockApiCall.mockImplementation(() => new Promise(resolve => {
      resolveFn = resolve;
    }));
    
    const { result } = renderHook(() => useApi());
    
    // Start API call
    const promise = act(async () => {
      return result.current.execute(mockApiCall);
    });
    
    expect(result.current.loading).toBe(true);
    
    // Reset while call is in progress
    act(() => {
      result.current.reset();
    });
    
    // Resolve the original call
    resolveFn!('delayed response');
    
    await promise;
    
    // State should remain reset
    expect(result.current.loading).toBe(false);
    expect(result.current.data).toBeNull();
  });
});