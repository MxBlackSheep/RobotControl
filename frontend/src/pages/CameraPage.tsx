/**
 * Camera Management Page for PyRobot Simplified Architecture
 * 
 * Features:
 * - Multiple camera management and viewing
 * - Live camera streaming interface
 * - Video archive browsing and playback
 * - System status monitoring
 * - Recording management controls
 * - Real-time camera status updates
 */

import React, { useState, useEffect } from 'react';
import {
  Box,
  Container,
  Typography,
  Grid,
  Card,
  CardContent,
  Button,
  Tabs,
  Tab,
  List,
  ListItem,
  ListItemText,
  IconButton,
  Chip,
  Paper,
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  Stack,
  Divider
} from '@mui/material';
import {
  ArrowBack as ArrowBackIcon,
  Videocam as VideocamIcon,
  VideoLibrary as VideoLibraryIcon,
  Refresh as RefreshIcon,
  Info as InfoIcon,
  Storage as StorageIcon,
  Stream as StreamIcon,
  PlayArrow as PlayArrowIcon,
  Stop as StopIcon,
  Settings as SettingsIcon,
  Fullscreen as FullscreenIcon,
  Close as CloseIcon
} from '@mui/icons-material';
import { useNavigate } from 'react-router-dom';
import LoadingSpinner, { PageLoading, ButtonLoading } from '../components/LoadingSpinner';
import ErrorAlert, { ServerError } from '../components/ErrorAlert';
import { buildApiUrl, buildWsUrl } from '@/utils/apiBase';
import VideoArchiveTab, {
  type ExperimentFolder
} from '../components/camera/VideoArchiveTab';

interface CameraInfo {
  id: number;
  name: string;
  width: number;
  height: number;
  fps: number;
  status: string;
  is_recording: boolean;
  has_live_stream: boolean;
}


interface StreamingSession {
  session_id: string;
  user_id: string;
  user_name: string;
  created_at: string;
  is_active: boolean;
  quality_level: string;
  bandwidth_usage_mbps: number;
  actual_fps: number;
  websocket_state: string;
}

interface StreamingStatus {
  enabled: boolean;
  active_session_count: number;
  max_sessions: number;
  total_bandwidth_mbps: number;
  available_bandwidth_mbps: number;
  resource_usage_percent: number;
  recording_impact: string;
  priority_mode: string;
}

interface CameraSystemStatus {
  system_health: any;
  camera_status: any;
  storage_info: any;
  configuration: any;
  paths: any;
}

interface TabPanelProps {
  children?: React.ReactNode;
  index: number;
  value: number;
}

const TabPanel = ({ children, value, index, ...other }: TabPanelProps) => (
  <div role="tabpanel" hidden={value !== index} {...other}>
    {value === index && <Box sx={{ p: 3 }}>{children}</Box>}
  </div>
);

const CameraPage: React.FC = () => {
  const navigate = useNavigate();
  
  // State management
  const [cameras, setCameras] = useState<CameraInfo[]>([]);
  const [experimentFolders, setExperimentFolders] = useState<ExperimentFolder[]>([]);
  const [systemStatus, setSystemStatus] = useState<CameraSystemStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [currentTab, setCurrentTab] = useState(0);
  const [statusDialogOpen, setStatusDialogOpen] = useState(false);
  
  // Streaming state
  const [streamingStatus, setStreamingStatus] = useState<StreamingStatus | null>(null);
  const [mySession, setMySession] = useState<StreamingSession | null>(null);
  const [streamingLoading, setStreamingLoading] = useState(false);
  const [currentFrame, setCurrentFrame] = useState<string | null>(null);
  const [fullscreenDialogOpen, setFullscreenDialogOpen] = useState(false);

  // Video streaming state
  const [wsRef, setWsRef] = useState<WebSocket | null>(null);

  // API base URL
    const fetchWithTimeout = async (url: string, options: RequestInit = {}, timeoutMs = 10000): Promise<Response> => {
    const controller = new AbortController();
    const timeoutId = window.setTimeout(() => controller.abort(), timeoutMs);
    try {
      return await fetch(url, { ...options, signal: controller.signal });
    } finally {
      window.clearTimeout(timeoutId);
    }
  };

  // Load camera data
  useEffect(() => {
    loadCameraData();
    const interval = setInterval(loadCameraData, 30000); // Refresh every 30 seconds
    return () => clearInterval(interval);
  }, []);

  // Cleanup WebSocket on unmount
  useEffect(() => {
    return () => {
      if (wsRef) {
        wsRef.close();
      }
    };
  }, [wsRef]);

  // Load recordings when switching to archive tab
  useEffect(() => {
    if (currentTab === 1) {
      loadRecordings();
    }
  }, [currentTab]);

  // Load streaming status when switching to streaming tab
  useEffect(() => {
    if (currentTab === 2) {
      loadStreamingStatus();
    }
  }, [currentTab]);

  useEffect(() => {
    if (
      fullscreenDialogOpen &&
      (!mySession || mySession.websocket_state !== 'connected')
    ) {
      setFullscreenDialogOpen(false);
    }
  }, [fullscreenDialogOpen, mySession]);

  const loadCameraData = async () => {
    try {
      const token = localStorage.getItem('access_token');
      const headers: HeadersInit = token
        ? { Authorization: `Bearer ${token}` }
        : {};

      const [camerasResult, statusResult] = await Promise.allSettled([
        fetchWithTimeout(buildApiUrl('/api/camera/cameras'), { headers }, 10000),
        fetchWithTimeout(buildApiUrl('/api/camera/status'), { headers }, 10000)
      ]);

      const errors: string[] = [];

      if (camerasResult.status === 'fulfilled') {
        const response = camerasResult.value;
        if (response.ok) {
          try {
            const camerasData = await response.json();
            setCameras(camerasData?.data?.cameras || []);
          } catch (parseError) {
            console.error('Failed to parse camera list response:', parseError);
            errors.push('Camera list response was malformed');
          }
        } else {
          console.error('Camera list request failed:', response.status, response.statusText);
          errors.push(`Camera list request failed (${response.status})`);
        }
      } else {
        const reason = camerasResult.reason as { name?: string; message?: string };
        if (reason?.name === 'AbortError') {
          errors.push('Camera list request timed out');
        } else {
          console.error('Camera list request rejected:', reason);
          errors.push('Failed to load camera list');
        }
      }

      if (statusResult.status === 'fulfilled') {
        const response = statusResult.value;
        if (response.ok) {
          try {
            const statusData = await response.json();
            setSystemStatus(statusData?.data ?? null);
          } catch (parseError) {
            console.error('Failed to parse camera status response:', parseError);
            errors.push('Camera status response was malformed');
            setSystemStatus(null);
          }
        } else {
          console.error('Camera status request failed:', response.status, response.statusText);
          errors.push(`Camera status request failed (${response.status})`);
          setSystemStatus(null);
        }
      } else {
        const reason = statusResult.reason as { name?: string; message?: string };
        if (reason?.name === 'AbortError') {
          errors.push('Camera status request timed out');
        } else {
          console.error('Camera status request rejected:', reason);
          errors.push('Failed to load camera system status');
        }
        setSystemStatus(null);
      }

      if (errors.length === 0) {
        setError('');
      } else {
        setError(errors.join(' | '));
      }

    } catch (error) {
      console.error('Error loading camera data:', error);
      setError('Failed to load camera data');
    } finally {
      setLoading(false);
    }

  };

  const loadRecordings = async () => {
    try {
      const token = localStorage.getItem('access_token');
      
      const response = await fetch(buildApiUrl('/api/camera/recordings?recording_type=experiment&limit=100'), {
        headers: { 'Authorization': `Bearer ${token}` }
      });

      if (response.ok) {
        const data = await response.json();
        setExperimentFolders(data.data?.experiment_folders || []);
      }
    } catch (error) {
      console.error('Error loading experiment folders:', error);
      setError('Failed to load experiment folders');
    }
  };

  const handleCameraStatusChange = (cameraId: number, status: string) => {
    setCameras(prev => prev.map(camera => 
      camera.id === cameraId 
        ? { ...camera, is_recording: status === 'recording' }
        : camera
    ));
  };

  const handleError = (errorMessage: string) => {
    setError(errorMessage);
  };

  const downloadRecording = async (filename: string) => {
    try {
      const token = localStorage.getItem('access_token');
      
      const response = await fetch(buildApiUrl(`/api/camera/recording/${filename}`), {
        headers: { 'Authorization': `Bearer ${token}` }
      });

      if (response.ok) {
        const blob = await response.blob();
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = filename;
        a.click();
        URL.revokeObjectURL(url);
      } else {
        setError('Failed to download recording');
      }
    } catch (error) {
      console.error('Error downloading recording:', error);
      setError('Failed to download recording');
    }
  };

  // Streaming functions
  const loadStreamingStatus = async () => {
    try {
      const token = localStorage.getItem('access_token');
      
      const response = await fetch(buildApiUrl('/api/camera/streaming/status'), {
        headers: { 'Authorization': `Bearer ${token}` }
      });
      
      if (response.ok) {
        const data = await response.json();
        setStreamingStatus(data.data.status);
      }
    } catch (error) {
      console.error('Error loading streaming status:', error);
    }
  };

  const createStreamingSession = async (quality: string = 'adaptive') => {
    if (streamingLoading) return;
    
    setStreamingLoading(true);
    try {
      const token = localStorage.getItem('access_token');
      
      const response = await fetch(buildApiUrl('/api/camera/streaming/session'), {
        method: 'POST',
        headers: { 
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({ quality })
      });
      
      if (response.ok) {
        const data = await response.json();
        const session = data.data;
        setMySession(session);
        
        // Connect to WebSocket for live streaming
        connectToStreamingWebSocket(session.session_id);
        
        await loadStreamingStatus();
      } else {
        const errorData = await response.json();
        setError(errorData.detail || 'Failed to create streaming session');
      }
    } catch (error) {
      console.error('Error creating streaming session:', error);
      setError('Failed to create streaming session');
    } finally {
      setStreamingLoading(false);
    }
  };

  const connectToStreamingWebSocket = (sessionId: string) => {
    const wsUrl = buildWsUrl(`/api/camera/streaming/video/${sessionId}`);
    console.log('Connecting to streaming WebSocket:', wsUrl);
    
    const ws = new WebSocket(wsUrl);
    
    ws.onopen = () => {
      console.log('Streaming WebSocket connected');
      // Update session state to connected
      setMySession(prev => prev ? { ...prev, websocket_state: 'connected' } : null);
    };
    
    ws.onmessage = (event) => {
      try {
        const message = JSON.parse(event.data);
        console.log('Streaming WebSocket message type:', message.type);

        if (message.type === 'frame' && message.data) {
          const frameDataUrl = `data:image/jpeg;base64,${message.data}`;
          setCurrentFrame(frameDataUrl);
        } else if (message.type === 'status') {
          console.log('Stream status:', message.status);
        } else if (message.type === 'error') {
          console.error('Stream error:', message.error);
          setError(message.error || 'Streaming error');
        }
      } catch (error) {
        console.error('Error parsing WebSocket message:', error);
        console.log('Raw message data:', event.data.substring(0, 200), '...');
      }
    };
    
    ws.onerror = (error) => {
      console.error('Streaming WebSocket error:', error);
      setError('WebSocket connection failed');
      setCurrentFrame(null);
      };
    
    ws.onclose = () => {
      console.log('Streaming WebSocket closed');
      setMySession(prev => prev ? { ...prev, websocket_state: 'disconnected' } : null);
      setCurrentFrame(null);
      };
    
    // Store WebSocket reference for cleanup
    setWsRef(ws);
    return ws;
  };

  const stopStreamingSession = async () => {
    if (!mySession || streamingLoading) return;

    // Close WebSocket connection
    if (wsRef) {
      wsRef.close();
      setWsRef(null);
    }
    setCurrentFrame(null);

    setStreamingLoading(true);
    try {
      const token = localStorage.getItem('access_token');

      const response = await fetch(buildApiUrl(`/api/camera/streaming/session/${mySession.session_id}`), {
        method: 'DELETE',
        headers: { Authorization: `Bearer ${token}` },
      });

      if (response.ok) {
        setMySession(null);
        await loadStreamingStatus();
        setCurrentFrame(null);
      } else {
        setError('Failed to stop streaming session');
      }
    } catch (error) {
      console.error('Error stopping streaming session:', error);
      setError('Failed to stop streaming session');
    } finally {
      setStreamingLoading(false);
    }
  };

  if (loading) {
    return <PageLoading message="Loading camera system..." />;
  }

  return (
    <>
      <Container 
        maxWidth="xl" 
        sx={{ 
          mt: { xs: 2, md: 4 }, 
          mb: { xs: 2, md: 4 },
          px: { xs: 1, sm: 2 }
        }}
      >
      {/* Header */}
      <Box sx={{ 
        display: 'flex', 
        alignItems: 'center', 
        mb: { xs: 2, md: 3 },
        flexWrap: 'wrap',
        gap: 1
      }}>
        <Button
          startIcon={<ArrowBackIcon />}
          onClick={() => navigate('/')}
          sx={{ 
            mr: { xs: 0, sm: 2 },
            minHeight: { xs: 44, sm: 36 }
          }}
        >
          Back to Dashboard
        </Button>
        <Box sx={{ display: 'flex', alignItems: 'center', flexGrow: 1 }}>
          <VideocamIcon sx={{ 
            mr: 1, 
            color: 'primary.main',
            fontSize: { xs: 24, sm: 28 }
          }} />
          <Typography 
            variant="h4" 
            sx={{ flexGrow: 1 }}
          >
            Camera System
          </Typography>
        </Box>
        
        {/* System Status Button */}
        <Stack 
          direction={{ xs: 'column', sm: 'row' }} 
          spacing={1}
          sx={{ width: { xs: '100%', sm: 'auto' } }}
        >
          <Button
            variant="outlined"
            startIcon={<InfoIcon />}
            onClick={() => setStatusDialogOpen(true)}
            sx={{ 
              minHeight: { xs: 44, sm: 36 },
              fontSize: { xs: '0.875rem', sm: '0.875rem' }
            }}
          >
            System Status
          </Button>
          <Button
            variant="outlined"
            startIcon={<RefreshIcon />}
            onClick={loadCameraData}
            sx={{ 
              minHeight: { xs: 44, sm: 36 },
              fontSize: { xs: '0.875rem', sm: '0.875rem' }
            }}
          >
            Refresh
          </Button>
        </Stack>
      </Box>

      {/* Error Display */}
      {error && (
        <ServerError
          message={error}
          retryable={true}
          onRetry={loadCameraData}
          onClose={() => setError('')}
          sx={{ mb: 3 }}
        />
      )}

      {/* Tabs */}
      <Paper sx={{ mb: { xs: 2, md: 3 } }}>
        <Tabs 
          value={currentTab} 
          onChange={(e, newValue) => setCurrentTab(newValue)}
          sx={{ 
            borderBottom: 1, 
            borderColor: 'divider',
            '& .MuiTabs-flexContainer': {
              flexWrap: { xs: 'wrap', sm: 'nowrap' }
            }
          }}
          variant="scrollable"
          scrollButtons="auto"
          allowScrollButtonsMobile
        >
          <Tab 
            label={`Live Cameras (${cameras.length})`}
            icon={<VideocamIcon />}
            iconPosition="start"
            sx={{ 
              minHeight: { xs: 72, sm: 48 },
              fontSize: { xs: '0.75rem', sm: '0.875rem' },
              minWidth: { xs: 120, sm: 160 }
            }}
          />
          <Tab 
            label={`Video Archive (${experimentFolders.length})`}
            icon={<VideoLibraryIcon />}
            iconPosition="start"
            sx={{ 
              minHeight: { xs: 72, sm: 48 },
              fontSize: { xs: '0.75rem', sm: '0.875rem' },
              minWidth: { xs: 120, sm: 160 }
            }}
          />
          <Tab 
            label={`Live Streaming ${streamingStatus ? `(${streamingStatus.active_session_count}/${streamingStatus.max_sessions})` : ''}`}
            icon={<StreamIcon />}
            iconPosition="start"
            sx={{ 
              minHeight: { xs: 72, sm: 48 },
              fontSize: { xs: '0.75rem', sm: '0.875rem' },
              minWidth: { xs: 120, sm: 160 }
            }}
          />
        </Tabs>
      </Paper>

      {/* Live Cameras Tab */}
      <TabPanel value={currentTab} index={0}>
        {cameras.length > 0 ? (
          <Grid container spacing={{ xs: 2, md: 3 }}>
            {cameras.map((camera) => (
              <Grid item xs={12} sm={6} lg={4} key={camera.id}>
                <Card>
                  <CardContent sx={{ p: { xs: 2, sm: 3 } }}>
                    <Box sx={{ 
                      display: 'flex', 
                      alignItems: 'center', 
                      mb: 2,
                      flexWrap: 'wrap',
                      gap: 1
                    }}>
                      <VideocamIcon sx={{ 
                        mr: 1, 
                        color: 'primary.main',
                        fontSize: { xs: 20, sm: 24 }
                      }} />
                      <Typography 
                        variant="h6"
                        sx={{ flexGrow: 1 }}
                      >
                        {camera.name}
                      </Typography>
                      <Chip
                        label={camera.is_recording ? 'Recording' : 'Available'}
                        color={camera.is_recording ? 'success' : 'default'}
                        size="small"
                      />
                    </Box>
                    
                    <Stack spacing={{ xs: 1.5, sm: 2 }}>
                      <Box>
                        <Typography variant="body2" color="textSecondary">
                          Resolution
                        </Typography>
                        <Typography 
                          variant="body1"
                          sx={{ fontSize: { xs: '0.875rem', sm: '1rem' } }}
                        >
                          {camera.width} x {camera.height}
                        </Typography>
                      </Box>
                      
                      <Box>
                        <Typography variant="body2" color="textSecondary">
                          Frame Rate
                        </Typography>
                        <Typography 
                          variant="body1"
                          sx={{ fontSize: { xs: '0.875rem', sm: '1rem' } }}
                        >
                          {camera.fps} FPS
                        </Typography>
                      </Box>
                      
                      <Box>
                        <Typography variant="body2" color="textSecondary">
                          Status
                        </Typography>
                        <Chip
                          label={camera.status}
                          color={camera.status === 'active' ? 'success' : 'default'}
                          size="small"
                        />
                      </Box>
                      
                      <Box>
                        <Typography variant="body2" color="textSecondary">
                          Live Stream Available
                        </Typography>
                        <Typography 
                          variant="body1"
                          sx={{ fontSize: { xs: '0.875rem', sm: '1rem' } }}
                        >
                          {camera.has_live_stream ? 'Yes' : 'No'}
                        </Typography>
                      </Box>
                      
                      <Divider />
                      
                      <Typography 
                        variant="body2" 
                        color="textSecondary" 
                        sx={{ 
                          fontStyle: 'italic',
                          fontSize: { xs: '0.75rem', sm: '0.875rem' }
                        }}
                      >
                        Use the Live Streaming tab to view live video from this camera.
                      </Typography>
                    </Stack>
                  </CardContent>
                </Card>
              </Grid>
            ))}
          </Grid>
        ) : (
          <Card>
            <CardContent>
              <Box sx={{ textAlign: 'center', py: 8 }}>
                <VideocamIcon sx={{ fontSize: 64, color: 'text.secondary', mb: 2 }} />
                <Typography variant="h6" color="textSecondary" gutterBottom>
                  No cameras detected
                </Typography>
                <Typography variant="body2" color="textSecondary">
                  Make sure cameras are connected and try refreshing the page.
                </Typography>
              </Box>
            </CardContent>
          </Card>
        )}
      </TabPanel>

      {/* Video Archive Tab */}
      <TabPanel value={currentTab} index={1}>
        <VideoArchiveTab
          experimentFolders={experimentFolders}
          loading={loading}
          error={error}
          onRefresh={loadRecordings}
          onDownloadVideo={downloadRecording}
        />
      </TabPanel>

      {/* Live Streaming Tab */}
      <TabPanel value={currentTab} index={2}>
        <Card>
          <CardContent sx={{ p: { xs: 2, sm: 3 } }}>
            <Stack spacing={2.5}>
              <Box
                sx={{
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'space-between',
                  flexWrap: 'wrap',
                  rowGap: 1.5
                }}
              >
                <Stack direction="row" spacing={1} alignItems="center">
                  <StreamIcon sx={{ fontSize: { xs: 20, sm: 24 } }} />
                  <Typography variant="h6">
                    Streaming Session
                  </Typography>
                  <Chip
                    label={streamingStatus?.enabled ? 'Service Enabled' : 'Service Disabled'}
                    color={streamingStatus?.enabled ? 'success' : 'default'}
                    size="small"
                  />
                </Stack>
                <Button
                  size="small"
                  startIcon={<RefreshIcon />}
                  onClick={loadStreamingStatus}
                >
                  Refresh Status
                </Button>
              </Box>

              {mySession ? (
                <Stack spacing={2}>
                  <Box>
                    <Typography variant="body2" color="textSecondary">
                      Session ID
                    </Typography>
                    <Typography variant="body1" sx={{ fontFamily: 'monospace' }}>
                      {mySession.session_id.substring(0, 8)}...
                    </Typography>
                  </Box>

                  <Box>
                    <Typography variant="body2" color="textSecondary">
                      Quality Level
                    </Typography>
                    <Chip
                      label={mySession.quality_level}
                      color="primary"
                      size="small"
                    />
                  </Box>

                  <Box>
                    <Typography variant="body2" color="textSecondary">
                      Bandwidth
                    </Typography>
                    <Typography variant="body1">
                      {mySession.bandwidth_usage_mbps.toFixed(1)} MB/s
                    </Typography>
                  </Box>

                  <Box>
                    <Typography variant="body2" color="textSecondary">
                      FPS
                    </Typography>
                    <Typography variant="body1">
                      {mySession.actual_fps.toFixed(1)} fps
                    </Typography>
                  </Box>

                  <Box>
                    <Typography variant="body2" color="textSecondary">
                      Connection
                    </Typography>
                    <Chip
                      label={mySession.websocket_state}
                      color={mySession.websocket_state === 'connected' ? 'success' : 'warning'}
                      size="small"
                    />
                  </Box>

                  <Button
                    variant="contained"
                    color="error"
                    startIcon={<StopIcon />}
                    onClick={stopStreamingSession}
                    disabled={streamingLoading}
                    fullWidth
                    sx={{
                      minHeight: { xs: 44, sm: 36 },
                      fontSize: { xs: '0.875rem', sm: '0.875rem' }
                    }}
                  >
                    {streamingLoading ? <ButtonLoading message="" /> : 'Stop My Stream'}
                  </Button>

                  <Divider />

                  <Box>
                    <Typography variant="subtitle2" gutterBottom>
                      Live Stream
                    </Typography>

                    {mySession.websocket_state === 'connected' ? (
                      <Box
                        sx={{
                          position: 'relative',
                          width: '100%',
                          height: { xs: 240, sm: 300, md: 360 },
                          bgcolor: 'black',
                          borderRadius: 1,
                          display: 'flex',
                          alignItems: 'center',
                          justifyContent: 'center',
                          overflow: 'hidden'
                        }}
                      >
                        <IconButton
                          size="small"
                          onClick={() => setFullscreenDialogOpen(true)}
                          sx={{
                            position: 'absolute',
                            top: 8,
                            right: 8,
                            bgcolor: 'rgba(0,0,0,0.5)',
                            color: 'common.white',
                            '&:hover': { bgcolor: 'rgba(0,0,0,0.7)' }
                          }}
                        >
                          <FullscreenIcon fontSize="small" />
                        </IconButton>
                        {currentFrame ? (
                          <img
                            src={currentFrame}
                            alt="Live camera stream"
                            style={{ width: '100%', height: '100%', objectFit: 'contain' }}
                          />
                        ) : (
                          <Stack spacing={2} alignItems="center">
                            <LoadingSpinner
                              variant="spinner"
                              size="large"
                              color="primary"
                              message="Waiting for frames..."
                            />
                            <Typography variant="body2" color="grey.400">
                              Session {mySession.session_id.substring(0, 8)}…
                            </Typography>
                          </Stack>
                        )}
                      </Box>
                    ) : (
                      <Box
                        sx={{
                          width: '100%',
                          height: { xs: 240, sm: 300, md: 360 },
                          bgcolor: 'grey.50',
                          border: 1,
                          borderColor: 'grey.200',
                          borderRadius: 1,
                          display: 'flex',
                          alignItems: 'center',
                          justifyContent: 'center'
                        }}
                      >
                        <Stack spacing={2} alignItems="center">
                          <StreamIcon sx={{ fontSize: 48, color: 'grey.400' }} />
                          <Typography variant="body2" color="textSecondary">
                            Connecting to stream鈥?                          </Typography>
                        </Stack>
                      </Box>
                    )}
                  </Box>
                </Stack>
              ) : (
                <Stack spacing={2}>
                  <Typography
                    color="textSecondary"
                    sx={{ fontSize: { xs: '0.875rem', sm: '1rem' } }}
                  >
                    No active streaming session
                  </Typography>

                  <Button
                    variant="contained"
                    startIcon={<PlayArrowIcon />}
                    onClick={() => createStreamingSession()}
                    disabled={streamingLoading || !streamingStatus?.enabled}
                    fullWidth
                    sx={{
                      minHeight: { xs: 44, sm: 36 },
                      fontSize: { xs: '0.875rem', sm: '0.875rem' }
                    }}
                  >
                    {streamingLoading ? <ButtonLoading message="" /> : 'Start Streaming'}
                  </Button>

                  {streamingStatus && !streamingStatus.enabled && (
                    <Typography variant="body2" color="error" sx={{ textAlign: 'center' }}>
                      Streaming service is currently disabled
                    </Typography>
                  )}
                </Stack>
              )}
            </Stack>
          </CardContent>
        </Card>
      </TabPanel>

      {/* System Status Dialog */}
      <Dialog
        open={statusDialogOpen}
        onClose={() => setStatusDialogOpen(false)}
        maxWidth="md"
        fullWidth
      >
        <DialogTitle>
          <Box sx={{ display: 'flex', alignItems: 'center' }}>
            <InfoIcon sx={{ mr: 1 }} />
            Camera System Status
          </Box>
        </DialogTitle>
        <DialogContent>
          {systemStatus ? (
            <Grid container spacing={3}>
              {/* System Health */}
              <Grid item xs={12} md={6}>
                <Typography variant="h6" gutterBottom>
                  System Health
                </Typography>
                <List dense>
                  <ListItem>
                    <ListItemText
                      primary="Overall Status"
                      secondary={
                        <Chip
                          label={systemStatus.system_health?.healthy ? 'Healthy' : 'Issues Detected'}
                          color={systemStatus.system_health?.healthy ? 'success' : 'error'}
                          size="small"
                        />
                      }
                    />
                  </ListItem>
                  <ListItem>
                    <ListItemText
                      primary="Storage Accessible"
                      secondary={systemStatus.system_health?.storage_accessible ? 'Yes' : 'No'}
                    />
                  </ListItem>
                  <ListItem>
                    <ListItemText
                      primary="Active Threads"
                      secondary={`${systemStatus.system_health?.active_recording_threads || 0} / ${systemStatus.system_health?.total_cameras || 0}`}
                    />
                  </ListItem>
                </List>
              </Grid>

              {/* Storage Info */}
              <Grid item xs={12} md={6}>
                <Typography variant="h6" gutterBottom>
                  Storage Information
                </Typography>
                <List dense>
                  <ListItem>
                    <ListItemText
                      primary="Free Space"
                      secondary={`${systemStatus.storage_info?.free_gb || 0} GB`}
                    />
                  </ListItem>
                  <ListItem>
                    <ListItemText
                      primary="Used Space"
                      secondary={`${systemStatus.storage_info?.used_gb || 0} GB`}
                    />
                  </ListItem>
                  <ListItem>
                    <ListItemText
                      primary="Usage"
                      secondary={`${systemStatus.storage_info?.usage_percent || 0}%`}
                    />
                  </ListItem>
                </List>
              </Grid>

              {/* Configuration */}
              <Grid item xs={12}>
                <Typography variant="h6" gutterBottom>
                  Configuration
                </Typography>
                <Grid container spacing={2}>
                  <Grid item xs={6} sm={3}>
                    <Typography variant="body2" color="textSecondary">
                      Max Cameras: {systemStatus.configuration?.max_cameras}
                    </Typography>
                  </Grid>
                  <Grid item xs={6} sm={3}>
                    <Typography variant="body2" color="textSecondary">
                      Recording Duration: {systemStatus.configuration?.recording_duration_minutes}m
                    </Typography>
                  </Grid>
                  <Grid item xs={6} sm={3}>
                    <Typography variant="body2" color="textSecondary">
                      Archive Duration: {systemStatus.configuration?.archive_duration_minutes}m
                    </Typography>
                  </Grid>
                  <Grid item xs={6} sm={3}>
                    <Typography variant="body2" color="textSecondary">
                      Rolling Clips: {systemStatus.configuration?.rolling_clips_count}
                    </Typography>
                  </Grid>
                </Grid>
              </Grid>

              {/* Paths */}
              <Grid item xs={12}>
                <Typography variant="h6" gutterBottom>
                  Storage Paths
                </Typography>
                <List dense>
                  <ListItem>
                    <ListItemText
                      primary="Video Base"
                      secondary={systemStatus.paths?.video_base}
                    />
                  </ListItem>
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

      <Dialog
      fullScreen
      open={fullscreenDialogOpen}
      onClose={() => setFullscreenDialogOpen(false)}
      PaperProps={{ sx: { bgcolor: 'black' } }}
    >
      <Box sx={{ display: 'flex', flexDirection: 'column', minHeight: '100%' }}>
        <Box
          sx={{
            display: 'flex',
            alignItems: { xs: 'flex-start', sm: 'center' },
            justifyContent: 'space-between',
            gap: 2,
            flexWrap: 'wrap',
            p: { xs: 2, md: 3 },
            bgcolor: 'rgba(0,0,0,0.6)'
          }}
        >
          <Stack spacing={0.5}>
            <Typography variant="h6" color="common.white">
              Live Stream
            </Typography>
            {mySession && (
              <Typography variant="body2" color="grey.300">
                Session {mySession.session_id.substring(0, 8)} • Quality {mySession.quality_level}
              </Typography>
            )}
          </Stack>
          <IconButton
            onClick={() => setFullscreenDialogOpen(false)}
            sx={{ color: 'common.white', alignSelf: { xs: 'flex-end', sm: 'center' } }}
            aria-label="Exit fullscreen"
          >
            <CloseIcon />
          </IconButton>
        </Box>

        <Box
          sx={{
            flex: 1,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            p: { xs: 2, md: 4 },
            bgcolor: 'black'
          }}
        >
          {currentFrame ? (
            <img
              src={currentFrame}
              alt="Live camera stream fullscreen"
              style={{ maxWidth: '100%', maxHeight: '100%', objectFit: 'contain' }}
            />
          ) : mySession?.websocket_state === 'connected' ? (
            <Stack spacing={2} alignItems="center">
              <LoadingSpinner
                variant="spinner"
                size="large"
                color="primary"
                message="Waiting for frames..."
              />
              <Typography variant="body2" color="grey.400">
                Stream is active, awaiting next frame…
              </Typography>
            </Stack>
          ) : (
            <Typography variant="body1" color="grey.400">
              Stream not connected.
            </Typography>
          )}
        </Box>
      </Box>
    </Dialog>
    </>
  );
};

export default CameraPage;




