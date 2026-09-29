import React, { useEffect, useRef } from 'react';
import Alert from '@mui/material/Alert';
import Button from '@mui/material/Button';
import Dialog from '@mui/material/Dialog';
import DialogActions from '@mui/material/DialogActions';
import DialogContent from '@mui/material/DialogContent';
import DialogTitle from '@mui/material/DialogTitle';

import { normalizeMultilineText } from '@/utils/text';

export type StatusSeverity = 'success' | 'error' | 'info' | 'warning';

export interface StatusMessage {
  message: string;
  title?: string;
  severity?: StatusSeverity;
  autoCloseMs?: number;
  action?: { label: string; onClick: () => void };
}

const DEFAULT_TITLES: Record<StatusSeverity, string> = {
  error: 'Error',
  warning: 'Warning',
  info: 'Information',
  success: 'Success',
};

/** Result of a user action. The owner holds `status` and clears it in `onClose`. */
const StatusDialog: React.FC<{ status: StatusMessage | null; onClose: () => void }> = ({ status, onClose }) => {
  // Keep the last message rendered while the dialog fades out after `status` is cleared.
  const shown = useRef<StatusMessage | null>(status);
  if (status) shown.current = status;
  const { message = '', title, severity = 'info', action } = shown.current ?? {};

  // Owners often pass an inline onClose; a re-render must not restart the timer.
  const close = useRef(onClose);
  close.current = onClose;
  useEffect(() => {
    if (!status?.autoCloseMs) return;
    const timeout = window.setTimeout(() => close.current(), status.autoCloseMs);
    return () => window.clearTimeout(timeout);
  }, [status]);

  return (
    <Dialog open={Boolean(status)} onClose={onClose} fullWidth maxWidth="sm" aria-describedby="status-dialog-message">
      <DialogTitle>{title || DEFAULT_TITLES[severity]}</DialogTitle>
      <DialogContent dividers>
        <Alert severity={severity} id="status-dialog-message" sx={{ whiteSpace: 'pre-line' }}>
          {normalizeMultilineText(message)}
        </Alert>
      </DialogContent>
      <DialogActions sx={{ px: 3, py: 2 }}>
        {action && (
          <Button variant="contained" onClick={() => { onClose(); action.onClick(); }}>{action.label}</Button>
        )}
        <Button onClick={onClose} variant={action ? 'outlined' : 'contained'} color="inherit">Close</Button>
      </DialogActions>
    </Dialog>
  );
};

export default StatusDialog;
