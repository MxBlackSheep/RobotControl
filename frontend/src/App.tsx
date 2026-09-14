import React, { Suspense } from 'react';
import { Routes, Route, Navigate } from 'react-router-dom';

// Optimized Material-UI imports for better tree-shaking
import Box from '@mui/material/Box';
import AppBar from '@mui/material/AppBar';
import Toolbar from '@mui/material/Toolbar';
import Typography from '@mui/material/Typography';
import Button from '@mui/material/Button';
import IconButton from '@mui/material/IconButton';
import Menu from '@mui/material/Menu';
import MenuItem from '@mui/material/MenuItem';
import MenuIcon from '@mui/icons-material/Menu';
import useTheme from '@mui/material/styles/useTheme';
import useMediaQuery from '@mui/material/useMediaQuery';
import { AuthProvider, useAuth } from './context/AuthContext';
import { loadComponent } from './utils/BundleOptimizer';
import NavigationBreadcrumbs from './components/NavigationBreadcrumbs';
import { PageLoading } from './components/LoadingSpinner';
import AppSidebar from './components/AppSidebar';
import { SchedulingNavigationContext, useSidebarLayout } from './components/navigation';
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
const LabwarePage = loadComponent(() => import('./pages/LabwarePage'));
const MaintenancePage = loadComponent(() => import('./pages/MaintenancePage'));
const LogFilePage = loadComponent(() => import('./pages/LogFilePage'));
const SystemStatusPage = loadComponent(() => import('./pages/MonitoringPage'));
const SchedulingPage = loadComponent(() => import('./pages/SchedulingPage'));
const AboutPage = loadComponent(() => import('./pages/AboutPage'));
const AdminPage = loadComponent(() => import('./pages/AdminPage'));

const AppContent: React.FC = () => {
  const { isAuthenticated, user, logout } = useAuth();
  const theme = useTheme();
  
  // Mobile drawer state
  const [mobileDrawerOpen, setMobileDrawerOpen] = React.useState(false);
  const [accountAnchor, setAccountAnchor] = React.useState<HTMLElement | null>(null);
  const [passwordDialogOpen, setPasswordDialogOpen] = React.useState(false);
  const { mobile: isMobile, expanded: sidebarExpanded, toggle: toggleSidebar } = useSidebarLayout();
  const [recoveryActive, setRecoveryActive] = React.useState(false);
  const navigationContext = React.useMemo(() => ({ recoveryActive, setRecoveryActive }), [recoveryActive]);
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

  if (!isAuthenticated) {
    return <LoginPage />;
  }

  return (
    <SchedulingNavigationContext.Provider value={navigationContext}><Box sx={{ minHeight: '100vh', bgcolor: 'background.default', display: 'flex' }}>
      <AppSidebar user={user} mobile={isMobile} expanded={sidebarExpanded} open={mobileDrawerOpen} onClose={() => setMobileDrawerOpen(false)} onToggle={toggleSidebar} />
      <Box sx={{ flex: 1, minWidth: 0 }}>
      {/* Skip Link for Accessibility */}
      <SkipLink />
      <MaintenanceDialog />
      
      <AppBar position="sticky" elevation={0} sx={{ bgcolor: 'background.paper', color: 'text.primary', borderBottom: 1, borderColor: 'divider' }}>
        <Toolbar sx={{ minHeight: '56px !important', px: { xs: 1, md: 2 }, gap: 1 }}>
          {isMobile && <IconButton aria-label="Open navigation" onClick={() => setMobileDrawerOpen(true)}><MenuIcon /></IconButton>}
          <Box sx={{ flex: 1, minWidth: 0 }}><NavigationBreadcrumbs compact showIcons={false} maxItems={isMobile ? 2 : 4} /></Box>
          <Button color="inherit" aria-haspopup="menu" aria-expanded={!!accountAnchor} onClick={event => setAccountAnchor(event.currentTarget)}>{user?.username} · {roleLabel}</Button>
        </Toolbar>
      </AppBar>
      <Menu anchorEl={accountAnchor} open={!!accountAnchor} onClose={() => setAccountAnchor(null)}>
        <MenuItem onClick={() => { setAccountAnchor(null); setPasswordDialogOpen(true); }}>Change password</MenuItem>
        <MenuItem onClick={() => { setAccountAnchor(null); logout(); }}>Log out</MenuItem>
      </Menu>

      {/* Main Content Area */}
      <Box 
        component="main"
        id="main-content"
        sx={{ p: { xs: 2, md: 3 }, minWidth: 0 }} // Less padding on mobile
        tabIndex={-1} // Make focusable for skip link
      >
        <Suspense fallback={<PageLoading message="Loading page..." />}>
          <Routes>
            <Route path="/" element={<Dashboard />} />
            <Route path="/database" element={<DatabasePage />} />
            <Route path="/camera" element={<CameraPage />} />
            {(['admin', 'user'].includes(user?.role || '')) && (
              <Route path="/labware" element={<LabwarePage />} />
            )}
            <Route path="/maintenance" element={<MaintenancePage />} />
            <Route path="/logfile" element={<LogFilePage />} />
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
    </Box></SchedulingNavigationContext.Provider>
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
