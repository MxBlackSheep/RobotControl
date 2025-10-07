/**
 * CreateScheduleDialog - Dialog for creating new schedules
 * 
 * Extracted from ScheduleActions.tsx to improve maintainability
 * Handles comprehensive form validation and schedule creation
 */

import React, { useState, useEffect } from 'react';
import {
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  TextField,
  Button,
  Typography,
  Stack,
  Card,
  CardContent,
  Divider,
  FormControl,
  InputLabel,
  Select,
  MenuItem,
  Grid,
  FormControlLabel,
  Checkbox,
  Switch,
  InputAdornment
} from '@mui/material';
import {
  Schedule as ScheduleIcon,
  AccessTime as ClockIcon,
  Info as InfoIcon
} from '@mui/icons-material';
import { ButtonLoading } from '../LoadingSpinner';
import ErrorAlert from '../ErrorAlert';

export interface CreateScheduleDialogProps {
  open: boolean;
  onClose: () => void;
  onSubmit: (scheduleData: any) => Promise<void>;
}

const CreateScheduleDialog: React.FC<CreateScheduleDialogProps> = ({
  open,
  onClose,
  onSubmit
}) => {
  const [formData, setFormData] = useState({
    name: '',
    experiment_name: '',
    start_time: '',
    end_time: '',
    interval_minutes: 60,
    repeat_count: 1,
    is_recurring: false,
    description: '',
    priority: 'medium' as 'low' | 'medium' | 'high',
    enabled: true,
    max_retries: 3,
    retry_delay_minutes: 5
  });

  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [formErrors, setFormErrors] = useState<Record<string, string>>({});

  // Reset form when dialog opens/closes
  useEffect(() => {
    if (open) {
      setFormData({
        name: '',
        experiment_name: '',
        start_time: '',
        end_time: '',
        interval_minutes: 60,
        repeat_count: 1,
        is_recurring: false,
        description: '',
        priority: 'medium',
        enabled: true,
        max_retries: 3,
        retry_delay_minutes: 5
      });
      setError('');
      setFormErrors({});
    }
  }, [open]);

  const handleInputChange = (field: string, value: any) => {
    setFormData(prev => ({ ...prev, [field]: value }));
    // Clear field error when user starts typing
    if (formErrors[field]) {
      setFormErrors(prev => ({ ...prev, [field]: '' }));
    }
  };

  const validateForm = (): boolean => {
    const errors: Record<string, string> = {};

    if (!formData.name.trim()) {
      errors.name = 'Schedule name is required';
    }

    if (!formData.experiment_name.trim()) {
      errors.experiment_name = 'Experiment name is required';
    }

    if (!formData.start_time) {
      errors.start_time = 'Start time is required';
    }

    if (formData.is_recurring) {
      if (!formData.end_time) {
        errors.end_time = 'End time is required for recurring schedules';
      } else if (new Date(formData.end_time) <= new Date(formData.start_time)) {
        errors.end_time = 'End time must be after start time';
      }

      if (formData.interval_minutes < 1) {
        errors.interval_minutes = 'Interval must be at least 1 minute';
      }
    }

    if (formData.repeat_count < 1) {
      errors.repeat_count = 'Repeat count must be at least 1';
    }

    setFormErrors(errors);
    return Object.keys(errors).length === 0;
  };

  const handleSubmit = async () => {
    if (!validateForm()) return;

    setLoading(true);
    try {
      await onSubmit(formData);
      handleClose();
    } catch (err: any) {
      setError(err.message || 'Failed to create schedule');
    } finally {
      setLoading(false);
    }
  };

  const handleClose = () => {
    if (!loading) {
      onClose();
    }
  };

  return (
    <Dialog open={open} onClose={handleClose} maxWidth="md" fullWidth>
      <DialogTitle>
        <Stack direction="row" alignItems="center" spacing={1}>
          <ScheduleIcon />
          <Typography variant="h6">Create New Schedule</Typography>
        </Stack>
      </DialogTitle>

      <DialogContent>
        {error && (
          <ErrorAlert
            message={error}
            severity="error"
            onClose={() => setError('')}
            sx={{ mb: 2 }}
          />
        )}

        <Grid container spacing={2} sx={{ mt: 1 }}>
          {/* Basic Information */}
          <Grid item xs={12}>
            <Typography variant="subtitle1" gutterBottom sx={{ fontWeight: 'bold' }}>
              Basic Information
            </Typography>
          </Grid>

          <Grid item xs={12} sm={6}>
            <TextField
              fullWidth
              label="Schedule Name"
              value={formData.name}
              onChange={(e) => handleInputChange('name', e.target.value)}
              error={!!formErrors.name}
              helperText={formErrors.name}
              required
            />
          </Grid>

          <Grid item xs={12} sm={6}>
            <TextField
              fullWidth
              label="Experiment Name"
              value={formData.experiment_name}
              onChange={(e) => handleInputChange('experiment_name', e.target.value)}
              error={!!formErrors.experiment_name}
              helperText={formErrors.experiment_name}
              required
            />
          </Grid>

          <Grid item xs={12}>
            <TextField
              fullWidth
              label="Description"
              value={formData.description}
              onChange={(e) => handleInputChange('description', e.target.value)}
              multiline
              rows={2}
              placeholder="Optional description of the schedule..."
            />
          </Grid>

          {/* Timing Configuration */}
          <Grid item xs={12}>
            <Divider sx={{ my: 2 }} />
            <Typography variant="subtitle1" gutterBottom sx={{ fontWeight: 'bold' }}>
              <ClockIcon sx={{ mr: 1, verticalAlign: 'middle' }} />
              Timing Configuration
            </Typography>
          </Grid>

          <Grid item xs={12} sm={6}>
            <TextField
              fullWidth
              label="Start Time"
              type="datetime-local"
              value={formData.start_time}
              onChange={(e) => handleInputChange('start_time', e.target.value)}
              error={!!formErrors.start_time}
              helperText={formErrors.start_time}
              required
              InputLabelProps={{ shrink: true }}
            />
          </Grid>

          <Grid item xs={12} sm={6}>
            <FormControlLabel
              control={
                <Switch
                  checked={formData.is_recurring}
                  onChange={(e) => handleInputChange('is_recurring', e.target.checked)}
                />
              }
              label="Recurring Schedule"
            />
          </Grid>

          {formData.is_recurring && (
            <>
              <Grid item xs={12} sm={6}>
                <TextField
                  fullWidth
                  label="End Time"
                  type="datetime-local"
                  value={formData.end_time}
                  onChange={(e) => handleInputChange('end_time', e.target.value)}
                  error={!!formErrors.end_time}
                  helperText={formErrors.end_time}
                  required
                  InputLabelProps={{ shrink: true }}
                />
              </Grid>

              <Grid item xs={12} sm={6}>
                <TextField
                  fullWidth
                  label="Interval"
                  type="number"
                  value={formData.interval_minutes}
                  onChange={(e) => handleInputChange('interval_minutes', parseInt(e.target.value))}
                  error={!!formErrors.interval_minutes}
                  helperText={formErrors.interval_minutes}
                  InputProps={{
                    endAdornment: <InputAdornment position="end">minutes</InputAdornment>
                  }}
                  inputProps={{ min: 1 }}
                />
              </Grid>
            </>
          )}

          <Grid item xs={12} sm={6}>
            <TextField
              fullWidth
              label="Repeat Count"
              type="number"
              value={formData.repeat_count}
              onChange={(e) => handleInputChange('repeat_count', parseInt(e.target.value))}
              error={!!formErrors.repeat_count}
              helperText={formErrors.repeat_count || 'Number of times to execute'}
              inputProps={{ min: 1 }}
            />
          </Grid>

          {/* Advanced Options */}
          <Grid item xs={12}>
            <Divider sx={{ my: 2 }} />
            <Typography variant="subtitle1" gutterBottom sx={{ fontWeight: 'bold' }}>
              Advanced Options
            </Typography>
          </Grid>

          <Grid item xs={12} sm={4}>
            <FormControl fullWidth>
              <InputLabel>Priority</InputLabel>
              <Select
                value={formData.priority}
                onChange={(e) => handleInputChange('priority', e.target.value)}
              >
                <MenuItem value="low">Low</MenuItem>
                <MenuItem value="medium">Medium</MenuItem>
                <MenuItem value="high">High</MenuItem>
              </Select>
            </FormControl>
          </Grid>

          <Grid item xs={12} sm={4}>
            <TextField
              fullWidth
              label="Max Retries"
              type="number"
              value={formData.max_retries}
              onChange={(e) => handleInputChange('max_retries', parseInt(e.target.value))}
              inputProps={{ min: 0, max: 10 }}
            />
          </Grid>

          <Grid item xs={12} sm={4}>
            <TextField
              fullWidth
              label="Retry Delay"
              type="number"
              value={formData.retry_delay_minutes}
              onChange={(e) => handleInputChange('retry_delay_minutes', parseInt(e.target.value))}
              InputProps={{
                endAdornment: <InputAdornment position="end">minutes</InputAdornment>
              }}
              inputProps={{ min: 1 }}
            />
          </Grid>

          <Grid item xs={12}>
            <FormControlLabel
              control={
                <Checkbox
                  checked={formData.enabled}
                  onChange={(e) => handleInputChange('enabled', e.target.checked)}
                />
              }
              label="Enable schedule immediately after creation"
            />
          </Grid>

          {/* Information Card */}
          <Grid item xs={12}>
            <Card variant="outlined" sx={{ bgcolor: 'info.light', color: 'info.contrastText' }}>
              <CardContent sx={{ py: 1 }}>
                <Stack direction="row" alignItems="center" spacing={1}>
                  <InfoIcon fontSize="small" />
                  <Typography variant="body2">
                    All times are in local timezone. Recurring schedules will run from start time to end time at the specified interval.
                  </Typography>
                </Stack>
              </CardContent>
            </Card>
          </Grid>
        </Grid>
      </DialogContent>

      <DialogActions>
        <Button onClick={handleClose} disabled={loading}>
          Cancel
        </Button>
        <Button
          onClick={handleSubmit}
          variant="contained"
          disabled={loading}
        >
          {loading ? <ButtonLoading /> : 'Create Schedule'}
        </Button>
      </DialogActions>
    </Dialog>
  );
};

export default CreateScheduleDialog;