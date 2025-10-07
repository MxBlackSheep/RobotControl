/**
 * VideoArchiveTab - Video archive management and browsing interface
 * 
 * Extracted from CameraPage.tsx to improve maintainability
 * Handles experiment folder browsing, video listing, and download functionality
 */

import React from 'react';
import {
  Box,
  Card,
  CardContent,
  Typography,
  List,
  ListItem,
  ListItemText,
  ListItemSecondaryAction,
  IconButton,
  Chip,
  Stack,
  Button
} from '@mui/material';
import {
  VideoLibrary as VideoLibraryIcon,
  Download as DownloadIcon,
  Delete as DeleteIcon,
  Refresh as RefreshIcon
} from '@mui/icons-material';
import { ButtonLoading } from '../LoadingSpinner';
import ErrorAlert from '../ErrorAlert';

export interface VideoFile {
  filename: string;
  timestamp: string;
  size_bytes: number;
  duration?: number;
}

export interface ExperimentFolder {
  folder_name: string;
  video_count: number;
  total_size_bytes: number;
  creation_time: string;
  videos: VideoFile[];
}

export interface VideoArchiveTabProps {
  experimentFolders: ExperimentFolder[];
  loading: boolean;
  error: string;
  onRefresh: () => void;
  onDownloadVideo: (filename: string) => void;
  onDeleteVideo?: (filename: string) => void;
}

// Utility functions
const formatFileSize = (bytes: number): string => {
  const units = ['B', 'KB', 'MB', 'GB'];
  let size = bytes;
  let unitIndex = 0;
  
  while (size >= 1024 && unitIndex < units.length - 1) {
    size /= 1024;
    unitIndex++;
  }
  
  return `${size.toFixed(1)} ${units[unitIndex]}`;
};

const formatTimestamp = (timestamp: string): string => {
  try {
    return new Date(timestamp).toLocaleString();
  } catch {
    return timestamp;
  }
};

const VideoArchiveTab: React.FC<VideoArchiveTabProps> = ({
  experimentFolders,
  loading,
  error,
  onRefresh,
  onDownloadVideo,
  onDeleteVideo
}) => {
  if (error) {
    return (
      <ErrorAlert
        message={error}
        severity="error"
        category="server"
        retryable={true}
        onRetry={onRefresh}
      />
    );
  }

  return (
    <Card>
      <CardContent>
        <Box sx={{ 
          display: 'flex', 
          justifyContent: 'space-between', 
          alignItems: 'center', 
          mb: 2 
        }}>
          <Typography variant="h6" gutterBottom>
            Video Archive ({experimentFolders.length} experiment folders)
          </Typography>
          <Button
            startIcon={<RefreshIcon />}
            onClick={onRefresh}
            disabled={loading}
            size="small"
          >
            {loading ? <ButtonLoading /> : 'Refresh'}
          </Button>
        </Box>
        
        {/* Experiment Folders Section */}
        {experimentFolders.length > 0 ? (
          <Box>
            <Typography variant="subtitle1" gutterBottom sx={{ fontWeight: 'bold' }}>
              Experiment Folders
            </Typography>
            {experimentFolders.map((folder) => (
              <ExperimentFolderCard
                key={folder.folder_name}
                folder={folder}
                onDownloadVideo={onDownloadVideo}
                onDeleteVideo={onDeleteVideo}
              />
            ))}
          </Box>
        ) : (
          <Box sx={{ textAlign: 'center', py: 4 }}>
            <VideoLibraryIcon sx={{ fontSize: 48, color: 'text.secondary', mb: 2 }} />
            <Typography variant="h6" color="textSecondary" gutterBottom>
              No experiment videos found
            </Typography>
            <Typography variant="body2" color="textSecondary" sx={{ mb: 3 }}>
              Videos will appear here after experiments are completed
            </Typography>
            <Button
              variant="contained"
              startIcon={<RefreshIcon />}
              onClick={onRefresh}
              disabled={loading}
            >
              {loading ? <ButtonLoading /> : 'Check for Videos'}
            </Button>
          </Box>
        )}
      </CardContent>
    </Card>
  );
};

// Sub-component for individual experiment folders
interface ExperimentFolderCardProps {
  folder: ExperimentFolder;
  onDownloadVideo: (filename: string) => void;
  onDeleteVideo?: (filename: string) => void;
}

const ExperimentFolderCard: React.FC<ExperimentFolderCardProps> = ({
  folder,
  onDownloadVideo,
  onDeleteVideo
}) => {
  return (
    <Card variant="outlined" sx={{ mb: 2 }}>
      <CardContent>
        <Typography variant="h6" gutterBottom>
          {folder.folder_name}
        </Typography>
        <Stack direction="row" spacing={2} sx={{ mb: 2 }}>
          <Chip
            label={`${folder.video_count} videos`}
            size="small"
            color="primary"
          />
          <Typography variant="body2" color="textSecondary">
            {formatFileSize(folder.total_size_bytes)}
          </Typography>
          <Typography variant="body2" color="textSecondary">
            {formatTimestamp(folder.creation_time)}
          </Typography>
        </Stack>
        
        {/* Videos in folder */}
        <List dense>
          {folder.videos.map((video) => (
            <VideoListItem
              key={video.filename}
              video={video}
              onDownload={() => onDownloadVideo(video.filename)}
              onDelete={onDeleteVideo ? () => onDeleteVideo(video.filename) : undefined}
            />
          ))}
        </List>
      </CardContent>
    </Card>
  );
};

// Sub-component for individual video items
interface VideoListItemProps {
  video: VideoFile;
  onDownload: () => void;
  onDelete?: () => void;
}

const VideoListItem: React.FC<VideoListItemProps> = ({
  video,
  onDownload,
  onDelete
}) => {
  return (
    <ListItem>
      <ListItemText
        primary={video.filename}
        secondary={
          <Stack direction="row" spacing={1} alignItems="center">
            <Typography variant="body2" color="textSecondary">
              {formatTimestamp(video.timestamp)}
            </Typography>
            <Typography variant="body2" color="textSecondary">
              {formatFileSize(video.size_bytes)}
            </Typography>
            {video.duration && (
              <Typography variant="body2" color="textSecondary">
                {video.duration}s
              </Typography>
            )}
          </Stack>
        }
      />
      <ListItemSecondaryAction>
        <Stack direction="row" spacing={1}>
          <IconButton
            edge="end"
            onClick={onDownload}
            size="small"
            title="Download video"
          >
            <DownloadIcon />
          </IconButton>
          {onDelete && (
            <IconButton
              edge="end"
              onClick={onDelete}
              size="small"
              color="error"
              title="Delete video"
            >
              <DeleteIcon />
            </IconButton>
          )}
        </Stack>
      </ListItemSecondaryAction>
    </ListItem>
  );
};

export default VideoArchiveTab;