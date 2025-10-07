/**
 * Types Index - Centralized export for all TypeScript types
 * 
 * Provides easy access to all type definitions with consistent imports
 */

// Export all component types
export * from './components';

// Export existing domain-specific types
export * from './backup';
export * from './scheduling';

// Re-export commonly used component namespace types for convenience
export type {
  // Base types
  BaseComponentProps,
  LoadingComponentProps,
  ErrorComponentProps,
  AsyncComponentProps,
  
  // Event handlers
  ClickHandler,
  ChangeHandler,
  SubmitHandler,
  ValidationHandler,
  AsyncOperation,
  AsyncOperationWithData,
  
  // API types
  ApiResponse,
  ListResponse,
  ValidationResult,
  ValidationSchema,
  
  // Common unions
  ComponentSize,
  ComponentVariant,
  ComponentColor,
  ComponentStatus,
  SortDirection,
  UserRole,
  DatabaseMode,
  CameraStatus,
  ScheduleStatus,
  ExecutionStatus,
  Priority
} from './components';

// Export namespaced types for easier access
export type {
  Database,
  Camera,
  Scheduling,
  Auth,
  Monitoring,
  DatabaseComponents,
  CameraComponents,
  SchedulingComponents,
  FormComponents,
  LayoutComponents,
  SharedComponents
} from './components';