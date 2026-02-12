import { api } from './api';

export interface HxRunMaintenancePermissions {
  is_local_session: boolean;
  can_edit: boolean;
  ip_classification?: string | null;
  client_ip?: string | null;
}

export interface HxRunMaintenanceState {
  enabled: boolean;
  reason?: string | null;
  updated_by?: string | null;
  updated_at?: string | null;
  permissions: HxRunMaintenancePermissions;
}

const unwrapData = <T>(response: any): T => {
  return (response?.data?.data ?? response?.data) as T;
};

export const hxrunMaintenanceApi = {
  getState: async (): Promise<HxRunMaintenanceState> => {
    const response = await api.get('/api/maintenance/hxrun');
    return unwrapData<HxRunMaintenanceState>(response);
  },

  updateState: async (enabled: boolean, reason?: string): Promise<HxRunMaintenanceState> => {
    const response = await api.put('/api/maintenance/hxrun', {
      enabled,
      reason,
    });
    return unwrapData<HxRunMaintenanceState>(response);
  },
};

