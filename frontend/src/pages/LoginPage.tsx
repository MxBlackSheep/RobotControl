import React, { useMemo, useState } from 'react';
import {
  Box,
  Card,
  CardContent,
  TextField,
  Button,
  Typography,
  Container,
  Stack,
} from '@mui/material';
import { isAxiosError } from 'axios';
import { useAuth } from '../context/AuthContext';
import ErrorAlert from '../components/ErrorAlert';

type AuthMode = 'login' | 'register';

const LoginPage: React.FC = () => {
  const [mode, setMode] = useState<AuthMode>('login');
  const [username, setUsername] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const { login, register } = useAuth();

  React.useEffect(() => {
    const usernameInput = document.querySelector('input[name="username"]') as HTMLInputElement | null;
    if (usernameInput) {
      setTimeout(() => usernameInput.focus(), 100);
    }
  }, [mode]);

  const headerText = useMemo(
    () => (mode === 'login' ? 'Sign in to PyRobot' : 'Create a PyRobot Account'),
    [mode],
  );

  const submitLabel = mode === 'login' ? 'Sign In' : 'Register & Sign In';

  const handleSubmit = async (event: React.FormEvent) => {
    event.preventDefault();
    setLoading(true);
    setError('');

    try {
      if (mode === 'login') {
        await login(username.trim(), password);
      } else {
        await register(username.trim(), email.trim(), password);
      }
    } catch (err) {
      if (isAxiosError(err)) {
        const message =
          err.response?.data?.error?.message ||
          err.response?.data?.message ||
          (mode === 'login' ? 'Invalid username or password' : 'Registration failed');
        setError(message);
      } else {
        setError(mode === 'login' ? 'Invalid username or password' : 'Registration failed');
      }
    } finally {
      setLoading(false);
    }
  };

  const toggleMode = () => {
    setMode((prev) => (prev === 'login' ? 'register' : 'login'));
    setError('');
  };

  return (
    <Container maxWidth="sm" sx={{ px: { xs: 2, sm: 3 } }}>
      <Box
        sx={{
          minHeight: '100vh',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          py: { xs: 2, sm: 4 },
        }}
      >
        <Card
          sx={{
            width: '100%',
            maxWidth: { xs: '100%', sm: 420 },
            mx: { xs: 1, sm: 0 },
          }}
        >
          <CardContent sx={{ p: { xs: 3, sm: 4 } }}>
            <Stack spacing={2}>
              <Box textAlign="center">
                <Typography
                  variant="h4"
                  gutterBottom
                  sx={{ fontSize: { xs: '1.5rem', sm: '2.125rem' } }}
                >
                  {headerText}
                </Typography>
                <Typography
                  variant="body2"
                  color="textSecondary"
                  sx={{ fontSize: { xs: '0.9rem', sm: '0.95rem' } }}
                >
                  Hamilton VENUS Robot Management Console
                </Typography>
              </Box>

              {error && (
                <ErrorAlert
                  message={error}
                  severity="error"
                  category="authentication"
                  sx={{ mb: 1 }}
                  closable
                  onClose={() => setError('')}
                />
              )}

              <Box
                component="form"
                onSubmit={handleSubmit}
                role="form"
                aria-label={mode === 'login' ? 'Login form' : 'Registration form'}
              >
                <TextField
                  fullWidth
                  label="Username"
                  name="username"
                  value={username}
                  onChange={(event) => setUsername(event.target.value)}
                  margin="normal"
                  required
                  autoComplete="username"
                  inputProps={{
                    'aria-label': 'Username',
                  }}
                  sx={{
                    '& .MuiInputBase-root': {
                      minHeight: { xs: 56, sm: 56 },
                    },
                  }}
                />

                {mode === 'register' && (
                  <TextField
                    fullWidth
                    label="Email"
                    name="email"
                    type="email"
                    value={email}
                    onChange={(event) => setEmail(event.target.value)}
                    margin="normal"
                    required
                    autoComplete="email"
                    inputProps={{
                      'aria-label': 'Email address',
                    }}
                    sx={{
                      '& .MuiInputBase-root': {
                        minHeight: { xs: 56, sm: 56 },
                      },
                    }}
                  />
                )}

                <TextField
                  fullWidth
                  label="Password"
                  name="password"
                  type="password"
                  value={password}
                  onChange={(event) => setPassword(event.target.value)}
                  margin="normal"
                  required
                  autoComplete={mode === 'login' ? 'current-password' : 'new-password'}
                  inputProps={{
                    'aria-label': 'Password',
                  }}
                  helperText={
                    mode === 'register'
                      ? 'Use at least 8 characters. Strong passwords mix numbers, symbols, and case.'
                      : undefined
                  }
                  sx={{
                    '& .MuiInputBase-root': {
                      minHeight: { xs: 56, sm: 56 },
                    },
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
                    fontSize: { xs: '1rem', sm: '0.875rem' },
                  }}
                >
                  {loading ? 'Please wait…' : submitLabel}
                </Button>
              </Box>

              <Stack spacing={1} textAlign="center">
                <Typography variant="caption" color="textSecondary">
                  Default admin: admin / ShouGroupAdmin
                </Typography>
                <Typography variant="caption" color="textSecondary">
                  Forgot your password? Contact a lab admin to reset it.
                </Typography>
              </Stack>

              <Button
                variant="text"
                color="primary"
                onClick={toggleMode}
                sx={{ mt: 1 }}
              >
                {mode === 'login'
                  ? "Don't have an account? Register now"
                  : 'Have an account? Back to sign in'}
              </Button>
            </Stack>
          </CardContent>
        </Card>
      </Box>
    </Container>
  );
};

export default LoginPage;
