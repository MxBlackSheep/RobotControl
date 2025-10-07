import React, { useState, useEffect } from 'react';
// Optimized Material-UI imports for better tree-shaking
import Box from '@mui/material/Box';
import Typography from '@mui/material/Typography';
import Grid from '@mui/material/Grid';
import Card from '@mui/material/Card';
import CardContent from '@mui/material/CardContent';
import Tabs from '@mui/material/Tabs';
import Tab from '@mui/material/Tab';
import Button from '@mui/material/Button';
import Chip from '@mui/material/Chip';
import List from '@mui/material/List';
import ListItem from '@mui/material/ListItem';
import ListItemText from '@mui/material/ListItemText';
import ListItemSecondaryAction from '@mui/material/ListItemSecondaryAction';
import IconButton from '@mui/material/IconButton';
import Divider from '@mui/material/Divider';
import LinearProgress from '@mui/material/LinearProgress';
import {
  People as UsersIcon,
  Storage as DatabaseIcon,
  MonitorHeart as SystemIcon,
  Refresh as RefreshIcon,
  ToggleOff,
  ToggleOn,
  CleaningServices as ClearCacheIcon
} from '@mui/icons-material';
import { useAuthContext } from '../context/AuthContext';
import { useNavigate } from 'react-router-dom';
import { api } from '../services/api';
import ErrorAlert, { AuthorizationError } from '../components/ErrorAlert';
import SystemStatus from '../components/SystemStatus';
import MonitoringDashboard from '../components/MonitoringDashboard';

interface TabPanelProps {
  children?: React.ReactNode;
  index: number;
  value: number;
}

function TabPanel(props: TabPanelProps) {
  const { children, value, index, ...other } = props;

  return (
    <div
      role="tabpanel"
      hidden={value !== index}
      id={`admin-tabpanel-${index}`}
      aria-labelledby={`admin-tab-${index}`}
      {...other}
    >
      {value === index && (
        <Box sx={{ pt: 3 }}>
          {children}
        </Box>
      )}
    </div>
  );
}

function a11yProps(index: number) {
  return {
    id: `admin-tab-${index}`,
    'aria-controls': `admin-tabpanel-${index}`,
  };
}

interface User {
  username: string;
  role: string;
  is_active: boolean;
  last_login?: string;
  created_at?: string;
}

interface SystemStatus {
  database: {
    is_connected: boolean;
    mode: string;
    database_name: string;
    server_name: string;
    last_check: string;
    error_message?: string;
  };
  system: {
    cpu_percent: number;
    memory_percent: number;
    memory_used_gb: number;
    memory_total_gb: number;
    disk_percent: number;
    disk_used_gb: number;
    disk_total_gb: number;
    uptime_hours: number;
  };
  timestamp: string;
}

interface DatabasePerformance {
  query_count: number;
  total_execution_time_ms: number;
  average_execution_time_ms: number;
  cache_entries: number;
  connection_pool_size: number;
  connection_attempts: any;
  last_error?: string;
}

export default function AdminPage() {
  const { user } = useAuthContext();
  const navigate = useNavigate();
  const [tabValue, setTabValue] = useState(0);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  
  // State for different sections
  const [users, setUsers] = useState<User[]>([]);
  const [systemStatus, setSystemStatus] = useState<SystemStatus | null>(null);
  const [dbPerformance, setDbPerformance] = useState<DatabasePerformance | null>(null);

  const handleTabChange = (event: React.SyntheticEvent, newValue: number) => {
    setTabValue(newValue);
  };

  // Load data functions
  const loadUsers = async () => {
    try {
      setLoading(true);
      const response = await api.get('/api/admin/users');
      setUsers(response.data);
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to load users');
    } finally {
      setLoading(false);
    }
  };

  const loadSystemStatus = async () => {
    try {
      setLoading(true);
      const response = await api.get('/api/admin/system/status');
      setSystemStatus(response.data);
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to load system status');
    } finally {
      setLoading(false);
    }
  };

  const loadDatabasePerformance = async () => {
    try {
      setLoading(true);
      const response = await api.get('/api/admin/database/performance');
      setDbPerformance(response.data);
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to load database performance');
    } finally {
      setLoading(false);
    }
  };

  // Action functions
  const toggleUserActive = async (username: string) => {
    try {
      await api.post(`/api/admin/users/${username}/toggle-active`);
      await loadUsers(); // Reload users
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to update user status');
    }
  };

  const clearDatabaseCache = async () => {
    try {
      setLoading(true);
      const response = await api.post('/api/admin/database/clear-cache');
      setError(null);
      // Show success message (could use a snackbar)
      await loadDatabasePerformance(); // Reload performance data
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to clear cache');
    } finally {
      setLoading(false);
    }
  };

  const performHealthCheck = async () => {
    try {
      setLoading(true);
      await api.post('/api/admin/database/health-check');
      await loadSystemStatus(); // Reload system status
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Health check failed');
    } finally {
      setLoading(false);
    }
  };

  // Load initial data
  useEffect(() => {
    if (tabValue === 0) loadSystemStatus();
    if (tabValue === 1) loadDatabasePerformance();
    if (tabValue === 2) loadUsers();
  }, [tabValue]);

  if (user?.role !== 'admin') {
    return (
      <Box sx={{ p: 3 }}>
        <AuthorizationError
          message="Admin privileges required to access this page."
          title="Access Denied"
        />
      </Box>
    );
  }

  return (
    <Box>
      <Typography variant="h4" sx={{ fontWeight: 700, mb: 1 }}>
        System Administration
      </Typography>
      <Typography variant="body1" color="text.secondary" sx={{ mb: 3 }}>
        System administration, monitoring, and configuration settings
      </Typography>

      {error && (
        <ErrorAlert
          message={error}
          severity="error"
          category="server"
          closable={true}
          retryable={true}
          onClose={() => setError(null)}
          onRetry={() => {
            if (tabValue === 0) loadSystemStatus();
            if (tabValue === 1) loadDatabasePerformance();
            if (tabValue === 2) loadUsers();
          }}
          sx={{ mb: 2 }}
        />
      )}

      <Box sx={{ borderBottom: 1, borderColor: 'divider' }}>
        <Tabs value={tabValue} onChange={handleTabChange} aria-label="admin tabs">
          <Tab 
            icon={<SystemIcon />} 
            label="System Status" 
            iconPosition="start"
            {...a11yProps(0)} 
          />
          <Tab 
            icon={<DatabaseIcon />} 
            label="Database" 
            iconPosition="start"
            {...a11yProps(1)} 
          />
          <Tab 
            icon={<UsersIcon />} 
            label="User Management" 
            iconPosition="start"
            {...a11yProps(2)} 
          />
        </Tabs>
      </Box>

      {/* System Status Tab - Real-time Monitoring */}
      <TabPanel value={tabValue} index={0}>
        <MonitoringDashboard />
      </TabPanel>

      {/* Database Tab */}
      <TabPanel value={tabValue} index={1}>
        <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 2 }}>
          <Typography variant="h6" sx={{ fontWeight: 600 }}>
            Database Administration
          </Typography>
          <Box>
            <Button
              startIcon={<ClearCacheIcon />}
              onClick={clearDatabaseCache}
              disabled={loading}
              sx={{ mr: 1 }}
            >
              Clear Cache
            </Button>
            <Button
              startIcon={<RefreshIcon />}
              onClick={() => { loadDatabasePerformance(); performHealthCheck(); }}
              disabled={loading}
            >
              Health Check
            </Button>
          </Box>
        </Box>

        {loading && <LinearProgress sx={{ mb: 2 }} />}

        {dbPerformance && (
          <Grid container spacing={3}>
            <Grid item xs={12} md={6}>
              <Card>
                <CardContent>
                  <Typography variant="h6" gutterBottom>
                    Query Performance
                  </Typography>
                  <Typography variant="body2">
                    <strong>Total Queries:</strong> {dbPerformance.query_count}
                  </Typography>
                  <Typography variant="body2">
                    <strong>Average Execution Time:</strong> {dbPerformance.average_execution_time_ms.toFixed(2)}ms
                  </Typography>
                  <Typography variant="body2">
                    <strong>Total Execution Time:</strong> {(dbPerformance.total_execution_time_ms / 1000).toFixed(2)}s
                  </Typography>
                </CardContent>
              </Card>
            </Grid>
            
            <Grid item xs={12} md={6}>
              <Card>
                <CardContent>
                  <Typography variant="h6" gutterBottom>
                    Connection Pool
                  </Typography>
                  <Typography variant="body2">
                    <strong>Cache Entries:</strong> {dbPerformance.cache_entries}
                  </Typography>
                  <Typography variant="body2">
                    <strong>Pool Size:</strong> {dbPerformance.connection_pool_size}
                  </Typography>
                  {dbPerformance.last_error && (
                    <ErrorAlert
                      message={`Last Error: ${dbPerformance.last_error}`}
                      severity="warning"
                      category="server"
                      compact={true}
                      sx={{ mt: 1 }}
                    />
                  )}
                </CardContent>
              </Card>
            </Grid>
          </Grid>
        )}
      </TabPanel>

      {/* User Management Tab */}
      <TabPanel value={tabValue} index={2}>
        <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 2 }}>
          <Typography variant="h6" sx={{ fontWeight: 600 }}>
            User Management
          </Typography>
          <Button
            startIcon={<RefreshIcon />}
            onClick={loadUsers}
            disabled={loading}
          >
            Refresh
          </Button>
        </Box>

        {loading && <LinearProgress sx={{ mb: 2 }} />}

        <Card>
          <CardContent>
            <List>
              {users.map((user, index) => (
                <React.Fragment key={user.username}>
                  <ListItem>
                    <ListItemText
                      primary={
                        <Box sx={{ display: 'flex', alignItems: 'center' }}>
                          <Typography variant="subtitle1" sx={{ mr: 1 }}>
                            {user.username}
                          </Typography>
                          <Chip 
                            label={user.role} 
                            size="small" 
                            color={user.role === 'admin' ? 'primary' : 'default'}
                            sx={{ mr: 1 }}
                          />
                          <Chip 
                            label={user.is_active ? 'Active' : 'Inactive'}
                            size="small"
                            color={user.is_active ? 'success' : 'default'}
                          />
                        </Box>
                      }
                      secondary={user.last_login ? `Last login: ${user.last_login}` : 'Never logged in'}
                    />
                    <ListItemSecondaryAction>
                      <IconButton
                        edge="end"
                        onClick={() => toggleUserActive(user.username)}
                        disabled={user.username === 'admin'} // Prevent disabling main admin
                      >
                        {user.is_active ? <ToggleOn color="primary" /> : <ToggleOff />}
                      </IconButton>
                    </ListItemSecondaryAction>
                  </ListItem>
                  {index < users.length - 1 && <Divider />}
                </React.Fragment>
              ))}
            </List>
          </CardContent>
        </Card>
      </TabPanel>

    </Box>
  );
}