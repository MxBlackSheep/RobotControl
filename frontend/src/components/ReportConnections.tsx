import React, { useEffect, useState } from 'react';
import { Alert, Button, Checkbox, Dialog, DialogActions, DialogContent, DialogTitle, FormControlLabel, MenuItem, Stack, TextField, Typography } from '@mui/material';
import { api } from '../services/api';
import { requestMessage } from './ReportInputs';
const base = '/api/database/tools';
export type Source = { id: string; name: string; server: string; database: string; username: string; driver: string; trust_certificate: boolean; password?: string };
const blank = (): Source => ({ id: '', name: '', server: '', database: '', username: '', password: '', driver: 'ODBC Driver 17 for SQL Server', trust_certificate: false });

export default function ReportConnections({ open, onClose }: { open: boolean; onClose: () => void }) {
  const [sources, setSources] = useState<Source[]>([]), [source, setSource] = useState<Source>(blank);
  const [error, setError] = useState(''), [notice, setNotice] = useState(''), [busy, setBusy] = useState(false);
  const load = () => api.get(`${base}/sources`).then(r => setSources(r.data));
  useEffect(() => { if (open) { setError(''); void load().catch(e => setError(requestMessage(e))); } }, [open]);
  const save = async () => {
    setBusy(true); setError(''); setNotice('');
    try {
      const { data } = await api.post(`${base}/sources`, source, { timeout: 120000 });
      setNotice(data.message); await load(); setSource(blank());
    } catch (e) { setError(requestMessage(e)); } finally { setBusy(false); }
  };
  return <Dialog open={open} onClose={() => !busy && onClose()} fullWidth maxWidth="md">
    <DialogTitle>Report connections</DialogTitle><DialogContent><Stack spacing={2} sx={{ pt: 1 }}>
      <Typography variant="body2">Use a dedicated SQL Server account with SELECT access. Settings stay on this computer.</Typography>
      {error && <Alert severity="error">{error}</Alert>}{notice && <Alert severity="success">{notice}</Alert>}
      {sources.map(item => <Stack key={item.id} direction="row" spacing={1} alignItems="center">
        <Typography sx={{ flex: 1 }}>{item.name} · {item.database}</Typography>
        <Button disabled={busy} onClick={() => { const { id, name, server, database, username, driver, trust_certificate } = item; setSource({ id, name, server, database, username, driver, trust_certificate }); setNotice(''); }}>Edit</Button>
        <Button disabled={busy} color="error" onClick={async () => { setBusy(true); try { await api.delete(`${base}/sources/${item.id}`); await load(); } catch (e) { setError(requestMessage(e)); } finally { setBusy(false); } }}>Remove</Button>
      </Stack>)}
      <Typography variant="subtitle1">Connection settings</Typography>
      {(['id', 'name', 'server', 'database', 'username', 'password', 'driver'] as const).map(key => <TextField key={key} size="small" disabled={busy}
        label={{ id: 'Connection ID', name: 'Name', server: 'Server', database: 'Database', username: 'Report account', password: 'Password', driver: 'ODBC driver' }[key]}
        type={key === 'password' ? 'password' : 'text'} value={source[key] || ''}
        helperText={key === 'password' && source.password === undefined ? 'Leave blank to keep the saved password.' : undefined}
        onChange={e => setSource(s => ({ ...s, [key]: key === 'password' && !e.target.value ? undefined : e.target.value }))} />)}
      <FormControlLabel label="Trust server certificate" control={<Checkbox disabled={busy} checked={source.trust_certificate} onChange={(_, v) => setSource(s => ({ ...s, trust_certificate: v }))} />} />
    </Stack></DialogContent><DialogActions><Button disabled={busy} onClick={onClose}>Close</Button>
      <Button disabled={busy} onClick={() => setSource(blank())}>New connection</Button>
      <Button disabled={busy} variant="contained" onClick={save}>{busy ? 'Checking…' : 'Check and save'}</Button></DialogActions>
  </Dialog>;
}

export function SourceMappings({ aliases, sources, mappings, onChange, disabled = false }: {
  aliases: string[]; sources: Source[]; mappings: Record<string, string>; onChange: (mapping: Record<string, string>) => void; disabled?: boolean;
}) {
  return <Stack spacing={2}>{aliases.map(alias => <TextField select key={alias} size="small" label={`Connection for ${alias}`} value={mappings[alias] || ''}
    disabled={disabled} onChange={e => onChange({ ...mappings, [alias]: e.target.value })}>
    {sources.map(s => <MenuItem key={s.id} value={s.id}>{s.name}</MenuItem>)}
  </TextField>)}</Stack>;
}
