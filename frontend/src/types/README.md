# RobotControl TypeScript Type System

This directory contains comprehensive TypeScript type definitions for all RobotControl components, providing type safety, better IntelliSense, and improved developer experience.

## Overview

The type system is organized into several key areas:

- **Component Interfaces**: Type definitions for all React component props
- **Data Models**: Types for data structures used throughout the application
- **Runtime Validation**: Tools for validating data at runtime
- **Utility Types**: Helper types for common patterns

## Core Files

### `components.ts`
Comprehensive type definitions organized by namespace:

- `BaseComponentProps`: Common props for all components
- `Database.*`: Database-related types and component props
- `Camera.*`: Camera system types and component props
- `Scheduling.*`: Scheduling system types and component props
- `Auth.*`: Authentication and user management types
- `SharedComponents.*`: Shared UI component props

### `index.ts`
Central export file providing easy access to all types with consistent imports.

### Validation Utilities

#### `utils/validation.ts`
Runtime validation tools that work with TypeScript interfaces:

```typescript
import { validateData, ValidationSchemas } from '../utils/validation';

// Validate user input
const result = validateData(userInput, ValidationSchemas.loginCredentials);
if (!result.isValid) {
  console.log('Errors:', result.errors);
}
```

#### `utils/withPropValidation.tsx`
Higher-order component for runtime prop validation:

```typescript
import { withPropValidation } from '../utils/withPropValidation';

const ValidatedComponent = withPropValidation(MyComponent, {
  title: { required: true, type: 'string', minLength: 1 },
  count: { required: true, type: 'number', min: 0 }
});
```

## Usage Patterns

### 1. Basic Component Props

```typescript
import { BaseComponentProps, AsyncComponentProps } from '../types';

interface MyComponentProps extends AsyncComponentProps {
  title: string;
  onSave: (data: any) => Promise<void>;
}

const MyComponent: React.FC<MyComponentProps> = ({
  title,
  loading,
  error,
  onSave,
  className,
  sx
}) => {
  // Component implementation
};
```

### 2. Using Namespaced Types

```typescript
import { Database, Camera } from '../types';

interface TableViewProps {
  tableInfo: Database.TableInfo;
  cameras: Camera.CameraInfo[];
  onTableSelect: (table: Database.TableInfo) => void;
}
```

### 3. API Response Handling

```typescript
import { ApiResponse, ListResponse } from '../types';

// Single item response
const handleUserResponse = (response: ApiResponse<Auth.User>) => {
  if (response.success && response.data) {
    console.log('User:', response.data.username);
  }
};

// List response with pagination
const handleUsersResponse = (response: ListResponse<Auth.User>) => {
  if (response.success && response.data) {
    console.log('Users:', response.data.length);
    console.log('Total:', response.metadata.total);
  }
};
```

### 4. Form Validation

```typescript
import { ValidationSchemas, validateData } from '../utils/validation';

const handleFormSubmit = (formData: any) => {
  const validation = validateData(formData, ValidationSchemas.scheduleForm);
  
  if (!validation.isValid) {
    setErrors(validation.errors);
    return;
  }
  
  // Submit valid data
  submitSchedule(formData);
};
```

### 5. Runtime Prop Validation

```typescript
import { withPropValidation } from '../utils/withPropValidation';

const schema = {
  data: { required: true, type: 'array' as const },
  onItemClick: { required: true, type: 'function' as const },
  pageSize: { 
    required: false, 
    type: 'number' as const, 
    min: 1, 
    max: 100 
  }
};

const ValidatedList = withPropValidation(MyList, schema, {
  displayName: 'MyList',
  strict: false // Only warn in development
});
```

### 6. Custom Hook Types

```typescript
import { Database, AsyncComponentProps } from '../types';

interface UseDatabaseOptions {
  autoRefresh?: boolean;
  refreshInterval?: number;
}

interface UseDatabaseReturn extends Pick<AsyncComponentProps, 'loading' | 'error'> {
  tables: Database.TableInfo[];
  connectionStatus: Database.ConnectionStatus | null;
  refresh: () => Promise<void>;
}

function useDatabase(options: UseDatabaseOptions = {}): UseDatabaseReturn {
  // Hook implementation
}
```

## Type Safety Best Practices

### 1. Always Use Interfaces for Component Props

```typescript
// Good: Clear interface definition
interface ButtonProps extends BaseComponentProps {
  variant: 'text' | 'outlined' | 'contained';
  disabled?: boolean;
  onClick: () => void;
}

// Avoid: Inline prop types
const Button: React.FC<{
  variant: string;
  disabled?: boolean;
  onClick: () => void;
}> = ({ variant, disabled, onClick }) => {
  // Implementation
};
```

### 2. Use Namespaces for Related Types

```typescript
// Good: Organized in namespace
import { Database } from '../types';

const processTable = (table: Database.TableInfo) => {
  // Implementation
};

// Avoid: Importing many individual types
import { TableInfo, ConnectionStatus, TableData } from '../types';
```

### 3. Leverage Union Types for State

```typescript
// Good: Clear state possibilities
type LoadingState = 'idle' | 'loading' | 'success' | 'error';

interface ComponentState {
  status: LoadingState;
  data: any[] | null;
  error: string | null;
}
```

### 4. Use Generic Types for Reusable Components

```typescript
interface DataListProps<T> extends BaseComponentProps {
  items: T[];
  renderItem: (item: T, index: number) => React.ReactNode;
  onItemSelect: (item: T) => void;
}

const DataList = <T,>({ items, renderItem, onItemSelect }: DataListProps<T>) => {
  // Generic implementation
};
```

### 5. Validate Critical Data at Runtime

```typescript
// For user inputs and API responses
const validateApiResponse = (response: unknown): response is ApiResponse => {
  return typeof response === 'object' &&
         response !== null &&
         'success' in response &&
         typeof response.success === 'boolean';
};

const handleApiCall = async () => {
  const response = await fetch('/api/data');
  const data = await response.json();
  
  if (!validateApiResponse(data)) {
    throw new Error('Invalid API response format');
  }
  
  // data is now properly typed
  if (data.success && data.data) {
    processData(data.data);
  }
};
```

## Migration Guide

### From Existing Components

1. **Identify Component Purpose**: Determine which namespace your component belongs to
2. **Add Type Imports**: Import relevant types from the types directory
3. **Define Props Interface**: Create a comprehensive interface extending base props
4. **Add Runtime Validation**: Use validation utilities for critical props
5. **Update Event Handlers**: Use typed event handler types

### Example Migration

```typescript
// Before: Untyped component
const MyComponent = ({ data, onSave, loading }) => {
  // Implementation
};

// After: Fully typed component
import { AsyncComponentProps, Database } from '../types';
import { withPropValidation } from '../utils/withPropValidation';

interface MyComponentProps extends AsyncComponentProps {
  data: Database.TableInfo[];
  onSave: (data: Database.TableInfo) => Promise<void>;
}

const schema = {
  data: { required: true, type: 'array' as const },
  onSave: { required: true, type: 'function' as const }
};

const MyComponentImpl: React.FC<MyComponentProps> = ({
  data,
  onSave,
  loading,
  error,
  className,
  sx
}) => {
  // Implementation with full type safety
};

const MyComponent = withPropValidation(MyComponentImpl, schema);

export default MyComponent;
```

## IDE Configuration

### VSCode Settings

Add to `.vscode/settings.json`:

```json
{
  "typescript.preferences.includePackageJsonAutoImports": "on",
  "typescript.suggest.autoImports": true,
  "typescript.suggest.enabled": true,
  "editor.codeActionsOnSave": {
    "source.organizeImports": true,
    "source.fixAll.eslint": true
  }
}
```

### IntelliSense Tips

- Use Ctrl/Cmd + Space for auto-completion
- Hover over types to see full definitions
- Use Go to Definition (F12) to navigate to type sources
- Enable strict TypeScript mode for maximum type safety

## Testing Types

```typescript
import { expectType } from 'tsd';
import { Database } from '../types';

// Test type constraints
expectType<Database.TableInfo>({
  name: 'test_table',
  schema: 'dbo',
  row_count: 100,
  is_important: true
});

// Test component props
expectType<MyComponentProps>({
  data: [],
  onSave: async (data) => {},
  loading: false
});
```

This type system provides a foundation for scalable, maintainable TypeScript code across the entire RobotControl application.