/* eslint-disable react-refresh/only-export-components -- useToast must ship with its provider */
import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from 'react';
import type { ReactNode } from 'react';

import { ToastViewport } from './Toast';
import type { ToastItem, ToastVariant } from './Toast';

export interface ToastOptions {
  title: string;
  description?: string;
  variant?: ToastVariant;
  duration?: number;
}

export interface ToastApi {
  toast: (options: ToastOptions) => string;
  success: (title: string, description?: string) => string;
  error: (title: string, description?: string) => string;
  warning: (title: string, description?: string) => string;
  dismiss: (id: string) => void;
}

const ToastContext = createContext<ToastApi | null>(null);

const DEFAULT_DURATION = 5000;
const MAX_VISIBLE = 4;

let counter = 0;
function nextId(): string {
  counter += 1;
  return `toast-${counter}`;
}

export function ToastProvider({ children }: { children: ReactNode }) {
  const outer = useContext(ToastContext);
  const [toasts, setToasts] = useState<ToastItem[]>([]);
  const timers = useRef(new Map<string, ReturnType<typeof setTimeout>>());

  const dismiss = useCallback((id: string) => {
    const timer = timers.current.get(id);
    if (timer) {
      clearTimeout(timer);
      timers.current.delete(id);
    }
    setToasts((current) => current.filter((item) => item.id !== id));
  }, []);

  const toast = useCallback(
    ({ title, description, variant = 'info', duration = DEFAULT_DURATION }: ToastOptions) => {
      const id = nextId();
      setToasts((current) =>
        [...current, { id, title, description, variant, duration }].slice(-MAX_VISIBLE),
      );
      if (duration > 0) {
        timers.current.set(
          id,
          setTimeout(() => dismiss(id), duration),
        );
      }
      return id;
    },
    [dismiss],
  );

  useEffect(() => {
    const pending = timers.current;
    return () => {
      pending.forEach((timer) => clearTimeout(timer));
      pending.clear();
    };
  }, []);

  const api = useMemo<ToastApi>(
    () => ({
      toast,
      success: (title, description) => toast({ title, description, variant: 'success' }),
      // Failures usually carry an instruction to act on, so they linger.
      error: (title, description) => toast({ title, description, variant: 'error', duration: 9000 }),
      warning: (title, description) =>
        toast({ title, description, variant: 'warning', duration: 7000 }),
      dismiss,
    }),
    [toast, dismiss],
  );

  // Nesting is harmless: an outer provider already owns a viewport, so the inner
  // one steps aside instead of rendering a second stack.
  if (outer) return <>{children}</>;

  return (
    <ToastContext.Provider value={api}>
      {children}
      <ToastViewport toasts={toasts} onDismiss={dismiss} />
    </ToastContext.Provider>
  );
}

export function useToast(): ToastApi {
  const context = useContext(ToastContext);
  if (!context) {
    throw new Error('useToast must be used inside a <ToastProvider>.');
  }
  return context;
}
