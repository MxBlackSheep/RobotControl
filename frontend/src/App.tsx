import React, { Suspense } from 'react';
import { Routes, Route, Navigate, useNavigate, useLocation } from 'react-router-dom';

// Optimized Material-UI imports for better tree-shaking
import Box from '@mui/material/Box';
import AppBar from '@mui/material/AppBar';
import Toolbar from '@mui/material/Toolbar';
import Typography from '@mui/material/Typography';
import Button from '@mui/material/Button';
import Tabs from '@mui/material/Tabs';
import Tab from '@mui/material/Tab';
import useTheme from '@mui/material/styles/useTheme';
import useMediaQuery from '@mui/material/useMediaQuery';
import { AuthProvider, useAuth } from './context/AuthContext';
import { loadComponent } from './utils/BundleOptimizer';
import NavigationBreadcrumbs from './components/NavigationBreadcrumbs';
import { PageLoading } from './components/LoadingSpinner';
import MobileDrawer, { MobileMenuButton } from './components/MobileDrawer';
import SkipLink from './components/SkipLink';
import KeyboardShortcutsHelp, { useKeyboardShortcutsHelp } from './components/KeyboardShortcutsHelp';
import { useKeyboardNavigation } from './hooks/useKeyboardNavigation';
import LoginPage from './pages/LoginPage';
import Dashboard from './pages/Dashboard';
import ChangePasswordDialog from './components/ChangePasswordDialog';
import MaintenanceDialog from './components/MaintenanceDialog';

// Lazy load non-critical pages for better initial load performance
const DatabasePage = loadComponent(() => import('./pages/DatabasePage'));
const CameraPage = loadComponent(() => import('./pages/CameraPage'));
const SystemStatusPage = loadComponent(() => import('./pages/MonitoringPage'));
const SchedulingPage = loadComponent(() => import('./pages/SchedulingPage'));
const AboutPage = loadComponent(() => import('./pages/AboutPage'));
const AdminPage = loadComponent(() => import('./pages/AdminPage'));

const AppContent: React.FC = () => {
  const { isAuthenticated, user, logout } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const theme = useTheme();
  
  // Mobile drawer state
  const [mobileDrawerOpen, setMobileDrawerOpen] = React.useState(false);
  const [passwordDialogOpen, setPasswordDialogOpen] = React.useState(false);
  const isMobile = useMediaQuery(theme.breakpoints.down('md')); // < 768px
  const roleLabel = React.useMemo(() => {
    if (!user?.role) {
      return '';
    }
    return user.role.charAt(0).toUpperCase() + user.role.slice(1);
  }, [user?.role]);

  // Keyboard navigation and shortcuts
  useKeyboardNavigation({ enabled: isAuthenticated });
  const { open: shortcutsHelpOpen, showHelp: showShortcutsHelp, hideHelp: hideShortcutsHelp } = useKeyboardShortcutsHelp();

  React.useEffect(() => {
    if (user?.must_reset) {
      setPasswordDialogOpen(true);
    }
  }, [user?.must_reset]);

  const tabItems = React.useMemo(() => {
    const items = [
      { label: 'Dashboard', path: '/' },
      { label: 'Database', path: '/database' },
    ];

    if (['admin', 'user'].includes(user?.role || '')) {
      items.push({ label: 'Scheduling', path: '/scheduling' });
    }

    items.push(
      { label: 'Camera', path: '/camera' },
      { label: 'System Status', path: '/system-status' },
    );

    if (user?.role === 'admin') {
      items.push({ label: 'Admin', path: '/admin' });
    }

    items.push({ label: 'About', path: '/about' });

    return items;
  }, [user?.role]);

  const tabValue = React.useMemo(() => {
    const index = tabItems.findIndex(item => location.pathname === item.path);
    if (index !== -1) {
      return index;
    }

    // Fallback for nested routes or unknown paths
    const fallback = tabItems.findIndex(item => location.pathname.startsWith(item.path) && item.path !== '/');
    return fallback !== -1 ? fallback : 0;
  }, [location.pathname, tabItems]);

  const handleTabChange = (event: React.SyntheticEvent, newValue: number) => {
    const target = tabItems[newValue];
    if (target) {
      navigate(target.path);
    }
  };

  if (!isAuthenticated) {
    return <LoginPage />;
  }

  return (
    <Box sx={{ minHeight: '100vh', bgcolor: 'background.default' }}>
      {/* Skip Link for Accessibility */}
      <SkipLink />
      <MaintenanceDialog />
      
      <AppBar position="static">
        <Toolbar
          sx={{
            flexWrap: { xs: 'wrap', md: 'nowrap' },
            alignItems: { xs: 'flex-start', sm: 'center' },
            gap: { xs: 1, md: 2 },
            py: { xs: 1, md: 0 },
          }}
        >
          {/* Mobile Menu Button - only visible on mobile */}
          <MobileMenuButton 
            onClick={() => setMobileDrawerOpen(true)} 
          />
          
          <Typography
            variant="h6"
            sx={{
              flexGrow: 1,
              minWidth: { xs: '100%', sm: 'auto' },
              mb: { xs: 0.5, sm: 0 },
            }}
          >
            RobotControl
          </Typography>
          
          {/* User info - hide username on mobile to save space */}
          <Typography 
            variant="body2" 
            sx={{ 
              mr: { sm: 2 },
              display: { xs: 'none', sm: 'block' }
            }}
          >
            {user ? `Welcome, ${user.username}${roleLabel ? ` (${roleLabel})` : ''}` : ''}
          </Typography>
          
          {/* Role indicator for mobile */}
          <Typography 
            variant="body2" 
            sx={{ 
              mr: { xs: 1, sm: 0 },
              display: { xs: 'block', sm: 'none' }
            }}
          >
            {user ? `${user.username}${roleLabel ? ` (${roleLabel})` : ''}` : ''}
          </Typography>
          
          <Box
            sx={{
              display: 'flex',
              flexDirection: 'row',
              alignItems: 'center',
              gap: 1,
              flexWrap: { xs: 'wrap', sm: 'nowrap' },
              width: { xs: '100%', sm: 'auto' },
              justifyContent: { xs: 'flex-end', sm: 'flex-start' },
            }}
          >
            <Button 
              color="inherit" 
              onClick={() => setPasswordDialogOpen(true)}
              sx={{
                minHeight: { xs: 44, sm: 36 }
              }}
            >
              Change Password
            </Button>
            <Button 
              color="inherit" 
              onClick={logout}
              sx={{
                minHeight: { xs: 44, sm: 36 }
              }}
            >
              Logout
            </Button>
          </Box>
        </Toolbar>
      </AppBar>
      
      {/* Navigation Tabs - only visible on desktop */}
      <Box 
        sx={{ 
          borderBottom: 1, 
          borderColor: 'divider', 
          bgcolor: 'background.paper',
          display: { xs: 'none', md: 'block' } // Hide on mobile (< 768px)
        }}
      >
        <Tabs 
          value={tabValue} 
          onChange={handleTabChange}
          aria-label="navigation tabs"
          sx={{ px: 2 }}
        >
          {tabItems.map(item => (
            <Tab key={item.path} label={item.label} />
          ))}
        </Tabs>
      </Box>
      
      {/* Mobile Drawer */}
      <MobileDrawer 
        isOpen={mobileDrawerOpen}
        onToggle={setMobileDrawerOpen}
      />
      
      {/* Navigation Breadcrumbs - more compact on mobile */}
      <Box sx={{ 
        px: { xs: 2, md: 3 }, 
        py: 1, 
        bgcolor: 'background.default',
        borderBottom: 1,
        borderColor: 'divider'
      }}>
        <NavigationBreadcrumbs 
          showIcons={!isMobile} // Hide icons on mobile to save space
          maxItems={isMobile ? 2 : 4} // Fewer items on mobile
        />
      </Box>
      
      {/* Main Content Area */}
      <Box 
        component="main"
        id="main-content"
        sx={{ p: { xs: 2, md: 3 } }} // Less padding on mobile
        tabIndex={-1} // Make focusable for skip link
      >
        <Suspense fallback={<PageLoading message="Loading page..." />}>
          <Routes>
            <Route path="/" element={<Dashboard />} />
            <Route path="/database" element={<DatabasePage />} />
            <Route path="/camera" element={<CameraPage />} />
            <Route path="/system-status" element={<SystemStatusPage />} />
            <Route path="/monitoring" element={<Navigate to="/system-status" replace />} />
            {(['admin', 'user'].includes(user?.role || '')) && (
              <Route path="/scheduling" element={<SchedulingPage />} />
            )}
            <Route
              path="/admin"
              element={user?.role === 'admin' ? <AdminPage /> : <Navigate to="/" replace />}
            />
            <Route path="/about" element={<AboutPage />} />
            <Route path="/login" element={<Navigate to="/" replace />} />
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        </Suspense>
      </Box>
      
      {/* Keyboard Shortcuts Help Dialog */}
      <KeyboardShortcutsHelp
        open={shortcutsHelpOpen}
        onClose={hideShortcutsHelp}
      />

      <ChangePasswordDialog
        open={passwordDialogOpen}
        onClose={() => setPasswordDialogOpen(false)}
        requireChange={Boolean(user?.must_reset)}
      />
    </Box>
  );
};

function App() {
  return (
    <AuthProvider>
      <AppContent />
    </AuthProvider>
  );
}

export default App;
