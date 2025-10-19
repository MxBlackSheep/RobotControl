import React, { useMemo, useState } from 'react';
import {
  Box,
  Button,
  Card,
  CardContent,
  CardHeader,
  Chip,
  CircularProgress,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  FormControlLabel,
  IconButton,
  Stack,
  Switch,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableRow,
  TextField,
  Tooltip,
  Typography,
} from '@mui/material';
import {
  Add as AddIcon,
  Delete as DeleteIcon,
  Edit as EditIcon,
  Refresh as RefreshIcon,
} from '@mui/icons-material';
import { NotificationContact, NotificationContactPayload } from '../../types/scheduling';
import StatusDialog, { StatusSeverity } from '../StatusDialog';

interface NotificationContactsPanelProps {
  contacts: NotificationContact[];
  onRefresh: (includeInactive: boolean) => Promise<{ contacts?: NotificationContact[]; error?: string }>;
  onCreate: (payload: NotificationContactPayload) => Promise<{ contact?: NotificationContact; error?: string }>;
  onUpdate: (
    contactId: string,
    payload: NotificationContactPayload,
  ) => Promise<{ contact?: NotificationContact; error?: string }>;
  onDelete: (contactId: string) => Promise<{ success: boolean; error?: string }>;
}

const defaultForm: NotificationContactPayload = {
  display_name: '',
  email_address: '',
  is_active: true,
};

const emailRegex = /^[^@\s]+@[^@\s]+\.[^@\s]+$/;

const NotificationContactsPanel: React.FC<NotificationContactsPanelProps> = ({
  contacts,
  onRefresh,
  onCreate,
  onUpdate,
  onDelete,
}) => {
  const [includeInactive, setIncludeInactive] = useState(false);
  const [refreshing, setRefreshing] = useState(false);

  const [dialogOpen, setDialogOpen] = useState(false);
  const [editingContact, setEditingContact] = useState<NotificationContact | null>(null);
  const [formData, setFormData] = useState<NotificationContactPayload>(defaultForm);
  const [saving, setSaving] = useState(false);
  const [statusDialog, setStatusDialog] = useState<{
    open: boolean;
    title: string;
    message: string;
    severity: StatusSeverity;
    autoCloseMs?: number;
  }>({ open: false, title: '', message: '', severity: 'info' });

  const showStatusDialog = ({
    title = '',
    message,
    severity = 'info',
    autoCloseMs,
  }: {
    title?: string;
    message: string;
    severity?: StatusSeverity;
    autoCloseMs?: number;
  }) => {
    setStatusDialog({ open: true, title, message, severity, autoCloseMs });
  };

  const closeStatusDialog = () => {
    setStatusDialog(prev => ({ ...prev, open: false }));
  };

  const sortedContacts = useMemo(
    () =>
      [...contacts].sort((a, b) => {
        if (a.is_active !== b.is_active) {
          return a.is_active ? -1 : 1;
        }
        return a.display_name.localeCompare(b.display_name);
      }),
    [contacts],
  );

  const resetDialog = () => {
    setDialogOpen(false);
    setEditingContact(null);
    setFormData(defaultForm);
    setSaving(false);
  };

  const handleRefresh = async (
    inactive: boolean,
    options: { silentSuccess?: boolean; silentError?: boolean } = {}
  ) => {
    setRefreshing(true);
    const result = await onRefresh(inactive);
    setRefreshing(false);

    if (result.error) {
      if (!options.silentError) {
        showStatusDialog({
          title: 'Refresh Failed',
          message: result.error,
          severity: 'error',
        });
      }
      return false;
    }

    if (!options.silentSuccess) {
      showStatusDialog({
        title: 'Contacts Refreshed',
        message: 'Notification contacts updated.',
        severity: 'success',
        autoCloseMs: 4000,
      });
    }

    return true;
  };

  const handleToggleInactive = async (checked: boolean) => {
    setIncludeInactive(checked);
    await handleRefresh(checked);
  };

  const handleOpenCreate = () => {
    setEditingContact(null);
    setFormData(defaultForm);
    setDialogOpen(true);
  };

  const handleOpenEdit = (contact: NotificationContact) => {
    setEditingContact(contact);
    setFormData({
      display_name: contact.display_name,
      email_address: contact.email_address,
      is_active: contact.is_active,
    });
    setDialogOpen(true);
  };

  const validateForm = () => {
    if (!formData.display_name.trim()) {
      return 'Display name is required.';
    }
    if (!formData.email_address.trim()) {
      return 'Email address is required.';
    }
    if (!emailRegex.test(formData.email_address.trim())) {
      return 'Please provide a valid email address.';
    }
    return null;
  };

  const handleSubmit = async () => {
    const validationError = validateForm();
    if (validationError) {
      showStatusDialog({
        title: editingContact ? 'Unable to update contact' : 'Unable to create contact',
        message: validationError,
        severity: 'warning',
      });
      return;
    }

    setSaving(true);
    const payload: NotificationContactPayload = {
      display_name: formData.display_name.trim(),
      email_address: formData.email_address.trim(),
      is_active: formData.is_active,
    };

    const result = editingContact
      ? await onUpdate(editingContact.contact_id, payload)
      : await onCreate(payload);

    setSaving(false);

    if (result.error) {
      showStatusDialog({
        title: editingContact ? 'Update failed' : 'Creation failed',
        message: result.error,
        severity: 'error',
      });
      return;
    }

    const refreshed = await handleRefresh(includeInactive, {
      silentSuccess: true,
      silentError: true,
    });

    const successTitle = editingContact ? 'Contact updated' : 'Contact created';
    const successMessage = editingContact
      ? 'Notification contact updated successfully.'
      : 'Notification contact created successfully.';

    showStatusDialog({
      title: successTitle,
      message: refreshed
        ? successMessage
        : `${successMessage}\n\nUnable to refresh the contact list automatically. Please try refreshing manually.`,
      severity: refreshed ? 'success' : 'warning',
      autoCloseMs: refreshed ? 4000 : undefined,
    });

    resetDialog();
  };

  const handleDelete = async (contact: NotificationContact) => {
    const confirmed = window.confirm(
      `Delete contact "${contact.display_name}"? They will no longer receive scheduling alerts.`,
    );
    if (!confirmed) {
      return;
    }

    const result = await onDelete(contact.contact_id);
    if (result.error) {
      showStatusDialog({
        title: 'Delete failed',
        message: result.error,
        severity: 'error',
      });
      return;
    }

    const refreshed = await handleRefresh(includeInactive, {
      silentSuccess: true,
      silentError: true,
    });

    showStatusDialog({
      title: 'Contact deleted',
      message: refreshed
        ? 'Notification contact deleted successfully.'
        : 'Notification contact deleted. Unable to refresh the list automatically—please refresh manually.',
      severity: refreshed ? 'success' : 'warning',
      autoCloseMs: refreshed ? 4000 : undefined,
    });
  };

  return (
    <>
      <Card sx={{ borderRadius: 2 }}>
        <CardHeader
          title="Notification Contacts"
          subheader="Manage who receives scheduling alert emails."
          action={
            <Stack direction="row" spacing={1} alignItems="center">
              <FormControlLabel
                control={
                  <Switch
                    size="small"
                    checked={includeInactive}
                    onChange={(event) => handleToggleInactive(event.target.checked)}
                  />
                }
                label="Show inactive"
              />
              <Tooltip title="Refresh contacts">
                <span>
                  <IconButton onClick={() => handleRefresh(includeInactive)} disabled={refreshing}>
                    {refreshing ? <CircularProgress size={20} /> : <RefreshIcon fontSize="small" />}
                  </IconButton>
                </span>
              </Tooltip>
            </Stack>
          }
        />
        <CardContent sx={{ pt: 0 }}>
          <Stack spacing={2.5}>
            <Box display="flex" justifyContent="flex-end">
              <Button variant="contained" startIcon={<AddIcon />} onClick={handleOpenCreate}>
                Add Contact
              </Button>
            </Box>

            {sortedContacts.length === 0 ? (
              <Box
                sx={{
                  border: 1,
                  borderColor: 'divider',
                  borderRadius: 2,
                  p: 3,
                  textAlign: 'center',
                }}
              >
                <Typography variant="body2" color="text.secondary">
                  No contacts available. Add a contact to begin receiving scheduling notifications.
                </Typography>
              </Box>
            ) : (
              <Table size="small">
                <TableHead>
                  <TableRow>
                    <TableCell>Name</TableCell>
                    <TableCell>Email</TableCell>
                    <TableCell>Status</TableCell>
                    <TableCell align="right">Actions</TableCell>
                  </TableRow>
                </TableHead>
                <TableBody>
                  {sortedContacts.map((contact) => (
                    <TableRow key={contact.contact_id} hover>
                      <TableCell>
                        <Typography variant="body2">{contact.display_name}</Typography>
                      </TableCell>
                      <TableCell>
                        <Typography variant="body2" color="text.secondary">
                          {contact.email_address}
                        </Typography>
                      </TableCell>
                      <TableCell>
                        <Chip
                          label={contact.is_active ? 'Active' : 'Inactive'}
                          color={contact.is_active ? 'success' : 'default'}
                          size="small"
                        />
                      </TableCell>
                      <TableCell align="right">
                        <Stack direction="row" spacing={0.75} justifyContent="flex-end">
                          <Tooltip title="Edit contact">
                            <IconButton size="small" onClick={() => handleOpenEdit(contact)}>
                              <EditIcon fontSize="small" />
                            </IconButton>
                          </Tooltip>
                          <Tooltip title="Delete contact">
                            <IconButton size="small" onClick={() => handleDelete(contact)}>
                              <DeleteIcon fontSize="small" />
                            </IconButton>
                          </Tooltip>
                        </Stack>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            )}
          </Stack>
        </CardContent>

      <Dialog open={dialogOpen} onClose={resetDialog} fullWidth maxWidth="sm">
        <DialogTitle>{editingContact ? 'Edit Contact' : 'Add Contact'}</DialogTitle>
        <DialogContent dividers>
          <Stack spacing={2.5} sx={{ pt: 1 }}>
            <TextField
              label="Display Name"
              value={formData.display_name}
              onChange={(event) => setFormData((prev) => ({ ...prev, display_name: event.target.value }))}
              fullWidth
              autoFocus
            />
            <TextField
              label="Email Address"
              value={formData.email_address}
              onChange={(event) => setFormData((prev) => ({ ...prev, email_address: event.target.value }))}
              type="email"
              fullWidth
            />
            <FormControlLabel
              control={
                <Switch
                  checked={Boolean(formData.is_active)}
                  onChange={(event) => setFormData((prev) => ({ ...prev, is_active: event.target.checked }))}
                />
              }
              label="Active"
            />
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={resetDialog} disabled={saving}>
            Cancel
          </Button>
          <Button
            onClick={handleSubmit}
            variant="contained"
            startIcon={
              saving ? <CircularProgress size={18} /> : editingContact ? <EditIcon /> : <AddIcon />
            }
            disabled={saving}
          >
            {editingContact ? 'Save Changes' : 'Create Contact'}
          </Button>
        </DialogActions>
      </Dialog>
      </Card>
      <StatusDialog
        open={statusDialog.open}
        onClose={closeStatusDialog}
        title={statusDialog.title}
        message={statusDialog.message}
        severity={statusDialog.severity}
        autoCloseMs={statusDialog.autoCloseMs}
      />
    </>
  );
};

export default NotificationContactsPanel;
