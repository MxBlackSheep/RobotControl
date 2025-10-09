/**
 * Camera Viewer Component for PyRobot Simplified Architecture
 * 
 * Features:
 * - Live camera streaming via MJPEG and WebSocket
 * - Camera control (start/stop recording)
 * - Real-time status monitoring
 * - Full-screen viewing mode
 * - Camera selection and management
 */

import React, { useState, useEffect, useRef, useCallback } from 'react';
import {
  Box,
  Card,
  CardContent,
  Typography,
  Button,
  IconButton,
  Chip,
  Dialog,
  Tooltip,
  Stack,
  Grid,
  Paper,
  useTheme,
  useMediaQuery
} from '@mui/material';
import LoadingSpinner from './LoadingSpinner';
import ErrorAlert from './ErrorAlert';
import { buildApiUrl, buildWsUrl } from '@/utils/apiBase';
import {
  PlayArrow as PlayIcon,
  Stop as StopIcon,
  Fullscreen as FullscreenIcon,
  FullscreenExit as FullscreenExitIcon,
  Refresh as RefreshIcon,
  Videocam as VideocamIcon,
  VideocamOff as VideocamOffIcon,
  Settings as SettingsIcon
} from '@mui/icons-material';

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

interface CameraViewerProps {
  cameraId: number;
  cameraInfo?: CameraInfo;
  onStatusChange?: (cameraId: number, status: string) => void;
  onError?: (error: string) => void;
}

const CameraViewer: React.FC<CameraViewerProps> = ({
  cameraId,
  cameraInfo,
  onStatusChange,
  onError
}) => {
  // Theme and responsive hooks
  const theme = useTheme();
  const isMobile = useMediaQuery(theme.breakpoints.down('md')); // < 768px
  const isSmallScreen = useMediaQuery(theme.breakpoints.down('sm')); // < 600px
  
  // State management
  const [isStreaming, setIsStreaming] = useState(false);
  const [isRecording, setIsRecording] = useState(false);
  const [connectionStatus, setConnectionStatus] = useState<'connecting' | 'connected' | 'disconnected'>('disconnected');
  const [error, setError] = useState<string>('');
  const [fullscreen, setFullscreen] = useState(false);
  const [lastFrameTime, setLastFrameTime] = useState<Date | null>(null);
  const [frameCount, setFrameCount] = useState(0);
  const [streamQuality, setStreamQuality] = useState<'high' | 'medium' | 'low'>('high');

  // Refs
  const streamRef = useRef<HTMLImageElement>(null);
  const wsRef = useRef<WebSocket | null>(null);
  const streamUrlRef = useRef<string>('');// Auto-detect stream quality based on device capabilities
  useEffect(() => {
    if (isMobile) {
      // Optimize for mobile bandwidth
      const connection = (navigator as any).connection;
      if (connection) {
        if (connection.effectiveType === '4g') {
          setStreamQuality('medium');
        } else if (connection.effectiveType === '3g' || connection.effectiveType === '2g') {
          setStreamQuality('low');
        }
      } else {
        // Default to medium quality on mobile if we can't detect connection
        setStreamQuality('medium');
      }
    } else {
      setStreamQuality('high');
    }
  }, [isMobile]);

  // Initialize component
  useEffect(() => {
    if (cameraInfo) {
      setIsRecording(cameraInfo.is_recording);
    }
    return () => {
      cleanup();
    };
  }, [cameraId, cameraInfo]);

  // Cleanup function
  const cleanup = useCallback(() => {
    if (wsRef.current) {
      wsRef.current.close();
      wsRef.current = null;
    }
    if (streamUrlRef.current) {
      URL.revokeObjectURL(streamUrlRef.current);
      streamUrlRef.current = '';
    }
    setIsStreaming(false);
    setConnectionStatus('disconnected');
  }, []);

  // Start MJPEG stream
  const startMJPEGStream = useCallback(async () => {
    try {
      setConnectionStatus('connecting');
      setError('');

      const token = localStorage.getItem('access_token');
      const streamUrl = buildApiUrl(`/api/camera/stream/${cameraId}`);
      
      if (streamRef.current) {
        streamRef.current.onload = () => {
          setConnectionStatus('connected');
          setIsStreaming(true);
          setLastFrameTime(new Date());
          setFrameCount(prev => prev + 1);
        };
        
        streamRef.current.onerror = () => {
          setError('Failed to load camera stream');
          setConnectionStatus('disconnected');
          setIsStreaming(false);
        };
        
        // Set stream source with authentication header (if needed via proxy)
        streamRef.current.src = streamUrl;
      }
    } catch (error) {
      console.error('Error starting MJPEG stream:', error);
      setError('Failed to start camera stream');
      setConnectionStatus('disconnected');
      onError?.('Failed to start camera stream');
    }
  }, [cameraId, onError]);

  // Start WebSocket stream
  const startWebSocketStream = useCallback(() => {
    try {
      setConnectionStatus('connecting');
      setError('');

      // Add quality parameter for mobile optimization
      const qualityParam = isMobile ? `?quality=${streamQuality}` : '';
      const wsUrl = buildWsUrl(`/api/camera/ws/${cameraId}${qualityParam}`);
      wsRef.current = new WebSocket(wsUrl);

      wsRef.current.onopen = () => {
        setConnectionStatus('connected');
        console.log(`WebSocket connected for camera ${cameraId}`);
        
        // Send initial ping
        wsRef.current?.send(JSON.stringify({ type: 'ping' }));
      };

      wsRef.current.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);
          
          switch (data.type) {
            case 'connected':
              setIsStreaming(true);
              break;
              
            case 'frame':
              // Handle base64 frame data
              if (streamRef.current && data.data) {
                streamRef.current.src = `data:image/jpeg;base64,${data.data}`;
                setLastFrameTime(new Date());
                setFrameCount(prev => prev + 1);
              }
              break;
              
            case 'pong':
            case 'heartbeat':
              // Connection is alive
              setLastFrameTime(new Date());
              break;
              
            case 'error':
            case 'warning':
              setError(data.message || 'WebSocket error');
              break;
              
            case 'no_frame':
              // No frame available (camera not recording)
              break;
          }
        } catch (error) {
          console.error('Error parsing WebSocket message:', error);
        }
      };

      wsRef.current.onerror = (error) => {
        console.error('WebSocket error:', error);
        setError('WebSocket connection error');
        setConnectionStatus('disconnected');
      };

      wsRef.current.onclose = () => {
        console.log(`WebSocket closed for camera ${cameraId}`);
        setConnectionStatus('disconnected');
        setIsStreaming(false);
      };

      // Request frames periodically - optimize FPS for mobile
      const getFps = () => {
        if (!isMobile) return 15; // Desktop: 15 FPS
        if (streamQuality === 'low') return 8; // Low quality mobile: 8 FPS
        if (streamQuality === 'medium') return 12; // Medium quality mobile: 12 FPS
        return 15; // High quality mobile: 15 FPS
      };
      
      const frameInterval = setInterval(() => {
        if (wsRef.current?.readyState === WebSocket.OPEN) {
          wsRef.current.send(JSON.stringify({ 
            type: 'request_frame',
            quality: streamQuality,
            mobile: isMobile
          }));
        }
      }, 1000 / getFps());

      // Cleanup interval on unmount
      return () => {
        clearInterval(frameInterval);
      };

    } catch (error) {
      console.error('Error starting WebSocket stream:', error);
      setError('Failed to start WebSocket stream');
      setConnectionStatus('disconnected');
      onError?.('Failed to start WebSocket stream');
    }
  }, [cameraId, onError, isMobile, streamQuality]);

  // Stop stream
  const stopStream = useCallback(() => {
    cleanup();
    setFrameCount(0);
    setLastFrameTime(null);
  }, [cleanup]);

  // Toggle fullscreen
  const toggleFullscreen = () => {
    setFullscreen(!fullscreen);
  };

  // Get status color
  const getStatusColor = () => {
    if (connectionStatus === 'connected' && isStreaming) return 'success';
    if (connectionStatus === 'connecting') return 'warning';
    return 'error';
  };

  // Get status text
  const getStatusText = () => {
    if (connectionStatus === 'connected' && isStreaming) return 'Live';
    if (connectionStatus === 'connecting') return 'Connecting';
    return 'Offline';
  };

  return (
    <>
      <Card>
        <CardContent>
          {/* Header */}
          <Box sx={{ 
            display: 'flex', 
            justifyContent: 'space-between', 
            alignItems: 'center', 
            mb: 2,
            flexWrap: 'wrap',
            gap: 1
          }}>
            <Typography 
              variant="h6" 
              sx={{ 
                display: 'flex', 
                alignItems: 'center',
                fontSize: { xs: '1rem', sm: '1.25rem' }
              }}
            >
              <VideocamIcon sx={{ 
                mr: 1,
                fontSize: { xs: 20, sm: 24 }
              }} />
              {cameraInfo?.name || `Camera ${cameraId}`}
            </Typography>
            
            <Stack 
              direction={{ xs: 'column', sm: 'row' }} 
              spacing={1} 
              alignItems="center"
              sx={{ minWidth: { xs: '100%', sm: 'auto' } }}
            >
              <Chip
                label={getStatusText()}
                color={getStatusColor()}
                size="small"
                icon={isRecording ? <VideocamIcon /> : <VideocamOffIcon />}
              />
              
              {isRecording && (
                <Chip
                  label="Recording"
                  color="error"
                  size="small"
                  sx={{ animation: 'pulse 1.5s infinite' }}
                />
              )}
              
              {/* Stream Quality Indicator for Mobile */}
              {isMobile && (
                <Chip
                  label={`${streamQuality.toUpperCase()} Quality`}
                  color="info"
                  size="small"
                  variant="outlined"
                />
              )}
            </Stack>
          </Box>

          {/* Error Display */}
          {error && (
            <ErrorAlert
              message={error}
              severity="error"
              category="network"
              retryable={true}
              onRetry={() => window.location.reload()}
              onClose={() => setError('')}
              sx={{ mb: 2 }}
            />
          )}

          {/* Camera Info */}
          {cameraInfo && (
            <Grid container spacing={{ xs: 1, sm: 2 }} sx={{ mb: 2 }}>
              <Grid item xs={6} sm={3}>
                <Typography 
                  variant="body2" 
                  color="textSecondary"
                  sx={{ fontSize: { xs: '0.75rem', sm: '0.875rem' } }}
                >
                  Resolution: {cameraInfo.width}x{cameraInfo.height}
                </Typography>
              </Grid>
              <Grid item xs={6} sm={3}>
                <Typography 
                  variant="body2" 
                  color="textSecondary"
                  sx={{ fontSize: { xs: '0.75rem', sm: '0.875rem' } }}
                >
                  FPS: {cameraInfo.fps}
                </Typography>
              </Grid>
              <Grid item xs={6} sm={3}>
                <Typography 
                  variant="body2" 
                  color="textSecondary"
                  sx={{ fontSize: { xs: '0.75rem', sm: '0.875rem' } }}
                >
                  Frames: {frameCount}
                </Typography>
              </Grid>
              <Grid item xs={6} sm={3}>
                <Typography 
                  variant="body2" 
                  color="textSecondary"
                  sx={{ fontSize: { xs: '0.75rem', sm: '0.875rem' } }}
                >
                  Last: {lastFrameTime ? lastFrameTime.toLocaleTimeString() : 'None'}
                </Typography>
              </Grid>
            </Grid>
          )}

          {/* Video Display */}
          <Paper sx={{ 
            position: 'relative', 
            backgroundColor: 'black', 
            minHeight: { xs: 200, sm: 250, md: 300 },
            borderRadius: 1,
            overflow: 'hidden'
          }}>
            {connectionStatus === 'connecting' ? (
              <Box sx={{ 
                display: 'flex', 
                justifyContent: 'center', 
                alignItems: 'center', 
                height: { xs: 200, sm: 250, md: 300 },
                flexDirection: 'column'
              }}>
                <LoadingSpinner 
                  variant="spinner" 
                  message="Connecting to camera..."
                  size="large"
                />
              </Box>
            ) : isStreaming ? (
              <Box 
                sx={{ position: 'relative' }}
                onDoubleClick={toggleFullscreen} // Double tap to fullscreen on mobile
              >
                <img
                  ref={streamRef}
                  alt={`Camera ${cameraId} stream`}
                  style={{
                    width: '100%',
                    height: 'auto',
                    maxHeight: isMobile ? '250px' : '400px',
                    objectFit: 'contain',
                    userSelect: 'none', // Prevent selection on mobile
                    WebkitUserSelect: 'none'
                  }}
                />
                
                {/* Fullscreen button overlay - larger for mobile */}
                <IconButton
                  sx={{
                    position: 'absolute',
                    top: { xs: 4, sm: 8 },
                    right: { xs: 4, sm: 8 },
                    backgroundColor: 'rgba(0, 0, 0, 0.5)',
                    color: 'white',
                    minWidth: { xs: 44, sm: 40 }, // Touch-friendly size
                    minHeight: { xs: 44, sm: 40 },
                    '&:hover': {
                      backgroundColor: 'rgba(0, 0, 0, 0.7)'
                    }
                  }}
                  onClick={toggleFullscreen}
                  aria-label="Toggle fullscreen"
                >
                  <FullscreenIcon />
                </IconButton>
                
                {/* Mobile touch hint overlay */}
                {isMobile && (
                  <Box
                    sx={{
                      position: 'absolute',
                      bottom: 8,
                      left: 8,
                      backgroundColor: 'rgba(0, 0, 0, 0.7)',
                      color: 'white',
                      padding: '4px 8px',
                      borderRadius: 1,
                      fontSize: '0.75rem',
                      opacity: 0.8
                    }}
                  >
                    Double tap for fullscreen
                  </Box>
                )}
              </Box>
            ) : (
              <Box sx={{ 
                display: 'flex', 
                justifyContent: 'center', 
                alignItems: 'center', 
                height: { xs: 200, sm: 250, md: 300 },
                flexDirection: 'column'
              }}>
                <VideocamOffIcon sx={{ 
                  fontSize: { xs: 48, sm: 64 }, 
                  color: 'gray', 
                  mb: 2 
                }} />
                <Typography 
                  color="textSecondary"
                  sx={{ fontSize: { xs: '0.875rem', sm: '1rem' } }}
                >
                  Camera offline
                </Typography>
                <Typography 
                  variant="body2" 
                  color="textSecondary"
                  sx={{ fontSize: { xs: '0.75rem', sm: '0.875rem' } }}
                >
                  Start recording to view live stream
                </Typography>
              </Box>
            )}
          </Paper>

          {/* Controls */}
          <Box sx={{ 
            display: 'flex', 
            justifyContent: 'center', 
            gap: { xs: 1, sm: 1 }, 
            mt: 2,
            flexWrap: 'wrap'
          }}>
            <Tooltip title={isStreaming ? "Stop Stream" : "Start MJPEG Stream"}>
              <Button
                variant="outlined"
                startIcon={<VideocamIcon />}
                onClick={isStreaming ? stopStream : startMJPEGStream}
                disabled={!isRecording}
                sx={{
                  minHeight: { xs: 44, sm: 36 },
                  fontSize: { xs: '0.875rem', sm: '0.875rem' },
                  minWidth: { xs: 120, sm: 'auto' }
                }}
              >
                {isStreaming ? 'Stop Stream' : (isMobile ? 'MJPEG' : 'MJPEG Stream')}
              </Button>
            </Tooltip>

            <Tooltip title="WebSocket Stream">
              <Button
                variant="outlined"
                startIcon={<SettingsIcon />}
                onClick={startWebSocketStream}
                disabled={!isRecording || isStreaming}
                sx={{
                  minHeight: { xs: 44, sm: 36 },
                  fontSize: { xs: '0.875rem', sm: '0.875rem' },
                  minWidth: { xs: 120, sm: 'auto' }
                }}
              >
                {isMobile ? 'WS' : 'WebSocket'}
              </Button>
            </Tooltip>

            <Tooltip title="Refresh">
              <IconButton 
                onClick={() => window.location.reload()}
                sx={{
                  minWidth: { xs: 44, sm: 40 },
                  minHeight: { xs: 44, sm: 40 }
                }}
              >
                <RefreshIcon />
              </IconButton>
            </Tooltip>
            
            {/* Quality selector for mobile */}
            {isMobile && (
              <Button
                variant="text"
                size="small"
                onClick={() => {
                  const qualities = ['low', 'medium', 'high'] as const;
                  const currentIndex = qualities.indexOf(streamQuality);
                  const nextIndex = (currentIndex + 1) % qualities.length;
                  setStreamQuality(qualities[nextIndex]);
                }}
                sx={{
                  minHeight: { xs: 44, sm: 36 },
                  fontSize: '0.75rem',
                  textTransform: 'none'
                }}
              >
                Quality: {streamQuality.toUpperCase()}
              </Button>
            )}
          </Box>
        </CardContent>
      </Card>

      {/* Fullscreen Dialog */}
      <Dialog
        open={fullscreen}
        onClose={toggleFullscreen}
        maxWidth={false}
        fullScreen
        PaperProps={{
          sx: { backgroundColor: 'black' }
        }}
      >
        <Box 
          sx={{ position: 'relative', width: '100%', height: '100%' }}
          onDoubleClick={toggleFullscreen} // Double tap to exit fullscreen
        >
          {streamRef.current && (
            <img
              src={streamRef.current.src}
              alt={`Camera ${cameraId} fullscreen`}
              style={{
                width: '100%',
                height: '100%',
                objectFit: 'contain',
                userSelect: 'none',
                WebkitUserSelect: 'none'
              }}
            />
          )}
          
          {/* Exit fullscreen button - larger and repositioned for mobile */}
          <IconButton
            sx={{
              position: 'absolute',
              top: { xs: 8, sm: 16 },
              right: { xs: 8, sm: 16 },
              backgroundColor: 'rgba(0, 0, 0, 0.5)',
              color: 'white',
              minWidth: { xs: 48, sm: 44 }, // Larger for mobile
              minHeight: { xs: 48, sm: 44 },
              '&:hover': {
                backgroundColor: 'rgba(0, 0, 0, 0.7)'
              }
            }}
            onClick={toggleFullscreen}
            aria-label="Exit fullscreen"
          >
            <FullscreenExitIcon />
          </IconButton>
          
          {/* Mobile touch hint for fullscreen */}
          {isMobile && (
            <Box
              sx={{
                position: 'absolute',
                bottom: 16,
                left: '50%',
                transform: 'translateX(-50%)',
                backgroundColor: 'rgba(0, 0, 0, 0.7)',
                color: 'white',
                padding: '8px 16px',
                borderRadius: 2,
                fontSize: '0.875rem',
                opacity: 0.9,
                textAlign: 'center'
              }}
            >
              Double tap or tap x to exit fullscreen
            </Box>
          )}
        </Box>
      </Dialog>

      {/* CSS for pulse animation */}
      <style>
        {`
          @keyframes pulse {
            0% { opacity: 1; }
            50% { opacity: 0.5; }
            100% { opacity: 1; }
          }
        `}
      </style>
    </>
  );
};

export default CameraViewer;


