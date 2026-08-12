import { ArrowLeft, Compass } from 'lucide-react';
import { Link } from 'react-router-dom';

export function NotFound() {
  return (
    <div className="flex min-h-[60vh] flex-col items-center justify-center gap-4 text-center animate-fade-in">
      <span
        aria-hidden
        className="grid h-12 w-12 place-items-center rounded-2xl border border-line bg-surface-sunken text-content-subtle"
      >
        <Compass className="h-5 w-5" strokeWidth={1.75} />
      </span>
      <p className="tabular text-4xl font-semibold text-gradient">404</p>
      <div className="space-y-1.5">
        <h1 className="text-xl">Esta página não existe</h1>
        <p className="mx-auto max-w-sm text-sm leading-relaxed text-content-muted">
          O link pode estar desatualizado, ou a vaga ou candidatura para onde ele apontava foi removida.
        </p>
      </div>
      <Link to="/" className="btn btn-primary">
        <ArrowLeft aria-hidden className="h-4 w-4" />
        Voltar ao painel
      </Link>
    </div>
  );
}
