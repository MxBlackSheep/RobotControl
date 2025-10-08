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
    <Container 
      maxWidth="xl" 
      sx={{ 
        py: { xs: 2, md: 3 },
        px: { xs: 1, sm: 2 }
      }}
    >
      {/* Page Header */}
      <Box sx={{ 
        mb: { xs: 3, md: 4 },
        px: { xs: 1, sm: 0 }
      }}>
        <Box sx={{ 
          display: 'flex', 
          alignItems: 'center', 
          mb: 1,
          flexWrap: 'wrap',
          gap: 1
        }}>
          <Typography 
            variant="h4" 
            sx={{ 
              fontWeight: 700, 
              mr: { xs: 0, sm: 2 },
              flexGrow: 1
            }}
          >
            System Status
          </Typography>
          <Chip
            label={`${user?.role || 'Unknown'} Access`}
            color="primary"
            variant="outlined"
            size="small"
          />
        </Box>
        <Typography 
          variant="body1" 
          color="text.secondary"
          sx={{ fontSize: { xs: '0.875rem', sm: '1rem' } }}
        >
          Real-time system health, performance metrics, and telemetry dashboard
        </Typography>
      </Box>

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
        />
      </Box>
    </Container>
  );
});

// Add display name for debugging
MonitoringPage.displayName = 'SystemStatusPage';

export default MonitoringPage;
