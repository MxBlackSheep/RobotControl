import { useState } from 'react';
import { Alert, Box, Button, Card, CardContent, Stack, Typography } from '@mui/material';
import { api } from '../services/api';

interface Issue { kind: string; id: string | number; description: string; repairable: boolean }
interface Preview { healthy: boolean; structural_error: boolean; token: string | null; message: string; issues: Issue[] }

function DatabaseHealth({ database, label }: { database: string; label: string }) {
  const [preview, setPreview] = useState<Preview | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [backup, setBackup] = useState<string | null>(null);
  const inspect = async () => {
    const { data } = await api.get<Preview>(`/api/admin/sqlite/${database}/preview`, { timeout: 60000 });
    setPreview(data);
  };
  const perform = async (action: 'preview' | 'repair' | 'reconcile', issue?: Issue) => {
    setBusy(true); setError(null);
    try {
      if (action === 'preview') { await inspect(); return; }
      let payload: Record<string, unknown> = { token: preview?.token };
      if (action === 'repair') {
        if (!window.confirm('Create a verified backup and apply the repairs shown as repairable? Recovery flags will remain in place.')) return;
      } else {
        if (!window.confirm('Confirm you have checked the robot and closed HxRun. This will record the abandoned run as cancelled; it will not resume scheduling.')) return;
        const note = window.prompt('Required reconciliation note');
        if (!note?.trim()) return;
        payload = { ...payload, execution_id: issue?.id, note: note.trim(), robot_ready: true };
      }
      const { data } = await api.post(`/api/admin/sqlite/${database}/${action}`, payload, { timeout: 60000 });
      setPreview(data.preview); setBackup(data.backup);
    } catch (err: any) {
      setError(err?.response?.data?.detail || err?.message || 'Storage operation failed');
      setPreview(null); // Require a fresh preview after any failed or stale request.
    } finally { setBusy(false); }
  };
  return <Card><CardContent><Stack spacing={1.5}>
    <Typography variant="h6">{label}</Typography>
    <Button disabled={busy} onClick={() => void perform('preview')}>Preview {label.toLowerCase()} health</Button>
    {error && <Alert severity="error">{error}</Alert>}
    {backup && <Alert severity="success">Verified backup saved: {backup}</Alert>}
    {preview && <>
      <Alert severity={preview.healthy ? 'success' : 'warning'}>{preview.message}</Alert>
      {preview.issues.map((issue, index) => <Stack key={`${issue.kind}-${index}`} spacing={0.5}>
        <Typography>{issue.description} Record: {issue.id}</Typography>
        <Typography variant="caption">{issue.repairable ? 'Included in reviewed repair' : 'Requires separate review'}</Typography>
        {['unfinished_execution', 'unfinished_archived_execution'].includes(issue.kind) && <Button disabled={busy} onClick={() => void perform('reconcile', issue)}>Reconcile abandoned run</Button>}
      </Stack>)}
      <Button variant="contained" disabled={busy || !preview.token || preview.structural_error || !preview.issues.some(i => i.repairable)}
        onClick={() => void perform('repair')}>Back up and apply reviewed repairs</Button>
    </>}
  </Stack></CardContent></Card>;
}

export default function SQLiteHealthPanel() {
  return <Stack spacing={1.5}>
    <Typography variant="body2" color="text.secondary">Preview repairs first. Recovery stays blocked until explicitly acknowledged.</Typography>
    <Box sx={{ display: "grid", gridTemplateColumns: { xs: "1fr", md: "repeat(2, minmax(0, 1fr))" }, gap: 1.5, alignItems: "start" }}>
    <DatabaseHealth database="scheduling" label="Scheduling storage" />
    <DatabaseHealth database="authentication" label="Authentication storage" />
    </Box>
  </Stack>;
}
