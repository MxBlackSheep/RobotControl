/**
 * Custom Hooks Index - Centralized export for all PyRobot custom hooks
 * 
 * Provides easy access to all shared logic hooks with consistent imports
 */

// API and data fetching hooks
export {
  useApi,
  useApiList,
  usePaginatedApi,
  type ApiState,
  type UseApiOptions,
  type UseApiReturn
} from './useApi';

// Error handling hooks
export {
  useErrorHandling,
  useApiErrorHandling,
  useGlobalErrorHandler,
  type ErrorInfo,
  type UseErrorHandlingOptions
} from './useErrorHandling';

// Form handling hooks
export {
  useFormHandling,
  useSimpleForm,
  useSearchForm,
  type FormField,
  type FormState,
  type UseFormOptions
} from './useFormHandling';

// Local storage and preferences hooks
export {
  useLocalStorage,
  useLocalStorageBoolean,
  useLocalStorageString,
  useLocalStorageNumber,
  useUserPreferences,
  type UseLocalStorageOptions,
  type UserPreferences
} from './useLocalStorage';

// Performance monitoring hooks
export {
  usePerformance,
  useAsyncPerformance,
  useMemoryMonitor,
  useDebounce,
  useThrottle,
  useLifecyclePerformance,
  usePerformanceProfiler,
  type PerformanceMetrics,
  type UsePerformanceOptions
} from './usePerformance';

// Domain-specific hooks
export {
  useDatabaseData,
  useTableList,
  type TableInfo,
  type ConnectionStatus,
  type DatabaseData,
  type UseDatabaseDataOptions
} from './useDatabaseData';

// Existing specialized hooks
export {
  useIntelligentStatusMonitor
} from './useIntelligentStatusMonitor';

export {
  useKeyboardNavigation
} from './useKeyboardNavigation';

export {
  useModalFocus
} from './useModalFocus';

export {
  useMonitoring,
  type ExperimentData,
  type SystemHealth,
  type DatabaseStatus,
  type MonitoringData
} from './useMonitoring';

export {
  useScheduling
} from './useScheduling';