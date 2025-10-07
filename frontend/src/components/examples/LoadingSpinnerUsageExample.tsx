/**
 * LoadingSpinner Usage Examples
 * 
 * Demonstrates various configurations and use cases for the LoadingSpinner component
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

import LoadingSpinner, { 
  TableLoading, 
  PageLoading, 
  ButtonLoading, 
  CardLoading 
} from '../LoadingSpinner';

// Example 1: Basic spinner variants
export const SpinnerVariantsExample: React.FC = () => (
  <Card>
    <CardContent>
      <Typography variant="h6" gutterBottom>
        Spinner Variants
      </Typography>
      <Grid container spacing={3}>
        <Grid item xs={12} md={3}>
          <Typography variant="body2" gutterBottom>Spinner (Default)</Typography>
          <LoadingSpinner variant="spinner" message="Loading data..." />
        </Grid>
        <Grid item xs={12} md={3}>
          <Typography variant="body2" gutterBottom>Linear Progress</Typography>
          <LoadingSpinner variant="linear" message="Processing..." />
        </Grid>
        <Grid item xs={12} md={3}>
          <Typography variant="body2" gutterBottom>Inline Loading</Typography>
          <LoadingSpinner variant="inline" size="small" message="Saving..." />
        </Grid>
        <Grid item xs={12} md={3}>
          <Typography variant="body2" gutterBottom>Skeleton Loading</Typography>
          <LoadingSpinner variant="skeleton" lines={3} message="Loading content..." />
        </Grid>
      </Grid>
    </CardContent>
  </Card>
);

// Example 2: Size variations
export const SizeVariationsExample: React.FC = () => (
  <Card>
    <CardContent>
      <Typography variant="h6" gutterBottom>
        Size Variations
      </Typography>
      <Box sx={{ display: 'flex', gap: 4, alignItems: 'center' }}>
        <Box>
          <Typography variant="body2" gutterBottom>Small</Typography>
          <LoadingSpinner size="small" />
        </Box>
        <Box>
          <Typography variant="body2" gutterBottom>Medium</Typography>
          <LoadingSpinner size="medium" />
        </Box>
        <Box>
          <Typography variant="body2" gutterBottom>Large</Typography>
          <LoadingSpinner size="large" />
        </Box>
        <Box>
          <Typography variant="body2" gutterBottom>Custom (80px)</Typography>
          <LoadingSpinner size={80} />
        </Box>
      </Box>
    </CardContent>
  </Card>
);

// Example 3: Predefined components
export const PredefinedComponentsExample: React.FC = () => (
  <Box>
    <Typography variant="h6" gutterBottom>
      Predefined Loading Components
    </Typography>
    <Grid container spacing={3}>
      <Grid item xs={12} md={6}>
        <Typography variant="body2" gutterBottom>Table Loading</Typography>
        <TableLoading rows={4} />
      </Grid>
      <Grid item xs={12} md={6}>
        <Typography variant="body2" gutterBottom>Card Loading</Typography>
        <CardLoading lines={5} message="Loading dashboard data..." />
      </Grid>
      <Grid item xs={12}>
        <Typography variant="body2" gutterBottom>Page Loading</Typography>
        <Box sx={{ border: 1, borderColor: 'divider', borderRadius: 1 }}>
          <PageLoading message="Loading application..." />
        </Box>
      </Grid>
    </Grid>
  </Box>
);

// Example 4: Button integration
export const ButtonIntegrationExample: React.FC = () => {
  const [loading, setLoading] = React.useState(false);
  
  const handleClick = () => {
    setLoading(true);
    setTimeout(() => setLoading(false), 3000);
  };

  return (
    <Card>
      <CardContent>
        <Typography variant="h6" gutterBottom>
          Button Integration
        </Typography>
        <Box sx={{ display: 'flex', gap: 2, alignItems: 'center' }}>
          <Button
            variant="contained"
            onClick={handleClick}
            disabled={loading}
          >
            {loading ? <ButtonLoading message="Processing..." /> : 'Start Process'}
          </Button>
          
          <Button
            variant="outlined"
            disabled={loading}
          >
            {loading ? (
              <LoadingSpinner variant="inline" size="small" />
            ) : (
              'Another Action'
            )}
          </Button>
        </Box>
      </CardContent>
    </Card>
  );
};

// Example 5: Custom skeleton patterns
export const CustomSkeletonExample: React.FC = () => (
  <Card>
    <CardContent>
      <Typography variant="h6" gutterBottom>
        Custom Skeleton Patterns
      </Typography>
      <Grid container spacing={3}>
        <Grid item xs={12} md={4}>
          <Typography variant="body2" gutterBottom>User Profile</Typography>
          <LoadingSpinner
            variant="skeleton"
            lines={4}
            widths={['60%', '100%', '80%', '40%']}
            size="medium"
          />
        </Grid>
        <Grid item xs={12} md={4}>
          <Typography variant="body2" gutterBottom>Article Card</Typography>
          <LoadingSpinner
            variant="skeleton"
            lines={5}
            widths={['100%', '95%', '85%', '90%', '50%']}
            size="small"
          />
        </Grid>
        <Grid item xs={12} md={4}>
          <Typography variant="body2" gutterBottom>Dashboard Widget</Typography>
          <LoadingSpinner
            variant="skeleton"
            lines={3}
            widths={['70%', '100%', '30%']}
            size="large"
          />
        </Grid>
      </Grid>
    </CardContent>
  </Card>
);

// Usage patterns documentation:
// 
// 1. Replace existing CircularProgress:
//    OLD: <CircularProgress size={40} />
//    NEW: <LoadingSpinner size="medium" />
//
// 2. Replace custom skeleton components:
//    OLD: <Skeleton variant="text" width="80%" height={32} />
//    NEW: <LoadingSpinner variant="skeleton" lines={1} widths={['80%']} size="large" />
//
// 3. For page-level loading:
//    <PageLoading message="Loading dashboard..." />
//
// 4. For table loading states:
//    <TableLoading rows={5} />
//
// 5. For button loading states:
//    <Button disabled={loading}>
//      {loading ? <ButtonLoading /> : 'Submit'}
//    </Button>
//
// 6. For fullscreen loading:
//    <LoadingSpinner variant="fullscreen" message="Initializing application..." />

export default {
  SpinnerVariantsExample,
  SizeVariationsExample,
  PredefinedComponentsExample,
  ButtonIntegrationExample,
  CustomSkeletonExample,
};