import { useCallback, useEffect, useRef, useState } from 'react';
import { Alert, Button, FormControl, FormControlLabel, InputLabel, MenuItem, Select, Stack, Switch, TextField, Typography } from '@mui/material';
import { api } from '../../services/api';

type Definition = { label?: string; description?: string; type?: string; default?: unknown; choices?: unknown[]; inactive?: boolean; shown_when?: Record<string, unknown[]> };
export type CheckedProtocol = { id: string; name: string; parameters: Record<string, Definition> };

const shown = (definition: Definition, values: Record<string, unknown>) =>
  !definition.inactive && Object.entries(definition.shown_when ?? {}).every(([other, allowed]) => allowed.includes(values[other]));

/** Only fields that exist for these values are sent: PyHSL refuses a value for a hidden field. */
const visibleValues = (definitions: Record<string, Definition>, values: Record<string, unknown>) => Object.fromEntries(Object.entries(definitions)
  .filter(([, definition]) => shown(definition, values)).map(([name, definition]) => [name, values[name] ?? definition.default]));

/**
 * Run Control lists protocols only to a person, so the machine token validates one by ID.
 * Validate returns the protocol's name and parameter definitions, which draw the fields below.
 */
export default function PyHslProtocolField({ protocolId, parameters, disabled, onChange }: {
  protocolId: string;
  parameters: Record<string, unknown>;
  disabled?: boolean;
  onChange: (protocolId: string, parameters: Record<string, unknown>, checked: CheckedProtocol | null) => void;
}) {
  const [checked, setChecked] = useState<CheckedProtocol | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const current = useRef({ protocolId, parameters, onChange });
  current.current = { protocolId, parameters, onChange };

  const check = useCallback(async () => {
    const { protocolId: id, parameters: values, onChange: changed } = current.current;
    setBusy(true);
    setError(null);
    try {
      const { data } = await api.post('/api/pyhsl/validate', { protocol_id: id.trim(), parameters: values, mode: 'simulation' });
      const definitions: Record<string, Definition> = data.protocol?.parameters ?? {};
      const known = data.parameters ?? visibleValues(definitions, values);
      const result = { id: id.trim(), name: data.protocol?.name || id.trim(), parameters: definitions };
      setChecked(result);
      changed(id.trim(), known, result);
    } catch (err: any) {
      setChecked(null);
      setError(err?.response?.data?.detail || 'Could not check the protocol');
      changed(id, values, null);
    } finally {
      setBusy(false);
    }
  }, []);

  // A saved schedule draws its fields as soon as the form opens.
  useEffect(() => { if (protocolId) void check(); }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const setValue = (name: string, value: unknown) => onChange(protocolId, visibleValues(checked?.parameters ?? {}, { ...parameters, [name]: value }), checked);
  return <Stack spacing={2}>
    <Stack direction="row" gap={1} alignItems="flex-start">
      <TextField fullWidth label="Protocol ID" value={protocolId} disabled={disabled} error={!!error}
        onChange={event => { setChecked(null); setError(null); onChange(event.target.value, {}, null); }} />
      <Button variant="outlined" onClick={() => void check()} disabled={disabled || busy || !protocolId.trim()} sx={{ height: 40, flexShrink: 0 }}>Check</Button>
    </Stack>
    {error && <Alert severity="error" sx={{ overflowWrap: 'anywhere' }}>{error}</Alert>}
    {checked && <Typography variant="body2" sx={{ overflowWrap: 'anywhere' }}>{checked.name}</Typography>}
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
