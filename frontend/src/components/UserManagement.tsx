import React, { useState, useEffect } from 'react';
import {
  Box,
  Typography,
  Card,
  CardContent,
  List,
  ListItem,
  ListItemText,
  ListItemSecondaryAction,
  IconButton,
  Chip,
  Button,
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  Alert,
  Divider,
  LinearProgress,
  Tooltip,
  TextField,
  Stack,
} from '@mui/material';
import {
  PersonAdd as AddUserIcon,
  Edit as EditIcon,
  Delete as DeleteIcon,
  ToggleOn,
  ToggleOff,
  Refresh as RefreshIcon,
  Security as SecurityIcon,
  AdminPanelSettings as AdminIcon,
  Person as PersonIcon
} from '@mui/icons-material';
import { api, adminAPI } from '../services/api';

interface User {
  username: string;
  email?: string;
  role: string;
  is_active: boolean;
  last_login?: string;
  created_at?: string;
  must_reset?: boolean;
  last_login_ip?: string | null;
  last_login_ip_type?: string | null;
}

interface PasswordResetRequest {
  id: number;
  user_id?: number | null;
  username: string;
  email: string;
  status: 'pending' | 'resolved' | string;
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

export default function UserManagement({ onError }: UserManagementProps) {
  const [users, setUsers] = useState<User[]>([]);
  const [loading, setLoading] = useState(false);
  const [resetRequests, setResetRequests] = useState<PasswordResetRequest[]>([]);
  const [requestsLoading, setRequestsLoading] = useState(false);
  const [activeRequest, setActiveRequest] = useState<PasswordResetRequest | null>(null);
  const [tempPassword, setTempPassword] = useState('');
  const [resolutionNote, setResolutionNote] = useState('');
  const [dialogSubmitting, setDialogSubmitting] = useState(false);
  const [dialogError, setDialogError] = useState('');
  const [confirmDialog, setConfirmDialog] = useState<{
    open: boolean;
    title: string;
    message: string;
    action: () => void;
  }>({
    open: false,
    title: '',
    message: '',
    action: () => {}
  });

  const extractArray = (raw: any): any[] => {
    if (Array.isArray(raw)) {
      return raw;
    }
    if (Array.isArray(raw?.data)) {
      return raw.data;
    }
    return [];
  };

  const loadUsers = async () => {
    try {
      setLoading(true);
      const response = await adminAPI.getUsers();
      const payload = extractArray(response.data);
      setUsers(payload);
    } catch (err: any) {
      const errorMessage = err.response?.data?.detail || 'Failed to load users';
      if (onError) onError(errorMessage);
    } finally {
      setLoading(false);
    }
  };

  const loadPasswordResetRequests = async () => {
    try {
      setRequestsLoading(true);
      const response = await adminAPI.getPasswordResetRequests();
      const payload = extractArray(response.data);
      setResetRequests(payload);
    } catch (err: any) {
      const errorMessage = err.response?.data?.detail || 'Failed to load password reset requests';
      if (onError) onError(errorMessage);
    } finally {
      setRequestsLoading(false);
    }
  };

  const formatDateTime = (value?: string | null) => {
    if (!value) return '—';
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) {
      return value;
    }
    return date.toLocaleString();
  };

  const handleResolveRequest = async (requestId: number, note?: string) => {
    try {
      await adminAPI.resolvePasswordResetRequest(requestId, note);
      await loadPasswordResetRequests();
    } catch (err: any) {
      const errorMessage = err.response?.data?.detail || 'Failed to resolve request';
      if (onError) onError(errorMessage);
    }
  };

  const openResetDialog = (request: PasswordResetRequest) => {
    setActiveRequest(request);
    setTempPassword('');
    setResolutionNote('');
    setDialogError('');
    setDialogSubmitting(false);
  };

  const closeResetDialog = () => {
    setActiveRequest(null);
    setTempPassword('');
    setResolutionNote('');
    setDialogError('');
    setDialogSubmitting(false);
  };

  const submitResetDialog = async () => {
    if (!activeRequest) {
      return;
    }

    if (!tempPassword.trim()) {
      setDialogError('Provide a temporary password before resetting');
      return;
    }

    try {
      setDialogSubmitting(true);
      setDialogError('');
      await adminAPI.resetUserPassword(activeRequest.username, tempPassword.trim(), true);
      await adminAPI.resolvePasswordResetRequest(
        activeRequest.id,
        resolutionNote.trim() || 'Password reset by administrator',
      );
      await Promise.all([loadPasswordResetRequests(), loadUsers()]);
      closeResetDialog();
    } catch (err: any) {
      const errorMessage = err.response?.data?.detail || 'Failed to reset password';
      setDialogError(errorMessage);
      if (onError) onError(errorMessage);
    } finally {
      setDialogSubmitting(false);
    }
  };

  const toggleUserActive = async (username: string) => {
    try {
      await api.post(`/admin/users/${username}/toggle-active`);
      await loadUsers(); // Reload users
    } catch (err: any) {
      const errorMessage = err.response?.data?.detail || 'Failed to update user status';
      if (onError) onError(errorMessage);
    }
  };

  const handleToggleActive = (user: User) => {
    if (user.username === 'admin') {
      if (onError) onError('Cannot deactivate the main admin account');
      return;
    }

    const action = user.is_active ? 'deactivate' : 'activate';
    setConfirmDialog({
      open: true,
      title: `${action.charAt(0).toUpperCase() + action.slice(1)} User`,
      message: `Are you sure you want to ${action} user "${user.username}"?`,
      action: () => {
        toggleUserActive(user.username);
        setConfirmDialog(prev => ({ ...prev, open: false }));
      }
    });
  };

  const getRoleIcon = (role: string) => {
    switch (role) {
      case 'admin':
        return <AdminIcon color="primary" />;
      case 'user':
        return <PersonIcon color="action" />;
      default:
        return <SecurityIcon color="action" />;
    }
  };

  const getRoleColor = (role: string): "primary" | "secondary" | "default" => {
    switch (role) {
      case 'admin':
        return 'primary';
      case 'user':
        return 'default';
      default:
        return 'secondary';
    }
  };

  useEffect(() => {
    loadUsers();
    loadPasswordResetRequests();
  }, []);

  return (
    <Box>
      <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 2 }}>
        <Box>
          <Typography 
            variant="h6" 
            sx={{ fontWeight: 600 }}
            id="user-management-title"
          >
            User Management
          </Typography>
          <Typography variant="body2" color="text.secondary">
            Manage user accounts and permissions
          </Typography>
        </Box>
        <Box>
          <Button
            startIcon={<RefreshIcon />}
            onClick={loadUsers}
            disabled={loading}
            sx={{ mr: 1 }}
          >
            Refresh
          </Button>
          <Button
            startIcon={<AddUserIcon />}
            variant="contained"
            disabled // For future implementation
          >
            Add User
          </Button>
        </Box>
      </Box>

      {loading && <LinearProgress sx={{ mb: 2 }} />}

      <Card>
        <CardContent>
          <Typography 
            variant="subtitle1" 
            sx={{ mb: 2, fontWeight: 600 }}
            id="user-list-title"
          >
            System Users ({users.length})
          </Typography>
          
          {users.length === 0 ? (
            <Alert severity="info">
              No users found. This might indicate a system issue.
            </Alert>
          ) : (
            <List 
              role="list"
              aria-labelledby="user-list-title"
            >
              {users.map((user, index) => (
                <React.Fragment key={user.username}>
                  <ListItem sx={{ px: 0 }}>
                    <ListItemText
                      primary={
                        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                          {getRoleIcon(user.role)}
                          <Typography variant="subtitle1" sx={{ fontWeight: 500 }}>
                            {user.username}
                          </Typography>
                          <Chip 
                            label={user.role} 
                            size="small" 
                            color={getRoleColor(user.role)}
                          />
                          <Chip 
                            label={user.is_active ? 'Active' : 'Inactive'}
                            size="small"
                            color={user.is_active ? 'success' : 'default'}
                            variant={user.is_active ? 'filled' : 'outlined'}
                          />
                        </Box>
                      }
                      secondary={
                        <Box sx={{ mt: 0.5 }}>
                          <Typography variant="body2" color="text.secondary">
                            {user.last_login 
                              ? `Last login: ${new Date(user.last_login).toLocaleString()}`
                              : 'Never logged in'
                            }
                          </Typography>
                          {user.created_at && (
                            <Typography variant="body2" color="text.secondary">
                              Created: {new Date(user.created_at).toLocaleDateString()}
                            </Typography>
                          )}
                        </Box>
                      }
                    />
                    <ListItemSecondaryAction>
                      <Box sx={{ display: 'flex', gap: 1 }}>
                        {/* Edit User - Future implementation */}
                        <Tooltip title="Edit user (coming soon)">
                          <span>
                            <IconButton 
                              size="small" 
                              disabled
                            >
                              <EditIcon />
                            </IconButton>
                          </span>
                        </Tooltip>

                        {/* Toggle Active Status */}
                        <Tooltip title={user.is_active ? 'Deactivate user' : 'Activate user'}>
                          <span>
                            <IconButton
                              size="small"
                              onClick={() => handleToggleActive(user)}
                              disabled={user.username === 'admin'}
                              color={user.is_active ? 'primary' : 'default'}
                            >
                              {user.is_active ? <ToggleOn /> : <ToggleOff />}
                            </IconButton>
                          </span>
                        </Tooltip>

                        {/* Delete User - Future implementation */}
                        <Tooltip title="Delete user (coming soon)">
                          <span>
                            <IconButton 
                              size="small" 
                              disabled
                              color="error"
                            >
                              <DeleteIcon />
                            </IconButton>
                          </span>
                        </Tooltip>
                      </Box>
                    </ListItemSecondaryAction>
                  </ListItem>
                  {index < users.length - 1 && <Divider />}
                </React.Fragment>
              ))}
            </List>
          )}
        </CardContent>
      </Card>

      <Card sx={{ mt: 2 }}>
        <CardContent>
          <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 2 }}>
            <Box>
              <Typography variant="subtitle1" sx={{ fontWeight: 600 }}>
                Password Reset Requests ({resetRequests.length})
              </Typography>
              <Typography variant="body2" color="text.secondary">
                Review pending requests and respond with reset actions
              </Typography>
            </Box>
            <Button
              startIcon={<RefreshIcon />}
              onClick={loadPasswordResetRequests}
              disabled={requestsLoading}
            >
              Refresh
            </Button>
          </Box>

          {requestsLoading && <LinearProgress sx={{ mb: 2 }} />}

          {!requestsLoading && resetRequests.length === 0 ? (
            <Alert severity="success">
              No pending reset requests. Users can submit new requests from the login page.
            </Alert>
          ) : (
            <List>
              {resetRequests.map((request, index) => (
                <React.Fragment key={request.id}>
                  <ListItem alignItems="flex-start" sx={{ px: 0 }}>
                    <ListItemText
                      primary={
                        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, flexWrap: 'wrap' }}>
                          <Typography variant="subtitle1" sx={{ fontWeight: 500 }}>
                            {request.username}
                          </Typography>
                          <Chip
                            label={request.status === 'pending' ? 'Pending' : 'Resolved'}
                            color={request.status === 'pending' ? 'warning' : 'success'}
                            size="small"
                          />
                          <Chip
                            label={request.email}
                            size="small"
                            variant="outlined"
                          />
                        </Box>
                      }
                      secondary={
                        <Stack spacing={0.5} sx={{ mt: 1 }}>
                          {request.note && (
                            <Typography variant="body2" color="text.secondary">
                              Note: {request.note}
                            </Typography>
                          )}
                          {request.client_ip && (
                            <Typography variant="body2" color="text.secondary">
                              IP: {request.client_ip}
                            </Typography>
                          )}
                          <Typography variant="body2" color="text.secondary">
                            Requested: {formatDateTime(request.requested_at)}
                          </Typography>
                          {request.resolved_at && (
                            <Typography variant="body2" color="text.secondary">
                              Resolved: {formatDateTime(request.resolved_at)} by {request.resolved_by || '—'}
                            </Typography>
                          )}
                          {request.resolution_note && (
                            <Typography variant="body2" color="text.secondary">
                              Resolution note: {request.resolution_note}
                            </Typography>
                          )}
                        </Stack>
                      }
                    />
                    <ListItemSecondaryAction>
                      <Stack direction="column" spacing={1}>
                        {request.status === 'pending' && (
                          <>
                            <Button
                              variant="contained"
                              size="small"
                              onClick={() => openResetDialog(request)}
                            >
                              Reset Password
                            </Button>
                            <Button
                              variant="text"
                              size="small"
                              onClick={() =>
                                setConfirmDialog({
                                  open: true,
                                  title: 'Resolve password reset request',
                                  message: `Mark the request from "${request.username}" as resolved?`,
                                  action: () => {
                                    void handleResolveRequest(request.id);
                                    setConfirmDialog(prev => ({ ...prev, open: false }));
                                  },
                                })
                              }
                            >
                              Mark Resolved
                            </Button>
                          </>
                        )}
                        {request.status !== 'pending' && (
                          <Chip label="Completed" color="success" size="small" />
                        )}
                      </Stack>
                    </ListItemSecondaryAction>
                  </ListItem>
                  {index < resetRequests.length - 1 && <Divider />}
                </React.Fragment>
              ))}
            </List>
          )}
        </CardContent>
      </Card>

      {/* Security Information */}
      <Card sx={{ mt: 2 }}>
        <CardContent>
          <Box sx={{ display: 'flex', alignItems: 'center', mb: 2 }}>
            <SecurityIcon sx={{ mr: 1 }} />
            <Typography variant="subtitle1" sx={{ fontWeight: 600 }}>
              Security Information
            </Typography>
          </Box>
          
          <Alert severity="info" sx={{ mb: 2 }}>
            <Typography variant="body2">
              <strong>Security Notes:</strong>
            </Typography>
            <Typography variant="body2" component="div">
              • The main admin account cannot be deactivated for security reasons<br/>
              • User management follows principle of least privilege<br/>
              • All administrative actions are logged for audit purposes<br/>
              • Future updates will include role-based permissions and session management
            </Typography>
          </Alert>

          <Box sx={{ display: 'flex', gap: 2, flexWrap: 'wrap' }}>
            <Chip 
              icon={<AdminIcon />}
              label={`${users.filter(u => u.role === 'admin').length} Admin(s)`}
              color="primary"
              variant="outlined"
            />
            <Chip 
              icon={<PersonIcon />}
              label={`${users.filter(u => u.role === 'user').length} User(s)`}
              color="default"
              variant="outlined"
            />
            <Chip 
              label={`${users.filter(u => u.is_active).length} Active`}
              color="success"
              variant="outlined"
            />
            <Chip 
              label={`${users.filter(u => !u.is_active).length} Inactive`}
              color="default"
              variant="outlined"
            />
          </Box>
        </CardContent>
      </Card>

      {/* Confirmation Dialog */}
      <Dialog
        open={confirmDialog.open}
        onClose={() => setConfirmDialog(prev => ({ ...prev, open: false }))}
        maxWidth="sm"
        fullWidth
      >
        <DialogTitle>{confirmDialog.title}</DialogTitle>
        <DialogContent>
          <Typography>{confirmDialog.message}</Typography>
        </DialogContent>
        <DialogActions>
          <Button 
            onClick={() => setConfirmDialog(prev => ({ ...prev, open: false }))}
          >
            Cancel
          </Button>
          <Button 
            onClick={confirmDialog.action}
            variant="contained"
            color="primary"
          >
            Confirm
          </Button>
        </DialogActions>
      </Dialog>

      <Dialog
        open={Boolean(activeRequest)}
        onClose={dialogSubmitting ? undefined : closeResetDialog}
        maxWidth="sm"
        fullWidth
      >
        <DialogTitle>Reset password for {activeRequest?.username}</DialogTitle>
        <DialogContent dividers>
          <Stack spacing={2}>
            <Typography variant="body2" color="text.secondary">
              Enter a temporary password to share with the user. They will be required to set a new password on next login.
            </Typography>
            <TextField
              label="Temporary password"
              value={tempPassword}
              onChange={(event) => setTempPassword(event.target.value)}
              type="text"
              required
              autoFocus
            />
            <TextField
              label="Resolution note (optional)"
              value={resolutionNote}
              onChange={(event) => setResolutionNote(event.target.value)}
              multiline
              minRows={2}
              placeholder="Example: Reset to temporary lab password over phone"
            />
            {dialogError && (
              <Alert severity="error" onClose={() => setDialogError('')}>
                {dialogError}
              </Alert>
            )}
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={closeResetDialog} disabled={dialogSubmitting}>
            Cancel
          </Button>
          <Button
            variant="contained"
            onClick={submitResetDialog}
            disabled={dialogSubmitting}
          >
            {dialogSubmitting ? 'Saving…' : 'Reset & Resolve'}
          </Button>
        </DialogActions>
      </Dialog>
    </Box>
  );
}
