/**
 * VideoArchiveTab - Collapsible, virtualized view of experiment recordings.
 *
 * Renders experiment folders as a lightweight tree, deferring the rendering of
 * individual video rows until the user expands a folder. Video rows use
 * react-window so large folders stay responsive.
 */

import React, { useCallback, useEffect, useMemo, useState } from 'react';
import {
  Box,
  Card,
  CardContent,
  Typography,
  IconButton,
  Chip,
  Stack,
  Button,
  Collapse,
  CircularProgress,
  List as MuiList,
  ListItemButton,
  ListItemIcon,
  ListItemText,
  Divider,
  Tooltip
} from '@mui/material';
import {
  VideoLibrary as VideoLibraryIcon,
  Download as DownloadIcon,
  Delete as DeleteIcon,
  Refresh as RefreshIcon,
  Folder as FolderIcon,
  ExpandLess as ExpandLessIcon,
  ExpandMore as ExpandMoreIcon
} from '@mui/icons-material';
import { List as VirtualizedList } from 'react-window';
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
  videos?: VideoFile[];
}

export interface VideoArchiveTabProps {
  experimentFolders: ExperimentFolder[];
  loading: boolean;
  error: string;
  onRefresh: () => void;
  onDownloadVideo: (filename: string) => void;
  onDeleteVideo?: (filename: string) => void;
  onLoadFolderVideos?: (folderName: string) => Promise<VideoFile[]>;
}

interface FolderState {
  videos: VideoFile[];
  loading: boolean;
  error?: string;
}

const ITEM_HEIGHT = 96;
const MAX_LIST_HEIGHT = 320;

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
  onDeleteVideo,
  onLoadFolderVideos
}) => {
  const [expandedFolders, setExpandedFolders] = useState<Record<string, boolean>>({});
  const [folderState, setFolderState] = useState<Record<string, FolderState>>({});

  // Keep folder state in sync with incoming data (e.g. refresh, new folders)
  useEffect(() => {
    setFolderState((prev) => {
      const next: Record<string, FolderState> = {};
      experimentFolders.forEach((folder) => {
        const existing = prev[folder.folder_name];
        next[folder.folder_name] = {
          videos: folder.videos ?? existing?.videos ?? [],
          loading: existing?.loading ?? false,
          error: existing?.error
        };
      });
      return next;
    });
  }, [experimentFolders]);

  const totalVideos = useMemo(
    () => experimentFolders.reduce((acc, folder) => acc + folder.video_count, 0),
    [experimentFolders]
  );

  const totalSize = useMemo(
    () => experimentFolders.reduce((acc, folder) => acc + folder.total_size_bytes, 0),
    [experimentFolders]
  );

  const ensureVideosLoaded = useCallback(
    async (folder: ExperimentFolder) => {
      const cached = folderState[folder.folder_name];
      const hasVideosLoaded =
        (folder.videos && folder.videos.length > 0) || (cached?.videos?.length ?? 0) > 0;

      if (hasVideosLoaded || !onLoadFolderVideos) {
        return;
      }

      setFolderState((prev) => ({
        ...prev,
        [folder.folder_name]: { videos: [], loading: true }
      }));

      try {
        const videos = await onLoadFolderVideos(folder.folder_name);
        setFolderState((prev) => ({
          ...prev,
          [folder.folder_name]: { videos, loading: false }
        }));
      } catch (fetchError) {
        console.error(`Failed to load videos for ${folder.folder_name}:`, fetchError);
        setFolderState((prev) => ({
          ...prev,
          [folder.folder_name]: {
            videos: [],
            loading: false,
            error: fetchError instanceof Error ? fetchError.message : 'Failed to load videos'
          }
        }));
      }
    },
    [folderState, onLoadFolderVideos]
  );

  const toggleFolder = useCallback(
    (folder: ExperimentFolder) => {
      const isExpanded = !!expandedFolders[folder.folder_name];
      setExpandedFolders((prev) => ({
        ...prev,
        [folder.folder_name]: !isExpanded
      }));

      if (!isExpanded) {
        void ensureVideosLoaded(folder);
      }
    },
    [ensureVideosLoaded, expandedFolders]
  );

  if (error) {
    return (
      <ErrorAlert
        message={error}
        severity="error"
        category="server"
        retryable
        onRetry={onRefresh}
      />
    );
  }

  return (
    <Card>
      <CardContent>
        <Box
          sx={{
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: { xs: 'flex-start', sm: 'center' },
            gap: 2,
            flexWrap: 'wrap',
            mb: 2
          }}
        >
          <Stack spacing={0.5}>
            <Typography variant="h6">
              Video Archive ({experimentFolders.length} folders)
            </Typography>
            {experimentFolders.length > 0 && (
              <Stack direction="row" spacing={2} flexWrap="wrap" sx={{ color: 'text.secondary' }}>
                <Typography variant="body2">{totalVideos} files</Typography>
                <Typography variant="body2">{formatFileSize(totalSize)}</Typography>
              </Stack>
            )}
          </Stack>
          <Button
            startIcon={<RefreshIcon />}
            onClick={onRefresh}
            disabled={loading}
            size="small"
          >
            {loading ? <ButtonLoading /> : 'Refresh'}
          </Button>
        </Box>

        {loading && experimentFolders.length === 0 ? (
          <Box sx={{ textAlign: 'center', py: 4 }}>
            <CircularProgress size={32} sx={{ mb: 2 }} />
            <Typography variant="body2" color="textSecondary">
              Loading recordings...
            </Typography>
          </Box>
        ) : experimentFolders.length === 0 ? (
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
        ) : (
          <FolderTree
            folders={experimentFolders}
            expanded={expandedFolders}
            folderState={folderState}
            onToggle={toggleFolder}
            onEnsureVideos={ensureVideosLoaded}
            onDownloadVideo={onDownloadVideo}
            onDeleteVideo={onDeleteVideo}
          />
        )}
      </CardContent>
    </Card>
  );
};

interface FolderTreeProps {
  folders: ExperimentFolder[];
  expanded: Record<string, boolean>;
  folderState: Record<string, FolderState>;
  onToggle: (folder: ExperimentFolder) => void;
  onEnsureVideos: (folder: ExperimentFolder) => void | Promise<void>;
  onDownloadVideo: (filename: string) => void;
  onDeleteVideo?: (filename: string) => void;
}

const FolderTree: React.FC<FolderTreeProps> = ({
  folders,
  expanded,
  folderState,
  onToggle,
  onEnsureVideos,
  onDownloadVideo,
  onDeleteVideo
}) => {
  return (
    <MuiList disablePadding sx={{ border: 1, borderColor: 'divider', borderRadius: 1 }}>
      {folders.map((folder, index) => {
        const isExpanded = !!expanded[folder.folder_name];
        const state = folderState[folder.folder_name] ?? { videos: [], loading: false };

        return (
          <Box key={folder.folder_name}>
            <ListItemButton
              onClick={() => onToggle(folder)}
              sx={{ alignItems: 'flex-start', py: 1.5 }}
            >
              <ListItemIcon sx={{ minWidth: 36, mt: 0.25 }}>
                <Tooltip title={`${folder.video_count} videos`}>
                  <FolderIcon color={isExpanded ? 'primary' : 'inherit'} />
                </Tooltip>
              </ListItemIcon>
              <ListItemText
                primary={
                  <Stack
                    direction={{ xs: 'column', sm: 'row' }}
                    spacing={1}
                    alignItems={{ xs: 'flex-start', sm: 'center' }}
                    flexWrap="wrap"
                    sx={{ width: '100%' }}
                  >
                    <Typography
                      variant="subtitle1"
                      sx={{
                        wordBreak: 'break-word',
                        overflowWrap: 'anywhere',
                        maxWidth: '100%'
                      }}
                    >
                      {folder.folder_name}
                    </Typography>
                    <Chip
                      label={`${folder.video_count} videos`}
                      size="small"
                      color="primary"
                      variant="outlined"
                    />
                    <Typography variant="body2" color="text.secondary">
                      {formatFileSize(folder.total_size_bytes)}
                    </Typography>
                  </Stack>
                }
                secondary={
                  <Typography variant="body2" color="text.secondary">
                    Updated {formatTimestamp(folder.creation_time)}
                  </Typography>
                }
              />
              {isExpanded ? <ExpandLessIcon /> : <ExpandMoreIcon />}
            </ListItemButton>

            <Collapse in={isExpanded} timeout="auto" unmountOnExit>
              <Box sx={{ pl: { xs: 6, sm: 8 }, pr: { xs: 2, sm: 4 }, pb: 2 }}>
                {state.loading ? (
                  <Box sx={{ display: 'flex', justifyContent: 'center', py: 3 }}>
                    <CircularProgress size={24} />
                  </Box>
                ) : state.error ? (
                  <ErrorAlert
                    message={state.error}
                    severity="error"
                    category="client"
                    retryable
                    onRetry={() => onEnsureVideos(folder)}
                  />
                ) : state.videos.length === 0 ? (
                  <Typography variant="body2" color="text.secondary" sx={{ py: 2 }}>
                    No videos detected in this folder.
                  </Typography>
                ) : (
                  <VirtualizedVideoList
                    videos={state.videos}
                    onDownloadVideo={onDownloadVideo}
                    onDeleteVideo={onDeleteVideo}
                  />
                )}
              </Box>
            </Collapse>

            {index < folders.length - 1 && <Divider component="li" />}
          </Box>
        );
      })}
    </MuiList>
  );
};

interface VirtualizedVideoListProps {
  videos: VideoFile[];
  onDownloadVideo: (filename: string) => void;
  onDeleteVideo?: (filename: string) => void;
}

type VideoRowExtraProps = {
  videos: VideoFile[];
  onDownloadVideo: (filename: string) => void;
  onDeleteVideo?: (filename: string) => void;
};

const VideoListRow: React.FC<
  { index: number; style: React.CSSProperties } & VideoRowExtraProps
> = ({ index, style, videos, onDownloadVideo, onDeleteVideo }) => {
  const video = videos[index];
  const isLast = index === videos.length - 1;

  return (
    <Box
      style={style}
      sx={{
        boxSizing: 'border-box',
        display: 'flex',
        flexWrap: 'wrap',
        alignItems: 'center',
        gap: 1.5,
        py: 1,
        pr: 1.5,
        pl: 1,
        borderBottom: isLast ? 'none' : '1px solid',
        borderColor: 'divider',
        bgcolor: 'background.paper'
      }}
    >
      <Box sx={{ flexGrow: 1, minWidth: 0, pr: { xs: 0, sm: 1.5 } }}>
        <Typography
          variant="body2"
          sx={{ fontWeight: 500, overflowWrap: 'anywhere' }}
        >
          {video.filename}
        </Typography>
        <Stack
          direction="row"
          spacing={1}
          alignItems="center"
          flexWrap="wrap"
          sx={{ color: 'text.secondary', fontSize: '0.75rem' }}
        >
          <Typography variant="caption" color="text.secondary">
            {formatTimestamp(video.timestamp)}
          </Typography>
          <Typography variant="caption" color="text.secondary">
            {formatFileSize(video.size_bytes)}
          </Typography>
          {typeof video.duration === 'number' && (
            <Typography variant="caption" color="text.secondary">
              {video.duration}s
            </Typography>
          )}
        </Stack>
      </Box>
      <Box
        sx={{
          display: 'flex',
          alignItems: 'center',
          gap: 1,
          flexShrink: 0,
          marginLeft: { xs: 0, sm: 'auto' }
        }}
      >
        <Tooltip title="Download video">
          <IconButton onClick={() => onDownloadVideo(video.filename)} size="small">
            <DownloadIcon fontSize="small" />
          </IconButton>
        </Tooltip>
        {onDeleteVideo && (
          <Tooltip title="Delete video">
            <IconButton onClick={() => onDeleteVideo(video.filename)} size="small" color="error">
              <DeleteIcon fontSize="small" />
            </IconButton>
          </Tooltip>
        )}
      </Box>
    </Box>
  );
};

const VirtualizedVideoList: React.FC<VirtualizedVideoListProps> = ({
  videos,
  onDownloadVideo,
  onDeleteVideo
}) => {
  const height = Math.min(MAX_LIST_HEIGHT, Math.max(ITEM_HEIGHT, videos.length * ITEM_HEIGHT));

  return (
    <VirtualizedList
      rowCount={videos.length}
      rowHeight={ITEM_HEIGHT}
      rowComponent={VideoListRow}
      rowProps={{ videos, onDownloadVideo, onDeleteVideo }}
      overscanCount={4}
      style={{ height, width: '100%' }}
    />
  );
};

export default VideoArchiveTab;
