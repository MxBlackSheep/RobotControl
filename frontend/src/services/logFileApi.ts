import { api } from "./api";

export type BrowseOptions = {
  search?: string;
  file_type?: string;
  modified_from?: string;
  modified_to?: string;
  sort_by?: string;
  sort_direction?: string;
  page?: number;
  limit?: number;
};

export type PreviewMode = "head" | "tail";

export interface LogFileSource {
  id: string;
  label: string;
  path: string;
  exists: boolean;
  accessible: boolean;
  error?: string | null;
  shortcuts?: { label: string; relative_path: string }[];
  permissions?: {
    is_local_session?: boolean;
    can_access?: boolean;
    access_scope?: string;
    ip_classification?: string | null;
    client_ip?: string | null;
  };
}

export interface LogReaderStatus {
  id: string;
  state: "preparing" | "ready" | "error";
  error?: string;
  file_path: string;
  entry_path?: string;
  display_name: string;
  compressed: boolean;
  encoding: string;
  replacement_characters: number;
  bytes_scanned: number;
  bytes_prepared: number;
  section_count: number;
  captured_at: number;
  source_changed: boolean;
}
export interface LogReaderSection extends LogReaderStatus {
  content: string;
  cursor: string;
  previous_cursor: string | null;
  next_cursor: string | null;
  section_number: number;
  start_byte: number;
  end_byte: number;
  line_continues: boolean;
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

const unwrapData = <T>(response: any): T =>
  (response?.data?.data ?? response?.data) as T;

export const logFileApi = {
  openReader: async (
    sourceId: string,
    relativePath: string,
    entryPath?: string,
  ): Promise<LogReaderStatus> =>
    unwrapData(
      await api.post("/api/logfiles/readers", {
        source_id: sourceId,
        relative_path: relativePath,
        entry_path: entryPath || null,
      }),
    ),
  readerStatus: async (
    id: string,
    signal?: AbortSignal,
  ): Promise<LogReaderStatus> =>
    unwrapData(await api.get(`/api/logfiles/readers/${id}`, { signal })),
  readerSection: async (
    id: string,
    cursor: string,
    signal?: AbortSignal,
  ): Promise<LogReaderSection> =>
    unwrapData(
      await api.get(`/api/logfiles/readers/${id}/sections`, {
        signal,
        params: { cursor },
      }),
    ),
  closeReader: async (id: string): Promise<void> => {
    await api.delete(`/api/logfiles/readers/${id}`);
  },
  getSources: async (): Promise<LogFileSource[]> => {
    const response = await api.get("/api/logfiles/sources");
    return unwrapData<LogFileSource[]>(response);
  },

  browse: async (
    sourceId: string,
    relativePath = "",
    options: BrowseOptions = {},
    signal?: AbortSignal,
  ): Promise<LogFileBrowseResponse> => {
    const response = await api.get("/api/logfiles/browse", {
      signal,
      params: { ...options, source_id: sourceId, relative_path: relativePath },
    });
    return unwrapData<LogFileBrowseResponse>(response);
  },

  preview: async (
    sourceId: string,
    relativePath: string,
    mode: PreviewMode = "tail",
    maxBytes = 1024 * 1024,
    signal?: AbortSignal,
  ): Promise<LogFilePreview> => {
    const response = await api.get("/api/logfiles/preview", {
      signal,
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
    entryPath = "",
    options: BrowseOptions = {},
    signal?: AbortSignal,
  ): Promise<LogFileArchiveBrowseResponse> => {
    const response = await api.get("/api/logfiles/archive/browse", {
      signal,
      params: {
        ...options,
        source_id: sourceId,
        archive_relative_path: archiveRelativePath,
        entry_path: entryPath,
      },
    });
    return unwrapData<LogFileArchiveBrowseResponse>(response);
  },

};
