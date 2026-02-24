import React, { useCallback, useEffect, useMemo, useState } from 'react';
import {
  Alert,
  Box,
  Button,
  Card,
  CardContent,
  Chip,
  CircularProgress,
  Container,
  Divider,
  FormControl,
  InputLabel,
  List,
  ListItem,
  ListItemButton,
  ListItemIcon,
  ListItemText,
  MenuItem,
  Paper,
  Select,
  Stack,
  ToggleButton,
  ToggleButtonGroup,
  Typography,
} from '@mui/material';
import DescriptionIcon from '@mui/icons-material/Description';
import FolderIcon from '@mui/icons-material/Folder';
import InsertDriveFileIcon from '@mui/icons-material/InsertDriveFile';
import ArchiveIcon from '@mui/icons-material/Archive';
import RefreshIcon from '@mui/icons-material/Refresh';
import ArrowUpwardIcon from '@mui/icons-material/ArrowUpward';

import { useAuth } from '../context/AuthContext';
import {
  logFileApi,
  LogFileArchiveBrowseResponse,
  LogFileBrowseResponse,
  LogFileListItem,
  LogFilePreview,
  LogFileSource,
  PreviewMode,
} from '../services/logFileApi';

const MAX_PREVIEW_BYTES = 1024 * 1024;

type BrowserMode = 'filesystem' | 'archive';

const getErrorMessage = (err: any): string => {
  return (
    err?.response?.data?.message ||
    err?.response?.data?.detail ||
    err?.message ||
    'Request failed'
  );
};

const getStatusCode = (err: any): number | undefined => err?.response?.status;

const isLocalSessionFromUser = (user: any): boolean => {
  if (typeof user?.session_is_local === 'boolean') {
    return user.session_is_local;
  }
  if (typeof window === 'undefined') {
    return false;
  }
  const hostname = window.location.hostname.toLowerCase();
  return hostname === 'localhost' || hostname === '127.0.0.1' || hostname === '::1' || hostname === '0.0.0.0';
};

const parentPath = (value: string): string => {
  if (!value) {
    return '';
  }
  const parts = value.split('/').filter(Boolean);
  parts.pop();
  return parts.join('/');
};

const formatBrowseLocation = (
  selectedSource: LogFileSource | undefined,
  browserMode: BrowserMode,
  filesystemPath: string,
  archiveRelativePath: string,
  archiveEntryPath: string,
) => {
  if (!selectedSource) {
    return 'No source selected';
  }
  if (browserMode === 'filesystem') {
    return `${selectedSource.label}${filesystemPath ? ` / ${filesystemPath}` : ''}`;
  }
  return `${selectedSource.label} / ${archiveRelativePath}${archiveEntryPath ? ` :: ${archiveEntryPath}` : ' :: /'}`;
};

const LogFilePage: React.FC = () => {
  const { user } = useAuth();
  const isLocalSession = useMemo(() => isLocalSessionFromUser(user), [user]);

  const [sources, setSources] = useState<LogFileSource[]>([]);
  const [selectedSourceId, setSelectedSourceId] = useState<string>('');
  const [browserMode, setBrowserMode] = useState<BrowserMode>('filesystem');
  const [filesystemRelativePath, setFilesystemRelativePath] = useState<string>('');
  const [archiveRelativePath, setArchiveRelativePath] = useState<string>('');
  const [archiveEntryPath, setArchiveEntryPath] = useState<string>('');
  const [browseItems, setBrowseItems] = useState<LogFileListItem[]>([]);
  const [browseTotalItems, setBrowseTotalItems] = useState<number>(0);
  const [browseReturnedItems, setBrowseReturnedItems] = useState<number>(0);
  const [browseTruncated, setBrowseTruncated] = useState<boolean>(false);
  const [browseMaxItems, setBrowseMaxItems] = useState<number>(200);
  const [preview, setPreview] = useState<LogFilePreview | null>(null);
  const [selectedItemLabel, setSelectedItemLabel] = useState<string>('');

  const [previewMode, setPreviewMode] = useState<PreviewMode>('tail');
  const [loadingSources, setLoadingSources] = useState(true);
  const [browsing, setBrowsing] = useState(false);
  const [previewing, setPreviewing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [warning, setWarning] = useState<string | null>(null);

  const selectedSource = useMemo(
    () => sources.find((source) => source.id === selectedSourceId),
    [sources, selectedSourceId],
  );

  const accessibleSourceCount = useMemo(
    () =>
      sources.filter(
        (source) => source.exists && source.accessible && (source.permissions?.can_access ?? true),
      ).length,
    [sources],
  );

  const loadSources = useCallback(async () => {
    setLoadingSources(true);
    setError(null);
    setWarning(null);
    try {
      const data = await logFileApi.getSources();
      setSources(data);
      setSelectedSourceId((current) => {
        if (current && data.some((source) => source.id === current)) {
          return current;
        }
        const preferred =
          data.find(
            (source) => source.exists && source.accessible && (source.permissions?.can_access ?? true),
          ) ??
          data.find((source) => source.exists && source.accessible) ??
          data[0];
        return preferred?.id ?? '';
      });
    } catch (err: any) {
      setError(getErrorMessage(err));
    } finally {
      setLoadingSources(false);
    }
  }, []);

  const loadFilesystem = useCallback(
    async (sourceId: string, relativePath = '') => {
      if (!sourceId) {
        return;
      }
      setBrowsing(true);
      setError(null);
      setWarning(null);
      try {
        const data: LogFileBrowseResponse = await logFileApi.browse(sourceId, relativePath);
        setBrowserMode('filesystem');
        setFilesystemRelativePath(data.relative_path || '');
        setBrowseItems(data.items || []);
        setBrowseTotalItems(data.total_items || 0);
        setBrowseReturnedItems(data.returned_items ?? data.items?.length ?? 0);
        setBrowseTruncated(Boolean(data.truncated));
        setBrowseMaxItems(data.max_items ?? 200);
      } catch (err: any) {
        setBrowseItems([]);
        setBrowseTotalItems(0);
        setBrowseReturnedItems(0);
        setBrowseTruncated(false);
        if (getStatusCode(err) === 423) {
          setWarning(getErrorMessage(err));
        } else {
          setError(getErrorMessage(err));
        }
      } finally {
        setBrowsing(false);
      }
    },
    [],
  );

  const loadArchive = useCallback(
    async (sourceId: string, nextArchiveRelativePath: string, nextEntryPath = '') => {
      if (!sourceId) {
        return;
      }
      setBrowsing(true);
      setError(null);
      setWarning(null);
      try {
        const data: LogFileArchiveBrowseResponse = await logFileApi.browseArchive(
          sourceId,
          nextArchiveRelativePath,
          nextEntryPath,
        );
        setBrowserMode('archive');
        setArchiveRelativePath(data.archive.relative_path);
        setArchiveEntryPath(data.entry_path || '');
        setBrowseItems(data.items || []);
        setBrowseTotalItems(data.total_items || 0);
        setBrowseReturnedItems(data.returned_items ?? data.items?.length ?? 0);
        setBrowseTruncated(Boolean(data.truncated));
        setBrowseMaxItems(data.max_items ?? 200);
      } catch (err: any) {
        setBrowseItems([]);
        setBrowseTotalItems(0);
        setBrowseReturnedItems(0);
        setBrowseTruncated(false);
        if (getStatusCode(err) === 423) {
          setWarning(getErrorMessage(err));
        } else {
          setError(getErrorMessage(err));
        }
      } finally {
        setBrowsing(false);
      }
    },
    [],
  );

  const loadPreview = useCallback(
    async (item: LogFileListItem) => {
      if (!selectedSourceId) {
        return;
      }
      const itemRelativePath =
        browserMode === 'archive' ? item.entry_path || '' : [...(filesystemRelativePath ? [filesystemRelativePath] : []), item.name].join('/');

      setPreviewing(true);
      setError(null);
      setWarning(null);
      setSelectedItemLabel(item.name);
      try {
        const data =
          browserMode === 'archive'
            ? await logFileApi.previewArchive(selectedSourceId, archiveRelativePath, itemRelativePath, previewMode, MAX_PREVIEW_BYTES)
            : await logFileApi.preview(selectedSourceId, itemRelativePath, previewMode, MAX_PREVIEW_BYTES);
        setPreview(data);
      } catch (err: any) {
        setPreview(null);
        if (getStatusCode(err) === 423) {
          setWarning(getErrorMessage(err));
        } else {
          setError(getErrorMessage(err));
        }
      } finally {
        setPreviewing(false);
      }
    },
    [archiveRelativePath, browserMode, filesystemRelativePath, previewMode, selectedSourceId],
  );

  const refreshCurrentView = useCallback(async () => {
    if (!selectedSourceId) {
      return;
    }
    if (browserMode === 'archive') {
      await loadArchive(selectedSourceId, archiveRelativePath, archiveEntryPath);
      return;
    }
    await loadFilesystem(selectedSourceId, filesystemRelativePath);
  }, [
    archiveEntryPath,
    archiveRelativePath,
    browserMode,
    filesystemRelativePath,
    loadArchive,
    loadFilesystem,
    selectedSourceId,
  ]);

  const handleItemClick = useCallback(
    async (item: LogFileListItem) => {
      if (item.is_directory) {
        if (browserMode === 'archive') {
          await loadArchive(selectedSourceId, archiveRelativePath, item.entry_path || '');
          return;
        }
        const nextRelativePath = [filesystemRelativePath, item.name].filter(Boolean).join('/');
        await loadFilesystem(selectedSourceId, nextRelativePath);
        return;
      }

      if (browserMode === 'filesystem' && item.extension?.toLowerCase() === '.zip') {
        const nextArchivePath = [filesystemRelativePath, item.name].filter(Boolean).join('/');
        setPreview(null);
        await loadArchive(selectedSourceId, nextArchivePath, '');
        return;
      }

      await loadPreview(item);
    },
    [
      archiveRelativePath,
      browserMode,
      filesystemRelativePath,
      loadArchive,
      loadFilesystem,
      loadPreview,
      selectedSourceId,
    ],
  );

  const handleUp = useCallback(async () => {
    if (!selectedSourceId) {
      return;
    }
    if (browserMode === 'archive') {
      if (archiveEntryPath) {
        await loadArchive(selectedSourceId, archiveRelativePath, parentPath(archiveEntryPath));
      } else {
        setBrowserMode('filesystem');
        setArchiveRelativePath('');
        setArchiveEntryPath('');
        await loadFilesystem(selectedSourceId, filesystemRelativePath);
      }
      return;
    }

    if (!filesystemRelativePath) {
      return;
    }
    await loadFilesystem(selectedSourceId, parentPath(filesystemRelativePath));
  }, [
    archiveEntryPath,
    archiveRelativePath,
    browserMode,
    filesystemRelativePath,
    loadArchive,
    loadFilesystem,
    selectedSourceId,
  ]);

  useEffect(() => {
    loadSources();
  }, [loadSources]);

  useEffect(() => {
    if (!selectedSourceId) {
      return;
    }
    setPreview(null);
    setSelectedItemLabel('');
    setArchiveRelativePath('');
    setArchiveEntryPath('');
    setFilesystemRelativePath('');
    loadFilesystem(selectedSourceId, '');
  }, [loadFilesystem, selectedSourceId]);

  useEffect(() => {
    if (!preview || !selectedItemLabel) {
      return;
    }
    const maybeSelected = browseItems.find((item) => !item.is_directory && item.name === selectedItemLabel);
    if (maybeSelected) {
      void loadPreview(maybeSelected);
    }
    // previewMode changes should refresh preview for current selected item
  }, [previewMode]); // eslint-disable-line react-hooks/exhaustive-deps

  const locationLabel = formatBrowseLocation(
    selectedSource,
    browserMode,
    filesystemRelativePath,
    archiveRelativePath,
    archiveEntryPath,
  );

  return (
    <Container maxWidth="xl" sx={{ py: { xs: 2, md: 3 } }}>
      <Box sx={{ mb: 3 }}>
        <Stack direction="row" spacing={1} alignItems="center" sx={{ mb: 1 }}>
          <DescriptionIcon color="primary" />
          <Typography variant="h4" sx={{ fontWeight: 700 }}>
            LogFile
          </Typography>
        </Stack>
        <Typography variant="body2" color="text.secondary">
          Read-only log file browser and previewer (plain text, .gz history, and .zip archives).
        </Typography>
      </Box>

      <Stack spacing={2}>
          {!isLocalSession && (
            <Alert severity="info">
              Remote session: Python Log and Hamilton LogFiles are available. RobotControl Logs is local-only.
            </Alert>
          )}
          {error && <Alert severity="error">{error}</Alert>}
          {warning && <Alert severity="warning">{warning}</Alert>}

          <Card>
            <CardContent>
              {loadingSources ? (
                <Box sx={{ py: 3, display: 'flex', justifyContent: 'center' }}>
                  <CircularProgress size={28} />
                </Box>
              ) : (
                <Stack spacing={2}>
                  <Stack
                    direction={{ xs: 'column', md: 'row' }}
                    spacing={2}
                    alignItems={{ xs: 'stretch', md: 'center' }}
                  >
                    <FormControl size="small" sx={{ minWidth: { xs: '100%', md: 420 } }}>
                      <InputLabel id="logfile-source-label">Log Source</InputLabel>
                      <Select
                        labelId="logfile-source-label"
                        value={selectedSourceId}
                        label="Log Source"
                        onChange={(event) => setSelectedSourceId(event.target.value)}
                      >
                        {sources.map((source) => {
                          const canAccess = source.permissions?.can_access ?? true;
                          const existsAndAccessible = source.exists && source.accessible;
                          const disabled = !existsAndAccessible || !canAccess;
                          const availabilityLabel = !existsAndAccessible
                            ? 'unavailable'
                            : !canAccess
                              ? 'local only'
                              : 'available';

                          return (
                            <MenuItem key={source.id} value={source.id} disabled={disabled}>
                              {source.label} ({availabilityLabel})
                            </MenuItem>
                          );
                        })}
                      </Select>
                    </FormControl>

                    <ToggleButtonGroup
                      size="small"
                      exclusive
                      value={previewMode}
                      onChange={(_event, value) => {
                        if (value) {
                          setPreviewMode(value as PreviewMode);
                        }
                      }}
                      aria-label="preview mode"
                    >
                      <ToggleButton value="tail">Tail</ToggleButton>
                      <ToggleButton value="head">Head</ToggleButton>
                    </ToggleButtonGroup>

                    <Button
                      variant="outlined"
                      startIcon={<ArrowUpwardIcon />}
                      onClick={handleUp}
                      disabled={browsing || (browserMode === 'filesystem' ? !filesystemRelativePath : false)}
                    >
                      Up
                    </Button>

                    <Button
                      variant="outlined"
                      startIcon={<RefreshIcon />}
                      onClick={() => void refreshCurrentView()}
                      disabled={browsing || !selectedSourceId}
                    >
                      Refresh
                    </Button>
                  </Stack>

                  <Stack direction="row" spacing={1} useFlexGap flexWrap="wrap">
                    <Chip
                      size="small"
                      label={`Mode: ${browserMode === 'archive' ? 'ZIP Archive' : 'Filesystem'}`}
                      color={browserMode === 'archive' ? 'warning' : 'primary'}
                      variant="outlined"
                    />
                    <Chip
                      size="small"
                      label={`Sources available: ${accessibleSourceCount}/${sources.length}${isLocalSession ? '' : ' (remote-filtered)'}`}
                      variant="outlined"
                    />
                    <Chip size="small" label={`Preview: ${previewMode.toUpperCase()} ${MAX_PREVIEW_BYTES / 1024} KB`} variant="outlined" />
                    <Chip
                      size="small"
                      label={
                        browseTruncated
                          ? `Showing ${browseReturnedItems}/${browseTotalItems} items (max ${browseMaxItems})`
                          : `Items: ${browseTotalItems}`
                      }
                      color={browseTruncated ? 'warning' : 'default'}
                      variant="outlined"
                    />
                  </Stack>

                  <Typography variant="body2" color="text.secondary">
                    {locationLabel}
                  </Typography>
                </Stack>
              )}
            </CardContent>
          </Card>

          <Stack direction={{ xs: 'column', lg: 'row' }} spacing={2} alignItems="stretch">
            <Card sx={{ flex: { lg: '0 0 42%' } }}>
              <CardContent>
                <Stack spacing={1.5}>
                  <Typography variant="h6">
                    {browserMode === 'archive' ? 'Archive Entries' : 'Files'}
                  </Typography>
                  <Divider />
                  {browseTruncated && (
                    <Alert severity="info">
                      This folder contains many items. Showing the first {browseReturnedItems} items (max {browseMaxItems})
                      with folders first and files sorted by newest modified time.
                    </Alert>
                  )}
                  {browsing ? (
                    <Box sx={{ py: 6, display: 'flex', justifyContent: 'center' }}>
                      <CircularProgress size={28} />
                    </Box>
                  ) : (
                    <Paper variant="outlined" sx={{ maxHeight: 560, overflow: 'auto' }}>
                      <List dense disablePadding>
                        {browseItems.length === 0 ? (
                          <ListItem>
                            <ListItemText
                              primary="No items found"
                              secondary={
                                browserMode === 'archive'
                                  ? 'No entries in this archive folder'
                                  : 'This folder is empty or unavailable'
                              }
                            />
                          </ListItem>
                        ) : (
                          browseItems.map((item) => {
                            const isSelected =
                              preview?.display_name === item.name &&
                              (!item.is_directory) &&
                              (browserMode === 'archive'
                                ? preview?.entry_path === item.entry_path
                                : preview?.file_path?.toLowerCase().endsWith(`\\${item.name}`.toLowerCase()) ||
                                  preview?.file_path?.toLowerCase().endsWith(`/${item.name}`.toLowerCase()));

                            const icon = item.is_directory ? (
                              <FolderIcon color="primary" />
                            ) : item.extension?.toLowerCase() === '.zip' ? (
                              <ArchiveIcon color="warning" />
                            ) : item.extension?.toLowerCase() === '.gz' ? (
                              <ArchiveIcon color="secondary" />
                            ) : (
                              <InsertDriveFileIcon color="action" />
                            );

                            return (
                              <ListItem key={`${item.is_directory ? 'dir' : 'file'}:${item.entry_path || item.path || item.name}`} disablePadding>
                                <ListItemButton onClick={() => void handleItemClick(item)} selected={isSelected}>
                                  <ListItemIcon>{icon}</ListItemIcon>
                                  <ListItemText
                                    primary={item.name}
                                    secondary={
                                      item.is_directory
                                        ? (browserMode === 'archive' ? 'Archive folder' : 'Directory')
                                        : [item.size_formatted, item.modified_date].filter(Boolean).join(' • ')
                                    }
                                  />
                                  {!item.is_directory && item.is_archive && (
                                    <Chip
                                      label={(item.archive_type || 'archive').toUpperCase()}
                                      size="small"
                                      color={item.archive_type === 'zip' ? 'warning' : 'secondary'}
                                      variant="outlined"
                                    />
                                  )}
                                </ListItemButton>
                              </ListItem>
                            );
                          })
                        )}
                      </List>
                    </Paper>
                  )}
                </Stack>
              </CardContent>
            </Card>

            <Card sx={{ flex: 1 }}>
              <CardContent>
                <Stack spacing={1.5}>
                  <Stack
                    direction={{ xs: 'column', sm: 'row' }}
                    justifyContent="space-between"
                    alignItems={{ xs: 'flex-start', sm: 'center' }}
                    spacing={1}
                  >
                    <Typography variant="h6">Preview</Typography>
                    {preview && (
                      <Stack direction="row" spacing={1} useFlexGap flexWrap="wrap">
                        {preview.archive_type && (
                          <Chip size="small" label={preview.archive_type.toUpperCase()} variant="outlined" />
                        )}
                        <Chip size="small" label={`Encoding: ${preview.encoding_used || 'n/a'}`} variant="outlined" />
                        <Chip size="small" label={preview.truncated ? 'Truncated' : 'Complete'} color={preview.truncated ? 'warning' : 'success'} />
                      </Stack>
                    )}
                  </Stack>
                  <Divider />

                  {previewing ? (
                    <Box sx={{ py: 6, display: 'flex', justifyContent: 'center' }}>
                      <CircularProgress size={28} />
                    </Box>
                  ) : !preview ? (
                    <Alert severity="info">
                      Select a file to preview. `.zip` files open as archive folders. `.gz` files are previewed directly.
                    </Alert>
                  ) : preview.is_binary ? (
                    <Alert severity="warning">
                      This file appears to be binary or non-text. Preview is not supported.
                    </Alert>
                  ) : (
                    <>
                      <Stack direction="row" spacing={1} useFlexGap flexWrap="wrap">
                        <Chip size="small" label={preview.display_name} />
                        <Chip size="small" label={`Scanned: ${Math.round(preview.bytes_scanned / 1024)} KB`} variant="outlined" />
                        <Chip size="small" label={`Returned: ${Math.round(preview.bytes_returned / 1024)} KB`} variant="outlined" />
                        {preview.file_size_formatted && <Chip size="small" label={`File: ${preview.file_size_formatted}`} variant="outlined" />}
                        {preview.entry_size_formatted && <Chip size="small" label={`Entry: ${preview.entry_size_formatted}`} variant="outlined" />}
                      </Stack>

                      {preview.modified_date && (
                        <Typography variant="caption" color="text.secondary">
                          Modified: {preview.modified_date}
                        </Typography>
                      )}

                      <Paper
                        variant="outlined"
                        sx={{
                          maxHeight: 560,
                          overflow: 'auto',
                          bgcolor: '#111',
                          color: '#d9f2d9',
                          p: 1.5,
                        }}
                      >
                        <Box
                          component="pre"
                          sx={{
                            m: 0,
                            whiteSpace: 'pre-wrap',
                            wordBreak: 'break-word',
                            fontFamily: 'Consolas, Monaco, monospace',
                            fontSize: '0.8rem',
                            lineHeight: 1.4,
                          }}
                        >
                          {preview.content || '(empty file)'}
                        </Box>
                      </Paper>

                      <Typography variant="caption" color="text.secondary">
                        {preview.truncated
                          ? `Showing ${preview.mode.toUpperCase()} preview only (max ${MAX_PREVIEW_BYTES / 1024} KB).`
                          : `Showing full preview (${preview.mode.toUpperCase()} mode requested).`}
                      </Typography>
                    </>
                  )}
                </Stack>
              </CardContent>
            </Card>
          </Stack>
      </Stack>
    </Container>
  );
};

export default LogFilePage;
