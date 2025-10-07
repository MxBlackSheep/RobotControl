import React, { useState, useEffect } from 'react';
import {
  Box,
  Card,
  CardContent,
  Typography,
  List,
  ListItem,
  ListItemButton,
  ListItemText,
  Accordion,
  AccordionSummary,
  AccordionDetails,
  Chip,
  Stack,
  Button,
  Paper,
  IconButton,
  Tooltip,
  Divider,
  Grid
} from '@mui/material';
import ExpandMoreIcon from '@mui/icons-material/ExpandMore';
import CodeIcon from '@mui/icons-material/Code';
import FunctionsIcon from '@mui/icons-material/Functions';
import RefreshIcon from '@mui/icons-material/Refresh';
import ContentCopyIcon from '@mui/icons-material/ContentCopy';
import { databaseAPI } from '../services/api';
import LoadingSpinner from './LoadingSpinner';

interface Parameter {
  name: string;
  data_type: string;
  mode: string;
  max_length: number | null;
}

interface RawStoredItem {
  name?: string;
  type?: string;
  created_date?: string | null;
  modified_date?: string | null;
  definition?: string | null;
  parameters?: Array<Partial<Parameter>> | null;
}

interface StoredProcedure {
  name: string;
  type: string;
  created_date: string | null;
  modified_date: string | null;
  definition: string;
  parameters: Parameter[];
}

interface StoredProceduresProps {
  onError?: (error: string) => void;
}

const normalizeParameter = (param: Partial<Parameter> | undefined): Parameter => ({
  name: param?.name ?? 'param',
  data_type: param?.data_type ?? 'UNKNOWN',
  mode: (param?.mode ?? 'IN').toUpperCase(),
  max_length: typeof param?.max_length === 'number' ? param.max_length : null
});

const normalizeStoredItem = (item: RawStoredItem | undefined): StoredProcedure => ({
  name: item?.name ?? 'Unnamed',
  type: item?.type ?? 'PROCEDURE',
  created_date: item?.created_date ?? null,
  modified_date: item?.modified_date ?? null,
  definition: item?.definition ?? 'Definition not available from server.',
  parameters: Array.isArray(item?.parameters)
    ? (item?.parameters ?? []).map(normalizeParameter)
    : []
});

const StoredProcedures: React.FC<StoredProceduresProps> = ({ onError }) => {
  const [procedures, setProcedures] = useState<StoredProcedure[]>([]);
  const [functions, setFunctions] = useState<StoredProcedure[]>([]);
  const [loading, setLoading] = useState(true);
  const [selectedItem, setSelectedItem] = useState<StoredProcedure | null>(null);
  const [expandedAccordion, setExpandedAccordion] = useState<string | false>('procedures');
  const [metadataExpanded, setMetadataExpanded] = useState(false);
  const [parametersExpanded, setParametersExpanded] = useState(true);

  const selectedParameters = Array.isArray(selectedItem?.parameters) ? selectedItem.parameters : [];

  useEffect(() => {
    loadStoredProcedures();
  }, []);

  const loadStoredProcedures = async () => {
    setLoading(true);
    try {
      const response = await databaseAPI.getStoredProcedures();
      const payload = response?.data?.data ?? {};

      const normalizedProcedures = Array.isArray(payload.procedures)
        ? payload.procedures.map(normalizeStoredItem)
        : [];
      const normalizedFunctions = Array.isArray(payload.functions)
        ? payload.functions.map(normalizeStoredItem)
        : [];

      setProcedures(normalizedProcedures);
      setFunctions(normalizedFunctions);

      if (normalizedProcedures.length > 0) {
        setSelectedItem(normalizedProcedures[0]);
      } else if (normalizedFunctions.length > 0) {
        setSelectedItem(normalizedFunctions[0]);
        setExpandedAccordion('functions');
      } else {
        setSelectedItem(null);
      }
    } catch (err: any) {
      console.error('Error loading stored procedures:', err);
      if (onError) {
        onError(err.response?.data?.detail || 'Failed to load stored procedures');
      }
    } finally {
      setLoading(false);
    }
  };

  const handleCopyDefinition = (definition: string) => {
    navigator.clipboard.writeText(definition);
  };

  const formatParameterString = (params: Parameter[]) => {
    if (params.length === 0) return '()';
    return `(${params.map(p => {
      const type = p.max_length ? `${p.data_type}(${p.max_length})` : p.data_type;
      return `${p.name} ${type}`;
    }).join(', ')})`;
  };

  const formatDate = (dateString: string | null) => {
    if (!dateString) return 'N/A';
    return new Date(dateString).toLocaleDateString('en-US', {
      year: 'numeric',
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit'
    });
  };

  const handleAccordionChange = (panel: string) => (event: React.SyntheticEvent, isExpanded: boolean) => {
    setExpandedAccordion(isExpanded ? panel : false);
  };

  if (loading) {
    return (
      <LoadingSpinner
        variant="fullscreen"
        message="Loading stored procedures and functions..."
        size="large"
      />
    );
  }

  return (
    <Box>
      <Stack direction="row" justifyContent="space-between" alignItems="center" sx={{ mb: 2 }}>
        <Typography variant="h6">Stored Procedures & Functions</Typography>
        <Button
          startIcon={<RefreshIcon />}
          onClick={loadStoredProcedures}
          size="small"
          disabled={loading}
        >
          Refresh
        </Button>
      </Stack>

      <Grid container spacing={2}>
        {/* Left Panel - List of Procedures and Functions */}
        <Grid item xs={12} md={3}>
          <Card sx={{ height: 'calc(100vh - 280px)', minHeight: '600px', display: 'flex', flexDirection: 'column' }}>
            <CardContent sx={{ flex: 1, overflow: 'auto', p: 1 }}>
              {/* Procedures Accordion */}
              <Accordion
                expanded={expandedAccordion === 'procedures'}
                onChange={handleAccordionChange('procedures')}
                elevation={0}
                sx={{ border: 'none', '&:before': { display: 'none' } }}
              >
                <AccordionSummary
                  expandIcon={<ExpandMoreIcon />}
                  sx={{ px: 1, minHeight: 48, '& .MuiAccordionSummary-content': { my: 1 } }}
                >
                  <Stack direction="row" spacing={1} alignItems="center">
                    <CodeIcon sx={{ fontSize: 20 }} />
                    <Typography>Procedures</Typography>
                    <Chip label={procedures.length} size="small" color="primary" />
                  </Stack>
                </AccordionSummary>
                <AccordionDetails sx={{ p: 0 }}>
                  <List dense sx={{ maxHeight: 'calc(40vh - 150px)', minHeight: 200, overflow: 'auto' }}>
                    {procedures.map((proc) => {
                      const parameterCount = Array.isArray(proc.parameters) ? proc.parameters.length : 0;
                      return (
                        <ListItem key={proc.name} disablePadding>
                          <ListItemButton
                            selected={selectedItem?.name === proc.name}
                            onClick={() => setSelectedItem(proc)}
                          >
                            <ListItemText
                              primary={proc.name}
                              secondary={`${parameterCount} parameters`}
                              primaryTypographyProps={{ fontSize: 14 }}
                              secondaryTypographyProps={{ fontSize: 12 }}
                            />
                          </ListItemButton>
                        </ListItem>
                      );
                    })}
                    {procedures.length === 0 && (
                      <ListItem>
                        <ListItemText
                          primary="No stored procedures found"
                          secondary="Database may not have any procedures"
                          primaryTypographyProps={{ fontSize: 14, color: 'text.secondary' }}
                          secondaryTypographyProps={{ fontSize: 12 }}
                        />
                      </ListItem>
                    )}
                  </List>
                </AccordionDetails>
              </Accordion>

              {/* Functions Accordion */}
              <Accordion
                expanded={expandedAccordion === 'functions'}
                onChange={handleAccordionChange('functions')}
                elevation={0}
                sx={{ border: 'none', '&:before': { display: 'none' } }}
              >
                <AccordionSummary
                  expandIcon={<ExpandMoreIcon />}
                  sx={{ px: 1, minHeight: 48, '& .MuiAccordionSummary-content': { my: 1 } }}
                >
                  <Stack direction="row" spacing={1} alignItems="center">
                    <FunctionsIcon sx={{ fontSize: 20 }} />
                    <Typography>Functions</Typography>
                    <Chip label={functions.length} size="small" color="secondary" />
                  </Stack>
                </AccordionSummary>
                <AccordionDetails sx={{ p: 0 }}>
                  <List dense sx={{ maxHeight: 'calc(40vh - 150px)', minHeight: 200, overflow: 'auto' }}>
                    {functions.map((func) => {
                      const parameterCount = Array.isArray(func.parameters) ? func.parameters.length : 0;
                      return (
                        <ListItem key={func.name} disablePadding>
                          <ListItemButton
                            selected={selectedItem?.name === func.name}
                            onClick={() => setSelectedItem(func)}
                          >
                            <ListItemText
                              primary={func.name}
                              secondary={`${parameterCount} parameters`}
                              primaryTypographyProps={{ fontSize: 14 }}
                              secondaryTypographyProps={{ fontSize: 12 }}
                            />
                          </ListItemButton>
                        </ListItem>
                      );
                    })}
                    {functions.length === 0 && (
                      <ListItem>
                        <ListItemText
                          primary="No functions found"
                          secondary="Database may not have any functions"
                          primaryTypographyProps={{ fontSize: 14, color: 'text.secondary' }}
                          secondaryTypographyProps={{ fontSize: 12 }}
                        />
                      </ListItem>
                    )}
                  </List>
                </AccordionDetails>
              </Accordion>
            </CardContent>
          </Card>
        </Grid>

        {/* Right Panel - Selected Item Details */}
        <Grid item xs={12} md={9}>
          {selectedItem ? (
            <Card sx={{ height: 'calc(100vh - 280px)', minHeight: '600px', display: 'flex', flexDirection: 'column' }}>
              <CardContent sx={{ flex: 1, overflow: 'auto', display: 'flex', flexDirection: 'column' }}>
                <Stack direction="row" justifyContent="space-between" alignItems="center" sx={{ mb: 2 }}>
                  <Box>
                    <Typography variant="h6" sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                      {selectedItem.type === 'PROCEDURE' ? <CodeIcon /> : <FunctionsIcon />}
                      {selectedItem.name}
                    </Typography>
                    <Typography variant="body2" color="text.secondary">
                      {selectedItem.type}
                    </Typography>
                  </Box>
                  <Tooltip title="Copy SQL definition">
                    <IconButton
                      size="small"
                      onClick={() => handleCopyDefinition(selectedItem.definition)}
                    >
                      <ContentCopyIcon />
                    </IconButton>
                  </Tooltip>
                </Stack>

                <Divider sx={{ my: 2 }} />

                {/* Collapsible Metadata */}
                <Accordion
                  expanded={metadataExpanded}
                  onChange={(_, isExpanded) => setMetadataExpanded(isExpanded)}
                  elevation={0}
                  sx={{ 
                    border: '1px solid',
                    borderColor: 'divider',
                    borderRadius: 1,
                    mb: 2,
                    '&:before': { display: 'none' }
                  }}
                >
                  <AccordionSummary
                    expandIcon={<ExpandMoreIcon />}
                    sx={{ minHeight: 40, '& .MuiAccordionSummary-content': { my: 1 } }}
                  >
                    <Typography variant="subtitle2">Metadata</Typography>
                  </AccordionSummary>
                  <AccordionDetails sx={{ pt: 0 }}>
                    <Stack spacing={1}>
                      <Typography variant="body2">
                        <strong>Created:</strong> {formatDate(selectedItem.created_date)}
                      </Typography>
                      <Typography variant="body2">
                        <strong>Modified:</strong> {formatDate(selectedItem.modified_date)}
                      </Typography>
                    </Stack>
                  </AccordionDetails>
                </Accordion>

                {/* Collapsible Parameters */}
                {selectedParameters.length > 0 && (
                  <Accordion
                    expanded={parametersExpanded}
                    onChange={(_, isExpanded) => setParametersExpanded(isExpanded)}
                    elevation={0}
                    sx={{ 
                      border: '1px solid',
                      borderColor: 'divider',
                      borderRadius: 1,
                      mb: 2,
                      '&:before': { display: 'none' }
                    }}
                  >
                    <AccordionSummary
                      expandIcon={<ExpandMoreIcon />}
                      sx={{ minHeight: 40, '& .MuiAccordionSummary-content': { my: 1 } }}
                    >
                      <Typography variant="subtitle2">
                        Parameters ({selectedParameters.length})
                      </Typography>
                    </AccordionSummary>
                    <AccordionDetails sx={{ pt: 0 }}>
                      <List dense>
                        {selectedParameters.map((param, index) => (
                          <ListItem key={index} sx={{ py: 0 }}>
                            <ListItemText
                              primary={
                                <Stack direction="row" spacing={1} alignItems="center">
                                  <Typography variant="body2" component="span" sx={{ fontFamily: 'monospace' }}>
                                    {param.name}
                                  </Typography>
                                  <Chip 
                                    label={param.data_type} 
                                    size="small" 
                                    variant="outlined"
                                    sx={{ height: 20 }}
                                  />
                                  {param.max_length && (
                                    <Typography variant="caption" color="text.secondary">
                                      ({param.max_length})
                                    </Typography>
                                  )}
                                  <Chip 
                                    label={param.mode} 
                                    size="small" 
                                    color={param.mode === 'OUT' ? 'secondary' : 'default'}
                                    sx={{ height: 20 }}
                                  />
                                </Stack>
                              }
                            />
                          </ListItem>
                        ))}
                      </List>
                    </AccordionDetails>
                  </Accordion>
                )}

                {/* SQL Definition */}
                <Box sx={{ flex: 1, display: 'flex', flexDirection: 'column', minHeight: 0 }}>
                  <Typography variant="subtitle2" gutterBottom>SQL Definition</Typography>
                  <Paper
                    variant="outlined"
                    sx={{
                      p: 2,
                      bgcolor: 'grey.50',
                      flex: 1,
                      minHeight: 300,
                      overflow: 'auto',
                      '& pre': {
                        margin: 0,
                        fontFamily: 'monospace',
                        fontSize: '0.85rem',
                        whiteSpace: 'pre-wrap',
                        wordBreak: 'break-word'
                      }
                    }}
                  >
                    <pre>{selectedItem.definition}</pre>
                  </Paper>
                </Box>
              </CardContent>
            </Card>
          ) : (
            <Card sx={{ height: 'calc(100vh - 280px)', minHeight: '600px', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
              <CardContent>
                <Box sx={{ textAlign: 'center' }}>
                  <CodeIcon sx={{ fontSize: 48, color: 'text.secondary', mb: 2 }} />
                  <Typography variant="h6" color="text.secondary" gutterBottom>
                    No Procedure or Function Selected
                  </Typography>
                  <Typography variant="body2" color="text.secondary">
                    Select a stored procedure or function from the list to view its details
                  </Typography>
                </Box>
              </CardContent>
            </Card>
          )}
        </Grid>
      </Grid>
    </Box>
  );
};

export default StoredProcedures;
