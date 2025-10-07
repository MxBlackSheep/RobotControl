import React, { ComponentType, LazyExoticComponent } from 'react';

/**
 * Bundle optimizer utility for implementing code splitting and lazy loading
 * Provides centralized lazy loading logic with error handling and fallbacks
 */

export interface LoadComponentOptions {
  fallback?: ComponentType;
  retryAttempts?: number;
  retryDelay?: number;
}

/**
 * Creates a lazy-loaded component with error handling and retry logic
 */
export function loadComponent<T extends ComponentType<any>>(
  importFn: () => Promise<{ default: T }>,
  options: LoadComponentOptions = {}
): LazyExoticComponent<T> {
  const { retryAttempts = 3, retryDelay = 1000 } = options;

  const componentLoader = async (): Promise<{ default: T }> => {
    let lastError: Error;

    for (let attempt = 1; attempt <= retryAttempts; attempt++) {
      try {
        return await importFn();
      } catch (error) {
        lastError = error as Error;
        
        if (attempt === retryAttempts) {
          console.error(`Failed to load component after ${retryAttempts} attempts:`, error);
          throw lastError;
        }

        console.warn(`Component load attempt ${attempt} failed, retrying in ${retryDelay}ms:`, error);
        await new Promise(resolve => setTimeout(resolve, retryDelay * attempt));
      }
    }

    throw lastError!;
  };

  return React.lazy(componentLoader);
}

/**
 * Default fallback component for loading states
 */
export const DefaultLoadingFallback: React.FC = () => 
  React.createElement('div', {
    style: { 
      display: 'flex', 
      justifyContent: 'center', 
      alignItems: 'center', 
      height: '200px' 
    }
  }, 'Loading...');

/**
 * Error boundary fallback for failed component loads
 */
export const ComponentLoadError: React.FC<{ error?: Error; onRetry?: () => void }> = ({ 
  error, 
  onRetry 
}) => React.createElement('div', {
  style: { 
    padding: '20px', 
    textAlign: 'center', 
    color: '#d32f2f' 
  }
}, [
  React.createElement('h3', { key: 'title' }, 'Failed to load component'),
  React.createElement('p', { key: 'message' }, error?.message || 'Unknown error occurred'),
  onRetry && React.createElement('button', {
    key: 'retry',
    onClick: onRetry,
    style: {
      padding: '8px 16px',
      backgroundColor: '#1976d2',
      color: 'white',
      border: 'none',
      borderRadius: '4px',
      cursor: 'pointer'
    }
  }, 'Retry')
].filter(Boolean));

/**
 * Preloads components for better UX
 */
export function preloadComponent(importFn: () => Promise<any>): Promise<void> {
  return importFn().then(() => {
    console.log('Component preloaded successfully');
  }).catch((error) => {
    console.warn('Failed to preload component:', error);
  });
}

