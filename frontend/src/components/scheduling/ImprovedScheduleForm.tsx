import React, { useState, useEffect, useCallback, useMemo, useRef } from 'react';
import { isAxiosError } from 'axios';
import { useTheme } from '@mui/material/styles';
import useMediaQuery from '@mui/material/useMediaQuery';
import MethodPicker from './MethodPicker';
import { useAuth } from '../../context/AuthContext';
import { isLocalUser } from '../navigation';
import PreparationStepField from './PreparationStepField';
import PyHslProtocolField, { type CheckedProtocol } from './PyHslProtocolField';
import type { LibraryMethod, NotificationContact, ScheduledExperiment, ScheduleFormValues, ScheduleRunner, ScheduleType, TimeoutAction } from '../../types/scheduling';
import { StatusMessage } from '../StatusDialog';
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
  FormControlLabel,
  CircularProgress,
  Stack,
  Grid,
  InputAdornment,
  Tooltip,
  IconButton,
  Switch,
  Autocomplete,
  Checkbox,
  ToggleButton,
  ToggleButtonGroup
} from '@mui/material';
import {
  Refresh as RefreshIcon,
  CheckBoxOutlineBlank as CheckBoxOutlineBlankIcon,
  CheckBox as CheckBoxIcon
} from '@mui/icons-material';
import { schedulingAPI } from '../../services/schedulingApi';

interface ExperimentFile {
  name: string;
  path: string;
  category: string;
  description: string;
  last_modified: string | null;
  file_size: number;
}

/** A record under review opens with no type chosen: the form may not offer the stored one. */
type Draft = Omit<ScheduleFormValues, 'schedule_type'> & { schedule_type: ScheduleType | '' };

const defaults: Draft = {
  experiment_name: '',
  experiment_path: '',
  schedule_type: 'once',
  interval_hours: 6,
  start_time: null,
  estimated_duration: 55,
  log_inactivity_threshold_minutes: 3,
  mode: 'real',
  runner: 'venus',
  notification_contacts: [],
  is_active: true,
  timeout_minutes: null,
  timeout_action: 'continue',
  timeout_cleanup_experiment_name: null,
  timeout_cleanup_experiment_path: null,
};

/** A stored ISO time as the datetime-local input's text, at the browser's offset. */
const inputTime = (iso?: string | null) => {
  const date = iso ? new Date(iso) : null;
  if (!date || Number.isNaN(date.getTime())) return null;
  return new Date(date.getTime() - date.getTimezoneOffset() * 60000).toISOString().slice(0, 16);
};

/** The draft a form opens with: the stored schedule, or a new one (from a library method). */
function startingDraft(schedule?: ScheduledExperiment, method?: LibraryMethod): Draft {
  if (!schedule) return method ? { ...defaults, experiment_name: method.method_name, experiment_path: method.file_path } : defaults;
  return {
    experiment_name: schedule.experiment_name,
    experiment_path: schedule.experiment_path,
    schedule_type: schedule.review_reason ? '' : schedule.schedule_type,
    interval_hours: schedule.interval_hours ?? defaults.interval_hours,
    start_time: inputTime(schedule.start_time),
    estimated_duration: schedule.estimated_duration,
    log_inactivity_threshold_minutes: schedule.log_inactivity_threshold_minutes,
    mode: schedule.mode,
    runner: schedule.runner,
    protocol_id: schedule.protocol_id ?? undefined,
    parameters: schedule.parameters,
    is_active: schedule.is_active,
    timeout_minutes: schedule.timeout_config?.timeout_minutes ?? null,
    timeout_action: schedule.timeout_config?.action ?? 'continue',
    timeout_cleanup_experiment_name: schedule.timeout_config?.cleanup_experiment_name ?? null,
    timeout_cleanup_experiment_path: schedule.timeout_config?.cleanup_experiment_path ?? null,
    notification_contacts: schedule.notification_contacts ?? [],
  };
}

const intervalPresets = [
  { label: 'Every 6 hours', hours: 6 },
  { label: 'Every 8 hours', hours: 8 },
  { label: 'Every 12 hours', hours: 12 },
  { label: 'Daily (24 hours)', hours: 24 },
];

interface ImprovedScheduleFormProps {
  /** The stored schedule to edit, as it was when the form opened; none creates a schedule. */
  schedule?: ScheduledExperiment;
  /** A library method a new schedule starts from. */
  method?: LibraryMethod;
  onClose: () => void;
  onSubmit: (values: ScheduleFormValues) => Promise<void>;
  contacts: NotificationContact[];
  catalogueVersion?: number;
}

/**
 * Create or edit one schedule. The parent mounts it for each opening, so the draft starts from a
 * snapshot and a background refresh never changes it.
 */
const ImprovedScheduleForm: React.FC<ImprovedScheduleFormProps> = ({
  schedule,
  method,
  onClose,
  onSubmit,
  contacts,
  catalogueVersion = 0,
}) => {
  const { user } = useAuth();
  const mode = schedule ? 'edit' : 'create';
  const [protocolChecked, setProtocolChecked] = useState(false);
  const canEditPreparation = user?.role === 'admin' && isLocalUser(user);
  const [initialDraft] = useState(() => startingDraft(schedule, method));
  const [formData, setFormData] = useState<Draft>(initialDraft);
  // The interval is stored once (interval_hours); only whether Custom is chosen is kept apart.
  const [customInterval, setCustomInterval] = useState(() => !intervalPresets.some(preset => preset.hours === initialDraft.interval_hours));
  const intervalMinutes = Math.round(formData.interval_hours * 60);
  const checkboxIcon = <CheckBoxOutlineBlankIcon fontSize="small" />;
  const checkboxCheckedIcon = <CheckBoxIcon fontSize="small" />;
  // A contact under review gets no mail, so it does not count as a recipient.
  const receivesAlerts = (contact: NotificationContact) => contact.is_active && !contact.review_reason;
  const selectedContacts = useMemo(
    () => contacts.filter((contact) => formData.notification_contacts.includes(contact.contact_id)),
    [contacts, formData.notification_contacts],
  );
  const [minimumStartTime] = useState(() => inputTime(new Date().toISOString()) ?? '');

  const chooseInterval = (value: string) => {
    setCustomInterval(value === 'custom');
    if (value !== 'custom') setFormData(prev => ({ ...prev, interval_hours: Number(value) }));
  };
  const changeCustomInterval = (part: 'hours' | 'minutes', rawValue: number) => {
    const parsed = Number.isFinite(rawValue) ? Math.max(0, Math.floor(rawValue)) : 0;
    const hours = part === 'hours' ? parsed : Math.floor(intervalMinutes / 60);
    const minutes = part === 'minutes' ? Math.min(59, parsed) : intervalMinutes % 60;
    setFormData(prev => ({ ...prev, interval_hours: (hours * 60 + minutes) / 60 }));
  };

  // UI state
  const fullScreen = useMediaQuery(useTheme().breakpoints.down('md'));
  const [confirmDiscard, setConfirmDiscard] = useState(false);
  const dirty = JSON.stringify(formData) !== JSON.stringify(initialDraft);
  const requestClose = () => {
    if (loading) return;
    if (dirty) setConfirmDiscard(true);
    else onClose();
  };
  useEffect(() => {
    if (!dirty) return;
    const protectDraft = (event: BeforeUnloadEvent) => { event.preventDefault(); event.returnValue = ''; };
    window.addEventListener('beforeunload', protectDraft);
    return () => window.removeEventListener('beforeunload', protectDraft);
  }, [dirty]);
  const [loading, setLoading] = useState(false);
  const [scanning, setScanning] = useState(false);
  const [experiments, setExperiments] = useState<ExperimentFile[]>([]);
  const [notice, setNotice] = useState<StatusMessage | null>(null);

  const experimentControlRef = useRef<HTMLDivElement>(null);

  const loadExperiments = useCallback(async () => {
    try {
      setScanning(true);
      const response = await schedulingAPI.getAvailableExperiments();
      
      if (response.data.success) {
        setExperiments(response.data.data.experiments);
      }
    } catch (error) {
      console.error('Failed to load experiments:', error);
      const detail = error instanceof Error ? error.message : undefined;
      setNotice({
        message: detail
          ? `Unable to load available experiments.\n${detail}`
          : 'Unable to load available experiments. Please try again.',
        severity: 'error',
      });
    } finally {
      setScanning(false);
    }
  }, []);

  // Opening and every library change (import, relink) read the methods again.
  useEffect(() => { void loadExperiments(); }, [catalogueVersion, loadExperiments]);

  const pyhsl = formData.runner === 'pyhsl';
  const chooseRunner = (runner: ScheduleRunner) => setFormData(prev => runner === 'pyhsl'
    ? { ...prev, runner, mode: 'simulation', experiment_path: '', experiment_name: '', timeout_action: 'continue', timeout_cleanup_experiment_name: null, timeout_cleanup_experiment_path: null }
    : { ...prev, runner, mode: 'real', experiment_name: '', protocol_id: undefined, parameters: undefined });
  const handleProtocolChange = (protocol_id: string, parameters: Record<string, unknown>, checked: CheckedProtocol | null) => {
    setProtocolChecked(!!checked);
    setFormData(prev => ({ ...prev, protocol_id, parameters, experiment_name: checked?.name ?? prev.experiment_name }));
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

  const handleTimeoutCleanupSelect = (experimentPath: string) => {
    const selectedExperiment = experiments.find((exp) => exp.path === experimentPath);
    setFormData((prev) => ({
      ...prev,
      timeout_cleanup_experiment_path: selectedExperiment?.path || null,
      timeout_cleanup_experiment_name: selectedExperiment?.name || null,
    }));
  };

  /** The values to save, or null after showing what is missing. */
  const validateForm = (): ScheduleFormValues | null => {
    const newErrors: string[] = [];

    if (pyhsl ? !protocolChecked : !formData.experiment_path) {
      newErrors.push(pyhsl ? 'Choose a protocol' : 'Please select an experiment');
    }

    if (!formData.experiment_name) {
      newErrors.push('Experiment name is required');
    }

    if (!Number.isInteger(formData.log_inactivity_threshold_minutes) || formData.log_inactivity_threshold_minutes <= 0) {
      newErrors.push('Log inactivity threshold must be a positive whole number of minutes');
    }
    if (formData.estimated_duration <= 0) {
      newErrors.push('Estimated duration must be greater than 0');
    }

    if (!formData.schedule_type) {
      newErrors.push('Choose a schedule type');
    }

    if (formData.schedule_type === 'interval' && formData.interval_hours <= 0) {
      newErrors.push('Interval must be greater than 0 minutes');
    }

    if (mode === 'create' && formData.start_time) {
      const startDate = new Date(formData.start_time);
      if (!Number.isNaN(startDate.getTime()) && startDate.getTime() < Date.now()) {
        newErrors.push('Start time cannot be in the past');
      }
    }

    if (formData.timeout_minutes !== null && formData.timeout_minutes !== undefined) {
      if (!Number.isFinite(formData.timeout_minutes) || formData.timeout_minutes <= 0) {
        newErrors.push('Timeout minutes must be greater than 0');
      }
    }

    if (
      formData.timeout_action === 'run_cleanup_and_terminate' &&
      !formData.timeout_cleanup_experiment_path
    ) {
      newErrors.push('Select a cleanup method for timeout action');
    }

    if (newErrors.length > 0 || !formData.schedule_type) {
      setNotice({
        message: newErrors.join('\n'),
        severity: 'warning',
      });
      return null;
    }

    return { ...formData, schedule_type: formData.schedule_type };
  };

  const handleSubmit = async () => {
    const values = validateForm();
    if (!values) {
      return;
    }

    setLoading(true);
    try {
      await onSubmit(values);
      onClose();
    } catch (error) {
      setNotice({
        message: isAxiosError(error) && error.response?.status === 409
          ? 'Schedule changed elsewhere. Your entries are kept. Reopen after refreshing to use the latest version.'
          : error instanceof Error ? error.message : 'Failed to save schedule',
        severity: 'error',
      });
    } finally {
      setLoading(false);
    }
  };

  return (
    <>
      <Dialog
      open
      TransitionProps={{ onEntered: () => experimentControlRef.current?.querySelector<HTMLElement>('button')?.focus({ preventScroll: true }) }}
      onClose={!loading ? requestClose : undefined}
      maxWidth="md"
      fullWidth fullScreen={fullScreen}
      PaperProps={{ sx: { maxHeight: fullScreen ? '100dvh' : 'calc(100dvh - 64px)', height: fullScreen ? '100dvh' : undefined } }}
      aria-labelledby="schedule-dialog-title"
      aria-describedby="schedule-dialog-description"
      disableEscapeKeyDown={loading}
    >
      <DialogTitle id="schedule-dialog-title">
        <Typography variant="h6">
          {mode === 'create' ? 'Create schedule' : 'Edit schedule'}
        </Typography>
      </DialogTitle>

      <DialogContent dividers id="schedule-dialog-description">
        <Stack spacing={3}>
          {notice && <Alert severity={notice.severity} onClose={() => setNotice(null)} sx={{ whiteSpace: 'pre-line' }}>{notice.message}</Alert>}
          {/* Experiment Selection Section */}
          <Box component="section">
            <Box sx={{ mb: 1.5 }}>
              <Typography variant="subtitle1">Method</Typography>
            </Box>
            <Box>
              <Stack spacing={2}>
                <ToggleButtonGroup exclusive size="small" color="primary" aria-label="Runner" value={formData.runner ?? 'venus'} disabled={loading}
                  onChange={(_, runner: ScheduleRunner | null) => { if (runner) chooseRunner(runner); }}>
                  <ToggleButton value="venus">VENUS method</ToggleButton>
                  <ToggleButton value="pyhsl">PyHSL protocol</ToggleButton>
                </ToggleButtonGroup>
                {pyhsl && <PyHslProtocolField protocolId={formData.protocol_id ?? ''} parameters={formData.parameters ?? {}} mode={formData.mode} disabled={loading} onChange={handleProtocolChange}
                  onModeChange={mode => setFormData(prev => ({ ...prev, mode }))} />}
                {!pyhsl && <><Box display="flex" alignItems="center" gap={1}>
                  <Box ref={experimentControlRef} sx={{ flex: 1 }}><MethodPicker methods={experiments} value={formData.experiment_path} label="Choose method" onChange={handleExperimentSelect} disabled={loading || scanning} /></Box>
                  <Tooltip title="Refresh method library">
                    <IconButton 
                      onClick={() => loadExperiments()}
                      disabled={scanning}
                    >
                      {scanning ? <CircularProgress size={24} /> : <RefreshIcon />}
                    </IconButton>
                  </Tooltip>
                </Box>

                {formData.experiment_path && <Typography variant="body2" sx={{ overflowWrap: 'anywhere' }}>{formData.experiment_name} · {formData.experiment_path}</Typography>}
                {!loading && !!formData.experiment_path && !experiments.some(exp => exp.path === formData.experiment_path) &&
                  <Alert severity="warning">This saved path is not in the current available method library. It may be archived or unavailable. Your selection is preserved; review it in Methods before changing it.</Alert>}
                </>}

                <TextField
                  label="Estimated duration (minutes)"
                  type="number"
                  value={formData.estimated_duration}
                  onChange={(e) => setFormData({ ...formData, estimated_duration: Number(e.target.value) })}
                  fullWidth
                  InputProps={{
                    endAdornment: <InputAdornment position="end">min</InputAdornment>
                  }}
                />
              </Stack>
            </Box>
          </Box>

          {/* Schedule Configuration Section */}
          <Box component="section">
            <Box sx={{ mb: 1.5 }}>
              <Typography variant="subtitle1">Timing and alerts</Typography>
            </Box>
            <Box>
              <Grid container spacing={2}>
                <Grid item xs={12} md={6}>
                  <FormControl fullWidth>
                    <InputLabel id="schedule-type-label">Schedule Type</InputLabel>
                    <Select
                      labelId="schedule-type-label"
                      value={formData.schedule_type}
                      onChange={(e) => setFormData({ ...formData, schedule_type: e.target.value as ScheduleType })}
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
                      <InputLabel id="schedule-interval-label">Interval</InputLabel>
                      <Select
                        labelId="schedule-interval-label"
                        value={customInterval ? 'custom' : String(formData.interval_hours)}
                        onChange={(e) => chooseInterval(e.target.value as string)}
                        label="Interval"
                      >
                        {intervalPresets.map(preset => (
                          <MenuItem key={preset.hours} value={String(preset.hours)}>
                            {preset.label}
                          </MenuItem>
                        ))}
                        <MenuItem value="custom">Custom interval</MenuItem>
                      </Select>
                    </FormControl>
                    {customInterval && (
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
                            value={Math.floor(intervalMinutes / 60)}
                            onChange={(e) => changeCustomInterval('hours', Number(e.target.value))}
                            fullWidth
                          />
                          <TextField
                            label="Minutes"
                            type="number"
                            inputProps={{ min: 0, max: 59 }}
                            value={intervalMinutes % 60}
                            onChange={(e) => changeCustomInterval('minutes', Number(e.target.value))}
                            fullWidth
                          />
                        </Stack>
                        {intervalMinutes < 1 && (
                          <Typography variant="caption" color="error" sx={{ display: 'block', mt: 1 }}>
                            Minimum interval is 1 minute.
                          </Typography>
                        )}
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
                    inputProps={{ min: minimumStartTime }}
                  />
                </Grid>

                <Grid item xs={12} md={6}>
                  <TextField
                    label="Timeout (minutes)"
                    type="number"
                    fullWidth
                    value={formData.timeout_minutes ?? ''}
                    onChange={(e) => {
                      const rawValue = e.target.value;
                      setFormData((prev) => ({
                        ...prev,
                        timeout_minutes: rawValue === '' ? null : Number(rawValue),
                      }));
                    }}
                    InputProps={{
                      endAdornment: <InputAdornment position="end">min</InputAdornment>
                    }}
                    inputProps={{ min: 1 }}
                  />
                </Grid>

                <Grid item xs={12} md={6}>
                  <FormControl fullWidth>
                    <InputLabel>Timeout Action</InputLabel>
                    <Select
                      value={formData.timeout_action}
                      onChange={(e) =>
                        setFormData((prev) => ({
                          ...prev,
                          timeout_action: e.target.value as TimeoutAction,
                          timeout_cleanup_experiment_name:
                            e.target.value === 'run_cleanup_and_terminate'
                              ? prev.timeout_cleanup_experiment_name
                              : null,
                          timeout_cleanup_experiment_path:
                            e.target.value === 'run_cleanup_and_terminate'
                              ? prev.timeout_cleanup_experiment_path
                              : null,
                        }))
                      }
                      label="Timeout Action"
                    >
                      <MenuItem value="continue">Do Nothing and Continue Execution</MenuItem>
                      {!pyhsl && <MenuItem value="run_cleanup_and_terminate">
                        Run Cleanup Method Instead and Stop Future Runs
                      </MenuItem>}
                    </Select>
                  </FormControl>
                </Grid>

                {formData.timeout_action === 'run_cleanup_and_terminate' && (
                  <Grid item xs={12}>
                    <MethodPicker methods={experiments} value={formData.timeout_cleanup_experiment_path || ''} label="Choose cleanup method" onChange={handleTimeoutCleanupSelect} disabled={loading || scanning} />
                    {formData.timeout_cleanup_experiment_path && <Typography variant="body2" sx={{ overflowWrap: 'anywhere', mt: 1 }}>{formData.timeout_cleanup_experiment_name} · {formData.timeout_cleanup_experiment_path}</Typography>}
                    {!!formData.timeout_cleanup_experiment_path && !experiments.some(exp => exp.path === formData.timeout_cleanup_experiment_path) &&
                      <Alert severity="warning">The saved cleanup path is archived, unavailable or absent from the current library. Your selection is preserved.</Alert>}
                  </Grid>
                )}

                {/* The VENUS run log only: a PyHSL run is followed through Run Control. */}
                {!pyhsl && <Grid item xs={12} md={6}>
                  <TextField fullWidth type="number" label="Log inactivity threshold (minutes)"
                    value={formData.log_inactivity_threshold_minutes}
                    onChange={(event) => setFormData({ ...formData, log_inactivity_threshold_minutes: Number(event.target.value) })}
                    inputProps={{ min: 1, step: 1 }}
                  />
                </Grid>}
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
                            {option.email_address}{option.review_reason ? ' · Needs review' : ''}
                          </Typography>
                        </Box>
                      </li>
                    )}
                    renderInput={(params) => (
                      <TextField
                        {...params}
                        label="Email alert recipients"
                        placeholder={contacts.length ? 'Select contacts' : 'No contacts available'}
                        helperText={selectedContacts.some(receivesAlerts)
                          ? 'Contacts receive alerts for log inactivity, unavailable monitoring, or aborted runs'
                          : 'Select an active contact to receive email alerts. Monitoring continues without email recipients.'}
                      />
                    )}
                    disabled={!contacts.length}
                  />
                </Grid>

                {!selectedContacts.some(receivesAlerts) && (
                  <Grid item xs={12}>
                    <Alert severity="warning">Log monitoring will continue, but no alert emails will be sent.</Alert>
                  </Grid>
                )}
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
                {!pyhsl && <Grid item xs={12}>
                  <FormControlLabel
                    control={
                      <Switch
                        checked={formData.mode === 'simulation'}
                        onChange={(event) =>
                          setFormData((prev) => ({ ...prev, mode: event.target.checked ? 'simulation' : 'real' }))
                        }
                      />
                    }
                    label="Run in VENUS Simulation Mode"
                  />
                </Grid>}
              </Grid>
            </Box>
          </Box>

          {/* Experiment Preparation Section */}
          <Box component="section">
            <Box sx={{ mb: 1.5 }}>
              <Typography variant="subtitle1">
                Before this run
              </Typography>
            </Box>
            <Box>
              <Stack spacing={2}>
                {canEditPreparation && <Button sx={{ alignSelf: 'flex-start' }} href="/database?section=settings" target="_blank" rel="noopener">Database settings</Button>}
                <PreparationStepField
                  saved={schedule?.preparation ?? null}
                  state={schedule?.preparation_state}
                  value={formData.preparation}
                  editable={canEditPreparation}
                  onChange={(preparation) => setFormData(prev => ({ ...prev, preparation }))}
                />
              </Stack>
            </Box>
          </Box>
        </Stack>
      </DialogContent>

      <DialogActions>
        <Button onClick={requestClose} disabled={loading}>
          Cancel
        </Button>
        <Button
          onClick={handleSubmit}
          variant="contained"
          disabled={loading || scanning}
          startIcon={loading ? <CircularProgress size={20} /> : undefined}
        >
          {mode === 'create' ? 'Create schedule' : 'Save schedule'}
        </Button>
      </DialogActions>
      </Dialog>
      <Dialog open={confirmDiscard} onClose={() => setConfirmDiscard(false)} aria-labelledby="discard-schedule-title">
        <DialogTitle id="discard-schedule-title">Discard schedule changes?</DialogTitle>
        <DialogContent>Your unsaved changes will be lost.</DialogContent>
        <DialogActions>
          <Button autoFocus onClick={() => setConfirmDiscard(false)}>Keep editing</Button>
          <Button color="error" onClick={() => { setConfirmDiscard(false); onClose(); }}>Discard changes</Button>
        </DialogActions>
      </Dialog>
    </>
  );
};

export default ImprovedScheduleForm;


