/**
 * LiveStreamingTab - Live streaming management and monitoring interface
 * 
 * Extracted from CameraPage.tsx to improve maintainability
 * Handles streaming sessions, WebSocket connections, and resource monitoring
 */

import React, { useState, useEffect, useRef } from 'react';
import {
  Grid,
  Card,
  CardContent,
  Typography,
  Button,
  Chip,
  Stack,
  Box,
  List,
  ListItem,
  ListItemText,
  ListItemSecondaryAction,
  IconButton,
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  TextField
} from '@mui/material';
import {
  Stream as StreamIcon,
  Refresh as RefreshIcon,
  PlayArrow as PlayArrowIcon,
  Stop as StopIcon,
  Close as CloseIcon
} from '@mui/icons-material';
import LoadingSpinner, { ButtonLoading } from '../LoadingSpinner';

export interface StreamingSession {
  session_id: string;
  camera_id: string;
  camera_name: string;
  client_count: number;
  bandwidth_mbps: number;
  start_time: string;
  status: 'active' | 'starting' | 'stopping' | 'error';
}

export interface StreamingStatus {
  enabled: boolean;
  active_session_count: number;
  max_sessions: number;
  total_bandwidth_mbps: number;
  resource_usage_percent: number;
  sessions: StreamingSession[];
}

export interface LiveStreamingTabProps {
  streamingStatus: StreamingStatus | null;
  loading: boolean;
  error: string;
  onRefresh: () => void;
  onStartSession: (cameraId: string) => Promise<void>;
  onStopSession: (sessionId: string) => Promise<void>;
  availableCameras?: { id: string; name: string }[];
}

const LiveStreamingTab: React.FC<LiveStreamingTabProps> = ({
  streamingStatus,
  loading,
  error,
  onRefresh,
  onStartSession,
  onStopSession,
  availableCameras = []
}) => {
  const [selectedCamera, setSelectedCamera] = useState<string>('');
  const [startDialogOpen, setStartDialogOpen] = useState(false);
  const [actionLoading, setActionLoading] = useState<string | null>(null);

  const handleStartSession = async () => {
    if (!selectedCamera) return;
    
    setActionLoading('start');
    try {
      await onStartSession(selectedCamera);
      setStartDialogOpen(false);
      setSelectedCamera('');
      onRefresh();
    } catch (error) {
      console.error('Failed to start streaming session:', error);
    } finally {
      setActionLoading(null);
    }
  };

  const handleStopSession = async (sessionId: string) => {
    setActionLoading(sessionId);
    try {
      await onStopSession(sessionId);
      onRefresh();
    } catch (error) {
      console.error('Failed to stop streaming session:', error);
    } finally {
      setActionLoading(null);
    }
  };

  if (error) {
    return (
      <Box
        sx={{
          p: 3,
          borderRadius: 2,
          border: '1px solid',
          borderColor: 'error.light',
          bgcolor: 'rgba(244, 67, 54, 0.08)'
        }}
      >
        <Stack spacing={2} alignItems="center" textAlign="center">
          <StreamIcon sx={{ fontSize: 48, color: 'error.main' }} />
          <Box>
            <Typography variant="h6" color="error.main">
              Streaming service unavailable
            </Typography>
            <Typography variant="body2" color="text.secondary">
              {error}
            </Typography>
          </Box>
          <Button
            variant="contained"
            color="error"
            startIcon={<RefreshIcon />}
            onClick={onRefresh}
            disabled={loading}
          >
            {loading ? <ButtonLoading /> : 'Try Again'}
          </Button>
        </Stack>
      </Box>
    );
  }

  return (
    <>
      <Grid container spacing={{ xs: 2, md: 3 }}>
        {/* Streaming Status Card */}
        <Grid item xs={12} lg={6}>
          <Card>
            <CardContent sx={{ p: { xs: 2, sm: 3 } }}>
              <Box sx={{ 
                display: 'flex', 
                justifyContent: 'space-between', 
                alignItems: 'center',
                mb: 2
              }}>
                <Typography 
                  variant="h6"
                  sx={{ display: 'flex', alignItems: 'center', gap: 1 }}
                >
                  <StreamIcon sx={{ fontSize: { xs: 20, sm: 24 } }} />
                  Streaming Status
                </Typography>
                <Button
                  size="small"
                  startIcon={<RefreshIcon />}
                  onClick={onRefresh}
                  disabled={loading}
                >
                  {loading ? <ButtonLoading /> : 'Refresh'}
                </Button>
              </Box>
              
              {streamingStatus ? (
                <Stack spacing={2}>
                  <Box>
                    <Typography variant="body2" color="textSecondary">
                      Service Status
                    </Typography>
                    <Chip
                      label={streamingStatus.enabled ? 'Enabled' : 'Disabled'}
                      color={streamingStatus.enabled ? 'success' : 'default'}
                      size="small"
                    />
                  </Box>
                  
                  <Box>
                    <Typography variant="body2" color="textSecondary">
                      Active Sessions
                    </Typography>
                    <Typography variant="body1">
                      {streamingStatus.active_session_count} / {streamingStatus.max_sessions}
                    </Typography>
                  </Box>
                  
                  <Box>
                    <Typography variant="body2" color="textSecondary">
                      Bandwidth Usage
                    </Typography>
                    <Typography variant="body1">
                      {streamingStatus.total_bandwidth_mbps.toFixed(1)} MB/s
                    </Typography>
                  </Box>
                  
                  <Box>
                    <Typography variant="body2" color="textSecondary">
                      System Resources
                    </Typography>
                    <Typography variant="body1">
                      {streamingStatus.resource_usage_percent.toFixed(1)}%
                    </Typography>
                  </Box>

                  {streamingStatus.enabled && (
                    <Button
                      variant="contained"
                      startIcon={<PlayArrowIcon />}
                      onClick={() => setStartDialogOpen(true)}
                      disabled={streamingStatus.active_session_count >= streamingStatus.max_sessions}
                      fullWidth
                    >
                      Start New Session
                    </Button>
                  )}
                </Stack>
              ) : (
                <Box sx={{ textAlign: 'center', py: 2 }}>
                  <LoadingSpinner message="Loading streaming status..." />
                </Box>
              )}
            </CardContent>
          </Card>
        </Grid>

        {/* Active Sessions Card */}
        <Grid item xs={12} lg={6}>
          <Card>
            <CardContent sx={{ p: { xs: 2, sm: 3 } }}>
              <Typography variant="h6" gutterBottom>
                Active Sessions ({streamingStatus?.active_session_count || 0})
              </Typography>
              
              {streamingStatus?.sessions && streamingStatus.sessions.length > 0 ? (
                <List dense>
                  {streamingStatus.sessions.map((session) => (
                    <StreamingSessionItem
                      key={session.session_id}
                      session={session}
                      onStop={handleStopSession}
                      loading={actionLoading === session.session_id}
                    />
                  ))}
                </List>
              ) : (
                <Box sx={{ textAlign: 'center', py: 3 }}>
                  <StreamIcon sx={{ fontSize: 48, color: 'text.secondary', mb: 2 }} />
                  <Typography variant="body2" color="textSecondary">
                    No active streaming sessions
                  </Typography>
                </Box>
              )}
            </CardContent>
          </Card>
        </Grid>

        {/* WebSocket Connection Status */}
        <Grid item xs={12}>
          <WebSocketStatusCard />
        </Grid>
      </Grid>

      {/* Start Session Dialog */}
      <Dialog open={startDialogOpen} onClose={() => setStartDialogOpen(false)}>
        <DialogTitle>Start Streaming Session</DialogTitle>
        <DialogContent>
          <TextField
            select
            fullWidth
            label="Select Camera"
            value={selectedCamera}
            onChange={(e) => setSelectedCamera(e.target.value)}
            SelectProps={{ native: true }}
            sx={{ mt: 1 }}
          >
            <option value="">Select a camera...</option>
            {availableCameras.map((camera) => (
              <option key={camera.id} value={camera.id}>
                {camera.name}
              </option>
            ))}
          </TextField>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setStartDialogOpen(false)}>Cancel</Button>
          <Button
            onClick={handleStartSession}
            disabled={!selectedCamera || actionLoading === 'start'}
            variant="contained"
          >
            {actionLoading === 'start' ? <ButtonLoading /> : 'Start Session'}
          </Button>
        </DialogActions>
      </Dialog>
    </>
  );
};

// Sub-component for individual streaming sessions
interface StreamingSessionItemProps {
  session: StreamingSession;
  onStop: (sessionId: string) => void;
  loading: boolean;
}

const StreamingSessionItem: React.FC<StreamingSessionItemProps> = ({
  session,
  onStop,
  loading
}) => {
  return (
    <ListItem>
      <ListItemText
        primary={session.camera_name}
        secondary={
          <Stack direction="row" spacing={1} alignItems="center">
            <Chip
              label={session.status}
              color={session.status === 'active' ? 'success' : 'warning'}
              size="small"
            />
            <Typography variant="body2" color="textSecondary">
              {session.client_count} clients
            </Typography>
            <Typography variant="body2" color="textSecondary">
              {session.bandwidth_mbps.toFixed(1)} MB/s
            </Typography>
          </Stack>
        }
      />
      <ListItemSecondaryAction>
        <IconButton
          edge="end"
          onClick={() => onStop(session.session_id)}
          disabled={loading}
          color="error"
          size="small"
        >
          {loading ? <ButtonLoading size="small" /> : <StopIcon />}
        </IconButton>
      </ListItemSecondaryAction>
    </ListItem>
  );
};

// Sub-component for WebSocket connection status
const WebSocketStatusCard: React.FC = () => {
  const [connectionStatus, setConnectionStatus] = useState<'connected' | 'connecting' | 'disconnected'>('disconnected');
  const wsRef = useRef<WebSocket | null>(null);

  useEffect(() => {
    // WebSocket connection logic would go here
    // This is a placeholder for the WebSocket implementation
    return () => {
      if (wsRef.current) {
        wsRef.current.close();
      }
    };
  }, []);

  return (
    <Card>
      <CardContent>
        <Typography variant="h6" gutterBottom>
          WebSocket Connection
        </Typography>
        <Stack direction="row" spacing={2} alignItems="center">
          <Chip
            label={connectionStatus}
            color={connectionStatus === 'connected' ? 'success' : 'warning'}
            size="small"
          />
          <Typography variant="body2" color="textSecondary">
            Real-time streaming updates
          </Typography>
        </Stack>
      </CardContent>
    </Card>
  );
};

export default LiveStreamingTab;
