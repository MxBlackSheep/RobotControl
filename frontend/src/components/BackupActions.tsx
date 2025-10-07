/**
 * PyRobot Backup Actions Component
 * 
 * Action buttons and dialogs for backup operations:
 * - Create backup with description form
 * - Restore backup with destructive operation warning
 * - Delete backup with confirmation dialog
 * - Progress indicators and status messaging
 * - Form validation and error handling
 */

import React, { useState } from 'react';
import {
  Box,
  Button,
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  TextField,
  Typography,
  Alert,
  Stack,
  Chip,
  CircularProgress,
  LinearProgress,
  Checkbox,
  FormControlLabel,
  Card,
  CardContent,
  Divider
} from '@mui/material';
import {
  Add as AddIcon,
  Restore as RestoreIcon,
  Delete as DeleteIcon,
  Warning as WarningIcon,
  Info as InfoIcon,
  Storage as StorageIcon,
  Schedule as ScheduleIcon
} from '@mui/icons-material';

import {
  BackupInfo,
  BackupOperationStatus,
  CreateBackupFormData,
  RestoreConfirmationData,
  formatBackupDate,
  BACKUP_CONSTANTS
} from '../types/backup';

interface BackupActionsProps {
  selectedBackup: BackupInfo | null;
  onCreateBackup: (description: string) => Promise<void>;
  onRestoreBackup: (backup: BackupInfo) => Promise<void>;
  onDeleteBackup: (backup: BackupInfo) => Promise<void>;
  operationStatus: BackupOperationStatus;
  disabled?: boolean;
}

interface CreateBackupDialogProps {
  open: boolean;
  onClose: () => void;
  onSubmit: (data: CreateBackupFormData) => Promise<void>;
  loading?: boolean;
}

interface RestoreConfirmationDialogProps {
  open: boolean;
  backup: BackupInfo | null;
  onClose: () => void;
  onConfirm: (data: RestoreConfirmationData) => Promise<void>;
  loading?: boolean;
}

interface DeleteConfirmationDialogProps {
  open: boolean;
  backup: BackupInfo | null;
  onClose: () => void;
  onConfirm: () => Promise<void>;
  loading?: boolean;
}

const CreateBackupDialog: React.FC<CreateBackupDialogProps> = ({
  open,
  onClose,
  onSubmit,
  loading = false
}) => {
  const [formData, setFormData] = useState<CreateBackupFormData>({
    description: ''
  });
  const [errors, setErrors] = useState<string[]>([]);

  const handleSubmit = async () => {
    // Validate form
    const validationErrors: string[] = [];
    
    if (!formData.description.trim()) {
      validationErrors.push('Description is required');
    } else if (formData.description.length > BACKUP_CONSTANTS.MAX_DESCRIPTION_LENGTH) {
      validationErrors.push(`Description cannot exceed ${BACKUP_CONSTANTS.MAX_DESCRIPTION_LENGTH} characters`);
    }
    
    setErrors(validationErrors);
    
    if (validationErrors.length === 0) {
      try {
        await onSubmit(formData);
        setFormData({ description: '' });
        setErrors([]);
        onClose();
      } catch (error) {
        setErrors([error instanceof Error ? error.message : 'Failed to create backup']);
      }
    }
  };

  const handleClose = () => {
    if (!loading) {
      setFormData({ description: '' });
      setErrors([]);
      onClose();
    }
  };

  return (
    <Dialog open={open} onClose={handleClose} maxWidth="sm" fullWidth>
      <DialogTitle>
        <Stack direction="row" alignItems="center" spacing={1}>
          <AddIcon color="primary" />
          <Typography variant="h6">Create Database Backup</Typography>
        </Stack>
      </DialogTitle>
      <DialogContent>
        <Stack spacing={2} sx={{ mt: 1 }}>
          {errors.length > 0 && (
            <Alert severity="error">
              <ul style={{ margin: 0, paddingLeft: 20 }}>
                {errors.map((error, index) => (
                  <li key={index}>{error}</li>
                ))}
              </ul>
            </Alert>
          )}
          
          <TextField
            label="Backup Description"
            placeholder="Enter a description for this backup (e.g., 'Before experiment batch #123')"
            multiline
            rows={3}
            fullWidth
            value={formData.description}
            onChange={(e) => setFormData({ description: e.target.value })}
            disabled={loading}
            helperText={`${formData.description.length}/${BACKUP_CONSTANTS.MAX_DESCRIPTION_LENGTH} characters`}
          />
          
          <Alert severity="info" icon={<InfoIcon />}>
            This will create a complete backup of the current database state. The process may take several minutes depending on database size.
          </Alert>
        </Stack>
      </DialogContent>
      <DialogActions>
        <Button onClick={handleClose} disabled={loading}>
          Cancel
        </Button>
        <Button
          onClick={handleSubmit}
          variant="contained"
          disabled={loading || !formData.description.trim()}
          startIcon={loading ? <CircularProgress size={16} /> : <AddIcon />}
        >
          {loading ? 'Creating...' : 'Create Backup'}
        </Button>
      </DialogActions>
    </Dialog>
  );
};

const RestoreConfirmationDialog: React.FC<RestoreConfirmationDialogProps> = ({
  open,
  backup,
  onClose,
  onConfirm,
  loading = false
}) => {
  const [confirmationData, setConfirmationData] = useState<RestoreConfirmationData>({
    backup: backup!,
    userConfirmed: false,
    acknowledged: false
  });

  React.useEffect(() => {
    if (backup) {
      setConfirmationData({
        backup,
        userConfirmed: false,
        acknowledged: false
      });
    }
  }, [backup]);

  const handleConfirm = async () => {
    if (confirmationData.userConfirmed && confirmationData.acknowledged) {
      try {
        await onConfirm(confirmationData);
        onClose();
      } catch (error) {
        // Error handling is managed by parent component
      }
    }
  };

  const handleClose = () => {
    if (!loading) {
      setConfirmationData({
        backup: backup!,
        userConfirmed: false,
        acknowledged: false
      });
      onClose();
    }
  };

  if (!backup) return null;

  const canProceed = confirmationData.userConfirmed && confirmationData.acknowledged;

  return (
    <Dialog open={open} onClose={handleClose} maxWidth="md" fullWidth>
      <DialogTitle>
        <Stack direction="row" alignItems="center" spacing={1}>
          <WarningIcon color="warning" />
          <Typography variant="h6">Restore Database - Confirmation Required</Typography>
        </Stack>
      </DialogTitle>
      <DialogContent>
        <Stack spacing={3}>
          {/* Warning Alert */}
          <Alert severity="warning" icon={<WarningIcon />}>
            <Typography variant="subtitle1" gutterBottom>
              <strong>DESTRUCTIVE OPERATION WARNING</strong>
            </Typography>
            <Typography variant="body2">
              This operation will completely replace the current database with the backup data.
              All current data will be permanently lost and cannot be recovered.
            </Typography>
          </Alert>

          {/* Backup Information */}
          <Card variant="outlined">
            <CardContent>
              <Typography variant="h6" gutterBottom>
                Backup Information
              </Typography>
              <Stack spacing={1}>
                <Box display="flex" justifyContent="space-between">
                  <Typography variant="body2" color="textSecondary">Filename:</Typography>
                  <Typography variant="body2" sx={{ fontFamily: 'monospace' }}>
                    {backup.filename}
                  </Typography>
                </Box>
                <Box display="flex" justifyContent="space-between">
                  <Typography variant="body2" color="textSecondary">Created:</Typography>
                  <Typography variant="body2">
                    {formatBackupDate(backup.created_date)}
                  </Typography>
                </Box>
                <Box display="flex" justifyContent="space-between">
                  <Typography variant="body2" color="textSecondary">Size:</Typography>
                  <Typography variant="body2">
                    {backup.file_size_formatted}
                  </Typography>
                </Box>
                <Divider sx={{ my: 1 }} />
                <Typography variant="body2" color="textSecondary">Description:</Typography>
                <Typography variant="body2" sx={{ fontStyle: backup.description ? 'normal' : 'italic' }}>
                  {backup.description || 'No description provided'}
                </Typography>
              </Stack>
            </CardContent>
          </Card>

          {/* Impact Information */}
          <Alert severity="info" icon={<InfoIcon />}>
            <Typography variant="subtitle1" gutterBottom>
              <strong>Operation Impact</strong>
            </Typography>
            <Typography variant="body2" component="div">
              During the restore process:
              <ul style={{ margin: '8px 0', paddingLeft: 20 }}>
                <li>Database will be temporarily unavailable (5-15 minutes)</li>
                <li>All active connections will be terminated</li>
                <li>Current experiments and monitoring will be interrupted</li>
                <li>Web application may show connection errors temporarily</li>
              </ul>
            </Typography>
          </Alert>

          {/* Confirmation Checkboxes */}
          <Stack spacing={2}>
            <FormControlLabel
              control={
                <Checkbox
                  checked={confirmationData.userConfirmed}
                  onChange={(e) => setConfirmationData(prev => ({
                    ...prev,
                    userConfirmed: e.target.checked
                  }))}
                  disabled={loading}
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
                  checked={confirmationData.acknowledged}
                  onChange={(e) => setConfirmationData(prev => ({
                    ...prev,
                    acknowledged: e.target.checked
                  }))}
                  disabled={loading}
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
      <DialogActions>
        <Button onClick={handleClose} disabled={loading}>
          Cancel
        </Button>
        <Button
          onClick={handleConfirm}
          variant="contained"
          color="warning"
          disabled={loading || !canProceed}
          startIcon={loading ? <CircularProgress size={16} /> : <RestoreIcon />}
        >
          {loading ? 'Restoring...' : 'Restore Database'}
        </Button>
      </DialogActions>
    </Dialog>
  );
};

const DeleteConfirmationDialog: React.FC<DeleteConfirmationDialogProps> = ({
  open,
  backup,
  onClose,
  onConfirm,
  loading = false
}) => {
  if (!backup) return null;

  const handleConfirm = async () => {
    try {
      await onConfirm();
      onClose();
    } catch (error) {
      // Error handling is managed by parent component
    }
  };

  return (
    <Dialog open={open} onClose={onClose} maxWidth="sm" fullWidth>
      <DialogTitle>
        <Stack direction="row" alignItems="center" spacing={1}>
          <DeleteIcon color="error" />
          <Typography variant="h6">Delete Backup</Typography>
        </Stack>
      </DialogTitle>
      <DialogContent>
        <Stack spacing={2}>
          <Alert severity="warning">
            <Typography variant="body1" gutterBottom>
              <strong>Are you sure you want to delete this backup?</strong>
            </Typography>
            <Typography variant="body2">
              This action cannot be undone. The backup file and its metadata will be permanently removed.
            </Typography>
          </Alert>
          
          <Card variant="outlined">
            <CardContent>
              <Typography variant="subtitle1" gutterBottom>
                Backup to Delete
              </Typography>
              <Stack spacing={1}>
                <Typography variant="body2">
                  <strong>File:</strong> {backup.filename}
                </Typography>
                <Typography variant="body2">
                  <strong>Created:</strong> {formatBackupDate(backup.created_date)}
                </Typography>
                <Typography variant="body2">
                  <strong>Size:</strong> {backup.file_size_formatted}
                </Typography>
                <Typography variant="body2">
                  <strong>Description:</strong> {backup.description || 'No description'}
                </Typography>
              </Stack>
            </CardContent>
          </Card>
        </Stack>
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose} disabled={loading}>
          Cancel
        </Button>
        <Button
          onClick={handleConfirm}
          variant="contained"
          color="error"
          disabled={loading}
          startIcon={loading ? <CircularProgress size={16} /> : <DeleteIcon />}
        >
          {loading ? 'Deleting...' : 'Delete Backup'}
        </Button>
      </DialogActions>
    </Dialog>
  );
};

const BackupActions: React.FC<BackupActionsProps> = ({
  selectedBackup,
  onCreateBackup,
  onRestoreBackup,
  onDeleteBackup,
  operationStatus,
  disabled = false
}) => {
  const [dialogs, setDialogs] = useState({
    create: false,
    restore: false,
    delete: false
  });

  const isOperationInProgress = operationStatus !== BackupOperationStatus.Idle && 
                                operationStatus !== BackupOperationStatus.Error;

  const handleCreateBackup = async (data: CreateBackupFormData) => {
    await onCreateBackup(data.description);
  };

  const handleRestoreConfirm = async (data: RestoreConfirmationData) => {
    await onRestoreBackup(data.backup);
  };

  const handleDeleteConfirm = async () => {
    if (selectedBackup) {
      await onDeleteBackup(selectedBackup);
    }
  };

  const openDialog = (type: 'create' | 'restore' | 'delete') => {
    setDialogs(prev => ({ ...prev, [type]: true }));
  };

  const closeDialog = (type: 'create' | 'restore' | 'delete') => {
    setDialogs(prev => ({ ...prev, [type]: false }));
  };

  const renderOperationStatus = () => {
    if (operationStatus === BackupOperationStatus.Idle) return null;

    const statusConfig = {
      [BackupOperationStatus.Creating]: { color: 'info', text: 'Creating backup...' },
      [BackupOperationStatus.Restoring]: { color: 'warning', text: 'Restoring database...' },
      [BackupOperationStatus.Deleting]: { color: 'error', text: 'Deleting backup...' },
      [BackupOperationStatus.Loading]: { color: 'info', text: 'Loading...' },
      [BackupOperationStatus.Error]: { color: 'error', text: 'Operation failed' }
    } as const;

    const config = statusConfig[operationStatus];
    if (!config) return null;

    return (
      <Box sx={{ mb: 2 }}>
        <Stack direction="row" alignItems="center" spacing={1} sx={{ mb: 1 }}>
          <CircularProgress size={16} />
          <Typography variant="body2" color={`${config.color}.main`}>
            {config.text}
          </Typography>
        </Stack>
        {isOperationInProgress && <LinearProgress />}
      </Box>
    );
  };

  return (
    <>
      {renderOperationStatus()}
      
      <Stack direction="row" spacing={2} flexWrap="wrap">
        {/* Create Backup Button */}
        <Button
          variant="contained"
          startIcon={<AddIcon />}
          onClick={() => openDialog('create')}
          disabled={disabled || isOperationInProgress}
        >
          Create Backup
        </Button>

        {/* Restore Backup Button */}
        <Button
          variant="outlined"
          color="warning"
          startIcon={<RestoreIcon />}
          onClick={() => openDialog('restore')}
          disabled={disabled || !selectedBackup || !selectedBackup.is_valid || isOperationInProgress}
        >
          Restore Database
        </Button>

        {/* Delete Backup Button */}
        <Button
          variant="outlined"
          color="error"
          startIcon={<DeleteIcon />}
          onClick={() => openDialog('delete')}
          disabled={disabled || !selectedBackup || isOperationInProgress}
        >
          Delete Backup
        </Button>
      </Stack>

      {/* Selection Status */}
      {selectedBackup && (
        <Box sx={{ mt: 2 }}>
          <Chip
            icon={<StorageIcon />}
            label={`Selected: ${selectedBackup.filename}`}
            variant="outlined"
            color="primary"
            size="small"
          />
        </Box>
      )}

      {/* Dialogs */}
      <CreateBackupDialog
        open={dialogs.create}
        onClose={() => closeDialog('create')}
        onSubmit={handleCreateBackup}
        loading={operationStatus === BackupOperationStatus.Creating}
      />

      <RestoreConfirmationDialog
        open={dialogs.restore}
        backup={selectedBackup}
        onClose={() => closeDialog('restore')}
        onConfirm={handleRestoreConfirm}
        loading={operationStatus === BackupOperationStatus.Restoring}
      />

      <DeleteConfirmationDialog
        open={dialogs.delete}
        backup={selectedBackup}
        onClose={() => closeDialog('delete')}
        onConfirm={handleDeleteConfirm}
        loading={operationStatus === BackupOperationStatus.Deleting}
      />
    </>
  );
};

export default BackupActions;
export { CreateBackupDialog, RestoreConfirmationDialog, DeleteConfirmationDialog };
export type { BackupActionsProps, CreateBackupDialogProps, RestoreConfirmationDialogProps, DeleteConfirmationDialogProps };