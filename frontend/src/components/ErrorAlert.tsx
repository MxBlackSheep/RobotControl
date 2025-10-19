/**
 * ErrorAlert - Unified error handling component for RobotControl
 * 
 * Provides consistent error display across the application with:
 * - Multiple severity levels (error, warning, info, success)
 * - Built-in retry functionality
 * - Accessibility compliance (ARIA labels, keyboard navigation)
 * - Customizable actions and styling
 * - Auto-dismiss functionality
 * - Error categorization and user-friendly messages
 */

import React, { memo, useCallback, useEffect, useMemo, useState } from 'react';

// Optimized Material-UI imports for better tree-shaking
import Box from '@mui/material/Box';
import Button from '@mui/material/Button';
import IconButton from '@mui/material/IconButton';
import Typography from '@mui/material/Typography';
import Collapse from '@mui/material/Collapse';
import Dialog from '@mui/material/Dialog';
import DialogActions from '@mui/material/DialogActions';
import DialogContent from '@mui/material/DialogContent';
import DialogTitle from '@mui/material/DialogTitle';
import { SxProps, Theme } from '@mui/material/styles';
import { useTheme } from '@mui/material/styles';
import {
  Close as CloseIcon,
  Refresh as RetryIcon,
  ExpandMore as ExpandIcon,
  ExpandLess as CollapseIcon,
  Info as InfoIcon,
  Warning as WarningIcon,
  Error as ErrorIcon,
  CheckCircle as SuccessIcon,
} from '@mui/icons-material';
import { normalizeMultilineText } from '@/utils/text';

// Error severity types
export type ErrorSeverity = 'error' | 'warning' | 'info' | 'success';

// Error categories for better UX
export type ErrorCategory = 
  | 'network'
  | 'authentication' 
  | 'authorization'
  | 'validation'
  | 'server'
  | 'client'
  | 'timeout'
  | 'unknown';

// Component props interface
export interface ErrorAlertProps {
  /** Error message to display */
  message: string;
  /** Error severity level */
  severity?: ErrorSeverity;
  /** Error category for better categorization */
  category?: ErrorCategory;
  /** Optional title for the alert */
  title?: string;
  /** Show close button */
  closable?: boolean;
  /** Show retry button */
  retryable?: boolean;
  /** Retry function callback */
  onRetry?: () => void | Promise<void>;
  /** Close function callback */
  onClose?: () => void;
  /** Custom action buttons */
  actions?: React.ReactNode;
  /** Show detailed error information */
  detailed?: boolean;
  /** Technical error details (hidden by default) */
  details?: string;
  /** Auto dismiss after specified milliseconds */
  autoHideDuration?: number;
  /** Custom styling className */
  className?: string;
  /** Material-UI sx prop for custom styling */
  sx?: SxProps<Theme>;
  /** Make alert full width */
  fullWidth?: boolean;
  /** Compact variant for smaller spaces */
  compact?: boolean;
  /** Loading state for retry operation */
  retrying?: boolean;
}

// Error category configurations
const errorCategoryConfig: Record<ErrorCategory, {
  defaultTitle: string;
  icon: React.ReactNode;
  userFriendlyMessage: string;
}> = {
  network: {
    defaultTitle: 'Connection Error',
    icon: <ErrorIcon />,
    userFriendlyMessage: 'Unable to connect to the server. Please check your internet connection.',
  },
  authentication: {
    defaultTitle: 'Authentication Required',
    icon: <WarningIcon />,
    userFriendlyMessage: 'Please log in to continue.',
  },
  authorization: {
    defaultTitle: 'Access Denied',
    icon: <WarningIcon />,
    userFriendlyMessage: 'You do not have permission to perform this action.',
  },
  validation: {
    defaultTitle: 'Invalid Input',
    icon: <InfoIcon />,
    userFriendlyMessage: 'Please check your input and try again.',
  },
  server: {
    defaultTitle: 'Server Error',
    icon: <ErrorIcon />,
    userFriendlyMessage: 'A server error occurred. Please try again later.',
  },
  client: {
    defaultTitle: 'Application Error',
    icon: <ErrorIcon />,
    userFriendlyMessage: 'An unexpected error occurred in the application.',
  },
  timeout: {
    defaultTitle: 'Request Timeout',
    icon: <WarningIcon />,
    userFriendlyMessage: 'The request took too long to complete. Please try again.',
  },
  unknown: {
    defaultTitle: 'Error',
    icon: <ErrorIcon />,
    userFriendlyMessage: 'An unexpected error occurred.',
  },
};

const severityTitleMap: Record<ErrorSeverity, string> = {
  error: 'Application Error',
  warning: 'Warning',
  info: 'Information',
  success: 'Success'
};

const ErrorAlert: React.FC<ErrorAlertProps> = memo(({
  message,
  severity = 'error',
  category = 'unknown',
  title,
  closable = true,
  retryable = false,
  onRetry,
  onClose,
  actions,
  detailed = false,
  details,
  autoHideDuration,
  className,
  sx,
  fullWidth = false,
  compact = false,
  retrying = false,
}) => {
  const [isVisible, setIsVisible] = useState(true);
  const [showDetails, setShowDetails] = useState(false);
  const theme = useTheme();

  // Get category configuration
  const categoryConfig = errorCategoryConfig[category];
  const defaultTitle =
    category === 'unknown'
      ? severityTitleMap[severity]
      : categoryConfig.defaultTitle;
  const alertTitle = title || defaultTitle;
  const normalizedMessage = useMemo(() => normalizeMultilineText(message), [message]);
  const normalizedDetails = useMemo(
    () => (details ? normalizeMultilineText(details) : undefined),
    [details]
  );

  // Handle auto dismiss
  useEffect(() => {
    if (autoHideDuration && autoHideDuration > 0) {
      const timer = setTimeout(() => {
        handleClose();
      }, autoHideDuration);

      return () => clearTimeout(timer);
    }
  }, [autoHideDuration]);

  // Handle close action
  const handleClose = useCallback(() => {
    setIsVisible(false);
    onClose?.();
  }, [onClose]);

  // Handle retry action
  const handleRetry = useCallback(async () => {
    if (onRetry) {
      try {
        await onRetry();
      } catch (error) {
        console.error('Retry failed:', error);
      }
    }
  }, [onRetry]);

  // Toggle details visibility
  const toggleDetails = useCallback(() => {
    setShowDetails(prev => !prev);
  }, []);

  // Don't render if not visible
  if (!isVisible) {
    return null;
  }

  // Determine the appropriate severity icon
  const getSeverityIcon = (): React.ReactNode => {
    switch (severity) {
      case 'success': return <SuccessIcon />;
      case 'warning': return <WarningIcon />;
      case 'info': return <InfoIcon />;
      case 'error':
      default: return <ErrorIcon />;
    }
  };

  const severityPaletteKey: 'error' | 'warning' | 'info' | 'success' =
    severity === 'success' ? 'success' :
    severity === 'warning' ? 'warning' :
    severity === 'info' ? 'info' : 'error';

  const severityColor = theme.palette[severityPaletteKey].main;

  const actionButtons: React.ReactNode[] = [];

  if (actions) {
    actionButtons.push(actions);
  }

  if (retryable && onRetry) {
    actionButtons.push(
      <Button
        key="retry"
        onClick={handleRetry}
        color={severityPaletteKey}
        startIcon={<RetryIcon />}
        disabled={retrying}
      >
        {retrying ? 'Retrying…' : 'Retry'}
      </Button>
    );
  }

  if (closable) {
    actionButtons.push(
      <Button
        key="dismiss"
        onClick={handleClose}
        color="inherit"
        startIcon={<CloseIcon />}
      >
        Dismiss
      </Button>
    );
  }

  const dialogActions = actionButtons.length > 0 ? (
    <Box
      sx={{
        display: 'flex',
        justifyContent: 'flex-end',
        width: '100%',
        flexWrap: 'wrap',
        gap: 1
      }}
    >
      {actionButtons}
    </Box>
  ) : null;

  return (
    <Dialog
      open={isVisible}
      onClose={closable ? handleClose : undefined}
      aria-labelledby="notification-dialog-title"
      aria-describedby="notification-dialog-description"
      role="alertdialog"
      aria-live="assertive"
      aria-atomic="true"
      fullWidth={fullWidth ?? true}
      maxWidth={compact ? 'xs' : 'sm'}
      PaperProps={{
        className,
        'data-severity': severity,
        sx: {
          borderTop: `6px solid ${severityColor}`,
          ...sx
        }
      }}
    >
      <DialogTitle
        id="notification-dialog-title"
        sx={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          gap: 2,
          pr: closable ? 1 : 3
        }}
      >
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.5 }}>
          <Box
            sx={{
              display: 'inline-flex',
              alignItems: 'center',
              justifyContent: 'center',
              color: severityColor,
            }}
          >
            {getSeverityIcon()}
          </Box>
          <Typography component="h2" variant="h6" sx={{ fontWeight: 600 }}>
            {alertTitle}
          </Typography>
        </Box>
      </DialogTitle>

      <DialogContent dividers sx={{ pt: 2 }}>
        <Typography
          id="notification-dialog-description"
          variant="body1"
          sx={{ whiteSpace: 'pre-line' }}
        >
          {normalizedMessage}
        </Typography>

        {detailed && details && (
          <Box sx={{ mt: 2 }}>
            <Button
              onClick={toggleDetails}
              size="small"
              startIcon={showDetails ? <CollapseIcon /> : <ExpandIcon />}
              sx={{ textTransform: 'none' }}
              aria-label={showDetails ? 'Hide details' : 'Show details'}
              aria-expanded={showDetails}
              aria-controls="error-details"
            >
              {showDetails ? 'Hide details' : 'Show details'}
            </Button>
            <Collapse in={showDetails} timeout="auto" unmountOnExit>
              <Box
                id="error-details"
                sx={{
                  mt: 2,
                  p: 2,
                  bgcolor: 'rgba(0, 0, 0, 0.04)',
                  borderRadius: 1,
                  border: '1px solid rgba(0, 0, 0, 0.12)'
                }}
              >
                <Typography variant="caption" color="text.secondary" display="block" gutterBottom>
                  Technical Details:
                </Typography>
                <Typography
                  variant="body2"
                  component="pre"
                  sx={{
                    fontFamily: 'monospace',
                    fontSize: '0.75rem',
                    whiteSpace: 'pre-wrap',
                    wordBreak: 'break-word'
                  }}
                >
                  {normalizedDetails}
                </Typography>
              </Box>
            </Collapse>
          </Box>
        )}
      </DialogContent>

      {dialogActions && (
        <DialogActions sx={{ px: 3, py: 2 }}>
          {dialogActions}
        </DialogActions>
      )}
    </Dialog>
  );
});

// Predefined error alert components for common scenarios
export const NetworkError: React.FC<Omit<ErrorAlertProps, 'category' | 'severity'>> = memo((props) => (
  <ErrorAlert
    {...props}
    category="network"
    severity="error"
    retryable={true}
  />
));

export const AuthenticationError: React.FC<Omit<ErrorAlertProps, 'category' | 'severity'>> = memo((props) => (
  <ErrorAlert
    {...props}
    category="authentication"
    severity="warning"
    retryable={false}
  />
));

export const AuthorizationError: React.FC<Omit<ErrorAlertProps, 'category' | 'severity'>> = memo((props) => (
  <ErrorAlert
    {...props}
    category="authorization"
    severity="warning"
    retryable={false}
  />
));

export const ValidationError: React.FC<Omit<ErrorAlertProps, 'category' | 'severity'>> = memo((props) => (
  <ErrorAlert
    {...props}
    category="validation"
    severity="info"
    retryable={false}
  />
));

export const ServerError: React.FC<Omit<ErrorAlertProps, 'category' | 'severity'>> = memo((props) => (
  <ErrorAlert
    {...props}
    category="server"
    severity="error"
    retryable={true}
  />
));

export const SuccessAlert: React.FC<Omit<ErrorAlertProps, 'severity'>> = memo((props) => (
  <ErrorAlert
    {...props}
    severity="success"
    autoHideDuration={5000}
  />
));

// Helper function to create error alert from HTTP status codes
export const createErrorFromStatus = (
  status: number,
  message?: string,
  details?: string
): Omit<ErrorAlertProps, 'onRetry' | 'onClose'> => {
  switch (status) {
    case 401:
      return {
        category: 'authentication',
        severity: 'warning',
        message: message || 'Please log in to continue.',
        details,
      };
    case 403:
      return {
        category: 'authorization',
        severity: 'warning',
        message: message || 'You do not have permission to perform this action.',
        details,
      };
    case 404:
      return {
        category: 'client',
        severity: 'info',
        message: message || 'The requested resource was not found.',
        details,
      };
    case 408:
      return {
        category: 'timeout',
        severity: 'warning',
        message: message || 'The request took too long to complete.',
        details,
        retryable: true,
      };
    case 500:
    case 502:
    case 503:
      return {
        category: 'server',
        severity: 'error',
        message: message || 'A server error occurred. Please try again later.',
        details,
        retryable: true,
      };
    default:
      return {
        category: 'unknown',
        severity: 'error',
        message: message || 'An unexpected error occurred.',
        details,
        retryable: true,
      };
  }
};

// Add display names for debugging
ErrorAlert.displayName = 'ErrorAlert';
NetworkError.displayName = 'NetworkError';
AuthenticationError.displayName = 'AuthenticationError';
AuthorizationError.displayName = 'AuthorizationError';
ValidationError.displayName = 'ValidationError';
ServerError.displayName = 'ServerError';
SuccessAlert.displayName = 'SuccessAlert';

export default ErrorAlert;
