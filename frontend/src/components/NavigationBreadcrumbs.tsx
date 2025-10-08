/**
 * NavigationBreadcrumbs Component
 * 
 * Provides hierarchical navigation breadcrumbs based on the current route
 * Shows the user's current location within the application
 * Supports both main navigation and sub-page navigation
 */

import React, { useMemo } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';

// Optimized Material-UI imports for better tree-shaking
import Breadcrumbs from '@mui/material/Breadcrumbs';
import Link from '@mui/material/Link';
import Typography from '@mui/material/Typography';
import Box from '@mui/material/Box';
import {
  Home as HomeIcon,
  Storage as DatabaseIcon,
  Videocam as CameraIcon,
  MonitorHeart as MonitoringIcon,
  Schedule as ScheduleIcon,
  Info as InfoIcon,
  NavigateNext as NavigateNextIcon,
} from '@mui/icons-material';

// Component props
interface NavigationBreadcrumbsProps {
  /** Custom separator icon (defaults to NavigateNext) */
  separator?: React.ReactNode;
  /** Maximum number of breadcrumbs to show */
  maxItems?: number;
  /** Custom styling className */
  className?: string;
  /** Show icons alongside breadcrumb text */
  showIcons?: boolean;
  /** Compact mode for smaller spaces */
  compact?: boolean;
}

// Route configuration for breadcrumb generation
interface BreadcrumbConfig {
  path: string;
  label: string;
  icon?: React.ReactNode;
  parent?: string;
  requiresAuth?: boolean;
  requiresRole?: string[];
}

// Route configurations
const routeConfigs: BreadcrumbConfig[] = [
  {
    path: '/',
    label: 'Dashboard',
    icon: <HomeIcon fontSize="small" />,
  },
  {
    path: '/database',
    label: 'Database',
    icon: <DatabaseIcon fontSize="small" />,
  },
  {
    path: '/camera',
    label: 'Camera System',
    icon: <CameraIcon fontSize="small" />,
  },
  {
    path: '/system-status',
    label: 'System Status',
    icon: <MonitoringIcon fontSize="small" />,
  },
  {
    path: '/scheduling',
    label: 'Scheduling',
    icon: <ScheduleIcon fontSize="small" />,
    requiresRole: ['admin', 'user'],
  },
  {
    path: '/about',
    label: 'About',
    icon: <InfoIcon fontSize="small" />,
  },
];

// Helper function to get breadcrumb trail for a given path
const getBreadcrumbTrail = (pathname: string): BreadcrumbConfig[] => {
  const trail: BreadcrumbConfig[] = [];
  
  // Find the current route config
  const currentConfig = routeConfigs.find(config => config.path === pathname);
  
  if (!currentConfig) {
    // Fallback for unknown routes - just show dashboard
    const dashboardConfig = routeConfigs.find(config => config.path === '/');
    if (dashboardConfig) {
      trail.push(dashboardConfig);
    }
    return trail;
  }
  
  // Build trail by following parent relationships
  let current = currentConfig;
  const visited = new Set<string>(); // Prevent infinite loops
  
  while (current && !visited.has(current.path)) {
    visited.add(current.path);
    trail.unshift(current); // Add to beginning to maintain order
    
    if (current.parent) {
      const parentConfig = routeConfigs.find(config => config.path === current.parent);
      current = parentConfig || null;
    } else {
      // If no parent and not already dashboard, add dashboard as root
      if (current.path !== '/') {
        const dashboardConfig = routeConfigs.find(config => config.path === '/');
        if (dashboardConfig) {
          trail.unshift(dashboardConfig);
        }
      }
      break;
    }
  }
  
  return trail;
};

const NavigationBreadcrumbs: React.FC<NavigationBreadcrumbsProps> = ({
  separator = <NavigateNextIcon fontSize="small" />,
  maxItems = 6,
  className,
  showIcons = true,
  compact = false,
}) => {
  const location = useLocation();
  const navigate = useNavigate();
  
  // Generate breadcrumb trail based on current location
  const breadcrumbTrail = useMemo(() => {
    return getBreadcrumbTrail(location.pathname);
  }, [location.pathname]);
  
  // Handle breadcrumb click navigation
  const handleBreadcrumbClick = (path: string) => (event: React.MouseEvent) => {
    event.preventDefault();
    navigate(path);
  };
  
  // Don't render breadcrumbs if there's only one item (current page)
  if (breadcrumbTrail.length <= 1) {
    return null;
  }
  
  return (
    <Box 
      className={className}
      sx={{ 
        py: compact ? 0.5 : 1,
        px: compact ? 1 : 0,
      }}
    >
      <Breadcrumbs
        separator={separator}
        maxItems={maxItems}
        aria-label="navigation breadcrumbs"
        sx={{
          '& .MuiBreadcrumbs-separator': {
            color: 'text.secondary',
            mx: compact ? 0.5 : 1,
          },
        }}
      >
        {breadcrumbTrail.map((config, index) => {
          const isLast = index === breadcrumbTrail.length - 1;
          const isClickable = !isLast && config.path !== location.pathname;
          
          const breadcrumbContent = (
            <Box 
              sx={{ 
                display: 'flex', 
                alignItems: 'center',
                gap: compact ? 0.5 : 0.75,
              }}
            >
              {showIcons && config.icon && (
                <Box sx={{ 
                  color: isLast ? 'text.primary' : 'text.secondary',
                  display: 'flex',
                  alignItems: 'center',
                }}>
                  {config.icon}
                </Box>
              )}
              <Typography
                variant={compact ? "body2" : "body1"}
                sx={{
                  color: isLast ? 'text.primary' : 'text.secondary',
                  fontWeight: isLast ? 500 : 400,
                  fontSize: compact ? '0.75rem' : undefined,
                }}
              >
                {config.label}
              </Typography>
            </Box>
          );
          
          if (isClickable) {
            return (
              <Link
                key={config.path}
                href={config.path}
                onClick={handleBreadcrumbClick(config.path)}
                sx={{
                  textDecoration: 'none',
                  color: 'inherit',
                  cursor: 'pointer',
                  '&:hover': {
                    textDecoration: 'underline',
                    '& .MuiTypography-root': {
                      color: 'primary.main',
                    },
                    '& svg': {
                      color: 'primary.main',
                    },
                  },
                }}
              >
                {breadcrumbContent}
              </Link>
            );
          }
          
          return (
            <Box key={config.path}>
              {breadcrumbContent}
            </Box>
          );
        })}
      </Breadcrumbs>
    </Box>
  );
};

export default NavigationBreadcrumbs;
