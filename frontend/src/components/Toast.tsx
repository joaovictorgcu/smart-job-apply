import { AlertTriangle, CheckCircle2, Info, X, XCircle } from 'lucide-react';
import type { LucideIcon } from 'lucide-react';

import { cn } from '@/lib/utils';

export type ToastVariant = 'info' | 'success' | 'warning' | 'error';

export interface ToastItem {
  id: string;
  title: string;
  description?: string;
  variant: ToastVariant;
  /** Milliseconds before auto-dismiss; 0 keeps the toast until dismissed. */
  duration: number;
}

const VARIANT: Record<ToastVariant, { icon: LucideIcon; border: string; iconClass: string }> = {
  info: { icon: Info, border: 'border-line', iconClass: 'text-info' },
  success: { icon: CheckCircle2, border: 'border-success/40', iconClass: 'text-success' },
  warning: { icon: AlertTriangle, border: 'border-warning/40', iconClass: 'text-warning' },
  error: { icon: XCircle, border: 'border-danger/40', iconClass: 'text-danger' },
};

export interface ToastProps {
  toast: ToastItem;
  onDismiss: (id: string) => void;
}

export function Toast({ toast, onDismiss }: ToastProps) {
  const { icon: Icon, border, iconClass } = VARIANT[toast.variant];

  return (
    <div
      role={toast.variant === 'error' ? 'alert' : 'status'}
      className={cn(
        'pointer-events-auto flex w-full items-start gap-3 rounded-xl border bg-surface-overlay px-3.5 py-3 shadow-lifted animate-fade-in',
        border,
      )}
    >
      <Icon aria-hidden className={cn('mt-px h-4 w-4 shrink-0', iconClass)} />
      <div className="min-w-0 flex-1 space-y-0.5">
        <p className="text-sm font-semibold leading-snug text-content">{toast.title}</p>
        {toast.description ? (
          <p className="break-words text-xs leading-relaxed text-content-muted">
            {toast.description}
          </p>
        ) : null}
      </div>
      <button
        type="button"
        onClick={() => onDismiss(toast.id)}
        aria-label="Dispensar notificação"
        className="-mr-1 -mt-0.5 rounded-lg p-1 text-content-subtle transition-colors duration-150 hover:bg-surface-sunken hover:text-content"
      >
        <X aria-hidden className="h-3.5 w-3.5" />
      </button>
    </div>
  );
}

export interface ToastViewportProps {
  toasts: ToastItem[];
  onDismiss: (id: string) => void;
}

export function ToastViewport({ toasts, onDismiss }: ToastViewportProps) {
  return (
    <div
      aria-live="polite"
      aria-atomic="false"
      className="pointer-events-none fixed inset-x-0 bottom-0 z-[60] flex flex-col items-center gap-2 p-4 sm:inset-x-auto sm:right-0 sm:w-96 sm:items-end"
    >
      {toasts.map((toast) => (
        <Toast key={toast.id} toast={toast} onDismiss={onDismiss} />
      ))}
    </div>
  );
}
