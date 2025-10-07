import React, { useState, useEffect } from 'react';
import {
  Box,
  Card,
  CardContent,
  Typography,
  FormControl,
  InputLabel,
  Select,
  MenuItem,
  Button,
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  Stack,
  Chip,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  Paper,
  IconButton,
  Tooltip
} from '@mui/material';
import DeleteIcon from '@mui/icons-material/Delete';
import PlayArrowIcon from '@mui/icons-material/PlayArrow';
import LoadingSpinner from './LoadingSpinner';
import ErrorAlert from './ErrorAlert';
import WarningIcon from '@mui/icons-material/Warning';
import CheckCircleIcon from '@mui/icons-material/CheckCircle';
import { databaseAPI } from '../services/api';

interface Experiment {
  ExperimentID: number;
  UserDefinedID?: string;
  Note?: string;
  [key: string]: any;
}

interface DatabaseOperationsProps {
  onError?: (error: string) => void;
}

const DatabaseOperations: React.FC<DatabaseOperationsProps> = ({ onError }) => {
  const [experiments, setExperiments] = useState<Experiment[]>([]);
  const [selectedExperiment, setSelectedExperiment] = useState<number | ''>('');
  const [loading, setLoading] = useState(false);
  const [deleteDialogOpen, setDeleteDialogOpen] = useState(false);
  const [executionResult, setExecutionResult] = useState<any>(null);
  const [showResult, setShowResult] = useState(false);

  useEffect(() => {
    loadExperiments();
  }, []);

  const loadExperiments = async () => {
    setLoading(true);
    try {
      const response = await databaseAPI.getExperiments(1, 1000); // Get all experiments
      const data = response.data.data;
      
      if (data.rows) {
        setExperiments(data.rows);
      }
    } catch (err: any) {
      console.error('Error loading experiments:', err);
      if (onError) {
        onError(err.response?.data?.detail || 'Failed to load experiments');
      }
    } finally {
      setLoading(false);
    }
  };

  const handleDeleteExperiment = async () => {
    if (!selectedExperiment) return;

    setLoading(true);
    try {
      const result = await databaseAPI.executeProcedure('DeleteExperiment', {
        ExpID: selectedExperiment
      });
      
      setExecutionResult(result.data);
      setShowResult(true);
      setDeleteDialogOpen(false);
      setSelectedExperiment('');
      
    } catch (err: any) {
      console.error('Error deleting experiment:', err);
      setExecutionResult({
        success: false,
        error: err.response?.data?.detail || 'Failed to delete experiment',
        data: { message: 'Deletion failed' }
      });
      setShowResult(true);
      setDeleteDialogOpen(false);
    } finally {
      // Always reload experiments list after deletion attempt
      await loadExperiments();
      setLoading(false);
    }
  };

  const getSelectedExperimentDetails = () => {
    if (!selectedExperiment) return null;
    return experiments.find(exp => exp.ExperimentID === selectedExperiment);
  };

  const formatExperimentLabel = (experiment: Experiment) => {
    const parts = [`ID: ${experiment.ExperimentID}`];
    if (experiment.UserDefinedID) {
      parts.push(`User: ${experiment.UserDefinedID}`);
    }
    if (experiment.Note) {
      parts.push(`Note: ${experiment.Note.length > 30 ? experiment.Note.substring(0, 30) + '...' : experiment.Note}`);
    }
    return parts.join(' | ');
  };

  const selectedExpDetails = getSelectedExperimentDetails();

  return (
    <Box>
      <Typography variant="h6" gutterBottom>Database Operations</Typography>
      
      {/* Delete Experiment Section */}
      <Card sx={{ mb: 3 }}>
        <CardContent>
          <Stack spacing={2}>
            <Typography variant="subtitle1" sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
              <DeleteIcon color="error" />
              Delete Experiment
            </Typography>
            
            <FormControl fullWidth disabled={loading}>
              <InputLabel>Select Experiment to Delete</InputLabel>
              <Select
                value={selectedExperiment}
                onChange={(e) => setSelectedExperiment(e.target.value as number)}
                label="Select Experiment to Delete"
              >
                <MenuItem value="">
                  <em>Choose an experiment...</em>
                </MenuItem>
                {experiments.map((exp) => (
                  <MenuItem key={exp.ExperimentID} value={exp.ExperimentID}>
                    {formatExperimentLabel(exp)}
                  </MenuItem>
                ))}
              </Select>
            </FormControl>

            {selectedExpDetails && (
              <Card variant="outlined" sx={{ p: 2, bgcolor: 'grey.50' }}>
                <Typography variant="subtitle2" gutterBottom>Selected Experiment Details:</Typography>
                <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
                  <Chip label={`ID: ${selectedExpDetails.ExperimentID}`} size="small" color="primary" />
                  {selectedExpDetails.UserDefinedID && (
                    <Chip label={`User: ${selectedExpDetails.UserDefinedID}`} size="small" color="secondary" />
                  )}
                  {selectedExpDetails.Note && (
                    <Chip 
                      label={`Note: ${selectedExpDetails.Note}`} 
                      size="small" 
                      variant="outlined"
                      sx={{ maxWidth: 300 }}
                    />
                  )}
                </Stack>
                
                {/* Show additional experiment details if available */}
                <Box sx={{ mt: 1 }}>
                  <Table size="small">
                    <TableBody>
                      {Object.entries(selectedExpDetails)
                        .filter(([key, value]) => !['ExperimentID', 'UserDefinedID', 'Note'].includes(key) && value !== null && value !== undefined)
                        .slice(0, 5) // Limit to first 5 additional fields
                        .map(([key, value]) => (
                          <TableRow key={key}>
                            <TableCell sx={{ py: 0.5, fontSize: '0.8rem', fontWeight: 'bold' }}>{key}:</TableCell>
                            <TableCell sx={{ py: 0.5, fontSize: '0.8rem' }}>
                              {typeof value === 'object' ? JSON.stringify(value) : String(value)}
                            </TableCell>
                          </TableRow>
                        ))}
                    </TableBody>
                  </Table>
                </Box>
              </Card>
            )}

            <Box sx={{ display: 'flex', gap: 2 }}>
              <Button
                variant="contained"
                color="error"
                startIcon={<DeleteIcon />}
                onClick={() => setDeleteDialogOpen(true)}
                disabled={!selectedExperiment || loading}
              >
                Delete Experiment
              </Button>
              
              <Button
                variant="outlined"
                onClick={loadExperiments}
                disabled={loading}
                startIcon={loading ? <LoadingSpinner variant="inline" size="small" /> : <PlayArrowIcon />}
              >
                Refresh List
              </Button>
            </Box>
          </Stack>
        </CardContent>
      </Card>

      {/* Future Operations Placeholder */}
      <Card sx={{ bgcolor: 'grey.50' }}>
        <CardContent>
          <Typography variant="subtitle2" color="textSecondary">
            Future Database Operations
          </Typography>
          <Typography variant="body2" color="textSecondary">
            This section can be expanded to include other stored procedure executions and database operations as needed.
          </Typography>
        </CardContent>
      </Card>

      {/* Delete Confirmation Dialog */}
      <Dialog
        open={deleteDialogOpen}
        onClose={() => setDeleteDialogOpen(false)}
        maxWidth="sm"
        fullWidth
      >
        <DialogTitle sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
          <WarningIcon color="error" />
          Confirm Experiment Deletion
        </DialogTitle>
        <DialogContent>
          <ErrorAlert
            message="This action cannot be undone. The experiment and all associated data will be permanently deleted."
            severity="error"
            category="server"
            title="Warning"
            sx={{ mb: 2 }}
          />
          
          {selectedExpDetails && (
            <Box>
              <Typography variant="body2" gutterBottom>
                You are about to delete the following experiment:
              </Typography>
              <Paper sx={{ p: 2, mt: 1, bgcolor: 'grey.100' }}>
                <Typography variant="body2"><strong>Experiment ID:</strong> {selectedExpDetails.ExperimentID}</Typography>
                {selectedExpDetails.UserDefinedID && (
                  <Typography variant="body2"><strong>User Defined ID:</strong> {selectedExpDetails.UserDefinedID}</Typography>
                )}
                {selectedExpDetails.Note && (
                  <Typography variant="body2"><strong>Note:</strong> {selectedExpDetails.Note}</Typography>
                )}
              </Paper>
            </Box>
          )}
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setDeleteDialogOpen(false)} disabled={loading}>
            Cancel
          </Button>
          <Button
            onClick={handleDeleteExperiment}
            color="error"
            variant="contained"
            disabled={loading}
            startIcon={loading ? <LoadingSpinner variant="inline" size="small" /> : <DeleteIcon />}
          >
            {loading ? 'Deleting...' : 'Delete Experiment'}
          </Button>
        </DialogActions>
      </Dialog>

      {/* Execution Result Dialog */}
      <Dialog
        open={showResult}
        onClose={() => setShowResult(false)}
        maxWidth="md"
        fullWidth
      >
        <DialogTitle sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
          {executionResult?.success ? (
            <>
              <CheckCircleIcon color="success" />
              Operation Successful
            </>
          ) : (
            <>
              <WarningIcon color="error" />
              Operation Failed
            </>
          )}
        </DialogTitle>
        <DialogContent>
          <ErrorAlert
            message={executionResult?.data?.message || executionResult?.error || 'Operation completed'}
            severity={executionResult?.success ? 'success' : 'error'}
            category={executionResult?.success ? 'unknown' : 'server'}
            title={executionResult?.success ? 'Operation Successful' : undefined}
            sx={{ mb: 2 }}
          />
          {executionResult?.data?.result && (
            <Box>
              <Typography variant="subtitle2" gutterBottom>Execution Details:</Typography>
              <Paper sx={{ p: 2, bgcolor: 'grey.50', fontFamily: 'monospace', fontSize: '0.9rem' }}>
                {JSON.stringify(executionResult.data.result, null, 2)}
              </Paper>
            </Box>
          )}
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setShowResult(false)}>Close</Button>
        </DialogActions>
      </Dialog>
    </Box>
  );
};

export default DatabaseOperations;

