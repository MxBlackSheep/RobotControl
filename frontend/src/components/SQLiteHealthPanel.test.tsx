import React from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, expect, it, vi } from 'vitest';
import SQLiteHealthPanel from './SQLiteHealthPanel';
import { api } from '../services/api';
vi.mock('../services/api', () => ({ api: { get: vi.fn(), post: vi.fn() } }));
beforeEach(() => vi.clearAllMocks());

it('previews repairs without applying them, then submits the reviewed token', async () => {
  vi.mocked(api.get).mockResolvedValue({ data: { token: 'review', healthy: false, structural_error: false, message: 'Review changes',
    issues: [{ kind: 'orphan_token', id: 1, description: 'Remove dangling token', repairable: true }] } });
  vi.mocked(api.post).mockResolvedValue({ data: { backup: 'backup.db', preview: { token: 'new', healthy: true, issues: [], message: 'Checks passed' } } });
  vi.spyOn(window, 'confirm').mockReturnValue(true);
  render(<SQLiteHealthPanel />);
  fireEvent.click(screen.getByRole('button', { name: 'Preview authentication storage health' }));
  await screen.findByText(/Remove dangling token/);
  expect(api.post).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole('button', { name: 'Back up and apply reviewed repairs' }));
  await waitFor(() => expect(api.post).toHaveBeenCalledWith('/api/admin/sqlite/authentication/repair', { token: 'review' }, { timeout: 60000 }));
  expect(await screen.findByText(/Verified backup saved/)).toBeTruthy();
});

it('never enables automatic repair for ambiguous history or corruption', async () => {
  vi.mocked(api.get).mockResolvedValue({ data: { token: 'review', healthy: false, structural_error: false, message: 'Review required',
    issues: [{ kind: 'execution_conflict', id: 'run', description: 'Conflicting history', repairable: false }] } });
  render(<SQLiteHealthPanel />);
  fireEvent.click(screen.getByRole('button', { name: 'Preview scheduling storage health' }));
  await screen.findByText(/Conflicting history/);
  expect((screen.getByRole('button', { name: 'Back up and apply reviewed repairs' }) as HTMLButtonElement).disabled).toBe(true);
});
