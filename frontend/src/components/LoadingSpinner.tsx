/**
 * LoadingSpinner - Unified loading component for PyRobot
 * 
 * Provides consistent loading states across the application with multiple variants:
 * - Spinner: Traditional circular progress indicator
 * - Skeleton: Content placeholder for better perceived performance
 * - Inline: Small loading indicators for buttons/actions
 * - Fullscreen: Page-level loading states
 */

import React, { memo } from 'react';

// Optimized Material-UI imports for better tree-shaking
import Box from '@mui/material/Box';
import CircularProgress from '@mui/material/CircularProgress';
import LinearProgress from '@mui/material/LinearProgress';
import Skeleton from '@mui/material/Skeleton';
import Typography from '@mui/material/Typography';
import Card from '@mui/material/Card';
import CardContent from '@mui/material/CardContent';
import { useTheme } from '@mui/material/styles';

// Component prop interfaces
export interface LoadingSpinnerProps {
  /** Loading variant type */
  variant?: 'spinner' | 'skeleton' | 'linear' | 'inline' | 'fullscreen';
  /** Size of the loading indicator */
  size?: 'small' | 'medium' | 'large' | number;
  /** Optional loading message */
  message?: string;
  /** Color theme */
  color?: 'primary' | 'secondary' | 'inherit';
  /** Custom styling */
  className?: string;
  /** Show delay before displaying (prevents flash for fast operations) */
  delay?: number;
  /** For skeleton variant - number of lines */
  lines?: number;
  /** For skeleton variant - custom widths for each line */
  widths?: (string | number)[];
  /** Center the loading indicator */
  center?: boolean;
  /** Minimum height for container */
  minHeight?: number | string;
}

// Default skeleton line configurations
const defaultSkeletonWidths = {
  1: ['80%'],
  2: ['100%', '60%'],
  3: ['100%', '80%', '40%'],
  4: ['100%', '90%', '70%', '50%'],
  5: ['100%', '95%', '85%', '65%', '45%'],
};

const LoadingSpinner: React.FC<LoadingSpinnerProps> = memo(({
  variant = 'spinner',
  size = 'medium',
  message,
  color = 'primary',
  className,
  delay = 0,
  lines = 3,
  widths,
  center = true,
  minHeight,
}) => {
  const theme = useTheme();
  const [showLoading, setShowLoading] = React.useState(delay === 0);

  // Handle delay before showing loading indicator
  React.useEffect(() => {
    if (delay > 0) {
      const timer = setTimeout(() => setShowLoading(true), delay);
      return () => clearTimeout(timer);
    }
  }, [delay]);

  if (!showLoading) {
    return null;
  }

  // Get size value for CircularProgress
  const getSpinnerSize = (): number => {
    if (typeof size === 'number') return size;
    switch (size) {
      case 'small': return 20;
      case 'medium': return 40;
      case 'large': return 60;
      default: return 40;
    }
  };

  // Get skeleton heights based on size
  const getSkeletonHeight = (): number => {
    switch (size) {
      case 'small': return 16;
      case 'medium': return 24;
      case 'large': return 32;
      default: return 24;
    }
  };

  // Common container styling
  const containerStyles = {
    display: center ? 'flex' : 'block',
    ...(center && {
      justifyContent: 'center',
      alignItems: 'center',
      flexDirection: 'column' as const,
    }),
    ...(minHeight && { minHeight }),
    ...(className && { className }),
  };

  // Render based on variant
  switch (variant) {
    case 'spinner':
      return (
        <Box sx={containerStyles}>
          <CircularProgress 
            size={getSpinnerSize()} 
            color={color}
            thickness={4}
          />
          {message && (
            <Typography 
              variant="body2" 
              color="text.secondary" 
              sx={{ mt: 2, textAlign: 'center' }}
            >
              {message}
            </Typography>
          )}
        </Box>
      );

    case 'linear':
      return (
        <Box sx={{ ...containerStyles, width: '100%' }}>
          <LinearProgress color={color} />
          {message && (
            <Typography 
              variant="body2" 
              color="text.secondary" 
              sx={{ mt: 1, textAlign: center ? 'center' : 'left' }}
            >
              {message}
            </Typography>
          )}
        </Box>
      );

    case 'inline':
      return (
        <Box sx={{ 
          display: 'inline-flex', 
          alignItems: 'center', 
          gap: 1,
          className 
        }}>
          <CircularProgress 
            size={getSpinnerSize()} 
            color={color}
            thickness={4}
          />
          {message && (
            <Typography variant="body2" color="text.secondary">
              {message}
            </Typography>
          )}
        </Box>
      );

    case 'fullscreen':
      return (
        <Box sx={{
          position: 'fixed',
          top: 0,
          left: 0,
          right: 0,
          bottom: 0,
          display: 'flex',
          flexDirection: 'column',
          justifyContent: 'center',
          alignItems: 'center',
          backgroundColor: 'rgba(255, 255, 255, 0.8)',
          backdropFilter: 'blur(2px)',
          zIndex: theme.zIndex.modal,
          className,
        }}>
          <CircularProgress 
            size={getSpinnerSize()} 
            color={color}
            thickness={4}
          />
          {message && (
            <Typography 
              variant="h6" 
              color="text.primary" 
              sx={{ mt: 3, textAlign: 'center', fontWeight: 500 }}
            >
              {message}
            </Typography>
          )}
        </Box>
      );

    case 'skeleton':
    default:
      const skeletonWidths = widths || defaultSkeletonWidths[Math.min(lines, 5) as keyof typeof defaultSkeletonWidths] || defaultSkeletonWidths[3];
      const height = getSkeletonHeight();

      return (
        <Box sx={containerStyles}>
          {skeletonWidths.slice(0, lines).map((width, index) => (
            <Skeleton
              key={index}
              variant="text"
              width={width}
              height={height}
              sx={{ 
                mb: index < lines - 1 ? 1 : 0,
                fontSize: height,
              }}
            />
          ))}
          {message && (
            <Typography 
              variant="caption" 
              color="text.secondary" 
              sx={{ mt: 1, fontStyle: 'italic' }}
            >
              {message}
            </Typography>
          )}
        </Box>
      );
  }
});

// Predefined loading components for common use cases
export const TableLoading: React.FC<{ rows?: number }> = memo(({ rows = 5 }) => (
  <Card>
    <CardContent>
      <LoadingSpinner
        variant="skeleton"
        lines={rows}
        widths={['100%', '85%', '90%', '75%', '95%']}
        size="medium"
        message="Loading table data..."
      />
    </CardContent>
  </Card>
));

export const PageLoading: React.FC<{ message?: string }> = memo(({ message = 'Loading page...' }) => (
  <Box sx={{ 
    display: 'flex', 
    justifyContent: 'center', 
    alignItems: 'center',
    minHeight: 400,
    flexDirection: 'column'
  }}>
    <LoadingSpinner
      variant="spinner"
      size="large"
      message={message}
    />
  </Box>
));

export const ButtonLoading: React.FC<{ message?: string; size?: LoadingSpinnerProps['size'] }> = memo(({
  message,
  size = 'small',
}) => (
  <LoadingSpinner
    variant="inline"
    size={size}
    message={message}
  />
));

export const CardLoading: React.FC<{ lines?: number; message?: string }> = memo(({ 
  lines = 3, 
  message = 'Loading...'
}) => (
  <Card>
    <CardContent>
      <LoadingSpinner
        variant="skeleton"
        lines={lines}
        size="medium"
        message={message}
      />
    </CardContent>
  </Card>
));

// Add display names for debugging
LoadingSpinner.displayName = 'LoadingSpinner';
TableLoading.displayName = 'TableLoading';
PageLoading.displayName = 'PageLoading';
ButtonLoading.displayName = 'ButtonLoading';
CardLoading.displayName = 'CardLoading';

export default LoadingSpinner;