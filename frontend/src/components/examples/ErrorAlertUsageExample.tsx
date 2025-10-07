/**
 * ErrorAlert Usage Examples
 * 
 * Demonstrates various configurations and use cases for the ErrorAlert component
 * This file serves as documentation for developers
 */

import React from 'react';

// Optimized Material-UI imports
import Box from '@mui/material/Box';
import Card from '@mui/material/Card';
import CardContent from '@mui/material/CardContent';
import Typography from '@mui/material/Typography';
import Button from '@mui/material/Button';
import Grid from '@mui/material/Grid';
import Divider from '@mui/material/Divider';

import ErrorAlert, {
  NetworkError,
  AuthenticationError,
  AuthorizationError,
  ValidationError,
  ServerError,
  SuccessAlert,
  createErrorFromStatus
} from '../ErrorAlert';

// Example 1: Basic error alert variants
export const BasicErrorAlertsExample: React.FC = () => (
  <Box>
    <Typography variant="h6" gutterBottom>
      Basic Error Alert Variants
    </Typography>
    <Grid container spacing={2}>
      <Grid item xs={12}>
        <ErrorAlert
          severity="error"
          message="This is a critical error that requires immediate attention."
          title="Critical Error"
        />
      </Grid>
      <Grid item xs={12}>
        <ErrorAlert
          severity="warning"
          message="This is a warning about a potential issue."
          title="Warning"
        />
      </Grid>
      <Grid item xs={12}>
        <ErrorAlert
          severity="info"
          message="This is an informational message."
          title="Information"
        />
      </Grid>
      <Grid item xs={12}>
        <ErrorAlert
          severity="success"
          message="Operation completed successfully!"
          title="Success"
        />
      </Grid>
    </Grid>
  </Box>
);

// Example 2: Predefined error components
export const PredefinedErrorsExample: React.FC = () => {
  const handleRetry = async () => {
    console.log('Retrying operation...');
    // Simulate retry delay
    await new Promise(resolve => setTimeout(resolve, 1000));
  };

  const handleClose = () => {
    console.log('Alert closed');
  };

  return (
    <Box>
      <Typography variant="h6" gutterBottom>
        Predefined Error Components
      </Typography>
      <Grid container spacing={2}>
        <Grid item xs={12}>
          <NetworkError
            message="Failed to connect to the PyRobot API server."
            onRetry={handleRetry}
            onClose={handleClose}
          />
        </Grid>
        <Grid item xs={12}>
          <AuthenticationError
            message="Your session has expired. Please log in again."
            onClose={handleClose}
          />
        </Grid>
        <Grid item xs={12}>
          <AuthorizationError
            message="Admin privileges required to access this feature."
            onClose={handleClose}
          />
        </Grid>
        <Grid item xs={12}>
          <ValidationError
            message="Please enter a valid experiment name (3-50 characters)."
            onClose={handleClose}
          />
        </Grid>
        <Grid item xs={12}>
          <ServerError
            message="Database connection failed. The server is temporarily unavailable."
            onRetry={handleRetry}
            onClose={handleClose}
          />
        </Grid>
        <Grid item xs={12}>
          <SuccessAlert
            message="Experiment scheduled successfully!"
            title="Success"
          />
        </Grid>
      </Grid>
    </Box>
  );
};

// Example 3: Interactive error alert with retry functionality
export const InteractiveErrorExample: React.FC = () => {
  const [retrying, setRetrying] = React.useState(false);
  const [error, setError] = React.useState<string | null>(
    'Failed to load experiment data from the database.'
  );

  const handleRetry = async () => {
    setRetrying(true);
    try {
      // Simulate API call
      await new Promise(resolve => setTimeout(resolve, 2000));
      // Simulate success - remove error
      setError(null);
    } catch (err) {
      console.error('Retry failed:', err);
    } finally {
      setRetrying(false);
    }
  };

  const handleClose = () => {
    setError(null);
  };

  const triggerError = () => {
    setError('Failed to load experiment data from the database.');
  };

  return (
    <Card>
      <CardContent>
        <Typography variant="h6" gutterBottom>
          Interactive Error Alert
        </Typography>
        
        {error && (
          <Box sx={{ mb: 2 }}>
            <ErrorAlert
              message={error}
              category="server"
              severity="error"
              retryable={true}
              retrying={retrying}
              onRetry={handleRetry}
              onClose={handleClose}
              detailed={true}
              details={`Error Code: DB_CONNECTION_FAILED
Timestamp: ${new Date().toISOString()}
Server: PyRobot Database Server
Connection: LOCALHOST\\HAMILTON
Database: EvoYeast`}
            />
          </Box>
        )}

        <Box sx={{ display: 'flex', gap: 2 }}>
          <Button
            variant="contained"
            color="error"
            onClick={triggerError}
            disabled={!!error}
          >
            Trigger Error
          </Button>
          {error && (
            <Typography variant="body2" color="text.secondary" sx={{ alignSelf: 'center' }}>
              Try the retry button or close the alert
            </Typography>
          )}
        </Box>
      </CardContent>
    </Card>
  );
};

// Example 4: HTTP status code error generation
export const HttpStatusErrorsExample: React.FC = () => {
  const statusCodes = [401, 403, 404, 408, 500, 502];
  const [selectedStatus, setSelectedStatus] = React.useState<number | null>(null);

  const handleStatusClick = (status: number) => {
    setSelectedStatus(status);
  };

  const handleClose = () => {
    setSelectedStatus(null);
  };

  return (
    <Card>
      <CardContent>
        <Typography variant="h6" gutterBottom>
          HTTP Status Code Error Generation
        </Typography>
        
        <Typography variant="body2" color="text.secondary" paragraph>
          Click a status code to see the corresponding error alert:
        </Typography>

        <Box sx={{ display: 'flex', gap: 1, mb: 3, flexWrap: 'wrap' }}>
          {statusCodes.map((status) => (
            <Button
              key={status}
              variant="outlined"
              size="small"
              onClick={() => handleStatusClick(status)}
            >
              {status}
            </Button>
          ))}
        </Box>

        {selectedStatus && (
          <ErrorAlert
            {...createErrorFromStatus(
              selectedStatus,
              undefined,
              `HTTP ${selectedStatus} error occurred while processing the request.`
            )}
            onRetry={selectedStatus >= 500 ? () => console.log('Retrying...') : undefined}
            onClose={handleClose}
            detailed={true}
          />
        )}
      </CardContent>
    </Card>
  );
};

// Example 5: Compact and full-width variants
export const VariantExamples: React.FC = () => (
  <Box>
    <Typography variant="h6" gutterBottom>
      Variant Examples
    </Typography>
    
    <Typography variant="body2" gutterBottom>
      Compact variant (for smaller spaces):
    </Typography>
    <ErrorAlert
      message="Compact error message"
      severity="warning"
      compact={true}
      sx={{ mb: 2 }}
    />

    <Typography variant="body2" gutterBottom>
      Full-width variant:
    </Typography>
    <ErrorAlert
      message="Full-width error message that spans the entire container"
      severity="error"
      fullWidth={true}
      sx={{ mb: 2 }}
    />

    <Typography variant="body2" gutterBottom>
      Auto-dismiss (5 seconds):
    </Typography>
    <ErrorAlert
      message="This alert will automatically disappear after 5 seconds"
      severity="info"
      autoHideDuration={5000}
    />
  </Box>
);

// Usage patterns documentation:
//
// 1. Replace basic Alert components:
//    OLD: <Alert severity="error">{error}</Alert>
//    NEW: <ErrorAlert message={error} severity="error" />
//
// 2. For API errors with retry:
//    <ErrorAlert
//      message="Failed to load data"
//      category="network"
//      retryable={true}
//      onRetry={handleRetry}
//    />
//
// 3. For HTTP status-based errors:
//    const errorProps = createErrorFromStatus(response.status, response.message);
//    <ErrorAlert {...errorProps} onRetry={handleRetry} />
//
// 4. For authentication errors:
//    <AuthenticationError
//      message="Session expired"
//      onClose={() => navigate('/login')}
//    />
//
// 5. For success messages:
//    <SuccessAlert message="Data saved successfully!" />

export default {
  BasicErrorAlertsExample,
  PredefinedErrorsExample,
  InteractiveErrorExample,
  HttpStatusErrorsExample,
  VariantExamples,
};