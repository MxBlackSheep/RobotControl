import React, { useCallback, useEffect, useMemo, useState } from 'react';
import {
  Alert,
  Box,
  Button,
  Chip,
  FormControl,
  MenuItem,
  Paper,
  Select,
  Stack,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  Typography,
} from '@mui/material';
import {
  DeleteSweep as DiscardIcon,
  Refresh as RefreshIcon,
  Save as SaveIcon,
} from '@mui/icons-material';

import { CytomatRowState, CytomatSnapshot, labwareApi } from '../../services/labwareApi';

const DEFAULT_AUTO_REFRESH_MS = 15000;

const CytomatPanel: React.FC = () => {
  const [snapshot, setSnapshot] = useState<CytomatSnapshot | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [saving, setSaving] = useState(false);
  const [pendingByPos, setPendingByPos] = useState<Record<string, string>>({});

  const loadSnapshot = useCallback(async (showLoader = false) => {
    if (showLoader) {
      setLoading(true);
    }
    try {
      const payload = await labwareApi.getCytomatSnapshot();
      setSnapshot(payload);
      setError('');
    } catch (err: any) {
      const message = err?.response?.data?.message || err?.message || 'Failed to load Cytomat data';
      setError(message);
    } finally {
      if (showLoader) {
        setLoading(false);
      }
    }
  }, []);

  useEffect(() => {
    void loadSnapshot(true);
  }, [loadSnapshot]);

  const rows = snapshot?.rows || [];
  const rowMap = useMemo(() => {
    const map: Record<string, CytomatRowState> = {};
    rows.forEach((row) => {
      map[row.cytomat_pos] = row;
    });
    return map;
  }, [rows]);

  const plateOptions = useMemo(() => {
    const seen = new Set<string>();
    const merged = ['', ...(snapshot?.plate_options || [])];
    return merged.filter((value) => {
      if (seen.has(value)) {
        return false;
      }
      seen.add(value);
      return true;
    });
  }, [snapshot?.plate_options]);

  const canUpdate = Boolean(snapshot?.permissions?.can_update);
  const pendingCount = Object.keys(pendingByPos).length;

  useEffect(() => {
    if (!snapshot || pendingCount > 0) {
      return;
    }

    const intervalMs = Number(snapshot.auto_refresh_ms || DEFAULT_AUTO_REFRESH_MS);
    const interval = window.setInterval(() => {
      void loadSnapshot(false);
    }, intervalMs);

    return () => {
      window.clearInterval(interval);
    };
  }, [loadSnapshot, pendingCount, snapshot]);

  const getSavedPlateId = useCallback((cytomatPos: string): string => {
    return rowMap[cytomatPos]?.plate_id || '';
  }, [rowMap]);

  const getDisplayPlateId = useCallback((cytomatPos: string): string => {
    if (Object.prototype.hasOwnProperty.call(pendingByPos, cytomatPos)) {
      return pendingByPos[cytomatPos];
    }
    return getSavedPlateId(cytomatPos);
  }, [getSavedPlateId, pendingByPos]);

  const queueChange = (cytomatPos: string, plateId: string) => {
    const saved = getSavedPlateId(cytomatPos);
    setPendingByPos((prev) => {
      const next = { ...prev };
      if (plateId === saved) {
        delete next[cytomatPos];
      } else {
        next[cytomatPos] = plateId;
      }
      return next;
    });
  };

  const discardPending = () => {
    if (pendingCount === 0) {
      return;
    }
    setPendingByPos({});
  };

  const savePending = async () => {
    if (!canUpdate || pendingCount === 0) {
      return;
    }

    setSaving(true);
    setError('');
    try {
      const updates = Object.entries(pendingByPos).map(([cytomat_pos, plate_id]) => ({
        cytomat_pos,
        plate_id,
      }));
      await labwareApi.updateCytomat(updates);
      setPendingByPos({});
      await loadSnapshot(false);
    } catch (err: any) {
      const message = err?.response?.data?.message || err?.message || 'Failed to save Cytomat updates';
      setError(message);
    } finally {
      setSaving(false);
    }
  };

  if (loading) {
    return (
      <Paper variant="outlined" sx={{ p: 2 }}>
        <Typography>Loading Cytomat data...</Typography>
      </Paper>
    );
  }

  if (!rows.length) {
    return (
      <Paper variant="outlined" sx={{ p: 2 }}>
        <Typography>No Cytomat rows were returned by the backend.</Typography>
      </Paper>
    );
  }

  return (
    <Stack spacing={2}>
      {!canUpdate && (
        <Alert severity="info">
          You are in read-only mode because this session is remote. Cytomat updates are available only from local
          sessions.
        </Alert>
      )}

      {error && <Alert severity="error">{error}</Alert>}

      <Paper variant="outlined" sx={{ p: 2 }}>
        <Stack direction={{ xs: 'column', sm: 'row' }} spacing={1} alignItems={{ xs: 'stretch', sm: 'center' }}>
          <Button startIcon={<RefreshIcon />} onClick={() => loadSnapshot(false)} disabled={saving}>
            Refresh
          </Button>
          <Button
            startIcon={<DiscardIcon />}
            color="inherit"
            onClick={discardPending}
            disabled={!canUpdate || pendingCount === 0 || saving}
          >
            Discard
          </Button>
          <Button
            variant="contained"
            startIcon={<SaveIcon />}
            onClick={savePending}
            disabled={!canUpdate || pendingCount === 0 || saving}
          >
            Save ({pendingCount})
          </Button>
        </Stack>
      </Paper>

      <TableContainer component={Paper} variant="outlined">
        <Table size="small">
          <TableHead>
            <TableRow>
              <TableCell sx={{ fontWeight: 700 }}>CytomatPos</TableCell>
              <TableCell sx={{ fontWeight: 700 }}>PlateID</TableCell>
              <TableCell sx={{ fontWeight: 700, width: 120 }}>State</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {rows.map((row) => {
              const selected = getDisplayPlateId(row.cytomat_pos);
              const pending = Object.prototype.hasOwnProperty.call(pendingByPos, row.cytomat_pos);
              return (
                <TableRow key={row.cytomat_pos} hover>
                  <TableCell>{row.cytomat_pos}</TableCell>
                  <TableCell>
                    <Box sx={{ maxWidth: 280 }}>
                      <FormControl fullWidth size="small">
                        <Select
                          value={selected}
                          onChange={(event) => queueChange(row.cytomat_pos, String(event.target.value))}
                          disabled={!canUpdate || saving}
                        >
                          {plateOptions.map((value) => (
                            <MenuItem key={value || '__empty__'} value={value}>
                              {value || <em>(Empty)</em>}
                            </MenuItem>
                          ))}
                        </Select>
                      </FormControl>
                    </Box>
                  </TableCell>
                  <TableCell>{pending ? <Chip label="Pending" size="small" color="warning" /> : '-'}</TableCell>
                </TableRow>
              );
            })}
          </TableBody>
        </Table>
      </TableContainer>
    </Stack>
  );
};

export default CytomatPanel;
