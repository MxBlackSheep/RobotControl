/**
 * TypedDatabaseTable - Example of comprehensive TypeScript usage
 * 
 * Demonstrates how to use the new type system with runtime validation
 * This is an example implementation showing best practices
 */

import React, { useCallback } from 'react';
import { DatabaseComponents, Database, type ValidationSchema } from '../types';
import { withPropValidation } from '../utils/withPropValidation';
import { ValidationSchemas } from '../utils/validation';
import VirtualizedTable from './VirtualizedTable';

// Define component props using the centralized types
interface TypedDatabaseTableProps extends DatabaseComponents.DatabaseTableProps {
  // Additional props specific to this implementation
  enableSearch?: boolean;
  searchPlaceholder?: string;
  onExport?: (format: 'csv' | 'json' | 'excel') => void;
  exportFormats?: Array<'csv' | 'json' | 'excel'>;
}

// Runtime validation schema
const databaseTableSchema: ValidationSchema<TypedDatabaseTableProps> = {
  tableName: {
    required: true,
    type: 'string' as const,
    minLength: 1,
    maxLength: 100
  },
  loading: {
    required: false,
    type: 'boolean' as const
  },
  error: {
    required: false,
    type: 'string' as const
  },
  maxHeight: {
    required: false,
    custom: (value: string | number) => {
      if (typeof value === 'string' && !/^\d+(px|%|vh|rem|em)$/.test(value)) {
        return 'maxHeight must be a valid CSS height value';
      }
      if (typeof value === 'number' && value < 0) {
        return 'maxHeight must be positive';
      }
      return null;
    }
  },
  pageSize: {
    required: false,
    type: 'number' as const,
    min: 10,
    max: 1000
  },
  onRowClick: {
    required: false,
    type: 'function' as const
  },
  onCellClick: {
    required: false,
    type: 'function' as const
  }
};

// Component implementation with full type safety
const TypedDatabaseTableComponent: React.FC<TypedDatabaseTableProps> = ({
  tableName,
  loading = false,
  error = null,
  maxHeight = '500px',
  onRowClick,
  onCellClick,
  onExport,
  exportFormats = ['csv', 'json'],
  className,
  sx: _sx,
}) => {
  // Example of using typed event handlers
  const handleRowClick = useCallback<NonNullable<TypedDatabaseTableProps['onRowClick']>>(
    (row, index) => {
      console.log('Row clicked:', { tableName, row, index });
      onRowClick?.(row, index);
    },
    [tableName, onRowClick]
  );

  const handleCellClick = useCallback<NonNullable<TypedDatabaseTableProps['onCellClick']>>(
    (value, column, row, index) => {
      console.log('Cell clicked:', { tableName, value, column, row, index });
      onCellClick?.(value, column, row, index);
    },
    [tableName, onCellClick]
  );

  const handleExport = useCallback((format: 'csv' | 'json' | 'excel') => {
    console.log('Exporting table:', { tableName, format });
    onExport?.(format);
  }, [tableName, onExport]);

  // Example of type-safe data transformation
  const processTableData = useCallback((data: Database.TableData): Database.TableData => {
    return {
      ...data,
      data: data.data.map((row, index) => {
        // Add row index for identification
        return [...row, index];
      }),
      columns: [...data.columns, '_rowIndex']
    };
  }, []);

  // Mock data for demonstration (in real implementation, this would come from props or hooks)
  const mockColumns = [
    { key: 'id', label: 'ID', width: 10, align: 'right' as const },
    { key: 'name', label: 'Name', width: 30 },
    { key: 'status', label: 'Status', width: 20, render: (value: string) => (
      <span style={{ 
        color: value === 'active' ? 'green' : 'red',
        fontWeight: 'bold'
      }}>
        {value}
      </span>
    )},
    { key: 'created_at', label: 'Created', width: 25 },
    { key: 'actions', label: 'Actions', width: 15, align: 'center' as const }
  ];

  const mockData = [
    { id: 1, name: 'Test Item 1', status: 'active', created_at: '2024-01-01', actions: 'Edit' },
    { id: 2, name: 'Test Item 2', status: 'inactive', created_at: '2024-01-02', actions: 'Edit' }
  ];

  return (
    <VirtualizedTable
      data={mockData}
      columns={mockColumns}
      loading={loading}
      error={error}
      height={typeof maxHeight === 'number' ? maxHeight : undefined}
      onRowClick={handleRowClick}
      onCellClick={handleCellClick}
      className={className}
    />
  );
};

// Apply runtime validation HOC
const TypedDatabaseTable = withPropValidation(
  TypedDatabaseTableComponent,
  databaseTableSchema,
  {
    displayName: 'TypedDatabaseTable',
    strict: false // Only warn in development, don't throw errors
  }
);

// Export with proper TypeScript types
export default TypedDatabaseTable;

// Export types for consumers
export type { TypedDatabaseTableProps };

// Example of creating a specialized version with preset validation
export const StrictDatabaseTable = withPropValidation(
  TypedDatabaseTableComponent,
  {
    ...databaseTableSchema,
    tableName: {
      ...databaseTableSchema.tableName,
      pattern: /^[a-zA-Z][a-zA-Z0-9_]*$/ // Valid SQL table name pattern
    }
  },
  { displayName: 'StrictDatabaseTable', strict: true }
);

/**
 * Usage examples:
 * 
 * // Basic usage with type safety
 * <TypedDatabaseTable
 *   tableName="users"
 *   loading={isLoading}
 *   error={error}
 *   onRowClick={(row, index) => {
 *     // row and index are properly typed
 *   }}
 * />
 * 
 * // Advanced usage with all features
 * <TypedDatabaseTable
 *   tableName="experiments"
 *   loading={false}
 *   maxHeight="600px"
 *   pageSize={50}
 *   enableSearch={true}
 *   searchPlaceholder="Search experiments..."
 *   onExport={(format) => handleExport(format)}
 *   exportFormats={['csv', 'excel']}
 *   onRowClick={(row, index) => {
 *     navigate(`/experiment/${row.id}`);
 *   }}
 *   onCellClick={(value, column, row, index) => {
 *     if (column === 'actions') {
 *       showContextMenu(value, row);
 *     }
 *   }}
 * />
 */