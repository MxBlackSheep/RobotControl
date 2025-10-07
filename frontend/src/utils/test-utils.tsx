/**
 * Test Utilities
 * 
 * Custom testing utilities for PyRobot components
 * Provides themed wrappers, mock providers, and common test helpers
 */

import React, { ReactElement } from 'react';
import { render, RenderOptions, RenderResult } from '@testing-library/react';
import { ThemeProvider, createTheme } from '@mui/material/styles';
import { BrowserRouter } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

// Import our types for better type safety in tests
import type { User } from '../types';

// Mock theme for consistent testing
const mockTheme = createTheme({
  palette: {
    mode: 'light',
    primary: {
      main: '#1976d2',
    },
    secondary: {
      main: '#dc004e',
    },
  },
});

// Mock user for authentication tests
export const mockUser: User = {
  id: '1',
  username: 'testuser',
  role: 'admin',
  email: 'test@example.com',
  created_at: '2024-01-01T00:00:00Z',
  last_login: '2024-01-01T00:00:00Z',
  active: true
};

// Mock auth context value
export const mockAuthContextValue = {
  user: mockUser,
  token: 'mock-token',
  isAuthenticated: true,
  login: jest.fn().mockResolvedValue(undefined),
  logout: jest.fn(),
  loading: false
};

// AuthContext mock provider
const MockAuthProvider: React.FC<{ 
  children: React.ReactNode; 
  value?: Partial<typeof mockAuthContextValue>;
}> = ({ children, value = {} }) => {
  // Since we can't import the actual AuthContext without circular dependencies,
  // we'll create a simple mock provider
  const contextValue = { ...mockAuthContextValue, ...value };
  return (
    <div data-testid="mock-auth-provider" data-auth={JSON.stringify(contextValue)}>
      {children}
    </div>
  );
};

// Query client for React Query tests
const createTestQueryClient = () => new QueryClient({
  defaultOptions: {
    queries: {
      retry: false,
      cacheTime: 0,
      staleTime: 0
    },
    mutations: {
      retry: false
    }
  }
});

// Custom render function with all providers
interface CustomRenderOptions extends Omit<RenderOptions, 'wrapper'> {
  withRouter?: boolean;
  withAuth?: boolean;
  withQuery?: boolean;
  authValue?: Partial<typeof mockAuthContextValue>;
  initialRoute?: string;
}

export function renderWithProviders(
  ui: ReactElement,
  {
    withRouter = true,
    withAuth = false,
    withQuery = false,
    authValue,
    initialRoute = '/',
    ...renderOptions
  }: CustomRenderOptions = {}
): RenderResult {
  function Wrapper({ children }: { children: React.ReactNode }) {
    let component = (
      <ThemeProvider theme={mockTheme}>
        {children}
      </ThemeProvider>
    );

    if (withQuery) {
      const queryClient = createTestQueryClient();
      component = (
        <QueryClientProvider client={queryClient}>
          {component}
        </QueryClientProvider>
      );
    }

    if (withAuth) {
      component = (
        <MockAuthProvider value={authValue}>
          {component}
        </MockAuthProvider>
      );
    }

    if (withRouter) {
      // Mock the router with initial route
      Object.defineProperty(window, 'location', {
        value: { pathname: initialRoute },
        writable: true
      });
      
      component = (
        <BrowserRouter>
          {component}
        </BrowserRouter>
      );
    }

    return component;
  }

  return render(ui, { wrapper: Wrapper, ...renderOptions });
}

// Specialized render functions
export const renderWithTheme = (ui: ReactElement, options?: RenderOptions) =>
  renderWithProviders(ui, { withRouter: false, withAuth: false, withQuery: false, ...options });

export const renderWithRouter = (ui: ReactElement, options?: CustomRenderOptions) =>
  renderWithProviders(ui, { withAuth: false, withQuery: false, ...options });

export const renderWithAuth = (ui: ReactElement, options?: CustomRenderOptions) =>
  renderWithProviders(ui, { withRouter: false, withQuery: false, withAuth: true, ...options });

export const renderWithAll = (ui: ReactElement, options?: CustomRenderOptions) =>
  renderWithProviders(ui, { withRouter: true, withAuth: true, withQuery: true, ...options });

// Mock data generators
export const mockTableData = {
  columns: ['id', 'name', 'status', 'created_at'],
  data: [
    [1, 'Test Item 1', 'active', '2024-01-01'],
    [2, 'Test Item 2', 'inactive', '2024-01-02'],
    [3, 'Test Item 3', 'active', '2024-01-03']
  ],
  total_rows: 3
};

export const mockCameraInfo = {
  id: 'camera1',
  name: 'Test Camera',
  url: 'http://localhost:8080/stream',
  status: 'online' as const,
  resolution: '1920x1080',
  fps: 30,
  last_frame_time: '2024-01-01T12:00:00Z'
};

export const mockSchedule = {
  id: 'schedule1',
  name: 'Test Schedule',
  experiment_name: 'Test Experiment',
  start_time: '2024-01-01T10:00:00Z',
  end_time: '2024-01-01T11:00:00Z',
  interval_minutes: 60,
  repeat_count: 1,
  is_recurring: false,
  enabled: true,
  status: 'pending' as const,
  priority: 'medium' as const,
  max_retries: 3,
  retry_delay_minutes: 5,
  created_at: '2024-01-01T09:00:00Z',
  updated_at: '2024-01-01T09:00:00Z'
};

// Helper functions for common test patterns
export const waitForLoadingToFinish = async () => {
  const { waitForElementToBeRemoved } = await import('@testing-library/react');
  await waitForElementToBeRemoved(
    () => document.querySelector('[data-testid="loading"]'),
    { timeout: 5000 }
  );
};

export const expectElementToBeVisible = (element: HTMLElement | null) => {
  expect(element).toBeInTheDocument();
  expect(element).toBeVisible();
};

export const expectElementToHaveAccessibleName = (element: HTMLElement | null, name: string) => {
  expect(element).toBeInTheDocument();
  expect(element).toHaveAccessibleName(name);
};

// Mock API responses
export const mockApiResponse = <T,>(data: T, success = true) => ({
  success,
  data: success ? data : undefined,
  error: success ? undefined : 'Mock error message',
  message: success ? 'Success' : 'Error occurred'
});

export const mockListResponse = <T,>(data: T[], total = data.length) => ({
  success: true,
  data,
  metadata: {
    total,
    page: 1,
    pageSize: 25,
    hasNext: false,
    hasPrev: false
  }
});

// Custom matchers (can be extended)
export const customMatchers = {
  toBeAccessible: async (element: HTMLElement) => {
    // Basic accessibility checks
    const hasAriaLabel = element.hasAttribute('aria-label') || element.hasAttribute('aria-labelledby');
    const hasRole = element.hasAttribute('role');
    const isButton = element.tagName === 'BUTTON';
    const isInteractive = isButton || element.hasAttribute('tabindex');
    
    if (isInteractive && !hasAriaLabel && !hasRole) {
      return {
        message: () => 'Interactive element should have aria-label or role',
        pass: false
      };
    }

    return { message: () => 'Element is accessible', pass: true };
  }
};

// Export commonly used testing library functions
export * from '@testing-library/react';
export { userEvent } from '@testing-library/user-event';

// Re-export our custom render as the default
export { renderWithProviders as render };
