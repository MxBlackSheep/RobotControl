import { useEffect, useState } from 'react';
import {
  MaintenanceState,
  subscribeToMaintenance,
  getMaintenanceRemainingMs,
} from '@/utils/MaintenanceManager';

interface MaintenanceHookState {
  active: boolean;
  remainingMs: number;
  reason?: string;
}

const mapState = (state: MaintenanceState): MaintenanceHookState => ({
  active: state.active,
  remainingMs: state.active ? getMaintenanceRemainingMs() : 0,
  reason: state.reason,
});

export const useMaintenanceMode = (): MaintenanceHookState => {
  const [maintenanceState, setMaintenanceState] = useState<MaintenanceHookState>(
    mapState({ active: false }),
  );

  useEffect(() => {
    const unsubscribe = subscribeToMaintenance((state) => {
      setMaintenanceState(mapState(state));
    });
    return () => unsubscribe();
  }, []);

  return maintenanceState;
};
