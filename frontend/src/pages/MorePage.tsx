import Box from '@mui/material/Box';
import ButtonBase from '@mui/material/ButtonBase';
import Typography from '@mui/material/Typography';
import ChevronRight from '@mui/icons-material/ChevronRight';
import { Link } from 'react-router-dom';
import { PageContent, PageHeader } from '../components/PageLayout';
import { useAuth } from '../context/AuthContext';
import { visibleMoreItems } from '../components/navigation';
import { layout } from '../theme';

const group = { bgcolor: 'background.paper', border: 1, borderColor: 'divider', borderRadius: `${layout.radius}px`, overflow: 'hidden' } as const;

/** The phone's More tab: read-only places, one level deep. Changes are made on the workstation. */
export default function MorePage() {
  const { user } = useAuth();
  return <PageContent>
    <PageHeader title="More" />
    <Box component="ul" aria-label="More pages" sx={{ ...group, listStyle: 'none', m: 0, p: 0 }}>
      {visibleMoreItems(user).map(item => <Box component="li" key={item.to} sx={{ '& + &': { borderTop: 1, borderColor: 'surface.rowLine' } }}>
        <ButtonBase component={Link} to={item.to} sx={{ width: '100%', minHeight: 52, px: 2, justifyContent: 'space-between', fontSize: 16 }}>
          {item.label}<ChevronRight aria-hidden sx={{ color: 'text.secondary' }} />
        </ButtonBase>
      </Box>)}
    </Box>
    <Typography component="h2" variant="body2" color="text.secondary" sx={{ mt: 3, mb: 0.5, mx: 0.5 }}>On the workstation</Typography>
    <Typography variant="body2" color="text.secondary" sx={{ ...group, px: 2, py: 1.5 }}>
      Editing schedules, methods, calendar, recovery, maintenance, tip marking, Cytomat changes, database tools and admin.
    </Typography>
  </PageContent>;
}
