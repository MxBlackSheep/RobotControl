import { NotificationSettings, NotificationSettingsUpdatePayload } from '../../types/scheduling';

export const validEmail = (value: string) => /^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(value.trim());
export const uniqueEmails = (values: string[]) => [...new Map(values.map(value => [value.trim().toLowerCase(), value.trim()])).values()].filter(Boolean);

export interface SmtpDraft {
  account: string;
  host: string;
  port: string;
  security: 'ssl' | 'starttls' | 'none';
  customLogin: boolean;
  login: string;
  customSender: boolean;
  sender: string;
  password: string;
  passwordAction: 'keep' | 'update' | 'clear';
  recipients: string[];
}

export function smtpDraft(settings: NotificationSettings | null): SmtpDraft {
  const account = validEmail(settings?.username || '') ? settings!.username! : settings?.sender || '';
  const login = settings?.username || settings?.sender || '';
  const sender = settings?.sender || account;
  return {
    account, host: settings?.host || '', port: String(settings?.port ?? 587),
    security: settings?.use_ssl ? 'ssl' : settings?.use_tls !== false ? 'starttls' : 'none',
    customLogin: login !== account, login, customSender: sender !== account, sender,
    password: '', passwordAction: 'keep', recipients: uniqueEmails(settings?.manual_recovery_recipients || []),
  };
}

export function smtpPayload(draft: SmtpDraft, saved: NotificationSettings | null): NotificationSettingsUpdatePayload {
  const account = draft.account.trim();
  const payload: NotificationSettingsUpdatePayload = {
    host: draft.host.trim(), port: Number(draft.port),
    sender: draft.customSender ? draft.sender.trim() : account,
    username: draft.customLogin ? draft.login.trim() || null
      : !saved?.username && account === smtpDraft(saved).account ? null : account,
    use_ssl: draft.security === 'ssl', use_tls: draft.security === 'starttls',
    manual_recovery_recipients: uniqueEmails(draft.recipients),
  };
  if (draft.passwordAction === 'update') payload.password = draft.password;
  if (draft.passwordAction === 'clear') payload.password = '';
  return payload;
}
