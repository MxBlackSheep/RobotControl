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

import React, { useState, useEffect, useCallback } from 'react';
import { useModalFocus } from '../../hooks/useModalFocus';
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
  Divider,
  FormGroup,
  FormControlLabel,
  Checkbox,
  CircularProgress,
  Stack,
  Accordion,
  AccordionSummary,
  AccordionDetails,
  Grid,
  InputAdornment,
  Tooltip,
  IconButton,
  ListSubheader
} from '@mui/material';
import {
  Add as AddIcon,
  Science as ScienceIcon,
  Schedule as ScheduleIcon,
  Settings as SettingsIcon,
  ExpandMore as ExpandMoreIcon,
  Info as InfoIcon,
  Refresh as RefreshIcon,
  FolderOpen as FolderIcon
} from '@mui/icons-material';
import { schedulingAPI, schedulingService } from '../../services/schedulingApi';
import { EvoYeastExperimentOption } from '../../types/scheduling';

interface ExperimentFile {
  name: string;
  path: string;
  category: string;
  description: string;
  last_modified: string | null;
  file_size: number;
}

interface Prerequisite {
  flag: string;
  description: string;
  table: string;
}

interface ScheduleFormData {
  experiment_name: string;
  experiment_path: string;
  schedule_type: 'once' | 'interval' | 'daily' | 'weekly';
  interval_hours: number;
  start_time: string | null;
  estimated_duration: number;
  prerequisites: string[];
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
}

const ImprovedScheduleForm: React.FC<ImprovedScheduleFormProps> = ({
  open,
  onClose,
  onSubmit,
  initialData,
  mode = 'create'
}) => {
  // Form state
  const [formData, setFormData] = useState<ScheduleFormData>({
    experiment_name: '',
    experiment_path: '',
    schedule_type: 'once',
    interval_hours: 6,
    start_time: null,
    estimated_duration: 55,
    prerequisites: ['ScheduledToRun'], // Default prerequisite
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
  const [prerequisites, setPrerequisites] = useState<Prerequisite[]>([]);
  const [errors, setErrors] = useState<string[]>([]);
  const [evoExperiments, setEvoExperiments] = useState<EvoYeastExperimentOption[]>([]);
  const [evoLoading, setEvoLoading] = useState(false);
  const [selectedExperimentId, setSelectedExperimentId] = useState<string>('');
  const [experimentAction, setExperimentAction] = useState<'none' | 'set_flag'>('none');
  const [basePrereqFlags, setBasePrereqFlags] = useState<string[]>(() =>
    (initialData?.prerequisites || []).filter((entry) => typeof entry === 'string' && !entry.startsWith('EvoYeastExperiment:'))
  );
  const buildPrerequisitePayload = useCallback((baseFlags: string[], experimentId: string, action: 'none' | 'set_flag') => {
    const payload = [...baseFlags];
    if (experimentId) {
      const actionToken = action === 'set_flag' ? 'set' : 'none';
      payload.push(`EvoYeastExperiment:${experimentId}|${actionToken}`);
    }
    return payload;
  }, []);
  const [expandedSections, setExpandedSections] = useState({
    experiment: true,
    schedule: true,
    prerequisites: false,
    advanced: false
  });

  // Add modal focus management
  const { modalRef } = useModalFocus({
    isOpen: open,
    onClose,
    initialFocusSelector: 'select[aria-label*="Select Experiment"]',
    restoreFocus: true,
    trapFocus: true,
    closeOnEscape: !loading // Don't close on escape when loading
  });

  // Load available experiments and prerequisites on mount
  useEffect(() => {
    if (open) {
      loadExperiments();
      loadPrerequisites();
      loadEvoExperiments();
    }
  }, [open]);

  const loadExperiments = async (rescan: boolean = false) => {
    try {
      setScanning(true);
      const response = await schedulingAPI.getAvailableExperiments(rescan);
      
      if (response.data.success) {
        setExperiments(response.data.data.experiments);
        setCategorizedExperiments(response.data.data.categorized);
      }
    } catch (error) {
      console.error('Failed to load experiments:', error);
      setErrors(['Failed to load available experiments']);
    } finally {
      setScanning(false);
    }
  };

  const loadPrerequisites = async () => {
    try {
      const response = await schedulingAPI.getAvailablePrerequisites();
      
      if (response.data.success) {
        setPrerequisites(response.data.data.prerequisites);
      }
    } catch (error) {
      console.error('Failed to load prerequisites:', error);
    }
  };

  const loadEvoExperiments = async (limit: number = 100) => {
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
  };

  useEffect(() => {
    if (!open) {
      return;
    }

    setFormData(prev => ({
      ...prev,
      prerequisites: buildPrerequisitePayload(basePrereqFlags, selectedExperimentId, experimentAction),
    }));
  }, [open, basePrereqFlags, selectedExperimentId, experimentAction, buildPrerequisitePayload]);

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

  const handlePrerequisiteToggle = (flag: string) => {
    setBasePrereqFlags(prev => (prev.includes(flag) ? prev.filter(item => item !== flag) : [...prev, flag]));
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

    setErrors(newErrors);
    return newErrors.length === 0;
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
      setErrors([error instanceof Error ? error.message : 'Failed to save schedule']);
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

  const totalPrerequisiteCount = basePrereqFlags.length + (selectedExperimentId ? 1 : 0);

  return (
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
          {errors.length > 0 && (
            <Alert 
              severity="error" 
              onClose={() => setErrors([])}
              role="alert"
              aria-live="assertive"
            >
              <ul style={{ margin: 0, paddingLeft: 20 }}>
                {errors.map((error, index) => (
                  <li key={index}>{error}</li>
                ))}
              </ul>
            </Alert>
          )}

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
              </Grid>
            </AccordionDetails>
          </Accordion>

          {/* Prerequisites Section */}
          <Accordion
            expanded={expandedSections.prerequisites}
            onChange={() => toggleSection('prerequisites')}
          >
            <AccordionSummary expandIcon={<ExpandMoreIcon />}>
              <Stack direction="row" alignItems="center" spacing={1}>
                <SettingsIcon color="primary" />
                <Typography variant="subtitle1">
                  Prerequisites 
                  {totalPrerequisiteCount > 0 && (
                    <Chip 
                      label={totalPrerequisiteCount} 
                      size="small" 
                      sx={{ ml: 1 }}
                    />
                  )}
                </Typography>
              </Stack>
            </AccordionSummary>
            <AccordionDetails>
              <Stack spacing={2}>
                <Typography variant="body2" color="text.secondary">
                  Select database flags to set before running this experiment
                </Typography>
                <FormGroup>
                  {prerequisites.map(prereq => (
                    <FormControlLabel
                      key={prereq.flag}
                      control={
                        <Checkbox
                          checked={basePrereqFlags.includes(prereq.flag)}
                          onChange={() => handlePrerequisiteToggle(prereq.flag)}
                        />
                      }
                      label={
                        <Box>
                          <Typography variant="body2">{prereq.flag}</Typography>
                          <Typography variant="caption" color="text.secondary">
                            {prereq.description} (Table: {prereq.table})
                          </Typography>
                        </Box>
                      }
                    />
                  ))}
                </FormGroup>

                <Divider />

                <Stack spacing={1}>
                  <Stack direction="row" alignItems="center" justifyContent="space-between">
                    <Typography variant="body2" color="text.secondary">
                      Link an EvoYeast experiment (updates ScheduledToRun prior to execution)
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
                      onChange={(event) => {
                        const value = event.target.value as string;
                        setSelectedExperimentId(value);
                        if (!value) {
                          setExperimentAction('none');
                        }
                      }}
                      displayEmpty
                    >
                      <MenuItem value="">None</MenuItem>
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

                  <FormControl fullWidth size="small" disabled={!selectedExperimentId}>
                    <InputLabel id="evoyeast-action-select">Pre-run Action</InputLabel>
                    <Select
                      labelId="evoyeast-action-select"
                      label="Pre-run Action"
                      value={experimentAction}
                      onChange={(event) => setExperimentAction(event.target.value as 'none' | 'set_flag')}
                    >
                      <MenuItem value="none">Do nothing</MenuItem>
                      <MenuItem value="set_flag">Reset all flags, then activate selected experiment</MenuItem>
                    </Select>
                  </FormControl>

                  {selectedExperimentId && (
                    <Typography variant="caption" color="text.secondary">
                      Choosing "Reset all flags" sets ScheduledToRun = 0 for other experiments before activating the selected ID.
                    </Typography>
                  )}

                  {!selectedExperimentId && !evoLoading && evoExperiments.length === 0 && (
                    <Typography variant="caption" color="text.secondary">
                      No EvoYeast experiments available. Refresh after the database is populated.
                    </Typography>
                  )}
                </Stack>
              </Stack>
            </AccordionDetails>
          </Accordion>

          {/* Advanced Settings Section */}
          <Accordion
            expanded={expandedSections.advanced}
            onChange={() => toggleSection('advanced')}
          >
            <AccordionSummary expandIcon={<ExpandMoreIcon />}>
              <Typography variant="subtitle1">Advanced Settings</Typography>
            </AccordionSummary>
            <AccordionDetails>
              <Stack spacing={2}>
                <Alert
                  severity="info"
                  icon={<InfoIcon fontSize="small" />}
                >
                  Conflict retries are managed automatically (up to 3 attempts with a 2-minute delay).
                  Backend configuration controls these thresholds if they need adjustment.
                </Alert>
                <FormControlLabel
                  control={
                    <Checkbox
                      checked={formData.is_active}
                      onChange={(e) => setFormData({ ...formData, is_active: e.target.checked })}
                    />
                  }
                  label="Schedule is active"
                />
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
  );
};

export default ImprovedScheduleForm;


