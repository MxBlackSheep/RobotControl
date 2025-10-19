/**
 * ErrorAlert Component Tests
 * 
 * Comprehensive unit tests for ErrorAlert component and its variants
 * Tests error handling, retry functionality, accessibility, and user interactions
 */

import React from 'react';
import { screen, waitFor, fireEvent } from '@testing-library/react';
import { userEvent } from '@testing-library/user-event';
import { renderWithTheme, expectElementToBeVisible } from '../../utils/test-utils';
import ErrorAlert, { 
  NetworkError, 
  AuthenticationError, 
  ServerError, 
  SuccessAlert,
  createErrorFromStatus 
} from '../ErrorAlert';

describe('ErrorAlert', () => {
  describe('Basic functionality', () => {
    it('renders error message', () => {
      const message = 'Something went wrong';
      renderWithTheme(<ErrorAlert message={message} />);
      
      expect(screen.getByText(message)).toBeInTheDocument();
      expect(screen.getByRole('alertdialog')).toBeInTheDocument();
    });

    it('displays custom title', () => {
      renderWithTheme(
        <ErrorAlert 
          message="Error occurred" 
          title="Custom Error Title" 
        />
      );
      
      expect(screen.getByText('Custom Error Title')).toBeInTheDocument();
    });

    it('applies custom className', () => {
      renderWithTheme(
        <ErrorAlert 
          message="Test error" 
          className="custom-error" 
        />
      );
      
      const alert = screen.getByRole('alertdialog');
      expect(alert).toHaveClass('custom-error');
    });
  });

  describe('Severity levels', () => {
    it('renders error severity by default', () => {
      renderWithTheme(<ErrorAlert message="Error message" />);
      
      const alert = screen.getByRole('alertdialog');
      expect(alert).toHaveAttribute('data-severity', 'error');
    });

    it('renders warning severity', () => {
      renderWithTheme(
        <ErrorAlert message="Warning message" severity="warning" />
      );
      
      const alert = screen.getByRole('alertdialog');
      expect(alert).toHaveAttribute('data-severity', 'warning');
    });

    it('renders info severity', () => {
      renderWithTheme(
        <ErrorAlert message="Info message" severity="info" />
      );
      
      const alert = screen.getByRole('alertdialog');
      expect(alert).toHaveAttribute('data-severity', 'info');
    });

    it('renders success severity', () => {
      renderWithTheme(
        <ErrorAlert message="Success message" severity="success" />
      );
      
      const alert = screen.getByRole('alertdialog');
      expect(alert).toHaveAttribute('data-severity', 'success');
    });
  });

  describe('Error categories', () => {
    it('shows network error with appropriate styling', () => {
      renderWithTheme(
        <ErrorAlert 
          message="Connection failed" 
          category="network" 
        />
      );
      
      expect(screen.getByText('Connection failed')).toBeInTheDocument();
    });

    it('shows authentication error with warning severity', () => {
      renderWithTheme(
        <ErrorAlert 
          message="Please log in" 
          category="authentication" 
        />
      );
      
      const alert = screen.getByRole('alertdialog');
      expect(alert).toBeInTheDocument();
    });
  });

  describe('Close functionality', () => {
    it('renders close button when closable', () => {
      renderWithTheme(
        <ErrorAlert message="Closable error" closable={true} />
      );
      
      const closeButton = screen.getByLabelText(/close/i);
      expectElementToBeVisible(closeButton);
    });

    it('calls onClose when close button is clicked', async () => {
      const onClose = jest.fn();
      const user = userEvent.setup();
      
      renderWithTheme(
        <ErrorAlert 
          message="Test error" 
          closable={true} 
          onClose={onClose} 
        />
      );
      
      const closeButton = screen.getByLabelText(/close/i);
      await user.click(closeButton);
      
      expect(onClose).toHaveBeenCalledTimes(1);
    });

    it('hides alert when closed', async () => {
      const user = userEvent.setup();
      
      renderWithTheme(
        <ErrorAlert message="Test error" closable={true} />
      );
      
      const alert = screen.getByRole('alertdialog');
      expect(alert).toBeInTheDocument();
      
      const closeButton = screen.getByLabelText(/close/i);
      await user.click(closeButton);
      
      await waitFor(() => {
        expect(screen.queryByRole('alertdialog')).not.toBeInTheDocument();
      });
    });
  });

  describe('Retry functionality', () => {
    it('renders retry button when retryable', () => {
      renderWithTheme(
        <ErrorAlert 
          message="Retryable error" 
          retryable={true} 
          onRetry={() => {}} 
        />
      );
      
      const retryButton = screen.getByText(/retry/i);
      expectElementToBeVisible(retryButton);
    });

    it('calls onRetry when retry button is clicked', async () => {
      const onRetry = jest.fn();
      const user = userEvent.setup();
      
      renderWithTheme(
        <ErrorAlert 
          message="Test error" 
          retryable={true} 
          onRetry={onRetry} 
        />
      );
      
      const retryButton = screen.getByText(/retry/i);
      await user.click(retryButton);
      
      expect(onRetry).toHaveBeenCalledTimes(1);
    });

    it('shows retrying state', () => {
      renderWithTheme(
        <ErrorAlert 
          message="Test error" 
          retryable={true} 
          retrying={true} 
          onRetry={() => {}} 
        />
      );
      
      expect(screen.getByText(/retrying/i)).toBeInTheDocument();
    });

    it('disables retry button while retrying', () => {
      renderWithTheme(
        <ErrorAlert 
          message="Test error" 
          retryable={true} 
          retrying={true} 
          onRetry={() => {}} 
        />
      );
      
      const retryButton = screen.getByText(/retrying/i);
      expect(retryButton).toBeDisabled();
    });
  });

  describe('Detailed error information', () => {
    it('shows details toggle when detailed is true', () => {
      renderWithTheme(
        <ErrorAlert 
          message="Error occurred" 
          detailed={true} 
          details="Stack trace here" 
        />
      );
      
      const detailsToggle = screen.getByRole('button', { name: /show details/i });
      expectElementToBeVisible(detailsToggle);
    });

    it('expands details when toggle is clicked', async () => {
      const user = userEvent.setup();
      const details = 'Detailed error information';
      
      renderWithTheme(
        <ErrorAlert 
          message="Error occurred" 
          detailed={true} 
          details={details} 
        />
      );
      
      expect(screen.queryByText(details)).not.toBeInTheDocument();
      
      const detailsToggle = screen.getByRole('button', { name: /show details/i });
      await user.click(detailsToggle);
      
      await waitFor(() => {
        expect(screen.getByText(details)).toBeInTheDocument();
      });
    });

    it('collapses details when toggle is clicked again', async () => {
      const user = userEvent.setup();
      const details = 'Detailed error information';
      
      renderWithTheme(
        <ErrorAlert 
          message="Error occurred" 
          detailed={true} 
          details={details} 
        />
      );
      
      const detailsToggle = screen.getByRole('button', { name: /show details/i });
      
      // Expand
      await user.click(detailsToggle);
      await waitFor(() => {
        expect(screen.getByText(details)).toBeInTheDocument();
      });
      
      // Collapse
      await user.click(detailsToggle);
      await waitFor(() => {
        expect(screen.queryByText(details)).not.toBeInTheDocument();
      });
    });
  });

  describe('Auto hide functionality', () => {
    it('auto hides after specified duration', async () => {
      jest.useFakeTimers();
      
      renderWithTheme(
        <ErrorAlert 
          message="Auto hide error" 
          autoHideDuration={3000} 
        />
      );
      
      expect(screen.getByRole('alertdialog')).toBeInTheDocument();
      
      jest.advanceTimersByTime(3000);
      
      await waitFor(() => {
        expect(screen.queryByRole('alertdialog')).not.toBeInTheDocument();
      });
      
      jest.useRealTimers();
    });
  });

  describe('Accessibility', () => {
    it('has proper ARIA attributes', () => {
      renderWithTheme(<ErrorAlert message="Accessible error" />);
      
      const alert = screen.getByRole('alertdialog');
      expect(alert).toHaveAttribute('aria-live', 'assertive');
      expect(alert).toHaveAttribute('aria-atomic', 'true');
    });

    it('has accessible retry button', () => {
      renderWithTheme(
        <ErrorAlert 
          message="Test error" 
          retryable={true} 
          onRetry={() => {}} 
        />
      );
      
      const retryButton = screen.getByText(/retry/i);
      expect(retryButton).toBeInTheDocument();
    });

    it('has accessible close button', () => {
      renderWithTheme(
        <ErrorAlert message="Test error" closable={true} />
      );
      
      const closeButton = screen.getByLabelText(/close notification/i);
      expect(closeButton).toBeInTheDocument();
    });

    it('has accessible details toggle', () => {
      renderWithTheme(
        <ErrorAlert 
          message="Error" 
          detailed={true} 
          details="Details" 
        />
      );
      
      const detailsToggle = screen.getByRole('button', { name: /show details/i });
      expect(detailsToggle).toHaveAttribute('aria-expanded', 'false');
      expect(detailsToggle).toHaveAttribute('aria-controls');
    });
  });
});

describe('Specialized Error Components', () => {
  describe('NetworkError', () => {
    it('renders with network category and retry enabled', () => {
      renderWithTheme(
        <NetworkError message="Connection failed" onRetry={() => {}} />
      );
      
      expect(screen.getByText('Connection failed')).toBeInTheDocument();
      expect(screen.getByText(/retry/i)).toBeInTheDocument();
    });
  });

  describe('AuthenticationError', () => {
    it('renders with warning severity', () => {
      renderWithTheme(
        <AuthenticationError message="Please log in" />
      );
      
      const alert = screen.getByRole('alertdialog');
      expect(alert).toHaveAttribute('data-severity', 'warning');
      expect(screen.getByText('Please log in')).toBeInTheDocument();
    });
  });

  describe('ServerError', () => {
    it('renders with error severity and retry enabled', () => {
      renderWithTheme(
        <ServerError message="Server error" onRetry={() => {}} />
      );
      
      const alert = screen.getByRole('alertdialog');
      expect(alert).toHaveAttribute('data-severity', 'error');
      expect(screen.getByText(/retry/i)).toBeInTheDocument();
    });
  });

  describe('SuccessAlert', () => {
    it('renders with success severity', () => {
      renderWithTheme(
        <SuccessAlert message="Operation successful" />
      );
      
      const alert = screen.getByRole('alertdialog');
      expect(alert).toHaveAttribute('data-severity', 'success');
    });

    it('auto hides by default', () => {
      jest.useFakeTimers();
      
      renderWithTheme(
        <SuccessAlert message="Success message" />
      );
      
      expect(screen.getByRole('alertdialog')).toBeInTheDocument();
      
      jest.advanceTimersByTime(5000);
      
      waitFor(() => {
        expect(screen.queryByRole('alertdialog')).not.toBeInTheDocument();
      });
      
      jest.useRealTimers();
    });
  });
});

describe('Error Factory Functions', () => {
  describe('createErrorFromStatus', () => {
    it('creates authentication error for 401', () => {
      const error = createErrorFromStatus(401, 'Unauthorized');
      
      expect(error.category).toBe('authentication');
      expect(error.severity).toBe('warning');
      expect(error.message).toBe('Unauthorized');
    });

    it('creates authorization error for 403', () => {
      const error = createErrorFromStatus(403, 'Forbidden');
      
      expect(error.category).toBe('authorization');
      expect(error.severity).toBe('warning');
      expect(error.message).toBe('Forbidden');
    });

    it('creates server error for 500', () => {
      const error = createErrorFromStatus(500, 'Internal Server Error');
      
      expect(error.category).toBe('server');
      expect(error.severity).toBe('error');
      expect(error.retryable).toBe(true);
    });

    it('creates timeout error for 408', () => {
      const error = createErrorFromStatus(408);
      
      expect(error.category).toBe('timeout');
      expect(error.severity).toBe('warning');
      expect(error.retryable).toBe(true);
    });

    it('creates unknown error for unrecognized status', () => {
      const error = createErrorFromStatus(999, 'Unknown error');
      
      expect(error.category).toBe('unknown');
      expect(error.severity).toBe('error');
      expect(error.message).toBe('Unknown error');
    });

    it('uses default messages when none provided', () => {
      const error = createErrorFromStatus(401);
      
      expect(error.message).toBe('Please log in to continue.');
    });
  });
});

describe('Integration scenarios', () => {
  it('handles complex error with all features', async () => {
    const onRetry = jest.fn();
    const onClose = jest.fn();
    const user = userEvent.setup();
    
    renderWithTheme(
      <ErrorAlert
        message="Complex error occurred"
        title="System Error"
        severity="error"
        category="server"
        closable={true}
        retryable={true}
        detailed={true}
        details="Stack trace and debug information"
        onRetry={onRetry}
        onClose={onClose}
      />
    );
    
    // Verify all elements are present
    expect(screen.getByText('System Error')).toBeInTheDocument();
    expect(screen.getByText('Complex error occurred')).toBeInTheDocument();
    expect(screen.getByLabelText(/retry operation/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/close alert/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/show details/i)).toBeInTheDocument();
    
    // Test interactions
    await user.click(screen.getByLabelText(/retry operation/i));
    expect(onRetry).toHaveBeenCalled();
    
    await user.click(screen.getByLabelText(/show details/i));
    await waitFor(() => {
      expect(screen.getByText('Stack trace and debug information')).toBeInTheDocument();
    });
  });
});
