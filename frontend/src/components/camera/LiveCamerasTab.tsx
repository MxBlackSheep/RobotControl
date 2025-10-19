/**
 * LiveCamerasTab - Live camera viewing and management interface
 * 
 * Extracted from CameraPage.tsx to improve maintainability
 * Handles live camera feeds, status monitoring, and system controls
 */

import React from 'react';
import {
  Grid,
  Card,
  CardContent,
  Box,
  Typography,
  Button,
  Chip,
  IconButton,
  Tooltip
} from '@mui/material';
import {
  Videocam as VideocamIcon,
  Refresh as RefreshIcon,
  Info as InfoIcon,
  Settings as SettingsIcon
} from '@mui/icons-material';
import { ButtonLoading } from '../LoadingSpinner';

export interface CameraInfo {
  id: string;
  name: string;
  url: string;
  status: 'online' | 'offline' | 'error';
  resolution: string;
  fps: number;
  last_frame_time?: string;
  error_message?: string;
}

export interface LiveCamerasTabProps {
  cameras: CameraInfo[];
  loading: boolean;
  error: string;
  onRefresh: () => void;
  onShowStatus: () => void;
  onCameraSettings?: (camera: CameraInfo) => void;
}

const LiveCamerasTab: React.FC<LiveCamerasTabProps> = ({
  cameras,
  loading,
  error,
  onRefresh,
  onShowStatus,
  onCameraSettings
}) => {
  if (error) {
    return (
      <Box
        sx={{
          p: 3,
          borderRadius: 2,
          border: '1px solid',
          borderColor: 'error.light',
          bgcolor: 'rgba(244, 67, 54, 0.08)',
          textAlign: 'center'
        }}
      >
        <VideocamIcon sx={{ fontSize: 48, color: 'error.main', mb: 2 }} />
        <Typography variant="h6" color="error.main" gutterBottom>
          Unable to load cameras
        </Typography>
        <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
          {error}
        </Typography>
        <Button
          variant="contained"
          color="error"
          startIcon={<RefreshIcon />}
          onClick={onRefresh}
          disabled={loading}
        >
          {loading ? <ButtonLoading /> : 'Try Again'}
        </Button>
      </Box>
    );
  }

  if (cameras.length === 0) {
    return (
      <Box sx={{ textAlign: 'center', py: 4 }}>
        <VideocamIcon sx={{ fontSize: 48, color: 'text.secondary', mb: 2 }} />
        <Typography variant="h6" color="textSecondary" gutterBottom>
          No cameras detected
        </Typography>
        <Typography variant="body2" color="textSecondary" sx={{ mb: 3 }}>
          Please ensure cameras are connected and configured properly
        </Typography>
        <Button
          variant="contained"
          startIcon={<RefreshIcon />}
          onClick={onRefresh}
          disabled={loading}
        >
          {loading ? <ButtonLoading /> : 'Check Again'}
        </Button>
      </Box>
    );
  }

  return (
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
                  color: camera.status === 'online' ? 'success.main' : 'error.main',
                  fontSize: { xs: 20, sm: 24 }
                }} />
                <Typography 
                  variant="h6"
                  sx={{ flexGrow: 1, fontSize: { xs: '1rem', sm: '1.25rem' } }}
                >
                  {camera.name}
                </Typography>
                <Chip
                  label={camera.status}
                  color={camera.status === 'online' ? 'success' : 'error'}
                  size="small"
                />
              </Box>

              {/* Camera Details */}
              <Box sx={{ mb: 2 }}>
                <Typography variant="body2" color="textSecondary">
                  Resolution: {camera.resolution}
                </Typography>
                <Typography variant="body2" color="textSecondary">
                  FPS: {camera.fps}
                </Typography>
                {camera.last_frame_time && (
                  <Typography variant="body2" color="textSecondary">
                    Last Frame: {new Date(camera.last_frame_time).toLocaleTimeString()}
                  </Typography>
                )}
                {camera.error_message && (
                  <Typography variant="body2" color="error.main" sx={{ mt: 1 }}>
                    Error: {camera.error_message}
                  </Typography>
                )}
              </Box>

              {/* Camera Feed Placeholder */}
              <Box sx={{
                width: '100%',
                height: 200,
                backgroundColor: camera.status === 'online' ? 'grey.100' : 'grey.300',
                border: '1px solid',
                borderColor: 'divider',
                borderRadius: 1,
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                mb: 2
              }}>
                {camera.status === 'online' ? (
                  <Typography variant="body2" color="textSecondary">
                    Live Feed: {camera.name}
                  </Typography>
                ) : (
                  <Typography variant="body2" color="error.main">
                    Camera Offline
                  </Typography>
                )}
              </Box>

              {/* Camera Actions */}
              <Box sx={{ display: 'flex', gap: 1, justifyContent: 'flex-end' }}>
                {onCameraSettings && (
                  <Tooltip title="Camera Settings">
                    <IconButton
                      size="small"
                      onClick={() => onCameraSettings(camera)}
                    >
                      <SettingsIcon />
                    </IconButton>
                  </Tooltip>
                )}
                <Tooltip title="Camera Info">
                  <IconButton
                    size="small"
                    onClick={onShowStatus}
                  >
                    <InfoIcon />
                  </IconButton>
                </Tooltip>
              </Box>
            </CardContent>
          </Card>
        </Grid>
      ))}
      
      {/* Refresh Button */}
      <Grid item xs={12}>
        <Box sx={{ display: 'flex', justifyContent: 'center', mt: 2 }}>
          <Button
            startIcon={<RefreshIcon />}
            onClick={onRefresh}
            disabled={loading}
            size="large"
          >
            {loading ? <ButtonLoading /> : 'Refresh Cameras'}
          </Button>
        </Box>
      </Grid>
    </Grid>
  );
};

export default LiveCamerasTab;
