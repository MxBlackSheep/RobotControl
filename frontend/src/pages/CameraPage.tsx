/**
 * Camera Management Page for RobotControl Simplified Architecture
 * 
 * Features:
 * - Live camera streaming interface
 * - Video archive browsing and playback
 * - Recording management controls
 */

import React, { useState, useEffect } from 'react';
import {
  Box,
  Container,
  Typography,
  Card,
  CardContent,
  Button,
  Tabs,
  Tab,
  IconButton,
  Chip,
  Paper,
  Dialog,
  Stack,
  Divider
} from '@mui/material';
import {
  ArrowBack as ArrowBackIcon,
  Videocam as VideocamIcon,
  VideoLibrary as VideoLibraryIcon,
  Refresh as RefreshIcon,
  Stream as StreamIcon,
  PlayArrow as PlayArrowIcon,
  Stop as StopIcon,
  Fullscreen as FullscreenIcon,
  Close as CloseIcon
} from '@mui/icons-material';
import { useNavigate } from 'react-router-dom';
import LoadingSpinner, { ButtonLoading } from '../components/LoadingSpinner';
import ErrorAlert, { ServerError } from '../components/ErrorAlert';
import { buildApiUrl, buildWsUrl } from '@/utils/apiBase';
import VideoArchiveTab, {
  type ExperimentFolder
} from '../components/camera/VideoArchiveTab';

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
  const [experimentFolders, setExperimentFolders] = useState<ExperimentFolder[]>([]);
  const [archiveLoading, setArchiveLoading] = useState(true);
  const [archiveError, setArchiveError] = useState('');
  const [error, setError] = useState('');
  const [currentTab, setCurrentTab] = useState(0);
  
  // Streaming state
  const [streamingStatus, setStreamingStatus] = useState<StreamingStatus | null>(null);
  const [mySession, setMySession] = useState<StreamingSession | null>(null);
  const [streamingLoading, setStreamingLoading] = useState(false);
  const [currentFrame, setCurrentFrame] = useState<string | null>(null);
  const [frameDimensions, setFrameDimensions] = useState<{ width: number; height: number } | null>(null);
  const [fullscreenDialogOpen, setFullscreenDialogOpen] = useState(false);

  // Video streaming state
  const [wsRef, setWsRef] = useState<WebSocket | null>(null);

  // Cleanup WebSocket on unmount
  useEffect(() => {
    return () => {
      if (wsRef) {
        wsRef.close();
      }
    };
  }, [wsRef]);

  // Load content when switching tabs
  useEffect(() => {
    if (currentTab === 0) {
      void loadRecordings();
    } else if (currentTab === 1) {
      void loadStreamingStatus();
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

  const loadRecordings = async () => {
    setArchiveLoading(true);
    setArchiveError('');
    try {
      const token = localStorage.getItem('access_token');
      
      const response = await fetch(buildApiUrl('/api/camera/recordings?recording_type=experiment&limit=100'), {
        headers: { Authorization: `Bearer ${token}` }
      });

      if (response.ok) {
        const data = await response.json();
        setExperimentFolders(data.data?.experiment_folders || []);
        setError('');
      } else {
        setArchiveError('Failed to load experiment folders');
        setError('Failed to load experiment folders');
      }
    } catch (err) {
      console.error('Error loading experiment folders:', err);
      setArchiveError('Failed to load experiment folders');
      setError('Failed to load experiment folders');
    } finally {
      setArchiveLoading(false);
    }
  };

  const handleRefresh = () => {
    if (currentTab === 0) {
      void loadRecordings();
    } else {
      void loadStreamingStatus();
    }
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
        setError('');
        
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
        setError('');
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

  const hasFrame = Boolean(currentFrame);
  useEffect(() => {
    if (!currentFrame) {
      setFrameDimensions(null);
    }
  }, [currentFrame]);

  const frameMaxHeight = { xs: '70vh', md: '80vh' } as const;

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
        
        <Button
          variant="outlined"
          startIcon={<RefreshIcon />}
          onClick={handleRefresh}
          sx={{ 
            minHeight: { xs: 44, sm: 36 },
            fontSize: { xs: '0.875rem', sm: '0.875rem' }
          }}
        >
          Refresh
        </Button>
      </Box>

      {/* Error Display */}
      {error && (
        <ServerError
          message={error}
          retryable={true}
          onRetry={handleRefresh}
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

      {/* Video Archive Tab */}
      <TabPanel value={currentTab} index={0}>
        <VideoArchiveTab
          experimentFolders={experimentFolders}
          loading={archiveLoading}
          error={archiveError}
          onRefresh={() => void loadRecordings()}
          onDownloadVideo={downloadRecording}
        />
      </TabPanel>

      {/* Live Streaming Tab */}
      <TabPanel value={currentTab} index={1}>
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
                  <Typography variant="h6">Streaming Session</Typography>
                </Stack>
                <Button
                  size="small"
                  startIcon={<RefreshIcon />}
                  onClick={() => loadStreamingStatus()}
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
                    <Typography
                      variant="body1"
                      sx={{ fontFamily: 'monospace', wordBreak: 'break-all' }}
                    >
                      {mySession.session_id}
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
                      hasFrame ? (
                        <Box
                          sx={{
                            position: 'relative',
                            width: '100%',
                            bgcolor: 'black',
                            borderRadius: 1,
                            overflow: 'hidden',
                            maxHeight: frameMaxHeight,
                            ...(frameDimensions && frameDimensions.width > 0 && frameDimensions.height > 0
                              ? {
                                  aspectRatio: `${frameDimensions.width} / ${frameDimensions.height}`,
                                  mx: 'auto'
                                }
                              : {
                                  minHeight: { xs: 240, sm: 300, md: 360 },
                                  display: 'flex',
                                  alignItems: 'center',
                                  justifyContent: 'center'
                                })
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
                          <Box
                            component="img"
                            src={currentFrame}
                            alt="Live camera stream"
                            onLoad={(event: React.SyntheticEvent<HTMLImageElement>) => {
                              const { naturalWidth, naturalHeight } = event.currentTarget;
                              if (!naturalWidth || !naturalHeight) return;
                              setFrameDimensions(prev => {
                                if (prev && prev.width === naturalWidth && prev.height === naturalHeight) {
                                  return prev;
                                }
                                return { width: naturalWidth, height: naturalHeight };
                              });
                            }}
                            sx={{
                              position: frameDimensions ? 'absolute' : 'relative',
                              inset: frameDimensions ? 0 : 'auto',
                              width: '100%',
                              height: frameDimensions ? '100%' : 'auto',
                              maxWidth: '100%',
                              maxHeight: frameDimensions ? '100%' : frameMaxHeight,
                              objectFit: 'contain',
                              margin: frameDimensions ? 0 : '0 auto'
                            }}
                          />
                        </Box>
                      ) : (
                        <Box
                          sx={{
                            width: '100%',
                            height: { xs: 240, sm: 300, md: 360 },
                            bgcolor: 'grey.50',
                            borderRadius: 1,
                            border: 1,
                            borderColor: 'grey.200',
                            display: 'flex',
                            alignItems: 'center',
                            justifyContent: 'center'
                          }}
                        >
                          <Stack spacing={2} alignItems="center">
                            <LoadingSpinner
                              variant="spinner"
                              size="large"
                              color="primary"
                              message="Waiting for frames..."
                            />
                            <Typography variant="body2" color="grey.400">
                              Session {mySession.session_id.substring(0, 8)}...
                            </Typography>
                          </Stack>
                        </Box>
                      )
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
                            Connecting to stream...
                          </Typography>
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
                Session {mySession.session_id.substring(0, 8)} • {mySession.websocket_state}
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
                Stream is active, awaiting next frame...
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




