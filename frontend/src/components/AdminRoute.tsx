import { ShieldOff } from 'lucide-react';
import type { ReactNode } from 'react';
import { Link, Navigate, useLocation } from 'react-router-dom';

import { useAuth } from '@/hooks/useAuth';

import { EmptyState } from './EmptyState';
import { FullPageSpinner } from './Spinner';

/**
 * Renders `children` only for a confirmed session holding the admin role.
 *
 * This is **convenience, not protection**: every /api/admin endpoint carries
 * `get_current_admin` on its router and answers 403 regardless of what the
 * frontend renders. What this buys is the right screen — a non-admin who follows
 * a link gets an explanation instead of a page full of failed requests.
 *
 * Not folded into `ProtectedRoute`: that one answers "is there a session", which
 * every page needs, and adding a role parameter would put an authorization
 * decision on the path of every route in the app.
 */
export function AdminRoute({ children }: { children: ReactNode }) {
  const { user, isLoading } = useAuth();
  const location = useLocation();

  if (isLoading) {
    return <FullPageSpinner label="Verificando permissões" />;
  }

  if (!user) {
    return <Navigate to="/login" replace state={{ from: location.pathname + location.search }} />;
  }

  if (!user.is_admin) {
    return (
      <div className="mx-auto max-w-lg px-4 py-16">
        <EmptyState
          icon={ShieldOff}
          title="Área restrita"
          description="Esta área é exclusiva de administradores. Se você precisa de acesso, fale com quem administra a instalação."
          action={
            <Link to="/" className="btn">
              Voltar ao painel
            </Link>
          }
        />
      </div>
    );
  }

  return <>{children}</>;
}
