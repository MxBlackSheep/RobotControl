import { PageContent, PageHeader } from '../components/PageLayout';
import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  Alert,
  Box,
  Button,
  Card,
  CardContent,
  Chip,
  CircularProgress,
  Dialog,
  DialogActions,
  DialogContent,
  DialogContentText,
  DialogTitle,
  Stack,
  TextField,
  Typography,
} from '@mui/material';
import RefreshIcon from '@mui/icons-material/Refresh';
import BlockIcon from '@mui/icons-material/Block';
import CheckCircleOutlineIcon from '@mui/icons-material/CheckCircleOutline';

import { useAuth } from '../context/AuthContext';
import { hxrunMaintenanceApi, HxRunMaintenanceState } from '../services/hxrunMaintenanceApi';

const formatTimestamp = (value?: string | null): string => {
  if (!value) {
    return 'N/A';
  }
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime()) ? value : parsed.toLocaleString();
};

const MaintenancePage: React.FC = () => {
  const { user } = useAuth();
  const [state, setState] = useState<HxRunMaintenanceState | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [reasonInput, setReasonInput] = useState('');
  const reasonEdited = useRef(false);
  const [hxRunRunningDialogOpen, setHxRunRunningDialogOpen] = useState(false);
  const [hxRunRunningDialogMessage, setHxRunRunningDialogMessage] = useState(
    'HxRun is running. Please close the software before entering maintenance mode.',
  );

  const isLocalSession = useMemo(() => {
    if (typeof user?.session_is_local === 'boolean') {
      return user.session_is_local;
    }
    if (typeof window === 'undefined') {
      return false;
    }
    const hostname = window.location.hostname.toLowerCase();
    return hostname === 'localhost' || hostname === '127.0.0.1' || hostname === '::1' || hostname === '0.0.0.0';
  }, [user?.session_is_local]);

  const canEdit = Boolean(state?.permissions?.can_edit ?? isLocalSession);

  const loadState = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const payload = await hxrunMaintenanceApi.getState();
      if (typeof payload?.enabled !== 'boolean' || typeof payload?.permissions?.can_edit !== 'boolean') throw new Error('Maintenance state unavailable. Refresh to retry.');
      setState(payload);
      if (!reasonEdited.current) setReasonInput(payload.reason || '');
    } catch (err: any) {
      const message = err?.response?.data?.message || err?.response?.data?.detail || err?.message || 'Failed to load maintenance state';
      setError(message);
    } finally {
      setLoading(false);
    }
  }, []);

  const updateState = useCallback(
    async (enabled: boolean) => {
      if (!canEdit || !state || loading || error || saving) {
        return;
      }
      setSaving(true);
      setError(null);
      try {
        const next = await hxrunMaintenanceApi.updateState(
          enabled,
          reasonInput.trim() ? reasonInput.trim() : undefined,
        );
        if (typeof next?.enabled !== 'boolean' || typeof next?.permissions?.can_edit !== 'boolean') throw new Error('Maintenance state unavailable. Refresh to verify the change.');
        setState(next);
        reasonEdited.current = false;
        setReasonInput(next.reason || "");
      } catch (err: any) {
        const message = err?.response?.data?.message || err?.response?.data?.detail || err?.message || 'Failed to update maintenance state';
        const statusCode = err?.response?.status;
        if (enabled && statusCode === 409) {
          setHxRunRunningDialogMessage(message);
          setHxRunRunningDialogOpen(true);
          return;
        }
        setError(message);
      } finally {
        setSaving(false);
      }
    },
    [canEdit, reasonInput, state, loading, error, saving],
  );

  useEffect(() => {
    loadState();
  }, [loadState]);

  return (
    <PageContent variant="task">
      <PageHeader title="Maintenance" actions={<Button onClick={loadState} disabled={saving || loading} startIcon={<RefreshIcon />}>Refresh</Button>} />

      {error && (
        <Alert severity="error" sx={{ mb: 2 }}>
          {error}
        </Alert>
      )}

      {state && !canEdit && (
        <Alert severity="info" sx={{ mb: 2 }}>
          Changes require a local session.
        </Alert>
      )}

      <Card variant="outlined">
        <CardContent>
          {loading && !state ? (
            <Box sx={{ py: 4, display: 'flex', justifyContent: 'center' }}>
              <CircularProgress size={28} />
            </Box>
          ) : (
            <Stack spacing={2}>
              <Stack direction={{ xs: 'column', sm: 'row' }} spacing={1} alignItems={{ sm: 'center' }}>
                <Typography variant="h6">HxRun launches</Typography>
                <Chip
                  color={!state || error ? 'default' : state.enabled ? 'warning' : 'success'}
                  icon={!state || error ? undefined : state.enabled ? <BlockIcon /> : <CheckCircleOutlineIcon />}
                  label={!state || error ? 'State unavailable' : state.enabled ? 'Blocked for maintenance' : 'Allowed'}
                />
              </Stack>

              <Typography variant="body2" color="text.secondary">
                {state ? `Last change: ${state.updated_by || 'Unknown'} · ${formatTimestamp(state.updated_at)}` : 'Refresh to check the current state.'}
              </Typography>

              <TextField
                label="Reason"
                value={reasonInput}
                onChange={(event) => { reasonEdited.current = true; setReasonInput(event.target.value); }}
                multiline
                minRows={2}
                disabled={!canEdit || saving || !state || loading || !!error}
                placeholder="Optional maintenance note"
                fullWidth
              />

              <Button
                variant="contained"
                color={state?.enabled ? 'primary' : 'warning'}
                onClick={() => updateState(!state?.enabled)}
                disabled={!canEdit || saving || loading || !state || !!error}
                startIcon={state?.enabled ? <CheckCircleOutlineIcon /> : <BlockIcon />}
                sx={{ alignSelf: { xs: 'stretch', sm: 'flex-start' } }}
              >
                {saving ? 'Saving…' : state?.enabled ? 'Allow HxRun launches' : 'Enter maintenance'}
              </Button>
            </Stack>
          )}
        </CardContent>
      </Card>

      <Dialog
        open={hxRunRunningDialogOpen}
        onClose={() => setHxRunRunningDialogOpen(false)}
        maxWidth="sm"
        fullWidth
      >
        <DialogTitle>HxRun is running</DialogTitle>
        <DialogContent>
          <DialogContentText>{hxRunRunningDialogMessage}</DialogContentText>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setHxRunRunningDialogOpen(false)} autoFocus>
            OK
          </Button>
        </DialogActions>
      </Dialog>
    </PageContent>
  );
};

export default MaintenancePage;
