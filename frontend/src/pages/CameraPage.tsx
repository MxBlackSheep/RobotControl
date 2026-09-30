import CameraControls, { type CameraSummary } from '../components/CameraControls';
import CameraViewport from '../components/CameraViewport';
import { createFrameStore } from '../components/LiveFrame';
import { useAuth } from '../context/AuthContext';
import { useModuleSection } from '../components/navigation';
import SectionPanel from '../components/SectionPanel';
import { PageContent, PageHeader } from '../components/PageLayout';
/**
 * Camera Management Page for RobotControl Simplified Architecture
 * 
 * Features:
 * - Live camera streaming interface
 * - Video archive browsing and playback
 * - Recording management controls
 */

import React, { useState, useEffect, useRef, useMemo, useCallback } from 'react';
import { Box, Typography, Button, Paper, Stack, LinearProgress, Chip, CircularProgress } from '@mui/material';
import { PlayArrow as PlayArrowIcon, Stop as StopIcon } from '@mui/icons-material';
import StatusDialog from '../components/StatusDialog';
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

const CameraPage: React.FC = () => {
  
  // State management
  const [experimentFolders, setExperimentFolders] = useState<ExperimentFolder[]>([]);
  const [archiveLoading, setArchiveLoading] = useState(true);
  const [archiveError, setArchiveError] = useState('');
  const [error, setError] = useState('');
  const { user } = useAuth();
  const [currentTab] = useModuleSection('/camera', user);
  
  // Streaming state
  const [streamingStatus, setStreamingStatus] = useState<StreamingStatus | null>(null);
  const [mySession, setMySession] = useState<StreamingSession | null>(null);
  const [streamingLoading, setStreamingLoading] = useState(false);
  const frameStore = useMemo(createFrameStore, []);
  const [hasFrame, setHasFrame] = useState(false);
  const setCurrentFrame = useCallback((value: string | null) => {
    const changedAvailability = Boolean(frameStore.getSnapshot()) !== Boolean(value);
    frameStore.set(value);
    if (changedAvailability) setHasFrame(Boolean(value));
  }, [frameStore]);
  const [cameraSummary, setCameraSummary] = useState<CameraSummary>({ text: 'Camera: Checking · Recording: Checking', error: null });
  const [sourceRevision, setSourceRevision] = useState(0);
  const handleSourceChange = useCallback(() => {
    setCurrentFrame(null);
    setSourceRevision(value => value + 1);
  }, [setCurrentFrame]);

  // Video streaming state
  const wsRef = useRef<WebSocket | null>(null);
  const streamRequestRef = useRef<AbortController | null>(null);
  const mountedRef = useRef(true);
  const [downloadProgress, setDownloadProgress] = useState<DownloadProgressState | null>(null);
  const downloadAbortRef = useRef<AbortController | null>(null);
  const downloadCancelledRef = useRef(false);
  const downloadInFlightRef = useRef(false);

  const closeSocket = useCallback(() => {
    const socket = wsRef.current;
    wsRef.current = null;
    if (socket) {
      socket.onopen = socket.onmessage = socket.onerror = socket.onclose = null;
      socket.close();
    }
    setCurrentFrame(null);
  }, [setCurrentFrame]);
  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
      streamRequestRef.current?.abort();
      closeSocket();
    };
  }, [closeSocket]);

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
    if (streamingLoading || streamRequestRef.current) return;
    const controller = new AbortController();
    streamRequestRef.current = controller;
    setStreamingLoading(true);
    try {
      const token = localStorage.getItem('access_token');
      
      const response = await fetch(buildApiUrl('/api/camera/streaming/session'), {
        method: 'POST',
        signal: controller.signal,
        headers: { 
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({ quality })
      });
      
      if (response.ok) {
        const data = await response.json();
        const session = data.data;
        if (!mountedRef.current || controller.signal.aborted) return;
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
      if (!mountedRef.current || controller.signal.aborted) return;
      console.error('Error creating streaming session:', error);
      setError('Failed to create streaming session');
    } finally {
      if (streamRequestRef.current === controller) streamRequestRef.current = null;
      if (mountedRef.current) setStreamingLoading(false);
    }
  };

  const connectToStreamingWebSocket = (sessionId: string) => {
    const wsUrl = buildWsUrl(`/api/camera/streaming/video/${sessionId}`);
    
    setCurrentFrame(null);
    closeSocket();
    const ws = new WebSocket(wsUrl);
    wsRef.current = ws;
    
    ws.onopen = () => {
      // Update session state to connected
      setMySession(prev => prev ? { ...prev, websocket_state: 'connected' } : null);
    };
    
    ws.onmessage = (event) => {
      try {
        const message = JSON.parse(event.data);

        if (message.type === 'frame' && message.data) {
          const frameDataUrl = `data:image/jpeg;base64,${message.data}`;
          setCurrentFrame(frameDataUrl);
        } else if (message.type === 'error') {
          console.error('Stream error:', message.error);
          setError(message.error || 'Streaming error');
        }
      } catch (error) {
        console.error('Error parsing WebSocket message:', error);
      }
    };
    
    ws.onerror = (error) => {
      console.error('Streaming WebSocket error:', error);
      setError('WebSocket connection failed');
      setCurrentFrame(null);
      };
    
    ws.onclose = () => {
      setMySession(prev => prev ? { ...prev, websocket_state: 'disconnected' } : null);
      setCurrentFrame(null);
      };
    
    // Store WebSocket reference for cleanup
    return ws;
  };

  const reconnectLiveView = async () => {
    if (!mySession || streamingLoading) return;
    setStreamingLoading(true);
    closeSocket();
    setCurrentFrame(null);
    try {
      const response = await fetch(buildApiUrl(`/api/camera/streaming/session/${mySession.session_id}`), {
        method: 'DELETE', headers: { Authorization: `Bearer ${localStorage.getItem('access_token')}` },
      });
      if (!response.ok && response.status !== 404) throw new Error('Could not release the previous live-view session');
      setMySession(null);
      await createStreamingSession();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Could not reconnect live view');
    } finally { setStreamingLoading(false); }
  };

  const stopStreamingSession = async () => {
    if (!mySession || streamingLoading) return;

    // Close WebSocket connection
    closeSocket();
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

  return (
    <>
      <PageContent variant="inspection">
      <PageHeader title={currentTab === 0 ? "Recordings" : "Live camera"} />

      {/* Error Display */}
      <StatusDialog
        status={error && currentTab !== 1 ? { title: 'Server Error', message: error, severity: 'error', action: { label: 'Retry', onClick: handleRefresh } } : null}
        onClose={() => setError('')}
      />

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

      {/* Video Archive Tab */}
      <SectionPanel active={currentTab === 0}>
        <VideoArchiveTab
          experimentFolders={experimentFolders}
          loading={archiveLoading}
          error={archiveError}
          onRefresh={() => void loadRecordings()}
          onDownloadVideo={downloadRecording}
          downloadingFilename={downloadProgress?.filename ?? null}
          downloadBusy={Boolean(downloadProgress)}
        />
      </SectionPanel>

      {/* The viewer owns display transforms only; camera controls keep polling below it. */}
      <SectionPanel active={currentTab === 1}>
        <CameraViewport
          store={frameStore}
          hasFrame={hasFrame}
          connection={mySession?.websocket_state ?? 'idle'}
          summary={cameraSummary.text}
          sourceRevision={sourceRevision}
          error={cameraSummary.error || error}
          controls={<>
            <Chip size="small" label={mySession ? `My view: ${mySession.websocket_state}` : 'My view: stopped'}
              color={mySession?.websocket_state === 'connected' ? 'success' : 'default'} />
            {mySession ? <>
              <Button variant="outlined" startIcon={<StopIcon />} onClick={stopStreamingSession} disabled={streamingLoading}>
                {streamingLoading ? <CircularProgress size={20} /> : 'Stop my live view'}
              </Button>
              <Button onClick={() => void reconnectLiveView()} disabled={streamingLoading}>Reconnect live view</Button>
            </> : <Button variant="contained" startIcon={<PlayArrowIcon />} onClick={() => void createStreamingSession()}
              disabled={streamingLoading || !streamingStatus?.enabled}>
              {streamingLoading ? <CircularProgress size={20} /> : 'Start my live view'}
            </Button>}
            {streamingStatus && !streamingStatus.enabled && <Typography variant="body2" color="error">Live viewing is currently disabled</Typography>}
          </>}
        />
        <CameraControls active={currentTab === 1} admin={user?.role === 'admin'} collapsible onSourceChange={handleSourceChange} onSummaryChange={setCameraSummary} />
        {mySession && <Box component="details" sx={{ mt: 1, color: 'text.secondary', fontSize: '0.875rem', '& summary': { cursor: 'pointer', minHeight: 44, display: 'flex', alignItems: 'center' } }}>
          <summary>Live view details</summary>
          <Typography variant="body2" sx={{ overflowWrap: 'anywhere' }}>Session ID: {mySession.session_id}</Typography>
          <Button onClick={() => void loadStreamingStatus()} sx={{ minHeight: 44 }}>Refresh view status</Button>
        </Box>}
      </SectionPanel>
      </PageContent>
    </>
  );
};

export default CameraPage;
