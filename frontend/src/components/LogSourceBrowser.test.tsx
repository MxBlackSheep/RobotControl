import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, expect, it, vi } from 'vitest';
import LogSourceBrowser from './LogSourceBrowser';
import { logFileApi } from '../services/logFileApi';

// Reading, following and expanded view belong to LogReader and are covered by e2e/logs.spec.ts.
vi.mock('./LogReader', () => ({ default: ({ selected }: any) => <div>Reading {selected.name}</div> }));
vi.mock('../services/logFileApi', () => ({ logFileApi: { browse: vi.fn(), browseArchive: vi.fn() } }));
const source = { id: 'python_log', label: 'Python logs', path: 'C:/logs', exists: true, accessible: true };
const rootListing = { items: [{ name: 'run.log', path: 'C:/logs/run.log', is_directory: false, extension: '.log' }, { name: 'nested', is_directory: true }], total_items: 251 };
const nestedListing = { items: [{ name: 'inner.log', path: 'C:/logs/nested/inner.log', is_directory: false, extension: '.log' }], total_items: 1 };
beforeEach(() => { vi.mocked(logFileApi.browse).mockResolvedValue(rootListing as any); });

it('searches filenames from page one and keeps old results when a refresh fails', async () => {
  render(<LogSourceBrowser source={source} active />);
  await screen.findByText('run.log');
  expect(vi.mocked(logFileApi.browse).mock.calls[0][2]).toMatchObject({ page: 1, limit: 50 });
  fireEvent.change(screen.getByLabelText('Find filenames'), { target: { value: ' old ' } });
  expect(logFileApi.browse).toHaveBeenCalledTimes(1);
  fireEvent.click(screen.getByRole('button', { name: 'Search', exact: true }));
  await waitFor(() => expect(logFileApi.browse).toHaveBeenCalledTimes(2));
  expect(vi.mocked(logFileApi.browse).mock.calls[1][2]).toMatchObject({ search: 'old', page: 1 });
  vi.mocked(logFileApi.browse).mockRejectedValueOnce(new Error('Folder locked'));
  fireEvent.click(screen.getByRole('button', { name: 'Refresh files' }));
  await screen.findByText(/Folder locked/);
  expect(screen.getByText(/Previous results are retained/)).toBeTruthy();
  expect(screen.getByText('run.log')).toBeTruthy();
});

it('ignores a late listing for a folder the user has already left', async () => {
  render(<LogSourceBrowser source={source} active />);
  await screen.findByText('run.log');
  let resolveNested!: (value: unknown) => void;
  vi.mocked(logFileApi.browse).mockImplementationOnce(() => new Promise(resolve => { resolveNested = resolve; }) as any);
  fireEvent.click(screen.getByText('▸ nested'));
  fireEvent.click(screen.getByRole('button', { name: 'Python logs' }));
  await waitFor(() => expect(logFileApi.browse).toHaveBeenCalledTimes(3));
  resolveNested(nestedListing);
  await waitFor(() => expect(screen.getByText('run.log')).toBeTruthy());
  expect(screen.queryByText('inner.log')).toBeNull();
});

it('opens the chosen file and clears it after moving to another folder', async () => {
  render(<LogSourceBrowser source={source} active />);
  fireEvent.click(await screen.findByText('run.log'));
  expect(screen.getByText('Reading run.log')).toBeTruthy();
  vi.mocked(logFileApi.browse).mockResolvedValueOnce(nestedListing as any);
  fireEvent.click(screen.getByText('▸ nested'));
  await screen.findByText('inner.log');
  expect(screen.queryByText('Reading run.log')).toBeNull();
  expect(screen.getByText('Choose a file to read it.')).toBeTruthy();
});
