import React, { useCallback, useEffect, useMemo, useState } from 'react';
import {
  Alert,
  Box,
  Button,
  Card,
  CardContent,
  Chip,
  Divider,
  FormControl,
  Grid,
  InputLabel,
  MenuItem,
  Paper,
  Select,
  Stack,
  Typography,
} from '@mui/material';
import {
  Refresh as RefreshIcon,
  Save as SaveIcon,
  DeleteSweep as DiscardIcon,
  RestartAlt as ResetIcon,
  CheckCircleOutline as ApplyIcon,
} from '@mui/icons-material';

import { labwareApi, TipTrackingFamilyState, TipTrackingSnapshot, TipTrackingUpdate } from '../../services/labwareApi';

const DEFAULT_AUTO_REFRESH_MS = 15000;
const DEFAULT_GRID_ROWS = 8;
const DEFAULT_GRID_COLS = 12;

interface SelectedTip {
  labwareId: string;
  positionId: number;
}

const pendingKey = (labwareId: string, positionId: number): string => `${labwareId}::${positionId}`;

const parsePendingKey = (value: string): SelectedTip | null => {
  const [labwareId, positionRaw] = value.split('::');
  if (!labwareId || !positionRaw) {
    return null;
  }
  const positionId = Number(positionRaw);
  if (!Number.isFinite(positionId)) {
    return null;
  }
  return { labwareId, positionId };
};

const TipTrackingPanel: React.FC = () => {
  const [snapshot, setSnapshot] = useState<TipTrackingSnapshot | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  const [selectedFamilyId, setSelectedFamilyId] = useState('');
  const [selectedTip, setSelectedTip] = useState<SelectedTip | null>(null);

  const [tipStatusChoice, setTipStatusChoice] = useState('clean');
  const [rackChoice, setRackChoice] = useState('');
  const [rackStatusChoice, setRackStatusChoice] = useState('clean');

  const [saving, setSaving] = useState(false);
  const [resetting, setResetting] = useState(false);

  const [pendingByFamily, setPendingByFamily] = useState<Record<string, Record<string, string>>>({});

  const loadSnapshot = useCallback(async (showLoader = false) => {
    if (showLoader) {
      setLoading(true);
    }
    try {
      const payload = await labwareApi.getTipTrackingSnapshot();
      setSnapshot(payload);
      setError('');

      if (payload.families.length > 0) {
        setSelectedFamilyId(prev => prev || payload.families[0].family_id);
      }

      if (payload.status_order.length > 0) {
        const firstStatus = payload.status_order[0];
        setTipStatusChoice(prev => (payload.status_order.includes(prev) ? prev : firstStatus));
        setRackStatusChoice(prev => (payload.status_order.includes(prev) ? prev : firstStatus));
      }
    } catch (err: any) {
      const message = err?.response?.data?.message || err?.message || 'Failed to load tip tracking data';
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

  const families = snapshot?.families || [];

  const activeFamily = useMemo<TipTrackingFamilyState | null>(() => {
    if (!families.length) {
      return null;
    }
    return families.find(family => family.family_id === selectedFamilyId) || families[0];
  }, [families, selectedFamilyId]);

  useEffect(() => {
    if (activeFamily && activeFamily.family_id !== selectedFamilyId) {
      setSelectedFamilyId(activeFamily.family_id);
    }
  }, [activeFamily, selectedFamilyId]);

  const statusOrder = snapshot?.status_order || ['clean', 'empty', 'dirty', 'rinsed', 'washed', 'reserved', 'unclear'];
  const statusColors = snapshot?.status_colors || {};
  const unknownStatus = snapshot?.unknown_status || 'unclear';

  const canUpdate = Boolean(snapshot?.permissions?.can_update);

  useEffect(() => {
    if (!activeFamily) {
      return;
    }

    const allRacks = [...activeFamily.left_racks, ...activeFamily.right_racks];
    if (!rackChoice || !allRacks.includes(rackChoice)) {
      setRackChoice(allRacks[0] || '');
    }

    if (selectedTip && !allRacks.includes(selectedTip.labwareId)) {
      setSelectedTip(null);
    }
  }, [activeFamily, rackChoice, selectedTip]);

  const currentFamilyPending = pendingByFamily[activeFamily?.family_id || ''] || {};
  const pendingCount = Object.keys(currentFamilyPending).length;

  useEffect(() => {
    if (!snapshot || !activeFamily) {
      return;
    }
    if (pendingCount > 0) {
      return;
    }

    const intervalMs = Number(snapshot.auto_refresh_ms || DEFAULT_AUTO_REFRESH_MS);
    const interval = window.setInterval(() => {
      void loadSnapshot(false);
    }, intervalMs);

    return () => {
      window.clearInterval(interval);
    };
  }, [activeFamily, loadSnapshot, pendingCount, snapshot]);

  const getSavedStatus = useCallback((labwareId: string, positionId: number): string => {
    if (!activeFamily) {
      return unknownStatus;
    }
    const rackTips = activeFamily.tips[labwareId] || {};
    return rackTips[String(positionId)] || unknownStatus;
  }, [activeFamily, unknownStatus]);

  const getDisplayStatus = useCallback((labwareId: string, positionId: number): string => {
    if (!activeFamily) {
      return unknownStatus;
    }
    const queued = pendingByFamily[activeFamily.family_id]?.[pendingKey(labwareId, positionId)];
    if (queued) {
      return queued;
    }
    return getSavedStatus(labwareId, positionId);
  }, [activeFamily, getSavedStatus, pendingByFamily, unknownStatus]);

  const queueStatusChange = useCallback((labwareId: string, positionId: number, status: string) => {
    if (!activeFamily) {
      return;
    }

    const targetKey = pendingKey(labwareId, positionId);
    const savedStatus = getSavedStatus(labwareId, positionId);

    setPendingByFamily(prev => {
      const next = { ...prev };
      const familyPending = { ...(next[activeFamily.family_id] || {}) };

      if (status === savedStatus) {
        delete familyPending[targetKey];
      } else {
        familyPending[targetKey] = status;
      }

      next[activeFamily.family_id] = familyPending;
      return next;
    });
  }, [activeFamily, getSavedStatus]);

  const applyToTip = () => {
    if (!selectedTip) {
      setError('Select a tip first to apply a status.');
      return;
    }
    queueStatusChange(selectedTip.labwareId, selectedTip.positionId, tipStatusChoice);
  };

  const applyToColumn = () => {
    if (!selectedTip) {
      setError('Select a tip first to apply a status to its column.');
      return;
    }

    const rows = snapshot?.grid?.rows || DEFAULT_GRID_ROWS;
    const columnIndex = Math.floor((selectedTip.positionId - 1) / rows);
    const start = columnIndex * rows + 1;

    for (let pos = start; pos < start + rows; pos += 1) {
      queueStatusChange(selectedTip.labwareId, pos, tipStatusChoice);
    }
  };

  const applyToRack = () => {
    if (!activeFamily || !rackChoice) {
      setError('Select a rack first.');
      return;
    }

    const positions = snapshot?.grid?.positions_per_rack || DEFAULT_GRID_ROWS * DEFAULT_GRID_COLS;
    for (let pos = 1; pos <= positions; pos += 1) {
      queueStatusChange(rackChoice, pos, rackStatusChoice);
    }
  };

  const discardPending = () => {
    if (!activeFamily || pendingCount === 0) {
      return;
    }
    setPendingByFamily(prev => {
      const next = { ...prev };
      next[activeFamily.family_id] = {};
      return next;
    });
  };

  const savePending = async () => {
    if (!activeFamily || pendingCount === 0) {
      return;
    }

    setSaving(true);
    setError('');

    try {
      const updates: TipTrackingUpdate[] = Object.entries(currentFamilyPending)
        .map(([key, status]) => {
          const parsed = parsePendingKey(key);
          if (!parsed) {
            return null;
          }
          return {
            labware_id: parsed.labwareId,
            position_id: parsed.positionId,
            status,
          };
        })
        .filter((item): item is TipTrackingUpdate => Boolean(item));

      await labwareApi.updateTipTracking(activeFamily.family_id, updates);

      setPendingByFamily(prev => {
        const next = { ...prev };
        next[activeFamily.family_id] = {};
        return next;
      });

      await loadSnapshot(false);
    } catch (err: any) {
      const message = err?.response?.data?.message || err?.message || 'Failed to save tip tracking changes';
      setError(message);
    } finally {
      setSaving(false);
    }
  };

  const resetFamily = async () => {
    if (!activeFamily) {
      return;
    }

    const confirmed = window.confirm(`Reset ${activeFamily.display_name} to its default state?`);
    if (!confirmed) {
      return;
    }

    setResetting(true);
    setError('');

    try {
      await labwareApi.resetTipTracking(activeFamily.family_id);
      setPendingByFamily(prev => {
        const next = { ...prev };
        next[activeFamily.family_id] = {};
        return next;
      });
      await loadSnapshot(false);
    } catch (err: any) {
      const message = err?.response?.data?.message || err?.message || 'Failed to reset tip family';
      setError(message);
    } finally {
      setResetting(false);
    }
  };

  const renderRack = (labwareId: string) => {
    const rows = snapshot?.grid?.rows || DEFAULT_GRID_ROWS;
    const cols = snapshot?.grid?.cols || DEFAULT_GRID_COLS;
    const positions = snapshot?.grid?.positions_per_rack || rows * cols;

    return (
      <Card key={labwareId} variant="outlined" sx={{ mb: 1.5 }}>
        <CardContent sx={{ p: 1.5 }}>
          <Typography variant="subtitle2" sx={{ mb: 1, fontFamily: 'monospace' }}>
            {labwareId}
          </Typography>

          <Box
            sx={{
              display: 'grid',
              gridTemplateColumns: `repeat(${cols}, minmax(10px, 1fr))`,
              gridTemplateRows: `repeat(${rows}, 14px)`,
              gap: 0.5,
            }}
          >
            {Array.from({ length: positions }, (_, index) => {
              const positionId = index + 1;
              const row = index % rows;
              const col = Math.floor(index / rows);

              const targetStatus = getDisplayStatus(labwareId, positionId);
              const dotColor = statusColors[targetStatus] || statusColors[unknownStatus] || '#9ca3af';

              const tipIsSelected =
                selectedTip?.labwareId === labwareId && selectedTip?.positionId === positionId;

              const key = pendingKey(labwareId, positionId);
              const tipIsPending = Boolean(currentFamilyPending[key]);

              return (
                <Box
                  key={`${labwareId}-${positionId}`}
                  onClick={() => setSelectedTip({ labwareId, positionId })}
                  title={`${labwareId} / ${positionId}: ${targetStatus}`}
                  sx={{
                    gridColumn: col + 1,
                    gridRow: row + 1,
                    width: 12,
                    height: 12,
                    borderRadius: '50%',
                    backgroundColor: dotColor,
                    border: tipIsSelected ? '2px solid #111827' : '1px solid #ffffff',
                    boxShadow: tipIsPending ? '0 0 0 2px rgba(245, 158, 11, 0.5)' : 'none',
                    cursor: 'pointer',
                    transition: 'transform 0.12s ease',
                    '&:hover': {
                      transform: 'scale(1.15)',
                    },
                  }}
                />
              );
            })}
          </Box>
        </CardContent>
      </Card>
    );
  };

  if (loading) {
    return (
      <Paper sx={{ p: 3 }}>
        <Typography>Loading tip tracking data...</Typography>
      </Paper>
    );
  }

  if (!activeFamily) {
    return (
      <Alert severity="warning">
        No tip tracking families were returned by the backend.
      </Alert>
    );
  }

  const selectedTipStatus = selectedTip ? getDisplayStatus(selectedTip.labwareId, selectedTip.positionId) : '-';

  return (
    <Stack spacing={2}>
      {error && <Alert severity="error" onClose={() => setError('')}>{error}</Alert>}

      {!canUpdate && (
        <Alert severity="info">
          You are in read-only mode because this session is remote. Tip status updates and reset are available only
          from a local session.
        </Alert>
      )}

      <Paper sx={{ p: 1.5 }}>
        <Stack direction={{ xs: 'column', sm: 'row' }} spacing={1.5} alignItems={{ sm: 'center' }}>
          <FormControl size="small" sx={{ minWidth: 180 }}>
            <InputLabel id="tip-family-select-label">Tip Family</InputLabel>
            <Select
              labelId="tip-family-select-label"
              label="Tip Family"
              value={activeFamily.family_id}
              onChange={(event) => setSelectedFamilyId(String(event.target.value))}
            >
              {families.map(family => (
                <MenuItem key={family.family_id} value={family.family_id}>
                  {family.display_name}
                </MenuItem>
              ))}
            </Select>
          </FormControl>

          <Chip label={`Pending: ${pendingCount}`} color={pendingCount > 0 ? 'warning' : 'default'} />

          <Button
            variant="outlined"
            startIcon={<RefreshIcon />}
            onClick={() => void loadSnapshot(false)}
          >
            Refresh
          </Button>

          <Button
            variant="contained"
            startIcon={<SaveIcon />}
            onClick={() => void savePending()}
            disabled={!canUpdate || pendingCount === 0 || saving}
          >
            Save
          </Button>

          <Button
            variant="outlined"
            startIcon={<DiscardIcon />}
            onClick={discardPending}
            disabled={!canUpdate || pendingCount === 0 || saving}
          >
            Discard
          </Button>

          <Button
            variant="outlined"
            color="warning"
            startIcon={<ResetIcon />}
            onClick={() => void resetFamily()}
            disabled={!canUpdate || resetting}
          >
            Reset
          </Button>
        </Stack>
      </Paper>

      <Grid container spacing={2}>
        <Grid item xs={12} md={9}>
          <Grid container spacing={2}>
            <Grid item xs={12} md={6}>
              <Paper sx={{ p: 1.5 }}>
                <Typography variant="subtitle1" sx={{ mb: 1 }}>ColA</Typography>
                {activeFamily.left_racks.map(rack => renderRack(rack))}
              </Paper>
            </Grid>

            <Grid item xs={12} md={6}>
              <Paper sx={{ p: 1.5 }}>
                <Typography variant="subtitle1" sx={{ mb: 1 }}>ColB</Typography>
                {activeFamily.right_racks.map(rack => renderRack(rack))}
              </Paper>
            </Grid>
          </Grid>
        </Grid>

        <Grid item xs={12} md={3}>
          <Paper sx={{ p: 2 }}>
            <Stack spacing={2}>
              <Box>
                <Typography variant="subtitle1">Selected Tip</Typography>
                <Typography variant="body2" sx={{ fontFamily: 'monospace' }}>
                  Rack: {selectedTip?.labwareId || '-'}
                </Typography>
                <Typography variant="body2">Position: {selectedTip?.positionId || '-'}</Typography>
                <Typography variant="body2">Status: {selectedTipStatus}</Typography>
              </Box>

              <Divider />

              <Typography variant="subtitle2">Apply to Tip / Column</Typography>

              <FormControl size="small" fullWidth>
                <InputLabel id="tip-status-select-label">Status</InputLabel>
                <Select
                  labelId="tip-status-select-label"
                  label="Status"
                  value={tipStatusChoice}
                  onChange={(event) => setTipStatusChoice(String(event.target.value))}
                >
                  {statusOrder.map(statusValue => (
                    <MenuItem key={statusValue} value={statusValue}>{statusValue}</MenuItem>
                  ))}
                </Select>
              </FormControl>

              <Button
                variant="outlined"
                startIcon={<ApplyIcon />}
                onClick={applyToTip}
                disabled={!canUpdate}
              >
                Apply to Tip
              </Button>

              <Button
                variant="outlined"
                startIcon={<ApplyIcon />}
                onClick={applyToColumn}
                disabled={!canUpdate}
              >
                Apply to Column (8)
              </Button>

              <Divider />

              <Typography variant="subtitle2">Apply to Rack</Typography>

              <FormControl size="small" fullWidth>
                <InputLabel id="rack-select-label">Rack</InputLabel>
                <Select
                  labelId="rack-select-label"
                  label="Rack"
                  value={rackChoice}
                  onChange={(event) => setRackChoice(String(event.target.value))}
                >
                  {[...activeFamily.left_racks, ...activeFamily.right_racks].map(rack => (
                    <MenuItem key={rack} value={rack}>{rack}</MenuItem>
                  ))}
                </Select>
              </FormControl>

              <FormControl size="small" fullWidth>
                <InputLabel id="rack-status-select-label">Status</InputLabel>
                <Select
                  labelId="rack-status-select-label"
                  label="Status"
                  value={rackStatusChoice}
                  onChange={(event) => setRackStatusChoice(String(event.target.value))}
                >
                  {statusOrder.map(statusValue => (
                    <MenuItem key={statusValue} value={statusValue}>{statusValue}</MenuItem>
                  ))}
                </Select>
              </FormControl>

              <Button
                variant="outlined"
                startIcon={<ApplyIcon />}
                onClick={applyToRack}
                disabled={!canUpdate}
              >
                Apply to Whole Rack
              </Button>
            </Stack>
          </Paper>

          <Paper sx={{ p: 2, mt: 2 }}>
            <Typography variant="subtitle2" sx={{ mb: 1 }}>Legend</Typography>
            <Stack spacing={1}>
              {statusOrder.map(statusValue => (
                <Stack key={statusValue} direction="row" spacing={1} alignItems="center">
                  <Box
                    sx={{
                      width: 12,
                      height: 12,
                      borderRadius: '50%',
                      backgroundColor: statusColors[statusValue] || '#9ca3af',
                      border: '1px solid #ffffff',
                    }}
                  />
                  <Typography variant="body2">{statusValue}</Typography>
                </Stack>
              ))}
            </Stack>
          </Paper>
        </Grid>
      </Grid>
    </Stack>
  );
};

export default TipTrackingPanel;
