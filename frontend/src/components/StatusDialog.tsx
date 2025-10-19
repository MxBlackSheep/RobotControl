import React, { useEffect, useMemo } from 'react';
import Button, { ButtonProps } from '@mui/material/Button';
import Alert from '@mui/material/Alert';
import Typography from '@mui/material/Typography';

import Modal, { ModalProps } from './Modal';
import { normalizeMultilineText } from '@/utils/text';

export type StatusSeverity = 'success' | 'error' | 'info' | 'warning';

export interface StatusDialogAction {
  label: string;
  onClick: () => void;
  color?: ButtonProps['color'];
  variant?: ButtonProps['variant'];
  autoFocus?: boolean;
  startIcon?: React.ReactNode;
}

export interface StatusDialogProps
  extends Omit<ModalProps, 'open' | 'onClose' | 'title' | 'actions' | 'children'> {
  open: boolean;
  onClose: () => void;
  title?: string;
  message: string | React.ReactNode;
  severity?: StatusSeverity;
  closeLabel?: string;
  primaryAction?: StatusDialogAction;
  secondaryAction?: StatusDialogAction;
  autoCloseMs?: number;
}

const StatusDialog: React.FC<StatusDialogProps> = ({
  open,
  onClose,
  title,
  message,
  severity = 'info',
  closeLabel = 'Close',
  primaryAction,
  secondaryAction,
  autoCloseMs,
  fullWidth = true,
  maxWidth = 'sm',
  ...modalProps
}) => {
  useEffect(() => {
    if (!open || !autoCloseMs) {
      return;
    }

    const timeout = window.setTimeout(() => {
      onClose();
    }, autoCloseMs);

    return () => window.clearTimeout(timeout);
  }, [open, autoCloseMs, onClose]);

  const renderedMessage = useMemo(() => {
    if (typeof message === 'string') {
      return (
        <Typography variant="body2" sx={{ whiteSpace: 'pre-line' }}>
          {normalizeMultilineText(message)}
        </Typography>
      );
    }

    return message;
  }, [message]);

  const makeButton = (action: StatusDialogAction, fallbackVariant: ButtonProps['variant'] = 'contained') => (
    <Button
      key={action.label}
      onClick={action.onClick}
      color={action.color ?? 'primary'}
      variant={action.variant ?? fallbackVariant}
      autoFocus={action.autoFocus}
      startIcon={action.startIcon}
    >
      {action.label}
    </Button>
  );

  const actions = (
    <>
      {secondaryAction && makeButton(secondaryAction, 'outlined')}
      {primaryAction && makeButton(primaryAction)}
      <Button onClick={onClose} variant={primaryAction ? 'outlined' : 'contained'} color="inherit">
        {closeLabel}
      </Button>
    </>
  );

  return (
    <Modal
      open={open}
      onClose={onClose}
      title={title}
      closeButton={false}
      actions={actions}
      fullWidth={fullWidth}
      maxWidth={maxWidth}
      ariaDescribedBy="status-dialog-description"
      {...modalProps}
    >
      <Alert severity={severity} role="alert">
        {renderedMessage}
      </Alert>
    </Modal>
  );
};

export default StatusDialog;
