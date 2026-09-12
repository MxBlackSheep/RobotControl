import React from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { expect, it, vi } from 'vitest';
import HostMethodBrowser from './HostMethodBrowser';
import { schedulingAPI } from '../../services/schedulingApi';
vi.mock('../../services/schedulingApi', () => ({ schedulingAPI: { browseMethodFolders: vi.fn() } }));

it('preserves the loaded folder and selection after failed navigation', async () => {
  vi.mocked(schedulingAPI.browseMethodFolders).mockResolvedValueOnce({ data: { success: true, data: {
    current_path: 'C:\\Methods', parent_path: 'C:\\', drives: ['C:\\'], shortcuts: [], breadcrumbs: [],
    folders: [{ name: 'Linked', path: 'C:\\Methods\\Linked', linked: true }], methods: [{ name: 'One.med', path: 'C:\\Methods\\One.med' }],
  } } } as any).mockRejectedValueOnce(new Error('Access denied'));
  const select = vi.fn();
  render(<HostMethodBrowser mode="method" onSelect={select} />);
  fireEvent.click(await screen.findByRole('radio', { name: /One.med/ }));
  fireEvent.change(screen.getByLabelText('Current folder'), { target: { value: 'C:\\Denied' } });
  fireEvent.click(screen.getByRole('button', { name: 'Go' }));
  await screen.findByText('Access denied');
  fireEvent.click(screen.getByRole('button', { name: 'Use selected method' }));
  expect(select).toHaveBeenCalledWith('C:\\Methods\\One.med');
  expect(screen.getByRole('radio', { name: /One.med/ }).getAttribute('aria-checked')).toBe('true');
});
