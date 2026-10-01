import { useEffect, useState } from 'react';
import { Alert, Autocomplete, Button, Checkbox, FormControlLabel, MenuItem, Stack, TextField, Typography } from '@mui/material';
import { api } from '../services/api';
import { requestErrorMessage } from '../services/requestError';

export type ReportField = { name: string; label: string; type: string; required: boolean; choices: string[];
  lookup?: { source?: string; query?: string; parameters: string[]; value_type: string } | null };
export const requestMessage = (e: any): string => requestErrorMessage(e, 'Check the fields and try again.');
export function changedInputs(fields: ReportField[], values: Record<string, any>, name: string, value: any) {
  const next = { ...values, [name]: value }, cleared = new Set([name]);
  for (let pass = 0; pass < fields.length; pass++) for (const field of fields) {
    if (!cleared.has(field.name) && field.lookup?.parameters.some(p => cleared.has(p))) {
      cleared.add(field.name); delete next[field.name];
    }
  }
  return next;
}

function DatabaseChoice({ field, values, onChange, disabled, endpoint, allFields }: {
  field: ReportField; values: Record<string, any>; onChange: (value: any) => void; disabled: boolean; endpoint: string;
  allFields: ReportField[];
}) {
  const [query, setQuery] = useState(''), [page, setPage] = useState(1);
  const [options, setOptions] = useState<{ value: any; label: string }[]>([]);
  const [selected, setSelected] = useState<{ value: any; label: string } | null>(null);
  const [more, setMore] = useState(false), [loading, setLoading] = useState(false), [error, setError] = useState('');
  const parents = Object.fromEntries((field.lookup?.parameters || []).map(p => [p, values[p]]));
  const parentKey = JSON.stringify(parents);
  const missing = Object.values(parents).some(v => v == null || v === '');
  useEffect(() => { setQuery(''); setPage(1); setOptions([]); setSelected(null); }, [parentKey, endpoint]);
  useEffect(() => { if (values[field.name] == null) setSelected(null); }, [values[field.name]]);
  useEffect(() => {
    if (disabled || missing) return;
    const controller = new AbortController();
    const timer = window.setTimeout(async () => {
      setLoading(true); setError('');
      try {
        const { data } = await api.post(endpoint, { inputs: parents, search: query, page }, { signal: controller.signal });
        if (!controller.signal.aborted) { setOptions(old => page === 1 ? data.options : [...old, ...data.options]); setMore(data.has_more); }
      } catch (e) { if (!controller.signal.aborted) setError(requestMessage(e)); }
      finally { if (!controller.signal.aborted) setLoading(false); }
    }, 250);
    return () => { clearTimeout(timer); controller.abort(); };
  }, [parentKey, endpoint, query, page, disabled, missing]);
  // A value set before this control mounted (a saved or prefilled step) stays visible: its
  // label once the choices include it, otherwise the value itself.
  const current = values[field.name];
  const shown = selected ?? (current == null ? null : options.find(x => x.value === current) ?? { value: current, label: String(current) });
  return <Stack spacing={1}>
    <Autocomplete options={options} value={shown} disabled={disabled || missing} loading={loading}
      filterOptions={x => x} isOptionEqualToValue={(a, b) => a.value === b.value}
      getOptionLabel={x => x.label} renderOption={(props, x) => <li {...props} key={String(x.value)}>{x.label} · {String(x.value)}</li>}
      onInputChange={(_, text, reason) => { if (reason === 'input' || reason === 'clear') { setQuery(text); setPage(1); } }}
      onChange={(_, x) => { setSelected(x); onChange(x?.value ?? null); }}
      renderInput={params => <TextField {...params} label={field.label} required={field.required} size="small" />} />
    {missing && <Typography variant="caption">Choose {(field.lookup?.parameters || []).filter(p => values[p] == null || values[p] === '').map(p => allFields.find(f => f.name === p)?.label || p).join(', ')} first.</Typography>}
    {more && <Button disabled={disabled || loading} onClick={() => setPage(p => p + 1)}>More choices</Button>}
    {error && <Alert severity="error">{error}</Alert>}
  </Stack>;
}

export default function ReportInputs({ fields, values, onChange, disabled, choiceBase, allFields = fields }: {
  fields: ReportField[]; values: Record<string, any>; onChange: (name: string, value: any) => void;
  disabled: boolean; choiceBase: string; allFields?: ReportField[];
}) {
  return <Stack spacing={2} sx={{ width: '100%', minWidth: 0 }}>
    {fields.map(field => field.type === 'lookup'
      ? <DatabaseChoice key={field.name} field={field} allFields={allFields} values={values} onChange={v => onChange(field.name, v)} disabled={disabled} endpoint={`${choiceBase}/${field.name}`} />
      : field.type === 'boolean'
        ? <FormControlLabel key={field.name} label={field.label} control={<Checkbox checked={values[field.name] === true} disabled={disabled} onChange={(_, v) => onChange(field.name, v)} />} />
        : <TextField key={field.name} label={field.label} required={field.required} disabled={disabled} size="small"
          select={field.type === 'choice'} InputLabelProps={field.type === 'date' ? { shrink: true } : undefined}
          type={field.type === 'date' ? 'date' : ['integer', 'number', 'experiment'].includes(field.type) ? 'number' : 'text'}
          value={values[field.name] ?? ''} onChange={e => onChange(field.name, ['integer', 'number', 'experiment'].includes(field.type) && e.target.value !== '' ? Number(e.target.value) : e.target.value)}>
          {(field.choices || []).map(x => <MenuItem key={x} value={x}>{x}</MenuItem>)}
        </TextField>)}
  </Stack>;
}

export function saveBlob(data: Blob, name: string) {
  const url = URL.createObjectURL(data), anchor = document.createElement('a');
  anchor.href = url; anchor.download = name; anchor.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
