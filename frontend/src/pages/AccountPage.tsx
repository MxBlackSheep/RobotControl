import React from 'react';
import { Link } from 'react-router-dom';
import Box from '@mui/material/Box';
import Button from '@mui/material/Button';
import ToggleButton from '@mui/material/ToggleButton';
import ToggleButtonGroup from '@mui/material/ToggleButtonGroup';
import Typography from '@mui/material/Typography';
import { PageContent, PageGrid, PageHeader, Panel } from '../components/PageLayout';
import ChangePasswordDialog from '../components/ChangePasswordDialog';
import { useAuth } from '../context/AuthContext';
import { type Appearance, useAppearance } from '../context/AppearanceContext';

const appearances: { value: Appearance; label: string }[] = [
  { value: 'system', label: 'System' }, { value: 'light', label: 'Light' }, { value: 'dark', label: 'Dark' },
];

/** The phone home of the desktop rail's account menu and appearance control. */
export default function AccountPage() {
  const { user, logout } = useAuth();
  const { preference, setPreference } = useAppearance();
  const [passwordOpen, setPasswordOpen] = React.useState(false);
  const roleLabel = user?.role ? user.role.charAt(0).toUpperCase() + user.role.slice(1) : '';
  const action = { minHeight: 44, justifyContent: 'flex-start' } as const;
  return <PageContent reading>
    <PageHeader title="Account" />
    <PageGrid>
      <Panel title="Signed in" span={6}>
        <Typography sx={{ fontSize: 16, fontWeight: 600, overflowWrap: 'anywhere' }}>{user?.username}</Typography>
        <Typography variant="body2" color="text.secondary">{roleLabel}</Typography>
        <Box sx={{ display: 'flex', flexDirection: 'column', gap: 1, mt: 2 }}>
          <Button variant="outlined" sx={action} onClick={() => setPasswordOpen(true)}>Change password</Button>
          <Button variant="outlined" sx={action} component={Link} to="/about">About</Button>
          <Button variant="outlined" color="error" sx={action} onClick={() => logout()}>Log out</Button>
        </Box>
      </Panel>
      <Panel title="Appearance" span={6}>
        <ToggleButtonGroup exclusive fullWidth aria-label="Appearance" value={preference}
          onChange={(_, value: Appearance | null) => { if (value) setPreference(value); }}>
          {appearances.map(option => <ToggleButton key={option.value} value={option.value} sx={{ minHeight: 44 }}>{option.label}</ToggleButton>)}
        </ToggleButtonGroup>
      </Panel>
    </PageGrid>
    <ChangePasswordDialog open={passwordOpen} onClose={() => setPasswordOpen(false)} />
  </PageContent>;
}
