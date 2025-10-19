/**
 * RobotControl Schedule Actions Component
 * 
 * Action buttons and dialogs for schedule operations:
 * - Create schedule with comprehensive form
 * - Edit schedule with pre-filled data
 * - Delete schedule with confirmation
 * - Start/stop scheduler service (admin only)
 * - Progress indicators and error handling
 */

import React, { useState, useEffect } from 'react';
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
  Divider,
  FormControl,
  InputLabel,
  Select,
  MenuItem,
  Grid,
  InputAdornment,
  Switch
} from '@mui/material';
// Using standard HTML date/time inputs instead of MUI X DateTimePicker to avoid additional dependencies
import {
  Add as AddIcon,
  Edit as EditIcon,
  Delete as DeleteIcon,
  PlayArrow as StartIcon,
  Stop as StopIcon,
  Warning as WarningIcon,
  Info as InfoIcon,
  Schedule as ScheduleIcon,
  AccessTime as ClockIcon,
  Science as ExperimentIcon,
  CheckCircle as CheckCircleIcon
} from '@mui/icons-material';

import {
  ScheduledExperiment,
  CreateScheduleFormData,
  UpdateScheduleRequest,
  SchedulingOperationStatus,
  ScheduleActionsProps,
  SCHEDULE_TYPE_OPTIONS,
  BACKOFF_STRATEGY_OPTIONS,
  SCHEDULING_CONSTANTS,
  validateScheduleFormData,
  formatScheduleType
} from '../types/scheduling';
import { ServerError } from './ErrorAlert';

interface CreateScheduleDialogProps {
  open: boolean;
  onClose: () => void;
  onSubmit: (data: CreateScheduleFormData) => Promise<void>;
  loading?: boolean;
}

interface EditScheduleDialogProps {
  open: boolean;
  schedule: ScheduledExperiment | null;
  onClose: () => void;
  onSubmit: (scheduleId: string, data: UpdateScheduleRequest) => Promise<void>;
  loading?: boolean;
}

interface DeleteConfirmationDialogProps {
  open: boolean;
  schedule: ScheduledExperiment | null;
  onClose: () => void;
  onConfirm: () => Promise<void>;
  loading?: boolean;
}

const CreateScheduleDialog: React.FC<CreateScheduleDialogProps> = ({
  open,
  onClose,
  onSubmit,
  loading = false
}) => {
  const [formData, setFormData] = useState<CreateScheduleFormData>({
    experiment_name: '',
    experiment_path: '',
    schedule_type: 'once',
    interval_hours: 6,
    start_time: null,
    estimated_duration: 55,
    is_active: true,
    max_retries: 3,
    retry_delay_minutes: 2,
    backoff_strategy: 'linear',
    prerequisites: [],
    notification_contacts: []
  });
  
  // Helper for date/time conversion
  const formatDateTimeForInput = (date: Date | null): string => {
    if (!date) return '';
    const d = new Date(date);
    d.setMinutes(d.getMinutes() - d.getTimezoneOffset()); // Adjust for timezone
    return d.toISOString().slice(0, 16);
  };
  
  const parseDateTimeFromInput = (dateTimeString: string): Date | null => {
    if (!dateTimeString) return null;
    return new Date(dateTimeString);
  };
  const [errors, setErrors] = useState<string[]>([]);
  const [prerequisiteInput, setPrerequisiteInput] = useState('');

  const handleSubmit = async () => {
    // Validate form
    const validationErrors = validateScheduleFormData(formData);
    setErrors(validationErrors);

    if (validationErrors.length === 0) {
      try {
        await onSubmit(formData);
        resetForm();
        onClose();
      } catch (error) {
        setErrors([error instanceof Error ? error.message : 'Failed to create schedule']);
      }
    }
  };

  const resetForm = () => {
    setFormData({
      experiment_name: '',
      experiment_path: '',
      schedule_type: 'once',
      interval_hours: 6,
      start_time: null,
      estimated_duration: 55,
      is_active: true,
      max_retries: 3,
      retry_delay_minutes: 2,
      backoff_strategy: 'linear',
      prerequisites: [],
      notification_contacts: []
    });
    setErrors([]);
    setPrerequisiteInput('');
  };

  const handleClose = () => {
    if (!loading) {
      resetForm();
      onClose();
    }
  };

  const handleAddPrerequisite = () => {
    const prerequisite = prerequisiteInput.trim();
    if (prerequisite && !formData.prerequisites.includes(prerequisite)) {
      setFormData(prev => ({
        ...prev,
        prerequisites: [...prev.prerequisites, prerequisite]
      }));
      setPrerequisiteInput('');
    }
  };

  const handleRemovePrerequisite = (index: number) => {
    setFormData(prev => ({
      ...prev,
      prerequisites: prev.prerequisites.filter((_, i) => i !== index)
    }));
  };

  return (
    <>
      {errors.length > 0 && (
        <ServerError
          title="Cannot Create Schedule"
          message={errors.map((item) => `• ${item}`).join('\n')}
          onClose={() => setErrors([])}
          retryable={false}
        />
      )}
      <Dialog open={open} onClose={handleClose} maxWidth="md" fullWidth>
        <DialogTitle>
          <Stack direction="row" alignItems="center" spacing={1}>
            <AddIcon color="primary" />
            <Typography variant="h6">Create New Schedule</Typography>
          </Stack>
        </DialogTitle>
        <DialogContent>
          <Stack spacing={3} sx={{ mt: 1 }}>
            {/* Basic Information */}
            <Card variant="outlined">
              <CardContent>
                <Typography variant="h6" gutterBottom>
                  Experiment Information
                </Typography>
                <Grid container spacing={2}>
                  <Grid item xs={12} md={6}>
                    <TextField
                      label="Experiment Name"
                      placeholder="e.g., Champions_FL"
                      fullWidth
                      value={formData.experiment_name}
                      onChange={(e) => setFormData({ ...formData, experiment_name: e.target.value })}
                      disabled={loading}
                      required
                    />
                  </Grid>
                  <Grid item xs={12} md={6}>
                    <TextField
                      label="Estimated Duration (minutes)"
                      type="number"
                      fullWidth
                      value={formData.estimated_duration}
                      onChange={(e) => setFormData({ ...formData, estimated_duration: Number(e.target.value) })}
                      disabled={loading}
                      required
                      InputProps={{
                        endAdornment: <InputAdornment position="end">min</InputAdornment>
                      }}
                    />
                  </Grid>
                  <Grid item xs={12}>
                    <TextField
                      label="Experiment Path"
                      placeholder="e.g., Champions_FL.med"
                      fullWidth
                      value={formData.experiment_path}
                      onChange={(e) => setFormData({ ...formData, experiment_path: e.target.value })}
                      disabled={loading}
                      required
                    />
                  </Grid>
                </Grid>
              </CardContent>
            </Card>

            {/* Schedule Configuration */}
            <Card variant="outlined">
              <CardContent>
                <Typography variant="h6" gutterBottom>
                  Schedule Configuration
                </Typography>
                <Grid container spacing={2}>
                  <Grid item xs={12} md={6}>
                    <FormControl fullWidth>
                      <InputLabel>Schedule Type</InputLabel>
                      <Select
                        value={formData.schedule_type}
                        label="Schedule Type"
                        onChange={(e) => setFormData({ ...formData, schedule_type: e.target.value as any })}
                        disabled={loading}
                      >
                        {SCHEDULE_TYPE_OPTIONS.map((option) => (
                          <MenuItem key={option.value} value={option.value}>
                            {option.label}
                          </MenuItem>
                        ))}
                      </Select>
                    </FormControl>
                  </Grid>
                  {formData.schedule_type === 'interval' && (
                    <Grid item xs={12} md={6}>
                      <TextField
                        label="Interval Hours"
                        type="number"
                        fullWidth
                        value={formData.interval_hours}
                        onChange={(e) => setFormData({ ...formData, interval_hours: Number(e.target.value) })}
                        disabled={loading}
                        required
                        InputProps={{
                          endAdornment: <InputAdornment position="end">hours</InputAdornment>
                        }}
                      />
                    </Grid>
                  )}
                  <Grid item xs={12}>
                    <TextField
                      label="Start Time (optional)"
                      type="datetime-local"
                      fullWidth
                      value={formatDateTimeForInput(formData.start_time)}
                      onChange={(e) => setFormData({ ...formData, start_time: parseDateTimeFromInput(e.target.value) })}
                      disabled={loading}
                      InputLabelProps={{
                        shrink: true,
                      }}
                      helperText="Leave empty to start immediately when scheduler runs"
                    />
                  </Grid>
                  <Grid item xs={12}>
                    <FormControlLabel
                      control={
                        <Switch
                          checked={formData.is_active}
                          onChange={(e) => setFormData({ ...formData, is_active: e.target.checked })}
                          disabled={loading}
                        />
                      }
                      label="Active (schedule will run automatically)"
                    />
                  </Grid>
                </Grid>
              </CardContent>
            </Card>

            {/* Retry Configuration */}
            <Card variant="outlined">
              <CardContent>
                <Typography variant="h6" gutterBottom>
                  Retry Behaviour
                </Typography>
                <Alert severity="info" icon={<InfoIcon fontSize="small" />}>
                  Conflict retries are handled automatically (up to 3 attempts with a 2-minute delay).
                </Alert>
              </CardContent>
            </Card>

            {/* Prerequisites */}
            <Card variant="outlined">
              <CardContent>
                <Typography variant="h6" gutterBottom>
                  Prerequisites (Optional)
                </Typography>
                <Stack spacing={2}>
                  <Stack direction="row" spacing={1}>
                    <TextField
                      label="Add Prerequisite"
                      placeholder="Enter prerequisite condition"
                      fullWidth
                      value={prerequisiteInput}
                      onChange={(e) => setPrerequisiteInput(e.target.value)}
                      disabled={loading}
                      onKeyPress={(e) => e.key === 'Enter' && handleAddPrerequisite()}
                    />
                    <Button
                      variant="outlined"
                      onClick={handleAddPrerequisite}
                      disabled={loading || !prerequisiteInput.trim()}
                    >
                      Add
                    </Button>
                  </Stack>
                  {formData.prerequisites.length > 0 && (
                    <Stack direction="row" spacing={1} flexWrap="wrap">
                      {formData.prerequisites.map((prerequisite, index) => (
                        <Chip
                          key={index}
                          label={prerequisite}
                          onDelete={() => handleRemovePrerequisite(index)}
                          disabled={loading}
                          size="small"
                        />
                      ))}
                    </Stack>
                  )}
                </Stack>
              </CardContent>
            </Card>

            <Alert severity="info" icon={<InfoIcon />}>
              The schedule will be created and managed by the scheduler service. 
              Make sure the experiment file exists at the specified path before activation.
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
            disabled={loading || !formData.experiment_name.trim() || !formData.experiment_path.trim()}
            startIcon={loading ? <CircularProgress size={16} /> : <AddIcon />}
          >
            {loading ? 'Creating...' : 'Create Schedule'}
          </Button>
        </DialogActions>
      </Dialog>
    </>
  );
};

const EditScheduleDialog: React.FC<EditScheduleDialogProps> = ({
  open,
  schedule,
  onClose,
  onSubmit,
  loading = false
}) => {
  const [formData, setFormData] = useState<UpdateScheduleRequest>({});
  const [errors, setErrors] = useState<string[]>([]);

  useEffect(() => {
    if (schedule) {
      setFormData({
        experiment_name: schedule.experiment_name,
        experiment_path: schedule.experiment_path,
        schedule_type: schedule.schedule_type,
        interval_hours: schedule.interval_hours,
        start_time: schedule.start_time,
        estimated_duration: schedule.estimated_duration,
        is_active: schedule.is_active,
        retry_config: schedule.retry_config,
        prerequisites: schedule.prerequisites,
        notification_contacts: schedule.notification_contacts ?? []
      });
    }
  }, [schedule]);

  const handleSubmit = async () => {
    if (!schedule) return;

    // Basic validation
    const validationErrors: string[] = [];
    if (formData.experiment_name && !formData.experiment_name.trim()) {
      validationErrors.push('Experiment name cannot be empty');
    }
    if (formData.experiment_path && !formData.experiment_path.trim()) {
      validationErrors.push('Experiment path cannot be empty');
    }

    setErrors(validationErrors);

    if (validationErrors.length === 0) {
      try {
        await onSubmit(schedule.schedule_id, formData);
        onClose();
      } catch (error) {
        setErrors([error instanceof Error ? error.message : 'Failed to update schedule']);
      }
    }
  };

  const handleClose = () => {
    if (!loading) {
      setErrors([]);
      onClose();
    }
  };

  if (!schedule) return null;

  return (
    <>
      {errors.length > 0 && (
        <ServerError
          title="Cannot Update Schedule"
          message={errors.map((item) => `• ${item}`).join('\n')}
          onClose={() => setErrors([])}
          retryable={false}
        />
      )}
    <Dialog open={open} onClose={handleClose} maxWidth="md" fullWidth>
      <DialogTitle>
        <Stack direction="row" alignItems="center" spacing={1}>
          <EditIcon color="primary" />
          <Typography variant="h6">Edit Schedule</Typography>
        </Stack>
      </DialogTitle>
      <DialogContent>
        <Stack spacing={3} sx={{ mt: 1 }}>
          <Grid container spacing={2}>
            <Grid item xs={12} md={6}>
              <TextField
                label="Experiment Name"
                fullWidth
                value={formData.experiment_name || ''}
                onChange={(e) => setFormData({ ...formData, experiment_name: e.target.value })}
                disabled={loading}
              />
            </Grid>
            <Grid item xs={12} md={6}>
              <TextField
                label="Estimated Duration (minutes)"
                type="number"
                fullWidth
                value={formData.estimated_duration || ''}
                onChange={(e) => setFormData({ ...formData, estimated_duration: Number(e.target.value) })}
                disabled={loading}
              />
            </Grid>
            <Grid item xs={12}>
              <TextField
                label="Experiment Path"
                fullWidth
                value={formData.experiment_path || ''}
                onChange={(e) => setFormData({ ...formData, experiment_path: e.target.value })}
                disabled={loading}
              />
            </Grid>
            <Grid item xs={12}>
              <FormControlLabel
                control={
                  <Switch
                    checked={formData.is_active ?? false}
                    onChange={(e) => setFormData({ ...formData, is_active: e.target.checked })}
                    disabled={loading}
                  />
                }
                label="Active"
              />
            </Grid>
          </Grid>

          <Alert severity="info">
            Editing a schedule will update its configuration but preserve execution history.
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
          disabled={loading}
          startIcon={loading ? <CircularProgress size={16} /> : <EditIcon />}
        >
          {loading ? 'Updating...' : 'Update Schedule'}
        </Button>
      </DialogActions>
      </Dialog>
    </>
  );
};

const DeleteConfirmationDialog: React.FC<DeleteConfirmationDialogProps> = ({
  open,
  schedule,
  onClose,
  onConfirm,
  loading = false
}) => {
  if (!schedule) return null;

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
          <Typography variant="h6">Delete Schedule</Typography>
        </Stack>
      </DialogTitle>
      <DialogContent>
        <Stack spacing={2}>
          <Alert severity="warning">
            <Typography variant="body1" gutterBottom>
              <strong>Are you sure you want to delete this schedule?</strong>
            </Typography>
            <Typography variant="body2">
              This action cannot be undone. The schedule and its execution history will be permanently removed.
            </Typography>
          </Alert>

          <Card variant="outlined">
            <CardContent>
              <Typography variant="subtitle1" gutterBottom>
                Schedule to Delete
              </Typography>
              <Stack spacing={1}>
                <Typography variant="body2">
                  <strong>Name:</strong> {schedule.experiment_name}
                </Typography>
                <Typography variant="body2">
                  <strong>Type:</strong> {formatScheduleType(schedule.schedule_type, schedule.interval_hours)}
                </Typography>
                <Typography variant="body2">
                  <strong>Duration:</strong> {schedule.estimated_duration} minutes
                </Typography>
                <Typography variant="body2">
                  <strong>Created:</strong> {new Date(schedule.created_at).toLocaleString()}
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
          {loading ? 'Deleting...' : 'Delete Schedule'}
        </Button>
      </DialogActions>
    </Dialog>
  );
};

const ScheduleActions: React.FC<ScheduleActionsProps> = ({
  selectedSchedule,
  onCreateSchedule,
  onUpdateSchedule,
  onDeleteSchedule,
  onRequireRecovery,
  onResolveRecovery,
  operationStatus,
  disabled = false
}) => {
  const [dialogs, setDialogs] = useState({
    create: false,
    edit: false,
    delete: false
  });

  const isOperationInProgress = operationStatus !== SchedulingOperationStatus.Idle && 
                                operationStatus !== SchedulingOperationStatus.Error;

  const handleCreateSchedule = async (data: CreateScheduleFormData) => {
    await onCreateSchedule(data);
  };

  const handleUpdateSchedule = async (scheduleId: string, data: UpdateScheduleRequest) => {
    await onUpdateSchedule(scheduleId, data);
  };

  const handleDeleteConfirm = async () => {
    if (selectedSchedule) {
      await onDeleteSchedule(selectedSchedule);
    }
  };

  const handleRequireRecovery = async () => {
    if (!selectedSchedule) {
      return;
    }
    const defaultNote = selectedSchedule.recovery_note || '';
    const noteInput = window.prompt('Add a recovery note (optional)', defaultNote);
    if (noteInput === null) {
      return;
    }
    try {
      const note = noteInput.trim() ? noteInput.trim() : undefined;
      await onRequireRecovery(selectedSchedule.schedule_id, note);
    } catch (error) {
      console.error('Failed to require recovery:', error);
    }
  };

  const handleResolveRecovery = async () => {
    if (!selectedSchedule) {
      return;
    }
    const noteInput = window.prompt('Optional note when resolving recovery', selectedSchedule.recovery_note || '');
    if (noteInput === null) {
      return;
    }
    try {
      const note = noteInput.trim() ? noteInput.trim() : undefined;
      await onResolveRecovery(selectedSchedule.schedule_id, note);
    } catch (error) {
      console.error('Failed to resolve recovery:', error);
    }
  };

  const openDialog = (type: 'create' | 'edit' | 'delete') => {
    setDialogs(prev => ({ ...prev, [type]: true }));
  };

  const closeDialog = (type: 'create' | 'edit' | 'delete') => {
    setDialogs(prev => ({ ...prev, [type]: false }));
    if (typeof document !== 'undefined') {
      document.body.style.overflow = '';
      if (typeof document.body.style.removeProperty === 'function') {
        document.body.style.removeProperty('padding-right');
      }
    }
  };

  const renderOperationStatus = () => {
    if (operationStatus === SchedulingOperationStatus.Idle) return null;

    const statusConfig = {
      [SchedulingOperationStatus.Creating]: { color: 'info', text: 'Creating schedule...' },
      [SchedulingOperationStatus.Updating]: { color: 'info', text: 'Updating schedule...' },
      [SchedulingOperationStatus.Deleting]: { color: 'error', text: 'Deleting schedule...' },
      [SchedulingOperationStatus.Starting]: { color: 'success', text: 'Starting scheduler...' },
      [SchedulingOperationStatus.Stopping]: { color: 'warning', text: 'Stopping scheduler...' },
      [SchedulingOperationStatus.Loading]: { color: 'info', text: 'Loading...' },
      [SchedulingOperationStatus.Error]: { color: 'error', text: 'Operation failed' }
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

        {/* Edit Schedule Button */}
        <Button
          variant="outlined"
          startIcon={<EditIcon />}
          onClick={() => openDialog('edit')}
          disabled={disabled || !selectedSchedule || isOperationInProgress}
        >
          Edit Schedule
        </Button>

        {/* Delete Schedule Button */}
        <Button
          variant="outlined"
          color="error"
          startIcon={<DeleteIcon />}
          onClick={() => openDialog('delete')}
          disabled={disabled || !selectedSchedule || isOperationInProgress}
        >
          Delete Schedule
        </Button>
      </Stack>

      {/* Selection Status */}
      {selectedSchedule && (
        <Box sx={{ mt: 2 }}>
          <Stack spacing={1}>
            <Chip
              icon={<ScheduleIcon />}
              label={`Selected: ${selectedSchedule.experiment_name}${selectedSchedule.recovery_required ? ' (Recovery Required)' : ''}`}
              variant="outlined"
              color="primary"
              size="small"
            />
            <Alert severity={selectedSchedule.recovery_required ? 'warning' : 'info'}>
              <Stack spacing={0.5}>
                <Typography variant="body2">
                  {selectedSchedule.recovery_required
                    ? 'Manual recovery is required before this schedule will run automatically.'
                    : 'No manual recovery pending.'}
                </Typography>
                {selectedSchedule.recovery_note && (
                  <Typography variant="caption" color="text.secondary">
                    Note: {selectedSchedule.recovery_note}
                  </Typography>
                )}
                {selectedSchedule.recovery_marked_at && (
                  <Typography variant="caption" color="text.secondary">
                    Marked by {selectedSchedule.recovery_marked_by || 'system'} on{' '}
                    {new Date(selectedSchedule.recovery_marked_at).toLocaleString()}
                  </Typography>
                )}
                {!selectedSchedule.recovery_required && selectedSchedule.recovery_resolved_at && (
                  <Typography variant="caption" color="text.secondary">
                    Resolved by {selectedSchedule.recovery_resolved_by || 'system'} on{' '}
                    {new Date(selectedSchedule.recovery_resolved_at).toLocaleString()}
                  </Typography>
                )}
              </Stack>
            </Alert>
            <Stack direction="row" spacing={1}>
              {selectedSchedule.recovery_required ? (
                <Button
                  variant="contained"
                  color="success"
                  onClick={handleResolveRecovery}
                  disabled={disabled || isOperationInProgress}
                >
                  Resolve Recovery
                </Button>
              ) : (
                <Button
                  variant="outlined"
                  color="warning"
                  onClick={handleRequireRecovery}
                  disabled={disabled || isOperationInProgress}
                >
                  Require Recovery
                </Button>
              )}
            </Stack>
          </Stack>
        </Box>
      )}

      {/* Dialogs */}
      <CreateScheduleDialog
        open={dialogs.create}
        onClose={() => closeDialog('create')}
        onSubmit={handleCreateSchedule}
        loading={operationStatus === SchedulingOperationStatus.Creating}
      />

      <EditScheduleDialog
        open={dialogs.edit}
        schedule={selectedSchedule}
        onClose={() => closeDialog('edit')}
        onSubmit={handleUpdateSchedule}
        loading={operationStatus === SchedulingOperationStatus.Updating}
      />

      <DeleteConfirmationDialog
        open={dialogs.delete}
        schedule={selectedSchedule}
        onClose={() => closeDialog('delete')}
        onConfirm={handleDeleteConfirm}
        loading={operationStatus === SchedulingOperationStatus.Deleting}
      />
    </>
  );
};

export default ScheduleActions;
export { CreateScheduleDialog, EditScheduleDialog, DeleteConfirmationDialog };


