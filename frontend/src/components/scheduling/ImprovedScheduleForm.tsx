/**
 * Improved Schedule Form Component
 * 
 * Modular form for creating and editing scheduled experiments.
 * Follows "let the user choose" principle with dropdowns instead of text input.
 * 
 * Features:
 * - Experiment selection from discovered files (grouped by category)
 * - Prerequisite checkboxes with clear descriptions
 * - Auto-populated fields based on selection
 * - Validation and error handling
 * - Responsive layout
 */

import React, { useState, useEffect, useCallback, useMemo } from 'react';
import { useModalFocus } from '../../hooks/useModalFocus';
import StatusDialog, { StatusSeverity } from '../StatusDialog';
import {
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  TextField,
  Button,
  Box,
  Alert,
  FormControl,
  InputLabel,
  Select,
  MenuItem,
  Typography,
  Chip,
  FormControlLabel,
  CircularProgress,
  Stack,
  Accordion,
  AccordionSummary,
  AccordionDetails,
  Grid,
  InputAdornment,
  Tooltip,
  IconButton,
  ListSubheader,
  Radio,
  RadioGroup,
  FormLabel,
  Switch,
  Autocomplete,
  Checkbox
} from '@mui/material';
import {
  Add as AddIcon,
  Science as ScienceIcon,
  Schedule as ScheduleIcon,
  Settings as SettingsIcon,
  ExpandMore as ExpandMoreIcon,
  Refresh as RefreshIcon,
  FolderOpen as FolderIcon,
  CheckBoxOutlineBlank as CheckBoxOutlineBlankIcon,
  CheckBox as CheckBoxIcon
} from '@mui/icons-material';
import { schedulingAPI, schedulingService } from '../../services/schedulingApi';
import { EvoYeastExperimentOption, NotificationContact } from '../../types/scheduling';

interface ExperimentFile {
  name: string;
  path: string;
  category: string;
  description: string;
  last_modified: string | null;
  file_size: number;
}

interface ScheduleFormData {
  experiment_name: string;
  experiment_path: string;
  schedule_type: 'once' | 'interval' | 'daily' | 'weekly';
  interval_hours: number;
  start_time: string | null;
  estimated_duration: number;
  prerequisites: string[];
  notification_contacts: string[];
  is_active: boolean;
  max_retries: number;
  retry_delay_minutes: number;
  backoff_strategy: 'linear' | 'exponential';
}

interface ImprovedScheduleFormProps {
  open: boolean;
  onClose: () => void;
  onSubmit: (data: ScheduleFormData) => Promise<void>;
  initialData?: Partial<ScheduleFormData>;
  mode?: 'create' | 'edit';
  contacts: NotificationContact[];
}

const ImprovedScheduleForm: React.FC<ImprovedScheduleFormProps> = ({
  open,
  onClose,
  onSubmit,
  initialData,
  mode = 'create',
  contacts,
}) => {
  // Form state
  const [formData, setFormData] = useState<ScheduleFormData>({
    experiment_name: '',
    experiment_path: '',
    schedule_type: 'once',
    interval_hours: 6,
    start_time: null,
    estimated_duration: 55,
    prerequisites: initialData?.prerequisites ?? [],
    notification_contacts: initialData?.notification_contacts ?? [],
    is_active: true,
    max_retries: 3,
    retry_delay_minutes: 2,
    backoff_strategy: 'linear',
    ...initialData
  });

  const intervalPresets = [
    { label: 'Every 6 hours', value: '6', hours: 6 },
    { label: 'Every 8 hours', value: '8', hours: 8 },
    { label: 'Every 12 hours', value: '12', hours: 12 },
    { label: 'Daily (24 hours)', value: '24', hours: 24 },
  ];

  const computeCustomInterval = (hoursValue: number | undefined) => {
    const safeHours = typeof hoursValue === "number" && !Number.isNaN(hoursValue) ? hoursValue : 0;
    const totalMinutes = Math.max(1, Math.round(safeHours * 60));
    return {
      hours: Math.floor(totalMinutes / 60),
      minutes: totalMinutes % 60,
    };
  };

  const [intervalSelection, setIntervalSelection] = useState<string>(() => {
    const preset = intervalPresets.find(p => p.hours === (initialData?.interval_hours ?? 6));
    return preset ? preset.value : 'custom';
  });

  const [customInterval, setCustomInterval] = useState<{ hours: number; minutes: number }>(() => {
    if (initialData?.interval_hours && !intervalPresets.some(p => p.hours === initialData.interval_hours)) {
      return computeCustomInterval(initialData.interval_hours);
    }
    return { hours: 1, minutes: 0 };
  });

  const checkboxIcon = <CheckBoxOutlineBlankIcon fontSize="small" />;
  const checkboxCheckedIcon = <CheckBoxIcon fontSize="small" />;
  const selectedContacts = useMemo(
    () => contacts.filter((contact) => formData.notification_contacts.includes(contact.contact_id)),
    [contacts, formData.notification_contacts],
  );


  useEffect(() => {
    if (formData.schedule_type !== 'interval') {
      return;
    }

    const preset = intervalPresets.find(p => p.hours === formData.interval_hours);
    if (preset) {
      setIntervalSelection(preset.value);
    } else if (typeof formData.interval_hours === 'number' && !Number.isNaN(formData.interval_hours)) {
      setIntervalSelection('custom');
      setCustomInterval(computeCustomInterval(formData.interval_hours));
    }
  }, [formData.schedule_type, formData.interval_hours, open]);

  const handleIntervalSelectionChange = (value: string) => {
    setIntervalSelection(value);
    if (value === 'custom') {
      const totalMinutes = customInterval.hours * 60 + customInterval.minutes;
      if (totalMinutes <= 0) {
        setCustomInterval({ hours: 1, minutes: 0 });
        setFormData(prev => ({ ...prev, interval_hours: 1 }));
      } else {
        setFormData(prev => ({ ...prev, interval_hours: totalMinutes / 60 }));
      }
    } else {
      const hoursValue = Number(value);
      setFormData(prev => ({ ...prev, interval_hours: hoursValue }));
    }
  };

  const handleCustomIntervalChange = (part: 'hours' | 'minutes', rawValue: number) => {
    const parsed = Number.isFinite(rawValue) ? Math.floor(rawValue) : 0;
    const next = {
      hours: part === 'hours' ? Math.max(0, parsed) : customInterval.hours,
      minutes: part === 'minutes' ? Math.max(0, Math.min(59, parsed)) : customInterval.minutes,
    };
    setCustomInterval(next);
    setIntervalSelection('custom');
    const totalMinutes = next.hours * 60 + next.minutes;
    setFormData(prev => ({ ...prev, interval_hours: totalMinutes > 0 ? totalMinutes / 60 : 0 }));
  };

  // UI state
  const [loading, setLoading] = useState(false);
  const [scanning, setScanning] = useState(false);
  const [experiments, setExperiments] = useState<ExperimentFile[]>([]);
  const [categorizedExperiments, setCategorizedExperiments] = useState<Record<string, ExperimentFile[]>>({});
  const [evoExperiments, setEvoExperiments] = useState<EvoYeastExperimentOption[]>([]);
  const [evoLoading, setEvoLoading] = useState(false);
  const [selectedExperimentId, setSelectedExperimentId] = useState<string>('');
  const [experimentPrepOption, setExperimentPrepOption] = useState<'none' | 'schedule'>('none');
  const [expandedSections, setExpandedSections] = useState({
    experiment: true,
    schedule: true,
    preparation: false
  });
  const [statusDialog, setStatusDialog] = useState<{
    open: boolean;
    title: string;
    message: string;
    severity: StatusSeverity;
    autoCloseMs?: number;
  }>({ open: false, title: '', message: '', severity: 'info' });

  const showStatusDialog = ({
    title = '',
    message,
    severity = 'info',
    autoCloseMs,
  }: {
    title?: string;
    message: string;
    severity?: StatusSeverity;
    autoCloseMs?: number;
  }) => {
    setStatusDialog({ open: true, title, message, severity, autoCloseMs });
  };

  const closeStatusDialog = () => {
    setStatusDialog((prev) => ({ ...prev, open: false }));
  };

  // Add modal focus management
  const { modalRef } = useModalFocus({
    isOpen: open,
    onClose,
    initialFocusSelector: 'select[aria-label*="Select Experiment"]',
    restoreFocus: true,
    trapFocus: true,
    closeOnEscape: !loading // Don't close on escape when loading
  });

  const loadExperiments = useCallback(async (rescan: boolean = false) => {
    try {
      setScanning(true);
      const response = await schedulingAPI.getAvailableExperiments(rescan);
      
      if (response.data.success) {
        setExperiments(response.data.data.experiments);
        setCategorizedExperiments(response.data.data.categorized);
      }
    } catch (error) {
      console.error('Failed to load experiments:', error);
      const detail = error instanceof Error ? error.message : undefined;
      showStatusDialog({
        title: 'Failed to load experiments',
        message: detail
          ? `Unable to load available experiments.\n${detail}`
          : 'Unable to load available experiments. Please try again.',
        severity: 'error',
      });
    } finally {
      setScanning(false);
    }
  }, []);

  const loadEvoExperiments = useCallback(async (limit: number = 100) => {
    try {
      setEvoLoading(true);
      const result = await schedulingService.getEvoYeastExperiments(limit);
      if (!result.error) {
        setEvoExperiments(result.experiments);
      } else {
        console.error(result.error);
      }
    } catch (error) {
      console.error('Failed to load EvoYeast experiments:', error);
    } finally {
      setEvoLoading(false);
    }
  }, []);

  useEffect(() => {
    if (!open) {
      return;
    }

    const defaultFormData: ScheduleFormData = {
      experiment_name: '',
      experiment_path: '',
      schedule_type: 'once',
      interval_hours: 6,
      start_time: null,
      estimated_duration: 55,
      prerequisites: [],
      notification_contacts: [],
      is_active: true,
      max_retries: 3,
      retry_delay_minutes: 2,
      backoff_strategy: 'linear',
    };

    const initialPrereqs = initialData?.prerequisites ?? [];
    const mergedData: ScheduleFormData = {
      ...defaultFormData,
      ...initialData,
      start_time: initialData?.start_time ?? null,
      prerequisites: initialPrereqs,
      notification_contacts: initialData?.notification_contacts ?? defaultFormData.notification_contacts,
      max_retries: initialData?.max_retries ?? defaultFormData.max_retries,
      retry_delay_minutes: initialData?.retry_delay_minutes ?? defaultFormData.retry_delay_minutes,
      backoff_strategy: initialData?.backoff_strategy ?? defaultFormData.backoff_strategy,
    };

    setFormData(mergedData);

    const hasScheduledFlag = initialPrereqs.includes('ScheduledToRun');
    setExperimentPrepOption(hasScheduledFlag ? 'schedule' : 'none');

    if (hasScheduledFlag) {
      const evoEntry = initialPrereqs.find((entry) => entry.startsWith('EvoYeastExperiment:'));
      if (evoEntry) {
        const payload = evoEntry.split(':')[1] ?? '';
        const [experimentId] = payload.split('|');
        setSelectedExperimentId(experimentId || '');
      } else {
        setSelectedExperimentId('');
      }
    } else {
      setSelectedExperimentId('');
    }

    const intervalHours =
      typeof mergedData.interval_hours === 'number' && !Number.isNaN(mergedData.interval_hours)
        ? mergedData.interval_hours
        : defaultFormData.interval_hours;

    if (mergedData.schedule_type === 'interval') {
      const preset = intervalPresets.find((preset) => preset.hours === intervalHours);
      setIntervalSelection(preset ? preset.value : 'custom');
      setCustomInterval(computeCustomInterval(intervalHours));
    } else {
      setIntervalSelection('custom');
      setCustomInterval({ hours: 1, minutes: 0 });
    }

    loadExperiments();
    loadEvoExperiments();
  }, [open, initialData, loadExperiments, loadEvoExperiments]);

  useEffect(() => {
    if (!open) {
      return;
    }

    setFormData((prev) => {
      const nextPrereqs =
        experimentPrepOption === 'schedule'
          ? [
              'ScheduledToRun',
              ...(selectedExperimentId ? [`EvoYeastExperiment:${selectedExperimentId}|set`] : []),
            ]
          : [];

      const isSame =
        prev.prerequisites.length === nextPrereqs.length &&
        prev.prerequisites.every((value, index) => value === nextPrereqs[index]);

      if (isSame) {
        return prev;
      }

      return { ...prev, prerequisites: nextPrereqs };
    });
  }, [experimentPrepOption, selectedExperimentId, open]);

  const handleExperimentPrepChange = (value: 'none' | 'schedule') => {
    setExperimentPrepOption(value);
    if (value === 'none') {
      setSelectedExperimentId('');
    }
  };

  const handleExperimentSelect = (experimentPath: string) => {
    const selectedExperiment = experiments.find(exp => exp.path === experimentPath);
    
    if (selectedExperiment) {
      setFormData(prev => ({
        ...prev,
        experiment_path: selectedExperiment.path,
        experiment_name: selectedExperiment.name
      }));
    }
  };

  const validateForm = (): boolean => {
    const newErrors: string[] = [];

    if (!formData.experiment_path) {
      newErrors.push('Please select an experiment');
    }

    if (!formData.experiment_name) {
      newErrors.push('Experiment name is required');
    }

    if (formData.estimated_duration <= 0) {
      newErrors.push('Estimated duration must be greater than 0');
    }

    if (formData.schedule_type === 'interval' && formData.interval_hours <= 0) {
      newErrors.push('Interval must be greater than 0 minutes');
    }

    if (experimentPrepOption === 'schedule' && !selectedExperimentId) {
      newErrors.push('Select an experiment to prepare before execution');
    }

    if (newErrors.length > 0) {
      showStatusDialog({
        title: 'Check schedule details',
        message: newErrors.join('\n'),
        severity: 'warning',
      });
      return false;
    }

    return true;
  };

  const handleSubmit = async () => {
    if (!validateForm()) {
      return;
    }

    try {
      setLoading(true);
      await onSubmit(formData);
      onClose();
    } catch (error) {
      showStatusDialog({
        title: 'Save failed',
        message: error instanceof Error ? error.message : 'Failed to save schedule',
        severity: 'error',
      });
    } finally {
      setLoading(false);
    }
  };

  const toggleSection = (section: keyof typeof expandedSections) => {
    setExpandedSections(prev => ({
      ...prev,
      [section]: !prev[section]
    }));
  };

  return (
    <>
      <Dialog
      ref={modalRef}
      open={open} 
      onClose={!loading ? onClose : undefined}
      maxWidth="md"
      fullWidth
      PaperProps={{ sx: { maxHeight: '90vh' } }}
      aria-labelledby="schedule-dialog-title"
      aria-describedby="schedule-dialog-description"
      disableEscapeKeyDown={loading}
    >
      <DialogTitle id="schedule-dialog-title">
        <Stack direction="row" alignItems="center" spacing={1}>
          <AddIcon color="primary" aria-hidden="true" />
          <Typography variant="h6">
            {mode === 'create' ? 'Create New Schedule' : 'Edit Schedule'}
          </Typography>
        </Stack>
      </DialogTitle>

      <DialogContent dividers id="schedule-dialog-description">
        <Stack spacing={2}>
          {/* Experiment Selection Section */}
          <Accordion 
            expanded={expandedSections.experiment}
            onChange={() => toggleSection('experiment')}
          >
            <AccordionSummary expandIcon={<ExpandMoreIcon />}>
              <Stack direction="row" alignItems="center" spacing={1}>
                <ScienceIcon color="primary" />
                <Typography variant="subtitle1">Experiment Selection</Typography>
              </Stack>
            </AccordionSummary>
            <AccordionDetails>
              <Stack spacing={2}>
                <Box display="flex" alignItems="center" gap={1}>
                  <FormControl fullWidth>
                    <InputLabel>Select Experiment</InputLabel>
                    <Select
                      value={formData.experiment_path}
                      onChange={(e) => handleExperimentSelect(e.target.value)}
                      label="Select Experiment"
                      disabled={loading || scanning}
                    >
                      {Object.entries(categorizedExperiments).map(([category, exps]) => [
                        <ListSubheader key={`header-${category}`}>
                          <Stack direction="row" alignItems="center" spacing={1}>
                            <FolderIcon fontSize="small" />
                            <Typography variant="caption">{category}</Typography>
                          </Stack>
                        </ListSubheader>,
                        ...exps.map(exp => (
                          <MenuItem key={exp.path} value={exp.path}>
                            <Box width="100%">
                              <Typography variant="body2">{exp.name}</Typography>
                              <Typography variant="caption" color="text.secondary">
                                {exp.description}
                              </Typography>
                            </Box>
                          </MenuItem>
                        ))
                      ])}
                    </Select>
                  </FormControl>
                  <Tooltip title="Rescan for experiments">
                    <IconButton 
                      onClick={() => loadExperiments(true)}
                      disabled={scanning}
                    >
                      {scanning ? <CircularProgress size={24} /> : <RefreshIcon />}
                    </IconButton>
                  </Tooltip>
                </Box>

                {formData.experiment_path && (
                  <Alert severity="info" variant="outlined">
                    <Typography variant="caption">
                      Selected: {formData.experiment_name}
                    </Typography>
                    <br />
                    <Typography variant="caption" color="text.secondary">
                      Path: {formData.experiment_path}
                    </Typography>
                  </Alert>
                )}

                <TextField
                  label="Estimated Duration (minutes)"
                  type="number"
                  value={formData.estimated_duration}
                  onChange={(e) => setFormData({ ...formData, estimated_duration: Number(e.target.value) })}
                  fullWidth
                  InputProps={{
                    endAdornment: <InputAdornment position="end">min</InputAdornment>
                  }}
                  helperText="How long this experiment typically takes to complete"
                />
              </Stack>
            </AccordionDetails>
          </Accordion>

          {/* Schedule Configuration Section */}
          <Accordion
            expanded={expandedSections.schedule}
            onChange={() => toggleSection('schedule')}
          >
            <AccordionSummary expandIcon={<ExpandMoreIcon />}>
              <Stack direction="row" alignItems="center" spacing={1}>
                <ScheduleIcon color="primary" />
                <Typography variant="subtitle1">Schedule Configuration</Typography>
              </Stack>
            </AccordionSummary>
            <AccordionDetails>
              <Grid container spacing={2}>
                <Grid item xs={12} md={6}>
                  <FormControl fullWidth>
                    <InputLabel>Schedule Type</InputLabel>
                    <Select
                      value={formData.schedule_type}
                      onChange={(e) => setFormData({ ...formData, schedule_type: e.target.value as any })}
                      label="Schedule Type"
                    >
                      <MenuItem value="once">Run Once</MenuItem>
                      <MenuItem value="interval">Fixed Interval</MenuItem>
                      <MenuItem value="daily">Daily</MenuItem>
                      <MenuItem value="weekly">Weekly</MenuItem>
                    </Select>
                  </FormControl>
                </Grid>

                {formData.schedule_type === 'interval' && (
                  <Grid item xs={12} md={6}>
                    <FormControl fullWidth>
                      <InputLabel>Interval</InputLabel>
                      <Select
                        value={intervalSelection}
                        onChange={(e) => handleIntervalSelectionChange(e.target.value as string)}
                        label="Interval"
                      >
                        {intervalPresets.map(preset => (
                          <MenuItem key={preset.value} value={preset.value}>
                            {preset.label}
                          </MenuItem>
                        ))}
                        <MenuItem value="custom">Custom interval</MenuItem>
                      </Select>
                    </FormControl>
                    {intervalSelection === 'custom' && (
                      <>
                        <Stack
                          direction={{ xs: 'column', sm: 'row' }}
                          spacing={2}
                          sx={{ mt: 2 }}
                        >
                          <TextField
                            label="Hours"
                            type="number"
                            inputProps={{ min: 0 }}
                            value={customInterval.hours}
                            onChange={(e) => handleCustomIntervalChange('hours', Number(e.target.value))}
                            fullWidth
                          />
                          <TextField
                            label="Minutes"
                            type="number"
                            inputProps={{ min: 0, max: 59 }}
                            value={customInterval.minutes}
                            onChange={(e) => handleCustomIntervalChange('minutes', Number(e.target.value))}
                            fullWidth
                          />
                        </Stack>
                        <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mt: 1 }}>
                          Minutes must be between 0 and 59. Minimum interval is 1 minute.
                        </Typography>
                      </>
                    )}
                  </Grid>
                )}

                <Grid item xs={12}>
                  <TextField
                    label="Start Time"
                    type="datetime-local"
                    value={formData.start_time || ''}
                    onChange={(e) => setFormData({ ...formData, start_time: e.target.value })}
                    fullWidth
                    InputLabelProps={{ shrink: true }}
                    helperText="When should this schedule start?"
                  />
                </Grid>

                <Grid item xs={12} md={6}>
                  <Autocomplete
                    multiple
                    disableCloseOnSelect
                    options={contacts}
                    value={selectedContacts}
                    isOptionEqualToValue={(option, value) => option.contact_id === value.contact_id}
                    getOptionLabel={(option) => option.display_name}
                    onChange={(_, selected) =>
                      setFormData({
                        ...formData,
                        notification_contacts: selected.map((contact) => contact.contact_id),
                      })
                    }
                    renderOption={(props, option, { selected }) => (
                      <li {...props}>
                        <Checkbox
                          icon={checkboxIcon}
                          checkedIcon={checkboxCheckedIcon}
                          style={{ marginRight: 8 }}
                          checked={selected}
                        />
                        <Box>
                          <Typography variant="body2">{option.display_name}</Typography>
                          <Typography variant="caption" color="text.secondary">
                            {option.email_address}
                          </Typography>
                        </Box>
                      </li>
                    )}
                    renderInput={(params) => (
                      <TextField
                        {...params}
                        label="Notification Contacts"
                        placeholder={contacts.length ? 'Select contacts' : 'No contacts available'}
                        helperText="Contacts receive alerts for long-running or aborted runs"
                      />
                    )}
                    disabled={!contacts.length}
                  />
                </Grid>

                <Grid item xs={12}>
                  <FormControlLabel
                    control={
                      <Switch
                        checked={formData.is_active}
                        onChange={(event) =>
                          setFormData((prev) => ({ ...prev, is_active: event.target.checked }))
                        }
                      />
                    }
                    label="Schedule is active"
                  />
                </Grid>
              </Grid>
            </AccordionDetails>
          </Accordion>

          {/* Experiment Preparation Section */}
          <Accordion
            expanded={expandedSections.preparation}
            onChange={() => toggleSection('preparation')}
          >
            <AccordionSummary expandIcon={<ExpandMoreIcon />}>
              <Stack direction="row" alignItems="center" spacing={1}>
                <SettingsIcon color="primary" />
                <Typography variant="subtitle1">
                  Experiment Preparation
                </Typography>
              </Stack>
            </AccordionSummary>
            <AccordionDetails>
              <Stack spacing={2}>
                <FormControl component="fieldset">
                  <FormLabel id="experiment-prep-options">Before running</FormLabel>
                  <RadioGroup
                    aria-labelledby="experiment-prep-options"
                    value={experimentPrepOption}
                    onChange={(event) => handleExperimentPrepChange(event.target.value as 'none' | 'schedule')}
                  >
                    <FormControlLabel
                      value="none"
                      control={<Radio />}
                      label="Do nothing"
                    />
                    <FormControlLabel
                      value="schedule"
                      control={<Radio />}
                      label="Mark an EvoYeast experiment as ScheduledToRun"
                    />
                  </RadioGroup>
                </FormControl>

                {experimentPrepOption === 'schedule' && (
                  <Stack spacing={1}>
                    <Stack direction="row" alignItems="center" justifyContent="space-between">
                      <Typography variant="body2" color="text.secondary">
                        Choose the experiment to activate before execution
                      </Typography>
                      <IconButton size="small" onClick={() => loadEvoExperiments()} disabled={evoLoading}>
                        {evoLoading ? <CircularProgress size={16} /> : <RefreshIcon fontSize="small" />}
                      </IconButton>
                    </Stack>

                    <FormControl fullWidth size="small">
                      <InputLabel id="evoyeast-experiment-select">Experiment ID</InputLabel>
                      <Select
                        labelId="evoyeast-experiment-select"
                        label="Experiment ID"
                        value={selectedExperimentId}
                        onChange={(event) => setSelectedExperimentId(event.target.value as string)}
                        displayEmpty
                      >
                        <MenuItem value="">Select experiment</MenuItem>
                        {evoExperiments.map((option) => (
                          <MenuItem key={option.experiment_id} value={option.experiment_id}>
                            <Stack direction="row" alignItems="center" spacing={1} justifyContent="space-between" sx={{ width: '100%' }}>
                              <Box>
                                <Typography variant="body2">{option.user_defined_id ?? option.experiment_id}</Typography>
                                {option.note && (
                                  <Typography variant="caption" color="text.secondary">
                                    {option.note}
                                  </Typography>
                                )}
                                {option.experiment_name &&
                                  option.experiment_name !== (option.user_defined_id ?? option.experiment_id) && (
                                    <Typography variant="caption" color="text.secondary">
                                      {option.experiment_name}
                                    </Typography>
                                  )}
                                {option.user_defined_id &&
                                  option.user_defined_id !== option.experiment_id && (
                                    <Typography variant="caption" color="text.secondary">
                                      ID: {option.experiment_id}
                                    </Typography>
                                  )}
                              </Box>
                              {option.scheduled_to_run && (
                                <Chip label="Scheduled" color="success" size="small" />
                              )}
                            </Stack>
                          </MenuItem>
                        ))}
                      </Select>
                    </FormControl>

                    {!evoLoading && evoExperiments.length === 0 && (
                      <Typography variant="caption" color="text.secondary">
                        No EvoYeast experiments available. Refresh after the database is populated.
                      </Typography>
                    )}
                  </Stack>
                )}
              </Stack>
            </AccordionDetails>
          </Accordion>
        </Stack>
      </DialogContent>

      <DialogActions>
        <Button onClick={onClose} disabled={loading}>
          Cancel
        </Button>
        <Button
          onClick={handleSubmit}
          variant="contained"
          disabled={loading || scanning}
          startIcon={loading ? <CircularProgress size={20} /> : <AddIcon />}
        >
          {mode === 'create' ? 'Create Schedule' : 'Update Schedule'}
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
    </>
  );
};

export default ImprovedScheduleForm;


