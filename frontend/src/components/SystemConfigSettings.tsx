import React, { useState, useEffect } from 'react';
import {
  Box,
  Typography,
  Card,
  CardContent,
  TextField,
  Button,
  Alert,
  Grid,
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  Chip,
  CircularProgress,
  LinearProgress,
  Divider,
  List,
  ListItem,
  ListItemText,
  ListItemIcon
} from '@mui/material';
import {
  Storage as DatabaseIcon,
  Settings as SettingsIcon,
  Save as SaveIcon,
  PlayArrow as TestIcon,
  CheckCircle as SuccessIcon,
  Error as ErrorIcon,
  Warning as WarningIcon,
  Info as InfoIcon,
  Refresh as RefreshIcon
} from '@mui/icons-material';
import { api } from '../services/api';

interface DatabaseConfig {
  vm_sql_server: string;
  vm_sql_user: string;
  vm_sql_password: string;
  local_backup_path: string;
  sql_backup_path: string;
}

interface SystemStatus {
  current_connection_mode: string;
  current_server: string;
  current_database: string;
  connection_status: string;
  backup_paths: {
    local_path: string;
    sql_path: string;
  };
}

interface ConnectionTestResult {
  success: boolean;
  message: string;
  server?: string;
  sql_server_version?: string;
}

export default function SystemConfigSettings() {
  const [config, setConfig] = useState<DatabaseConfig>({
    vm_sql_server: '',
    vm_sql_user: '',
    vm_sql_password: '',
    local_backup_path: '',
    sql_backup_path: ''
  });
  
  const [systemStatus, setSystemStatus] = useState<SystemStatus | null>(null);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [testing, setTesting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [testResult, setTestResult] = useState<ConnectionTestResult | null>(null);
  const [showTestDialog, setShowTestDialog] = useState(false);

  // Load current configuration
  const loadConfig = async () => {
    try {
      setLoading(true);
      setError(null);
      
      const [configResponse, statusResponse] = await Promise.all([
        api.get('/api/admin/system/config/database'),
        api.get('/api/admin/system/config/status')
      ]);
      
      setConfig(configResponse.data);
      setSystemStatus(statusResponse.data);
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to load configuration');
    } finally {
      setLoading(false);
    }
  };

  // Save configuration
  const saveConfig = async () => {
    try {
      setSaving(true);
      setError(null);
      setSuccess(null);
      
      await api.post('/api/admin/system/config/database', config);
      
      setSuccess('Configuration updated successfully! The changes will take effect on the next database connection.');
      
      // Reload status after save
      setTimeout(() => {
        loadConfig();
      }, 1000);
      
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to save configuration');
    } finally {
      setSaving(false);
    }
  };

  // Test database connection
  const testConnection = async () => {
    try {
      setTesting(true);
      setTestResult(null);
      
      const response = await api.post('/api/admin/system/test-connection');
      setTestResult(response.data);
      setShowTestDialog(true);
      
    } catch (err: any) {
      setTestResult({
        success: false,
        message: err.response?.data?.message || 'Connection test failed',
        server: config.vm_sql_server
      });
      setShowTestDialog(true);
    } finally {
      setTesting(false);
    }
  };

  // Handle input changes
  const handleInputChange = (field: keyof DatabaseConfig) => (event: React.ChangeEvent<HTMLInputElement>) => {
    setConfig(prev => ({
      ...prev,
      [field]: event.target.value
    }));
    // Clear messages when user starts editing
    if (error) setError(null);
    if (success) setSuccess(null);
  };

  // Load initial data
  useEffect(() => {
    loadConfig();
  }, []);

  return (
    <Box>
      <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 3 }}>
        <Box>
          <Typography variant="h6" sx={{ fontWeight: 600, display: 'flex', alignItems: 'center', gap: 1 }}>
            <SettingsIcon color="primary" />
            System Configuration
          </Typography>
          <Typography variant="body2" color="text.secondary">
            Manage centralized database connection settings and system parameters
          </Typography>
        </Box>
        <Button
          startIcon={<RefreshIcon />}
          onClick={loadConfig}
          disabled={loading}
          variant="outlined"
          size="small"
        >
          Refresh
        </Button>
      </Box>

      {error && (
        <Alert severity="error" sx={{ mb: 2 }} onClose={() => setError(null)}>
          {error}
        </Alert>
      )}

      {success && (
        <Alert severity="success" sx={{ mb: 2 }} onClose={() => setSuccess(null)}>
          {success}
        </Alert>
      )}

      {loading && <LinearProgress sx={{ mb: 2 }} />}

      <Grid container spacing={3}>
        {/* Current System Status */}
        <Grid item xs={12} lg={6}>
          <Card sx={{ mb: 3 }}>
            <CardContent>
              <Typography variant="h6" gutterBottom sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                <InfoIcon color="info" />
                Current System Status
              </Typography>
              
              {systemStatus ? (
                <List dense>
                  <ListItem>
                    <ListItemIcon>
                      <Chip
                        icon={systemStatus.connection_status === 'Connected' ? <SuccessIcon /> : <ErrorIcon />}
                        label={systemStatus.connection_status}
                        color={systemStatus.connection_status === 'Connected' ? 'success' : 'error'}
                        size="small"
                      />
                    </ListItemIcon>
                    <ListItemText
                      primary="Connection Status"
                      secondary={`${systemStatus.current_server} (${systemStatus.current_connection_mode})`}
                    />
                  </ListItem>
                  
                  <ListItem>
                    <ListItemIcon>
                      <DatabaseIcon />
                    </ListItemIcon>
                    <ListItemText
                      primary="Database"
                      secondary={systemStatus.current_database}
                    />
                  </ListItem>
                  
                  <ListItem>
                    <ListItemText
                      primary="Backup Paths"
                      secondary={
                        <Box component="div">
                          <Typography variant="caption" display="block">
                            Local: {systemStatus.backup_paths.local_path}
                          </Typography>
                          <Typography variant="caption" display="block">
                            SQL: {systemStatus.backup_paths.sql_path}
                          </Typography>
                        </Box>
                      }
                    />
                  </ListItem>
                </List>
              ) : (
                <Typography variant="body2" color="text.secondary">
                  Loading system status...
                </Typography>
              )}
            </CardContent>
          </Card>
        </Grid>

        {/* Database Configuration */}
        <Grid item xs={12} lg={6}>
          <Card>
            <CardContent>
              <Typography variant="h6" gutterBottom sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                <DatabaseIcon color="primary" />
                Database Configuration
              </Typography>
              
              <Box sx={{ display: 'flex', gap: 2, mb: 2 }}>
                <Button
                  startIcon={<TestIcon />}
                  onClick={testConnection}
                  disabled={testing || saving || loading}
                  variant="outlined"
                  size="small"
                >
                  {testing ? <CircularProgress size={16} /> : 'Test Connection'}
                </Button>
                
                <Button
                  startIcon={<SaveIcon />}
                  onClick={saveConfig}
                  disabled={saving || loading}
                  variant="contained"
                  size="small"
                >
                  {saving ? <CircularProgress size={16} /> : 'Save Configuration'}
                </Button>
              </Box>

              <Grid container spacing={2}>
                <Grid item xs={12}>
                  <TextField
                    fullWidth
                    label="SQL Server Address"
                    value={config.vm_sql_server}
                    onChange={handleInputChange('vm_sql_server')}
                    placeholder="192.168.3.21,50131"
                    helperText="Format: IP_ADDRESS,PORT"
                    disabled={loading}
                  />
                </Grid>
                
                <Grid item xs={6}>
                  <TextField
                    fullWidth
                    label="Username"
                    value={config.vm_sql_user}
                    onChange={handleInputChange('vm_sql_user')}
                    placeholder="Hamilton"
                    disabled={loading}
                  />
                </Grid>
                
                <Grid item xs={6}>
                  <TextField
                    fullWidth
                    label="Password"
                    type="password"
                    value={config.vm_sql_password}
                    onChange={handleInputChange('vm_sql_password')}
                    placeholder="••••••••"
                    disabled={loading}
                  />
                </Grid>
                
                <Grid item xs={12}>
                  <TextField
                    fullWidth
                    label="Local Backup Path"
                    value={config.local_backup_path}
                    onChange={handleInputChange('local_backup_path')}
                    placeholder="\\192.168.3.20\RobotControl\data\backups"
                    helperText="Network path for host machine backup operations"
                    disabled={loading}
                  />
                </Grid>
                
                <Grid item xs={12}>
                  <TextField
                    fullWidth
                    label="SQL Backup Path"
                    value={config.sql_backup_path}
                    onChange={handleInputChange('sql_backup_path')}
                    placeholder="Z:\backups"
                    helperText="VM path for SQL Server backup operations"
                    disabled={loading}
                  />
                </Grid>
              </Grid>
            </CardContent>
          </Card>
        </Grid>
      </Grid>

      {/* Configuration Notes */}
      <Card sx={{ mt: 3 }}>
        <CardContent>
          <Typography variant="h6" gutterBottom sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
            <WarningIcon color="warning" />
            Configuration Notes
          </Typography>
          
          <Typography variant="body2" paragraph>
            <strong>Centralized Configuration:</strong> Changes made here will affect all backend services that connect to the database.
            This includes backup operations, monitoring data, and table access.
          </Typography>
          
          <Typography variant="body2" paragraph>
            <strong>Dual-Path Architecture:</strong> The system uses two different paths:
          </Typography>
          
          <Box sx={{ ml: 2, mb: 2 }}>
            <Typography variant="body2">
              • <strong>Local Backup Path:</strong> Used by the host machine for file operations (UNC path)
            </Typography>
            <Typography variant="body2">
              • <strong>SQL Backup Path:</strong> Used by SQL Server on the VM for backup operations (mapped drive)
            </Typography>
          </Box>
          
          <Typography variant="body2" paragraph>
            <strong>Environment Variables:</strong> Configuration can also be managed via environment variables or the .env file in the backend directory.
            Web changes will override environment settings for the current session.
          </Typography>
        </CardContent>
      </Card>

      {/* Connection Test Dialog */}
      <Dialog open={showTestDialog} onClose={() => setShowTestDialog(false)} maxWidth="sm" fullWidth>
        <DialogTitle sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
          {testResult?.success ? (
            <><SuccessIcon color="success" /> Connection Test Successful</>
          ) : (
            <><ErrorIcon color="error" /> Connection Test Failed</>
          )}
        </DialogTitle>
        
        <DialogContent>
          {testResult && (
            <Box>
              <Alert severity={testResult.success ? 'success' : 'error'} sx={{ mb: 2 }}>
                {testResult.message}
              </Alert>
              
              <Typography variant="body2" gutterBottom>
                <strong>Server:</strong> {testResult.server || 'Unknown'}
              </Typography>
              
              {testResult.sql_server_version && (
                <Typography variant="body2" gutterBottom>
                  <strong>SQL Server Version:</strong> {testResult.sql_server_version}
                </Typography>
              )}
              
              {testResult.success && (
                <Typography variant="body2" color="success.main" sx={{ mt: 2 }}>
                  The database connection is working properly. You can save the configuration to apply these settings.
                </Typography>
              )}
            </Box>
          )}
        </DialogContent>
        
        <DialogActions>
          <Button onClick={() => setShowTestDialog(false)}>
            Close
          </Button>
          {testResult?.success && (
            <Button variant="contained" onClick={() => { setShowTestDialog(false); saveConfig(); }}>
              Save Configuration
            </Button>
          )}
        </DialogActions>
      </Dialog>
    </Box>
  );
}