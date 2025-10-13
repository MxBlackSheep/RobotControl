import React, { useEffect, useState } from 'react';
import {
  Alert,
  Box,
  Card,
  CardContent,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  IconButton,
  LinearProgress,
  List,
  ListItem,
  ListItemSecondaryAction,
  ListItemText,
  Stack,
  TextField,
  Typography,
  Button,
  Tooltip,
} from '@mui/material';
import {
  Edit as EditIcon,
  Delete as DeleteIcon,
  Refresh as RefreshIcon,
  AdminPanelSettings as AdminIcon,
  Person as PersonIcon,
  Security as SecurityIcon,
} from '@mui/icons-material';
import { adminAPI } from '../services/api';

interface UserSummary {
  username: string;
  email?: string;
  role: string;
  created_at?: string;
  last_login?: string;
}

interface PasswordResetRequest {
  id: number;
  user_id?: number | null;
  username: string;
  email: string;
  status: string;
  note?: string | null;
  client_ip?: string | null;
  user_agent?: string | null;
  requested_at?: string | null;
  resolved_at?: string | null;
  resolved_by?: string | null;
  resolution_note?: string | null;
}

interface UserManagementProps {
  onError?: (error: string) => void;
}

const formatTimestamp = (value?: string) => {
  if (!value) return '—';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }
  return date.toLocaleString();
};

const coerceArray = <T,>(payload: any): T[] => {
  if (Array.isArray(payload)) {
    return payload;
  }
  if (Array.isArray(payload?.data)) {
    return payload.data as T[];
  }
  return [];
};

const UserManagement: React.FC<UserManagementProps> = ({ onError }) => {
  const [users, setUsers] = useState<UserSummary[]>([]);
  const [userLoading, setUserLoading] = useState(false);
  const [resetRequests, setResetRequests] = useState<PasswordResetRequest[]>([]);
  const [requestsLoading, setRequestsLoading] = useState(false);
  const [feedback, setFeedback] = useState<string | null>(null);

  const [emailDialog, setEmailDialog] = useState({
    open: false,
    username: '',
    email: '',
    submitting: false,
  });

  const [deleteDialog, setDeleteDialog] = useState({
    open: false,
    username: '',
    submitting: false,
  });

  const [resetDialog, setResetDialog] = useState({
    open: false,
    request: null as PasswordResetRequest | null,
    tempPassword: '',
    resolutionNote: '',
    submitting: false,
    error: '',
  });

  const loadUsers = async () => {
    try {
      setUserLoading(true);
      const response = await adminAPI.getUsers();
      setUsers(coerceArray<UserSummary>(response.data));
    } catch (error: any) {
      const message = error.response?.data?.detail || 'Failed to load users';
      if (onError) onError(message);
    } finally {
      setUserLoading(false);
    }
  };

  const loadPasswordResetRequests = async () => {
    try {
      setRequestsLoading(true);
      const response = await adminAPI.getPasswordResetRequests();
      setResetRequests(coerceArray<PasswordResetRequest>(response.data));
    } catch (error: any) {
      const message = error.response?.data?.detail || 'Failed to load password reset requests';
      if (onError) onError(message);
    } finally {
      setRequestsLoading(false);
    }
  };

  useEffect(() => {
    loadUsers();
    loadPasswordResetRequests();
  }, []);

  const openEmailEditor = (user: UserSummary) => {
    setEmailDialog({
      open: true,
      username: user.username,
      email: user.email ?? '',
      submitting: false,
    });
    setFeedback(null);
  };

  const submitEmailUpdate = async () => {
    const email = emailDialog.email.trim();
    if (!email) {
      setFeedback('Email address is required.');
      return;
    }

    try {
      setEmailDialog((prev) => ({ ...prev, submitting: true }));
      await adminAPI.updateUserEmail(emailDialog.username, email);
      await loadUsers();
      setEmailDialog({ open: false, username: '', email: '', submitting: false });
    } catch (error: any) {
      const message =
        error.response?.data?.message ||
        error.response?.data?.detail ||
        'Failed to update email address';
      setFeedback(message);
      if (onError) onError(message);
      setEmailDialog((prev) => ({ ...prev, submitting: false }));
    }
  };

  const openDeleteConfirmation = (username: string) => {
    setDeleteDialog({ open: true, username, submitting: false });
    setFeedback(null);
  };

  const confirmDelete = async () => {
    try {
      setDeleteDialog((prev) => ({ ...prev, submitting: true }));
      await adminAPI.deleteUser(deleteDialog.username);
      await loadUsers();
      setDeleteDialog({ open: false, username: '', submitting: false });
    } catch (error: any) {
      const message =
        error.response?.data?.message ||
        error.response?.data?.detail ||
        'Failed to delete user';
      setFeedback(message);
      if (onError) onError(message);
      setDeleteDialog((prev) => ({ ...prev, submitting: false }));
    }
  };

  const openResetDialog = (request: PasswordResetRequest) => {
    setResetDialog({
      open: true,
      request,
      tempPassword: '',
      resolutionNote: '',
      submitting: false,
      error: '',
    });
    setFeedback(null);
  };

  const closeResetDialog = () => {
    setResetDialog({
      open: false,
      request: null,
      tempPassword: '',
      resolutionNote: '',
      submitting: false,
      error: '',
    });
  };

  const submitResetDialog = async () => {
    if (!resetDialog.request) {
      return;
    }

    if (!resetDialog.tempPassword.trim()) {
      setResetDialog((prev) => ({ ...prev, error: 'Temporary password is required.' }));
      return;
    }

    try {
      setResetDialog((prev) => ({ ...prev, submitting: true, error: '' }));
      await adminAPI.resetUserPassword(
        resetDialog.request.username,
        resetDialog.tempPassword.trim(),
        true,
      );
      await adminAPI.resolvePasswordResetRequest(
        resetDialog.request.id,
        resetDialog.resolutionNote.trim() || 'Password reset by administrator',
      );
      await Promise.all([loadPasswordResetRequests(), loadUsers()]);
      closeResetDialog();
    } catch (error: any) {
      const message =
        error.response?.data?.detail ||
        error.response?.data?.message ||
        'Failed to reset password';
      setResetDialog((prev) => ({ ...prev, error: message, submitting: false }));
      if (onError) onError(message);
    }
  };

  return (
    <Stack spacing={3}>
      <Card>
        <CardContent>
          <Stack direction="row" justifyContent="space-between" alignItems="center" sx={{ mb: 2 }}>
            <Stack direction="row" spacing={1} alignItems="center">
              <AdminIcon color="primary" />
              <Typography variant="h6">User Accounts</Typography>
            </Stack>
            <Tooltip title="Refresh users">
              <IconButton onClick={loadUsers} size="small" disabled={userLoading}>
                <RefreshIcon />
              </IconButton>
            </Tooltip>
          </Stack>

          <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
            Update user email addresses or delete accounts. Other profile attributes are read-only.
          </Typography>

          {feedback && (
            <Alert severity="warning" sx={{ mb: 2 }}>
              {feedback}
            </Alert>
          )}

          {userLoading ? (
            <LinearProgress />
          ) : (
            <List disablePadding>
              {users.map((user) => (
                <ListItem key={user.username} divider>
                  <ListItemText
                    primary={
                      <Stack direction="row" spacing={1} alignItems="center">
                        {user.role === 'admin' ? (
                          <AdminIcon fontSize="small" />
                        ) : (
                          <PersonIcon fontSize="small" />
                        )}
                        <Typography variant="subtitle1" fontWeight={600}>
                          {user.username}
                        </Typography>
                        <Typography variant="caption" color="text.secondary">
                          {user.role}
                        </Typography>
                      </Stack>
                    }
                    secondary={
                      <Box sx={{ mt: 0.5 }}>
                        <Typography variant="body2">Email: {user.email || '—'}</Typography>
                        <Typography variant="caption" color="text.secondary">
                          Created: {formatTimestamp(user.created_at)} • Last login: {formatTimestamp(user.last_login)}
                        </Typography>
                      </Box>
                    }
                  />
                  <ListItemSecondaryAction>
                    <Tooltip title="Edit email">
                      <IconButton
                        edge="end"
                        onClick={() => openEmailEditor(user)}
                        aria-label={`Edit email for ${user.username}`}
                      >
                        <EditIcon />
                      </IconButton>
                    </Tooltip>
                    <Tooltip title="Delete user">
                      <IconButton
                        edge="end"
                        sx={{ ml: 1 }}
                        onClick={() => openDeleteConfirmation(user.username)}
                        aria-label={`Delete ${user.username}`}
                      >
                        <DeleteIcon />
                      </IconButton>
                    </Tooltip>
                  </ListItemSecondaryAction>
                </ListItem>
              ))}

              {users.length === 0 && (
                <ListItem>
                  <ListItemText primary="No users found." />
                </ListItem>
              )}
            </List>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardContent>
          <Stack direction="row" justifyContent="space-between" alignItems="center" sx={{ mb: 2 }}>
            <Stack direction="row" spacing={1} alignItems="center">
              <SecurityIcon color="primary" />
              <Typography variant="h6">Password Reset Requests</Typography>
            </Stack>
            <Tooltip title="Refresh requests">
              <IconButton onClick={loadPasswordResetRequests} size="small" disabled={requestsLoading}>
                <RefreshIcon />
              </IconButton>
            </Tooltip>
          </Stack>

          <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
            Process reset requests by issuing a temporary password and recording the resolution.
          </Typography>

          {requestsLoading ? (
            <LinearProgress />
          ) : (
            <List disablePadding>
              {resetRequests.map((request) => (
                <ListItem key={request.id} divider alignItems="flex-start">
                  <ListItemText
                    primary={
                      <Stack spacing={0.5}>
                        <Typography variant="subtitle1" fontWeight={600}>
                          {request.username}
                        </Typography>
                        <Typography variant="body2" color="text.secondary">
                          {request.email}
                        </Typography>
                      </Stack>
                    }
                    secondary={
                      <Box sx={{ mt: 0.5 }}>
                        <Typography variant="caption" color="text.secondary" display="block">
                          Requested: {formatTimestamp(request.requested_at)}
                        </Typography>
                        {request.note && (
                          <Typography variant="caption" color="text.secondary" display="block">
                            Note: {request.note}
                          </Typography>
                        )}
                      </Box>
                    }
                  />
                  <ListItemSecondaryAction>
                    <Button
                      variant="contained"
                      size="small"
                      onClick={() => openResetDialog(request)}
                    >
                      Reset Password
                    </Button>
                  </ListItemSecondaryAction>
                </ListItem>
              ))}

              {resetRequests.length === 0 && (
                <ListItem>
                  <ListItemText primary="No password reset requests at this time." />
                </ListItem>
              )}
            </List>
          )}
        </CardContent>
      </Card>

      <Dialog
        open={emailDialog.open}
        onClose={() =>
          emailDialog.submitting
            ? undefined
            : setEmailDialog({ open: false, username: '', email: '', submitting: false })
        }
        fullWidth
        maxWidth="sm"
      >
        <DialogTitle>Update Email</DialogTitle>
        <DialogContent dividers>
          <TextField
            label="Email address"
            type="email"
            value={emailDialog.email}
            onChange={(event) =>
              setEmailDialog((prev) => ({ ...prev, email: event.target.value }))
            }
            fullWidth
            autoFocus
            disabled={emailDialog.submitting}
          />
        </DialogContent>
        <DialogActions>
          <Button
            onClick={() =>
              setEmailDialog({ open: false, username: '', email: '', submitting: false })
            }
            disabled={emailDialog.submitting}
          >
            Cancel
          </Button>
          <Button onClick={submitEmailUpdate} variant="contained" disabled={emailDialog.submitting}>
            {emailDialog.submitting ? 'Saving…' : 'Save'}
          </Button>
        </DialogActions>
      </Dialog>

      <Dialog
        open={deleteDialog.open}
        onClose={() =>
          deleteDialog.submitting
            ? undefined
            : setDeleteDialog({ open: false, username: '', submitting: false })
        }
        maxWidth="xs"
        fullWidth
      >
        <DialogTitle>Delete User</DialogTitle>
        <DialogContent dividers>
          <Typography variant="body2">
            Permanently delete the account <strong>{deleteDialog.username}</strong>? This action cannot
            be undone.
          </Typography>
        </DialogContent>
        <DialogActions>
          <Button
            onClick={() => setDeleteDialog({ open: false, username: '', submitting: false })}
            disabled={deleteDialog.submitting}
          >
            Cancel
          </Button>
          <Button
            onClick={confirmDelete}
            variant="contained"
            color="error"
            disabled={deleteDialog.submitting}
          >
            {deleteDialog.submitting ? 'Deleting…' : 'Delete'}
          </Button>
        </DialogActions>
      </Dialog>

      <Dialog
        open={resetDialog.open}
        onClose={() => (resetDialog.submitting ? undefined : closeResetDialog())}
        fullWidth
        maxWidth="sm"
      >
        <DialogTitle>Reset password for {resetDialog.request?.username}</DialogTitle>
        <DialogContent dividers>
          <Stack spacing={2}>
            <Typography variant="body2" color="text.secondary">
              Provide a temporary password to share with the user. They will be required to change it
              after logging in.
            </Typography>
            <TextField
              label="Temporary password"
              value={resetDialog.tempPassword}
              onChange={(event) =>
                setResetDialog((prev) => ({ ...prev, tempPassword: event.target.value }))
              }
              type="text"
              required
              autoFocus
              disabled={resetDialog.submitting}
            />
            <TextField
              label="Resolution note (optional)"
              value={resetDialog.resolutionNote}
              onChange={(event) =>
                setResetDialog((prev) => ({ ...prev, resolutionNote: event.target.value }))
              }
              multiline
              minRows={2}
              placeholder="Example: Reset to temporary lab password over phone"
              disabled={resetDialog.submitting}
            />
            {resetDialog.error && (
              <Alert
                severity="error"
                onClose={() => setResetDialog((prev) => ({ ...prev, error: '' }))}
              >
                {resetDialog.error}
              </Alert>
            )}
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={closeResetDialog} disabled={resetDialog.submitting}>
            Cancel
          </Button>
          <Button onClick={submitResetDialog} variant="contained" disabled={resetDialog.submitting}>
            {resetDialog.submitting ? 'Resetting…' : 'Reset & Resolve'}
          </Button>
        </DialogActions>
      </Dialog>
    </Stack>
  );
};

export default UserManagement;
