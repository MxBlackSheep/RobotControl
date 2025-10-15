/**
 * Enhanced Database Table Component for RobotControl Simplified Architecture
 * 
 * Features:
 * - Advanced filtering and search
 * - Pagination with configurable page sizes
 * - Data export capabilities (CSV, JSON)
 * - Column sorting and management
 * - Real-time data refresh
 * - Cell value inspection
 */

import React, { useState, useEffect, useMemo } from 'react';

// Optimized Material-UI imports for better tree-shaking
import Box from '@mui/material/Box';
import Paper from '@mui/material/Paper';
import Table from '@mui/material/Table';
import TableBody from '@mui/material/TableBody';
import TableCell from '@mui/material/TableCell';
import TableContainer from '@mui/material/TableContainer';
import TableHead from '@mui/material/TableHead';
import TableRow from '@mui/material/TableRow';
import TablePagination from '@mui/material/TablePagination';
import TextField from '@mui/material/TextField';
import Button from '@mui/material/Button';
import IconButton from '@mui/material/IconButton';
import Tooltip from '@mui/material/Tooltip';
import Chip from '@mui/material/Chip';
import Dialog from '@mui/material/Dialog';
import DialogTitle from '@mui/material/DialogTitle';
import DialogContent from '@mui/material/DialogContent';
import DialogActions from '@mui/material/DialogActions';
import Typography from '@mui/material/Typography';
import Drawer from '@mui/material/Drawer';
import Divider from '@mui/material/Divider';
import useTheme from '@mui/material/styles/useTheme';
import useMediaQuery from '@mui/material/useMediaQuery';
import LoadingSpinner from './LoadingSpinner';
import Menu from '@mui/material/Menu';
import MenuItem from '@mui/material/MenuItem';
import Grid from '@mui/material/Grid';
import Card from '@mui/material/Card';
import CardContent from '@mui/material/CardContent';
import FormControl from '@mui/material/FormControl';
import InputLabel from '@mui/material/InputLabel';
import Select from '@mui/material/Select';
import OutlinedInput from '@mui/material/OutlinedInput';
import InputAdornment from '@mui/material/InputAdornment';
import {
  Search as SearchIcon,
  Refresh as RefreshIcon,
  Download as DownloadIcon,
  FilterList as FilterIcon,
  Sort as SortIcon,
  Clear as ClearIcon,
  Close as CloseIcon,
  Add as AddIcon
} from '@mui/icons-material';
import { databaseAPI } from '../services/api';
import { useModalFocus } from '../hooks/useModalFocus';

interface DatabaseTableProps {
  tableName: string;
  onError?: (error: string) => void;
}

interface TableData {
  columns: string[];
  data: any[][];
  total_rows: number;
  page: number;
  total_pages: number;
}

interface ColumnFilter {
  column: string;
  value: string;
  operator: 'contains' | 'equals' | 'starts_with' | 'ends_with';
}

const DatabaseTable: React.FC<DatabaseTableProps> = ({ tableName, onError }) => {
  // State management
  const [data, setData] = useState<TableData | null>(null);
  const [loading, setLoading] = useState(false);
  const [page, setPage] = useState(0);
  const [rowsPerPage, setRowsPerPage] = useState(25);
  const [searchTerm, setSearchTerm] = useState('');
  const [filters, setFilters] = useState<ColumnFilter[]>([]);
  const [sortColumn, setSortColumn] = useState<string>('');
  const [sortDirection, setSortDirection] = useState<'asc' | 'desc'>('asc');
  const [selectedCell, setSelectedCell] = useState<any>(null);
  const [exportMenuAnchor, setExportMenuAnchor] = useState<null | HTMLElement>(null);
  const [filterDrawerOpen, setFilterDrawerOpen] = useState(false);

  const theme = useTheme();
  const isSmallScreen = useMediaQuery(theme.breakpoints.down('sm'));

  // Add modal focus management for cell value dialog
  const { modalRef: cellDialogRef } = useModalFocus({
    isOpen: selectedCell !== null,
    onClose: () => setSelectedCell(null),
    initialFocusSelector: 'button',
    restoreFocus: true,
    trapFocus: true,
    closeOnEscape: true
  });

  // Load table data
  const loadData = async (resetPage = false) => {
    if (!tableName) return;
    
    setLoading(true);
    try {
      const currentPage = resetPage ? 1 : page + 1;
      
      // Build additional query parameters (page and limit passed separately)
      const params: any = {};
      
      if (sortColumn) {
        params.order_by = sortColumn;
      }
      
      // Build filters object for backend (JSON format)
      if (filters.length > 0 || searchTerm) {
        const filterObj: any = {};
        
        // Add column-specific filters with operator support
        filters.forEach((filter) => {
          if (filter.value) {
            filterObj[filter.column] = {
              value: filter.value,
              operator: filter.operator
            };
          }
        });
        
        // Note: Search across all columns not directly supported by current backend
        // TODO: Implement search functionality in backend or convert to filters
        
        if (Object.keys(filterObj).length > 0) {
          params.filters = JSON.stringify(filterObj);
        }
      }
      
      const response = await databaseAPI.getTableData(tableName, currentPage, rowsPerPage, params);
      
      // Transform backend response to component format (axios wraps response in .data)
      const backendData = response.data.data;
      if (backendData) {
        const transformedData = {
          columns: backendData.columns || [],
          data: backendData.rows ? backendData.rows.map(row => 
            backendData.columns.map(col => row[col])
          ) : [],
          total_rows: backendData.total_count || 0,
          page: backendData.page || 1,
          total_pages: backendData.total_pages || 1
        };
        setData(transformedData);
      }
      
      if (resetPage) {
        setPage(0);
      }
    } catch (error) {
      console.error('Error loading table data:', error);
      onError?.('Failed to load table data');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    setPage(0);
    setFilters([]);
    setSearchTerm('');
    setSortColumn('');
    setSortDirection('asc');
    setExportMenuAnchor(null);
    setFilterDrawerOpen(false);
  }, [tableName]);
  // Effects
  useEffect(() => {
    loadData(true);
  }, [tableName, rowsPerPage, searchTerm, filters, sortColumn, sortDirection]);

  useEffect(() => {
    loadData();
  }, [page]);

  // Handlers
  const handlePageChange = (event: unknown, newPage: number) => {
    setPage(newPage);
  };

  const handleRowsPerPageChange = (event: React.ChangeEvent<HTMLInputElement>) => {
    setRowsPerPage(parseInt(event.target.value, 10));
    setPage(0);
  };

  const handleSearch = (event: React.ChangeEvent<HTMLInputElement>) => {
    setSearchTerm(event.target.value);
    setPage(0);
  };

  const handleSort = (column: string) => {
    if (sortColumn === column) {
      setSortDirection(sortDirection === 'asc' ? 'desc' : 'asc');
    } else {
      setSortColumn(column);
      setSortDirection('asc');
    }
    setPage(0);
  };

  const handleCellClick = (value: any) => {
    setSelectedCell(value);
  };

  const handleAddFilter = (column?: string) => {
    const targetColumn = column ?? data?.columns?.[0];
    if (!targetColumn) {
      return;
    }
    setFilters([...filters, { column: targetColumn, value: '', operator: 'contains' }]);
  };

  const handleUpdateFilter = (index: number, field: keyof ColumnFilter, value: string) => {
    const newFilters = [...filters];
    newFilters[index] = { ...newFilters[index], [field]: value };
    setFilters(newFilters);
  };

  const handleRemoveFilter = (index: number) => {
    setFilters(filters.filter((_, i) => i !== index));
  };

  const handleClearFilters = () => {
    setFilters([]);
    setSearchTerm('');
    setSortColumn('');
    setPage(0);
  };

  const handleExport = async (format: 'csv' | 'json') => {
    try {
      setLoading(true);
      
      // Build export parameters
      const exportParams: any = {};
      
      if (sortColumn) {
        exportParams.order_by = sortColumn;
      }
      
      // Build filters for export
      if (filters.length > 0) {
        const filterObj: any = {};
        filters.forEach((filter) => {
          if (filter.value) {
            filterObj[filter.column] = {
              value: filter.value,
              operator: filter.operator
            };
          }
        });
        
        if (Object.keys(filterObj).length > 0) {
          exportParams.filters = JSON.stringify(filterObj);
        }
      }
      
      const response = await databaseAPI.getTableData(tableName, 1, data?.total_rows || 1000, exportParams);
      const exportData = response.data.data;
      
      if (format === 'csv') {
        // Generate CSV
        const csvHeader = exportData.columns.join(',');
        const csvRows = exportData.rows.map(row => 
          exportData.columns.map(col => {
            const cellStr = row[col] !== null ? String(row[col]) : '';
            // Escape quotes and wrap in quotes if contains comma/quote
            if (cellStr.includes(',') || cellStr.includes('"') || cellStr.includes('\n')) {
              return `"${cellStr.replace(/"/g, '""')}"`;
            }
            return cellStr;
          }).join(',')
        );
        const csvContent = [csvHeader, ...csvRows].join('\n');
        
        // Download CSV
        const blob = new Blob([csvContent], { type: 'text/csv' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `${tableName}_export.csv`;
        a.click();
        URL.revokeObjectURL(url);
      } else {
        // Generate JSON
        const jsonContent = JSON.stringify({
          table: tableName,
          exported_at: new Date().toISOString(),
          total_rows: exportData.rows.length,
          columns: exportData.columns,
          data: exportData.rows
        }, null, 2);
        
        // Download JSON
        const blob = new Blob([jsonContent], { type: 'application/json' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `${tableName}_export.json`;
        a.click();
        URL.revokeObjectURL(url);
      }
      
    } catch (error) {
      console.error('Export error:', error);
      onError?.('Failed to export data');
    } finally {
      setLoading(false);
      setExportMenuAnchor(null);
    }
  };

  // Memoized values
  const hasActiveFilters = useMemo(() => {
    return searchTerm || filters.length > 0 || sortColumn;
  }, [searchTerm, filters, sortColumn]);

  return (
    <Box sx={{ display: 'flex', flexDirection: 'column', height: '100%', minHeight: 0 }}>
      {/* Controls Bar */}
      <Card sx={{ mb: 2, flexShrink: 0, overflow: 'visible' }}>
        <CardContent>
          <Grid container spacing={2} alignItems="center">
            {/* Search */}
            <Grid item xs={12} md={4}>
              <TextField
                fullWidth
                size="small"
                placeholder="Search all columns..."
                value={searchTerm}
                onChange={handleSearch}
                inputProps={{
                  'aria-label': 'Search all columns in the table'
                }}
                InputProps={{
                  startAdornment: (
                    <InputAdornment position="start">
                      <SearchIcon aria-hidden="true" />
                    </InputAdornment>
                  ),
                  endAdornment: searchTerm && (
                    <InputAdornment position="end">
                      <IconButton 
                        size="small" 
                        onClick={() => setSearchTerm('')}
                        aria-label="Clear search"
                      >
                        <ClearIcon />
                      </IconButton>
                    </InputAdornment>
                  )
                }}
              />
            </Grid>

            {/* Action Buttons */}
            <Grid item xs={12} md={8}>
              <Box sx={{ display: 'flex', gap: 1, justifyContent: 'flex-end' }}>
                <Tooltip title="Refresh Data">
                  <IconButton onClick={() => loadData(true)} disabled={loading}>
                    <RefreshIcon />
                  </IconButton>
                </Tooltip>
                
                <Tooltip title="Manage Filters">
                  <IconButton 
                    onClick={() => setFilterDrawerOpen(true)}
                    disabled={!data?.columns?.length}
                    aria-label="Open filters panel"
                  >
                    <FilterIcon />
                  </IconButton>
                </Tooltip>
                
                <Tooltip title="Export Data">
                  <IconButton 
                    onClick={(e) => setExportMenuAnchor(e.currentTarget)}
                    disabled={!data?.data?.length}
                  >
                    <DownloadIcon />
                  </IconButton>
                </Tooltip>
                
                {hasActiveFilters && (
                  <Button
                    size="small"
                    startIcon={<ClearIcon />}
                    onClick={handleClearFilters}
                  >
                    Clear All
                  </Button>
                )}
              </Box>
            </Grid>
          </Grid>

          {/* Active Filters */}
          {filters.length > 0 && (
            <Box sx={{ mt: 2 }}>
              <Typography variant="subtitle2" sx={{ mb: 1 }}>
                Active Filters:
              </Typography>
              <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 1 }}>
                {filters.map((filter, index) => (
                  <Chip
                    key={index}
                    size="small"
                    label={`${filter.column} ${filter.operator} "${filter.value}"`}
                    onDelete={() => handleRemoveFilter(index)}
                    color="primary"
                    variant="outlined"
                  />
                ))}
              </Box>
            </Box>
          )}

        </CardContent>
      </Card>

      {/* Data Table */}
      <Box sx={{ display: 'flex', flexDirection: 'column', flexGrow: 1, minHeight: 0 }}>
        <Paper sx={{ display: 'flex', flexDirection: 'column', flex: 1, minHeight: 0, overflow: 'hidden' }}>
          {loading ? (
            <LoadingSpinner 
              variant="spinner" 
              message="Loading table data..." 
              minHeight={200}
            />
          ) : data ? (
            <TableContainer 
              sx={{ 
                flex: 1, 
                minHeight: 0,
                maxHeight: '100%',
                overflowY: 'auto',
                overflowX: 'auto'
              }}
              role="region"
              aria-label={`Database table for ${tableName}`}
            >
              <Table 
                stickyHeader 
                size="small"
                role="table"
                aria-label={`Data from ${tableName} table`}
              >
                <TableHead role="rowgroup">
                  <TableRow role="row">
                    {data.columns.map((column) => (
                      <TableCell 
                        key={column}
                        role="columnheader"
                        scope="col"
                        aria-sort={
                          sortColumn === column 
                            ? sortDirection === 'asc' ? 'ascending' : 'descending'
                            : 'none'
                        }
                      >
                        <Box sx={{ display: 'flex', alignItems: 'center' }}>
                          <Typography variant="subtitle2" sx={{ fontWeight: 'bold' }}>
                            {column}
                          </Typography>
                          <IconButton
                            size="small"
                            onClick={() => handleSort(column)}
                            sx={{ ml: 1 }}
                            aria-label={`Sort by ${column} ${sortColumn === column && sortDirection === 'asc' ? 'descending' : 'ascending'}`}
                          >
                            <SortIcon 
                              fontSize="small"
                              color={sortColumn === column ? 'primary' : 'disabled'}
                            />
                          </IconButton>
                        </Box>
                      </TableCell>
                    ))}
                  </TableRow>
                </TableHead>
                <TableBody role="rowgroup">
                  {data.data.map((row, rowIndex) => (
                    <TableRow key={rowIndex} hover role="row">
                      {row.map((cell, cellIndex) => (
                        <TableCell 
                          key={cellIndex}
                          onClick={() => handleCellClick(cell)}
                          sx={{ cursor: 'pointer' }}
                          role="gridcell"
                          aria-describedby={`cell-${rowIndex}-${cellIndex}-desc`}
                        >
                          {cell !== null ? (
                            <Box sx={{ maxWidth: 200, overflow: 'hidden', textOverflow: 'ellipsis' }}>
                              {String(cell)}
                            </Box>
                          ) : (
                            <Typography variant="body2" color="textSecondary" fontStyle="italic">
                              NULL
                            </Typography>
                          )}
                        </TableCell>
                      ))}
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </TableContainer>
          ) : (
            <Box sx={{ textAlign: 'center', py: 4 }}>
              <Typography color="textSecondary">
                No data available
              </Typography>
            </Box>
          )}
        </Paper>

        {!loading && data && (
          <Box sx={{ flexShrink: 0, borderTop: 1, borderColor: 'divider', bgcolor: 'background.paper' }}>
            <TablePagination
              component="div"
              count={data.total_rows}
              page={page}
              onPageChange={handlePageChange}
              rowsPerPage={rowsPerPage}
              onRowsPerPageChange={handleRowsPerPageChange}
              rowsPerPageOptions={[10, 25, 50, 100]}
              showFirstButton
              showLastButton
              sx={{
                '.MuiTablePagination-toolbar': {
                  flexWrap: 'wrap',
                  rowGap: 1.5,
                  columnGap: { xs: 1, sm: 2 },
                  justifyContent: { xs: 'center', md: 'space-between' },
                  px: { xs: 1, sm: 2 }
                },
                '.MuiTablePagination-selectLabel, .MuiTablePagination-displayedRows': {
                  fontSize: { xs: '0.85rem', sm: '0.9rem' }
                },
                '.MuiTablePagination-selectRoot': {
                  marginRight: { xs: 0, md: 3 }
                },
                '.MuiInputBase-root': {
                  minWidth: 120,
                  fontSize: { xs: '0.9rem', sm: '1rem' }
                },
                '.MuiTablePagination-actions': {
                  marginLeft: { xs: 0, md: 1 }
                }
              }}
            />
          </Box>
        )}
      </Box>

      <Drawer
        anchor={isSmallScreen ? 'bottom' : 'right'}
        open={filterDrawerOpen}
        onClose={() => setFilterDrawerOpen(false)}
        ModalProps={{ keepMounted: true }}
        PaperProps={{
          sx: {
            width: isSmallScreen ? '100%' : 360,
            maxWidth: '100%',
            height: isSmallScreen ? '60vh' : '100%',
            display: 'flex',
            flexDirection: 'column'
          }
        }}
      >
        <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', p: 2 }}>
          <Typography variant="h6">
            Filters
          </Typography>
          <IconButton onClick={() => setFilterDrawerOpen(false)} aria-label="Close filters panel">
            <CloseIcon />
          </IconButton>
        </Box>
        <Divider />
        <Box sx={{ flexGrow: 1, overflowY: 'auto', p: 2, pt: 1 }}>
          {filters.length === 0 ? (
            <Typography variant="body2" color="textSecondary">
              No filters applied. Use "Add condition" to create one.
            </Typography>
          ) : (
            filters.map((filter, index) => (
              <Grid container spacing={1.5} key={index} sx={{ mb: 2, alignItems: 'flex-start' }}>
                <Grid item xs={12} sm={12}>
                  <Typography variant="subtitle2" color="textSecondary">
                    Condition {index + 1}
                  </Typography>
                </Grid>
                <Grid item xs={12} sm={6}>
                  <FormControl fullWidth size="small">
                    <InputLabel>Column</InputLabel>
                    <Select
                      value={filter.column}
                      onChange={(e) => handleUpdateFilter(index, 'column', e.target.value)}
                      input={<OutlinedInput label="Column" />}
                    >
                      {data?.columns.map(col => (
                        <MenuItem key={col} value={col}>{col}</MenuItem>
                      ))}
                    </Select>
                  </FormControl>
                </Grid>
                <Grid item xs={12} sm={6}>
                  <FormControl fullWidth size="small">
                    <InputLabel>Operator</InputLabel>
                    <Select
                      value={filter.operator}
                      onChange={(e) => handleUpdateFilter(index, 'operator', e.target.value)}
                      input={<OutlinedInput label="Operator" />}
                    >
                      <MenuItem value="contains">Contains</MenuItem>
                      <MenuItem value="equals">Equals</MenuItem>
                      <MenuItem value="starts_with">Starts With</MenuItem>
                      <MenuItem value="ends_with">Ends With</MenuItem>
                    </Select>
                  </FormControl>
                </Grid>
                <Grid item xs={12}>
                  <TextField
                    fullWidth
                    size="small"
                    label="Value"
                    value={filter.value}
                    onChange={(e) => handleUpdateFilter(index, 'value', e.target.value)}
                  />
                </Grid>
                <Grid item xs={12}>
                  <Button
                    size="small"
                    color="error"
                    onClick={() => handleRemoveFilter(index)}
                    sx={{ justifyContent: 'flex-start' }}
                  >
                    Remove condition
                  </Button>
                </Grid>
              </Grid>
            ))
          )}
        </Box>
        <Divider />
        <Box sx={{ p: 2, display: 'flex', flexWrap: 'wrap', gap: 1 }}>
          <Button
            variant="contained"
            size="small"
            startIcon={<AddIcon />}
            onClick={() => handleAddFilter()}
            disabled={!data?.columns?.length}
          >
            Add condition
          </Button>
          {filters.length > 0 && (
            <Button
              size="small"
              color="error"
              startIcon={<ClearIcon />}
              onClick={handleClearFilters}
            >
              Clear all
            </Button>
          )}
        </Box>
      </Drawer>

      {/* Export Menu */}
      <Menu
        anchorEl={exportMenuAnchor}
        open={Boolean(exportMenuAnchor)}
        onClose={() => setExportMenuAnchor(null)}
      >
        <MenuItem onClick={() => handleExport('csv')}>
          Export as CSV
        </MenuItem>
        <MenuItem onClick={() => handleExport('json')}>
          Export as JSON
        </MenuItem>
      </Menu>

      {/* Cell Value Dialog */}
      <Dialog
        ref={cellDialogRef}
        open={selectedCell !== null}
        onClose={() => setSelectedCell(null)}
        maxWidth="md"
        fullWidth
        aria-labelledby="cell-value-dialog-title"
        aria-describedby="cell-value-dialog-content"
      >
        <DialogTitle id="cell-value-dialog-title">Cell Value</DialogTitle>
        <DialogContent id="cell-value-dialog-content">
          <Box sx={{ mt: 1 }}>
            <Typography variant="body2" color="textSecondary" gutterBottom>
              Full cell content:
            </Typography>
            <Paper sx={{ p: 2, bgcolor: 'grey.50', maxHeight: 300, overflow: 'auto' }}>
              <Typography variant="body2" component="pre" sx={{ whiteSpace: 'pre-wrap' }}>
                {selectedCell !== null ? String(selectedCell) : 'NULL'}
              </Typography>
            </Paper>
          </Box>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setSelectedCell(null)} autoFocus>
            Close
          </Button>
        </DialogActions>
      </Dialog>
    </Box>
  );
};

export default DatabaseTable;






