import React, { useEffect, useRef, useState } from 'react';
import { isAxiosError } from 'axios';
import {
  Alert, Box, Button, Checkbox, Chip, Dialog, DialogActions, DialogContent, DialogTitle,
  FormControl, FormControlLabel, FormLabel, LinearProgress, List, ListItem, Radio,
  RadioGroup, Stack, Step, StepLabel, Stepper, TextField, Typography,
} from '@mui/material';
import HostMethodBrowser from './HostMethodBrowser';
import { schedulingAPI } from '../../services/schedulingApi';
import { MethodImportPreview, MethodImportResult, MethodImportRow } from '../../types/scheduling';

interface Props {
  open: boolean;
  onClose: () => void;
  onImportComplete?: () => void;
  onCreateSchedule?: () => void;
  isLocalClient: boolean;
}

const errorMessage = (error: unknown) => {
  if (isAxiosError(error)) {
    const detail = error.response?.data?.detail;
    if (typeof detail === 'string') return detail;
    if (Array.isArray(detail)) return detail.map(item => item.msg).join('\n');
  }
  return error instanceof Error ? error.message : 'The request failed. Please try again.';
};

export default function FolderImportDialog({ open, onClose, onImportComplete, onCreateSchedule, isLocalClient }: Props) {
  const [source, setSource] = useState<'browser' | 'manual'>('browser');
  const [folder, setFolder] = useState('');
  const [preview, setPreview] = useState<MethodImportPreview | null>(null);
  const [result, setResult] = useState<MethodImportResult | null>(null);
  const [selected, setSelected] = useState<string[]>([]);
  const [search, setSearch] = useState('');
  const [stage, setStage] = useState(0);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const initialFocus = useRef<HTMLDivElement>(null);

  const reset = () => {
    setSource('browser'); setFolder(''); setPreview(null); setResult(null);
    setSelected([]); setSearch(''); setStage(0); setError(null);
  };
  useEffect(() => { if (open) reset(); }, [open]);
  const close = () => { if (!busy) onClose(); };
  const rows = stage === 2 ? result?.methods || [] : preview?.methods || [];
  const visibleRows = rows.filter(row => `${row.name} ${row.path || row.relative_path} ${row.reason || ''}`.toLowerCase().includes(search.toLowerCase()));
  const validRows = preview?.methods.filter(row => row.action !== 'invalid') || [];

  const scan = async (chosenFolder = folder) => {
    if (!isLocalClient || busy) return;
    setFolder(chosenFolder); setBusy(true); setError(null);
    try {
      const response = await schedulingAPI.previewExperimentImport({ folder_path: chosenFolder.trim() });
      if (!response.data.success || !response.data.data) throw new Error(response.data.message || 'Unable to preview this folder.');
      setPreview(response.data.data);
      setSelected(response.data.data.methods.filter(row => row.action !== 'invalid').map(row => row.relative_path));
      setSearch(''); setStage(1);
    } catch (err) { setError(errorMessage(err)); }
    finally { setBusy(false); }
  };

  const importSelected = async () => {
    if (!isLocalClient || busy || !preview || !selected.length) return;
    setBusy(true); setError(null);
    try {
      const response = await schedulingAPI.importExperimentFolder(preview.folder, selected);
      if (!response.data.data) throw new Error(response.data.message || 'No import results were returned.');
      // Partial/all file failures still have useful per-file results.
      const imported = response.data.data;
      setResult(imported); setSearch(''); setStage(2);
      if (imported.new_methods + imported.updated_methods > 0) onImportComplete?.();
    } catch (err) { setError(errorMessage(err)); }
    finally { setBusy(false); }
  };

  const toggle = (relative: string) => setSelected(previous => previous.includes(relative)
    ? previous.filter(value => value !== relative) : [...previous, relative]);
  const rowLabel = (row: MethodImportRow) => ({ new: 'New', update: 'Update', invalid: 'Invalid', added: 'Added', updated: 'Updated', failed: 'Failed' }[stage === 2 ? row.status! : row.action!] || 'Unknown');

  return (
    <Dialog open={open} onClose={close} disableEscapeKeyDown={busy} fullWidth maxWidth="md" sx={{ '@media (max-width: 899px)': { '& .MuiDialog-paper': { m: 0, width: '100%', maxWidth: '100%', height: '100dvh', maxHeight: '100dvh', borderRadius: 0 } } }}
      aria-labelledby="method-import-title" aria-describedby="method-import-description"
      TransitionProps={{ onEntered: () => initialFocus.current?.querySelector<HTMLInputElement>('input:checked')?.focus({ preventScroll: true }) }}>
      <DialogTitle id="method-import-title">Import Hamilton methods</DialogTitle>
      <DialogContent dividers>
        <Stack spacing={2.5}>
          <Typography id="method-import-description" variant="body2" color="text.secondary">
            Add .med methods to the experiment list, then create schedules for them. Importing does not run a method or create a schedule.
          </Typography>
          <Stepper activeStep={stage} alternativeLabel>
            {['Choose folder', 'Review methods', 'Import results'].map(label => <Step key={label}><StepLabel>{label}</StepLabel></Step>)}
          </Stepper>
          {!isLocalClient && <Alert severity="warning">Open RobotControl locally on the robot computer to import methods.</Alert>}
          {stage === 0 && <>
            <FormControl ref={initialFocus} disabled={busy || !isLocalClient}>
              <FormLabel id="method-source-label">Choose how to select the folder</FormLabel>
              <RadioGroup aria-labelledby="method-source-label" value={source} onChange={event => { setSource(event.target.value as 'browser' | 'manual'); setError(null); }}>
                <FormControlLabel value="browser" control={<Radio />} label="Browse RobotControl folders" />
                <FormControlLabel value="manual" control={<Radio />} label="Enter a folder path" />
              </RadioGroup>
            </FormControl>
            {source === 'browser' ? <HostMethodBrowser initialPath={folder || undefined} disabled={busy || !isLocalClient} onSelect={path => { void scan(path); }} /> :
              <TextField fullWidth required label="Folder path on RobotControl computer" value={folder} disabled={busy || !isLocalClient}
                onChange={event => { setFolder(event.target.value); setError(null); }}
                placeholder={'C:\\Program Files\\HAMILTON\\Methods'}
                helperText={folder.trim() ? 'Regular subfolders are included; linked folders are not scanned.' : 'Enter the full folder path to enable Review methods.'} />}

          </>}
          {stage > 0 && <>
            <Typography variant="body2" sx={{ overflowWrap: 'anywhere' }}>Folder: {preview?.folder}</Typography>
            {stage === 1 && <>
              {validRows.length > 0 && <Alert severity="info">{validRows.filter(row => row.action === 'new').length} new methods; {validRows.filter(row => row.action === 'update').length} existing methods to update. Review full paths before importing.</Alert>}
              {rows.length === 0 && <Alert severity="info">No .med methods found. Go back and choose another folder.</Alert>}
              {rows.some(row => row.action === 'invalid') && <Alert severity="warning">Some methods cannot be imported. Their reasons appear below.</Alert>}
            </>}
            {stage === 2 && result && <Alert severity={result.failed_methods ? 'warning' : 'success'}>
              {result.new_methods} added · {result.updated_methods} updated · {result.failed_methods} failed
            </Alert>}
            {rows.length > 0 && <>
              <TextField label="Search methods and paths" fullWidth size="small" value={search} onChange={event => setSearch(event.target.value)} />
              {stage === 1 && <FormControlLabel label={`Select all valid methods (${validRows.length})`}
                control={<Checkbox disabled={busy || !validRows.length} checked={validRows.length > 0 && selected.length === validRows.length}
                  indeterminate={selected.length > 0 && selected.length < validRows.length}
                  onChange={(_, checked) => setSelected(checked ? validRows.map(row => row.relative_path) : [])} />} />}
              <Box role="region" aria-label="Method review and results" sx={{ maxHeight: '40vh', overflowY: 'auto', border: 1, borderColor: 'divider', borderRadius: 1 }}>
                <List disablePadding>{visibleRows.map((row, index) => <ListItem key={`${row.relative_path}-${index}`} divider sx={{ alignItems: 'flex-start', gap: 1 }}>
                  {stage === 1 && <Checkbox checked={row.action !== 'invalid' && selected.includes(row.relative_path)} disabled={busy || row.action === 'invalid'}
                    inputProps={{ 'aria-label': `Import ${row.relative_path}` }} onChange={() => toggle(row.relative_path)} />}
                  <Box sx={{ minWidth: 0, flex: 1 }}>
                    <Typography variant="subtitle2" sx={{ overflowWrap: 'anywhere' }}>{row.name}</Typography>
                    <Typography variant="caption" color="text.secondary" sx={{ display: 'block', overflowWrap: 'anywhere' }}>{row.path || row.relative_path}</Typography>
                    {row.reason && <Typography variant="body2" color="error" sx={{ overflowWrap: 'anywhere' }}>{row.reason}</Typography>}
                  </Box>
                  <Chip size="small" label={`${rowLabel(row)}${row.archived ? ' (archived)' : ''}`} color={row.status === 'failed' || row.action === 'invalid' ? 'error' : row.status === 'added' || row.action === 'new' ? 'success' : 'info'} />
                </ListItem>)}</List>
                {visibleRows.length === 0 && <Typography sx={{ p: 2 }}>No methods match your search.</Typography>}
              </Box>
            </>}
          </>}
          {error && <Alert severity="error" sx={{ whiteSpace: 'pre-line' }}>{error}</Alert>}
          {busy && <Box aria-live="polite"><Typography variant="body2">{stage === 0 ? 'Checking host methods…' : 'Importing selected methods…'}</Typography><LinearProgress sx={{ mt: 1 }} /></Box>}
        </Stack>
      </DialogContent>
      <DialogActions sx={{ flexWrap: 'wrap', gap: 1 }}>
        <Button onClick={close} disabled={busy}>{stage === 2 ? 'Close' : 'Cancel'}</Button>
        {stage === 1 && <Button onClick={() => { setStage(0); setError(null); }} disabled={busy}>Back</Button>}
        {stage === 0 && source === 'manual' && <Button variant="contained" onClick={() => scan()} disabled={busy || !isLocalClient || !folder.trim()}>Review methods</Button>}
        {stage === 1 && <Button variant="contained" onClick={importSelected} disabled={busy || !isLocalClient || !selected.length}>Import {selected.length} selected</Button>}
        {stage === 2 && <Button onClick={reset}>Import another folder</Button>}
        {stage === 2 && result && result.new_methods + result.updated_methods > 0 && onCreateSchedule &&
          <Button variant="contained" onClick={() => { close(); onCreateSchedule(); }}>Create a schedule</Button>}
      </DialogActions>
    </Dialog>
  );
}
