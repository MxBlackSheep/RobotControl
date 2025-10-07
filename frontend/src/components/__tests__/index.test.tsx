/**
 * Component Index Tests
 * 
 * Tests for overall component architecture and integration
 * Validates that all major components render and integrate properly
 */

import React from 'react';
import { screen } from '@testing-library/react';
import { renderWithTheme, renderWithAll } from '../../utils/test-utils';

// Import major components to test basic rendering
import LoadingSpinner from '../LoadingSpinner';
import ErrorAlert from '../ErrorAlert';
import VirtualizedTable from '../VirtualizedTable';

describe('Component Integration', () => {
  describe('Component exports', () => {
    it('exports LoadingSpinner component', () => {
      expect(LoadingSpinner).toBeDefined();
      expect(typeof LoadingSpinner).toBe('function');
    });

    it('exports ErrorAlert component', () => {
      expect(ErrorAlert).toBeDefined();
      expect(typeof ErrorAlert).toBe('function');
    });

    it('exports VirtualizedTable component', () => {
      expect(VirtualizedTable).toBeDefined();
      expect(typeof VirtualizedTable).toBe('function');
    });
  });

  describe('Basic component rendering', () => {
    it('renders LoadingSpinner without errors', () => {
      expect(() => {
        renderWithTheme(<LoadingSpinner />);
      }).not.toThrow();
    });

    it('renders ErrorAlert without errors', () => {
      expect(() => {
        renderWithTheme(<ErrorAlert message="Test error" />);
      }).not.toThrow();
    });

    it('renders VirtualizedTable without errors', () => {
      const mockData = [{ id: 1, name: 'Test' }];
      const mockColumns = [
        { key: 'id', label: 'ID' },
        { key: 'name', label: 'Name' }
      ];

      expect(() => {
        renderWithTheme(
          <VirtualizedTable data={mockData} columns={mockColumns} />
        );
      }).not.toThrow();
    });
  });

  describe('Component composition', () => {
    it('can compose LoadingSpinner with ErrorAlert', () => {
      const ComposedComponent = () => (
        <div>
          <LoadingSpinner message="Loading..." />
          <ErrorAlert message="Error occurred" />
        </div>
      );

      renderWithTheme(<ComposedComponent />);

      expect(screen.getByText('Loading...')).toBeInTheDocument();
      expect(screen.getByText('Error occurred')).toBeInTheDocument();
    });

    it('handles conditional rendering patterns', () => {
      const ConditionalComponent = ({ 
        loading, 
        error, 
        data 
      }: { 
        loading: boolean; 
        error: string | null; 
        data: any[] | null;
      }) => (
        <div>
          {loading && <LoadingSpinner message="Loading data..." />}
          {error && <ErrorAlert message={error} />}
          {data && !loading && !error && (
            <VirtualizedTable
              data={data}
              columns={[{ key: 'name', label: 'Name' }]}
            />
          )}
        </div>
      );

      // Test loading state
      const { rerender } = renderWithTheme(
        <ConditionalComponent loading={true} error={null} data={null} />
      );
      expect(screen.getByText('Loading data...')).toBeInTheDocument();

      // Test error state
      rerender(
        <ConditionalComponent loading={false} error="Failed to load" data={null} />
      );
      expect(screen.getByText('Failed to load')).toBeInTheDocument();

      // Test success state
      rerender(
        <ConditionalComponent 
          loading={false} 
          error={null} 
          data={[{ name: 'Test Item' }]} 
        />
      );
      expect(screen.getByText('Name')).toBeInTheDocument();
    });
  });

  describe('Theme integration', () => {
    it('components work with Material-UI theme', () => {
      const ThemedComponents = () => (
        <div>
          <LoadingSpinner color="primary" />
          <ErrorAlert message="Themed error" severity="warning" />
        </div>
      );

      renderWithTheme(<ThemedComponents />);

      expect(screen.getByRole('progressbar')).toBeInTheDocument();
      expect(screen.getByRole('alert')).toBeInTheDocument();
    });
  });

  describe('Accessibility integration', () => {
    it('maintains accessibility when components are composed', () => {
      const AccessibleApp = () => (
        <main role="main">
          <h1>Test Application</h1>
          <LoadingSpinner message="Loading content" />
          <ErrorAlert 
            message="Error message" 
            closable={true} 
            retryable={true}
            onRetry={() => {}}
          />
        </main>
      );

      renderWithTheme(<AccessibleApp />);

      expect(screen.getByRole('main')).toBeInTheDocument();
      expect(screen.getByRole('progressbar')).toHaveAttribute('aria-label');
      expect(screen.getByRole('alert')).toHaveAttribute('aria-live');
      expect(screen.getByLabelText(/retry/i)).toBeInTheDocument();
      expect(screen.getByLabelText(/close/i)).toBeInTheDocument();
    });
  });

  describe('Performance considerations', () => {
    it('handles large datasets efficiently', () => {
      const largeMockData = Array.from({ length: 1000 }, (_, i) => ({
        id: i,
        name: `Item ${i}`,
        value: Math.random() * 100
      }));

      const mockColumns = [
        { key: 'id', label: 'ID' },
        { key: 'name', label: 'Name' },
        { key: 'value', label: 'Value' }
      ];

      const start = performance.now();
      
      renderWithTheme(
        <VirtualizedTable data={largeMockData} columns={mockColumns} />
      );
      
      const end = performance.now();
      const renderTime = end - start;

      // Should render quickly even with large dataset
      expect(renderTime).toBeLessThan(1000); // Less than 1 second
      
      // Should still show the table
      expect(screen.getByRole('table')).toBeInTheDocument();
    });
  });

  describe('Error boundaries', () => {
    it('gracefully handles component errors', () => {
      const ErrorBoundary = class extends React.Component<
        { children: React.ReactNode },
        { hasError: boolean }
      > {
        constructor(props: { children: React.ReactNode }) {
          super(props);
          this.state = { hasError: false };
        }

        static getDerivedStateFromError() {
          return { hasError: true };
        }

        render() {
          if (this.state.hasError) {
            return <ErrorAlert message="Component error occurred" />;
          }

          return this.props.children;
        }
      };

      const ProblematicComponent = () => {
        throw new Error('Test error');
      };

      renderWithTheme(
        <ErrorBoundary>
          <ProblematicComponent />
        </ErrorBoundary>
      );

      expect(screen.getByText('Component error occurred')).toBeInTheDocument();
    });
  });
});

describe('Component API consistency', () => {
  describe('Common prop patterns', () => {
    it('supports className prop consistently', () => {
      const customClass = 'custom-test-class';

      renderWithTheme(
        <div>
          <LoadingSpinner className={customClass} />
          <ErrorAlert message="Test" className={customClass} />
        </div>
      );

      const elements = document.getElementsByClassName(customClass);
      expect(elements.length).toBeGreaterThanOrEqual(2);
    });

    it('supports sx prop for Material-UI styling', () => {
      const customSx = { marginTop: 2, padding: 1 };

      renderWithTheme(
        <div>
          <LoadingSpinner sx={customSx} />
          <ErrorAlert message="Test" sx={customSx} />
        </div>
      );

      // Components should accept sx prop without throwing
      expect(screen.getByRole('progressbar')).toBeInTheDocument();
      expect(screen.getByRole('alert')).toBeInTheDocument();
    });
  });

  describe('Event handler patterns', () => {
    it('follows consistent callback naming', () => {
      const onClose = jest.fn();
      const onRetry = jest.fn();

      renderWithTheme(
        <ErrorAlert
          message="Test error"
          closable={true}
          retryable={true}
          onClose={onClose}
          onRetry={onRetry}
        />
      );

      expect(screen.getByLabelText(/close/i)).toBeInTheDocument();
      expect(screen.getByLabelText(/retry/i)).toBeInTheDocument();
    });
  });
});