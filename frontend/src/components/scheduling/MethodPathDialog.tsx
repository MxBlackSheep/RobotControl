import React, { useState } from 'react';
import { Alert, Box, Button, Checkbox, Dialog, DialogActions, DialogContent, DialogTitle, FormControlLabel, LinearProgress, Stack, TextField, Typography } from '@mui/material';
import { LibraryMethod, MethodPathPreview, MethodReference } from '../../types/scheduling';
import { schedulingAPI } from '../../services/schedulingApi';
import HostMethodBrowser, { methodError } from './HostMethodBrowser';

const referenceKey = (ref: MethodReference) => `${ref.schedule_id}:${ref.role}`;
const groups = [
  { name: 'Busy schedules — cannot update', matches: (ref: MethodReference) => !!ref.busy },
  { name: 'Archived schedules — cannot update', matches: (ref: MethodReference) => !ref.busy && !!ref.archived },
  { name: 'Active schedules', matches: (ref: MethodReference) => !ref.busy && !ref.archived && !!ref.is_active },
  { name: 'Inactive schedules', matches: (ref: MethodReference) => !ref.busy && !ref.archived && !ref.is_active },
];

export default function MethodPathDialog({ method, onClose, onChanged }: { method: LibraryMethod; onClose: () => void; onChanged: () => void }) {
  const [path, setPath] = useState('');
  const [browse, setBrowse] = useState(false);
  const [preview, setPreview] = useState<MethodPathPreview | null>(null);
  const [selected, setSelected] = useState<string[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [saved, setSaved] = useState<string | null>(null);
  const check = async () => {
    setBusy(true); setError('');
    try {
      const response = await schedulingAPI.previewMethodPath(method.method_id, path);
      if (!response.data.success || !response.data.data) throw new Error('Could not preview the change.');
      setPreview(response.data.data); setSelected([]);
    } catch (err) { setError(methodError(err)); }
    finally { setBusy(false); }
  };
  const save = async () => {
    if (!preview) return;
    setBusy(true); setError('');
    const references = preview.references.filter(ref => selected.includes(referenceKey(ref)));
    try {
      const response = await schedulingAPI.changeMethodPath(method.method_id, { new_path: preview.new_path, expected_revision: preview.expected_revision,
        references: references.map(ref => ({ schedule_id: ref.schedule_id, role: ref.role, expected_updated_at: ref.updated_at })) });
      if (!response.data.success || !response.data.data) throw new Error('The path change could not be saved.');
      setSaved(`Path updated. ${response.data.data.updated_schedule_ids.length} schedule(s) updated; ${preview.references.length - references.length} unselected reference(s) kept their original paths.`);
      onChanged();
    } catch (err) { setError(`${methodError(err)} Your entries are retained. Use Review again to reload the affected schedules.`); }
    finally { setBusy(false); }
  };
  return <Dialog open onClose={() => { if (!busy) onClose(); }} disableEscapeKeyDown={busy} fullWidth maxWidth="md" aria-labelledby="method-path-title">
    <DialogTitle id="method-path-title">Change method path</DialogTitle>
    <DialogContent dividers><Stack spacing={2}>
      <Typography sx={{ overflowWrap: 'anywhere' }}>Original library path: {method.file_path}</Typography>
      {saved ? <Alert severity="success">{saved}</Alert> : !preview ? <>
        <Typography>Choose the existing .med file at its new location. RobotControl will not move files.</Typography>
        <TextField required autoFocus label="New absolute method path" value={path} fullWidth disabled={busy}
          onChange={e => setPath(e.target.value)} helperText="Review the new path and affected schedules before saving." />
        <Button disabled={busy} onClick={() => setBrowse(value => !value)}>{browse ? 'Hide folder browser' : 'Browse for method'}</Button>
        {browse && <HostMethodBrowser mode="method" disabled={busy} onSelect={value => { setPath(value); setBrowse(false); }} />}
      </> : <>
        <Typography sx={{ overflowWrap: 'anywhere' }}>New library path: {preview.new_path}</Typography>
        <Alert severity="info">Select only the schedule references to update. Unselected schedules keep their old paths. Queued, running, paused and archived schedules cannot be selected.</Alert>
        {groups.map(group => {
          const references = preview.references.filter(group.matches);
          return references.length > 0 && <Box key={group.name}>
            <Typography variant="subtitle2">{group.name}</Typography>
            {references.map(ref => <FormControlLabel key={referenceKey(ref)} sx={{ display: 'flex', alignItems: 'flex-start' }}
              control={<Checkbox disabled={busy || !!ref.busy || !!ref.archived} checked={selected.includes(referenceKey(ref))}
                onChange={(_, checked) => setSelected(old => checked ? [...old, referenceKey(ref)] : old.filter(key => key !== referenceKey(ref)))} />}
              label={<Box sx={{ overflowWrap: 'anywhere', pt: 1 }}><Typography>{ref.experiment_name} — {ref.role} method</Typography><Typography variant="caption">{ref.schedule_id}</Typography></Box>} />)}
          </Box>;
        })}
        {!preview.references.length && <Typography>No existing schedules reference this path.</Typography>}
        <Typography>{selected.length} of {preview.references.length} references selected. {selected.length ? 'Only these selected references will change.' : 'Only the library path will change.'}</Typography>
      </>}
      {!!error && <Alert severity="error">{error}</Alert>}
      {busy && <LinearProgress aria-label="Checking or saving method path" />}
    </Stack></DialogContent>
    <DialogActions sx={{ flexWrap: 'wrap' }}>
      <Button disabled={busy} onClick={onClose}>{saved ? 'Close' : 'Cancel'}</Button>
      {!saved && preview && <Button disabled={busy} onClick={() => { setPreview(null); setSelected([]); setError(''); }}>Change entry</Button>}
      {!saved && <Button disabled={busy || !path.trim()} onClick={check}>{preview ? 'Review again' : 'Review change'}</Button>}
      {!saved && preview && <Button variant="contained" disabled={busy} onClick={save}>Save reviewed change</Button>}
    </DialogActions>
  </Dialog>;
}
