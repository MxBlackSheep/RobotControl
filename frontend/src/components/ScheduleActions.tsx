/**
 * Schedule deletion confirmation. The schedule form is ImprovedScheduleForm.
 */

import React from 'react';
import {
  Button,
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  Typography,
  Alert,
  Stack,
  CircularProgress,
  Card,
  CardContent,
} from '@mui/material';
import { Delete as DeleteIcon } from '@mui/icons-material';

import { ScheduledExperiment, formatScheduleType } from '../types/scheduling';

interface DeleteConfirmationDialogProps {
  open: boolean;
  schedule: ScheduledExperiment | null;
  onClose: () => void;
  onConfirm: () => Promise<void>;
  loading?: boolean;
}

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
          disabled={loading || Boolean(schedule?.recovery_required)}
          startIcon={loading ? <CircularProgress size={16} /> : <DeleteIcon />}
        >
          {loading ? 'Deleting...' : 'Delete Schedule'}
        </Button>
      </DialogActions>
    </Dialog>
  );
};

export { DeleteConfirmationDialog };
