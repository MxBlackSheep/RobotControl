import React, { useState } from 'react';
import {
  Box,
  Card,
  CardContent,
  TextField,
  Button,
  Typography,
  Container
} from '@mui/material';
import { useAuth } from '../context/AuthContext';
import ErrorAlert from '../components/ErrorAlert';

const LoginPage: React.FC = () => {
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const { login } = useAuth();

  // Focus management for login page
  React.useEffect(() => {
    // Focus the first input when page loads
    const usernameInput = document.querySelector('input[name="username"]') as HTMLInputElement;
    if (usernameInput) {
      setTimeout(() => usernameInput.focus(), 100);
    }
  }, []);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setError('');

    try {
      await login(username, password);
    } catch (err) {
      setError('Invalid username or password');
    } finally {
      setLoading(false);
    }
  };

  return (
    <Container maxWidth="sm" sx={{ px: { xs: 2, sm: 3 } }}>
      <Box
        sx={{
          minHeight: '100vh',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          py: { xs: 2, sm: 4 }
        }}
      >
        <Card sx={{ 
          width: '100%', 
          maxWidth: { xs: '100%', sm: 400 },
          mx: { xs: 1, sm: 0 }
        }}>
          <CardContent sx={{ p: { xs: 3, sm: 4 } }}>
            <Typography 
              variant="h4" 
              align="center" 
              gutterBottom
              sx={{ fontSize: { xs: '1.5rem', sm: '2.125rem' } }}
            >
              PyRobot Simplified
            </Typography>
            <Typography 
              variant="body2" 
              align="center" 
              color="textSecondary" 
              mb={3}
              sx={{ fontSize: { xs: '0.875rem', sm: '0.875rem' } }}
            >
              Hamilton VENUS Robot Management
            </Typography>

            {error && (
              <ErrorAlert
                message={error}
                severity="error"
                category="authentication"
                sx={{ mb: 2 }}
                closable={true}
                onClose={() => setError('')}
              />
            )}

            <form onSubmit={handleSubmit} role="form" aria-label="Login form">
              <TextField
                fullWidth
                label="Username"
                name="username"
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                margin="normal"
                required
                autoFocus
                autoComplete="username"
                inputProps={{
                  'aria-label': 'Username',
                  'aria-describedby': 'username-help'
                }}
                sx={{
                  '& .MuiInputBase-root': {
                    minHeight: { xs: 56, sm: 56 }
                  }
                }}
              />
              <TextField
                fullWidth
                label="Password"
                name="password"
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                margin="normal"
                required
                autoComplete="current-password"
                inputProps={{
                  'aria-label': 'Password',
                  'aria-describedby': 'password-help'
                }}
                sx={{
                  '& .MuiInputBase-root': {
                    minHeight: { xs: 56, sm: 56 }
                  }
                }}
              />
              <Button
                type="submit"
                fullWidth
                variant="contained"
                size="large"
                disabled={loading}
                sx={{ 
                  mt: 3,
                  minHeight: { xs: 48, sm: 42 },
                  fontSize: { xs: '1rem', sm: '0.875rem' }
                }}
              >
                {loading ? 'Signing In...' : 'Sign In'}
              </Button>
            </form>

            <Box sx={{ mt: 2, textAlign: 'center' }}>
              <Typography 
                id="username-help"
                variant="caption" 
                color="textSecondary"
                aria-label="Login help information"
              >
                Default login: admin / PyRobot_Admin_2025!
              </Typography>
              <div id="password-help" style={{ display: 'none' }}>
                Enter your password to access the PyRobot system
              </div>
            </Box>
          </CardContent>
        </Card>
      </Box>
    </Container>
  );
};

export default LoginPage;