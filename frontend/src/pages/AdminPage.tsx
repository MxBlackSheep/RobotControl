import { useModuleSection } from '../components/navigation';
import { PageContent, PageHeader } from '../components/PageLayout';
import React, { useState } from 'react';
import Box from '@mui/material/Box';
import Typography from '@mui/material/Typography';

import { useAuthContext } from '../context/AuthContext';
import ErrorAlert, { AuthorizationError } from '../components/ErrorAlert';
import UserManagement from '../components/UserManagement';
import SQLiteHealthPanel from '../components/SQLiteHealthPanel';
import { isLocalUser } from '../components/navigation';

const AdminPage: React.FC = () => {
  const { user } = useAuthContext();
  const [section] = useModuleSection('/admin', user);
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
    <PageContent>
      <PageHeader title="Administration" description={section === 0 ? "Update user email addresses or remove accounts that should no longer have access." : "Review and resolve password reset requests."} />

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

      <UserManagement section={section} onError={setError} />
      {isLocalUser(user) && <SQLiteHealthPanel />}
    </PageContent>
  );
};

export default AdminPage;
