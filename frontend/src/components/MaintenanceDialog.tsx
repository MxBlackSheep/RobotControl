import React, { useEffect, useState } from 'react';
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
import { useMaintenanceMode } from '@/hooks/useMaintenanceMode';

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
  const { active, remainingMs, reason } = useMaintenanceMode();
  const [dismissed, setDismissed] = useState(false);

  useEffect(() => {
    if (!active) {
      setDismissed(false);
    }
  }, [active]);

  if (!active) {
    return null;
  }

  const handleDismiss = () => {
    setDismissed(true);
  };

  if (dismissed) {
    return null;
  }

  return (
    <Dialog open fullWidth maxWidth="sm">
      <DialogTitle>Database Maintenance In Progress</DialogTitle>
      <DialogContent dividers>
        <Stack spacing={2}>
          <Alert severity="info">
            {reason ?? 'A database restore is currently running. Some actions are temporarily paused.'}
          </Alert>
          <Typography variant="body2" color="textSecondary">
            We will automatically resume background updates once the database is back online.
          </Typography>
          <Typography variant="body2">
            Estimated remaining time: <strong>{formatRemaining(remainingMs)}</strong>
          </Typography>
        </Stack>
      </DialogContent>
      <DialogActions>
        <Button onClick={handleDismiss} variant="contained">
          Got it
        </Button>
      </DialogActions>
    </Dialog>
  );
};

export default MaintenanceDialog;
