import React, { useEffect, useRef, useState } from 'react';
import {
  Accordion, AccordionDetails, AccordionSummary, Alert, Autocomplete, Button,
  Card, CardContent, CardHeader, Chip, CircularProgress, Dialog, DialogActions,
  DialogContent, DialogTitle, Divider, FormControlLabel, MenuItem, Stack, Switch,
  TextField, Typography,
} from '@mui/material';
import { ExpandMore, Refresh, Save, Send } from '@mui/icons-material';
import { NotificationContact, NotificationSettings, NotificationSettingsUpdatePayload } from '../../types/scheduling';
import { smtpDraft, smtpPayload, SmtpDraft, uniqueEmails, validEmail } from './smtpForm';

interface Props {
  settings: NotificationSettings | null;
  loading: boolean;
  onRefresh: () => Promise<{ settings?: NotificationSettings | null; error?: string }>;
  onSave: (payload: NotificationSettingsUpdatePayload) => Promise<{ settings?: NotificationSettings; error?: string }>;
  onSendTest: (recipient: string) => Promise<{ success: boolean; recipient?: string; warning?: string; error?: string }>;
  contacts: NotificationContact[];
}

type Feedback = { severity: 'success' | 'error' | 'info' | 'warning'; message: string } | null;
const messageOf = (error: unknown) => error instanceof Error ? error.message : 'The request failed. Please try again.';

export default function NotificationEmailSettingsPanel({ settings, loading, onRefresh, onSave, onSendTest, contacts }: Props) {
  const [saved, setSaved] = useState(settings);
  const [draft, setDraft] = useState(() => smtpDraft(settings));
  const [advanced, setAdvanced] = useState(() => smtpDraft(settings).customLogin || smtpDraft(settings).customSender);
  const [busy, setBusy] = useState<'save' | 'refresh' | 'test' | null>(null);
  const [feedback, setFeedback] = useState<Feedback>(null);
  const [testFeedback, setTestFeedback] = useState<Feedback>(null);
  const [testRecipient, setTestRecipient] = useState(settings?.sender || '');
  const [confirmDiscard, setConfirmDiscard] = useState(false);
  const initialized = useRef(Boolean(settings));
  const payload = smtpPayload(draft, saved);
  const dirty = JSON.stringify(payload) !== JSON.stringify(smtpPayload(smtpDraft(saved), saved));
  const disabled = loading || busy !== null;

  const adopt = (latest: NotificationSettings | null) => {
    const next = smtpDraft(latest);
    setSaved(latest);
    setDraft(next);
    setAdvanced(next.customLogin || next.customSender);
    setTestRecipient(previous => previous || latest?.sender || '');
    initialized.current = true;
    setTestFeedback(null);
  };

  useEffect(() => {
    if (settings && !initialized.current) adopt(settings);
  }, [settings]);

  const change = <K extends keyof SmtpDraft>(key: K, value: SmtpDraft[K]) => {
    initialized.current = true;
    setDraft(previous => ({ ...previous, [key]: value }));
    setFeedback(null);
    setTestFeedback(null);
  };

  const refresh = async () => {
    setConfirmDiscard(false);
    setBusy('refresh');
    setFeedback(null);
    try {
      const result = await onRefresh();
      if (result.error) throw new Error(result.error);
      if (result.settings === undefined) throw new Error('No settings were returned. Your entries have been kept.');
      adopt(result.settings);
      setFeedback({ severity: 'success', message: 'Saved email settings loaded.' });
    } catch (error) {
      setFeedback({ severity: 'error', message: messageOf(error) });
    } finally { setBusy(null); }
  };

  const save = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!dirty || disabled) return;
    if (!validEmail(draft.account) || !validEmail(payload.sender) || !payload.host ||
        !Number.isInteger(payload.port) || payload.port < 1 || payload.port > 65535 ||
        payload.manual_recovery_recipients.some(email => !validEmail(email))) {
      setFeedback({ severity: 'error', message: 'Enter a valid account and From address, outgoing server, whole-number port (1–65535), and recovery recipient addresses.' });
      return;
    }
    setBusy('save');
    setFeedback(null);
    try {
      const result = await onSave(payload);
      if (result.error) throw new Error(result.error);
      // Only a confirmed saved snapshot unlocks testing.
      if (!result.settings) throw new Error('The saved settings could not be confirmed. Refresh before sending a test email.');
      adopt(result.settings);
      setFeedback({ severity: 'success', message: 'Email settings saved. You can now send a test email.' });
    } catch (error) {
      setFeedback({ severity: 'error', message: messageOf(error) });
    } finally { setBusy(null); }
  };

  const sendTest = async () => {
    if (dirty || disabled || !saved || !validEmail(testRecipient)) return;
    setBusy('test');
    setTestFeedback(null);
    try {
      const result = await onSendTest(testRecipient.trim());
      if (!result.success || result.error) throw new Error(result.error || 'The test email could not be sent.');
      setTestFeedback({ severity: result.warning ? 'warning' : 'success', message: result.warning || `Test email sent to ${result.recipient || testRecipient.trim()}.` });
    } catch (error) {
      setTestFeedback({ severity: 'error', message: messageOf(error) });
    } finally { setBusy(null); }
  };

  const recoveryOptions = uniqueEmails([...contacts.map(contact => contact.email_address), ...draft.recipients]);
  const passwordHelp = draft.passwordAction === 'clear'
    ? 'The stored password will be removed when you save.'
    : saved?.has_password
      ? 'A password is stored securely. Leave this blank to keep it.'
      : 'Use the SMTP or app password supplied by your email provider.';

  return (
    <Card sx={{ borderRadius: 2, width: '100%', maxWidth: 1000, mx: 'auto' }}>
      <CardHeader title="Email delivery settings" subheader="Choose the account RobotControl uses to send scheduling alerts."
        action={<Button startIcon={<Refresh />} disabled={disabled} onClick={() => dirty ? setConfirmDiscard(true) : void refresh()}>Refresh</Button>} />
      <Divider />
      <CardContent>
        <Stack component="form" spacing={3} onSubmit={save} autoComplete="off">
          <Stack direction="row" alignItems="center" spacing={1}>
            <Typography variant="h6">Sending account</Typography>
            {dirty && <Chip size="small" color="warning" label="Unsaved changes" />}
          </Stack>
          <Typography color="text.secondary" variant="body2">This account sends emails. Choose who receives alerts in each schedule's Email alert recipients field.</Typography>
          <TextField label="Email account address" name="smtp-account-address" type="email" required fullWidth
            value={draft.account} onChange={event => change('account', event.target.value)} disabled={disabled}
            placeholder="robot-alerts@example.com" helperText="Used for both mail-server login and the From address unless overridden below." />
          <Stack spacing={1}>
            <TextField label="App password / SMTP password" name="smtp-account-password" type="password" autoComplete="new-password" fullWidth
              value={draft.password} disabled={disabled} helperText={passwordHelp}
              onChange={event => { change('password', event.target.value); change('passwordAction', event.target.value ? 'update' : 'keep'); }} />
            <Stack direction="row" spacing={1}>
              <Button size="small" disabled={disabled || !saved?.has_password || draft.passwordAction === 'clear'}
                onClick={() => { change('password', ''); change('passwordAction', 'clear'); }}>Remove stored password on save</Button>
              {draft.passwordAction !== 'keep' && <Button size="small" disabled={disabled}
                onClick={() => { change('password', ''); change('passwordAction', 'keep'); }}>Undo password change</Button>}
            </Stack>
          </Stack>
          <Divider />
          <Typography variant="h6">Mail server</Typography>
          <Stack direction={{ xs: 'column', md: 'row' }} spacing={2}>
            <TextField label="Outgoing mail server (SMTP)" name="smtp-outgoing-server" required fullWidth disabled={disabled}
              value={draft.host} onChange={event => change('host', event.target.value)} placeholder="smtp.example.com"
              helperText="Use your provider's outgoing SMTP server, not its incoming IMAP server." />
            <TextField label="Port" required type="number" disabled={disabled} sx={{ minWidth: 140 }}
              value={draft.port} onChange={event => change('port', event.target.value)} inputProps={{ min: 1, max: 65535, step: 1 }} />
          </Stack>
          <TextField select label="Connection security" fullWidth disabled={disabled} value={draft.security}
            onChange={event => change('security', event.target.value as SmtpDraft['security'])}
            helperText="SSL/TLS commonly uses port 465; STARTTLS commonly uses 587. Changing security does not change the port.">
            <MenuItem value="ssl">SSL/TLS</MenuItem><MenuItem value="starttls">STARTTLS</MenuItem><MenuItem value="none">None</MenuItem>
          </TextField>
          <Accordion expanded={advanced} onChange={(_, expanded) => setAdvanced(expanded)} disableGutters variant="outlined">
            <AccordionSummary expandIcon={<ExpandMore />}><Typography>Advanced settings</Typography></AccordionSummary>
            <AccordionDetails><Stack spacing={2}>
              <FormControlLabel label="Different login username" control={<Switch disabled={disabled} checked={draft.customLogin}
                onChange={(_, checked) => { if (checked && !draft.login) change('login', draft.account); change('customLogin', checked); }} />} />
              {draft.customLogin && <TextField label="Mail-server login username" name="smtp-login-override" value={draft.login} disabled={disabled}
                onChange={event => change('login', event.target.value)} helperText="This is your email provider's login, not your RobotControl username. Blank uses the From address." />}
              <FormControlLabel label="Different From address" control={<Switch disabled={disabled} checked={draft.customSender}
                onChange={(_, checked) => { if (checked && !draft.sender) change('sender', draft.account); change('customSender', checked); }} />} />
              {draft.customSender && <TextField label="From email address" type="email" required disabled={disabled} value={draft.sender}
                onChange={event => change('sender', event.target.value)} helperText="The address recipients see as the sender. Your mail provider must allow it." />}
              <Divider />
              <Typography variant="subtitle1">Manual-recovery notifications</Typography>
              <Autocomplete multiple freeSolo options={recoveryOptions} value={draft.recipients} disabled={disabled}
                onChange={(_, values) => change('recipients', uniqueEmails(values))}
                renderOption={(optionProps, email) => <li {...optionProps}>{contacts.find(contact => contact.email_address === email)?.display_name || 'Custom recipient'} — {email}</li>}
                renderInput={params => <TextField {...params} label="Manual-recovery recipients"
                  helperText="Only for manual recovery. Leave empty to use the schedule's selected active contacts." />} />
            </Stack></AccordionDetails>
          </Accordion>
          {feedback && <Alert severity={feedback.severity} sx={{ whiteSpace: 'pre-line' }}>{feedback.message}</Alert>}
          <Stack direction="row" spacing={1} justifyContent="flex-end" flexWrap="wrap">
            <Button disabled={disabled || !dirty} onClick={() => setConfirmDiscard(true)}>Discard changes</Button>
            <Button variant="contained" type="submit" disabled={disabled || !dirty} startIcon={busy === 'save' ? <CircularProgress size={18} /> : <Save />}>Save settings</Button>
          </Stack>
          {saved?.updated_at && <Typography variant="caption" color="text.secondary">Last saved {new Date(saved.updated_at).toLocaleString()}{saved.updated_by && ` by ${saved.updated_by}`}</Typography>}
        </Stack>
        <Divider sx={{ my: 3 }} />
        <Stack spacing={2}>
          <Typography variant="h6">Test email</Typography>
          <Typography variant="body2" color="text.secondary">Send one email using the saved settings. Saving settings does not send a message.</Typography>
          {dirty && <Alert severity="info">Save your changes before sending a test email.</Alert>}
          <Stack direction={{ xs: 'column', md: 'row' }} spacing={2}>
            <TextField label="Send test to" type="email" fullWidth value={testRecipient} disabled={disabled}
              onChange={event => setTestRecipient(event.target.value)} />
            <Button variant="outlined" sx={{ minWidth: 180 }} disabled={disabled || dirty || !saved?.host || !validEmail(testRecipient)}
              onClick={sendTest} startIcon={busy === 'test' ? <CircularProgress size={18} /> : <Send />}>
              {busy === 'test' ? 'Sending…' : 'Send test email'}
            </Button>
          </Stack>
          {testFeedback && <Alert severity={testFeedback.severity} sx={{ whiteSpace: 'pre-line' }}>{testFeedback.message}</Alert>}
        </Stack>
      </CardContent>
      <Dialog open={confirmDiscard} onClose={() => setConfirmDiscard(false)} aria-labelledby="discard-email-title">
        <DialogTitle id="discard-email-title">Discard unsaved email settings?</DialogTitle>
        <DialogContent>Your entries will be replaced with the saved settings. If loading fails, your entries will be kept.</DialogContent>
        <DialogActions><Button autoFocus onClick={() => setConfirmDiscard(false)}>Keep editing</Button><Button onClick={refresh}>Discard and reload</Button></DialogActions>
      </Dialog>
    </Card>
  );
}
