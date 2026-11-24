import { useAuth } from '../context/AuthContext';
import { allowedSections } from './navigation';
import { headerLink } from './PageLayout';

export default function ManagePackagesLink() {
  const { user } = useAuth();
  return allowedSections('/database', user).some(section => section.id === 'packages')
    ? headerLink('/database?section=packages', 'Manage packages') : null;
}
