/**
 * RobotControl Backup List Component
 * 
 * Material-UI table component for displaying database backups with:
 * - Sortable columns by date, size, filename, and description  
 * - Selection functionality for backup operations
 * - Detailed backup information dialog
 * - Status indicators and validation warnings
 * - Responsive design with loading states
 */

import React, { useState, useMemo } from 'react';
import {
  Box,
  Paper,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  TableSortLabel,
  Checkbox,
  Radio,
  IconButton,
  Tooltip,
  Chip,
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  Typography,
  Button,
  Grid,
  Card,
  CardContent,
  Divider,
  CircularProgress,
  Alert,
  Stack
} from '@mui/material';
import {
  Info as InfoIcon,
  Refresh as RefreshIcon,
  Warning as WarningIcon,
  CheckCircle as CheckCircleIcon,
  Error as ErrorIcon,
  Schedule as ScheduleIcon,
  Storage as StorageIcon
} from '@mui/icons-material';

import {
  BackupInfo,
  BackupDetails,
  BackupSortField,
  BackupSortOrder,
  BackupSortOptions,
  formatBackupDate,
  formatBackupTimestamp
} from '../types/backup';

interface BackupListComponentProps {
  backups: BackupInfo[];
  selectedBackup: BackupInfo | null;
  onBackupSelect: (backup: BackupInfo | null) => void;
  onRefresh: () => void;
  onViewDetails?: (backup: BackupInfo) => void;
  loading?: boolean;
  error?: string | null;
  selectionMode?: 'single' | 'multiple' | 'none';
  showActions?: boolean;
}

interface BackupDetailsDialogProps {
  backup: BackupInfo | null;
  details: BackupDetails | null;
  open: boolean;
  onClose: () => void;
  loading?: boolean;
}

const BackupDetailsDialog: React.FC<BackupDetailsDialogProps> = ({
  backup,
  details,
  open,
  onClose,
  loading = false
}) => {
  if (!backup) return null;

  return (
    <Dialog open={open} onClose={onClose} maxWidth="md" fullWidth>
      <DialogTitle>
        <Stack direction="row" alignItems="center" spacing={1}>
          <InfoIcon color="primary" />
          <Typography variant="h6">Backup Details</Typography>
        </Stack>
      </DialogTitle>
      <DialogContent>
        {loading ? (
          <Box display="flex" justifyContent="center" alignItems="center" minHeight={200}>
            <CircularProgress />
          </Box>
        ) : (
          <Grid container spacing={2}>
            {/* Basic Information */}
            <Grid item xs={12}>
              <Card variant="outlined">
                <CardContent>
                  <Typography variant="h6" gutterBottom>
                    Basic Information
                  </Typography>
                  <Grid container spacing={2}>
                    <Grid item xs={6}>
                      <Typography variant="body2" color="textSecondary">
                        Filename
                      </Typography>
                      <Typography variant="body1" sx={{ fontFamily: 'monospace' }}>
                        {backup.filename}
                      </Typography>
                    </Grid>
                    <Grid item xs={6}>
                      <Typography variant="body2" color="textSecondary">
                        File Size
                      </Typography>
                      <Typography variant="body1">
                        {backup.file_size_formatted}
                      </Typography>
                    </Grid>
                    <Grid item xs={6}>
                      <Typography variant="body2" color="textSecondary">
                        Created Date
                      </Typography>
                      <Typography variant="body1">
                        {formatBackupDate(backup.created_date)}
                      </Typography>
                    </Grid>
                    <Grid item xs={6}>
                      <Typography variant="body2" color="textSecondary">
                        Status
                      </Typography>
                      <Chip
                        icon={backup.is_valid ? <CheckCircleIcon /> : <WarningIcon />}
                        label={backup.is_valid ? 'Valid' : 'Invalid'}
                        color={backup.is_valid ? 'success' : 'warning'}
                        size="small"
                      />
                    </Grid>
                  </Grid>
                </CardContent>
              </Card>
            </Grid>

            {/* Description */}
            <Grid item xs={12}>
              <Card variant="outlined">
                <CardContent>
                  <Typography variant="h6" gutterBottom>
                    Description
                  </Typography>
                  <Typography variant="body1" sx={{ whiteSpace: 'pre-wrap' }}>
                    {backup.description || 'No description provided'}
                  </Typography>
                </CardContent>
              </Card>
            </Grid>

            {/* Database Information */}
            {(backup.database_name || backup.sql_server) && (
              <Grid item xs={12}>
                <Card variant="outlined">
                  <CardContent>
                    <Typography variant="h6" gutterBottom>
                      Database Information
                    </Typography>
                    <Grid container spacing={2}>
                      {backup.database_name && (
                        <Grid item xs={6}>
                          <Typography variant="body2" color="textSecondary">
                            Database
                          </Typography>
                          <Typography variant="body1" sx={{ fontFamily: 'monospace' }}>
                            {backup.database_name}
                          </Typography>
                        </Grid>
                      )}
                      {backup.sql_server && (
                        <Grid item xs={6}>
                          <Typography variant="body2" color="textSecondary">
                            SQL Server
                          </Typography>
                          <Typography variant="body1" sx={{ fontFamily: 'monospace' }}>
                            {backup.sql_server}
                          </Typography>
                        </Grid>
                      )}
                    </Grid>
                  </CardContent>
                </Card>
              </Grid>
            )}

            {/* Detailed Metadata */}
            {details && details.metadata && (
              <Grid item xs={12}>
                <Card variant="outlined">
                  <CardContent>
                    <Typography variant="h6" gutterBottom>
                      Metadata
                    </Typography>
                    <Box
                      component="pre"
                      sx={{
                        backgroundColor: 'grey.50',
                        padding: 2,
                        borderRadius: 1,
                        overflow: 'auto',
                        fontSize: '0.875rem',
                        fontFamily: 'monospace'
                      }}
                    >
                      {JSON.stringify(details.metadata, null, 2)}
                    </Box>
                  </CardContent>
                </Card>
              </Grid>
            )}
          </Grid>
        )}
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose} color="primary">
          Close
        </Button>
      </DialogActions>
    </Dialog>
  );
};

const BackupListComponent: React.FC<BackupListComponentProps> = ({
  backups,
  selectedBackup,
  onBackupSelect,
  onRefresh,
  onViewDetails,
  loading = false,
  error = null,
  selectionMode = 'single',
  showActions = true
}) => {
  const [sortOptions, setSortOptions] = useState<BackupSortOptions>({
    field: 'created_date',
    order: 'desc'
  });
  const [detailsDialog, setDetailsDialog] = useState({
    open: false,
    backup: null as BackupInfo | null,
    details: null as BackupDetails | null,
    loading: false
  });

  // Sort backups
  const sortedBackups = useMemo(() => {
    const sorted = [...backups].sort((a, b) => {
      let aValue: any = a[sortOptions.field];
      let bValue: any = b[sortOptions.field];

      // Handle date sorting
      if (sortOptions.field === 'created_date') {
        aValue = new Date(aValue).getTime();
        bValue = new Date(bValue).getTime();
      }
      // Handle file size sorting
      else if (sortOptions.field === 'file_size') {
        aValue = a.file_size;
        bValue = b.file_size;
      }
      // Handle string sorting
      else {
        aValue = String(aValue).toLowerCase();
        bValue = String(bValue).toLowerCase();
      }

      if (sortOptions.order === 'asc') {
        return aValue < bValue ? -1 : aValue > bValue ? 1 : 0;
      } else {
        return aValue > bValue ? -1 : aValue < bValue ? 1 : 0;
      }
    });
    return sorted;
  }, [backups, sortOptions]);

  const handleSort = (field: BackupSortField) => {
    setSortOptions(prev => ({
      field,
      order: prev.field === field && prev.order === 'asc' ? 'desc' : 'asc'
    }));
  };

  const handleRowClick = (backup: BackupInfo) => {
    if (selectionMode !== 'none') {
      const newSelection = selectedBackup?.filename === backup.filename ? null : backup;
      onBackupSelect(newSelection);
    }
  };

  const handleViewDetails = async (backup: BackupInfo) => {
    setDetailsDialog({
      open: true,
      backup,
      details: null,
      loading: true
    });

    if (onViewDetails) {
      onViewDetails(backup);
    }

    // In a real implementation, you would fetch details here
    // For now, we'll just show basic info
    setTimeout(() => {
      setDetailsDialog(prev => ({
        ...prev,
        loading: false
      }));
    }, 500);
  };

  const renderStatusIcon = (backup: BackupInfo) => {
    if (!backup.is_valid) {
      return (
        <Tooltip title="Invalid backup - missing files or corrupted metadata">
          <WarningIcon color="warning" fontSize="small" />
        </Tooltip>
      );
    }
    return (
      <Tooltip title="Valid backup">
        <CheckCircleIcon color="success" fontSize="small" />
      </Tooltip>
    );
  };

  const renderTableHeader = () => {
    const columns = [
      { field: 'filename' as BackupSortField, label: 'Filename', width: '25%' },
      { field: 'created_date' as BackupSortField, label: 'Created', width: '20%' },
      { field: 'file_size' as BackupSortField, label: 'Size', width: '15%' },
      { field: 'description' as BackupSortField, label: 'Description', width: '30%' },
    ];

    return (
      <TableHead>
        <TableRow>
          {selectionMode !== 'none' && (
            <TableCell padding="checkbox" width="5%">
              Status
            </TableCell>
          )}
          {columns.map((column) => (
            <TableCell key={column.field} width={column.width}>
              <TableSortLabel
                active={sortOptions.field === column.field}
                direction={sortOptions.field === column.field ? sortOptions.order : 'asc'}
                onClick={() => handleSort(column.field)}
              >
                {column.label}
              </TableSortLabel>
            </TableCell>
          ))}
          {showActions && (
            <TableCell width="5%">Actions</TableCell>
          )}
        </TableRow>
      </TableHead>
    );
  };

  if (loading) {
    return (
      <Box display="flex" justifyContent="center" alignItems="center" minHeight={300}>
        <CircularProgress />
      </Box>
    );
  }

  if (error) {
    return (
      <Alert severity="error" sx={{ mb: 2 }}>
        {error}
      </Alert>
    );
  }

  return (
    <>
      <Paper elevation={1}>
        {/* Header */}
        <Box p={2} borderBottom={1} borderColor="divider">
          <Stack direction="row" justifyContent="space-between" alignItems="center">
            <Typography variant="h6">
              Database Backups ({backups.length})
            </Typography>
            <Button
              startIcon={<RefreshIcon />}
              onClick={onRefresh}
              variant="outlined"
              size="small"
            >
              Refresh
            </Button>
          </Stack>
        </Box>

        {/* Table */}
        <TableContainer>
          <Table stickyHeader>
            {renderTableHeader()}
            <TableBody>
              {sortedBackups.length === 0 ? (
                <TableRow>
                  <TableCell 
                    colSpan={selectionMode !== 'none' ? 6 : 5} 
                    align="center"
                    sx={{ py: 4 }}
                  >
                    <Stack alignItems="center" spacing={2}>
                      <StorageIcon color="disabled" sx={{ fontSize: 48 }} />
                      <Typography color="textSecondary">
                        No backups found
                      </Typography>
                    </Stack>
                  </TableCell>
                </TableRow>
              ) : (
                sortedBackups.map((backup) => (
                  <TableRow
                    key={backup.filename}
                    hover
                    selected={selectedBackup?.filename === backup.filename}
                    onClick={() => handleRowClick(backup)}
                    sx={{ cursor: selectionMode !== 'none' ? 'pointer' : 'default' }}
                  >
                    {selectionMode !== 'none' && (
                      <TableCell padding="checkbox">
                        <Stack direction="row" alignItems="center" spacing={1}>
                          {selectionMode === 'single' ? (
                            <Radio
                              checked={selectedBackup?.filename === backup.filename}
                              onChange={() => handleRowClick(backup)}
                              size="small"
                            />
                          ) : (
                            <Checkbox
                              checked={selectedBackup?.filename === backup.filename}
                              onChange={() => handleRowClick(backup)}
                              size="small"
                            />
                          )}
                          {renderStatusIcon(backup)}
                        </Stack>
                      </TableCell>
                    )}
                    
                    <TableCell>
                      <Typography variant="body2" sx={{ fontFamily: 'monospace' }}>
                        {backup.filename}
                      </Typography>
                    </TableCell>
                    
                    <TableCell>
                      <Stack spacing={0.5}>
                        <Typography variant="body2">
                          {formatBackupDate(backup.created_date)}
                        </Typography>
                        <Typography variant="caption" color="textSecondary">
                          {formatBackupTimestamp(backup.timestamp)}
                        </Typography>
                      </Stack>
                    </TableCell>
                    
                    <TableCell>
                      <Typography variant="body2">
                        {backup.file_size_formatted}
                      </Typography>
                    </TableCell>
                    
                    <TableCell>
                      <Typography 
                        variant="body2" 
                        sx={{ 
                          maxWidth: 200,
                          overflow: 'hidden',
                          textOverflow: 'ellipsis',
                          whiteSpace: 'nowrap'
                        }}
                        title={backup.description}
                      >
                        {backup.description || <em>No description</em>}
                      </Typography>
                    </TableCell>
                    
                    {showActions && (
                      <TableCell>
                        <IconButton
                          size="small"
                          onClick={(e) => {
                            e.stopPropagation();
                            handleViewDetails(backup);
                          }}
                        >
                          <InfoIcon fontSize="small" />
                        </IconButton>
                      </TableCell>
                    )}
                  </TableRow>
                ))
              )}
            </TableBody>
          </Table>
        </TableContainer>
      </Paper>

      {/* Details Dialog */}
      <BackupDetailsDialog
        backup={detailsDialog.backup}
        details={detailsDialog.details}
        open={detailsDialog.open}
        onClose={() => setDetailsDialog(prev => ({ ...prev, open: false }))}
        loading={detailsDialog.loading}
      />
    </>
  );
};

export default BackupListComponent;
export { BackupDetailsDialog };
export type { BackupListComponentProps, BackupDetailsDialogProps };