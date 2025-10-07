/**
 * Accessible Status Indicator Component
 * 
 * Provides status indication using multiple sensory channels:
 * - Color (for users with normal vision)
 * - Icons (for visual clarity and meaning)  
 * - Patterns/textures (for color-blind users)
 * - Text labels (for screen readers)
 * - Animation cues (for dynamic states)
 * 
 * Meets WCAG 2.1 AA standards for color accessibility
 */

import React from 'react';
import { 
  Chip, 
  ChipProps, 
  Badge,
  Box,
  Typography
} from '@mui/material';
import {
  CheckCircle as SuccessIcon,
  Error as ErrorIcon,
  Warning as WarningIcon,
  Info as InfoIcon,
  CircleOutlined as NeutralIcon
} from '@mui/icons-material';

export type StatusType = 'success' | 'error' | 'warning' | 'info' | 'neutral';

export interface AccessibleStatusIndicatorProps extends Omit<ChipProps, 'color' | 'variant'> {
  status: StatusType;
  label: string;
  variant?: 'chip' | 'badge' | 'text';
  showIcon?: boolean;
  showPattern?: boolean;
  animate?: boolean;
  ariaLabel?: string;
}

// Status configuration with accessibility features
const statusConfig = {
  success: {
    color: 'success' as const,
    icon: <SuccessIcon />,
    pattern: 'solid',
    bgPattern: 'none',
    borderStyle: 'solid',
    animation: 'none',
    ariaLabel: 'Success status'
  },
  error: {
    color: 'error' as const,
    icon: <ErrorIcon />,
    pattern: 'striped',
    bgPattern: 'repeating-linear-gradient(45deg, rgba(198, 40, 40, 0.1), rgba(198, 40, 40, 0.1) 8px, transparent 8px, transparent 16px)',
    borderStyle: 'dashed',
    animation: 'none',
    ariaLabel: 'Error status'
  },
  warning: {
    color: 'warning' as const,
    icon: <WarningIcon />,
    pattern: 'dotted', 
    bgPattern: 'radial-gradient(circle, rgba(239, 108, 0, 0.1) 2px, transparent 2px)',
    borderStyle: 'dotted',
    animation: 'none',
    ariaLabel: 'Warning status'
  },
  info: {
    color: 'info' as const,
    icon: <InfoIcon />,
    pattern: 'double',
    bgPattern: 'none',
    borderStyle: 'double',
    animation: 'none',
    ariaLabel: 'Information status'
  },
  neutral: {
    color: 'default' as const,
    icon: <NeutralIcon />,
    pattern: 'none',
    bgPattern: 'none',
    borderStyle: 'solid',
    animation: 'none',
    ariaLabel: 'Neutral status'
  }
} as const;

const AccessibleStatusIndicator: React.FC<AccessibleStatusIndicatorProps> = ({
  status,
  label,
  variant = 'chip',
  showIcon = true,
  showPattern = true,
  animate = false,
  ariaLabel,
  sx,
  ...props
}) => {
  const config = statusConfig[status];
  const finalAriaLabel = ariaLabel || `${config.ariaLabel}: ${label}`;

  // Base styles with accessibility enhancements
  const baseStyles = {
    // Background pattern for color-blind users
    backgroundImage: showPattern ? config.bgPattern : 'none',
    // Border style variations
    borderStyle: showPattern ? config.borderStyle : 'solid',
    // Animation for dynamic states
    animation: animate && config.animation !== 'none' ? config.animation : 'none',
    // Pulse animation for active/running states
    ...(animate && status === 'success' && {
      animation: 'pulse 2s infinite',
      '@keyframes pulse': {
        '0%': { opacity: 1 },
        '50%': { opacity: 0.7 },
        '100%': { opacity: 1 }
      }
    }),
    ...sx
  };

  switch (variant) {
    case 'chip':
      return (
        <Chip
          icon={showIcon ? config.icon : undefined}
          label={label}
          color={config.color}
          sx={baseStyles}
          aria-label={finalAriaLabel}
          role="status"
          {...props}
        />
      );

    case 'badge':
      return (
        <Badge
          badgeContent={
            <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5 }}>
              {showIcon && config.icon}
              <Typography variant="caption">{label}</Typography>
            </Box>
          }
          color={config.color}
          sx={baseStyles}
          aria-label={finalAriaLabel}
          {...props}
        />
      );

    case 'text':
      return (
        <Box 
          sx={{
            display: 'inline-flex',
            alignItems: 'center',
            gap: 1,
            padding: '4px 8px',
            borderRadius: '4px',
            ...baseStyles
          }}
          role="status"
          aria-label={finalAriaLabel}
        >
          {showIcon && (
            <Box sx={{ color: `${config.color}.main` }}>
              {config.icon}
            </Box>
          )}
          <Typography variant="body2" color={`${config.color}.main`}>
            {label}
          </Typography>
        </Box>
      );

    default:
      return null;
  }
};

// Pre-configured common status indicators for convenience
export const StatusIndicators = {
  Success: (props: Omit<AccessibleStatusIndicatorProps, 'status'>) => (
    <AccessibleStatusIndicator status="success" {...props} />
  ),
  Error: (props: Omit<AccessibleStatusIndicatorProps, 'status'>) => (
    <AccessibleStatusIndicator status="error" {...props} />
  ),
  Warning: (props: Omit<AccessibleStatusIndicatorProps, 'status'>) => (
    <AccessibleStatusIndicator status="warning" {...props} />
  ),
  Info: (props: Omit<AccessibleStatusIndicatorProps, 'status'>) => (
    <AccessibleStatusIndicator status="info" {...props} />
  ),
  Neutral: (props: Omit<AccessibleStatusIndicatorProps, 'status'>) => (
    <AccessibleStatusIndicator status="neutral" {...props} />
  )
};

export default AccessibleStatusIndicator;