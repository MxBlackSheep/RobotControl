import React from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, expect, it, vi } from 'vitest';
import MethodPathDialog from './MethodPathDialog';
import { schedulingAPI } from '../../services/schedulingApi';
vi.mock('../../services/schedulingApi', () => ({ schedulingAPI: { previewMethodPath: vi.fn(), changeMethodPath: vi.fn() } }));
const method = { method_id: 'm', file_path: 'C:\\Old\\One.med' } as any;
const references = [
  { schedule_id: 'a', experiment_name: 'Active', role: 'primary', is_active: true, archived: false, busy: false, updated_at: 'version-a' },
  { schedule_id: 'a', experiment_name: 'Active', role: 'cleanup', is_active: true, archived: false, busy: false, updated_at: 'version-a' },
  { schedule_id: 'b', experiment_name: 'Paused', role: 'primary', is_active: true, archived: false, busy: true, updated_at: 'version-b' },
  { schedule_id: 'c', experiment_name: 'Archived', role: 'primary', is_active: false, archived: true, busy: false, updated_at: 'version-c' },
];
beforeEach(() => {
  vi.mocked(schedulingAPI.previewMethodPath).mockResolvedValue({ data: { success: true, data: { method_id: 'm', expected_revision: 7, old_path: method.file_path, new_path: 'C:\\New\\One.med', references } } } as any);
});
async function review() {
  fireEvent.change(screen.getByLabelText(/New absolute method path/), { target: { value: 'C:\\New\\One.med' } });
  fireEvent.click(screen.getByRole('button', { name: 'Review change' }));
  await screen.findByText('Only the library path will change.', { exact: false });
}
it('requires explicit reference selection and excludes paused/archived schedules', async () => {
  const changed = vi.fn();
  vi.mocked(schedulingAPI.changeMethodPath).mockResolvedValue({ data: { success: true, data: { updated_schedule_ids: ['a'] } } } as any);
  render(<MethodPathDialog method={method} onClose={vi.fn()} onChanged={changed} />);
  await review();
  expect(screen.getAllByRole('checkbox').every(input => !(input as HTMLInputElement).checked)).toBe(true);
  expect((screen.getByRole('checkbox', { name: /Paused/ }) as HTMLInputElement).disabled).toBe(true);
  expect((screen.getByRole('checkbox', { name: /Archived/ }) as HTMLInputElement).disabled).toBe(true);
  fireEvent.click(screen.getByRole('checkbox', { name: /Active.*cleanup/ }));
  fireEvent.click(screen.getByRole('button', { name: 'Save reviewed change' }));
  await waitFor(() => expect(changed).toHaveBeenCalledOnce());
  expect(schedulingAPI.changeMethodPath).toHaveBeenCalledWith('m', { new_path: 'C:\\New\\One.med', expected_revision: 7,
    references: [{ schedule_id: 'a', role: 'cleanup', expected_updated_at: 'version-a' }] });
  expect(screen.getByText(/3 unselected reference\(s\) kept their original paths/)).toBeTruthy();
});
it('retains the reviewed selection on conflict and clears selection on an explicit new review', async () => {
  vi.mocked(schedulingAPI.changeMethodPath).mockRejectedValue({ response: { data: { detail: 'Schedule changed' } } });
  render(<MethodPathDialog method={method} onClose={vi.fn()} onChanged={vi.fn()} />);
  await review();
  fireEvent.click(screen.getByRole('checkbox', { name: /Active.*primary/ }));
  fireEvent.click(screen.getByRole('button', { name: 'Save reviewed change' }));
  await screen.findByText(/Schedule changed.*Your entries are retained/);
  expect((screen.getByRole('checkbox', { name: /Active.*primary/ }) as HTMLInputElement).checked).toBe(true);
  fireEvent.click(screen.getByRole('button', { name: 'Review again' }));
  await waitFor(() => expect((screen.getByRole('checkbox', { name: /Active.*primary/ }) as HTMLInputElement).checked).toBe(false));
});
