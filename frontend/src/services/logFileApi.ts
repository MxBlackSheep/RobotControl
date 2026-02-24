import { api } from './api';

export type PreviewMode = 'head' | 'tail';

export interface LogFileSource {
  id: string;
  label: string;
  path: string;
  exists: boolean;
  accessible: boolean;
  error?: string | null;
  permissions?: {
    is_local_session?: boolean;
    can_access?: boolean;
    access_scope?: string;
    ip_classification?: string | null;
    client_ip?: string | null;
  };
}

export interface LogFileListItem {
  name: string;
  path?: string;
  is_directory: boolean;
  extension?: string;
  is_archive?: boolean;
  archive_type?: string | null;
  size?: number;
  size_formatted?: string;
  compressed_size?: number;
  modified_date?: string;
  entry_path?: string;
}

export interface LogFileBrowseResponse {
  source: {
    id: string;
    label: string;
    path: string;
  };
  current_path: string;
  relative_path: string;
  items: LogFileListItem[];
  total_items: number;
  returned_items?: number;
  truncated?: boolean;
  max_items?: number;
}

export interface LogFileArchiveBrowseResponse {
  source: {
    id: string;
    label: string;
    path: string;
  };
  archive: {
    relative_path: string;
    path: string;
    name: string;
  };
  entry_path: string;
  items: LogFileListItem[];
  total_items: number;
  returned_items?: number;
  truncated?: boolean;
  max_items?: number;
}

export interface LogFilePreview {
  source_id: string;
  source_label: string;
  file_path: string;
  display_name: string;
  mode: PreviewMode;
  max_bytes: number;
  bytes_returned: number;
  bytes_scanned: number;
  truncated: boolean;
  encoding_used?: string | null;
  is_binary: boolean;
  file_locked: boolean;
  content: string | null;
  compressed?: boolean;
  archive_type?: string;
  file_size?: number;
  file_size_formatted?: string;
  modified_date?: string;
  archive_relative_path?: string;
  entry_path?: string;
  entry_size?: number;
  entry_size_formatted?: string;
  entry_compressed_size?: number;
}

const unwrapData = <T>(response: any): T => (response?.data?.data ?? response?.data) as T;

export const logFileApi = {
  getSources: async (): Promise<LogFileSource[]> => {
    const response = await api.get('/api/logfiles/sources');
    return unwrapData<LogFileSource[]>(response);
  },

  browse: async (sourceId: string, relativePath = ''): Promise<LogFileBrowseResponse> => {
    const response = await api.get('/api/logfiles/browse', {
      params: {
        source_id: sourceId,
        relative_path: relativePath,
      },
    });
    return unwrapData<LogFileBrowseResponse>(response);
  },

  preview: async (
    sourceId: string,
    relativePath: string,
    mode: PreviewMode = 'tail',
    maxBytes = 1024 * 1024,
  ): Promise<LogFilePreview> => {
    const response = await api.get('/api/logfiles/preview', {
      params: {
        source_id: sourceId,
        relative_path: relativePath,
        mode,
        max_bytes: maxBytes,
      },
    });
    return unwrapData<LogFilePreview>(response);
  },

  browseArchive: async (
    sourceId: string,
    archiveRelativePath: string,
    entryPath = '',
  ): Promise<LogFileArchiveBrowseResponse> => {
    const response = await api.get('/api/logfiles/archive/browse', {
      params: {
        source_id: sourceId,
        archive_relative_path: archiveRelativePath,
        entry_path: entryPath,
      },
    });
    return unwrapData<LogFileArchiveBrowseResponse>(response);
  },

  previewArchive: async (
    sourceId: string,
    archiveRelativePath: string,
    entryPath: string,
    mode: PreviewMode = 'tail',
    maxBytes = 1024 * 1024,
  ): Promise<LogFilePreview> => {
    const response = await api.get('/api/logfiles/archive/preview', {
      params: {
        source_id: sourceId,
        archive_relative_path: archiveRelativePath,
        entry_path: entryPath,
        mode,
        max_bytes: maxBytes,
      },
    });
    return unwrapData<LogFilePreview>(response);
  },
};
