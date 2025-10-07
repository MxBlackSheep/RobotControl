/**
 * LoadingSpinner Component Tests
 * 
 * Comprehensive unit tests for LoadingSpinner component variants
 * Tests loading states, accessibility, and responsive behavior
 */

import React from 'react';
import { screen, waitFor } from '@testing-library/react';
import { renderWithTheme, expectElementToBeVisible } from '../../utils/test-utils';
import LoadingSpinner, { 
  PageLoading, 
  ButtonLoading, 
  CardLoading, 
  SkeletonLoading 
} from '../LoadingSpinner';

describe('LoadingSpinner', () => {
  describe('Basic functionality', () => {
    it('renders spinner variant by default', () => {
      renderWithTheme(<LoadingSpinner />);
      
      const spinner = screen.getByRole('progressbar');
      expectElementToBeVisible(spinner);
    });

    it('displays custom message', () => {
      const message = 'Loading test data...';
      renderWithTheme(<LoadingSpinner message={message} />);
      
      expect(screen.getByText(message)).toBeInTheDocument();
    });

    it('applies custom size', () => {
      renderWithTheme(<LoadingSpinner size={64} />);
      
      const spinner = screen.getByRole('progressbar');
      expect(spinner).toHaveStyle({ width: '64px', height: '64px' });
    });

    it('applies custom className', () => {
      renderWithTheme(<LoadingSpinner className="custom-spinner" />);
      
      const container = screen.getByTestId('loading-spinner');
      expect(container).toHaveClass('custom-spinner');
    });
  });

  describe('Variants', () => {
    it('renders linear progress variant', () => {
      renderWithTheme(<LoadingSpinner variant="linear" />);
      
      const linearProgress = screen.getByRole('progressbar');
      expect(linearProgress).toBeInTheDocument();
    });

    it('renders skeleton variant', () => {
      renderWithTheme(<LoadingSpinner variant="skeleton" />);
      
      // Skeleton renders multiple skeleton items
      const skeletons = screen.getAllByTestId(/skeleton/);
      expect(skeletons.length).toBeGreaterThan(0);
    });

    it('renders fullscreen variant with overlay', () => {
      renderWithTheme(<LoadingSpinner variant="fullscreen" message="Loading..." />);
      
      const fullscreen = screen.getByTestId('loading-fullscreen');
      expect(fullscreen).toBeInTheDocument();
      expect(fullscreen).toHaveStyle({
        position: 'fixed',
        top: '0',
        left: '0',
        width: '100%',
        height: '100%'
      });
    });

    it('renders inline variant without wrapper', () => {
      renderWithTheme(<LoadingSpinner variant="inline" />);
      
      const spinner = screen.getByRole('progressbar');
      expect(spinner).toBeInTheDocument();
      // Should not have the default wrapper styling
      expect(spinner.parentElement).not.toHaveStyle({
        display: 'flex',
        justifyContent: 'center'
      });
    });
  });

  describe('Accessibility', () => {
    it('has proper ARIA attributes', () => {
      renderWithTheme(<LoadingSpinner message="Loading content" />);
      
      const spinner = screen.getByRole('progressbar');
      expect(spinner).toHaveAttribute('aria-label', 'Loading content');
    });

    it('uses aria-describedby when message is present', () => {
      renderWithTheme(<LoadingSpinner message="Processing request..." />);
      
      const spinner = screen.getByRole('progressbar');
      const messageElement = screen.getByText('Processing request...');
      
      expect(spinner).toHaveAttribute('aria-describedby', messageElement.id);
    });

    it('has semantic HTML structure', () => {
      renderWithTheme(<LoadingSpinner variant="fullscreen" message="Loading application..." />);
      
      const main = screen.getByRole('main');
      expect(main).toBeInTheDocument();
      expect(main).toHaveAttribute('aria-busy', 'true');
    });
  });

  describe('Color variants', () => {
    it('applies primary color', () => {
      renderWithTheme(<LoadingSpinner color="primary" />);
      
      const spinner = screen.getByRole('progressbar');
      expect(spinner).toHaveClass(/primary/i);
    });

    it('applies secondary color', () => {
      renderWithTheme(<LoadingSpinner color="secondary" />);
      
      const spinner = screen.getByRole('progressbar');
      expect(spinner).toHaveClass(/secondary/i);
    });
  });

  describe('Responsive behavior', () => {
    it('adjusts size based on screen size', () => {
      renderWithTheme(<LoadingSpinner size={{ xs: 20, sm: 30, md: 40 }} />);
      
      const spinner = screen.getByRole('progressbar');
      expect(spinner).toBeInTheDocument();
      // Note: Testing responsive values would require more complex setup
      // This test validates the component accepts responsive props
    });
  });
});

describe('PageLoading', () => {
  it('renders with default message', () => {
    renderWithTheme(<PageLoading />);
    
    expect(screen.getByText('Loading page...')).toBeInTheDocument();
    expect(screen.getByRole('progressbar')).toBeInTheDocument();
  });

  it('renders with custom message', () => {
    const message = 'Loading dashboard data...';
    renderWithTheme(<PageLoading message={message} />);
    
    expect(screen.getByText(message)).toBeInTheDocument();
  });

  it('has fullscreen styling', () => {
    renderWithTheme(<PageLoading />);
    
    const container = screen.getByTestId('loading-fullscreen');
    expect(container).toBeInTheDocument();
  });
});

describe('ButtonLoading', () => {
  it('renders small spinner for buttons', () => {
    renderWithTheme(<ButtonLoading />);
    
    const spinner = screen.getByRole('progressbar');
    expect(spinner).toBeInTheDocument();
    expect(spinner).toHaveStyle({ width: '20px', height: '20px' });
  });

  it('accepts custom size', () => {
    renderWithTheme(<ButtonLoading size={16} />);
    
    const spinner = screen.getByRole('progressbar');
    expect(spinner).toHaveStyle({ width: '16px', height: '16px' });
  });

  it('has no message by default', () => {
    renderWithTheme(<ButtonLoading />);
    
    expect(screen.queryByText(/loading/i)).not.toBeInTheDocument();
  });
});

describe('CardLoading', () => {
  it('renders skeleton variant', () => {
    renderWithTheme(<CardLoading />);
    
    const skeletons = screen.getAllByTestId(/skeleton/);
    expect(skeletons.length).toBeGreaterThan(0);
  });

  it('accepts custom height', () => {
    renderWithTheme(<CardLoading height={200} />);
    
    const container = screen.getByTestId('loading-card');
    expect(container).toHaveStyle({ minHeight: '200px' });
  });
});

describe('SkeletonLoading', () => {
  it('renders multiple skeleton lines', () => {
    renderWithTheme(<SkeletonLoading lines={5} />);
    
    const skeletons = screen.getAllByTestId(/skeleton-line/);
    expect(skeletons).toHaveLength(5);
  });

  it('varies skeleton widths for realistic appearance', () => {
    renderWithTheme(<SkeletonLoading lines={3} />);
    
    const skeletons = screen.getAllByTestId(/skeleton-line/);
    expect(skeletons.length).toBe(3);
    
    // Check that skeletons have different widths (for realistic appearance)
    const widths = skeletons.map(skeleton => 
      getComputedStyle(skeleton).width
    );
    expect(new Set(widths).size).toBeGreaterThan(1);
  });

  it('accepts custom line height', () => {
    renderWithTheme(<SkeletonLoading height={24} />);
    
    const skeleton = screen.getByTestId(/skeleton/);
    expect(skeleton).toHaveStyle({ height: '24px' });
  });
});

describe('Integration tests', () => {
  it('transitions smoothly between loading states', async () => {
    const { rerender } = renderWithTheme(<LoadingSpinner />);
    
    expect(screen.getByRole('progressbar')).toBeInTheDocument();
    
    rerender(<div>Content loaded!</div>);
    
    await waitFor(() => {
      expect(screen.getByText('Content loaded!')).toBeInTheDocument();
      expect(screen.queryByRole('progressbar')).not.toBeInTheDocument();
    });
  });

  it('maintains accessibility during state changes', async () => {
    const { rerender } = renderWithTheme(
      <LoadingSpinner message="Loading data..." />
    );
    
    const spinner = screen.getByRole('progressbar');
    expect(spinner).toHaveAttribute('aria-label', 'Loading data...');
    
    rerender(<LoadingSpinner message="Saving data..." />);
    
    await waitFor(() => {
      const updatedSpinner = screen.getByRole('progressbar');
      expect(updatedSpinner).toHaveAttribute('aria-label', 'Saving data...');
    });
  });
});

describe('Error handling', () => {
  it('handles missing props gracefully', () => {
    expect(() => renderWithTheme(<LoadingSpinner />)).not.toThrow();
  });

  it('handles invalid size values', () => {
    expect(() => 
      renderWithTheme(<LoadingSpinner size={-1} />)
    ).not.toThrow();
  });

  it('handles invalid variant gracefully', () => {
    expect(() => 
      renderWithTheme(
        // @ts-ignore - Testing invalid prop
        <LoadingSpinner variant="invalid" />
      )
    ).not.toThrow();
  });
});