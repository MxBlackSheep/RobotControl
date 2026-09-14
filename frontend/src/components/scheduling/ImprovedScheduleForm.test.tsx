import React from 'react';
import { act, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import ImprovedScheduleForm from './ImprovedScheduleForm';

vi.mock('../../services/schedulingApi', () => ({
  schedulingAPI: { getAvailableExperiments: vi.fn(async () => ({ data: { success: true, data: { experiments: [], categorized: {} } } })) },
  schedulingService: { getEvoYeastExperiments: vi.fn(async () => ({ experiments: [] })) },
}));

describe('schedule draft sessions', () => {
  beforeEach(() => vi.useFakeTimers());
  afterEach(() => vi.useRealTimers());

  it('preserves focus, scroll, draft and sections across two status refreshes', async () => {
    const props = { open: true, onClose: vi.fn(), onSubmit: vi.fn(), contacts: [], initialData: { estimated_duration: 55 } };
    const view = render(<ImprovedScheduleForm {...props} />);
    await act(async () => { await vi.advanceTimersByTimeAsync(1000); });
    const duration = screen.getByRole('spinbutton', { name: 'Estimated Duration (minutes)' }) as HTMLInputElement;
    fireEvent.change(duration, { target: { value: '61' } });
    fireEvent.click(screen.getByRole('button', { name: 'Experiment Preparation' }));
    duration.focus();
    const content = document.getElementById('schedule-dialog-description')!;
    content.scrollTop = 200;
    for (let tick = 0; tick < 2; tick++) {
      view.rerender(<ImprovedScheduleForm {...props} onClose={() => {}} initialData={{ estimated_duration: 99 }} contacts={[]} />);
      await act(async () => { await vi.advanceTimersByTimeAsync(30000); });
      expect(document.activeElement).toBe(duration);
      expect(duration.value).toBe('61');
      expect(content.scrollTop).toBe(200);
      expect(screen.getByRole('button', { name: 'Experiment Preparation' }).getAttribute('aria-expanded')).toBe('true');
    }
    expect(screen.getByText('Log monitoring will continue, but no alert emails will be sent.')).toBeTruthy();
  });

  it('loads fresh initial data only after closing and reopening', async () => {
    const props = { onClose: vi.fn(), onSubmit: vi.fn(), contacts: [] };
    const view = render(<ImprovedScheduleForm {...props} open initialData={{ estimated_duration: 55 }} />);
    await act(async () => { await vi.advanceTimersByTimeAsync(1000); });
    fireEvent.change(screen.getByRole('spinbutton', { name: 'Estimated Duration (minutes)' }), { target: { value: '61' } });
    view.rerender(<ImprovedScheduleForm {...props} open={false} />);
    await act(async () => { await vi.advanceTimersByTimeAsync(1000); });
    view.rerender(<ImprovedScheduleForm {...props} open initialData={{ estimated_duration: 72 }} />);
    await act(async () => { await vi.advanceTimersByTimeAsync(1000); });
    expect((screen.getByRole('spinbutton', { name: 'Estimated Duration (minutes)' }) as HTMLInputElement).value).toBe('72');
  });

  it('keeps unavailable primary and cleanup paths visible when the catalogue refreshes', async () => {
    const initialData = { experiment_name: 'Saved method', experiment_path: 'C:\\Old\\Saved.med', timeout_cleanup_experiment_path: 'C:\\Old\\Cleanup.med', timeout_action: 'run_cleanup_and_terminate' as any };
    const props = { open: true, mode: 'edit' as const, onClose: vi.fn(), onSubmit: vi.fn(), contacts: [], initialData };
    const view = render(<ImprovedScheduleForm {...props} catalogueVersion={0} />);
    await act(async () => { await vi.advanceTimersByTimeAsync(1000); });
    view.rerender(<ImprovedScheduleForm {...props} catalogueVersion={1} />);
    await act(async () => { await vi.advanceTimersByTimeAsync(1000); });
    expect(screen.getByText(/This saved path is not in the current available method library/)).toBeTruthy();
    expect(screen.getByText(/The saved cleanup path is archived/)).toBeTruthy();
    expect(screen.getByText(/C:\\Old\\Saved.med/)).toBeTruthy();
    expect(screen.getByText(/C:\\Old\\Cleanup.med/)).toBeTruthy();
  });

  it('retains the draft when an edit conflicts and explains how to reload', async () => {
    const onClose = vi.fn();
    const onSubmit = vi.fn().mockRejectedValue({ isAxiosError: true, response: { status: 409 } });
    render(<ImprovedScheduleForm open mode="edit" onClose={onClose} onSubmit={onSubmit} contacts={[]}
      initialData={{ experiment_name: 'Method', experiment_path: 'C:\\Methods\\Method.med' }} />);
    await act(async () => { await vi.advanceTimersByTimeAsync(1000); });
    fireEvent.change(screen.getByRole('spinbutton', { name: 'Estimated Duration (minutes)' }), { target: { value: '61' } });
    await act(async () => { fireEvent.click(screen.getByRole('button', { name: 'Update Schedule' })); });
    expect(screen.getByText(/Your entries are still here/)).toBeTruthy();
    expect(onSubmit.mock.calls[0][0].estimated_duration).toBe(61);
    expect(onClose).not.toHaveBeenCalled();
  });
});
