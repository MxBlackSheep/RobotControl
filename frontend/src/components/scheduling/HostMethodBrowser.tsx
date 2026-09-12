import React, { useEffect, useRef, useState } from 'react';
import { Alert, Box, Breadcrumbs, Button, LinearProgress, List, ListItemButton, ListItemText, Stack, TextField, Typography } from '@mui/material';
import { schedulingAPI } from '../../services/schedulingApi';
import { HostMethodDirectory } from '../../types/scheduling';

export const methodError = (error: any): string => {
  const detail = error?.response?.data?.detail;
  return typeof detail === 'string' ? detail : error?.message || 'The request failed. Please try again.';
};

export default function HostMethodBrowser({ onSelect, mode = 'folder', initialPath, disabled = false }: {
  onSelect: (path: string) => void; mode?: 'folder' | 'method'; initialPath?: string; disabled?: boolean;
}) {
  const [directory, setDirectory] = useState<HostMethodDirectory | null>(null);
  const [input, setInput] = useState(initialPath || '');
  const [selection, setSelection] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const sequence = useRef(0);
  const load = async (path?: string) => {
    if (disabled) return;
    const request = ++sequence.current;
    setBusy(true); setError('');
    try {
      const response = await schedulingAPI.browseMethodFolders(path);
      if (request !== sequence.current) return;
      const data = response.data.data;
      if (!response.data.success || !data) throw new Error(response.data.message || 'Cannot browse this folder.');
      setDirectory(data); setInput(data.current_path || ''); setSelection('');
    } catch (err) { if (request === sequence.current) setError(methodError(err)); }
    finally { if (request === sequence.current) setBusy(false); }
  };
  useEffect(() => { void load(initialPath); return () => { sequence.current += 1; }; }, []);
  return <Stack spacing={1.5}>
    <Typography variant="body2">Browse folders on the RobotControl computer. The selected path is supplied automatically.</Typography>
    <Stack direction="row" spacing={1}>
      <Button disabled={disabled || busy} onClick={() => load('')}>Drives</Button>
      <Button disabled={disabled || busy || !directory?.parent_path} onClick={() => load(directory!.parent_path!)}>Up</Button>
    </Stack>
    <Breadcrumbs aria-label="Folder location" sx={{ overflowWrap: 'anywhere' }}>
      {directory?.breadcrumbs.map(crumb => <Button key={crumb.path} size="small" disabled={disabled || busy} onClick={() => load(crumb.path)}>{crumb.name}</Button>)}
    </Breadcrumbs>
    <Stack direction={{ xs: 'column', sm: 'row' }} spacing={1}>
      <TextField label="Current folder" fullWidth size="small" value={input} disabled={disabled || busy}
        onChange={e => setInput(e.target.value)} onKeyDown={e => { if (e.key === 'Enter') { e.preventDefault(); void load(input); } }} />
      <Button disabled={disabled || busy} onClick={() => load(input)}>Go</Button>
    </Stack>
    {directory && !directory.current_path && <Stack direction="row" flexWrap="wrap" gap={1}>
      {directory.drives.map(path => <Button key={path} disabled={disabled || busy} onClick={() => load(path)}>{path}</Button>)}
      {!directory.drives.length && <Typography>No accessible drives found. Enter a folder path above.</Typography>}
    </Stack>}
    {!!directory?.shortcuts.length && <TextField select SelectProps={{ native: true }} label="Imported folders" value="" disabled={disabled || busy}
      InputLabelProps={{ shrink: true }} onChange={e => { if (e.target.value) void load(e.target.value); }}>
      <option value="">Choose an imported folder</option>
      {directory.shortcuts.map(path => <option key={path} value={path}>{path}</option>)}
    </TextField>}
    <Box sx={{ maxHeight: '32vh', overflowY: 'auto', border: 1, borderColor: 'divider', borderRadius: 1 }}>
      <List dense aria-label="Host folders and methods">
        {directory?.folders.map(folder => <ListItemButton key={folder.path} disabled={disabled || busy || folder.linked} onClick={() => load(folder.path)}>
          <ListItemText primary={folder.name} secondary={folder.linked ? 'Linked folder — use its original path' : 'Folder'} sx={{ overflowWrap: 'anywhere' }} />
        </ListItemButton>)}
        {mode === 'method' && directory?.methods.map(method => <ListItemButton key={method.path} disabled={disabled || busy} selected={selection === method.path}
          role="radio" aria-checked={selection === method.path} onClick={() => setSelection(method.path)}>
          <ListItemText primary={method.name} secondary={method.path} sx={{ overflowWrap: 'anywhere' }} />
        </ListItemButton>)}
      </List>
      {directory?.current_path && !directory.folders.length && (mode === 'folder' || !directory.methods.length) &&
        <Typography sx={{ p: 1.5 }}>No {mode === 'folder' ? 'subfolders' : 'methods or subfolders'} here.</Typography>}
    </Box>
    {error && <Alert severity="error">{error}</Alert>}
    {busy && <LinearProgress aria-label="Loading host folders" />}
    <Button variant="contained" disabled={disabled || busy || (mode === 'folder' ? !directory?.current_path : !selection)}
      onClick={() => onSelect(mode === 'folder' ? directory!.current_path! : selection)}>
      {mode === 'folder' ? 'Use this folder' : 'Use selected method'}
    </Button>
  </Stack>;
}
