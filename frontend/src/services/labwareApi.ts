import { api } from './api';

export interface TipTrackingPermissions {
  role: string;
  is_local_session: boolean;
  can_update: boolean;
  ip_classification?: string | null;
  client_ip?: string | null;
}

export interface TipTrackingFamilyState {
  family_id: string;
  display_name: string;
  left_racks: string[];
  right_racks: string[];
  reset_map: Record<string, Record<string, string[]>>;
  tips: Record<string, Record<string, string>>;
}

export interface TipTrackingSnapshot {
  grid: {
    rows: number;
    cols: number;
    positions_per_rack: number;
  };
  auto_refresh_ms: number;
  status_order: string[];
  status_colors: Record<string, string>;
  unknown_status: string;
  families: TipTrackingFamilyState[];
  permissions: TipTrackingPermissions;
  refreshed_at: string;
}

export interface TipTrackingUpdate {
  labware_id: string;
  position_id: number;
  status: string;
}

export interface TipTrackingUpdateResult {
  family: string;
  requested_count: number;
  updated_count: number;
  updated_at: string;
}

export interface TipTrackingResetResult {
  family: string;
  updated_count: number;
  updated_at: string;
}

export interface CytomatRowState {
  cytomat_pos: string;
  plate_id: string;
}

export interface CytomatSnapshot {
  rows: CytomatRowState[];
  plate_options: string[];
  auto_refresh_ms: number;
  permissions: TipTrackingPermissions;
  refreshed_at: string;
}

export interface CytomatUpdate {
  cytomat_pos: string;
  plate_id: string;
}

export interface CytomatUpdateResult {
  requested_count: number;
  updated_count: number;
  updated_at: string;
}

const unwrapData = <T>(response: any): T => {
  return (response?.data?.data ?? response?.data) as T;
};

export const labwareApi = {
  getTipTrackingSnapshot: async (): Promise<TipTrackingSnapshot> => {
    const response = await api.get('/api/labware/tip-tracking');
    return unwrapData<TipTrackingSnapshot>(response);
  },

  updateTipTracking: async (family: string, updates: TipTrackingUpdate[]): Promise<TipTrackingUpdateResult> => {
    const response = await api.put('/api/labware/tip-tracking', {
      family,
      updates,
    });
    return unwrapData<TipTrackingUpdateResult>(response);
  },

  resetTipTracking: async (family: string): Promise<TipTrackingResetResult> => {
    const response = await api.post('/api/labware/tip-tracking/reset', { family });
    return unwrapData<TipTrackingResetResult>(response);
  },

  getCytomatSnapshot: async (): Promise<CytomatSnapshot> => {
    const response = await api.get('/api/labware/cytomat');
    return unwrapData<CytomatSnapshot>(response);
  },

  updateCytomat: async (updates: CytomatUpdate[]): Promise<CytomatUpdateResult> => {
    const response = await api.put('/api/labware/cytomat', { updates });
    return unwrapData<CytomatUpdateResult>(response);
  },
};
