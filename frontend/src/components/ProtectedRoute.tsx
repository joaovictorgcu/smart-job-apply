import type { ReactNode } from 'react';
import { Navigate, useLocation } from 'react-router-dom';

import { useAuth } from '@/hooks/useAuth';

import { FullPageSpinner } from './Spinner';

/**
 * Renders `children` only for a confirmed session. While /auth/me is still in
 * flight we show a spinner rather than a redirect, so a page reload with a valid
 * token does not bounce the user to the login screen.
 */
export function ProtectedRoute({ children }: { children: ReactNode }) {
  const { user, isLoading } = useAuth();
  const location = useLocation();

  if (isLoading) {
    return <FullPageSpinner label="Restoring session" />;
  }

  if (!user) {
    return <Navigate to="/login" replace state={{ from: location.pathname + location.search }} />;
  }

  return <>{children}</>;
}
