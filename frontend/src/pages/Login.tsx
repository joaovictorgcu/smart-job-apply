import { ArrowRight, Moon, ShieldAlert, Sun } from 'lucide-react';
import { useState } from 'react';
import type { FormEvent } from 'react';
import { Link, Navigate, useLocation, useNavigate } from 'react-router-dom';

import { Button, Field, Input, Note } from '@/components/primitives';
import { FullPageSpinner } from '@/components/Spinner';
import { useAuth } from '@/hooks/useAuth';
import { useTheme } from '@/lib/theme';
import { errorMessage } from '@/services/client';

const EMAIL_PATTERN = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

interface FieldErrors {
  email?: string;
  password?: string;
}

export function Login() {
  const { user, isLoading, login } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const { theme, toggleTheme } = useTheme();

  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [errors, setErrors] = useState<FieldErrors>({});
  const [formError, setFormError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  if (isLoading) return <FullPageSpinner label="Restaurando sessão" />;
  if (user) return <Navigate to="/" replace />;

  const redirectTo = (location.state as { from?: string } | null)?.from ?? '/';

  const validate = (): boolean => {
    const next: FieldErrors = {};
    if (!email.trim()) next.email = 'Informe o seu e-mail.';
    else if (!EMAIL_PATTERN.test(email.trim())) next.email = 'Isso não parece um e-mail.';
    if (!password) next.password = 'Informe a sua senha.';
    setErrors(next);
    return Object.keys(next).length === 0;
  };

  const onSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setFormError(null);
    if (!validate()) return;

    setSubmitting(true);
    try {
      await login({ email: email.trim(), password });
      navigate(redirectTo, { replace: true });
    } catch (error) {
      setFormError(errorMessage(error, 'Não foi possível entrar. Confira o seu e-mail e a senha.'));
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="flex min-h-screen flex-col bg-surface">
      <div className="flex justify-end p-4">
        <Button
          variant="ghost"
          size="icon"
          onClick={toggleTheme}
          aria-label={theme === 'dark' ? 'Mudar para o tema claro' : 'Mudar para o tema escuro'}
        >
          {theme === 'dark' ? (
            <Sun aria-hidden className="h-[18px] w-[18px]" />
          ) : (
            <Moon aria-hidden className="h-[18px] w-[18px]" />
          )}
        </Button>
      </div>

      <div className="flex flex-1 items-start justify-center px-4 pb-16 sm:items-center">
        <div className="w-full max-w-[26rem] space-y-6">
          <div className="space-y-2">
            <div className="flex items-center gap-2.5">
              <span
                aria-hidden
                className="grid h-9 w-9 place-items-center rounded-xl bg-accent-600 text-xs font-bold text-white shadow-glow-sm"
              >
                LA
              </span>
              <span className="text-lg font-semibold tracking-tight text-content">
                LinkedIn Auto Apply
              </span>
            </div>
            <p className="text-sm leading-relaxed text-content-muted">
              Encontra vagas de Candidatura Simplificada, pontua com IA e preenche o formulário —
              depois para e espera você aprovar cada envio.
            </p>
          </div>

          <div className="card">
            <form onSubmit={onSubmit} noValidate className="card-body space-y-4">
              <h1 className="text-lg">Entrar</h1>

              {formError ? (
                <div role="alert" className="rounded-lg border border-danger/40 bg-danger/10 px-3 py-2.5 text-xs leading-relaxed text-danger-strong">
                  {formError}
                </div>
              ) : null}

              <Field label="E-mail" htmlFor="login-email" error={errors.email} required>
                <Input
                  id="login-email"
                  name="email"
                  type="email"
                  autoComplete="username"
                  autoFocus
                  value={email}
                  aria-invalid={Boolean(errors.email)}
                  aria-describedby={errors.email ? 'login-email-error' : undefined}
                  onChange={(event) => setEmail(event.target.value)}
                  placeholder="voce@exemplo.com"
                />
              </Field>

              <Field label="Senha" htmlFor="login-password" error={errors.password} required>
                <Input
                  id="login-password"
                  name="password"
                  type="password"
                  autoComplete="current-password"
                  value={password}
                  aria-invalid={Boolean(errors.password)}
                  aria-describedby={errors.password ? 'login-password-error' : undefined}
                  onChange={(event) => setPassword(event.target.value)}
                  placeholder="••••••••••"
                />
              </Field>

              <Button
                type="submit"
                variant="primary"
                className="w-full"
                loading={submitting}
                icon={<ArrowRight aria-hidden className="h-4 w-4" />}
              >
                Entrar
              </Button>

              <p className="text-center text-xs text-content-subtle">
                Ainda não tem conta?{' '}
                <Link to="/register" className="font-medium text-accent-400 hover:underline">
                  Criar uma
                </Link>
              </p>
            </form>
          </div>

          <Note tone="neutral" icon={<ShieldAlert aria-hidden className="h-3.5 w-3.5" />}>
            Esta é uma ferramenta auto-hospedada que automatiza o LinkedIn. Automatizar o LinkedIn
            viola os Termos de Uso do LinkedIn e pode fazer a sua conta ser restringida ou banida —
            você usa por sua conta e risco. A sua senha do LinkedIn nunca é armazenada: você faz o
            login manualmente na janela do navegador que a ferramenta abre.
          </Note>
        </div>
      </div>
    </div>
  );
}
