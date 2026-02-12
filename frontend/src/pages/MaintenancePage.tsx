import React, { useCallback, useEffect, useMemo, useState } from 'react';
import {
  Alert,
  Box,
  Button,
  Card,
  CardContent,
  Chip,
  CircularProgress,
  Container,
  Stack,
  TextField,
  Typography,
} from '@mui/material';
import BuildIcon from '@mui/icons-material/Build';
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
      setState(payload);
      if (payload.reason) {
        setReasonInput(payload.reason);
      }
    } catch (err: any) {
      const message = err?.response?.data?.message || err?.response?.data?.detail || err?.message || 'Failed to load maintenance state';
      setError(message);
    } finally {
      setLoading(false);
    }
  }, []);

  const updateState = useCallback(
    async (enabled: boolean) => {
      if (!canEdit) {
        return;
      }
      setSaving(true);
      setError(null);
      try {
        const next = await hxrunMaintenanceApi.updateState(
          enabled,
          reasonInput.trim() ? reasonInput.trim() : undefined,
        );
        setState(next);
      } catch (err: any) {
        const message = err?.response?.data?.message || err?.response?.data?.detail || err?.message || 'Failed to update maintenance state';
        setError(message);
      } finally {
        setSaving(false);
      }
    },
    [canEdit, reasonInput],
  );

  useEffect(() => {
    loadState();
  }, [loadState]);

  return (
    <Container maxWidth="lg" sx={{ py: { xs: 2, md: 3 } }}>
      <Box sx={{ mb: 3 }}>
        <Stack direction="row" spacing={1} alignItems="center" sx={{ mb: 1 }}>
          <BuildIcon color="primary" />
          <Typography variant="h4" sx={{ fontWeight: 700 }}>
            Maintenance
          </Typography>
        </Stack>
        <Typography variant="body2" color="text.secondary">
          Manage HxRun Maintenance Mode.
        </Typography>
      </Box>

      {error && (
        <Alert severity="error" sx={{ mb: 2 }}>
          {error}
        </Alert>
      )}

      {!canEdit && (
        <Alert severity="info" sx={{ mb: 2 }}>
          Local Access Required: remote sessions can inspect this flag but cannot change it.
        </Alert>
      )}

      <Card>
        <CardContent>
          {loading && !state ? (
            <Box sx={{ py: 4, display: 'flex', justifyContent: 'center' }}>
              <CircularProgress size={28} />
            </Box>
          ) : (
            <Stack spacing={2}>
              <Stack direction={{ xs: 'column', sm: 'row' }} spacing={1} alignItems={{ sm: 'center' }}>
                <Typography variant="h6">HxRun Maintenance Mode</Typography>
                <Chip
                  color={state?.enabled ? 'warning' : 'success'}
                  icon={state?.enabled ? <BlockIcon /> : <CheckCircleOutlineIcon />}
                  label={state?.enabled ? 'Enabled (HxRun blocked)' : 'Disabled (HxRun allowed)'}
                />
              </Stack>

              <Typography variant="body2" color="text.secondary">
                Updated by: {state?.updated_by || 'N/A'} | Updated at: {formatTimestamp(state?.updated_at)}
              </Typography>

              <TextField
                label="Reason"
                value={reasonInput}
                onChange={(event) => setReasonInput(event.target.value)}
                multiline
                minRows={2}
                disabled={!canEdit || saving}
                helperText="Optional note shown when HxRun launch is blocked."
                fullWidth
              />

              <Stack direction={{ xs: 'column', sm: 'row' }} spacing={1}>
                <Button
                  variant="contained"
                  color="warning"
                  onClick={() => updateState(true)}
                  disabled={!canEdit || saving || Boolean(state?.enabled)}
                  startIcon={<BlockIcon />}
                >
                  Enable Maintenance Mode
                </Button>
                <Button
                  variant="contained"
                  color="success"
                  onClick={() => updateState(false)}
                  disabled={!canEdit || saving || !state?.enabled}
                  startIcon={<CheckCircleOutlineIcon />}
                >
                  Disable Maintenance Mode
                </Button>
                <Button
                  variant="outlined"
                  onClick={loadState}
                  disabled={saving || loading}
                  startIcon={<RefreshIcon />}
                >
                  Refresh
                </Button>
              </Stack>
            </Stack>
          )}
        </CardContent>
      </Card>
    </Container>
  );
};

export default MaintenancePage;
