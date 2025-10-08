/**
 * MonitoringDashboard Component
 * 
 * Comprehensive real-time monitoring dashboard that displays:
 * - System health metrics (CPU, memory, disk)
 * - WebSocket connection status
 * - Live updates via WebSocket
 * 
 * Used in the Admin page for system monitoring.
 */

import React, { useEffect, useState, useMemo, memo, useCallback } from 'react';

// Optimized Material-UI imports for better tree-shaking
import Box from '@mui/material/Box';
import Card from '@mui/material/Card';
import CardContent from '@mui/material/CardContent';
import Typography from '@mui/material/Typography';
import Grid from '@mui/material/Grid';
import LinearProgress from '@mui/material/LinearProgress';
import Chip from '@mui/material/Chip';
import ErrorAlert from './ErrorAlert';
import IconButton from '@mui/material/IconButton';
import Tooltip from '@mui/material/Tooltip';
import Button from '@mui/material/Button';
import Divider from '@mui/material/Divider';
import LoadingSpinner from './LoadingSpinner';
import {
  Refresh as RefreshIcon,
  SignalWifi4Bar as ConnectedIcon,
  SignalWifiOff as DisconnectedIcon,
  Computer as SystemIcon,
  Memory as MemoryIcon,
  Storage as DiskIcon,
  Speed as CpuIcon
} from '@mui/icons-material';
import { useMonitoring } from '../hooks/useMonitoring';
import { buildApiUrl } from '@/utils/apiBase';

interface ProgressCardProps {
  title: string;
  value: number;
  unit: string;
  color: 'primary' | 'secondary' | 'success' | 'warning' | 'error';
  icon: React.ReactNode;
  detail?: string;
}

const ProgressCard: React.FC<ProgressCardProps> = memo(({
  title,
  value,
  unit,
  color,
  icon,
  detail
}) => {
  return (
    <Card>
      <CardContent>
        <Box display="flex" alignItems="center" mb={2}>
          <Box sx={{ color: `${color}.main`, mr: 1 }}>
            {icon}
          </Box>
          <Typography variant="h6" component="div">
            {title}
          </Typography>
        </Box>
        <Box display="flex" alignItems="center" mb={1}>
          <Typography variant="h4" component="div" sx={{ mr: 1 }}>
            {value.toFixed(1)}
          </Typography>
          <Typography variant="h6" color="text.secondary">
            {unit}
          </Typography>
        </Box>
        <LinearProgress
          variant="determinate"
          value={value}
          color={color}
          sx={{ mb: 1 }}
        />
        {detail && (
          <Typography variant="body2" color="text.secondary">
            {detail}
          </Typography>
        )}
      </CardContent>
    </Card>
  );
});

const MonitoringDashboard: React.FC = memo(() => {
  const {
    monitoringData,
    systemHealth,
    isConnected,
    isLoading,
    error,
    connectionRetries,
    connect,
    disconnect,
    refreshData,
    resetError
  } = useMonitoring();

  const [lastUpdate, setLastUpdate] = useState<string | null>(null);

  useEffect(() => {
    if (systemHealth?.timestamp) {
      setLastUpdate(new Date(systemHealth.timestamp).toLocaleTimeString());
      return;
    }

    if (monitoringData?.last_updated) {
      setLastUpdate(new Date(monitoringData.last_updated).toLocaleTimeString());
    } else {
      setLastUpdate(null);
    }
  }, [systemHealth, monitoringData]);

  const handleRefresh = useCallback(async () => {
    resetError();
    await refreshData();
  }, [resetError, refreshData]);

  const handleReconnect = useCallback(() => {
    resetError();
    connect();
  }, [resetError, connect]);

  const healthStatus = useMemo(() => {
    if (!systemHealth) return { status: 'Unknown', color: 'default' as const };
    
    const { cpu_percent, memory_percent, disk_percent } = systemHealth;
    const maxUsage = Math.max(cpu_percent, memory_percent, disk_percent);
    
    if (maxUsage > 90) return { status: 'Critical', color: 'error' as const };
    if (maxUsage > 80) return { status: 'Warning', color: 'warning' as const };
    if (maxUsage > 60) return { status: 'Good', color: 'success' as const };
    return { status: 'Excellent', color: 'primary' as const };
  }, [systemHealth]);

  // Memoized metric cards to prevent unnecessary re-renders
  const metricCards = useMemo(() => {
    if (!systemHealth) return null;

    return [
      {
        title: "CPU Usage",
        value: systemHealth.cpu_percent,
        unit: "%",
        color: systemHealth.cpu_percent > 80 ? 'error' : systemHealth.cpu_percent > 60 ? 'warning' : 'success',
        icon: <CpuIcon />,
        detail: "Current CPU utilization"
      },
      {
        title: "Memory Usage", 
        value: systemHealth.memory_percent,
        unit: "%",
        color: systemHealth.memory_percent > 80 ? 'error' : systemHealth.memory_percent > 60 ? 'warning' : 'success',
        icon: <MemoryIcon />,
        detail: `${systemHealth.memory_used_gb}GB / ${systemHealth.memory_total_gb}GB`
      },
      {
        title: "Disk Usage",
        value: systemHealth.disk_percent, 
        unit: "%",
        color: systemHealth.disk_percent > 80 ? 'error' : systemHealth.disk_percent > 60 ? 'warning' : 'success',
        icon: <DiskIcon />,
        detail: `${systemHealth.disk_used_gb}GB / ${systemHealth.disk_total_gb}GB`
      }
    ];
  }, [systemHealth]);

  return (
    <Box>
      {/* Header */}
      <Box
        sx={{
          mb: { xs: 2, md: 3 },
          display: 'flex',
          flexDirection: { xs: 'column', md: 'row' },
          alignItems: { xs: 'flex-start', md: 'center' },
          justifyContent: 'space-between',
          gap: { xs: 2, md: 0 }
        }}
      >
        <Typography variant="h5">
          Real-time System Monitoring
        </Typography>
        <Box
          sx={{
            display: 'flex',
            flexDirection: { xs: 'column', sm: 'row' },
            alignItems: { xs: 'flex-start', sm: 'center' },
            gap: { xs: 1, sm: 2 }
          }}
        >
          <Chip
            icon={isConnected ? <ConnectedIcon /> : <DisconnectedIcon />}
            label={isConnected ? 'Active' : 'Inactive'}
            color={isConnected ? 'success' : 'error'}
            variant="outlined"
          />
          <Typography variant="body2" color="text.secondary">
            Last update: {lastUpdate ?? '--'}
          </Typography>
          <Tooltip title="Refresh data">
            <IconButton onClick={handleRefresh} disabled={isLoading}>
              <RefreshIcon />
            </IconButton>
          </Tooltip>
        </Box>
      </Box>

      {/* Error Alert */}
      {error && (
        <ErrorAlert
          message={connectionRetries > 0 ? 
            `${error}\nReconnection attempts: ${connectionRetries}/5` : 
            error
          }
          severity="error"
          category="network"
          retryable={true}
          onRetry={handleReconnect}
          sx={{ mb: 3 }}
        />
      )}

      {/* Overall Health Status */}
      <Card sx={{ mb: 3 }}>
        <CardContent>
          <Box display="flex" alignItems="center" justifyContent="space-between">
            <Box display="flex" alignItems="center">
              <SystemIcon sx={{ mr: 2, color: healthStatus.color + '.main' }} />
              <div>
                <Typography variant="h6">
                  System Health: <Chip label={healthStatus.status} color={healthStatus.color} size="small" />
                </Typography>
                <Typography variant="body2" color="text.secondary">
                  Overall system performance status
                </Typography>
              </div>
            </Box>
          <Box
            sx={{
              display: 'flex',
              flexDirection: { xs: 'column', sm: 'row' },
              alignItems: { xs: 'flex-start', sm: 'center' },
              gap: { xs: 1, sm: 2 }
            }}
          >
            <Typography variant="body2" color="text.secondary">
              Polling status: {isConnected ? 'Active' : 'Stopped'}
            </Typography>
            {isLoading && <LoadingSpinner variant="inline" size="small" />}
          </Box>
          </Box>
        </CardContent>
      </Card>

      {/* System Metrics */}
      {metricCards ? (
        <Grid container spacing={3}>
          {metricCards.map((card, index) => (
            <Grid item xs={12} md={4} key={card.title}>
              <ProgressCard
                title={card.title}
                value={card.value}
                unit={card.unit}
                color={card.color as any}
                icon={card.icon}
                detail={card.detail}
              />
            </Grid>
          ))}
        </Grid>
      ) : (
        <Card>
          <CardContent>
            <Box display="flex" alignItems="center" justifyContent="center" p={4}>
              {isLoading ? (
                <LoadingSpinner 
                  variant="spinner" 
                  message="Loading system metrics..." 
                  size="medium"
                />
              ) : (
                <Box textAlign="center">
                  <Typography variant="h6" gutterBottom>
                    No monitoring data available
                  </Typography>
                  <Typography variant="body2" color="text.secondary" gutterBottom>
                    System metrics will appear here when connection is established
                  </Typography>
                  <Button variant="contained" onClick={handleReconnect} sx={{ mt: 2 }}>
                    Start Monitoring
                  </Button>
                </Box>
              )}
            </Box>
          </CardContent>
        </Card>
      )}

      {/* Connection Details */}
      {isConnected && systemHealth && (
        <Card sx={{ mt: 3 }}>
          <CardContent>
            <Typography variant="h6" gutterBottom>
              Connection Details
            </Typography>
            <Divider sx={{ mb: 2 }} />
            <Grid container spacing={2}>
              <Grid item xs={6} sm={3}>
                <Typography variant="body2" color="text.secondary">
                  API Endpoint
                </Typography>
                <Typography variant="body2">
                  ${buildApiUrl('/api/monitoring/*')}
                </Typography>
              </Grid>
              <Grid item xs={6} sm={3}>
                <Typography variant="body2" color="text.secondary">
                  Connection Status
                </Typography>
                <Typography variant="body2" color="success.main">
                  Active
                </Typography>
              </Grid>
              <Grid item xs={6} sm={3}>
                <Typography variant="body2" color="text.secondary">
                  Update Frequency
                </Typography>
                <Typography variant="body2">
                  60 seconds
                </Typography>
              </Grid>
              <Grid item xs={6} sm={3}>
                <Typography variant="body2" color="text.secondary">
                  Data Source
                </Typography>
                <Typography variant="body2">
                  Live System Metrics
                </Typography>
              </Grid>
            </Grid>
          </CardContent>
        </Card>
      )}
    </Box>
  );
});

// Add display names for debugging
MonitoringDashboard.displayName = 'MonitoringDashboard';
ProgressCard.displayName = 'ProgressCard';

export default MonitoringDashboard;
