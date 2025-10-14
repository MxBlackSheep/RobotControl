# RobotControl Custom Hooks

This directory contains custom React hooks that provide shared logic and consistent patterns across the RobotControl application.

## Core Hooks

### `useApi` - API Call Management
Provides standardized loading, error, and success states for API calls.

```typescript
import { useApi } from './hooks';

const MyComponent = () => {
  const api = useApi({
    retryOnError: true,
    maxRetries: 3,
    errorTimeout: 5000
  });

  const loadData = async () => {
    const result = await api.execute(() => myAPI.getData());
    if (result) {
      // Handle success
    }
  };

  return (
    <div>
      {api.loading && <LoadingSpinner />}
      {api.error && <ErrorAlert message={api.error} onRetry={loadData} />}
      {api.data && <div>{JSON.stringify(api.data)}</div>}
    </div>
  );
};
```

### `useLocalStorage` - Persistent State
Synchronizes React state with localStorage for user preferences.

```typescript
import { useLocalStorage, useUserPreferences } from './hooks';

const SettingsComponent = () => {
  const [theme, setTheme] = useLocalStorage('theme', {
    defaultValue: 'light',
    syncAcrossTabs: true
  });
  
  // Or use predefined preferences
  const { preferences, updatePreference } = useUserPreferences();

  return (
    <div>
      <select value={theme} onChange={(e) => setTheme(e.target.value)}>
        <option value="light">Light</option>
        <option value="dark">Dark</option>
      </select>
    </div>
  );
};
```

### `useErrorHandling` - Error Management
Centralized error handling with categorization and user-friendly messaging.

```typescript
import { useErrorHandling } from './hooks';

const DataComponent = () => {
  const errorHandler = useErrorHandling({
    contextPrefix: 'Data Loading',
    autoCategorize: true
  });

  const loadData = async () => {
    try {
      await api.getData();
    } catch (error) {
      errorHandler.handleError(error, 'Failed to load user data');
    }
  };

  return (
    <div>
      {errorHandler.currentError && (
        <ErrorAlert
          {...errorHandler.currentError}
          onRetry={errorHandler.hasRetryableError ? loadData : undefined}
          onClose={errorHandler.clearError}
        />
      )}
    </div>
  );
};
```

### `useFormHandling` - Form Management
Comprehensive form state management with validation.

```typescript
import { useFormHandling } from './hooks';

const UserForm = () => {
  const form = useFormHandling({
    initialValues: { name: '', email: '' },
    validators: {
      email: (value) => /^[^@]+@[^@]+$/.test(value) ? null : 'Invalid email'
    },
    requiredFields: ['name', 'email'],
    onSubmit: async (values) => {
      await api.createUser(values);
    }
  });

  return (
    <form onSubmit={(e) => { e.preventDefault(); form.submitForm(); }}>
      <TextField
        {...form.getFieldProps('name')}
        label="Name"
      />
      <TextField
        {...form.getFieldProps('email')}
        label="Email"
        type="email"
      />
      <Button 
        type="submit" 
        disabled={!form.isValid || form.isSubmitting}
      >
        {form.isSubmitting ? 'Saving...' : 'Save'}
      </Button>
    </form>
  );
};
```

### `usePerformance` - Performance Monitoring
Development-time performance tracking and optimization helpers.

```typescript
import { usePerformance, useDebounce } from './hooks';

const OptimizedComponent = () => {
  const metrics = usePerformance({
    componentName: 'OptimizedComponent',
    renderTimeWarning: 50
  });
  
  const [searchTerm, setSearchTerm] = useState('');
  const debouncedSearch = useDebounce(searchTerm, 300);

  useEffect(() => {
    if (debouncedSearch) {
      performSearch(debouncedSearch);
    }
  }, [debouncedSearch]);

  return (
    <div>
      <input onChange={(e) => setSearchTerm(e.target.value)} />
      <div>Renders: {metrics.renderCount}</div>
    </div>
  );
};
```

## Domain-Specific Hooks

### `useDatabaseData` - Database Operations
Specialized hook combining API calls with database-specific logic.

```typescript
import { useDatabaseData } from './hooks';

const DatabasePage = () => {
  const {
    tables,
    connectionStatus,
    loading,
    error,
    selectedTable,
    showImportantOnly,
    handleTableSelect,
    toggleImportantFilter,
    retry
  } = useDatabaseData({
    autoRefreshInterval: 30000,
    persistPreferences: true
  });

  return (
    <div>
      <Switch
        checked={showImportantOnly}
        onChange={(e) => toggleImportantFilter(e.target.checked)}
      />
      {loading && <PageLoading />}
      {error && <ServerError message={error} onRetry={retry} />}
      <TableList tables={tables} onSelect={handleTableSelect} />
    </div>
  );
};
```

## Hook Composition Patterns

### Combining Multiple Hooks
```typescript
const ComplexComponent = () => {
  // Error handling
  const errorHandler = useErrorHandling({ contextPrefix: 'Complex Component' });
  
  // API with error integration
  const api = useApi({
    retryOnError: true,
    onError: errorHandler.handleError
  });
  
  // Persistent preferences
  const [preferences, setPreferences] = useLocalStorage('component_prefs', {
    defaultValue: { viewMode: 'grid', sortBy: 'name' }
  });
  
  // Performance monitoring
  const metrics = usePerformance({ componentName: 'ComplexComponent' });
  
  // Form handling
  const searchForm = useSearchForm(
    { query: '', filters: [] },
    (values) => api.execute(() => searchAPI.search(values))
  );

  return (
    <div>
      {/* Component implementation using all hooks */}
    </div>
  );
};
```

## Best Practices

1. **Use TypeScript**: All hooks are fully typed for better development experience
2. **Error Boundaries**: Combine with React error boundaries for comprehensive error handling
3. **Performance**: Use performance hooks in development to identify bottlenecks
4. **Consistent Patterns**: Prefer shared hooks over custom component-specific logic
5. **Composition**: Combine multiple hooks for complex functionality
6. **Testing**: Hooks can be tested independently using React Testing Library

## Testing

```typescript
import { renderHook, act } from '@testing-library/react';
import { useApi } from './useApi';

test('useApi handles successful API calls', async () => {
  const { result } = renderHook(() => useApi());
  
  await act(async () => {
    await result.current.execute(() => Promise.resolve('test data'));
  });
  
  expect(result.current.data).toBe('test data');
  expect(result.current.loading).toBe(false);
  expect(result.current.error).toBe(null);
});
```

## Migration Guide

When migrating existing components to use shared hooks:

1. **Identify Patterns**: Look for repeated useState/useEffect patterns
2. **Start Small**: Begin with one hook (usually useApi or useLocalStorage)
3. **Test Thoroughly**: Ensure existing functionality is preserved
4. **Gradual Migration**: Update components incrementally
5. **Document Changes**: Update component documentation

For questions or suggestions, please refer to the RobotControl development guidelines.