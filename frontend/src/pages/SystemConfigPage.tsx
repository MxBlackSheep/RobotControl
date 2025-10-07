import React from 'react';
import {
  Box,
  Container,
  Typography,
  Button,
  Paper
} from '@mui/material';
import { useNavigate } from 'react-router-dom';
import ArrowBackIcon from '@mui/icons-material/ArrowBack';
import SettingsIcon from '@mui/icons-material/Settings';
import { useAuthContext } from '../context/AuthContext';
import SystemConfigSettings from '../components/SystemConfigSettings';

export default function SystemConfigPage() {
  const navigate = useNavigate();
  const { user } = useAuthContext();

  // Require admin access
  if (user?.role !== 'admin') {
    return (
      <Container maxWidth="md" sx={{ py: 4 }}>
        <Paper elevation={2} sx={{ p: 4, textAlign: 'center' }}>
          <Typography variant="h5" color="error" gutterBottom>
            Access Denied
          </Typography>
          <Typography variant="body1" sx={{ mb: 3 }}>
            Administrator privileges are required to access system configuration settings.
          </Typography>
          <Button
            variant="contained"
            startIcon={<ArrowBackIcon />}
            onClick={() => navigate('/admin')}
          >
            Return to Admin Dashboard
          </Button>
        </Paper>
      </Container>
    );
  }

  return (
    <Container maxWidth="lg" sx={{ py: 3 }}>
      {/* Header */}
      <Box sx={{ mb: 4 }}>
        <Button
          startIcon={<ArrowBackIcon />}
          onClick={() => navigate('/admin')}
          sx={{ mb: 2 }}
          variant="outlined"
        >
          Back to Admin
        </Button>
        
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 2, mb: 2 }}>
          <SettingsIcon color="primary" sx={{ fontSize: 32 }} />
          <Typography variant="h4" sx={{ fontWeight: 700 }}>
            System Configuration Manager
          </Typography>
        </Box>
        
        <Typography variant="body1" color="text.secondary">
          Manage centralized database connections, backup paths, and system parameters.
          Changes made here affect the entire PyRobot system and are automatically persisted.
        </Typography>
      </Box>

      {/* Configuration Interface */}
      <Paper elevation={2} sx={{ p: 4 }}>
        <SystemConfigSettings />
      </Paper>
    </Container>
  );
}