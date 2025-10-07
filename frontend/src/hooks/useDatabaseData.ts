/**
 * useDatabaseData Hook - Specialized hook for database operations
 * 
 * Demonstrates integration of shared hooks (useApi, useErrorHandling) 
 * with domain-specific logic for database table management
 */

import { useState, useCallback, useEffect } from 'react';
import { useApi, useLocalStorage } from './index';
import { databaseAPI } from '../services/api';

export interface TableInfo {
  name: string;
  schema: string;
  row_count: number;
  is_important?: boolean;
}

export interface ConnectionStatus {
  connected: boolean;
  database: string;
  server: string;
  mode: string;
}

export interface DatabaseData {
  tables: TableInfo[];
  connectionStatus: ConnectionStatus | null;
  tableStats: {
    importantCount: number;
    allCount: number;
  };
}

export interface UseDatabaseDataOptions {
  /** Auto-refresh interval in milliseconds */
  autoRefreshInterval?: number;
  /** Initially show only important tables */
  initialShowImportantOnly?: boolean;
  /** Enable persistent preferences */
  persistPreferences?: boolean;
}

/**
 * Hook for managing database table data with integrated shared logic
 */
export const useDatabaseData = (options: UseDatabaseDataOptions = {}) => {
  const {
    autoRefreshInterval = 0,
    initialShowImportantOnly = true,
    persistPreferences = true
  } = options;

  // Use shared hooks for consistent patterns
  const databaseApi = useApi<DatabaseData>({
    initialData: {
      tables: [],
      connectionStatus: null,
      tableStats: { importantCount: 0, allCount: 0 }
    },
    retryOnError: true,
    maxRetries: 3
  });

  // Persistent user preference for important tables filter
  const [showImportantOnly, setShowImportantOnly] = useLocalStorage(
    'show_important_tables_only',
    {
      defaultValue: initialShowImportantOnly,
      syncAcrossTabs: true
    }
  );

  // Selected table state (could also be persisted if needed)
  const [selectedTable, setSelectedTable] = useState<string | null>(null);

  // Load database tables and status
  const loadDatabaseData = useCallback(async () => {
    return databaseApi.execute(async () => {
      // Load tables and connection status in parallel
      const [tablesResponse, statusResponse] = await Promise.all([
        databaseAPI.getTables(showImportantOnly),
        databaseAPI.getStatus()
      ]);
      
      // Process tables data
      const tableDetails = tablesResponse.data.data.table_details || [];
      const tables: TableInfo[] = tableDetails.map((table: any) => ({
        name: table.name,
        schema: 'dbo',
        row_count: table.has_data ? 1000 : 0,
        is_important: table.is_important || false
      }));

      // Process connection status
      const statusData = statusResponse.data;
      const connectionStatus: ConnectionStatus | null = statusData ? {
        connected: Boolean(statusData.is_connected) === true,
        database: statusData.database_name || 'Unknown',
        server: statusData.server_name || 'Unknown', 
        mode: statusData.mode || 'unknown'
      } : null;

      // Calculate table statistics
      const tableStats = {
        importantCount: tablesResponse.data.data.important_count || 0,
        allCount: tablesResponse.data.data.all_count || 0
      };

      return {
        tables,
        connectionStatus,
        tableStats
      };
    });
  }, [showImportantOnly, databaseApi]);

  // Effect to load data when filter changes
  useEffect(() => {
    loadDatabaseData();
  }, [loadDatabaseData]);

  // Auto-refresh functionality
  useEffect(() => {
    if (autoRefreshInterval <= 0) return;

    const interval = setInterval(loadDatabaseData, autoRefreshInterval);
    return () => clearInterval(interval);
  }, [loadDatabaseData, autoRefreshInterval]);

  // Handle table selection with error clearing
  const handleTableSelect = useCallback((tableName: string) => {
    setSelectedTable(tableName);
    databaseApi.clearError(); // Clear any previous errors
  }, [databaseApi]);

  // Toggle important tables filter
  const toggleImportantFilter = useCallback((value: boolean) => {
    setShowImportantOnly(value);
  }, [setShowImportantOnly]);

  return {
    // Data state
    tables: databaseApi.data?.tables || [],
    connectionStatus: databaseApi.data?.connectionStatus || null,
    tableStats: databaseApi.data?.tableStats || { importantCount: 0, allCount: 0 },
    selectedTable,
    
    // UI state
    loading: databaseApi.loading,
    error: databaseApi.error,
    showImportantOnly,
    
    // Actions
    loadDatabaseData,
    handleTableSelect,
    setSelectedTable,
    toggleImportantFilter,
    clearError: databaseApi.clearError,
    retry: () => loadDatabaseData(),
    
    // Computed values
    hasData: (databaseApi.data?.tables?.length || 0) > 0,
    isConnected: databaseApi.data?.connectionStatus?.connected || false
  };
};

/**
 * Simplified hook for just loading table list
 */
export const useTableList = (showImportantOnly: boolean = true) => {
  const tableApi = useApi<TableInfo[]>({
    initialData: [],
    retryOnError: true
  });

  const loadTables = useCallback(async () => {
    return tableApi.execute(async () => {
      const response = await databaseAPI.getTables(showImportantOnly);
      const tableDetails = response.data.data.table_details || [];
      
      return tableDetails.map((table: any) => ({
        name: table.name,
        schema: 'dbo',
        row_count: table.has_data ? 1000 : 0,
        is_important: table.is_important || false
      }));
    });
  }, [showImportantOnly, tableApi]);

  useEffect(() => {
    loadTables();
  }, [loadTables]);

  return {
    tables: tableApi.data || [],
    loading: tableApi.loading,
    error: tableApi.error,
    loadTables,
    clearError: tableApi.clearError
  };
};