import React, { Suspense } from 'react';
import { Routes, Route, Navigate, Link, useLocation } from 'react-router-dom';

// Optimized Material-UI imports for better tree-shaking
import Box from '@mui/material/Box';
import Button from '@mui/material/Button';
import Menu from '@mui/material/Menu';
import MenuItem from '@mui/material/MenuItem';
import Tooltip from '@mui/material/Tooltip';
import { AuthProvider, useAuth } from './context/AuthContext';
import { loadComponent } from './utils/BundleOptimizer';
import LoadingSpinner from './components/LoadingSpinner';
import PageLoadBoundary from './components/PageLoadBoundary';
import AppSidebar from './components/AppSidebar';
import PhoneTabs from './components/PhoneTabs';
import RobotAttentionBanner from './components/RobotAttentionBanner';
import { useSidebarLayout } from './components/navigation';
import SkipLink from './components/SkipLink';
import KeyboardShortcutsHelp from './components/KeyboardShortcutsHelp';
import { useKeyboardNavigation } from './hooks/useKeyboardNavigation';
import { RobotStatusContext, useRobotStatus } from './hooks/useRobotStatus';
import LoginPage from './pages/LoginPage';
import Dashboard from './pages/Dashboard';
import ChangePasswordDialog from './components/ChangePasswordDialog';
import MaintenanceDialog from './components/MaintenanceDialog';
import { AppearanceControl } from './context/AppearanceContext';
import { layout } from './theme';

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
const AccountPage = loadComponent(() => import('./pages/AccountPage'));
const MorePage = loadComponent(() => import('./pages/MorePage'));

function AccountMenu({ compact, onChangePassword }: { compact: boolean; onChangePassword: () => void }) {
  const { user, logout } = useAuth();
  const [anchor, setAnchor] = React.useState<HTMLElement | null>(null);
  const roleLabel = user?.role ? user.role.charAt(0).toUpperCase() + user.role.slice(1) : '';
  return <>
    <Tooltip title={compact ? `${user?.username ?? ''} · ${roleLabel}` : ''} placement="right">
    <Button color="inherit" aria-label="Account menu" aria-haspopup="menu" aria-expanded={!!anchor} onClick={event => setAnchor(event.currentTarget)}
      sx={{ flex: compact ? '0 0 auto' : 1, minWidth: 44, minHeight: 44, px: compact ? 0.5 : 1, justifyContent: 'flex-start', gap: 1.25, color: 'inherit', fontWeight: 400, textAlign: 'left' }}>
      {/* The collapsed rail keeps the signed-in name for assistive technology; the tooltip shows it on hover. */}
      <Box component="span" sx={compact
        ? { position: 'absolute', width: 1, height: 1, overflow: 'hidden', clip: 'rect(0 0 0 0)', whiteSpace: 'nowrap' }
        : { display: 'flex', flexDirection: 'column', minWidth: 0, lineHeight: 1.3 }}>
        <Box component="span" sx={{ fontSize: 14, color: 'rail.activeText', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{user?.username}</Box>
        <Box component="span" sx={{ fontSize: 12, color: 'rail.muted' }}>{roleLabel}</Box>
      </Box>
    </Button>
    </Tooltip>
    <Menu anchorEl={anchor} open={!!anchor} onClose={() => setAnchor(null)}>
      <MenuItem onClick={() => { setAnchor(null); onChangePassword(); }}>Change password</MenuItem>
      <MenuItem component={Link} to="/about" onClick={() => setAnchor(null)}>About</MenuItem>
      <MenuItem onClick={() => { setAnchor(null); logout(); }}>Log out</MenuItem>
    </Menu>
  </>;
}

function AppShell() {
  const { user } = useAuth();
  const [passwordDialogOpen, setPasswordDialogOpen] = React.useState(false);
  React.useEffect(() => { if (user?.must_reset) setPasswordDialogOpen(true); }, [user?.must_reset]);
  const { mobile: isMobile, expanded: sidebarExpanded, toggle: toggleSidebar } = useSidebarLayout();
  const robotStatus = useRobotStatus(user?.username ?? null);
  const { helpOpen: shortcutsHelpOpen, closeHelp: hideShortcutsHelp } = useKeyboardNavigation({ enabled: true });
  const { pathname } = useLocation();
  const railFooter = <Box sx={{ display: 'flex', flexDirection: sidebarExpanded ? 'row' : 'column', alignItems: 'center', gap: 0.5, width: '100%', color: 'rail.text', '& .MuiIconButton-root': { color: 'rail.text' } }}>
    <AccountMenu compact={!sidebarExpanded} onChangePassword={() => setPasswordDialogOpen(true)} />
    <AppearanceControl />
  </Box>;

  return (
    <RobotStatusContext.Provider value={robotStatus}><Box sx={{
      // A fixed frame (see appShell.ts): only main scrolls, so iOS bounce or a collapsing browser
      // toolbar cannot pull the header or page bar away from the screen edge.
      height: '100vh', '@supports (height: 100dvh)': { height: '100dvh' }, overflow: 'hidden', bgcolor: 'background.default', display: 'flex' }}>
      {!isMobile && <AppSidebar user={user} expanded={sidebarExpanded} onToggle={toggleSidebar} footer={railFooter} />}
      <Box sx={{ flex: 1, minWidth: 0, display: 'flex', flexDirection: 'column' }}>
      <SkipLink />
      <MaintenanceDialog />

      <Box component="header" sx={{ flexShrink: 0, zIndex: theme => theme.zIndex.appBar }}>
        <RobotAttentionBanner />
      </Box>

      <Box
        component="main"
        id="main-content"
        sx={{ p: { xs: `${layout.pagePhone}px`, sm: `${layout.page}px` }, flex: 1, minWidth: 0, minHeight: 0, overflowY: 'auto', overscrollBehaviorY: 'contain' }}
        tabIndex={-1} // Make focusable for skip link
      >
        <PageLoadBoundary key={pathname}>
        <Suspense fallback={<LoadingSpinner message="Loading page..." minHeight={400} />}>
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
            <Route path="/account" element={<AccountPage />} />
            <Route path="/more" element={<MorePage />} />
            <Route path="/login" element={<Navigate to="/" replace />} />
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        </Suspense>
        </PageLoadBoundary>
      </Box>

      {isMobile && <PhoneTabs />}

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
    </Box></RobotStatusContext.Provider>
  );
}

const AppContent: React.FC = () => {
  const { isAuthenticated, loading } = useAuth();
  if (loading) {
    return <LoadingSpinner message="Connecting to the server. Your sign-in is saved; retrying automatically..." minHeight={400} />;
  }
  return isAuthenticated ? <AppShell /> : <LoginPage />;
};

function App() {
  return (
    <AuthProvider>
      <AppContent />
    </AuthProvider>
  );
}

export default App;
