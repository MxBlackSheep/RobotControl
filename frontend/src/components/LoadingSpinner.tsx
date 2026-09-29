import React from 'react';
import Box from '@mui/material/Box';
import CircularProgress from '@mui/material/CircularProgress';
import LinearProgress from '@mui/material/LinearProgress';
import Typography from '@mui/material/Typography';

interface LoadingSpinnerProps {
  message?: string;
  minHeight?: number;
  /** A full-width bar for long operations instead of a centered spinner. */
  linear?: boolean;
}

/** Loading state for a page or section. Buttons use a small CircularProgress directly. */
const LoadingSpinner: React.FC<LoadingSpinnerProps> = ({ message, minHeight, linear = false }) => (
  <Box
    sx={{ display: 'flex', flexDirection: 'column', justifyContent: 'center', alignItems: linear ? 'stretch' : 'center', gap: 1.5, minHeight }}
  >
    {linear ? <LinearProgress /> : <CircularProgress />}
    {message && <Typography variant="body2" color="text.secondary" textAlign="center">{message}</Typography>}
  </Box>
);

export default LoadingSpinner;
