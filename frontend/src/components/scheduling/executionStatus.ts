import type { StatusTone } from '../../theme';

/** Scheduler execution statuses in the shared status colours (Overview and History). */
export const executionTone = (status: string): [string, StatusTone] => {
  const value = status.toLowerCase();
  switch (value) {
    case 'completed': case 'success': return ['Completed', 'completed'];
    case 'failed': case 'error': return ['Failed', 'fault'];
    case 'running': case 'executing': return ['Running', 'running'];
    case 'recovery_required': return ['Recovery required', 'attention'];
    default: return [value ? value.charAt(0).toUpperCase() + value.slice(1).replace(/_/g, ' ') : 'Unknown', 'neutral'];
  }
};
