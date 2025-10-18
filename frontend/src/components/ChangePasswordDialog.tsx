import React, { useState } from 'react';
import {
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  TextField,
  Button,
  Alert,
  Box,
} from '@mui/material';
import { isAxiosError } from 'axios';
import { useAuth } from '@/context/AuthContext';

interface ChangePasswordDialogProps {
  open: boolean;
  onClose: () => void;
  onSuccess?: () => void;
  requireChange?: boolean;
}

const ChangePasswordDialog: React.FC<ChangePasswordDialogProps> = ({
  open,
  onClose,
  onSuccess,
  requireChange = false,
}) => {
  const { changePassword } = useAuth();
  const [currentPassword, setCurrentPassword] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);

  const handleClose = () => {
    if (loading) {
      return;
    }

    if (!requireChange) {
      onClose();
    }
  };

  const resetForm = () => {
    setCurrentPassword('');
    setNewPassword('');
    setConfirmPassword('');
    setError(null);
    setSuccessMessage(null);
  };

  const handleSubmit = async (event: React.FormEvent) => {
    event.preventDefault();

    if (newPassword !== confirmPassword) {
      setError('New passwords do not match');
      return;
    }

    setLoading(true);
    setError(null);
    setSuccessMessage(null);

    try {
      await changePassword(currentPassword, newPassword);
      setSuccessMessage('Password changed successfully. You may continue using the app.');
      if (onSuccess) {
        onSuccess();
      }
      resetForm();
      onClose();
    } catch (err) {
      if (isAxiosError(err)) {
        const message =
          err.response?.data?.error?.message ||
          err.response?.data?.message ||
          'Incorrect current password';
        setError(message);
      } else {
        setError('Unable to change password. Please try again.');
      }
    } finally {
      setLoading(false);
    }
  };

  return (
    <Dialog open={open} onClose={handleClose} fullWidth maxWidth="xs">
      <DialogTitle>
        {requireChange ? 'Password Reset Required' : 'Change Password'}
      </DialogTitle>
      <Box component="form" onSubmit={handleSubmit}>
        <DialogContent dividers>
          <Alert severity="info" sx={{ mb: 2 }}>
            Use a strong password that you do not reuse elsewhere.
          </Alert>
          {error && (
            <Alert severity="error" sx={{ mb: 2 }}>
              {error}
            </Alert>
          )}
          {successMessage && (
            <Alert severity="success" sx={{ mb: 2 }}>
              {successMessage}
            </Alert>
          )}
          <TextField
            fullWidth
            type="password"
            label="Current Password"
            value={currentPassword}
            onChange={(event) => setCurrentPassword(event.target.value)}
            margin="normal"
            required
            autoFocus
          />
          <TextField
            fullWidth
            type="password"
            label="New Password"
            value={newPassword}
            onChange={(event) => setNewPassword(event.target.value)}
            margin="normal"
            required
            helperText="At least 8 characters, include numbers and symbols for strength."
          />
          <TextField
            fullWidth
            type="password"
            label="Confirm New Password"
            value={confirmPassword}
            onChange={(event) => setConfirmPassword(event.target.value)}
            margin="normal"
            required
          />
        </DialogContent>
        <DialogActions sx={{ px: 3, py: 2 }}>
          <Button
            onClick={handleClose}
            color="inherit"
            disabled={loading || requireChange}
          >
            Cancel
          </Button>
          <Button
            variant="contained"
            color="primary"
            type="submit"
            disabled={loading}
          >
            {loading ? 'Updating...' : 'Update Password'}
          </Button>
        </DialogActions>
      </Box>
    </Dialog>
  );
};

export default ChangePasswordDialog;
