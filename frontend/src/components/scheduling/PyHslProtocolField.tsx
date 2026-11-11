import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Alert, Autocomplete, Box, Button, FormControl, FormControlLabel, InputLabel, MenuItem, Select, Stack, Switch, TextField, ToggleButton, ToggleButtonGroup, Typography } from '@mui/material';
import { api } from '../../services/api';
import { fontMono } from '../../theme';
import { SCHEDULE_MODE_LABELS, type ScheduleMode } from '../../types/scheduling';

type Definition = { label?: string; description?: string; type?: string; default?: unknown; choices?: unknown[]; shown_when?: Record<string, unknown[]> };
type Listed = { id: string; name: string; revision: string; modes: ScheduleMode[]; description?: string };
export type CheckedProtocol = { id: string; name: string; modes: ScheduleMode[]; parameters: Record<string, Definition> };

const MODE_ORDER: ScheduleMode[] = ['simulation', 'test', 'real'];

const shown = (definition: Definition, values: Record<string, unknown>) =>
  Object.entries(definition.shown_when ?? {}).every(([other, allowed]) => allowed.includes(values[other]));

/** Only fields that exist for these values are sent: PyHSL refuses a value for a hidden field. */
const visibleValues = (definitions: Record<string, Definition>, values: Record<string, unknown>) => Object.fromEntries(Object.entries(definitions)
  .filter(([, definition]) => shown(definition, values)).map(([name, definition]) => [name, values[name] ?? definition.default]));

/**
 * The search lists the protocols PyHSL can run unattended; choosing one validates it in the
 * chosen mode, and validate's parameter definitions draw the fields below.
 */
export default function PyHslProtocolField({ protocolId, parameters, mode, disabled, onChange, onModeChange }: {
  protocolId: string;
  parameters: Record<string, unknown>;
  mode: ScheduleMode;
  disabled?: boolean;
  onChange: (protocolId: string, parameters: Record<string, unknown>, checked: CheckedProtocol | null) => void;
  onModeChange: (mode: ScheduleMode) => void;
}) {
  const [protocols, setProtocols] = useState<Listed[] | null>(null);
  const [listError, setListError] = useState<string | null>(null);
  const [checked, setChecked] = useState<CheckedProtocol | null>(null);
  const [error, setError] = useState<string | null>(null);
  const current = useRef({ parameters, onChange });
  current.current = { parameters, onChange };

  const load = useCallback(async () => {
    setListError(null);
    try {
      const { data } = await api.get('/api/pyhsl/protocols');
      setProtocols(data);
    } catch (err: any) {
      setListError(err?.response?.data?.detail || 'Could not read the protocol list');
    }
  }, []);

  const latestCheck = useRef(0);
  const check = useCallback(async (listed: Listed, runMode: ScheduleMode) => {
    const { parameters: values, onChange: changed } = current.current;
    const mine = ++latestCheck.current;
    setError(null);
    try {
      const { data } = await api.post('/api/pyhsl/validate', { protocol_id: listed.id, parameters: values, mode: runMode });
      // Validate can take up to a minute; only the reply for the latest choice may change the form.
      if (mine !== latestCheck.current) return;
      const definitions: Record<string, Definition> = data.protocol?.parameters ?? {};
      const result = { id: listed.id, name: data.protocol?.name || listed.name, modes: listed.modes, parameters: definitions };
      setChecked(result);
      changed(listed.id, data.parameters ?? visibleValues(definitions, values), result);
    } catch (err: any) {
      if (mine !== latestCheck.current) return;
      setChecked(null);
      setError(err?.response?.data?.detail || 'Could not check the protocol');
      changed(listed.id, values, null);
    }
  }, []);

  useEffect(() => { void load(); }, [load]);
  const selected = protocols?.find(protocol => protocol.id === protocolId) ?? null;
  const options = useMemo(() => [...(protocols ?? [])].sort((a, b) => (a.name || a.id).localeCompare(b.name || b.id)), [protocols]);
  // A saved schedule draws its fields as soon as the list arrives.
  useEffect(() => { if (selected) void check(selected, mode); }, [selected?.id, mode]); // eslint-disable-line react-hooks/exhaustive-deps

  const choose = (id: string) => {
    const listed = protocols?.find(protocol => protocol.id === id);
    if (!listed) return;
    setChecked(null);
    onChange(id, {}, null);
    const nextMode = listed.modes.includes(mode) ? mode : listed.modes.includes('simulation') ? 'simulation' : listed.modes[0];
    if (nextMode !== mode) onModeChange(nextMode);
  };

  const setValue = (name: string, value: unknown) => onChange(protocolId, visibleValues(checked?.parameters ?? {}, { ...parameters, [name]: value }), checked);
  if (listError) return <Alert severity="error" sx={{ overflowWrap: 'anywhere' }}
    action={<Button color="inherit" size="small" onClick={() => void load()}>Retry</Button>}>{protocolId ? `${protocolId}: ${listError}` : listError}</Alert>;

  return <Stack spacing={2}>
    {protocols && protocolId && !selected && <Alert severity="warning" sx={{ overflowWrap: 'anywhere' }}>
      {protocolId} is not in Run Control's list of protocols it can run unattended.</Alert>}
    <Autocomplete options={options} value={selected} loading={!protocols} disabled={disabled}
      getOptionLabel={protocol => protocol.name || protocol.id}
      isOptionEqualToValue={(option, value) => option.id === value.id}
      filterOptions={(list, { inputValue }) => list.filter(protocol => `${protocol.name} ${protocol.id}`.toLowerCase().includes(inputValue.trim().toLowerCase()))}
      onChange={(_, protocol) => { if (protocol) choose(protocol.id); }}
      noOptionsText={protocols?.length ? 'No matching protocols' : 'No protocols ready to schedule'}
      renderOption={({ key, ...props }, protocol) => <Box component="li" key={key} {...props} sx={{ flexDirection: 'column', alignItems: 'flex-start !important' }}>
        <Typography variant="body2" sx={{ fontWeight: 500 }}>{protocol.name || protocol.id}</Typography>
        <Typography sx={{ fontFamily: fontMono, fontSize: 12, lineHeight: '16px', color: 'text.secondary' }}>{protocol.id}</Typography>
      </Box>}
      renderInput={params => <TextField {...params} label="Protocol" placeholder="Name or ID" error={!!error} />} />
    {selected && <Box>
      <Typography variant="body2" color="text.secondary" sx={{ mb: 0.75 }}>Mode</Typography>
      <ToggleButtonGroup exclusive size="small" color="primary" aria-label="Mode" value={mode} disabled={disabled}
        onChange={(_, value: ScheduleMode | null) => { if (value) onModeChange(value); }}>
        {MODE_ORDER.filter(value => selected.modes.includes(value)).map(value =>
          <ToggleButton key={value} value={value}>{SCHEDULE_MODE_LABELS[value]}</ToggleButton>)}
      </ToggleButtonGroup>
    </Box>}
    {error && <Alert severity="error" sx={{ overflowWrap: 'anywhere' }}>{error}</Alert>}
    {checked && Object.entries(checked.parameters).filter(([, definition]) => shown(definition, parameters)).map(([name, definition]) => definition.type === 'boolean'
      ? <FormControlLabel key={name} label={definition.label || name} disabled={disabled}
          control={<Switch checked={parameters[name] === true} onChange={event => setValue(name, event.target.checked)} />} />
      : definition.choices?.length
      ? <FormControl key={name} fullWidth>
          <InputLabel id={`pyhsl-parameter-${name}`}>{definition.label || name}</InputLabel>
          <Select labelId={`pyhsl-parameter-${name}`} label={definition.label || name} value={String(parameters[name] ?? '')} disabled={disabled}
            onChange={event => setValue(name, event.target.value)}>
            {definition.choices.map(choice => <MenuItem key={String(choice)} value={String(choice)}>{String(choice)}</MenuItem>)}
          </Select>
        </FormControl>
      : <TextField key={name} fullWidth label={definition.label || name} value={String(parameters[name] ?? '')} disabled={disabled}
          type={definition.type === 'number' || definition.type === 'integer' ? 'number' : 'text'}
          onChange={event => setValue(name, definition.type === 'number' || definition.type === 'integer' ? Number(event.target.value) : event.target.value)} />)}
  </Stack>;
}
