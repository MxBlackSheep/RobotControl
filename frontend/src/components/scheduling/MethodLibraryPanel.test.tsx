import React from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, expect, it, vi } from 'vitest';
import MethodLibraryPanel from './MethodLibraryPanel';
import { schedulingAPI } from '../../services/schedulingApi';
vi.mock('../../services/schedulingApi', () => ({ schedulingAPI: { getMethodLibrary: vi.fn(), archiveMethod: vi.fn(), checkMethodPaths: vi.fn() } }));
const rows = [
  { method_id: 'a', method_name: 'One', file_path: 'C:\\Methods\\One.med', containing_folder: 'C:\\Methods', archived: false, revision: 2, path_status: 'available', schedule_count: 1,
    references: [{ schedule_id: 's', experiment_name: 'Original schedule', role: 'cleanup', busy: true }], imported_by: 'tester', imported_at: 'now' },
  { method_id: 'b', method_name: 'Two', file_path: 'D:\\Two.med', containing_folder: 'D:\\', archived: true, revision: 4, path_status: 'missing', schedule_count: 0, references: [] },
];
const props = () => ({ version: 0, onChanged: vi.fn(), onImport: vi.fn(), onCreateSchedule: vi.fn() });
beforeEach(() => {
  vi.mocked(schedulingAPI.getMethodLibrary).mockResolvedValue({ data: { success: true, data: { methods: rows } } } as any);
  vi.mocked(schedulingAPI.archiveMethod).mockResolvedValue({} as any);
});
it('requires explicit selection and confirmation before archiving', async () => {
  const p = props(); render(<MethodLibraryPanel {...p} />);
  await screen.findByRole('button', { name: 'One' });
  expect(screen.queryByRole('button', { name: 'Two' })).toBeNull();
  fireEvent.click(screen.getByRole('checkbox', { name: 'Select C:\\Methods\\One.med' }));
  fireEvent.click(screen.getByRole('button', { name: 'Archive selected' }));
  expect(schedulingAPI.archiveMethod).not.toHaveBeenCalled();
  expect(screen.getByText(/Hamilton files and existing schedules will remain unchanged/)).toBeTruthy();
  fireEvent.click(screen.getByRole('button', { name: 'Archive methods' }));
  await waitFor(() => expect(p.onChanged).toHaveBeenCalledOnce());
  expect(schedulingAPI.archiveMethod).toHaveBeenCalledWith('a', true, 2);
});
it('filters archived entries separately from missing paths and shows schedule usage', async () => {
  render(<MethodLibraryPanel {...props()} />);
  fireEvent.click(await screen.findByRole('button', { name: 'One' }));
  expect(await screen.findByText('Original schedule — cleanup method')).toBeTruthy();
  expect(screen.getByText(/Busy \(queued, running or paused\)/)).toBeTruthy();
  fireEvent.click(screen.getByRole('button', { name: 'Close' }));
  fireEvent.change(screen.getByLabelText('Library view'), { target: { value: 'archived' } });
  expect(await screen.findByRole('button', { name: 'Two' })).toBeTruthy();
  expect(screen.queryByRole('button', { name: 'One' })).toBeNull();
  fireEvent.change(screen.getByLabelText('Path status'), { target: { value: 'available' } });
  expect(screen.queryByRole('button', { name: 'Two' })).toBeNull();
});
it('preserves filter and existing rows after a refresh failure', async () => {
  render(<MethodLibraryPanel {...props()} />);
  await screen.findByRole('button', { name: 'One' });
  fireEvent.change(screen.getByLabelText('Search methods or paths'), { target: { value: 'One' } });
  vi.mocked(schedulingAPI.getMethodLibrary).mockRejectedValueOnce(new Error('Offline'));
  fireEvent.click(screen.getByRole('button', { name: 'Refresh library' }));
  await screen.findByText('Offline');
  expect((screen.getByLabelText('Search methods or paths') as HTMLInputElement).value).toBe('One');
  expect(screen.getByRole('button', { name: 'One' })).toBeTruthy();
});
