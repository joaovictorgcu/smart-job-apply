import { ArrowRight, Moon, ShieldAlert, Sun } from 'lucide-react';
import { useState } from 'react';
import type { FormEvent } from 'react';
import { Link, Navigate, useNavigate } from 'react-router-dom';

import { Button, Field, Input, Note } from '@/components/primitives';
import { FullPageSpinner } from '@/components/Spinner';
import { useAuth } from '@/hooks/useAuth';
import { useTheme } from '@/lib/theme';
import { errorMessage } from '@/services/client';

const EMAIL_PATTERN = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
const MIN_PASSWORD = 10;
const MAX_PASSWORD = 72;

interface FieldErrors {
  email?: string;
  password?: string;
  confirm?: string;
}

export function Register() {
  const { user, isLoading, register } = useAuth();
  const navigate = useNavigate();
  const { theme, toggleTheme } = useTheme();

  const [fullName, setFullName] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [confirm, setConfirm] = useState('');
  const [errors, setErrors] = useState<FieldErrors>({});
  const [formError, setFormError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  if (isLoading) return <FullPageSpinner label="Restaurando sessão" />;
  if (user) return <Navigate to="/" replace />;

  const validate = (): boolean => {
    const next: FieldErrors = {};
    if (!email.trim()) next.email = 'Informe o seu e-mail.';
    else if (!EMAIL_PATTERN.test(email.trim())) next.email = 'Isso não parece um e-mail.';

    if (!password) next.password = 'Escolha uma senha.';
    else if (password.length < MIN_PASSWORD)
      next.password = `Use pelo menos ${MIN_PASSWORD} caracteres.`;
    else if (password.length > MAX_PASSWORD)
      next.password = `Use no máximo ${MAX_PASSWORD} caracteres.`;

    if (confirm !== password) next.confirm = 'As duas senhas não coincidem.';

    setErrors(next);
    return Object.keys(next).length === 0;
  };

  const onSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setFormError(null);
    if (!validate()) return;

    setSubmitting(true);
    try {
      await register({
        email: email.trim(),
        password,
        full_name: fullName.trim() || null,
      });
      navigate('/', { replace: true });
    } catch (error) {
      setFormError(errorMessage(error, 'Não foi possível criar a conta.'));
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
              Uma conta local protege o seu painel. Ela não tem relação com o seu login do LinkedIn,
              que você sempre digita na janela do navegador.
            </p>
          </div>

          <div className="card">
            <form onSubmit={onSubmit} noValidate className="card-body space-y-4">
              <h1 className="text-lg">Crie a sua conta</h1>

              {formError ? (
                <div role="alert" className="rounded-lg border border-danger/40 bg-danger/10 px-3 py-2.5 text-xs leading-relaxed text-danger-strong">
                  {formError}
                </div>
              ) : null}

              <Field label="Nome completo" htmlFor="register-name" hint="Opcional — usado nas cartas de apresentação.">
                <Input
                  id="register-name"
                  name="name"
                  autoComplete="name"
                  value={fullName}
                  onChange={(event) => setFullName(event.target.value)}
                  placeholder="Ada Lovelace"
                />
              </Field>

              <Field label="E-mail" htmlFor="register-email" error={errors.email} required>
                <Input
                  id="register-email"
                  name="email"
                  type="email"
                  autoComplete="username"
                  value={email}
                  aria-invalid={Boolean(errors.email)}
                  aria-describedby={errors.email ? 'register-email-error' : undefined}
                  onChange={(event) => setEmail(event.target.value)}
                  placeholder="voce@exemplo.com"
                />
              </Field>

              <Field
                label="Senha"
                htmlFor="register-password"
                error={errors.password}
                hint={`Pelo menos ${MIN_PASSWORD} caracteres.`}
                required
              >
                <Input
                  id="register-password"
                  name="password"
                  type="password"
                  autoComplete="new-password"
                  value={password}
                  aria-invalid={Boolean(errors.password)}
                  aria-describedby={
                    errors.password ? 'register-password-error' : 'register-password-hint'
                  }
                  onChange={(event) => setPassword(event.target.value)}
                  placeholder="••••••••••"
                />
              </Field>

              <Field label="Confirmar senha" htmlFor="register-confirm" error={errors.confirm} required>
                <Input
                  id="register-confirm"
                  name="confirm-password"
                  type="password"
                  autoComplete="new-password"
                  value={confirm}
                  aria-invalid={Boolean(errors.confirm)}
                  aria-describedby={errors.confirm ? 'register-confirm-error' : undefined}
                  onChange={(event) => setConfirm(event.target.value)}
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
                Criar conta
              </Button>

              <p className="text-center text-xs text-content-subtle">
                Já tem uma conta?{' '}
                <Link to="/login" className="font-medium text-accent-400 hover:underline">
                  Entrar
                </Link>
              </p>
            </form>
          </div>

          <Note tone="neutral" icon={<ShieldAlert aria-hidden className="h-3.5 w-3.5" />}>
            Esta é uma ferramenta auto-hospedada que automatiza o LinkedIn. Automatizar o LinkedIn
            viola os Termos de Uso do LinkedIn e pode fazer a sua conta ser restringida ou banida —
            você usa por sua conta e risco.
          </Note>
        </div>
      </div>
    </div>
  );
}
