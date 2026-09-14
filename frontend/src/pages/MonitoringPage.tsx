import { PageContent, PageHeader } from '../components/PageLayout';
/**
 * MonitoringPage - Dedicated real-time system status page
 * 
 * Provides full-screen telemetry without admin overhead
 * Available to both admin and user roles for system observation
 */

import React, { memo } from 'react';

// Optimized Material-UI imports for better tree-shaking
import Box from '@mui/material/Box';
import Container from '@mui/material/Container';
import Typography from '@mui/material/Typography';
import Chip from '@mui/material/Chip';

import MonitoringDashboard from '../components/MonitoringDashboard';
import SystemStatus from '../components/SystemStatus';
import { useAuth } from '../context/AuthContext';

const MonitoringPage: React.FC = memo(() => {
  const { user } = useAuth();

  return (
    <PageContent>
      <PageHeader title="System Status" actions={<Chip label={`${user?.role || 'Unknown'} Access`} color="primary" variant="outlined" size="small" />} />

      {/* Main Monitoring Content */}
      <Box sx={{ mb: { xs: 3, md: 4 } }}>
        <MonitoringDashboard />
      </Box>

      {/* System Status Overview */}
      <Box>
        <SystemStatus 
          compact={false}
          autoRefresh={true}
          refreshInterval={30}
          showHeader={false}
          showExperiments={false}
        />
      </Box>
    </PageContent>
  );
});

// Add display name for debugging
MonitoringPage.displayName = 'SystemStatusPage';

export default MonitoringPage;
