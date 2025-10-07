/**
 * VirtualizedTable Component for PyRobot Optimization
 * 
 * High-performance table component using custom virtualization
 * Handles large datasets efficiently without performance degradation
 * Compatible with existing DatabaseTable props and Material-UI styling
 */

import React, { useState, useMemo, useCallback, useEffect, useRef } from 'react';

// Optimized Material-UI imports for better tree-shaking
import Box from '@mui/material/Box';
import Paper from '@mui/material/Paper';
import Table from '@mui/material/Table';
import TableBody from '@mui/material/TableBody';
import TableCell from '@mui/material/TableCell';
import TableContainer from '@mui/material/TableContainer';
import TableHead from '@mui/material/TableHead';
import TableRow from '@mui/material/TableRow';
import Typography from '@mui/material/Typography';
import IconButton from '@mui/material/IconButton';
import Tooltip from '@mui/material/Tooltip';
import { styled } from '@mui/material/styles';
import {
  Sort as SortIcon,
  Visibility as ViewIcon
} from '@mui/icons-material';

// Shared components
import LoadingSpinner from './LoadingSpinner';
import ErrorAlert from './ErrorAlert';

// Props interface compatible with existing table components
export interface VirtualizedTableProps<T = any> {
  data: T[];
  columns: Array<{
    key: string;
    label: string;
    width?: number;
    align?: 'left' | 'center' | 'right';
    render?: (value: any, row: T, rowIndex: number) => React.ReactNode;
  }>;
  rowHeight?: number;
  height?: number;
  loading?: boolean;
  error?: string;
  onRowClick?: (row: T, index: number) => void;
  onCellClick?: (value: any, column: string, row: T, rowIndex: number) => void;
  onSort?: (columnKey: string) => void;
  sortColumn?: string;
  sortDirection?: 'asc' | 'desc';
  stickyHeader?: boolean;
  className?: string;
  overscanCount?: number;
}

// Styled components for better performance
const StyledTableContainer = styled(TableContainer)(({ theme }) => ({
  '& .MuiTable-root': {
    tableLayout: 'fixed',
  },
  '& .virtualized-row': {
    display: 'flex',
    alignItems: 'center',
    borderBottom: `1px solid ${theme.palette.divider}`,
    '&:hover': {
      backgroundColor: theme.palette.action.hover,
    },
  },
  '& .virtualized-cell': {
    padding: theme.spacing(1),
    overflow: 'hidden',
    textOverflow: 'ellipsis',
    whiteSpace: 'nowrap',
    borderRight: `1px solid ${theme.palette.divider}`,
    '&:last-child': {
      borderRight: 'none',
    },
  },
}));

// Custom hook for virtualization logic
const useVirtualization = (
  itemCount: number,
  itemHeight: number,
  containerHeight: number
) => {
  const [scrollTop, setScrollTop] = useState(0);
  
  const visibleStart = Math.floor(scrollTop / itemHeight);
  const visibleEnd = Math.min(
    itemCount - 1,
    Math.floor((scrollTop + containerHeight) / itemHeight)
  );
  
  const overscan = 5;
  const startIndex = Math.max(0, visibleStart - overscan);
  const endIndex = Math.min(itemCount - 1, visibleEnd + overscan);
  
  const visibleItems = [];
  for (let i = startIndex; i <= endIndex; i++) {
    visibleItems.push(i);
  }
  
  return {
    visibleItems,
    totalHeight: itemCount * itemHeight,
    offsetY: startIndex * itemHeight,
    setScrollTop,
  };
};

const VirtualizedTable = <T extends Record<string, any>>({
  data,
  columns,
  rowHeight = 48,
  height = 400,
  loading = false,
  error,
  onRowClick,
  onCellClick,
  onSort,
  sortColumn,
  sortDirection = 'asc',
  stickyHeader = true,
  className,
  overscanCount = 5,
}: VirtualizedTableProps<T>) => {
  const containerRef = useRef<HTMLDivElement>(null);
  
  // Calculate column widths if not specified
  const processedColumns = useMemo(() => {
    const totalSpecifiedWidth = columns.reduce((sum, col) => sum + (col.width || 0), 0);
    const unspecifiedColumns = columns.filter(col => !col.width).length;
    const remainingWidth = unspecifiedColumns > 0 ? 
      (100 - totalSpecifiedWidth) / unspecifiedColumns : 0;

    return columns.map(col => ({
      ...col,
      width: col.width || Math.max(remainingWidth, 10), // Minimum 10% width
    }));
  }, [columns]);

  // Virtualization logic
  const tableBodyHeight = height - 56; // Subtract header height
  const { visibleItems, totalHeight, offsetY, setScrollTop } = useVirtualization(
    data.length,
    rowHeight,
    tableBodyHeight
  );

  // Handle scroll events
  const handleScroll = useCallback((e: React.UIEvent<HTMLDivElement>) => {
    setScrollTop(e.currentTarget.scrollTop);
  }, [setScrollTop]);

  // Handle sort click
  const handleSortClick = useCallback((columnKey: string) => {
    onSort?.(columnKey);
  }, [onSort]);

  // Handle row click
  const handleRowClick = useCallback((row: T, index: number) => {
    onRowClick?.(row, index);
  }, [onRowClick]);

  // Handle cell click
  const handleCellClick = useCallback((value: any, columnKey: string, row: T, index: number) => {
    onCellClick?.(value, columnKey, row, index);
  }, [onCellClick]);

  if (loading) {
    return (
      <Paper className={className}>
        <Box sx={{ height: height }}>
          <LoadingSpinner
            variant="fullscreen"
            message="Loading table data..."
            size="large"
          />
        </Box>
      </Paper>
    );
  }

  if (error) {
    return (
      <Paper className={className}>
        <Box sx={{ p: 2 }}>
          <ErrorAlert
            message={error}
            severity="error"
            category="server"
            retryable={false}
          />
        </Box>
      </Paper>
    );
  }

  if (!data || data.length === 0) {
    return (
      <Paper className={className}>
        <Box sx={{ 
          display: 'flex', 
          justifyContent: 'center', 
          alignItems: 'center',
          height: height,
          flexDirection: 'column'
        }}>
          <Typography variant="h6" color="textSecondary">
            No data to display
          </Typography>
          <Typography variant="body2" color="textSecondary">
            The table is empty or no data matches your current filters.
          </Typography>
        </Box>
      </Paper>
    );
  }

  return (
    <Paper className={className}>
      <StyledTableContainer>
        {/* Table Header */}
        <Table 
          stickyHeader={stickyHeader} 
          size="small"
          role="table"
          aria-label="Virtualized data table"
        >
          <TableHead role="rowgroup">
            <TableRow role="row">
              {processedColumns.map((column) => (
                <TableCell 
                  key={column.key}
                  align={column.align}
                  style={{ width: `${column.width}%` }}
                  sortDirection={sortColumn === column.key ? sortDirection : false}
                  role="columnheader"
                  scope="col"
                  aria-sort={
                    sortColumn === column.key
                      ? sortDirection === 'asc' ? 'ascending' : 'descending'
                      : 'none'
                  }
                >
                  <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                    <Typography variant="subtitle2" sx={{ fontWeight: 'bold' }}>
                      {column.label}
                    </Typography>
                    {onSort && (
                      <Tooltip title={`Sort by ${column.label}`}>
                        <IconButton
                          size="small"
                          onClick={() => handleSortClick(column.key)}
                          color={sortColumn === column.key ? 'primary' : 'default'}
                          aria-label={`Sort by ${column.label} ${sortColumn === column.key && sortDirection === 'asc' ? 'descending' : 'ascending'}`}
                        >
                          <SortIcon fontSize="small" />
                        </IconButton>
                      </Tooltip>
                    )}
                  </Box>
                </TableCell>
              ))}
            </TableRow>
          </TableHead>
        </Table>

        {/* Virtualized Table Body */}
        <Box 
          ref={containerRef}
          sx={{ 
            height: tableBodyHeight,
            overflow: 'auto',
            position: 'relative'
          }}
          onScroll={handleScroll}
        >
          {/* Spacer to maintain scroll height */}
          <div style={{ height: totalHeight, width: '100%', position: 'relative' }}>
            {/* Visible rows container */}
            <div style={{ 
              transform: `translateY(${offsetY}px)`,
              position: 'absolute',
              top: 0,
              left: 0,
              right: 0,
            }}>
              <Table size="small" role="table" aria-hidden="true">
                <TableBody role="rowgroup">
                  {visibleItems.map((index) => {
                    const row = data[index];
                    return (
                      <TableRow 
                        key={index}
                        hover
                        onClick={() => handleRowClick(row, index)}
                        sx={{ cursor: onRowClick ? 'pointer' : 'default' }}
                        role="row"
                        aria-rowindex={index + 1}
                      >
                        {processedColumns.map((column) => {
                          const value = row[column.key];
                          return (
                            <TableCell 
                              key={column.key}
                              align={column.align}
                              style={{ width: `${column.width}%` }}
                              onClick={(e) => {
                                e.stopPropagation();
                                handleCellClick(value, column.key, row, index);
                              }}
                              sx={{ cursor: onCellClick ? 'pointer' : 'default' }}
                              role="gridcell"
                              aria-describedby={`virtualized-cell-${index}-${column.key}`}
                            >
                              <Box sx={{ 
                                maxWidth: 200, 
                                overflow: 'hidden', 
                                textOverflow: 'ellipsis',
                                whiteSpace: 'nowrap'
                              }}>
                                {column.render ? (
                                  column.render(value, row, index)
                                ) : value !== null && value !== undefined ? (
                                  String(value)
                                ) : (
                                  <Typography variant="body2" color="textSecondary" fontStyle="italic">
                                    NULL
                                  </Typography>
                                )}
                              </Box>
                            </TableCell>
                          );
                        })}
                      </TableRow>
                    );
                  })}
                </TableBody>
              </Table>
            </div>
          </div>
        </Box>
      </StyledTableContainer>

      {/* Footer with row count */}
      <Box sx={{ 
        p: 1, 
        borderTop: 1, 
        borderColor: 'divider',
        display: 'flex',
        justifyContent: 'space-between',
        alignItems: 'center',
        backgroundColor: 'background.default'
      }}>
        <Typography variant="caption" color="textSecondary">
          {data.length} row{data.length !== 1 ? 's' : ''} displayed
        </Typography>
        <Typography variant="caption" color="textSecondary">
          Virtualized for optimal performance
        </Typography>
      </Box>
    </Paper>
  );
};

// Export helper function to convert DatabaseTable data format to VirtualizedTable format
export const convertDatabaseTableData = (
  tableData: {
    columns: string[];
    data: any[][];
    total_rows: number;
  }
) => {
  const columns = tableData.columns.map(col => ({
    key: col,
    label: col,
    width: 100 / tableData.columns.length,
  }));

  const data = tableData.data.map(row => {
    const rowObj: Record<string, any> = {};
    tableData.columns.forEach((col, index) => {
      rowObj[col] = row[index];
    });
    return rowObj;
  });

  return { columns, data };
};

// Export performance thresholds for when to use virtualized table
export const VIRTUALIZATION_THRESHOLD = {
  ROW_COUNT: 100, // Use virtualized table when more than 100 rows
  ESTIMATED_HEIGHT: 5000, // Use virtualized table when estimated table height > 5000px
};

export default VirtualizedTable;