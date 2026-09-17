import React from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, expect, it, vi } from 'vitest';
import RecoverySafetyPanel from './RecoverySafetyPanel';
import { api } from '../../services/api';
import { ManualRecoveryState } from '../../types/scheduling';
vi.mock('../../services/api', () => ({ api: { post: vi.fn() } }));
const state: ManualRecoveryState = { active: true, storage_healthy: true, safety_revision: 7, resume_required: true,
  pending_recoveries: [{ schedule_id: 'deleted', experiment_name: 'Original method', schedule_missing: true, archived: false }] };
beforeEach(() => { vi.clearAllMocks(); vi.mocked(api.post).mockResolvedValue({ data: {} }); });

it('requires a note and robot confirmation for a missing schedule, and never resumes on acknowledgement', async () => {
  const changed = vi.fn().mockResolvedValue(undefined);
  render(<RecoverySafetyPanel state={state} isLocal onChanged={changed} />);
  const acknowledge = screen.getByRole('button', { name: 'Acknowledge recovery' });
  expect((acknowledge as HTMLButtonElement).disabled).toBe(true);
  fireEvent.click(screen.getByRole('checkbox'));
  expect((acknowledge as HTMLButtonElement).disabled).toBe(true);
  fireEvent.change(screen.getByLabelText('Recovery note'), { target: { value: 'Deck checked' } });
  fireEvent.click(acknowledge);
  await waitFor(() => expect(changed).toHaveBeenCalledOnce());
  expect(api.post).toHaveBeenCalledWith('/api/scheduling/recovery/resolve', {
    schedule_id: 'deleted', expected_revision: 7, robot_ready: true, note: 'Deck checked',
  });
});

it('requires a separate confirmed Resume action', async () => {
  vi.spyOn(window, 'confirm').mockReturnValue(true);
  render(<RecoverySafetyPanel state={{ ...state, active: false, pending_recoveries: [] }} isLocal onChanged={vi.fn()} />);
  fireEvent.click(screen.getByRole('button', { name: 'Resume queued jobs' }));
  await waitFor(() => expect(api.post).toHaveBeenCalledWith('/api/scheduling/dispatch/resume', { expected_revision: 7 }));
  expect(window.confirm).toHaveBeenCalledWith(expect.stringContaining('immediately'));
});

it('blocks controls on storage failure and hides them for remote sessions', () => {
  const { rerender } = render(<RecoverySafetyPanel state={{ ...state, storage_healthy: false }} isLocal onChanged={vi.fn()} />);
  expect((screen.getByRole('button', { name: 'Acknowledge recovery' }) as HTMLButtonElement).disabled).toBe(true);
  expect((screen.getByRole('button', { name: 'Resume queued jobs' }) as HTMLButtonElement).disabled).toBe(true);
  rerender(<RecoverySafetyPanel state={state} isLocal={false} onChanged={vi.fn()} />);
  expect(screen.queryByRole('button', { name: 'Acknowledge recovery' })).toBeNull();
  expect(screen.queryByRole('button', { name: 'Resume queued jobs' })).toBeNull();
});

it('refreshes after stale acknowledgement while preserving the error', async () => {
  vi.mocked(api.post).mockRejectedValue({ response: { status: 409, data: { detail: 'Scheduler safety state changed' } } });
  const changed = vi.fn();
  render(<RecoverySafetyPanel state={state} isLocal onChanged={changed} />);
  fireEvent.click(screen.getByRole('checkbox'));
  fireEvent.change(screen.getByLabelText('Recovery note'), { target: { value: 'Checked' } });
  fireEvent.click(screen.getByRole('button', { name: 'Acknowledge recovery' }));
  expect(await screen.findByText('Scheduler safety state changed')).toBeTruthy();
  expect(changed).toHaveBeenCalledOnce();
});
