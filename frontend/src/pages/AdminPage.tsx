import { useModuleSection } from '../components/navigation';
import { PageContent, PageHeader } from '../components/PageLayout';
import React, { useState } from 'react';

import { useAuthContext } from '../context/AuthContext';
import StatusDialog from '../components/StatusDialog';
import UserManagement from '../components/UserManagement';
import SQLiteHealthPanel from '../components/SQLiteHealthPanel';
import { isLocalUser } from '../components/navigation';

const AdminPage: React.FC = () => {
  const { user } = useAuthContext();
  const [section] = useModuleSection('/admin', user);
  const [error, setError] = useState<string | null>(null);

  return (
    <PageContent variant="task">
      <PageHeader title={section === 2 ? "Storage health" : "Administration"} />

      <StatusDialog status={error ? { title: 'Server Error', message: error, severity: 'error' } : null} onClose={() => setError(null)} />

      {section !== 2 && <UserManagement section={section} onError={setError} />}
      {section === 2 && isLocalUser(user) && <SQLiteHealthPanel />}
    </PageContent>
  );
};

export default AdminPage;
