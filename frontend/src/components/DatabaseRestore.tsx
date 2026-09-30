import React, { useState, useEffect, useRef } from 'react';
import {
  Box,
  Card,
  CardContent,
  Typography,
  Button,
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  Stack,
  FormControl,
  InputLabel,
  Select,
  MenuItem,
  Checkbox,
  FormControlLabel,
  Divider,
  Alert,
  CircularProgress,
  TextField,
  Tab,
  Tabs,
  Paper,
  List,
  ListItem,
  ListItemButton,
  ListItemText,
  ListItemIcon,
  IconButton,
  Collapse
} from '@mui/material';
import StatusChip from './StatusChip';
import useTheme from '@mui/material/styles/useTheme';
import useMediaQuery from '@mui/material/useMediaQuery';
import {
  Restore as RestoreIcon,
  Upload as UploadIcon,
  Warning as WarningIcon,
  Storage as StorageIcon,
  Refresh as RefreshIcon,
  Folder as FolderIcon,
  InsertDriveFile as FileIcon,
  Computer as ComputerIcon,
  ExpandMore as ExpandMoreIcon,
  ExpandLess as ExpandLessIcon
} from '@mui/icons-material';
import LoadingSpinner from './LoadingSpinner';
import { api } from '../services/api';
import { activateMaintenance, clearMaintenance } from '@/utils/MaintenanceManager';
import StatusDialog, { StatusMessage } from './StatusDialog';
import { useAuthContext } from '../context/AuthContext';

interface BackupFile {
  filename: string;
  file_path?: string;
  file_size: number;
  file_size_formatted: string;
  created_date: string;
  description?: string;
  is_valid: boolean;
  database_name?: string;
  sql_server?: string;
  timestamp?: string;
}

interface FileSystemItem {
  name: string;
  path: string;
  is_directory: boolean;
  size?: number;
  size_formatted?: string;
  modified_date?: string;
  is_backup_file?: boolean;
}

interface FileExplorerProps {
  open: boolean;
  onClose: () => void;
  onSelect: (filePath: string) => void;
}

interface DatabaseRestoreProps {
  onError?: (error: string) => void;
}

// The backend restore allows 600 s; include a minute for response/recovery overhead.
const RESTORE_REQUEST_TIMEOUT_MS = (600 + 60) * 1000;

const FileExplorer: React.FC<FileExplorerProps> = ({ open, onClose, onSelect }) => {
  const [currentPath, setCurrentPath] = useState('C:\\');
  const [pathInput, setPathInput] = useState(currentPath);
  const requestRef = useRef(0);
  const [browseError, setBrowseError] = useState<string | null>(null);
  const [items, setItems] = useState<FileSystemItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [selectedFile, setSelectedFile] = useState<FileSystemItem | null>(null);
  const theme = useTheme();
  const fullScreen = useMediaQuery(theme.breakpoints.down('sm'));

  useEffect(() => {
    if (open) void loadDirectory(currentPath);
    return () => { requestRef.current += 1; };
  }, [open]);

  const loadDirectory = async (path: string) => {
    const normalizedPath = /^[a-z]:$/i.test(path.trim()) ? `${path.trim()}\\` : path.trim();
    const request = ++requestRef.current;
    setCurrentPath(normalizedPath);
    setPathInput(normalizedPath);
    setSelectedFile(null);
    setBrowseError(null);
    setLoading(true);
    try {
      const response = await api.get('/api/system/browse', {
        params: { path: normalizedPath, filter: '.bck' }
      });
      if (request !== requestRef.current) return;
      // The server's resolved path keeps Parent Directory correct for typed "/" or ".." paths.
      const resolvedPath = response.data.data.current_path || normalizedPath;
      setCurrentPath(resolvedPath);
      // Keep a newer draft typed while this directory was loading.
      setPathInput(draft => draft === normalizedPath ? resolvedPath : draft);
      setItems(response.data.data.items || []);
    } catch (err: any) {
      if (request !== requestRef.current) return;
      // /api/system/browse answers with ResponseFormatter's error body; auth failures use FastAPI's `detail`.
      const body = err.response?.data;
      const details = typeof body?.error?.details === 'string' ? body.error.details : undefined;
      setBrowseError(details || body?.message || body?.detail
        || 'Could not load this directory. Check the path and try again.');
      setItems([]);
    } finally {
      if (request === requestRef.current) setLoading(false);
    }
  };

  const navigateToParent = () => {
    const path = currentPath.replace(/[\\/]+$/, '');
    const separator = Math.max(path.lastIndexOf('\\'), path.lastIndexOf('/'));
    if (separator < 0) return;
    const parent = path.slice(0, separator);
    void loadDirectory(/^[a-z]:$/i.test(parent) ? `${parent}\\` : parent || currentPath);
  };

  const handleItemClick = (item: FileSystemItem) => {
    if (item.is_directory) {
      void loadDirectory(item.path);
    } else if (item.name.toLowerCase().endsWith('.bck')) {
      setSelectedFile(item);
    }
  };

  const handleSelect = () => {
    if (selectedFile) {
      onSelect(selectedFile.path);
      onClose();
    }
  };

  return (
    <Dialog open={open} onClose={onClose} maxWidth="md" fullWidth fullScreen={fullScreen}>
      <DialogTitle>
        <Stack direction="row" alignItems="center" spacing={1}>
          <ComputerIcon />
          <Typography variant="h6">Browse for .bck Backup Files</Typography>
        </Stack>
      </DialogTitle>
      <DialogContent>
        <Stack spacing={2} sx={{ pt: 1 }}>
          <TextField
            label="Current Directory"
            value={pathInput}
            onChange={(e) => setPathInput(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && void loadDirectory(pathInput)}
            helperText="Press Enter or Go to open a directory"
            fullWidth
            size="small"
          />

          <Stack direction="row" spacing={1}>
            <Button size="small" onClick={() => void loadDirectory(pathInput)}>Go</Button>
            <Button
              size="small"
              startIcon={<FolderIcon />}
              onClick={navigateToParent}
              disabled={/^[a-z]:\\$/i.test(currentPath)}
            >
              Parent Directory
            </Button>
            <Button
              size="small"
              startIcon={<RefreshIcon />}
              onClick={() => loadDirectory(currentPath)}
              disabled={loading}
            >
              Refresh
            </Button>
          </Stack>

          {browseError && <Alert severity="error">{browseError}</Alert>}
          {loading ? (
            <LoadingSpinner message="Loading backup files..." minHeight={200} />
          ) : (
            <Paper sx={{ maxHeight: 400, overflow: 'auto' }}>
              <List dense>
                {items.length === 0 ? (
                  <ListItem>
                    <ListItemText 
                      primary="No items found"
                      secondary="No directories or .bck files in this location" 
                    />
                  </ListItem>
                ) : (
                  items.map((item, index) => (
                    <ListItem key={index} disablePadding>
                      <ListItemButton
                        onClick={() => handleItemClick(item)}
                        selected={selectedFile?.path === item.path}
                        disabled={!item.is_directory && !item.name.toLowerCase().endsWith('.bck')}
                      >
                        <ListItemIcon>
                          {item.is_directory ? (
                            <FolderIcon color="primary" />
                          ) : item.name.toLowerCase().endsWith('.bck') ? (
                            <FileIcon color="secondary" />
                          ) : (
                            <FileIcon sx={{ opacity: 0.5 }} />
                          )}
                        </ListItemIcon>
                        <ListItemText
                          primary={item.name}
                          secondary={
                            item.is_directory 
                              ? 'Directory' 
                              : `${item.size_formatted || ''} ${item.modified_date ? `•${item.modified_date}` : ''}`
                          }
                        />
                        {item.name.toLowerCase().endsWith('.bck') && (
                          <StatusChip tone="neutral" label="BCK" />
                        )}
                      </ListItemButton>
                    </ListItem>
                  ))
                )}
              </List>
            </Paper>
          )}

          {selectedFile && (
            <Alert severity="info" sx={{ whiteSpace: 'pre-line', overflowWrap: 'anywhere' }}>
              {`Selected: ${selectedFile.name}\nPath: ${selectedFile.path}\nSize: ${selectedFile.size_formatted || 'Unknown'}`}
            </Alert>
          )}
        </Stack>
      </DialogContent>
      <DialogActions
        sx={{
          px: { xs: 2, sm: 3 },
          py: { xs: 2, sm: 2 },
          flexWrap: 'wrap',
          gap: 1,
          justifyContent: fullScreen ? 'flex-start' : 'flex-end'
        }}
      >
        <Button
          onClick={onClose}
          sx={{ flex: { xs: '1 1 100%', sm: '0 0 auto' } }}
        >
          Cancel
        </Button>
        <Button
          onClick={handleSelect}
          variant="contained"
          disabled={!selectedFile}
          startIcon={<FileIcon />}
          sx={{ flex: { xs: '1 1 100%', sm: '0 0 auto' } }}
        >
          Select File
        </Button>
      </DialogActions>
    </Dialog>
  );
};

const DatabaseRestore: React.FC<DatabaseRestoreProps> = ({ onError }) => {
  const { user } = useAuthContext();
  const isLocalSession = React.useMemo(() => {
    if (typeof user?.session_is_local === 'boolean') {
      return user.session_is_local;
    }
    if (typeof window !== 'undefined') {
      const hostname = window.location.hostname.toLowerCase();
      return (
        hostname === 'localhost' ||
        hostname === '127.0.0.1' ||
        hostname === '::1' ||
        hostname === '0.0.0.0'
      );
    }
    return false;
  }, [user?.session_is_local]);
  const hasBackupAccess = Boolean(
    user && (user.role === 'admin' || isLocalSession)
  );

  const [activeTab, setActiveTab] = useState(0); // 0 = .bak files, 1 = .bck browser
  const [backupFiles, setBackupFiles] = useState<BackupFile[]>([]);
  const [selectedBackup, setSelectedBackup] = useState<BackupFile | null>(null);
  const [selectedBckPath, setSelectedBckPath] = useState<string>('');
  const [loading, setLoading] = useState(false);
  const [restoreDialogOpen, setRestoreDialogOpen] = useState(false);
  const [fileExplorerOpen, setFileExplorerOpen] = useState(false);
  const [restoreProgress, setRestoreProgress] = useState(false);
  const [expandedMetadata, setExpandedMetadata] = useState(false);
  const [confirmationChecks, setConfirmationChecks] = useState({
    dataLoss: false,
    downtime: false
  });
  const [createDialogOpen, setCreateDialogOpen] = useState(false);
  const [creatingBackup, setCreatingBackup] = useState(false);
  const [createDescription, setCreateDescription] = useState('');
  const [createDialogError, setCreateDialogError] = useState<string | null>(null);
  const [status, setStatus] = useState<StatusMessage | null>(null);
  const theme = useTheme();
  const isSmallScreen = useMediaQuery(theme.breakpoints.down('sm'));

  const maintenancePollRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const maintenancePollAttemptsRef = useRef(0);

  const clearMaintenancePoll = () => {
    if (maintenancePollRef.current) {
      clearTimeout(maintenancePollRef.current);
      maintenancePollRef.current = null;
    }
  };

  const scheduleMaintenanceRecoveryCheck = (delayMs = 5000) => {
    clearMaintenancePoll();
    maintenancePollRef.current = setTimeout(async () => {
      maintenancePollAttemptsRef.current += 1;
      try {
        await api.get('/health', {
          headers: { 'X-Allow-Maintenance': 'true' },
        });
        clearMaintenance();
        maintenancePollAttemptsRef.current = 0;
        clearMaintenancePoll();
      } catch {
        if (maintenancePollAttemptsRef.current < 12) {
          scheduleMaintenanceRecoveryCheck(5000);
        } else {
          maintenancePollAttemptsRef.current = 0;
          clearMaintenancePoll();
        }
      }
    }, delayMs);
  };

  const startMaintenanceRecoveryWatcher = () => {
    maintenancePollAttemptsRef.current = 0;
    scheduleMaintenanceRecoveryCheck(5000);
  };

  useEffect(() => {
    if (!hasBackupAccess) {
      setLoading(false);
      setBackupFiles([]);
      setSelectedBackup(null);
      return;
    }
    loadBackupFiles();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [hasBackupAccess]);

  useEffect(() => {
    return () => {
      clearMaintenancePoll();
    };
  }, []);

  const loadBackupFiles = async (): Promise<BackupFile[]> => {
    if (!hasBackupAccess) {
      setLoading(false);
      return [];
    }
    setLoading(true);
    try {
      const response = await api.get('/api/admin/backup/list');
      
      // Backend returns { success, data: [...backup files...], message }
      const files = response.data.data || [];
      const managedBackups = files.filter((f: any) => f.filename.endsWith('.bak'));
      setBackupFiles(managedBackups);
      return managedBackups;
    } catch (err: any) {
      console.error('Error loading backup files:', err);
      if (onError) {
        onError(err.response?.data?.detail || 'Failed to load backup files');
      }
      return [];
    } finally {
      setLoading(false);
    }
  };

  const formatDate = (dateString: string): string => {
    try {
      return new Date(dateString).toLocaleString();
    } catch {
      return dateString;
    }
  };

  const getFileType = (filename: string): 'bak' | 'bck' => {
    return filename.toLowerCase().endsWith('.bck') ? 'bck' : 'bak';
  };

  const handleTabChange = (_: React.SyntheticEvent, newValue: number) => {
    setActiveTab(newValue);
    // Reset selections when switching tabs
    setSelectedBackup(null);
    setSelectedBckPath('');
  };

  const handleBackupSelect = (filename: string) => {
    const backup = backupFiles.find(f => f.filename === filename);
    setSelectedBackup(backup || null);
  };

  const handleBckFileSelected = (filePath: string) => {
    setSelectedBckPath(filePath);
  };

  const canProceed = confirmationChecks.dataLoss && confirmationChecks.downtime;
  const hasSelection = (activeTab === 0 && selectedBackup) || (activeTab === 1 && selectedBckPath);

  const handleRestoreBackup = async () => {
    if (!hasBackupAccess) {
      setStatus({ title: 'Access Restricted', message: 'Only administrators or trusted lab machines can restore backups.', severity: 'warning', autoCloseMs: 5000 });
      return;
    }
    if (!canProceed || !hasSelection) return;
    
    const restoreRequest = activeTab === 0 && selectedBackup 
      ? { filename: selectedBackup.filename } 
      : { file_path: selectedBckPath };

    setRestoreProgress(true);
    try {
      const response = await api.post('/api/admin/backup/restore', restoreRequest, { timeout: RESTORE_REQUEST_TIMEOUT_MS });

      // A failed restore still answers HTTP 200, with { success: false, message, data.error_details }.
      if (!response.data?.success) {
        const details = response.data?.data?.error_details;
        const message = [response.data?.message || 'Failed to restore backup', details,
          ...(response.data?.data?.warnings || [])]
          .filter(Boolean)
          .join('\n\n');
        setStatus({ title: 'Restore Failed', message, severity: 'error' });
        return;
      }

      activateMaintenance(60000, 'Database restore is finishing.');
      startMaintenanceRecoveryWatcher();
      const warnings: string[] = response.data?.data?.warnings || [];
      setStatus({
        title: warnings.length ? 'Restore Completed with Warnings' : 'Restore Completed',
        message: [response.data.message || 'Database restored successfully.', ...warnings,
          'Services may take a moment to reconnect.'].join('\n\n'),
        severity: warnings.length ? 'warning' : 'success',
      });

      // Success - close dialog and refresh
      setRestoreDialogOpen(false);
      setSelectedBackup(null);
      setSelectedBckPath('');
      setConfirmationChecks({ dataLoss: false, downtime: false });

    } catch (err: any) {
      console.error('Error restoring backup:', err);
      const message = err.response?.data?.detail || err.message || 'Failed to restore backup';
      setStatus({ title: 'Restore Failed', message, severity: 'error' });
    } finally {
      setRestoreProgress(false);
    }
  };

  const getCurrentSelection = () => {
    if (activeTab === 0 && selectedBackup) {
      return {
        filename: selectedBackup.filename,
        type: getFileType(selectedBackup.filename),
        size: selectedBackup.file_size_formatted,
        created: selectedBackup.created_date,
        description: selectedBackup.description,
        hasMetadata: true,
        database: selectedBackup.database_name,
        server: selectedBackup.sql_server
      };
    }
    
    if (activeTab === 1 && selectedBckPath) {
      return {
        filename: selectedBckPath.split('\\').pop() || selectedBckPath,
        path: selectedBckPath,
        type: 'bck' as const,
        size: 'Unknown',
        created: 'Unknown',
        hasMetadata: false
      };
    }
    
    return null;
  };

  const currentSelection = getCurrentSelection();

  const handleOpenCreateDialog = () => {
    setCreateDialogError(null);
    setCreateDescription('');
    setCreateDialogOpen(true);
  };

  const handleCreateBackup = async () => {
    if (!hasBackupAccess) {
      setStatus({ title: 'Access Restricted', message: 'Only administrators or trusted lab machines can create or manage backups.', severity: 'warning', autoCloseMs: 5000 });
      return;
    }
    if (!createDescription.trim()) {
      setCreateDialogError('Please provide a brief description for the backup.');
      return;
    }

    setCreateDialogError(null);
    setCreatingBackup(true);

    try {
      const response = await api.post('/api/admin/backup/create', {
        description: createDescription.trim()
      });

      const message = response?.data?.message || 'Backup created successfully.';
      const filename = response?.data?.data?.filename;

      setCreateDialogError(null);
      setCreateDialogOpen(false);
      setCreateDescription('');
      setStatus({ title: 'Backup Created', message, severity: 'success' });

      const updatedBackups = await loadBackupFiles();
      if (filename) {
        const created = updatedBackups.find((backup) => backup.filename === filename);
        if (created) {
          setSelectedBackup(created);
          setActiveTab(0);
        }
      }
    } catch (err: any) {
      const message = err?.response?.data?.detail || err?.message || 'Failed to create backup.';
      setCreateDialogError(message);
    } finally {
      setCreatingBackup(false);
    }
  };

  return (
    <Card>
      <CardContent>
        <Stack spacing={3}>
          <Typography variant="h6" gutterBottom>
            Database Restore
          </Typography>


          {/* Tab Navigation */}
          <Paper sx={{ borderBottom: 1, borderColor: 'divider' }}>
            <Tabs
              value={activeTab}
              onChange={handleTabChange}
              aria-label="restore tabs"
              variant={isSmallScreen ? 'scrollable' : 'standard'}
              scrollButtons="auto"
              allowScrollButtonsMobile
            >
              <Tab 
                icon={<StorageIcon />} 
                label={isSmallScreen ? 'Managed (.bak)' : 'Managed Backups (.bak)'} 
                iconPosition="start" 
              />
              <Tab 
                icon={<ComputerIcon />} 
                label={isSmallScreen ? 'Browse (.bck)' : 'Browse Files (.bck)'} 
                iconPosition="start" 
              />
            </Tabs>
          </Paper>

          {/* Tab 0: Managed .bak files */}
          {activeTab === 0 && (
            <Stack spacing={2}>
              <Typography variant="body2" color="textSecondary">
                Select from managed backup files with metadata and descriptions.
              </Typography>

              <FormControl fullWidth size="small">
                <InputLabel>Select Backup File</InputLabel>
                <Select
                  value={selectedBackup?.filename || ''}
                  onChange={(e) => handleBackupSelect(e.target.value)}
                  label="Select Backup File"
                  disabled={loading}
                >
                  <MenuItem value="">
                    <em>Choose a backup file...</em>
                  </MenuItem>
                  {backupFiles.map((backup) => (
                    <MenuItem key={backup.filename} value={backup.filename}>
                      <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, width: '100%' }}>
                        <StorageIcon fontSize="small" color="primary" />
                        <Box sx={{ flex: 1 }}>
                          <Typography variant="body2">
                            {backup.filename}
                          </Typography>
                          <Typography variant="caption" color="textSecondary">
                            {backup.file_size_formatted} •{formatDate(backup.created_date)}
                          </Typography>
                          {backup.description && (
                            <Typography variant="caption" display="block" sx={{ fontStyle: 'italic' }}>
                              {backup.description}
                            </Typography>
                          )}
                        </Box>
                        <Stack direction="row" spacing={0.5}>
                          <StatusChip tone="neutral" label="BAK" />
                          {!backup.is_valid && (
                            <StatusChip tone="fault" label="Invalid" />
                          )}
                        </Stack>
                      </Box>
                    </MenuItem>
                  ))}
                </Select>
              </FormControl>

              {/* Metadata Details for Selected BAK */}
              {selectedBackup && (
                <Card variant="outlined" sx={{ bgcolor: 'background.default' }}>
                  <CardContent sx={{ pb: 1 }}>
                    <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: 1, mb: 1 }}>
                      <Typography variant="subtitle2">
                        Backup Metadata
                      </Typography>
                      <IconButton 
                        size="small" 
                        onClick={() => setExpandedMetadata(!expandedMetadata)}
                      >
                        {expandedMetadata ? <ExpandLessIcon /> : <ExpandMoreIcon />}
                      </IconButton>
                    </Box>
                    
                    <Stack spacing={1}>
                      <Stack
                        direction={{ xs: 'column', sm: 'row' }}
                        spacing={0.5}
                        justifyContent="space-between"
                        alignItems={{ xs: 'flex-start', sm: 'center' }}
                      >
                        <Typography variant="body2" color="textSecondary">Status:</Typography>
                        <StatusChip tone={selectedBackup.is_valid ? 'completed' : 'fault'} label={selectedBackup.is_valid ? 'Valid' : 'Invalid'} />
                      </Stack>
                      
                      {selectedBackup.description && (
                        <Stack spacing={0.5}>
                          <Typography variant="body2" color="textSecondary" gutterBottom>Description:</Typography>
                          <Typography variant="body2" sx={{ fontStyle: 'italic', pl: 1, borderLeft: 2, borderColor: 'divider' }}>
                            {selectedBackup.description}
                          </Typography>
                        </Stack>
                      )}
                    </Stack>

                    <Collapse in={expandedMetadata}>
                      <Divider sx={{ my: 1 }} />
                      <Stack spacing={1}>
                        <Box sx={{ display: 'flex', justifyContent: 'space-between', flexWrap: 'wrap', gap: 0.75 }}>
                          <Typography variant="body2" color="textSecondary">Database:</Typography>
                          <Typography variant="body2">{selectedBackup.database_name || 'Unknown'}</Typography>
                        </Box>
                        <Box sx={{ display: 'flex', justifyContent: 'space-between', flexWrap: 'wrap', gap: 0.75 }}>
                          <Typography variant="body2" color="textSecondary">Server:</Typography>
                          <Typography variant="body2">{selectedBackup.sql_server || 'Unknown'}</Typography>
                        </Box>
                        <Box sx={{ display: 'flex', justifyContent: 'space-between', flexWrap: 'wrap', gap: 0.75 }}>
                          <Typography variant="body2" color="textSecondary">Timestamp:</Typography>
                          <Typography variant="body2">{selectedBackup.timestamp || 'Unknown'}</Typography>
                        </Box>
                      </Stack>
                    </Collapse>
                  </CardContent>
                </Card>
              )}

              <Box sx={{ display: 'flex', gap: 2 }}>
                <Button
                  variant="outlined"
                  startIcon={loading ? <CircularProgress size={20} /> : <RefreshIcon />}
                  onClick={loadBackupFiles}
                  disabled={loading || restoreProgress}
                >
                  Refresh List
                </Button>
              </Box>

              {backupFiles.length === 0 && !loading && (
                <Alert severity="info">
                  No managed backup files found. Create backups using the backup manager or switch to browse mode for .bck files.
                </Alert>
              )}
            </Stack>
          )}

          {/* Tab 1: File browser for .bck files */}
          {activeTab === 1 && (
            <Stack spacing={2}>
              <Typography variant="body2" color="textSecondary">
                Browse your file system to select .bck backup files generated automatically by the machine.
                These files don't have metadata but can still be restored.
              </Typography>

              <Box sx={{ display: 'flex', gap: 2, alignItems: 'center' }}>
                <TextField
                  label="Selected .bck File"
                  value={selectedBckPath}
                  placeholder="No file selected"
                  fullWidth
                  size="small"
                  InputProps={{
                    readOnly: true,
                  }}
                />
                <Button
                  variant="contained"
                  startIcon={<FolderIcon />}
                  onClick={() => setFileExplorerOpen(true)}
                >
                  Browse
                </Button>
              </Box>
            </Stack>
          )}

          {/* Selection Summary */}
          {currentSelection && (
            <Card variant="outlined" sx={{ p: 2, bgcolor: 'blue.50' }}>
              <Typography variant="subtitle2" gutterBottom>Selected Backup:</Typography>
              <Stack spacing={1.25}>
                <Stack
                  direction={{ xs: 'column', sm: 'row' }}
                  spacing={0.5}
                  justifyContent="space-between"
                  alignItems={{ xs: 'flex-start', sm: 'center' }}
                >
                  <Typography variant="body2" color="textSecondary">
                    File:
                  </Typography>
                  <Typography variant="body2" sx={{ fontFamily: 'monospace', wordBreak: 'break-word' }}>
                    {currentSelection.filename}
                  </Typography>
                </Stack>

                {currentSelection.path && (
                  <Stack
                    direction={{ xs: 'column', sm: 'row' }}
                    spacing={0.5}
                    justifyContent="space-between"
                    alignItems={{ xs: 'flex-start', sm: 'center' }}
                  >
                    <Typography variant="body2" color="textSecondary">
                      Full Path:
                    </Typography>
                    <Typography
                      variant="body2"
                      sx={{ fontFamily: 'monospace', fontSize: '0.8rem', wordBreak: 'break-all' }}
                    >
                      {currentSelection.path}
                    </Typography>
                  </Stack>
                )}

                <Stack
                  direction={{ xs: 'column', sm: 'row' }}
                  spacing={0.5}
                  justifyContent="space-between"
                  alignItems={{ xs: 'flex-start', sm: 'center' }}
                >
                  <Typography variant="body2" color="textSecondary">
                    Type:
                  </Typography>
                  <StatusChip tone="neutral" label={`${currentSelection.type.toUpperCase()} ${currentSelection.hasMetadata ? '(with metadata)' : '(no metadata)'}`} />
                </Stack>

                <Stack
                  direction={{ xs: 'column', sm: 'row' }}
                  spacing={0.5}
                  justifyContent="space-between"
                  alignItems={{ xs: 'flex-start', sm: 'center' }}
                >
                  <Typography variant="body2" color="textSecondary">
                    Size:
                  </Typography>
                  <Typography variant="body2">{currentSelection.size}</Typography>
                </Stack>

                <Stack
                  direction={{ xs: 'column', sm: 'row' }}
                  spacing={0.5}
                  justifyContent="space-between"
                  alignItems={{ xs: 'flex-start', sm: 'center' }}
                >
                  <Typography variant="body2" color="textSecondary">
                    Created:
                  </Typography>
                  <Typography variant="body2">
                    {currentSelection.created !== 'Unknown' ? formatDate(currentSelection.created) : 'Unknown'}
                  </Typography>
                </Stack>

                {currentSelection.description && (
                  <Stack spacing={0.5}>
                    <Typography variant="body2" color="textSecondary">
                      Description:
                    </Typography>
                    <Typography
                      variant="body2"
                      sx={{ fontStyle: 'italic', pl: { xs: 1, sm: 2 }, borderLeft: 2, borderColor: 'primary.main' }}
                    >
                      {currentSelection.description}
                    </Typography>
                  </Stack>
                )}
              </Stack>
            </Card>
          )}

          {/* Restore & pre-backup actions */}
          <Box sx={{ display: 'flex', gap: 2, flexWrap: 'wrap' }}>
            <Button
              variant="outlined"
              startIcon={<UploadIcon />}
              onClick={handleOpenCreateDialog}
              disabled={loading || restoreProgress}
            >
              Create Managed Backup
            </Button>
            <Button
              variant="contained"
              color="warning"
              startIcon={<RestoreIcon />}
              onClick={() => setRestoreDialogOpen(true)}
              disabled={!currentSelection || loading || restoreProgress}
            >
              Restore Database
            </Button>
          </Box>
        </Stack>
      </CardContent>

      {/* Restore Confirmation Dialog */}
      <Dialog
        open={restoreDialogOpen}
        onClose={() => !restoreProgress && setRestoreDialogOpen(false)}
        maxWidth="md"
        fullWidth
        fullScreen={isSmallScreen}
      >
        <DialogTitle>
          <Stack direction="row" alignItems="center" spacing={1}>
            <WarningIcon color="warning" />
            <Typography variant="h6">Restore Database - Confirmation Required</Typography>
          </Stack>
        </DialogTitle>
        <DialogContent sx={{ px: { xs: 2, sm: 3 } }}>
          <Stack spacing={3}>
            {restoreProgress && (
              <LoadingSpinner
                linear
                message="Restoring database... This may take several minutes."
              />
            )}

            {/* Backup Information */}
            {currentSelection && (
              <Card variant="outlined">
                <CardContent>
                  <Typography variant="h6" gutterBottom>
                    Backup Information
                  </Typography>
                  <Stack spacing={1}>
                    <Box display="flex" justifyContent="space-between">
                      <Typography variant="body2" color="textSecondary">Filename:</Typography>
                      <Typography variant="body2" sx={{ fontFamily: 'monospace' }}>
                        {currentSelection.filename}
                      </Typography>
                    </Box>
                    <Box display="flex" justifyContent="space-between">
                      <Typography variant="body2" color="textSecondary">Type:</Typography>
                      <StatusChip tone="neutral" label={`${currentSelection.type.toUpperCase()} ${currentSelection.hasMetadata ? '(with metadata)' : '(machine generated)'}`} />
                    </Box>
                    <Box display="flex" justifyContent="space-between">
                      <Typography variant="body2" color="textSecondary">Size:</Typography>
                      <Typography variant="body2">
                        {currentSelection.size}
                      </Typography>
                    </Box>
                    {currentSelection.description && (
                      <>
                        <Divider sx={{ my: 1 }} />
                        <Typography variant="body2" color="textSecondary">Description:</Typography>
                        <Typography variant="body2" sx={{ fontStyle: 'italic' }}>
                          {currentSelection.description}
                        </Typography>
                      </>
                    )}
                  </Stack>
                </CardContent>
              </Card>
            )}

            <Card variant="outlined" sx={{ bgcolor: 'rgba(255, 167, 38, 0.08)', borderColor: 'warning.light' }}>
              <CardContent>
                <Stack spacing={1.5}>
                  <Typography variant="subtitle2" color="warning.main" gutterBottom>
                    What this restore will do
                  </Typography>
                  <Typography variant="body2">
                    • Replace the entire database with the selected backup (no undo)
                    <br />
                    • Disconnect all users and pause monitoring during the restore
                    <br />
                    • Cause a short outage (typically 5–15 minutes)
                  </Typography>
                </Stack>
              </CardContent>
            </Card>

            {/* Confirmation Checkboxes */}
            <Stack spacing={2}>
              <FormControlLabel
                control={
                  <Checkbox
                    checked={confirmationChecks.dataLoss}
                    onChange={(e) => setConfirmationChecks(prev => ({
                      ...prev,
                      dataLoss: e.target.checked
                    }))}
                    disabled={restoreProgress}
                  />
                }
                label={
                  <Typography variant="body2">
                    I understand that this operation will permanently replace all current database data
                  </Typography>
                }
              />
              
              <FormControlLabel
                control={
                  <Checkbox
                    checked={confirmationChecks.downtime}
                    onChange={(e) => setConfirmationChecks(prev => ({
                      ...prev,
                      downtime: e.target.checked
                    }))}
                    disabled={restoreProgress}
                  />
                }
                label={
                  <Typography variant="body2">
                    I acknowledge that the database will be temporarily unavailable during the restore process
                  </Typography>
                }
              />
            </Stack>
          </Stack>
        </DialogContent>
        <DialogActions
          sx={{
            px: { xs: 2, sm: 3 },
            py: { xs: 2, sm: 2 },
            flexWrap: 'wrap',
            gap: 1,
            justifyContent: isSmallScreen ? 'flex-start' : 'flex-end'
          }}
        >
          <Button 
            onClick={() => setRestoreDialogOpen(false)} 
            disabled={restoreProgress}
            sx={{ flex: { xs: '1 1 100%', sm: '0 0 auto' } }}
          >
            Cancel
          </Button>
          <Button
            onClick={handleRestoreBackup}
            variant="contained"
            color="warning"
            disabled={restoreProgress || !canProceed}
            startIcon={restoreProgress ? <CircularProgress size={20} /> : <RestoreIcon />}
            sx={{ flex: { xs: '1 1 100%', sm: '0 0 auto' } }}
          >
            {restoreProgress ? 'Restoring...' : 'Restore Database'}
          </Button>
        </DialogActions>
      </Dialog>

      {/* Create Backup Dialog */}
      <Dialog
        open={createDialogOpen}
        onClose={() => !creatingBackup && setCreateDialogOpen(false)}
        maxWidth="sm"
        fullWidth
        fullScreen={isSmallScreen}
      >
        <DialogTitle sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
          <StorageIcon color="primary" />
          Create Managed Backup
        </DialogTitle>
        <DialogContent dividers sx={{ px: { xs: 2, sm: 3 } }}>
          <Stack spacing={2}>
            <Typography variant="body2" color="textSecondary">
              Capture a managed `.bak` file with JSON metadata before performing a restore. This gives you a rollback point if the restore introduces issues.
            </Typography>
            {createDialogError && (
              <Alert severity="error">{createDialogError}</Alert>
            )}
            <TextField
              label="Backup Description"
              value={createDescription}
              onChange={(e) => setCreateDescription(e.target.value)}
              placeholder="Describe why you're capturing this backup"
              fullWidth
              multiline
              minRows={2}
              disabled={creatingBackup}
            />
          </Stack>
        </DialogContent>
        <DialogActions
          sx={{
            px: { xs: 2, sm: 3 },
            py: { xs: 2, sm: 2 },
            gap: 1,
            flexWrap: 'wrap',
            justifyContent: isSmallScreen ? 'flex-start' : 'flex-end'
          }}
        >
          <Button
            onClick={() => setCreateDialogOpen(false)}
            disabled={creatingBackup}
            sx={{ flex: { xs: '1 1 100%', sm: '0 0 auto' } }}
          >
            Cancel
          </Button>
          <Button
            onClick={handleCreateBackup}
            variant="contained"
            startIcon={creatingBackup ? <CircularProgress size={20} /> : <StorageIcon />}
            disabled={creatingBackup}
            sx={{ flex: { xs: '1 1 100%', sm: '0 0 auto' } }}
          >
            {creatingBackup ? 'Creating...' : 'Create Backup'}
          </Button>
        </DialogActions>
      </Dialog>

      <StatusDialog status={status} onClose={() => setStatus(null)} />

      {/* File Explorer Dialog */}
      <FileExplorer
        open={fileExplorerOpen}
        onClose={() => setFileExplorerOpen(false)}
        onSelect={handleBckFileSelected}
      />
    </Card>
  );
};

export default DatabaseRestore;
