import React, { useState, useEffect } from 'react';
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
  Chip,
  Checkbox,
  FormControlLabel,
  Divider,
  LinearProgress,
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
  Tooltip,
  Collapse
} from '@mui/material';
import useTheme from '@mui/material/styles/useTheme';
import useMediaQuery from '@mui/material/useMediaQuery';
import {
  Restore as RestoreIcon,
  Upload as UploadIcon,
  Warning as WarningIcon,
  Info as InfoIcon,
  Storage as StorageIcon,
  Refresh as RefreshIcon,
  Folder as FolderIcon,
  InsertDriveFile as FileIcon,
  Computer as ComputerIcon,
  ExpandMore as ExpandMoreIcon,
  ExpandLess as ExpandLessIcon,
  Description as DescriptionIcon
} from '@mui/icons-material';
import LoadingSpinner from './LoadingSpinner';
import ErrorAlert from './ErrorAlert';
import { api } from '../services/api';
import { activateMaintenance } from '@/utils/MaintenanceManager';
import StatusDialog, { StatusSeverity } from './StatusDialog';

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

const FileExplorer: React.FC<FileExplorerProps> = ({ open, onClose, onSelect }) => {
  const [currentPath, setCurrentPath] = useState('C:\\');
  const [items, setItems] = useState<FileSystemItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [selectedFile, setSelectedFile] = useState<FileSystemItem | null>(null);
  const theme = useTheme();
  const fullScreen = useMediaQuery(theme.breakpoints.down('sm'));

  useEffect(() => {
    if (open) {
      loadDirectory(currentPath);
    }
  }, [open, currentPath]);

  const loadDirectory = async (path: string) => {
    setLoading(true);
    try {
      const response = await api.get('/api/system/browse', { 
        params: { path, filter: '.bck' } 
      });
      setItems(response.data.items || []);
    } catch (err: any) {
      console.error('Error browsing directory:', err);
      setItems([]);
    } finally {
      setLoading(false);
    }
  };

  const navigateToParent = () => {
    const parentPath = currentPath.split('\\').slice(0, -1).join('\\') || 'C:\\';
    setCurrentPath(parentPath);
  };

  const handleItemClick = (item: FileSystemItem) => {
    if (item.is_directory) {
      setCurrentPath(item.path);
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
        <Stack spacing={2}>
          <TextField
            label="Current Directory"
            value={currentPath}
            onChange={(e) => setCurrentPath(e.target.value)}
            onKeyPress={(e) => e.key === 'Enter' && loadDirectory(currentPath)}
            fullWidth
            size="small"
          />

          <Stack direction="row" spacing={1}>
            <Button
              size="small"
              startIcon={<FolderIcon />}
              onClick={navigateToParent}
              disabled={currentPath === 'C:\\'}
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

          {loading ? (
            <LoadingSpinner 
              variant="spinner" 
              message="Loading backup files..." 
              minHeight={200}
            />
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
                          <Chip label="BCK" size="small" color="secondary" />
                        )}
                      </ListItemButton>
                    </ListItem>
                  ))
                )}
              </List>
            </Paper>
          )}

          {selectedFile && (
            <ErrorAlert
              message={`Selected: ${selectedFile.name}\nPath: ${selectedFile.path}\nSize: ${selectedFile.size_formatted || 'Unknown'}`}
              severity="info"
              category="client"
              compact={true}
            />
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
  const [createFeedback, setCreateFeedback] = useState<{ type: 'success' | 'error'; message: string } | null>(null);
  const [statusDialog, setStatusDialog] = useState<{
    open: boolean;
    title: string;
    message: string;
    severity: StatusSeverity;
    autoCloseMs?: number;
  }>({ open: false, title: '', message: '', severity: 'info' });
  const theme = useTheme();
  const isSmallScreen = useMediaQuery(theme.breakpoints.down('sm'));

  useEffect(() => {
    loadBackupFiles();
  }, []);

  const showStatusDialog = (
    title: string,
    message: string,
    severity: StatusSeverity,
    autoCloseMs?: number
  ) => {
    setStatusDialog({ open: true, title, message, severity, autoCloseMs });
  };

  const closeStatusDialog = () => {
    setStatusDialog(prev => ({ ...prev, open: false }));
  };

  const loadBackupFiles = async (): Promise<BackupFile[]> => {
    setLoading(true);
    try {
      const response = await api.get('/api/admin/backup/list');
      console.log('Backup API Response:', response.data);
      
      // Backend returns { success, data: [...backup files...], message }
      const files = response.data.data || [];
      const managedBackups = files.filter((f: any) => f.filename.endsWith('.bak'));
      setBackupFiles(managedBackups);
      console.log('Loaded backup files:', files);
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
    if (!canProceed || !hasSelection) return;
    
    const restoreRequest = activeTab === 0 && selectedBackup 
      ? { filename: selectedBackup.filename } 
      : { file_path: selectedBckPath };

    setRestoreProgress(true);
    try {
      await api.post('/api/admin/backup/restore', restoreRequest);

      activateMaintenance(60000, 'Database restore is finishing.');
      showStatusDialog(
        'Restore Started',
        'Database restore has begun. The system may be unavailable for several minutes while services restart. Background updates are paused briefly.',
        'success'
      );

      // Success - close dialog and refresh
      setRestoreDialogOpen(false);
      setSelectedBackup(null);
      setSelectedBckPath('');
      setConfirmationChecks({ dataLoss: false, downtime: false });

    } catch (err: any) {
      console.error('Error restoring backup:', err);
      const message = err.response?.data?.detail || err.message || 'Failed to restore backup';
      showStatusDialog('Restore Failed', message, 'error');
      if (onError) {
        onError(message);
      }
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
      setCreateFeedback({ type: 'success', message });
      showStatusDialog('Backup Created', message, 'success');

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
      setCreateFeedback({ type: 'error', message });
      showStatusDialog('Backup Creation Failed', message, 'error');
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

          {createFeedback && (
            <ErrorAlert
              message={createFeedback.message}
              severity={createFeedback.type === 'success' ? 'success' : 'error'}
              category="client"
              closable
              onClose={() => setCreateFeedback(null)}
            />
          )}

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
                          <Chip label="BAK" size="small" variant="outlined" color="primary" />
                          {!backup.is_valid && (
                            <Chip label="Invalid" size="small" color="error" />
                          )}
                        </Stack>
                      </Box>
                    </MenuItem>
                  ))}
                </Select>
              </FormControl>

              {/* Metadata Details for Selected BAK */}
              {selectedBackup && (
                <Card variant="outlined" sx={{ bgcolor: 'grey.50' }}>
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
                        <Chip 
                          label={selectedBackup.is_valid ? 'Valid' : 'Invalid'}
                          size="small" 
                          color={selectedBackup.is_valid ? 'success' : 'error'}
                        />
                      </Stack>
                      
                      {selectedBackup.description && (
                        <Stack spacing={0.5}>
                          <Typography variant="body2" color="textSecondary" gutterBottom>Description:</Typography>
                          <Typography variant="body2" sx={{ fontStyle: 'italic', pl: 1, borderLeft: 2, borderColor: 'grey.300' }}>
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
                  startIcon={loading ? <LoadingSpinner variant="inline" size="small" /> : <RefreshIcon />}
                  onClick={loadBackupFiles}
                  disabled={loading || restoreProgress}
                >
                  Refresh List
                </Button>
              </Box>

              {backupFiles.length === 0 && !loading && (
                <ErrorAlert
                  message="No managed backup files found. Create backups using the backup manager or switch to browse mode for .bck files."
                  severity="info"
                  category="client"
                  compact={true}
                />
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
                  <Chip
                    label={`${currentSelection.type.toUpperCase()} ${currentSelection.hasMetadata ? '(with metadata)' : '(no metadata)'}`}
                    size="small"
                    color={currentSelection.type === 'bak' ? 'primary' : 'secondary'}
                  />
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
              Create JSON Backup
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
                variant="linear"
                message="Restoring database... This may take several minutes."
              />
            )}

            <ErrorAlert
              message="This operation will completely replace the current database with the backup data. All current data will be permanently lost and cannot be recovered."
              severity="warning"
              category="server"
              title="DESTRUCTIVE OPERATION WARNING"
            />

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
                      <Chip 
                        label={`${currentSelection.type.toUpperCase()} ${currentSelection.hasMetadata ? '(with metadata)' : '(machine generated)'}`}
                        size="small" 
                        color={currentSelection.type === 'bak' ? 'primary' : 'secondary'}
                      />
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

            <ErrorAlert
              message="During the restore process:\n• Database will be temporarily unavailable (5-15 minutes)\n• All active connections will be terminated\n• Current experiments and monitoring will be interrupted\n• Web application may show connection errors temporarily"
              severity="info"
              category="server"
              title="Operation Impact"
            />

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
            startIcon={restoreProgress ? <LoadingSpinner variant="inline" size="small" /> : <RestoreIcon />}
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
              <ErrorAlert
                message={createDialogError}
                severity="error"
                category="client"
                compact
              />
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
            startIcon={creatingBackup ? <LoadingSpinner variant="inline" size="small" /> : <StorageIcon />}
            disabled={creatingBackup}
            sx={{ flex: { xs: '1 1 100%', sm: '0 0 auto' } }}
          >
            {creatingBackup ? 'Creating...' : 'Create Backup'}
          </Button>
        </DialogActions>
      </Dialog>

      <StatusDialog
        open={statusDialog.open}
        onClose={closeStatusDialog}
        title={statusDialog.title}
        message={statusDialog.message}
        severity={statusDialog.severity}
        autoCloseMs={statusDialog.autoCloseMs}
      />

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
