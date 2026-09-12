import React from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import FolderImportDialog, { browserMethodPaths } from './FolderImportDialog';
import { schedulingAPI } from '../../services/schedulingApi';

vi.mock('../../services/schedulingApi', () => ({ schedulingAPI: {
  previewExperimentImport: vi.fn(), importExperimentFolder: vi.fn(), importExperimentFiles: vi.fn(),
} }));

const rows = [
  { name: 'First', relative_path: 'First.med', path: 'C:\\Methods\\First.med', action: 'new' },
  { name: 'Second', relative_path: 'nested/Second.MED', path: 'C:\\Methods\\nested\\Second.MED', action: 'update' },
  { name: 'Missing', relative_path: 'Missing.med', path: null, action: 'invalid', reason: 'File missing' },
];
const props = () => ({ open: true, onClose: vi.fn(), onImportComplete: vi.fn(), onCreateSchedule: vi.fn(), isLocalClient: true });
async function chooseManualFolder() {
  fireEvent.click(screen.getByRole('radio', { name: 'Enter a folder path' }));
  fireEvent.change(screen.getByLabelText('Folder path on RobotControl computer'), { target: { value: 'C:\\Methods' } });
  fireEvent.click(screen.getByRole('button', { name: 'Review methods' }));
  await screen.findByText('First');
}

beforeEach(() => {
  vi.mocked(schedulingAPI.previewExperimentImport).mockResolvedValue({ data: { success: true, data: { folder: 'C:\\Methods', total_found: 3, methods: rows } } } as any);
});

describe('method import workflow', () => {
  it('previews before writing and imports only selected valid methods', async () => {
    const p = props();
    vi.mocked(schedulingAPI.importExperimentFolder).mockResolvedValue({ data: { success: false, data: {
      new_methods: 0, updated_methods: 0, failed_methods: 1, total_found: 1, methods: [{ ...rows[1], status: 'failed', reason: 'File disappeared after preview' }], errors: [],
    } } } as any);
    render(<FolderImportDialog {...p} />);
    await chooseManualFolder();
    expect(schedulingAPI.importExperimentFolder).not.toHaveBeenCalled();
    expect((screen.getByRole('checkbox', { name: 'Import Missing.med' }) as HTMLInputElement).disabled).toBe(true);
    fireEvent.click(screen.getByRole('checkbox', { name: 'Import First.med' }));
    fireEvent.click(screen.getByRole('button', { name: 'Import 1 selected' }));
    expect(await screen.findByText('File disappeared after preview')).toBeTruthy();
    expect(schedulingAPI.importExperimentFolder).toHaveBeenCalledWith('C:\\Methods', ['nested/Second.MED']);
    expect(screen.getByText('0 added · 0 updated · 1 failed')).toBeTruthy();
    expect(screen.queryByRole('button', { name: 'Create a schedule' })).toBeNull();
    expect(p.onImportComplete).not.toHaveBeenCalled();
  });

  it('requires a host path for browser selections and strips only the selected root', async () => {
    const file = new File(['method'], 'Second.MED');
    Object.defineProperty(file, 'webkitRelativePath', { value: 'Selected/nested/Second.MED' });
    expect(browserMethodPaths([file])).toEqual(['nested/Second.MED']);
    const p = props();
    vi.mocked(schedulingAPI.importExperimentFiles).mockResolvedValue({ data: { success: true, data: {
      new_methods: 1, updated_methods: 1, failed_methods: 0, total_found: 2, methods: rows.slice(0, 2).map(row => ({ ...row, status: 'added' })), errors: [],
    } } } as any);
    render(<FolderImportDialog {...p} />);
    fireEvent.change(screen.getByLabelText('Method folder files'), { target: { files: [file] } });
    expect((screen.getByRole('button', { name: 'Review methods' }) as HTMLButtonElement).disabled).toBe(true);
    fireEvent.change(screen.getByLabelText('Folder path on RobotControl computer'), { target: { value: 'C:\\Methods' } });
    fireEvent.click(screen.getByRole('button', { name: 'Review methods' }));
    await screen.findByText('First');
    expect(schedulingAPI.previewExperimentImport).toHaveBeenCalledWith({ folder_path: 'C:\\Methods', relative_paths: ['nested/Second.MED'] });
    fireEvent.click(screen.getByRole('button', { name: 'Import 2 selected' }));
    await screen.findByText('1 added · 1 updated · 0 failed');
    expect(p.onImportComplete).toHaveBeenCalledOnce();
    expect(p.onCreateSchedule).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole('button', { name: 'Create a schedule' }));
    expect(p.onCreateSchedule).toHaveBeenCalledOnce();
  });

  it('keeps every result searchable, including rows beyond the first ten', async () => {
    const many = Array.from({ length: 15 }, (_, index) => ({ ...rows[0], name: `Method ${index}`, relative_path: `${index}.med`, path: `C:\\Methods\\${index}.med` }));
    vi.mocked(schedulingAPI.previewExperimentImport).mockResolvedValue({ data: { success: true, data: { folder: 'C:\\Methods', total_found: 15, methods: many } } } as any);
    render(<FolderImportDialog {...props()} />);
    fireEvent.click(screen.getByRole('radio', { name: 'Enter a folder path' }));
    fireEvent.change(screen.getByLabelText('Folder path on RobotControl computer'), { target: { value: 'C:\\Methods' } });
    fireEvent.click(screen.getByRole('button', { name: 'Review methods' }));
    expect(await screen.findByText('Method 14')).toBeTruthy();
    fireEvent.change(screen.getByLabelText('Search methods and paths'), { target: { value: '14.med' } });
    expect(screen.queryByText('Method 0')).toBeNull();
    expect(screen.getByText('Method 14')).toBeTruthy();
    expect(screen.getByRole('button', { name: 'Import 15 selected' })).toBeTruthy();
  });

  it('blocks preview for a remote client', () => {
    render(<FolderImportDialog {...props()} isLocalClient={false} />);
    expect((screen.getByRole('button', { name: 'Review methods' }) as HTMLButtonElement).disabled).toBe(true);
    expect(schedulingAPI.previewExperimentImport).not.toHaveBeenCalled();
  });
});
