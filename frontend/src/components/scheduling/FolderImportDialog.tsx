/**
 * Folder Import Dialog Component
 * 
 * Dialog for importing multiple experiment .med files from a folder.
 * Provides folder path input, import progress, and results display.
 */

import React, { useState, useRef } from 'react';
import { useModalFocus } from '../../hooks/useModalFocus';
import {
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  TextField,
  Button,
  Box,
  Alert,
  Typography,
  Stack,
  LinearProgress,
  List,
  ListItem,
  ListItemText,
  Chip,
  InputAdornment,
  IconButton,
  Divider,
  Card,
  CardContent
} from '@mui/material';
import {
  FolderOpen as FolderIcon,
  Upload as UploadIcon,
  CheckCircle as SuccessIcon,
  Error as ErrorIcon,
  Info as InfoIcon,
  CloudUpload as BrowserIcon,
  Edit as ManualIcon
} from '@mui/icons-material';
import { schedulingAPI } from '../../services/schedulingApi';

interface FolderImportDialogProps {
  open: boolean;
  onClose: () => void;
  onImportComplete?: () => void;
  isLocalClient: boolean;
}

const FolderImportDialog: React.FC<FolderImportDialogProps> = ({
  open,
  onClose,
  onImportComplete,
  isLocalClient
}) => {
  const [folderPath, setFolderPath] = useState('');
  const [importing, setImporting] = useState(false);
  const [importResults, setImportResults] = useState<{
    success: boolean;
    new_methods: number;
    updated_methods: number;
    failed_methods: number;
    total_found: number;
    errors: string[];
    methods?: Array<{ name: string; path: string; size: number }>;
  } | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [selectedFiles, setSelectedFiles] = useState<File[]>([]);
  const [importMethod, setImportMethod] = useState<'browser' | 'manual'>('browser');
  const fileInputRef = useRef<HTMLInputElement>(null);

  const handleFolderSelect = (event: React.ChangeEvent<HTMLInputElement>) => {
    if (!isLocalClient) {
      setError('Folder import is only available from the RobotControl host.');
      return;
    }
    const files = Array.from(event.target.files || []);
    
    // Filter for .med files only
    const medFiles = files.filter(file => 
      file.name.toLowerCase().endsWith('.med')
    );
    
    setSelectedFiles(medFiles);
    setError(null);
    
    if (medFiles.length === 0) {
      setError('No .med files found in the selected folder');
    }
  };

  const handleBrowserFolderPicker = () => {
    if (!isLocalClient) {
      setError('Folder import is only available from the RobotControl host.');
      return;
    }
    if (fileInputRef.current) {
      fileInputRef.current.click();
    }
  };

  const handleImportFromBrowser = async () => {
    if (!isLocalClient) {
      setError('Folder import is only available from the RobotControl host.');
      return;
    }
    if (selectedFiles.length === 0) {
      setError('Please select a folder containing .med files');
      return;
    }

    setImporting(true);
    setError(null);
    setImportResults(null);

    try {
      // Process selected files and create metadata
      const fileMetadata = selectedFiles.map(file => {
        // Extract relative path from file.webkitRelativePath
        const relativePath = file.webkitRelativePath || file.name;
        const pathParts = relativePath.split('/');
        const folderName = pathParts[0] || 'Selected Folder';
        
        return {
          name: file.name.replace('.med', ''),
          path: relativePath,
          size: file.size,
          lastModified: new Date(file.lastModified).toISOString(),
          sourceFolder: folderName
        };
      });

      // Send metadata to backend for import
      const response = await schedulingAPI.importExperimentFiles(fileMetadata);
      
      if (response.data.success) {
        setImportResults({
          success: true,
          new_methods: response.data.data.new_methods,
          updated_methods: response.data.data.updated_methods,
          failed_methods: response.data.data.failed_methods || 0,
          total_found: selectedFiles.length,
          errors: response.data.data.errors || [],
          methods: fileMetadata.map(f => ({
            name: f.name,
            path: f.path,
            size: f.size
          }))
        });
        
        if (onImportComplete && (response.data.data.new_methods > 0 || response.data.data.updated_methods > 0)) {
          onImportComplete();
        }
      } else {
        setError(response.data.message || 'Import failed');
      }
    } catch (err) {
      console.error('Import error:', err);
      setError(err instanceof Error ? err.message : 'Failed to import experiments');
    } finally {
      setImporting(false);
    }
  };

  const handleImportFromPath = async () => {
    if (!isLocalClient) {
      setError('Folder import is only available from the RobotControl host.');
      return;
    }
    if (!folderPath.trim()) {
      setError('Please enter a folder path');
      return;
    }

    setImporting(true);
    setError(null);
    setImportResults(null);

    try {
      const response = await schedulingAPI.importExperimentFolder(folderPath);
      
      if (response.data.success || response.data.data.new_methods > 0 || response.data.data.updated_methods > 0) {
        setImportResults(response.data.data);
        
        if (onImportComplete && (response.data.data.new_methods > 0 || response.data.data.updated_methods > 0)) {
          onImportComplete();
        }
      } else {
        setError(response.data.message || 'Import failed');
        if (response.data.data.errors?.length > 0) {
          setError(response.data.data.errors[0]);
        }
      }
    } catch (err) {
      console.error('Import error:', err);
      setError(err instanceof Error ? err.message : 'Failed to import experiments');
    } finally {
      setImporting(false);
    }
  };

  const handleClose = () => {
    if (!importing) {
      setFolderPath('');
      setSelectedFiles([]);
      setImportResults(null);
      setError(null);
      setImportMethod('browser');
      if (fileInputRef.current) {
        fileInputRef.current.value = '';
      }
      onClose();
    }
  };

  // Add modal focus management
  const { modalRef } = useModalFocus({
    isOpen: open,
    onClose: handleClose,
    initialFocusSelector: importMethod === 'browser' ? 'button[aria-label*="Select Folder"]' : 'input[label="Folder Path"]',
    restoreFocus: true,
    trapFocus: true,
    closeOnEscape: true
  });

  const getSamplePaths = () => {
    // Provide example paths based on platform
    const isWindows = navigator.platform.toLowerCase().includes('win');
    
    return isWindows ? [
      'C:\\Program Files (x86)\\HAMILTON\\Methods',
      'C:\\Hamilton\\Methods',
      'D:\\Experiments\\Methods'
    ] : [
      '/usr/local/hamilton/methods',
      '/home/user/hamilton/methods'
    ];
  };

  return (
    <Dialog 
      ref={modalRef}
      open={open} 
      onClose={handleClose} 
      maxWidth="md" 
      fullWidth
      aria-labelledby="folder-import-dialog-title"
      aria-describedby="folder-import-dialog-description"
    >
      <DialogTitle id="folder-import-dialog-title">
        <Stack direction="row" alignItems="center" spacing={1}>
          <FolderIcon color="primary" aria-hidden="true" />
          <Typography variant="h6">Import Experiments from Folder</Typography>
        </Stack>
      </DialogTitle>

      <DialogContent dividers id="folder-import-dialog-description">
        <Stack spacing={3}>
          {/* Instructions */}
          <Alert severity="info" variant="outlined">
            <Typography variant="body2">
              Import all .med experiment files from a folder into the database.
              This allows easy selection in scheduling forms without typing paths.
            </Typography>
          </Alert>

          {/* Method Selection */}
          {!importResults && (
            <Box>
              <Typography variant="subtitle2" gutterBottom>
                Choose Import Method:
              </Typography>
              <Stack direction="row" spacing={2}>
                <Card 
                  variant={importMethod === 'browser' ? 'elevation' : 'outlined'}
                  sx={{ 
                    cursor: 'pointer',
                    border: importMethod === 'browser' ? 2 : 1,
                    borderColor: importMethod === 'browser' ? 'primary.main' : 'divider'
                  }}
                  onClick={() => setImportMethod('browser')}
                >
                  <CardContent sx={{ textAlign: 'center', py: 2 }}>
                    <BrowserIcon color={importMethod === 'browser' ? 'primary' : 'disabled'} sx={{ mb: 1 }} />
                    <Typography variant="body2" color={importMethod === 'browser' ? 'primary' : 'text.secondary'}>
                      Browse Folder
                    </Typography>
                    <Typography variant="caption" display="block">
                      Select folder in browser
                    </Typography>
                  </CardContent>
                </Card>
                <Card 
                  variant={importMethod === 'manual' ? 'elevation' : 'outlined'}
                  sx={{ 
                    cursor: 'pointer',
                    border: importMethod === 'manual' ? 2 : 1,
                    borderColor: importMethod === 'manual' ? 'primary.main' : 'divider'
                  }}
                  onClick={() => setImportMethod('manual')}
                >
                  <CardContent sx={{ textAlign: 'center', py: 2 }}>
                    <ManualIcon color={importMethod === 'manual' ? 'primary' : 'disabled'} sx={{ mb: 1 }} />
                    <Typography variant="body2" color={importMethod === 'manual' ? 'primary' : 'text.secondary'}>
                      Type Path
                    </Typography>
                    <Typography variant="caption" display="block">
                      Enter folder path manually
                    </Typography>
                  </CardContent>
                </Card>
              </Stack>
            </Box>
          )}

          {/* Hidden file input for folder selection */}
          <input
            ref={fileInputRef}
            type="file"
            // @ts-ignore - webkitdirectory is not in standard HTML types but widely supported
            webkitdirectory=""
            multiple
            accept=".med"
            onChange={handleFolderSelect}
            style={{ display: 'none' }}
          />

          {/* Browser Method - Folder Picker */}
          {!importResults && importMethod === 'browser' && (
            <Box>
              <Button
                variant="outlined"
                size="large"
                fullWidth
                startIcon={<FolderIcon />}
                onClick={handleBrowserFolderPicker}
                disabled={importing}
                sx={{ py: 2, mb: 2 }}
              >
                Select Folder Containing .med Files
              </Button>

              <Alert severity="info" variant="outlined" sx={{ mb: 2 }}>
                <Typography variant="body2">
                  <strong>Browser Folder Selection:</strong>
                </Typography>
                <Typography variant="caption" component="div">
                  • Works in Chrome, Firefox, Edge, Safari (modern browsers)
                  <br />
                  • Click button → Select any file in target folder → Browser loads all folder contents
                  <br />
                  • Only .med files will be imported to database
                </Typography>
              </Alert>

              {selectedFiles.length > 0 && (
                <Alert severity="success" variant="outlined">
                  <Typography variant="body2" gutterBottom>
                    <strong>Selected {selectedFiles.length} experiment files:</strong>
                  </Typography>
                  <Box sx={{ maxHeight: 150, overflow: 'auto' }}>
                    {selectedFiles.slice(0, 10).map((file, index) => (
                      <Chip
                        key={index}
                        label={file.name}
                        size="small"
                        sx={{ m: 0.5 }}
                      />
                    ))}
                    {selectedFiles.length > 10 && (
                      <Typography variant="caption" color="text.secondary">
                        ...and {selectedFiles.length - 10} more files
                      </Typography>
                    )}
                  </Box>
                </Alert>
              )}
            </Box>
          )}

          {/* Manual Method - Path Input */}
          {!importResults && importMethod === 'manual' && (
            <>
              <TextField
                label="Folder Path"
                value={folderPath}
                onChange={(e) => setFolderPath(e.target.value)}
                fullWidth
                disabled={importing}
                placeholder="e.g., C:\Hamilton\Methods or /usr/local/hamilton/methods"
                helperText="Enter the full path to a folder containing .med files (copy from File Explorer)"
                InputProps={{
                  startAdornment: (
                    <InputAdornment position="start">
                      <FolderIcon />
                    </InputAdornment>
                  )
                }}
                sx={{ mb: 1 }}
              />
              
              <Alert severity="info" icon={<InfoIcon />} sx={{ mb: 2 }}>
                <Typography variant="body2">
                  <strong>How to get folder path:</strong>
                </Typography>
                <Typography variant="caption" component="div">
                  1. Open File Explorer/Finder
                  <br />
                  2. Navigate to your Hamilton methods folder
                  <br />
                  3. Click the address bar and copy the full path
                  <br />
                  4. Paste it into the field above
                </Typography>
              </Alert>

              {/* Example Paths */}
              <Box>
                <Typography variant="caption" color="text.secondary" gutterBottom>
                  Common Hamilton method locations:
                </Typography>
                <Stack direction="row" spacing={1} flexWrap="wrap" mt={1}>
                  {getSamplePaths().map((path) => (
                    <Chip
                      key={path}
                      label={path}
                      size="small"
                      variant="outlined"
                      onClick={() => setFolderPath(path)}
                      sx={{ mb: 1 }}
                    />
                  ))}
                </Stack>
              </Box>
            </>
          )}

          {/* Error Display */}
          {error && (
            <Alert severity="error" onClose={() => setError(null)}>
              {error}
            </Alert>
          )}

          {/* Import Progress */}
          {importing && (
            <Box>
              <Typography variant="body2" gutterBottom>
                Scanning folder for experiment files...
              </Typography>
              <LinearProgress />
            </Box>
          )}

          {/* Import Results */}
          {importResults && (
            <Box>
              <Alert 
                severity={importResults.success ? "success" : "warning"}
                icon={importResults.success ? <SuccessIcon /> : <InfoIcon />}
              >
                <Typography variant="subtitle2" gutterBottom>
                  Import Summary
                </Typography>
                <Stack spacing={0.5}>
                  <Typography variant="body2">
                    Total files found: <strong>{importResults.total_found}</strong>
                  </Typography>
                  {importResults.new_methods > 0 && (
                    <Typography variant="body2" color="success.main">
                      New methods imported: <strong>{importResults.new_methods}</strong>
                    </Typography>
                  )}
                  {importResults.updated_methods > 0 && (
                    <Typography variant="body2" color="info.main">
                      Existing methods updated: <strong>{importResults.updated_methods}</strong>
                    </Typography>
                  )}
                  {importResults.failed_methods > 0 && (
                    <Typography variant="body2" color="error.main">
                      Failed imports: <strong>{importResults.failed_methods}</strong>
                    </Typography>
                  )}
                </Stack>
              </Alert>

              {/* Method List (show first 10) */}
              {importResults.methods && importResults.methods.length > 0 && (
                <Box>
                  <Typography variant="subtitle2" gutterBottom>
                    Imported Methods {importResults.methods.length > 10 && '(showing first 10)'}:
                  </Typography>
                  <List dense sx={{ maxHeight: 200, overflow: 'auto' }}>
                    {importResults.methods.slice(0, 10).map((method, index) => (
                      <ListItem key={index}>
                        <ListItemText
                          primary={method.name}
                          secondary={`${(method.size / 1024).toFixed(1)} KB`}
                        />
                      </ListItem>
                    ))}
                  </List>
                </Box>
              )}

              {/* Errors */}
              {importResults.errors && importResults.errors.length > 0 && (
                <Alert severity="error" variant="outlined">
                  <Typography variant="subtitle2" gutterBottom>
                    Errors:
                  </Typography>
                  <ul style={{ margin: 0, paddingLeft: 20 }}>
                    {importResults.errors.map((err, index) => (
                      <li key={index}>
                        <Typography variant="caption">{err}</Typography>
                      </li>
                    ))}
                  </ul>
                </Alert>
              )}
            </Box>
          )}
        </Stack>
      </DialogContent>

      <DialogActions>
        <Button onClick={handleClose} disabled={importing}>
          {importResults ? 'Close' : 'Cancel'}
        </Button>
        {!importResults && importMethod === 'browser' && (
          <Button
            onClick={handleImportFromBrowser}
            variant="contained"
            disabled={importing || selectedFiles.length === 0}
            startIcon={<UploadIcon />}
          >
            Import {selectedFiles.length} Files
          </Button>
        )}
        {!importResults && importMethod === 'manual' && (
          <Button
            onClick={handleImportFromPath}
            variant="contained"
            disabled={importing || !folderPath.trim()}
            startIcon={<UploadIcon />}
          >
            Import
          </Button>
        )}
        {importResults && (importResults.new_methods > 0 || importResults.updated_methods > 0) && (
          <Button
            onClick={() => {
              setFolderPath('');
              setImportResults(null);
              setError(null);
            }}
            variant="outlined"
            startIcon={<FolderIcon />}
          >
            Import Another Folder
          </Button>
        )}
      </DialogActions>
    </Dialog>
  );
};

export default FolderImportDialog;
