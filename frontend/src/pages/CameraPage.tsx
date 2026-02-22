/**
 * Camera Management Page for RobotControl Simplified Architecture
 * 
 * Features:
 * - Live camera streaming interface
 * - Video archive browsing and playback
 * - Recording management controls
 */

import React, { useState, useEffect, useRef } from 'react';
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
  Divider,
  LinearProgress
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

interface DownloadProgressState {
  filename: string;
  downloadedBytes: number;
  totalBytes: number | null;
  attempt: number;
  maxAttempts: number;
  isRetrying: boolean;
}

class NonRetryableDownloadError extends Error {}

const MAX_DOWNLOAD_ATTEMPTS = 5;
const RETRY_BASE_DELAY_MS = 1200;
const RETRY_MAX_DELAY_MS = 8000;

const wait = (ms: number) =>
  new Promise<void>((resolve) => {
    window.setTimeout(resolve, ms);
  });

const formatBytes = (bytes: number): string => {
  if (!Number.isFinite(bytes) || bytes < 0) {
    return '0 B';
  }

  const units = ['B', 'KB', 'MB', 'GB'];
  let size = bytes;
  let unitIndex = 0;

  while (size >= 1024 && unitIndex < units.length - 1) {
    size /= 1024;
    unitIndex += 1;
  }

  return `${size.toFixed(size >= 100 ? 0 : 1)} ${units[unitIndex]}`;
};

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
  const [downloadProgress, setDownloadProgress] = useState<DownloadProgressState | null>(null);
  const downloadAbortRef = useRef<AbortController | null>(null);
  const downloadCancelledRef = useRef(false);
  const downloadInFlightRef = useRef(false);

  // Cleanup WebSocket on unmount
  useEffect(() => {
    return () => {
      if (wsRef) {
        wsRef.close();
      }
    };
  }, [wsRef]);

  useEffect(() => {
    return () => {
      downloadCancelledRef.current = true;
      if (downloadAbortRef.current) {
        downloadAbortRef.current.abort();
      }
      downloadInFlightRef.current = false;
    };
  }, []);

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
    if (downloadInFlightRef.current || downloadProgress) {
      setError('Another download is already in progress');
      return;
    }

    const token = localStorage.getItem('access_token');
    if (!token) {
      setError('Missing authentication token. Please sign in again.');
      return;
    }

    setError('');
    downloadCancelledRef.current = false;
    downloadInFlightRef.current = true;

    let downloadedBytes = 0;
    let totalBytes: number | null = null;
    let contentType = 'application/octet-stream';
    const chunks: ArrayBuffer[] = [];

    setDownloadProgress({
      filename,
      downloadedBytes: 0,
      totalBytes: null,
      attempt: 1,
      maxAttempts: MAX_DOWNLOAD_ATTEMPTS,
      isRetrying: false
    });

    try {
      for (let attempt = 1; attempt <= MAX_DOWNLOAD_ATTEMPTS; attempt += 1) {
        if (downloadCancelledRef.current) {
          break;
        }

        const abortController = new AbortController();
        downloadAbortRef.current = abortController;

        setDownloadProgress((prev) => prev ? {
          ...prev,
          downloadedBytes,
          totalBytes,
          attempt,
          isRetrying: false
        } : prev);

        try {
          const headers: Record<string, string> = {
            Authorization: `Bearer ${token}`
          };
          if (downloadedBytes > 0) {
            headers.Range = `bytes=${downloadedBytes}-`;
          }

          const response = await fetch(buildApiUrl(`/api/camera/recording/${filename}`), {
            headers,
            signal: abortController.signal
          });

          if (!response.ok) {
            if (response.status === 416 && totalBytes !== null && downloadedBytes >= totalBytes) {
              break;
            }

            let message = `Download request failed (${response.status})`;
            if (response.status === 404) {
              message = 'Recording not found on server. It may have been moved or deleted.';
            } else if (response.status === 401 || response.status === 403) {
              message = 'You are not authorized to download this recording.';
            } else if (response.status >= 400 && response.status < 500) {
              message = 'Download request is invalid and cannot be retried automatically.';
            }

            if (response.status >= 400 && response.status < 500 && response.status !== 408 && response.status !== 429) {
              throw new NonRetryableDownloadError(message);
            }

            throw new Error(message);
          }

          const currentContentType = response.headers.get('Content-Type');
          if (currentContentType) {
            contentType = currentContentType;
          }

          const contentRange = response.headers.get('Content-Range');
          const contentLengthHeader = response.headers.get('Content-Length');

          if (contentRange) {
            const rangeMatch = /bytes\s+(\d+)-(\d+)\/(\d+|\*)/i.exec(contentRange);
            if (rangeMatch) {
              const rangeStart = Number(rangeMatch[1]);
              const totalFromHeader = rangeMatch[3] === '*' ? null : Number(rangeMatch[3]);
              if (downloadedBytes > 0 && rangeStart !== downloadedBytes) {
                throw new Error('Server resume offset mismatch');
              }
              if (totalFromHeader !== null && Number.isFinite(totalFromHeader)) {
                totalBytes = totalFromHeader;
              }
            }
          } else if (contentLengthHeader) {
            const contentLength = Number(contentLengthHeader);
            if (Number.isFinite(contentLength) && contentLength >= 0) {
              totalBytes = downloadedBytes > 0
                ? (totalBytes ?? downloadedBytes + contentLength)
                : contentLength;
            }
            if (downloadedBytes > 0 && response.status === 200) {
              // Server ignored range request; restart cleanly from byte 0.
              downloadedBytes = 0;
              chunks.length = 0;
              totalBytes = Number.isFinite(contentLength) ? contentLength : totalBytes;
            }
          }

          const reader = response.body?.getReader();
          if (!reader) {
            const arrayBuffer = await response.arrayBuffer();
            chunks.push(arrayBuffer);
            downloadedBytes += arrayBuffer.byteLength;
            setDownloadProgress((prev) => prev ? {
              ...prev,
              downloadedBytes,
              totalBytes
            } : prev);
            break;
          }

          while (true) {
            const { done, value } = await reader.read();
            if (done) {
              break;
            }
            if (!value || value.length === 0) {
              continue;
            }

            // Copy into a plain ArrayBuffer so Blob constructor typing stays strict.
            const copiedChunk = new Uint8Array(value.byteLength);
            copiedChunk.set(value);
            chunks.push(copiedChunk.buffer);
            downloadedBytes += value.length;
            setDownloadProgress((prev) => prev ? {
              ...prev,
              downloadedBytes,
              totalBytes
            } : prev);
          }

          break;
        } catch (downloadError) {
          const aborted = downloadError instanceof DOMException && downloadError.name === 'AbortError';
          if (downloadCancelledRef.current || aborted) {
            break;
          }

          if (downloadError instanceof NonRetryableDownloadError) {
            throw downloadError;
          }

          if (attempt === MAX_DOWNLOAD_ATTEMPTS) {
            throw downloadError;
          }

          const retryDelayMs = Math.min(
            RETRY_BASE_DELAY_MS * (2 ** (attempt - 1)),
            RETRY_MAX_DELAY_MS
          );

          setDownloadProgress((prev) => prev ? {
            ...prev,
            downloadedBytes,
            totalBytes,
            attempt,
            isRetrying: true
          } : prev);

          let waitedMs = 0;
          while (waitedMs < retryDelayMs && !downloadCancelledRef.current) {
            await wait(Math.min(200, retryDelayMs - waitedMs));
            waitedMs += 200;
          }

          if (downloadCancelledRef.current) {
            break;
          }
        }
      }

      if (downloadCancelledRef.current) {
        return;
      }

      if (chunks.length === 0) {
        throw new Error('No data was received');
      }

      if (totalBytes !== null && downloadedBytes < totalBytes) {
        throw new Error('Download incomplete');
      }

      const blob = new Blob(chunks, { type: contentType });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = filename;
      a.click();
      URL.revokeObjectURL(url);
    } catch (downloadError) {
      console.error('Error downloading recording:', downloadError);
      const message = downloadError instanceof Error
        ? downloadError.message
        : 'Failed to download recording after multiple retry attempts';
      setError(message);
    } finally {
      downloadAbortRef.current = null;
      setDownloadProgress(null);
      downloadCancelledRef.current = false;
      downloadInFlightRef.current = false;
    }
  };

  const cancelActiveDownload = () => {
    downloadCancelledRef.current = true;
    if (downloadAbortRef.current) {
      downloadAbortRef.current.abort();
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

      {downloadProgress && (
        <Paper sx={{ mb: 3, p: 2 }}>
          <Stack spacing={1.5}>
            <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 2, flexWrap: 'wrap' }}>
              <Typography variant="subtitle1" sx={{ wordBreak: 'break-word' }}>
                Downloading {downloadProgress.filename}
              </Typography>
              <Button size="small" color="warning" variant="outlined" onClick={cancelActiveDownload}>
                Cancel
              </Button>
            </Box>
            <Typography variant="body2" color="text.secondary">
              {downloadProgress.totalBytes
                ? `${formatBytes(downloadProgress.downloadedBytes)} / ${formatBytes(downloadProgress.totalBytes)}`
                : `${formatBytes(downloadProgress.downloadedBytes)} downloaded`}
              {` · Attempt ${downloadProgress.attempt}/${downloadProgress.maxAttempts}`}
              {downloadProgress.isRetrying ? ' · Reconnecting...' : ''}
            </Typography>
            {downloadProgress.totalBytes && downloadProgress.totalBytes > 0 ? (
              <LinearProgress
                variant="determinate"
                value={Math.min(100, (downloadProgress.downloadedBytes / downloadProgress.totalBytes) * 100)}
              />
            ) : (
              <LinearProgress variant="indeterminate" />
            )}
          </Stack>
        </Paper>
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
          downloadingFilename={downloadProgress?.filename ?? null}
          downloadBusy={Boolean(downloadProgress)}
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
