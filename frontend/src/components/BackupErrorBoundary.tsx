/**
 * PyRobot Backup Error Boundary Component
 * 
 * React error boundary specifically for backup-related components.
 * Implements graceful error recovery and user-friendly error displays.
 * Prevents backup system errors from affecting other application features.
 * 
 * Key Features:
 * - Isolates backup failures from rest of application
 * - Provides user-friendly error messages
 * - Offers recovery options (retry, navigate away)
 * - Logs detailed error information for debugging
 * - Follows CLAUDE.md isolation principles
 */

import React, { Component, ErrorInfo, ReactNode } from 'react';
import {
  Box,
  Typography,
  Button,
  Alert,
  Card,
  CardContent,
  Stack,
  Divider,
  Accordion,
  AccordionSummary,
  AccordionDetails,
  Chip
} from '@mui/material';
import {
  Error as ErrorIcon,
  Refresh as RefreshIcon,
  Home as HomeIcon,
  ExpandMore as ExpandMoreIcon,
  BugReport as BugReportIcon,
  Schedule as TimeIcon
} from '@mui/icons-material';

interface BackupErrorBoundaryProps {
  children: ReactNode;
  onError?: (error: string, errorInfo?: string) => void;
  fallback?: ReactNode;
  showDetailedError?: boolean;
}

interface BackupErrorBoundaryState {
  hasError: boolean;
  error: Error | null;
  errorInfo: ErrorInfo | null;
  errorId: string;
  timestamp: Date;
  retryCount: number;
}

/**
 * Error boundary component for backup operations
 * 
 * Catches JavaScript errors anywhere in the backup component tree,
 * logs those errors, and displays a fallback UI instead of crashing.
 */
class BackupErrorBoundary extends Component<BackupErrorBoundaryProps, BackupErrorBoundaryState> {
  private maxRetries = 3;
  
  constructor(props: BackupErrorBoundaryProps) {
    super(props);
    
    this.state = {
      hasError: false,
      error: null,
      errorInfo: null,
      errorId: this.generateErrorId(),
      timestamp: new Date(),
      retryCount: 0
    };
  }

  /**
   * Generate unique error ID for tracking
   */
  private generateErrorId(): string {
    return `backup-error-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`;
  }

  /**
   * Static method called when an error is caught
   */
  static getDerivedStateFromError(error: Error): Partial<BackupErrorBoundaryState> {
    // Update state so the next render will show the fallback UI
    return {
      hasError: true,
      error,
      errorId: `backup-error-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`,
      timestamp: new Date()
    };
  }

  /**
   * Called when an error is caught
   * Used for error reporting and logging
   */
  componentDidCatch(error: Error, errorInfo: ErrorInfo) {
    // Update state with error info
    this.setState({
      errorInfo
    });

    // Log detailed error information
    console.group(`🚨 Backup Error Boundary - ${this.state.errorId}`);
    console.error('Error caught by BackupErrorBoundary:', error);
    console.error('Component stack:', errorInfo.componentStack);
    console.error('Error info:', errorInfo);
    console.groupEnd();

    // Report error to parent component if callback provided
    if (this.props.onError) {
      const errorMessage = error?.message || 'Unknown backup system error';
      const errorDetails = `${errorInfo.componentStack}\n\nError: ${error?.stack}`;
      this.props.onError(errorMessage, errorDetails);
    }

    // In production, you could send error to logging service
    // Example: errorReportingService.logError(error, errorInfo);
  }

  /**
   * Retry the component by clearing error state
   */
  private handleRetry = () => {
    if (this.state.retryCount < this.maxRetries) {
      this.setState(prevState => ({
        hasError: false,
        error: null,
        errorInfo: null,
        errorId: this.generateErrorId(),
        timestamp: new Date(),
        retryCount: prevState.retryCount + 1
      }));
    }
  };

  /**
   * Navigate back to admin page
   */
  private handleNavigateToAdmin = () => {
    window.location.href = '/admin';
  };

  /**
   * Navigate back to dashboard
   */
  private handleNavigateToDashboard = () => {
    window.location.href = '/';
  };

  /**
   * Copy error details to clipboard for support
   */
  private handleCopyErrorDetails = async () => {
    const errorDetails = this.getErrorDetailsText();
    try {
      await navigator.clipboard.writeText(errorDetails);
      alert('Error details copied to clipboard');
    } catch (err) {
      console.error('Failed to copy error details:', err);
      // Fallback for older browsers
      const textArea = document.createElement('textarea');
      textArea.value = errorDetails;
      document.body.appendChild(textArea);
      textArea.select();
      document.execCommand('copy');
      document.body.removeChild(textArea);
      alert('Error details copied to clipboard');
    }
  };

  /**
   * Get formatted error details text
   */
  private getErrorDetailsText(): string {
    const { error, errorInfo, errorId, timestamp } = this.state;
    
    return `
PyRobot Backup System Error Report
=================================

Error ID: ${errorId}
Timestamp: ${timestamp.toISOString()}
User Agent: ${navigator.userAgent}

Error Message:
${error?.message || 'Unknown error'}

Error Stack:
${error?.stack || 'No stack trace available'}

Component Stack:
${errorInfo?.componentStack || 'No component stack available'}

Environment:
- URL: ${window.location.href}
- Timestamp: ${new Date().toISOString()}
- Browser: ${navigator.userAgent}
    `.trim();
  }

  /**
   * Render error state
   */
  private renderErrorState() {
    const { error, errorId, timestamp, retryCount } = this.state;
    const { showDetailedError = false } = this.props;
    const canRetry = retryCount < this.maxRetries;

    return (
      <Box sx={{ p: 3 }}>
        {/* Main Error Alert */}
        <Alert 
          severity="error" 
          icon={<ErrorIcon />}
          sx={{ mb: 3 }}
        >
          <Typography variant="h6" gutterBottom>
            Backup System Error
          </Typography>
          <Typography variant="body2">
            The backup system encountered an unexpected error. This issue has been isolated 
            to prevent affecting other application features.
          </Typography>
        </Alert>

        {/* Error Summary Card */}
        <Card variant="outlined" sx={{ mb: 3 }}>
          <CardContent>
            <Stack spacing={2}>
              <Stack direction="row" justifyContent="space-between" alignItems="center">
                <Typography variant="h6" sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                  <BugReportIcon color="error" />
                  Error Information
                </Typography>
                <Stack direction="row" spacing={1}>
                  <Chip 
                    icon={<TimeIcon />}
                    label={timestamp.toLocaleString()} 
                    size="small" 
                    variant="outlined" 
                  />
                  <Chip 
                    label={`ID: ${errorId.split('-').pop()}`} 
                    size="small" 
                    variant="outlined" 
                  />
                </Stack>
              </Stack>

              <Divider />

              <Typography variant="body2">
                <strong>Error:</strong> {error?.message || 'Unknown error occurred'}
              </Typography>
              
              {retryCount > 0 && (
                <Typography variant="body2" color="warning.main">
                  <strong>Retry Attempts:</strong> {retryCount} of {this.maxRetries}
                </Typography>
              )}

              {/* Action Buttons */}
              <Stack direction="row" spacing={2} sx={{ pt: 1 }}>
                {canRetry && (
                  <Button
                    variant="contained"
                    startIcon={<RefreshIcon />}
                    onClick={this.handleRetry}
                    color="primary"
                  >
                    Retry ({this.maxRetries - retryCount} attempts left)
                  </Button>
                )}
                
                <Button
                  variant="outlined"
                  startIcon={<HomeIcon />}
                  onClick={this.handleNavigateToAdmin}
                >
                  Back to Admin
                </Button>

                <Button
                  variant="text"
                  onClick={this.handleCopyErrorDetails}
                  size="small"
                >
                  Copy Error Details
                </Button>
              </Stack>
            </Stack>
          </CardContent>
        </Card>

        {/* Detailed Error Information (Collapsible) */}
        {showDetailedError && (
          <Accordion>
            <AccordionSummary expandIcon={<ExpandMoreIcon />}>
              <Typography variant="subtitle2">
                Technical Details (for developers)
              </Typography>
            </AccordionSummary>
            <AccordionDetails>
              <Box
                component="pre"
                sx={{
                  backgroundColor: 'grey.100',
                  padding: 2,
                  borderRadius: 1,
                  overflow: 'auto',
                  fontSize: '0.875rem',
                  fontFamily: 'monospace',
                  whiteSpace: 'pre-wrap',
                  maxHeight: 300
                }}
              >
                {this.getErrorDetailsText()}
              </Box>
            </AccordionDetails>
          </Accordion>
        )}

        {/* Recommendations */}
        <Alert severity="info" sx={{ mt: 3 }}>
          <Typography variant="subtitle2" gutterBottom>
            Troubleshooting Recommendations
          </Typography>
          <Typography variant="body2" component="div">
            <ul style={{ margin: 0, paddingLeft: 20 }}>
              <li>Try refreshing the page or retrying the operation</li>
              <li>Check your network connection and authentication status</li>
              <li>Verify that the backup service is running properly</li>
              <li>If the problem persists, contact your system administrator</li>
              <li>Use the "Copy Error Details" button to share technical information</li>
            </ul>
          </Typography>
        </Alert>
      </Box>
    );
  }

  render() {
    if (this.state.hasError) {
      // Use custom fallback if provided, otherwise use default error state
      if (this.props.fallback) {
        return this.props.fallback;
      }
      
      return this.renderErrorState();
    }

    // No error, render children normally
    return this.props.children;
  }
}

export default BackupErrorBoundary;
export type { BackupErrorBoundaryProps };