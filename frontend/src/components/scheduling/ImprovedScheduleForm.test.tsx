import { act, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import ImprovedScheduleForm from './ImprovedScheduleForm';
import type { ScheduledExperiment } from '../../types/scheduling';

vi.mock('../../services/schedulingApi', () => ({
  schedulingAPI: { getAvailableExperiments: vi.fn(async () => ({ data: { success: true, data: { experiments: [], categorized: {} } } })) },
}));

vi.mock('../../context/AuthContext', () => ({ useAuth: () => ({ user: { username: 'operator', role: 'user' } }) }));

/** A schedule as the list sends it after normalizeSchedule. */
const stored = (extra: Partial<ScheduledExperiment> = {}): ScheduledExperiment => ({
  schedule_id: 'method', experiment_name: 'Method', experiment_path: 'C:\\Methods\\Method.med', schedule_type: 'once', interval_hours: null,
  start_time: null, estimated_duration: 55, log_inactivity_threshold_minutes: 3, mode: 'real', runner: 'venus', created_by: 'operator',
  created_at: '2026-09-25T10:00:00', updated_at: '2026-09-25T10:00:00', is_active: true, archived: false,
  timeout_config: { timeout_minutes: null, action: 'continue' }, prerequisites: [], notification_contacts: [], recovery_required: false, ...extra,
});

describe('schedule draft sessions', () => {
  beforeEach(() => vi.useFakeTimers());
  afterEach(() => vi.useRealTimers());

  it('preserves focus, scroll and draft across two status refreshes', async () => {
    const props = { onClose: vi.fn(), onSubmit: vi.fn(), contacts: [], schedule: stored() };
    const view = render(<ImprovedScheduleForm {...props} />);
    await act(async () => { await vi.advanceTimersByTimeAsync(1000); });
    const duration = screen.getByRole('spinbutton', { name: 'Estimated duration (minutes)' }) as HTMLInputElement;
    fireEvent.change(duration, { target: { value: '61' } });
    duration.focus();
    const content = document.getElementById('schedule-dialog-description')!;
    content.scrollTop = 200;
    for (let tick = 0; tick < 2; tick++) {
      view.rerender(<ImprovedScheduleForm {...props} onClose={() => {}} schedule={stored({ estimated_duration: 99 })} contacts={[]} />);
      await act(async () => { await vi.advanceTimersByTimeAsync(30000); });
      expect(document.activeElement).toBe(duration);
      expect(duration.value).toBe('61');
      expect(content.scrollTop).toBe(200);
    }
    expect(screen.getByText('Log monitoring will continue, but no alert emails will be sent.')).toBeTruthy();
  });

  it('loads fresh values only after closing and reopening', async () => {
    const props = { onClose: vi.fn(), onSubmit: vi.fn(), contacts: [] };
    const view = render(<ImprovedScheduleForm {...props} schedule={stored()} />);
    await act(async () => { await vi.advanceTimersByTimeAsync(1000); });
    fireEvent.change(screen.getByRole('spinbutton', { name: 'Estimated duration (minutes)' }), { target: { value: '61' } });
    view.unmount();
    render(<ImprovedScheduleForm {...props} schedule={stored({ estimated_duration: 72 })} />);
    await act(async () => { await vi.advanceTimersByTimeAsync(1000); });
    expect((screen.getByRole('spinbutton', { name: 'Estimated duration (minutes)' }) as HTMLInputElement).value).toBe('72');
  });

  it('keeps unavailable primary and cleanup paths visible when the catalogue refreshes', async () => {
    const schedule = stored({ experiment_name: 'Saved method', experiment_path: 'C:\\Old\\Saved.med',
      timeout_config: { timeout_minutes: null, action: 'run_cleanup_and_terminate', cleanup_experiment_path: 'C:\\Old\\Cleanup.med' } });
    const props = { onClose: vi.fn(), onSubmit: vi.fn(), contacts: [], schedule };
    const view = render(<ImprovedScheduleForm {...props} catalogueVersion={0} />);
    await act(async () => { await vi.advanceTimersByTimeAsync(1000); });
    view.rerender(<ImprovedScheduleForm {...props} catalogueVersion={1} />);
    await act(async () => { await vi.advanceTimersByTimeAsync(1000); });
    expect(screen.getByText(/This saved path is not in the current available method library/)).toBeTruthy();
    expect(screen.getByText(/The saved cleanup path is archived/)).toBeTruthy();
    expect(screen.getByText(/C:\\Old\\Saved.med/)).toBeTruthy();
    expect(screen.getByText(/C:\\Old\\Cleanup.med/)).toBeTruthy();
  });

  it('sends a custom interval as typed, also when it equals a preset', async () => {
    const onSubmit = vi.fn().mockResolvedValue(undefined);
    render(<ImprovedScheduleForm onClose={vi.fn()} onSubmit={onSubmit} contacts={[]} schedule={stored({ schedule_type: 'interval', interval_hours: 6 })} />);
    await act(async () => { await vi.advanceTimersByTimeAsync(1000); });
    fireEvent.mouseDown(screen.getByText('Every 6 hours'));
    await act(async () => { await vi.advanceTimersByTimeAsync(500); });
    fireEvent.click(screen.getByRole('option', { name: 'Custom interval' }));
    await act(async () => { await vi.advanceTimersByTimeAsync(500); });
    const hours = () => screen.getByRole('spinbutton', { name: 'Hours' });
    const minutes = () => screen.getByRole('spinbutton', { name: 'Minutes' });
    fireEvent.change(hours(), { target: { value: '1' } });
    fireEvent.change(minutes(), { target: { value: '30' } });
    await act(async () => { fireEvent.click(screen.getByRole('button', { name: 'Save schedule' })); });
    expect(onSubmit.mock.calls[0][0].interval_hours).toBe(1.5);
    fireEvent.change(hours(), { target: { value: '6' } });
    fireEvent.change(minutes(), { target: { value: '0' } });
    await act(async () => { await vi.advanceTimersByTimeAsync(500); });
    // Still the custom fields: a value equal to a preset must not switch the choice back.
    expect(screen.getByText('Custom interval')).toBeTruthy();
    await act(async () => { fireEvent.click(screen.getByRole('button', { name: 'Save schedule' })); });
    expect(onSubmit.mock.calls[1][0].interval_hours).toBe(6);
  });

  it('retains the draft when an edit conflicts and explains how to reload', async () => {
    const onClose = vi.fn();
    const onSubmit = vi.fn().mockRejectedValue({ isAxiosError: true, response: { status: 409 } });
    render(<ImprovedScheduleForm onClose={onClose} onSubmit={onSubmit} contacts={[]} schedule={stored()} />);
    await act(async () => { await vi.advanceTimersByTimeAsync(1000); });
    fireEvent.change(screen.getByRole('spinbutton', { name: 'Estimated duration (minutes)' }), { target: { value: '61' } });
    await act(async () => { fireEvent.click(screen.getByRole('button', { name: 'Save schedule' })); });
    expect(screen.getByText(/Your entries are kept/)).toBeTruthy();
    expect(onSubmit.mock.calls[0][0].estimated_duration).toBe(61);
    expect(onClose).not.toHaveBeenCalled();
  });
});
