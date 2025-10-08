import React, { useEffect, useState } from 'react';
import {
  Box,
  Container,
  Typography,
  Grid,
  Card,
  CardContent,
  List,
  ListItem,
  ListItemText,
  ListItemButton,
  Button,
  Stack,
  FormControlLabel,
  Switch,
  Tooltip,
  Tabs,
  Tab,
  Paper
} from '@mui/material';
import useTheme from '@mui/material/styles/useTheme';
import useMediaQuery from '@mui/material/useMediaQuery';
import { useNavigate } from 'react-router-dom';
import ArrowBackIcon from '@mui/icons-material/ArrowBack';
import StorageIcon from '@mui/icons-material/Storage';
import StarIcon from '@mui/icons-material/Star';
import TableChartIcon from '@mui/icons-material/TableChart';
import CodeIcon from '@mui/icons-material/Code';
import SettingsIcon from '@mui/icons-material/Settings';
import RestoreIcon from '@mui/icons-material/Restore';
import { databaseAPI } from '../services/api';
import DatabaseTable from '../components/DatabaseTable';
import StoredProcedures from '../components/StoredProcedures';
import DatabaseOperations from '../components/DatabaseOperations';
import DatabaseRestore from '../components/DatabaseRestore';
import LoadingSpinner, { PageLoading } from '../components/LoadingSpinner';
import ErrorAlert, { ServerError } from '../components/ErrorAlert';

interface TableInfo {
  name: string;
  schema: string;
  row_count: number;
  is_important?: boolean;
}

const DatabasePage: React.FC = () => {
  const navigate = useNavigate();
  const [tables, setTables] = useState<TableInfo[]>([]);
  const [selectedTable, setSelectedTable] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [showImportantOnly, setShowImportantOnly] = useState(true);
  const [tableStats, setTableStats] = useState({ importantCount: 0, allCount: 0 });
  const [activeTab, setActiveTab] = useState(0);
  const theme = useTheme();
  const isSmallScreen = useMediaQuery(theme.breakpoints.down('sm'));

  useEffect(() => {
    loadTablesAndStatus();
  }, [showImportantOnly]);

  const loadTablesAndStatus = async () => {
    setLoading(true);
    setError(''); // Clear previous errors
    try {
      // Load tables
      const tablesResponse = await databaseAPI.getTables(showImportantOnly);
      
      // Backend response structure for tables (axios wraps response in .data)
      const tableDetails = tablesResponse.data.data.table_details || [];
      const formattedTables = tableDetails.map((table: any) => ({
        name: table.name,
        schema: 'dbo', // Default schema
        row_count: table.has_data ? 1000 : 0, // Placeholder, will get actual count when viewing
        is_important: table.is_important || false
      }));
      setTables(formattedTables);
      
      // Update table statistics
      setTableStats({
        importantCount: tablesResponse.data.data.important_count || 0,
        allCount: tablesResponse.data.data.all_count || 0
      });
    } catch (err) {
      console.error('Database loading error:', err);
      setError('Failed to load database information');
    } finally {
      setLoading(false);
    }
  };

  const handleTableSelect = (tableName: string) => {
    setSelectedTable(tableName);
    setError('');
  };

  const handleError = (errorMessage: string) => {
    setError(errorMessage);
  };

  if (loading) {
    return <PageLoading message="Loading database tables..." />;
  }

  return (
    <Container 
      maxWidth="xl" 
      sx={{ 
        mt: { xs: 1, sm: 2 }, 
        mb: { xs: 1, sm: 2 },
        px: { xs: 1, sm: 2 }
      }}
    >
      {/* Header */}
      <Box sx={{ 
        display: 'flex', 
        alignItems: 'center', 
        mb: { xs: 1, sm: 2 },
        flexWrap: 'wrap',
        gap: 1
      }}>
        <Button
          startIcon={<ArrowBackIcon />}
          onClick={() => navigate('/')}
          size="small"
          sx={{ 
            mr: { xs: 0, sm: 2 },
            minHeight: { xs: 44, sm: 36 }
          }}
        >
          Back
        </Button>
        <Box sx={{ display: 'flex', alignItems: 'center', flexGrow: 1 }}>
          <StorageIcon sx={{ 
            mr: 1, 
            color: 'primary.main', 
            fontSize: { xs: 24, sm: 28 }
          }} />
          <Typography 
            variant="h5"
            sx={{ flexGrow: 1 }}
          >
            Database Browser
          </Typography>
        </Box>
        
        {/* Important tables filter */}
        <Stack
          direction={{ xs: 'column', sm: 'row' }}
          spacing={{ xs: 1, sm: 2 }}
          alignItems={{ xs: 'stretch', sm: 'center' }}
          sx={{ width: { xs: '100%', sm: 'auto' } }}
        >
          <Tooltip title={showImportantOnly ? 
            `Showing ${tableStats.importantCount} important tables only` : 
            `Showing all ${tableStats.allCount} tables`
          }>
            <FormControlLabel
              control={
                <Switch
                  checked={showImportantOnly}
                  onChange={(e) => setShowImportantOnly(e.target.checked)}
                  size="small"
                />
              }
              label="Important tables only"
              sx={{ 
                m: 0,
                justifyContent: { xs: 'flex-start', sm: 'center' }
              }}
            />
          </Tooltip>
        </Stack>
      </Box>

      {error && (
        <ServerError
          message={error}
          retryable={true}
          onRetry={loadTablesAndStatus}
          onClose={() => setError('')}
          sx={{ mb: 2 }}
        />
      )}

      {/* Tabs for different database features */}
      <Paper sx={{ mb: 2, overflowX: 'auto' }}>
        <Tabs
          value={activeTab}
          onChange={(_, v) => setActiveTab(v)}
          aria-label="database tabs"
          variant="scrollable"
          scrollButtons="auto"
          allowScrollButtonsMobile
        >
          <Tab icon={<TableChartIcon />} label="Tables" iconPosition="start" />
          <Tab icon={<CodeIcon />} label={isSmallScreen ? 'Procedures' : 'Stored Procedures'} iconPosition="start" />
          <Tab icon={<RestoreIcon />} label="Restore" iconPosition="start" />
          <Tab icon={<SettingsIcon />} label={isSmallScreen ? 'Ops' : 'Operations'} iconPosition="start" />
        </Tabs>
      </Paper>

      {/* Tab Panel 0: Tables */}
      {activeTab === 0 && (
        <Grid container spacing={{ xs: 1, sm: 2 }}>
          {/* Tables List */}
          <Grid item xs={12} md={3} lg={2}>
            <Card sx={{ 
              height: { xs: 'auto', md: 'calc(100vh - 240px)' }, 
              minHeight: { xs: 'auto', md: '500px' },
              mb: { xs: 2, md: 0 }
            }}>
            <CardContent sx={{ p: { xs: 2, sm: 3 } }}>
              <Typography 
                variant="h6" 
                gutterBottom
                sx={{ fontSize: { xs: '1rem', sm: '1.25rem' } }}
              >
                {showImportantOnly ? 'Important Tables' : 'All Tables'} ({tables.length})
                {!showImportantOnly && tableStats.importantCount > 0 && (
                  <Typography component="span" variant="body2" color="textSecondary">
                    {' '}• {tableStats.importantCount} important
                  </Typography>
                )}
              </Typography>
              
              <List 
                dense 
                sx={{ 
                  maxHeight: { xs: '300px', md: 'calc(100vh - 350px)' }, 
                  minHeight: { xs: '200px', md: '300px' }, 
                  overflow: 'auto' 
                }}
              >
                {tables.map((table) => (
                  <ListItem key={table.name} disablePadding>
                    <ListItemButton
                      selected={selectedTable === table.name}
                      onClick={() => handleTableSelect(table.name)}
                      sx={{ 
                        minHeight: { xs: 44, sm: 36 },
                        borderRadius: 1,
                        mb: 0.5
                      }}
                    >
                      <ListItemText
                        primary={
                          <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                            {table.is_important && (
                              <StarIcon 
                                sx={{ fontSize: 16, color: 'orange' }} 
                                titleAccess="Important table"
                              />
                            )}
                            <Typography 
                              variant="body2" 
                              sx={{ 
                                fontSize: { xs: '0.875rem', sm: '0.875rem' },
                                fontWeight: selectedTable === table.name ? 600 : 400
                              }}
                            >
                              {table.name}
                            </Typography>
                          </Box>
                        }
                        secondary={
                          <Typography 
                            variant="caption" 
                            color="textSecondary"
                            sx={{ fontSize: '0.75rem' }}
                          >
                            {table.row_count.toLocaleString()} rows
                          </Typography>
                        }
                      />
                    </ListItemButton>
                  </ListItem>
                ))}
              </List>
              
              {tables.length === 0 && (
                <Typography variant="body2" color="textSecondary" sx={{ textAlign: 'center', py: 2 }}>
                  No tables found
                </Typography>
              )}
              
              <Box sx={{ mt: 2, pt: 2, borderTop: 1, borderColor: 'divider' }}>
                <Button
                  fullWidth
                  size="small"
                  onClick={loadTablesAndStatus}
                  disabled={loading}
                  sx={{ minHeight: { xs: 44, sm: 36 } }}
                >
                  Refresh Tables
                </Button>
              </Box>
            </CardContent>
          </Card>
        </Grid>

          {/* Table Data */}
          <Grid item xs={12} md={9} lg={10}>
            {selectedTable ? (
              <Card sx={{ 
                height: { xs: 'auto', md: 'calc(100vh - 240px)' }, 
                minHeight: { xs: 'auto', md: '500px' }, 
                overflow: 'hidden' 
              }}>
                <CardContent sx={{ height: '100%', p: { xs: 1, sm: 2 }, display: 'flex', flexDirection: 'column' }}>
                  <Typography 
                    variant="h6" 
                    gutterBottom 
                    sx={{ 
                      display: 'flex', 
                      alignItems: 'center',
                      fontSize: { xs: '1rem', sm: '1.25rem' }
                    }}
                  >
                    <TableChartIcon sx={{ mr: 1, fontSize: { xs: 18, sm: 20 } }} />
                    {selectedTable}
                  </Typography>
                  <Box sx={{ flex: 1, minHeight: 0 }}>
                    <DatabaseTable
                      tableName={selectedTable}
                      onError={handleError}
                    />
                  </Box>
                </CardContent>
              </Card>
            ) : (
              <Card sx={{ 
                height: { xs: 'auto', md: 'calc(100vh - 240px)' }, 
                minHeight: { xs: '300px', md: '500px' } 
              }}>
                <CardContent sx={{ p: { xs: 2, sm: 3 } }}>
                  <Box sx={{ textAlign: 'center', py: { xs: 4, sm: 8 } }}>
                    <TableChartIcon sx={{ 
                      fontSize: { xs: 48, sm: 64 }, 
                      color: 'text.secondary', 
                      mb: 2 
                    }} />
                    <Typography 
                      variant="h6" 
                      color="textSecondary" 
                      gutterBottom
                    >
                      Select a table to view its data
                    </Typography>
                    <Typography variant="body2" color="textSecondary">
                      Choose from the list of available tables {window.innerWidth < 768 ? 'above' : 'on the left'} to browse data
                    </Typography>
                  </Box>
                </CardContent>
              </Card>
            )}
          </Grid>
        </Grid>
      )}

      {/* Tab Panel 1: Stored Procedures */}
      {activeTab === 1 && (
        <Box>
          <StoredProcedures onError={handleError} />
        </Box>
      )}

      {/* Tab Panel 2: Database Restore */}
      {activeTab === 2 && (
        <Box>
          <DatabaseRestore onError={handleError} />
        </Box>
      )}

      {/* Tab Panel 3: Database Operations */}
      {activeTab === 3 && (
        <Box>
          <DatabaseOperations onError={handleError} />
        </Box>
      )}
    </Container>
  );
};

export default DatabasePage;
