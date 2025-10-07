/**
 * Camera Management Page - Refactored Version
 * 
 * Simplified main page component that delegates specific functionality
 * to focused, reusable sub-components for better maintainability
 */

import React, { useState, useEffect } from 'react';
import {
  Box,
  Container,
  Typography,
  Button,
  Tabs,
  Tab,
  Paper,
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  Grid,
  List,
  ListItem,
  ListItemText
} from '@mui/material';
import {
  ArrowBack as ArrowBackIcon,
  Videocam as VideocamIcon,
  VideoLibrary as VideoLibraryIcon,
  Stream as StreamIcon,
  Info as InfoIcon
} from '@mui/icons-material';
import { useNavigate } from 'react-router-dom';
import { PageLoading } from '../components/LoadingSpinner';
import { ServerError } from '../components/ErrorAlert';
import { buildApiUrl } from '@/utils/apiBase';

// Import refactored components
import {
  LiveCamerasTab,
  VideoArchiveTab,
  LiveStreamingTab,
  TabPanel,
  type CameraInfo,
  type ExperimentFolder,
  type StreamingStatus
} from '../components/camera';

// Interfaces from the original file
interface CameraSystemStatus {
  storage_info?: {
    total_space_gb: number;
    used_space_gb: number;
    available_space_gb: number;
  };
  paths?: {
    rolling_clips: string;
    experiments: string;
  };
}

const CameraPageRefactored: React.FC = () => {
  const navigate = useNavigate();
  
  // State management - consolidated from original
  const [cameras, setCameras] = useState<CameraInfo[]>([]);
  const [experimentFolders, setExperimentFolders] = useState<ExperimentFolder[]>([]);
  const [streamingStatus, setStreamingStatus] = useState<StreamingStatus | null>(null);
  const [systemStatus, setSystemStatus] = useState<CameraSystemStatus | null>(null);
  
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [currentTab, setCurrentTab] = useState(0);
  const [statusDialogOpen, setStatusDialogOpen] = useState(false);

  // API base URL
    // Load initial data
  useEffect(() => {
    loadInitialData();
    
    // Auto-refresh every 30 seconds
    const interval = setInterval(loadInitialData, 30000);
    return () => clearInterval(interval);
  }, []);

  // Combined data loading function
  const loadInitialData = async () => {
    setLoading(true);
    setError('');

    try {
      await Promise.all([
        loadCameraData(),
        loadRecordings(),
        loadStreamingStatus(),
        loadSystemStatus()
      ]);
    } catch (err: any) {
      console.error('Error loading camera data:', err);
      setError('Failed to load camera information');
    } finally {
      setLoading(false);
    }
  };

  // Load camera information
  const loadCameraData = async () => {
    try {
      const response = await fetch(buildApiUrl('/api/camera/list'));
      if (!response.ok) throw new Error('Failed to load cameras');
      
      const data = await response.json();
      setCameras(data.cameras || []);
    } catch (err) {
      console.error('Failed to load camera data:', err);
      // Don't set error here, let the parent handle it
    }
  };

  // Load video recordings
  const loadRecordings = async () => {
    try {
      const response = await fetch(buildApiUrl('/api/camera/recordings'));
      if (!response.ok) throw new Error('Failed to load recordings');
      
      const data = await response.json();
      setExperimentFolders(data.experiments || []);
    } catch (err) {
      console.error('Failed to load recordings:', err);
    }
  };

  // Load streaming status
  const loadStreamingStatus = async () => {
    try {
      const response = await fetch(buildApiUrl('/api/camera/streaming/status'));
      if (!response.ok) throw new Error('Failed to load streaming status');
      
      const data = await response.json();
      setStreamingStatus(data);
    } catch (err) {
      console.error('Failed to load streaming status:', err);
    }
  };

  // Load system status
  const loadSystemStatus = async () => {
    try {
      const response = await fetch(buildApiUrl('/api/camera/system-status'));
      if (!response.ok) throw new Error('Failed to load system status');
      
      const data = await response.json();
      setSystemStatus(data);
    } catch (err) {
      console.error('Failed to load system status:', err);
    }
  };

  // Video download handler
  const handleDownloadVideo = async (filename: string) => {
    try {
      const response = await fetch(`${buildApiUrl(`/api/camera/download/${filename}`)}`);
      if (!response.ok) throw new Error('Download failed');
      
      const blob = await response.blob();
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.style.display = 'none';
      a.href = url;
      a.download = filename;
      document.body.appendChild(a);
      a.click();
      window.URL.revokeObjectURL(url);
    } catch (err) {
      console.error('Download error:', err);
      setError(`Failed to download ${filename}`);
    }
  };

  // Streaming session handlers
  const handleStartStreamingSession = async (cameraId: string) => {
    const response = await fetch(buildApiUrl('/api/camera/streaming/start'), {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ camera_id: cameraId })
    });
    
    if (!response.ok) {
      throw new Error('Failed to start streaming session');
    }
  };

  const handleStopStreamingSession = async (sessionId: string) => {
    const response = await fetch(buildApiUrl(`/api/camera/streaming/stop/${sessionId}`), {
      method: 'POST'
    });
    
    if (!response.ok) {
      throw new Error('Failed to stop streaming session');
    }
  };

  // Main loading state
  if (loading && cameras.length === 0) {
    return <PageLoading message="Loading camera system..." />;
  }

  return (
    <Container 
      maxWidth="xl" 
      sx={{ 
        mt: { xs: 1, sm: 2 }, 
        mb: { xs: 1, sm: 2 },
        px: { xs: 1, sm: 2 }
      }}
    >
      {/* Header */}
      <Box sx={{ 
        display: 'flex', 
        alignItems: 'center', 
        mb: { xs: 1, sm: 2 },
        flexWrap: 'wrap',
        gap: 1
      }}>
        <Button
          startIcon={<ArrowBackIcon />}
          onClick={() => navigate('/')}
          size="small"
          sx={{ mr: { xs: 0, sm: 2 } }}
        >
          Back
        </Button>
        
        <Box sx={{ display: 'flex', alignItems: 'center', flexGrow: 1 }}>
          <VideocamIcon sx={{ 
            mr: 1, 
            color: 'primary.main', 
            fontSize: { xs: 24, sm: 28 }
          }} />
          <Typography variant="h5" sx={{ flexGrow: 1 }}>
            Camera Management
          </Typography>
        </Box>

        <Button
          startIcon={<InfoIcon />}
          onClick={() => setStatusDialogOpen(true)}
          size="small"
          variant="outlined"
        >
          System Info
        </Button>
      </Box>

      {/* Global Error Display */}
      {error && (
        <ServerError
          message={error}
          retryable={true}
          onRetry={loadInitialData}
          onClose={() => setError('')}
          sx={{ mb: 2 }}
        />
      )}

      {/* Tab Navigation */}
      <Paper sx={{ mb: 2 }}>
        <Tabs 
          value={currentTab} 
          onChange={(_, newValue) => setCurrentTab(newValue)}
          variant="scrollable"
          scrollButtons="auto"
          aria-label="camera management tabs"
        >
          <Tab 
            label={`Live Cameras (${cameras.length})`}
            icon={<VideocamIcon />}
            iconPosition="start"
          />
          <Tab 
            label={`Video Archive (${experimentFolders.length})`}
            icon={<VideoLibraryIcon />}
            iconPosition="start"
          />
          <Tab 
            label={`Live Streaming ${streamingStatus ? `(${streamingStatus.active_session_count}/${streamingStatus.max_sessions})` : ''}`}
            icon={<StreamIcon />}
            iconPosition="start"
          />
        </Tabs>
      </Paper>

      {/* Tab Content - Using Refactored Components */}
      <TabPanel value={currentTab} index={0}>
        <LiveCamerasTab
          cameras={cameras}
          loading={loading}
          error={error}
          onRefresh={loadCameraData}
          onShowStatus={() => setStatusDialogOpen(true)}
        />
      </TabPanel>

      <TabPanel value={currentTab} index={1}>
        <VideoArchiveTab
          experimentFolders={experimentFolders}
          loading={loading}
          error={error}
          onRefresh={loadRecordings}
          onDownloadVideo={handleDownloadVideo}
        />
      </TabPanel>

      <TabPanel value={currentTab} index={2}>
        <LiveStreamingTab
          streamingStatus={streamingStatus}
          loading={loading}
          error={error}
          onRefresh={loadStreamingStatus}
          onStartSession={handleStartStreamingSession}
          onStopSession={handleStopStreamingSession}
          availableCameras={cameras.map(c => ({ id: c.id, name: c.name }))}
        />
      </TabPanel>

      {/* System Status Dialog */}
      <Dialog 
        open={statusDialogOpen} 
        onClose={() => setStatusDialogOpen(false)}
        maxWidth="md"
        fullWidth
      >
        <DialogTitle>Camera System Status</DialogTitle>
        <DialogContent>
          {systemStatus ? (
            <Grid container spacing={2}>
              <Grid item xs={12} md={6}>
                <Typography variant="h6" gutterBottom>Storage Information</Typography>
                <List dense>
                  <ListItem>
                    <ListItemText
                      primary="Total Space"
                      secondary={`${systemStatus.storage_info?.total_space_gb.toFixed(1)} GB`}
                    />
                  </ListItem>
                  <ListItem>
                    <ListItemText
                      primary="Used Space"
                      secondary={`${systemStatus.storage_info?.used_space_gb.toFixed(1)} GB`}
                    />
                  </ListItem>
                  <ListItem>
                    <ListItemText
                      primary="Available Space"
                      secondary={`${systemStatus.storage_info?.available_space_gb.toFixed(1)} GB`}
                    />
                  </ListItem>
                </List>
              </Grid>
              <Grid item xs={12} md={6}>
                <Typography variant="h6" gutterBottom>Paths</Typography>
                <List dense>
                  <ListItem>
                    <ListItemText
                      primary="Rolling Clips"
                      secondary={systemStatus.paths?.rolling_clips}
                    />
                  </ListItem>
                  <ListItem>
                    <ListItemText
                      primary="Experiments"
                      secondary={systemStatus.paths?.experiments}
                    />
                  </ListItem>
                </List>
              </Grid>
            </Grid>
          ) : (
            <Typography>No status information available</Typography>
          )}
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setStatusDialogOpen(false)}>Close</Button>
        </DialogActions>
      </Dialog>
    </Container>
  );
};

export default CameraPageRefactored;

