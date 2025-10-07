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
  Tooltip
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
import { api } from '../services/api';

interface User {
  username: string;
  role: string;
  is_active: boolean;
  last_login?: string;
  created_at?: string;
}

interface UserManagementProps {
  onError?: (error: string) => void;
}

export default function UserManagement({ onError }: UserManagementProps) {
  const [users, setUsers] = useState<User[]>([]);
  const [loading, setLoading] = useState(false);
  const [selectedUser, setSelectedUser] = useState<User | null>(null);
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

  const loadUsers = async () => {
    try {
      setLoading(true);
      const response = await api.get('/admin/users');
      setUsers(response.data);
    } catch (err: any) {
      const errorMessage = err.response?.data?.detail || 'Failed to load users';
      if (onError) onError(errorMessage);
    } finally {
      setLoading(false);
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
    </Box>
  );
}