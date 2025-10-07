/**
 * CompactBreadcrumbs Component
 * 
 * A compact version of NavigationBreadcrumbs for use in smaller spaces
 * or as an inline navigation helper within specific pages
 */

import React from 'react';
import NavigationBreadcrumbs from './NavigationBreadcrumbs';

interface CompactBreadcrumbsProps {
  /** Custom styling className */
  className?: string;
  /** Maximum number of breadcrumbs to show */
  maxItems?: number;
}

const CompactBreadcrumbs: React.FC<CompactBreadcrumbsProps> = ({
  className,
  maxItems = 3,
}) => {
  return (
    <NavigationBreadcrumbs
      className={className}
      compact={true}
      showIcons={true}
      maxItems={maxItems}
    />
  );
};

export default CompactBreadcrumbs;