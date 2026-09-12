import { Trash2, TriangleAlert } from 'lucide-react';
import { useState } from 'react';
import { useNavigate } from 'react-router-dom';

import { Button, Card, CardHeader, Field, Input } from '@/components/primitives';
import { deleteAccount } from '@/services/auth';
import { errorMessage } from '@/services/client';

/** Everything the deletion takes, named rather than summarised as "your data". */
const ERASED = [
  'o seu perfil e o currículo que você enviou',
  'as versões do currículo de cada candidatura, e os PDFs gerados',
  'as suas preferências de vaga, buscas salvas e vagas pontuadas',
  'as suas candidaturas, com as cartas e as respostas de triagem',
  'a sessão do LinkedIn guardada, e o perfil de navegador dela',
  'a sua chave de IA, se você guardou uma',
  'a trilha de auditoria desta conta',
];

/**
 * Erasing the account, from the bottom of the settings screen.
 *
 * Two things this deliberately does not do. It does not hide behind a modal:
 * the consequences are a list worth reading, and a dialog is the wrong shape
 * for a list someone should read slowly. And it does not accept a typed-out
 * "DELETE" phrase — that proves the warning was read, whereas the password
 * proves it is the account holder typing, which is the thing actually worth
 * proving on a machine someone else may have walked away from.
 */
export function DangerZone() {
  const navigate = useNavigate();
  const [open, setOpen] = useState(false);
  const [password, setPassword] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);

  const close = () => {
    setOpen(false);
    setPassword('');
    setError(null);
  };

  const submit = async () => {
    if (!password || pending) return;
    setPending(true);
    setError(null);
    try {
      // Clears the token and the cached session on the way out, through the
      // same listener a 401 goes through. `replace` keeps the back button from
      // returning to an app whose account no longer exists.
      await deleteAccount(password);
      navigate('/login', { replace: true });
    } catch (caught) {
      setError(errorMessage(caught, 'Não foi possível apagar a conta.'));
      setPending(false);
    }
  };

  return (
    <Card className="border-danger/40">
      <CardHeader
        title="Apagar a conta"
        description="Some com tudo, de uma vez, sem recuperação."
      />
      <div className="card-body space-y-4">
        <div>
          <p className="text-sm text-content-muted">Apagar esta conta remove:</p>
          <ul className="mt-2 space-y-1 text-xs leading-relaxed text-content-subtle">
            {ERASED.map((item) => (
              <li key={item} className="flex gap-2">
                <span aria-hidden className="text-danger">
                  •
                </span>
                {item}
              </li>
            ))}
          </ul>
          <p className="mt-2.5 text-xs leading-relaxed text-content-muted">
            Não há período de carência e não há cópia de segurança do nosso lado. Se você quer
            ficar com o seu histórico, exporte o CSV das candidaturas antes.
          </p>
          <p className="mt-1.5 text-xs leading-relaxed text-content-muted">
            Isto não desfaz nada que você já enviou: candidaturas que saíram estão com o
            empregador, e a sua conta do LinkedIn continua existindo.
          </p>
        </div>

        {open ? (
          <div className="space-y-3 rounded-lg border border-danger/40 bg-danger/[0.07] px-3.5 py-3">
            <p className="flex items-center gap-1.5 text-sm font-medium text-danger-strong">
              <TriangleAlert aria-hidden className="h-4 w-4" />
              Confirme com a sua senha
            </p>
            <Field label="Senha" htmlFor="danger-password" error={error ?? undefined}>
              <Input
                id="danger-password"
                type="password"
                autoComplete="current-password"
                value={password}
                disabled={pending}
                placeholder="A sua senha desta conta"
                onChange={(event) => {
                  setPassword(event.target.value);
                  setError(null);
                }}
                onKeyDown={(event) => {
                  if (event.key === 'Enter') void submit();
                }}
              />
            </Field>
            <div className="flex flex-wrap gap-2">
              <Button
                variant="danger"
                loading={pending}
                disabled={!password}
                icon={<Trash2 aria-hidden className="h-4 w-4" />}
                onClick={() => void submit()}
              >
                Apagar definitivamente
              </Button>
              <Button variant="ghost" disabled={pending} onClick={close}>
                Cancelar
              </Button>
            </div>
          </div>
        ) : (
          <Button
            variant="danger"
            icon={<Trash2 aria-hidden className="h-4 w-4" />}
            onClick={() => setOpen(true)}
          >
            Apagar minha conta
          </Button>
        )}
      </div>
    </Card>
  );
}
