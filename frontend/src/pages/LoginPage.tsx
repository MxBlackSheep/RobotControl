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
  Alert,
} from '@mui/material';
import { isAxiosError } from 'axios';
import { useAuth } from '../context/AuthContext';
import ErrorAlert from '../components/ErrorAlert';
import { authAPI } from '../services/api';

type AuthMode = 'login' | 'register' | 'forgot';

const LoginPage: React.FC = () => {
  const [mode, setMode] = useState<AuthMode>('login');
  const [username, setUsername] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [note, setNote] = useState('');
  const [error, setError] = useState('');
  const [successMessage, setSuccessMessage] = useState('');
  const [loading, setLoading] = useState(false);
  const { login, register } = useAuth();

  React.useEffect(() => {
    const usernameInput = document.querySelector('input[name="username"]') as HTMLInputElement | null;
    if (usernameInput) {
      setTimeout(() => usernameInput.focus(), 100);
    }
  }, [mode]);

  const headerText = useMemo(() => {
    switch (mode) {
      case 'register':
        return 'Create a PyRobot Account';
      case 'forgot':
        return 'Request a Password Reset';
      case 'login':
      default:
        return 'Sign in to PyRobot';
    }
  }, [mode]);

  const submitLabel = useMemo(() => {
    switch (mode) {
      case 'register':
        return 'Register & Sign In';
      case 'forgot':
        return 'Send Reset Request';
      case 'login':
      default:
        return 'Sign In';
    }
  }, [mode]);

  const handleSubmit = async (event: React.FormEvent) => {
    event.preventDefault();
    setLoading(true);
    setError('');
     setSuccessMessage('');

    try {
      if (mode === 'login') {
        await login(username.trim(), password);
      } else if (mode === 'register') {
        await register(username.trim(), email.trim(), password);
      } else {
        if (!username.trim() && !email.trim()) {
          setError('Provide a username or email so we can locate your account');
          return;
        }
        await authAPI.requestPasswordReset({
          username: username.trim() || undefined,
          email: email.trim() || undefined,
          note: note.trim() || undefined,
        });
        setSuccessMessage('Request submitted. An administrator will follow up soon.');
        setUsername('');
        setEmail('');
        setPassword('');
        setNote('');
      }
    } catch (err) {
      if (isAxiosError(err)) {
        const message =
          err.response?.data?.error?.message ||
          err.response?.data?.message ||
          (mode === 'login'
            ? 'Invalid username or password'
            : mode === 'register'
              ? 'Registration failed'
              : 'Unable to submit reset request');
        setError(message);
      } else {
        setError(
          mode === 'login'
            ? 'Invalid username or password'
            : mode === 'register'
              ? 'Registration failed'
              : 'Unable to submit reset request'
        );
      }
    } finally {
      setLoading(false);
    }
  };

  const switchToMode = (nextMode: AuthMode) => {
    setMode(nextMode);
    setError('');
    setSuccessMessage('');
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

              {successMessage && (
                <Alert
                  severity="success"
                  onClose={() => setSuccessMessage('')}
                  sx={{ mb: 1 }}
                >
                  {successMessage}
                </Alert>
              )}

              <Box
                component="form"
                onSubmit={handleSubmit}
                role="form"
                aria-label={mode === 'login'
                  ? 'Login form'
                  : mode === 'register'
                    ? 'Registration form'
                    : 'Password reset request form'}
              >
                <TextField
                  fullWidth
                  label="Username"
                  name="username"
                  value={username}
                  onChange={(event) => setUsername(event.target.value)}
                  margin="normal"
                  required={mode !== 'forgot'}
                  autoComplete="username"
                  inputProps={{
                    'aria-label': 'Username',
                  }}
                  helperText={
                    mode === 'forgot' ? 'Provide either your username or email' : undefined
                  }
                  sx={{
                    '& .MuiInputBase-root': {
                      minHeight: { xs: 56, sm: 56 },
                    },
                  }}
                />

                {(mode === 'register' || mode === 'forgot') && (
                  <TextField
                    fullWidth
                    label="Email"
                    name="email"
                    type="email"
                    value={email}
                    onChange={(event) => setEmail(event.target.value)}
                    margin="normal"
                    required={mode === 'register'}
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

                {mode !== 'forgot' ? (
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
                ) : (
                  <TextField
                    fullWidth
                    label="Additional details (optional)"
                    name="note"
                    value={note}
                    onChange={(event) => setNote(event.target.value)}
                    margin="normal"
                    multiline
                    minRows={2}
                    inputProps={{
                      'aria-label': 'Additional details for administrators',
                    }}
                    helperText="Include context to help admins verify your request"
                    sx={{
                      '& .MuiInputBase-root': {
                        minHeight: { xs: 56, sm: 56 },
                      },
                    }}
                  />
                )}

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
                {mode === 'forgot' ? (
                  <Typography variant="caption" color="textSecondary">
                    Submit the form and our admins will follow up with next steps.
                  </Typography>
                ) : (
                  <Typography variant="caption" color="textSecondary">
                    Forgot your password? Submit a reset request or contact a lab admin.
                  </Typography>
                )}
              </Stack>

              <Stack spacing={1} sx={{ mt: 1 }}>
                {mode !== 'login' && (
                  <Button
                    variant="text"
                    color="primary"
                    onClick={() => switchToMode('login')}
                  >
                    Back to sign in
                  </Button>
                )}
                {mode !== 'register' && (
                  <Button
                    variant="text"
                    color="primary"
                    onClick={() => switchToMode('register')}
                  >
                    Need an account? Register now
                  </Button>
                )}
                {mode !== 'forgot' && (
                  <Button
                    variant="text"
                    color="primary"
                    onClick={() => switchToMode('forgot')}
                  >
                    Forgot your password?
                  </Button>
                )}
              </Stack>
            </Stack>
          </CardContent>
        </Card>
      </Box>
    </Container>
  );
};

export default LoginPage;
