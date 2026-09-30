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
} from '@mui/icons-material';
import { adminAPI } from '../services/api';
import StatusChip from './StatusChip';
import { fontMono } from '../theme';
import { dayTime } from '../utils/displayTime';

// Wide enough for the table columns; narrower cards stack each account.
const userTable = '@container users (min-width: 720px)';
const userColumns = 'minmax(140px, 1fr) minmax(0, 1.4fr) 110px 180px 96px';

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
  section?: number;
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

const UserManagement: React.FC<UserManagementProps> = ({ onError, section }) => {
  const [users, setUsers] = useState<UserSummary[]>([]);
  const [userQuery, setUserQuery] = useState('');
  const visibleUsers = users.filter(user => `${user.username} ${user.email ?? ''}`.toLowerCase().includes(userQuery.trim().toLowerCase()));
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
      <Card variant="outlined" sx={{display: section === 1 ? 'none' : undefined, containerType: 'inline-size', containerName: 'users'}}>
        <CardContent>
          <Stack direction="row" alignItems="center" gap={1.5} flexWrap="wrap" sx={{ mb: 1.5 }}>
            <Typography component="h2" variant="h6">User accounts</Typography>
            <TextField size="small" label="Find a user" value={userQuery} onChange={event => setUserQuery(event.target.value)} sx={{ flex: '1 1 200px', maxWidth: 320 }} />
            <Box sx={{ flex: 1 }} />
            <Typography variant="body2" color="text.secondary">{users.length} {users.length === 1 ? 'account' : 'accounts'}</Typography>
            <Button startIcon={<RefreshIcon />} onClick={loadUsers} disabled={userLoading}>Refresh</Button>
          </Stack>

          {feedback && (
            <Alert severity="warning" sx={{ mb: 2 }}>
              {feedback}
            </Alert>
          )}

          {userLoading ? (
            <LinearProgress />
          ) : (
            <Box role="list" aria-label="User accounts">
              <Box aria-hidden sx={{ display: 'none', [userTable]: { display: 'grid' }, gridTemplateColumns: userColumns, columnGap: 2, py: 1, borderBottom: 1, borderColor: 'divider',
                fontSize: 12, fontWeight: 600, letterSpacing: 0.6, textTransform: 'uppercase', color: 'text.secondary' }}>
                <span>Username</span><span>Email</span><span>Role</span><span>Last login</span><span />
              </Box>
              {visibleUsers.map((user) => (
                <Box role="listitem" key={user.username} sx={{ display: 'grid', gridTemplateColumns: 'minmax(0, 1fr) auto', [userTable]: { gridTemplateColumns: userColumns }, columnGap: 2, rowGap: 0.25,
                  alignItems: 'center', py: 1, borderBottom: 1, borderColor: 'divider', fontSize: 14, minWidth: 0 }}>
                  <Box sx={{ minWidth: 0 }}>
                    <Typography sx={{ fontFamily: fontMono, fontSize: 14, fontWeight: 500, overflowWrap: 'anywhere' }}>{user.username}</Typography>
                    <Typography sx={{ fontSize: 13, color: 'text.secondary', overflowWrap: 'anywhere', [userTable]: { display: 'none' } }}>
                      {user.email || 'No email'} · {user.role} · {user.last_login ? `Last login ${dayTime(user.last_login)}` : 'Never signed in'}
                    </Typography>
                  </Box>
                  <Typography sx={{ display: 'none', [userTable]: { display: 'block' }, fontSize: 14, color: user.email ? 'text.primary' : 'text.secondary', overflowWrap: 'anywhere' }}>{user.email || '—'}</Typography>
                  <Box sx={{ display: 'none', [userTable]: { display: 'block' } }}><StatusChip tone={user.role === 'admin' ? 'running' : 'neutral'} label={user.role} /></Box>
                  <Typography sx={{ display: 'none', [userTable]: { display: 'block' }, fontSize: 13, color: 'text.secondary' }} title={`Created ${formatTimestamp(user.created_at)}`}>{user.last_login ? dayTime(user.last_login) : 'Never'}</Typography>
                  <Stack direction="row" alignItems="center" justifyContent="flex-end">
                    <Tooltip title="Edit email">
                      <IconButton onClick={() => openEmailEditor(user)} aria-label={`Edit email for ${user.username}`}>
                        <EditIcon fontSize="small" />
                      </IconButton>
                    </Tooltip>
                    <Tooltip title="Delete user">
                      <IconButton onClick={() => openDeleteConfirmation(user.username)} aria-label={`Delete ${user.username}`}>
                        <DeleteIcon fontSize="small" />
                      </IconButton>
                    </Tooltip>
                  </Stack>
                </Box>
              ))}

              {visibleUsers.length === 0 && (
                <Typography sx={{ py: 2, color: 'text.secondary' }}>{users.length ? 'No users match this search.' : 'No users found.'}</Typography>
              )}
            </Box>
          )}
        </CardContent>
      </Card>

      <Card variant="outlined" sx={{display: section === 0 ? 'none' : undefined}}>
        <CardContent>
          <Stack direction="row" justifyContent="space-between" alignItems="center" sx={{ mb: 1.5 }}>
            <Typography component="h2" variant="h6">Password reset requests</Typography>
            <Button startIcon={<RefreshIcon />} onClick={loadPasswordResetRequests} disabled={requestsLoading}>Refresh</Button>
          </Stack>


          {requestsLoading ? (
            <LinearProgress />
          ) : (
            <List disablePadding>
              {resetRequests.map((request) => (
                <ListItem key={request.id} divider alignItems="flex-start" sx={{ gap: 1, flexWrap: "wrap", px: 0 }}>
                  <ListItemText
                    sx={{ flex: "1 1 240px", minWidth: 0, overflowWrap: "anywhere" }}
                    primaryTypographyProps={{ component: "div" }} secondaryTypographyProps={{ component: "div" }}
                    primary={
                      <Stack spacing={0.5}>
                        <Typography variant="subtitle1" fontWeight={600}>
                          <Box component="span" sx={{ fontFamily: fontMono }}>{request.username}</Box>
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
                  <Stack direction="row" alignItems="center" sx={{ ml: "auto" }}>
                    <Button
                      variant="contained"
                      size="small"
                      onClick={() => openResetDialog(request)}
                    >
                      Reset password
                    </Button>
                  </Stack>
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
