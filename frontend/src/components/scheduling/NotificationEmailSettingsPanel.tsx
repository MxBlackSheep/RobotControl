import React, { useEffect, useMemo, useState } from 'react';
import Autocomplete from '@mui/material/Autocomplete';
import {
  Box,
  Button,
  Card,
  CardContent,
  CardHeader,
  CircularProgress,
  Divider,
  FormControlLabel,
  Stack,
  Switch,
  TextField,
  Typography,
} from '@mui/material';
import { Refresh as RefreshIcon, Save as SaveIcon, LockReset as LockResetIcon, Send as SendIcon } from '@mui/icons-material';
import StatusDialog, { StatusSeverity } from '../StatusDialog';
import { NotificationContact, NotificationSettings, NotificationSettingsUpdatePayload } from '../../types/scheduling';

interface ManualRecipientOption {
  value: string;
  label: string;
  isInactive?: boolean;
  isCustom?: boolean;
}

interface NotificationEmailSettingsPanelProps {
  settings: NotificationSettings | null;
  loading: boolean;
  onRefresh: () => Promise<{ settings?: NotificationSettings | null; error?: string }>;
  onSave: (
    payload: NotificationSettingsUpdatePayload,
  ) => Promise<{ settings?: NotificationSettings; error?: string }>;
  onSendTest: (recipient: string) => Promise<{ success: boolean; recipient?: string; error?: string }>;
  contacts: NotificationContact[];
}

type PasswordAction = 'keep' | 'update' | 'clear';

const emailRegex = /^[^@\s]+@[^@\s]+\.[^@\s]+$/;

const uniqueEmailList = (values: string[]): string[] => {
  const seen = new Set<string>();
  const results: string[] = [];
  for (const raw of values) {
    const trimmed = raw.trim();
    if (!trimmed) {
      continue;
    }
    const key = trimmed.toLowerCase();
    if (seen.has(key)) {
      continue;
    }
    seen.add(key);
    results.push(trimmed);
  }
  return results;
};

const NotificationEmailSettingsPanel: React.FC<NotificationEmailSettingsPanelProps> = ({
  settings,
  loading,
  onRefresh,
  onSave,
  onSendTest,
  contacts,
}) => {
  const [formHost, setFormHost] = useState('');
  const [formPort, setFormPort] = useState('587');
  const [formUsername, setFormUsername] = useState('');
  const [formSender, setFormSender] = useState('');
  const [formUseTls, setFormUseTls] = useState(true);
  const [formUseSsl, setFormUseSsl] = useState(false);
  const [formPassword, setFormPassword] = useState('');
  const [formManualRecipients, setFormManualRecipients] = useState<string[]>([]);
  const [passwordAction, setPasswordAction] = useState<PasswordAction>('keep');
  const [testRecipient, setTestRecipient] = useState('');
  const [testingEmail, setTestingEmail] = useState(false);

  const [statusDialog, setStatusDialog] = useState<{
    open: boolean;
    title: string;
    message: string;
    severity: StatusSeverity;
    autoCloseMs?: number;
  }>({ open: false, title: '', message: '', severity: 'info' });
  const [saving, setSaving] = useState(false);
  const hasStoredPassword = Boolean(settings?.has_password);

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

  useEffect(() => {
    if (!settings) {
      return;
    }
    setFormHost(settings.host || '');
    setFormPort((settings.port ?? 587).toString());
    setFormUsername(settings.username || '');
    setFormSender(settings.sender || '');
    setFormUseTls(settings.use_tls ?? true);
    setFormUseSsl(settings.use_ssl ?? false);
    setFormPassword('');
    setPasswordAction('keep');
    setTestRecipient(settings.sender || '');
    setFormManualRecipients(uniqueEmailList(settings.manual_recovery_recipients ?? []));
  }, [settings]);

  const manualRecipientOptions = useMemo<ManualRecipientOption[]>(() => {
    const options: ManualRecipientOption[] = contacts.map((contact) => ({
      value: contact.email_address,
      label: `${contact.display_name} — ${contact.email_address}`,
      isInactive: !contact.is_active,
    }));

    const knownEmails = new Set(options.map((option) => option.value.toLowerCase()));

    const customOptions: ManualRecipientOption[] = formManualRecipients
      .filter((email) => !knownEmails.has(email.toLowerCase()))
      .map((email) => ({
        value: email,
        label: `${email} (custom)`,
        isCustom: true,
      }));

    return [...options, ...customOptions];
  }, [contacts, formManualRecipients]);

  const selectedManualRecipientOptions = useMemo(() => {
    const optionMap = new Map<string, ManualRecipientOption>(
      manualRecipientOptions.map((option) => [option.value.toLowerCase(), option]),
    );
    return formManualRecipients
      .map((email) => optionMap.get(email.toLowerCase()))
      .filter((option): option is ManualRecipientOption => Boolean(option));
  }, [manualRecipientOptions, formManualRecipients]);

  const passwordHelperText = useMemo(() => {
    if (passwordAction === 'update') {
      return 'Enter a new SMTP password. This value will be encrypted before saving.';
    }
    if (passwordAction === 'clear') {
      return 'The stored SMTP password will be cleared on save.';
    }
    if (hasStoredPassword) {
      return 'A password is stored securely. Leave blank to keep it, or enter a new value to rotate.';
    }
    return 'No SMTP password is currently stored. Provide an app password if authentication is required.';
  }, [passwordAction, hasStoredPassword]);

  const handleRefresh = async () => {
    const result = await onRefresh();
    if (result.error) {
      showStatusDialog({
        title: 'Refresh Failed',
        message: result.error,
        severity: 'error',
      });
      return;
    }
    showStatusDialog({
      title: 'Settings Updated',
      message: 'Latest SMTP settings loaded.',
      severity: 'success',
      autoCloseMs: 4000,
    });
  };

  const handleSendTestEmail = async () => {
    const recipient = testRecipient.trim();
    if (!emailRegex.test(recipient)) {
      showStatusDialog({
        title: 'Invalid Recipient',
        message: 'Enter a valid test recipient email address.',
        severity: 'warning',
      });
      return;
    }
    setTestingEmail(true);
    try {
      const result = await onSendTest(recipient);
      if (!result.success || result.error) {
        showStatusDialog({
          title: 'Test Email Failed',
          message: result.error || 'Failed to send test email.',
          severity: 'error',
        });
        return;
      }
      const reportedRecipient = result.recipient || recipient;
      showStatusDialog({
        title: 'Test Email Sent',
        message: `Test email sent to ${reportedRecipient}.`,
        severity: 'success',
        autoCloseMs: 5000,
      });
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Failed to send test email.';
      showStatusDialog({
        title: 'Test Email Failed',
        message,
        severity: 'error',
      });
    } finally {
      setTestingEmail(false);
    }
  };

  const validate = (): boolean => {
    const host = formHost.trim();
    const issues: string[] = [];

    if (!host) {
      issues.push('SMTP host is required.');
    }
    const portNum = Number(formPort);
    if (!Number.isFinite(portNum) || portNum < 1 || portNum > 65535) {
      issues.push('SMTP port must be a number between 1 and 65535.');
    }
    const sender = formSender.trim();
    if (!emailRegex.test(sender)) {
      issues.push('Sender must be a valid email address.');
    }
    if (passwordAction === 'update' && !formPassword) {
      issues.push('Enter a password or switch to "clear password" to remove it.');
    }

    if (issues.length > 0) {
      showStatusDialog({
        title: 'Update Incomplete',
        message: issues.join('\n'),
        severity: 'warning',
      });
      return false;
    }

    return true;
  };

  const handleSubmit = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();

    if (!validate()) {
      return;
    }

    const payload: NotificationSettingsUpdatePayload = {
      host: formHost.trim(),
      port: Number(formPort),
      sender: formSender.trim(),
      username: formUsername.trim() ? formUsername.trim() : null,
      use_tls: formUseTls,
      use_ssl: formUseSsl,
      manual_recovery_recipients: [],
    };

    if (passwordAction === 'update') {
      payload.password = formPassword;
    } else if (passwordAction === 'clear') {
      payload.password = '';
    }

    const manualRecipients = uniqueEmailList(formManualRecipients);
    const invalidRecipient = manualRecipients.find((recipient) => !emailRegex.test(recipient));

    if (invalidRecipient) {
      showStatusDialog({
        title: 'Invalid Recipient',
        message: `Invalid manual recovery recipient address: ${invalidRecipient}`,
        severity: 'warning',
      });
      return;
    }

    payload.manual_recovery_recipients = manualRecipients;

    setSaving(true);
    const result = await onSave(payload);
    setSaving(false);

    if (result.error) {
      showStatusDialog({
        title: 'Save Failed',
        message: result.error,
        severity: 'error',
      });
      return;
    }

    showStatusDialog({
      title: 'Settings Saved',
      message: 'SMTP settings updated successfully.',
      severity: 'success',
      autoCloseMs: 5000,
    });
    setFormPassword('');
    setPasswordAction('keep');
  };

  const toggleTls = (checked: boolean) => {
    setFormUseTls(checked);
    if (checked) {
      setFormUseSsl(false);
    }
  };

  const toggleSsl = (checked: boolean) => {
    setFormUseSsl(checked);
    if (checked) {
      setFormUseTls(false);
    }
  };

  const handleClearPassword = () => {
    setFormPassword('');
    setPasswordAction('clear');
  };

  const handlePasswordChange = (value: string) => {
    setFormPassword(value);
    setPasswordAction(value ? 'update' : 'keep');
  };

  const handleManualRecipientsChange = (_event: React.SyntheticEvent, value: ManualRecipientOption[]) => {
    const unique = uniqueEmailList(value.map((option) => option.value));
    setFormManualRecipients(unique);
  };

  return (
    <>
      <Card sx={{ borderRadius: 2 }}>
      <CardHeader
        title="SMTP / Email Settings"
        subheader="Configure the global sender used for scheduling notifications"
        action={
          <Button
            variant="outlined"
            size="small"
            startIcon={loading ? <CircularProgress size={18} /> : <RefreshIcon />}
            onClick={handleRefresh}
            disabled={loading}
          >
            Refresh
          </Button>
        }
      />
      <Divider />
      <CardContent>
        <Stack component="form" spacing={3} onSubmit={handleSubmit}>
          <Stack direction={{ xs: 'column', md: 'row' }} spacing={2.5}>
            <TextField
              label="SMTP Host"
              value={formHost}
              onChange={(event) => setFormHost(event.target.value)}
              fullWidth
              required
              placeholder="smtp.gmail.com"
            />
            <TextField
              label="Port"
              value={formPort}
              onChange={(event) => setFormPort(event.target.value)}
              type="number"
              inputProps={{ min: 1, max: 65535 }}
              sx={{ width: { xs: '100%', md: 160 } }}
              required
            />
          </Stack>

          <Stack direction={{ xs: 'column', md: 'row' }} spacing={2.5}>
            <TextField
              label="SMTP Username"
              value={formUsername}
              onChange={(event) => setFormUsername(event.target.value)}
              fullWidth
              placeholder="mxlittleblacksheep@gmail.com"
            />
            <TextField
              label="Sender Email"
              value={formSender}
              onChange={(event) => setFormSender(event.target.value)}
              type="email"
              fullWidth
              required
              placeholder="alerts@example.com"
            />
          </Stack>

          <Stack direction={{ xs: 'column', md: 'row' }} spacing={3}>
            <FormControlLabel
              control={<Switch checked={formUseTls} onChange={(event) => toggleTls(event.target.checked)} />}
              label="Use STARTTLS"
            />
            <FormControlLabel
              control={<Switch checked={formUseSsl} onChange={(event) => toggleSsl(event.target.checked)} />}
              label="Use SSL"
            />
            <Box sx={{ flexGrow: 1 }}>
              <Typography variant="body2" color="text.secondary">
                STARTTLS upgrades a plain connection; SSL dials a secure port (e.g., 465). Only one should be enabled.
              </Typography>
            </Box>
          </Stack>

          <Stack spacing={1.5}>
            <TextField
              label="SMTP Password"
              value={formPassword}
              onChange={(event) => handlePasswordChange(event.target.value)}
              type="password"
              fullWidth
              placeholder={hasStoredPassword ? '********' : 'App password'}
              helperText={passwordHelperText}
            />
            <Stack direction="row" spacing={1}>
              <Button
                variant="outlined"
                size="small"
                startIcon={<LockResetIcon />}
                onClick={handleClearPassword}
                disabled={passwordAction === 'clear' && !hasStoredPassword}
              >
                Clear Stored Password
          </Button>
        </Stack>
      </Stack>

      <Divider />


          <Stack spacing={1.5}>
            <Autocomplete
              multiple
              options={manualRecipientOptions}
              value={selectedManualRecipientOptions}
              onChange={handleManualRecipientsChange}
              disableCloseOnSelect
              getOptionLabel={(option) => option.label}
              isOptionEqualToValue={(option, value) => option.value.toLowerCase() === value.value.toLowerCase()}
              renderOption={(props, option) => (
                <li {...props}>
                  <Box sx={{ display: 'flex', flexDirection: 'column' }}>
                    <Typography variant="body2">{option.label}</Typography>
                    {option.isInactive && (
                      <Typography variant="caption" color="text.secondary">
                        Inactive contact
                      </Typography>
                    )}
                    {option.isCustom && (
                      <Typography variant="caption" color="text.secondary">
                        Custom email
                      </Typography>
                    )}
                  </Box>
                </li>
              )}
              renderInput={(params) => (
                <TextField
                  {...params}
                  label="Manual Recovery Recipients"
                  placeholder="Select recipients"
                  helperText="Select contacts to notify during manual recovery. Leave empty to notify schedule owners."
                />
              )}
            />
          </Stack>
      <Stack spacing={1.5}>
        <Typography variant="subtitle2" color="text.secondary">
          Send a test message using the saved SMTP settings to confirm delivery.
        </Typography>
        <Stack direction={{ xs: 'column', md: 'row' }} spacing={2.5}>
          <TextField
            label="Test Recipient Email"
            value={testRecipient}
            onChange={(event) => setTestRecipient(event.target.value)}
            type="email"
            fullWidth
            placeholder="alerts-check@example.com"
          />
          <Button
            variant="contained"
            color="secondary"
            startIcon={testingEmail ? <CircularProgress size={18} /> : <SendIcon />}
            type="button"
            onClick={handleSendTestEmail}
            disabled={testingEmail || !testRecipient.trim()}
            sx={{ width: { xs: '100%', md: 220 } }}
          >
            Send Test Email
          </Button>
        </Stack>
      </Stack>

      {settings?.updated_at && (
        <Typography variant="caption" color="text.secondary">
          Last updated {new Date(settings.updated_at).toLocaleString()}
          {settings.updated_by ? ` by ${settings.updated_by}` : ''}
        </Typography>
          )}

          <Stack direction="row" spacing={1.5} justifyContent="flex-end">
            <Button variant="outlined" onClick={handleRefresh} disabled={loading || saving}>
              Discard Changes
            </Button>
            <Button
              type="submit"
              variant="contained"
              startIcon={saving ? <CircularProgress size={18} /> : <SaveIcon />}
              disabled={saving}
            >
              Save Settings
            </Button>
          </Stack>
        </Stack>
      </CardContent>
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

export default NotificationEmailSettingsPanel;
