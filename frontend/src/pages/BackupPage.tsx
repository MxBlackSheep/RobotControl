/**
 * RobotControl Database Backup Page
 * 
 * Dedicated page for database backup and restore operations.
 * Provides full-page backup management interface with:
 * - Page-level error boundaries to prevent crashes
 * - Breadcrumb navigation following app patterns
 * - Admin-only access control
 * - Comprehensive backup management functionality
 * - Integration with main application navigation
 */

import React from 'react';
import {
  Box,
  Container,
  Typography,
  Button,
  Breadcrumbs,
  Link,
  Paper,
  Stack,
  Card,
  CardContent
} from '@mui/material';
import {
  ArrowBack as ArrowBackIcon,
  Home as HomeIcon,
  AdminPanelSettings as AdminIcon,
  Storage as BackupIcon
} from '@mui/icons-material';
import { useNavigate, Link as RouterLink } from 'react-router-dom';
import { useAuthContext } from '../context/AuthContext';
import BackupManager from '../components/BackupManager';
import BackupErrorBoundary from '../components/BackupErrorBoundary';
import {
  AuthenticationError,
  AuthorizationError
} from '../components/ErrorAlert';

/**
 * BackupPage Component
 * 
 * Full-page interface for database backup operations.
 * Implements admin-only access control and proper navigation patterns.
 */
const BackupPage: React.FC = () => {
  const navigate = useNavigate();
  const { user } = useAuthContext();

  // Admin access control - following CLAUDE.md security principles
  if (!user) {
    return (
      <AuthenticationError
        title="Authentication Required"
        message="Please log in to access backup management functionality."
        retryable={false}
        actions={
          <Button variant="contained" onClick={() => navigate('/login')}>
            Go to Login
          </Button>
        }
        onClose={() => navigate('/login')}
      />
    );
  }

  if (user.role !== 'admin') {
    return (
      <AuthorizationError
        title="Admin Access Required"
        message="Database backup operations require administrator privileges. Contact your system administrator for access."
        retryable={false}
        actions={
          <Button
            startIcon={<ArrowBackIcon />}
            onClick={() => navigate('/')}
            variant="outlined"
          >
            Return to Dashboard
          </Button>
        }
        onClose={() => navigate('/')}
      />
    );
  }

  /**
   * Handle successful backup operations
   * Provides user feedback and optional navigation
   */
  const handleBackupCreated = () => {
    // BackupManager handles notifications
    // Could add additional page-level actions here if needed
  };

  const handleBackupRestored = () => {
    // BackupManager handles notifications
    // Could add additional page-level actions here if needed
  };

  const handleBackupDeleted = () => {
    // BackupManager handles notifications
    // Could add additional page-level actions here if needed
  };

  /**
   * Handle page-level errors
   * Provides fallback error handling if BackupManager fails
   */
  const handleBackupError = (error: string) => {
    console.error('Backup page error:', error);
    // Additional error handling could be added here
    // (e.g., reporting to error tracking service)
  };

  return (
    <Container maxWidth="xl" sx={{ mt: 2, mb: 4 }}>
      {/* Page Header with Navigation */}
      <Box sx={{ mb: 3 }}>
        {/* Navigation Controls */}
        <Stack direction="row" alignItems="center" spacing={2} sx={{ mb: 2 }}>
          <Button
            startIcon={<ArrowBackIcon />}
            onClick={() => navigate(-1)}
            variant="outlined"
            size="small"
          >
            Back
          </Button>

          {/* Breadcrumb Navigation */}
          <Breadcrumbs aria-label="backup page breadcrumb">
            <Link
              component={RouterLink}
              to="/"
              underline="hover"
              color="inherit"
              sx={{ display: 'flex', alignItems: 'center' }}
            >
              <HomeIcon sx={{ mr: 0.5, fontSize: 18 }} />
              Dashboard
            </Link>
            <Link
              component={RouterLink}
              to="/admin"
              underline="hover"
              color="inherit"
              sx={{ display: 'flex', alignItems: 'center' }}
            >
              <AdminIcon sx={{ mr: 0.5, fontSize: 18 }} />
              Admin
            </Link>
            <Typography
              color="text.primary"
              sx={{ display: 'flex', alignItems: 'center' }}
            >
              <BackupIcon sx={{ mr: 0.5, fontSize: 18 }} />
              Backup Manager
            </Typography>
          </Breadcrumbs>
        </Stack>

        {/* Page Title */}
        <Typography variant="h4" component="h1" sx={{ fontWeight: 700, mb: 1 }}>
          Database Backup Manager
        </Typography>
        <Typography variant="body1" color="text.secondary" sx={{ mb: 2 }}>
          Create, restore, and manage database backups for the RobotControl system.
          All backup operations are logged and secured for administrator access only.
        </Typography>

        {/* Information Box */}
        <Card variant="outlined" sx={{ mb: 3 }}>
          <CardContent>
            <Typography variant="subtitle2" gutterBottom>
              Important Notes
            </Typography>
            <Typography variant="body2" component="div">
              • Backup operations may temporarily affect database connectivity
              <br />
              • Restore operations will replace all current data with backup content
              <br />
              • Always verify backup integrity before performing restore operations
              <br />
              • Large databases may require several minutes to backup or restore
            </Typography>
          </CardContent>
        </Card>
      </Box>

      {/* Main Content with Error Boundary */}
      <Paper elevation={1} sx={{ overflow: 'hidden' }}>
        <BackupErrorBoundary
          onError={handleBackupError}
          fallback={
            <Box sx={{ p: 4, textAlign: 'center' }}>
              <BackupIcon sx={{ fontSize: 64, color: 'text.secondary', mb: 2 }} />
              <Typography variant="h6" color="textSecondary" gutterBottom>
                Backup System Unavailable
              </Typography>
              <Typography variant="body2" color="textSecondary" sx={{ mb: 3 }}>
                The backup system encountered an error and is temporarily unavailable.
                Please try refreshing the page or contact your administrator.
              </Typography>
              <Stack direction="row" spacing={2} justifyContent="center">
                <Button
                  onClick={() => window.location.reload()}
                  variant="contained"
                >
                  Refresh Page
                </Button>
                <Button
                  onClick={() => navigate('/admin')}
                  variant="outlined"
                >
                  Return to Admin
                </Button>
              </Stack>
            </Box>
          }
        >
          <Box sx={{ p: 3 }}>
            <BackupManager
              onBackupCreated={handleBackupCreated}
              onBackupRestored={handleBackupRestored}
              onBackupDeleted={handleBackupDeleted}
              onError={handleBackupError}
              autoRefresh={true}
              refreshInterval={30000} // 30 seconds
              showHealthStatus={true}
            />
          </Box>
        </BackupErrorBoundary>
      </Paper>
    </Container>
  );
};

export default BackupPage;
