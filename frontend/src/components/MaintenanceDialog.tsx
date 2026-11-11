import React, { useEffect, useState, useSyncExternalStore } from 'react';
import {
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  Button,
  Typography,
  Stack,
  Alert,
} from '@mui/material';
import { getMaintenanceExpiry, subscribeToMaintenance } from '@/utils/MaintenanceManager';

const formatRemaining = (remainingMs: number) => {
  if (remainingMs <= 0) {
    return 'a few moments';
  }
  const seconds = Math.ceil(remainingMs / 1000);
  if (seconds < 60) {
    return `${seconds}s`;
  }
  const minutes = Math.floor(seconds / 60);
  const leftover = seconds % 60;
  if (leftover === 0) {
    return `${minutes}m`;
  }
  return `${minutes}m ${leftover}s`;
};

const MaintenanceDialog: React.FC = () => {
  const expiresAt = useSyncExternalStore(subscribeToMaintenance, getMaintenanceExpiry);
  // "Got it" hides the dialog for this pause only; the next restore sets a new end time.
  const [dismissedAt, setDismissedAt] = useState(0);
  const [now, setNow] = useState(Date.now);

  // The countdown ticks only while the dialog can be open and stops when the pause ends.
  useEffect(() => {
    if (expiresAt === dismissedAt) return;
    const tick = () => {
      const time = Date.now();
      setNow(time);
      if (time >= expiresAt) clearInterval(timer);
    };
    const timer = setInterval(tick, 1000);
    tick();
    return () => clearInterval(timer);
  }, [expiresAt, dismissedAt]);

  if (expiresAt <= now || expiresAt === dismissedAt) {
    return null;
  }

  return (
    <Dialog open fullWidth maxWidth="sm">
      <DialogTitle>Database Maintenance In Progress</DialogTitle>
      <DialogContent dividers>
        <Stack spacing={2}>
          <Alert severity="info">Database restore is finishing.</Alert>
          <Typography variant="body2">
            Estimated remaining time: <strong>{formatRemaining(expiresAt - now)}</strong>
          </Typography>
        </Stack>
      </DialogContent>
      <DialogActions>
        <Button onClick={() => setDismissedAt(expiresAt)} variant="contained">
          Got it
        </Button>
      </DialogActions>
    </Dialog>
  );
};

export default MaintenanceDialog;
