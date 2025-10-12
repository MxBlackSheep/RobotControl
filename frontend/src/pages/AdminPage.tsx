import React, { useState } from 'react';
import Box from '@mui/material/Box';
import Typography from '@mui/material/Typography';

import { useAuthContext } from '../context/AuthContext';
import ErrorAlert, { AuthorizationError } from '../components/ErrorAlert';
import UserManagement from '../components/UserManagement';

const AdminPage: React.FC = () => {
  const { user } = useAuthContext();
  const [error, setError] = useState<string | null>(null);

  if (user?.role !== 'admin') {
    return (
      <Box sx={{ p: { xs: 2, md: 4 } }}>
        <AuthorizationError
          title="Access Denied"
          message="Admin privileges are required to access this page."
        />
      </Box>
    );
  }

  return (
    <Box sx={{ p: { xs: 2, md: 4 }, maxWidth: 1200, mx: 'auto' }}>
      <Typography variant="h4" sx={{ fontWeight: 700, mb: 1 }}>
        Administration
      </Typography>
      <Typography variant="body1" color="text.secondary" sx={{ mb: 3 }}>
        Manage user accounts, handle password reset requests, and review access status.
      </Typography>

      {error && (
        <ErrorAlert
          message={error}
          severity="error"
          category="server"
          closable
          onClose={() => setError(null)}
          sx={{ mb: 2 }}
        />
      )}

      <UserManagement onError={setError} />
    </Box>
  );
};

export default AdminPage;
