import React from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import NotificationEmailSettingsPanel from './NotificationEmailSettingsPanel';
import { smtpDraft, smtpPayload } from './smtpForm';
import { NotificationSettings } from '../../types/scheduling';

const saved: NotificationSettings = { host: 'smtp.example.test', port: 465, username: 'robot@example.test',
  sender: 'robot@example.test', use_ssl: true, use_tls: false, has_password: true, manual_recovery_recipients: [] };
const props = () => ({ settings: saved, loading: false, contacts: [],
  onSave: vi.fn(async payload => ({ settings: { ...saved, ...payload } })),
  onRefresh: vi.fn(async () => ({ settings: saved })),
  onSendTest: vi.fn(async () => ({ success: true })),
});

describe('SMTP draft compatibility', () => {
  it.each([
    saved,
    { ...saved, username: 'service-login', sender: 'from@example.test' },
    { ...saved, username: 'login@example.test', sender: 'alias@example.test' },
    { ...saved, username: null },
    { ...saved, use_ssl: false, use_tls: true, port: 2525 },
    { ...saved, use_ssl: false, use_tls: false },
  ])('round trips saved configuration without a password', settings => {
    const payload = smtpPayload(smtpDraft(settings), settings);
    expect(payload).toEqual({ host: settings.host, port: settings.port, username: settings.username,
      sender: settings.sender, use_ssl: settings.use_ssl, use_tls: settings.use_tls, manual_recovery_recipients: [] });
    expect(payload).not.toHaveProperty('password');
  });

  it('distinguishes keeping, replacing and clearing the password', () => {
    const draft = smtpDraft(saved);
    expect(smtpPayload(draft, saved)).not.toHaveProperty('password');
    draft.passwordAction = 'update'; draft.password = 'test-only-value';
    expect(smtpPayload(draft, saved).password).toBe('test-only-value');
    draft.passwordAction = 'clear';
    expect(smtpPayload(draft, saved).password).toBe('');
  });
});

describe('SMTP setup interaction', () => {
  it('requires saving a dirty draft before testing, and saving never sends email', async () => {
    const p = props();
    render(<NotificationEmailSettingsPanel {...p} />);
    fireEvent.change(screen.getByLabelText(/Email account address/), { target: { value: 'new@example.test' } });
    expect((screen.getByRole('button', { name: 'Send test email' }) as HTMLButtonElement).disabled).toBe(true);
    expect(screen.getByText('Save your changes before sending a test email.')).toBeTruthy();
    fireEvent.click(screen.getByRole('button', { name: 'Save settings' }));
    await waitFor(() => expect(p.onSave).toHaveBeenCalledOnce());
    expect(p.onSave.mock.calls[0][0]).toMatchObject({ username: 'new@example.test', sender: 'new@example.test' });
    expect(p.onSave.mock.calls[0][0]).not.toHaveProperty('password');
    p.onSendTest.mockClear();
    await waitFor(() => expect((screen.getByRole('button', { name: 'Send test email' }) as HTMLButtonElement).disabled).toBe(false));
    expect(p.onSendTest).not.toHaveBeenCalled();
  });

  it('exposes existing custom login and sender overrides', () => {
    render(<NotificationEmailSettingsPanel {...props()} settings={{ ...saved, username: 'service', sender: 'alias@example.test' }} />);
    expect((screen.getByLabelText('Mail-server login username') as HTMLInputElement).value).toBe('service');
    expect(screen.getByRole('button', { name: 'Advanced settings' }).getAttribute('aria-expanded')).toBe('true');
  });

  it('preserves the draft when confirmed refresh fails or props change', async () => {
    const p = { ...props(), onRefresh: vi.fn(async () => ({ error: 'Server unavailable' })) };
    const view = render(<NotificationEmailSettingsPanel {...p} />);
    fireEvent.change(screen.getByLabelText(/Email account address/), { target: { value: 'draft@example.test' } });
    view.rerender(<NotificationEmailSettingsPanel {...p} settings={{ ...saved, sender: 'external@example.test' }} />);
    fireEvent.click(screen.getByRole('button', { name: 'Refresh' }));
    expect(p.onRefresh).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole('button', { name: 'Discard and reload' }));
    await screen.findByText('Server unavailable');
    expect((screen.getByLabelText(/Email account address/) as HTMLInputElement).value).toBe('draft@example.test');
  });

  it('shows a persistent detailed SMTP failure inline', async () => {
    const p = { ...props(), onSendTest: vi.fn(async () => ({ success: false, error: 'SMTP authentication rejected (smtp.example.test:465)' })) };
    render(<NotificationEmailSettingsPanel {...p} />);
    fireEvent.click(screen.getByRole('button', { name: 'Send test email' }));
    expect(await screen.findByText('SMTP authentication rejected (smtp.example.test:465)')).toBeTruthy();
    expect(screen.queryByRole('dialog')).toBeNull();
  });

  it('allows undoing password removal before saving', () => {
    render(<NotificationEmailSettingsPanel {...props()} />);
    fireEvent.click(screen.getByRole('button', { name: 'Remove stored password on save' }));
    expect(screen.getByText('The stored password will be removed when you save.')).toBeTruthy();
    fireEvent.click(screen.getByRole('button', { name: 'Undo password change' }));
    expect((screen.getByRole('button', { name: 'Save settings' }) as HTMLButtonElement).disabled).toBe(true);
  });
});
