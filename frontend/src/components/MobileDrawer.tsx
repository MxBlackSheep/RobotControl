/**
 * MobileDrawer Component - Mobile-optimized navigation drawer
 * 
 * Features:
 * - Touch-friendly navigation for mobile devices (< 768px)
 * - Sliding drawer with overlay
 * - Role-based navigation items
 * - Touch-friendly controls (44px minimum touch targets)
 * - Gesture-based opening/closing
 */

import React, { useState, useEffect } from 'react';
import { useNavigate, useLocation } from 'react-router-dom';

// Optimized Material-UI imports for better tree-shaking
import Drawer from '@mui/material/Drawer';
import List from '@mui/material/List';
import ListItem from '@mui/material/ListItem';
import ListItemButton from '@mui/material/ListItemButton';
import ListItemIcon from '@mui/material/ListItemIcon';
import ListItemText from '@mui/material/ListItemText';
import IconButton from '@mui/material/IconButton';
import Box from '@mui/material/Box';
import Typography from '@mui/material/Typography';
import Divider from '@mui/material/Divider';
import useTheme from '@mui/material/styles/useTheme';
import useMediaQuery from '@mui/material/useMediaQuery';

// Icons
import {
  Menu as MenuIcon,
  Close as CloseIcon,
  Dashboard as DashboardIcon,
  Storage as DatabaseIcon,
  Videocam as CameraIcon,
  MonitorHeart as MonitoringIcon,
  Schedule as SchedulingIcon,
  Logout as LogoutIcon,
  Person as UserIcon,
  Info as InfoIcon,
} from '@mui/icons-material';

import { useAuth } from '../context/AuthContext';

interface NavigationItem {
  label: string;
  path: string;
  icon: React.ReactNode;
  roles?: string[];
}

interface MobileDrawerProps {
  /**
   * Whether the drawer is open
   */
  isOpen?: boolean;
  /**
   * Callback when drawer state changes
   */
  onToggle?: (open: boolean) => void;
  /**
   * Force mobile mode regardless of screen size (for testing)
   */
  forceMobile?: boolean;
}

const MobileDrawer: React.FC<MobileDrawerProps> = ({
  isOpen = false,
  onToggle,
  forceMobile = false
}) => {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const theme = useTheme();
  
  // Check if we're on mobile
  const isMobileScreen = useMediaQuery(theme.breakpoints.down('md')); // < 768px
  const isMobile = forceMobile || isMobileScreen;

  const [drawerOpen, setDrawerOpen] = useState(isOpen);

  // Navigation items with role-based filtering
  const navigationItems: NavigationItem[] = [
    {
      label: 'Dashboard',
      path: '/',
      icon: <DashboardIcon />,
    },
    {
      label: 'Database',
      path: '/database',
      icon: <DatabaseIcon />,
    },
    {
      label: 'Scheduling',
      path: '/scheduling',
      icon: <SchedulingIcon />,
      roles: ['admin', 'user'], // Only visible to admin and user roles
    },
    {
      label: 'Camera',
      path: '/camera',
      icon: <CameraIcon />,
    },
    {
      label: 'System Status',
      path: '/system-status',
      icon: <MonitoringIcon />,
    },
    {
      label: 'About',
      path: '/about',
      icon: <InfoIcon />,
    },
  ];

  // Filter navigation items based on user role
  const visibleNavigationItems = navigationItems.filter(item => {
    if (!item.roles) return true; // No role restriction
    return item.roles.includes(user?.role || '');
  });

  // Update internal state when prop changes
  useEffect(() => {
    setDrawerOpen(isOpen);
  }, [isOpen]);

  // Handle drawer toggle
  const handleDrawerToggle = (open: boolean) => {
    setDrawerOpen(open);
    onToggle?.(open);
  };

  // Handle navigation
  const handleNavigation = (path: string) => {
    navigate(path);
    handleDrawerToggle(false); // Close drawer after navigation
  };

  // Handle logout
  const handleLogout = () => {
    logout();
    handleDrawerToggle(false);
  };

  // Don't render on desktop unless forced
  if (!isMobile) {
    return null;
  }

  // Get current path for highlighting active item
  const currentPath = location.pathname;
  
  const drawerContent = (
    <Box
      sx={{ 
        width: 280,
        height: '100%',
        display: 'flex',
        flexDirection: 'column'
      }}
      role="presentation"
    >
      {/* Header */}
      <Box
        sx={{
          p: 2,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          bgcolor: 'primary.main',
          color: 'primary.contrastText',
          minHeight: 64, // Match AppBar height
        }}
      >
        <Box sx={{ display: 'flex', alignItems: 'center' }}>
          <UserIcon sx={{ mr: 1 }} />
          <Box>
            <Typography variant="subtitle1" sx={{ fontWeight: 600, lineHeight: 1.2 }}>
              {user?.username}
            </Typography>
            <Typography variant="caption" sx={{ opacity: 0.8 }}>
              {user?.role}
            </Typography>
          </Box>
        </Box>
        <IconButton
          onClick={() => handleDrawerToggle(false)}
          sx={{
            color: 'inherit',
            minWidth: 44,
            minHeight: 44, // Touch-friendly minimum
          }}
          aria-label="Close navigation menu"
        >
          <CloseIcon />
        </IconButton>
      </Box>

      <Divider />

      {/* Navigation Items */}
      <List sx={{ flex: 1, px: 1, py: 0 }}>
        {visibleNavigationItems.map((item) => {
          const isActive = currentPath === item.path || 
                          (item.path !== '/' && currentPath.startsWith(item.path));
          
          return (
            <ListItem key={item.path} disablePadding>
              <ListItemButton
                onClick={() => handleNavigation(item.path)}
                selected={isActive}
                sx={{
                  minHeight: 44, // Touch-friendly minimum
                  borderRadius: 1,
                  mx: 0.5,
                  my: 0.25,
                  '&.Mui-selected': {
                    bgcolor: 'primary.main',
                    color: 'primary.contrastText',
                    '&:hover': {
                      bgcolor: 'primary.dark',
                    },
                    '& .MuiListItemIcon-root': {
                      color: 'primary.contrastText',
                    },
                  },
                  '&:hover': {
                    bgcolor: 'action.hover',
                    borderRadius: 1,
                  },
                }}
                aria-label={`Navigate to ${item.label}`}
              >
                <ListItemIcon 
                  sx={{ 
                    minWidth: 40,
                    color: isActive ? 'inherit' : 'text.secondary'
                  }}
                >
                  {item.icon}
                </ListItemIcon>
                <ListItemText 
                  primary={item.label}
                  primaryTypographyProps={{
                    fontWeight: isActive ? 600 : 400,
                  }}
                />
              </ListItemButton>
            </ListItem>
          );
        })}
      </List>

      <Divider />

      {/* Logout Button */}
      <List sx={{ px: 1, pb: 1 }}>
        <ListItem disablePadding>
          <ListItemButton
            onClick={handleLogout}
            sx={{
              minHeight: 44, // Touch-friendly minimum
              borderRadius: 1,
              mx: 0.5,
              my: 0.25,
              color: 'error.main',
              '&:hover': {
                bgcolor: 'error.light',
                color: 'error.contrastText',
                '& .MuiListItemIcon-root': {
                  color: 'error.contrastText',
                },
              },
            }}
            aria-label="Logout"
          >
            <ListItemIcon sx={{ minWidth: 40, color: 'error.main' }}>
              <LogoutIcon />
            </ListItemIcon>
            <ListItemText primary="Logout" />
          </ListItemButton>
        </ListItem>
      </List>
    </Box>
  );

  return (
    <Drawer
      anchor="left"
      open={drawerOpen}
      onClose={() => handleDrawerToggle(false)}
      variant="temporary"
      ModalProps={{
        keepMounted: true, // Better performance on mobile
      }}
      sx={{
        '& .MuiDrawer-paper': {
          width: 280,
          boxSizing: 'border-box',
        },
      }}
      onKeyDown={(event) => {
        // Close drawer on Escape key
        if (event.key === 'Escape') {
          handleDrawerToggle(false);
        }
      }}
    >
      {drawerContent}
    </Drawer>
  );
};

// Menu button component for triggering the drawer
export const MobileMenuButton: React.FC<{
  onClick?: () => void;
  forceMobile?: boolean;
}> = ({ onClick, forceMobile = false }) => {
  const theme = useTheme();
  const isMobileScreen = useMediaQuery(theme.breakpoints.down('md'));
  const isMobile = forceMobile || isMobileScreen;

  if (!isMobile) {
    return null;
  }

  return (
    <IconButton
      color="inherit"
      aria-label="Open navigation menu"
      edge="start"
      onClick={onClick}
      sx={{
        mr: 2,
        minWidth: 44,
        minHeight: 44, // Touch-friendly minimum
      }}
    >
      <MenuIcon />
    </IconButton>
  );
};

export default MobileDrawer;
