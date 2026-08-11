/**
 * Typed React wrappers over the component classes defined in index.css.
 *
 * The CSS layer owns the look; this module only adds behaviour (loading state,
 * label/hint wiring, switch semantics) so pages never hand-assemble class names.
 */

import { Loader2 } from 'lucide-react';
import { forwardRef, useId } from 'react';
import type { ComponentPropsWithoutRef, ElementType, ReactNode } from 'react';

import { cn } from '@/lib/utils';

/* ------------------------------------------------------------------ button */

export type ButtonVariant = 'default' | 'primary' | 'ghost' | 'danger';
export type ButtonSize = 'sm' | 'md' | 'lg' | 'icon';

const VARIANT_CLASS: Record<ButtonVariant, string> = {
  default: '',
  primary: 'btn-primary',
  ghost: 'btn-ghost',
  danger: 'btn-danger',
};

const SIZE_CLASS: Record<ButtonSize, string> = {
  sm: 'btn-sm',
  md: '',
  lg: 'btn-lg',
  icon: 'btn-icon',
};

export function buttonClass(
  variant: ButtonVariant = 'default',
  size: ButtonSize = 'md',
  extra?: string,
): string {
  return cn('btn', VARIANT_CLASS[variant], SIZE_CLASS[size], extra);
}

export interface ButtonProps extends ComponentPropsWithoutRef<'button'> {
  variant?: ButtonVariant;
  size?: ButtonSize;
  loading?: boolean;
  icon?: ReactNode;
}

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(function Button(
  { variant = 'default', size = 'md', loading = false, icon, className, children, disabled, type, ...rest },
  ref,
) {
  return (
    <button
      ref={ref}
      type={type ?? 'button'}
      disabled={disabled || loading}
      aria-busy={loading || undefined}
      className={buttonClass(variant, size, className)}
      {...rest}
    >
      {loading ? <Loader2 aria-hidden className="h-4 w-4 animate-spin" /> : icon}
      {children}
    </button>
  );
});

/* -------------------------------------------------------------------- card */

export interface CardProps extends ComponentPropsWithoutRef<'section'> {
  as?: ElementType;
  hoverable?: boolean;
}

export function Card({ className, as, hoverable = false, ...rest }: CardProps) {
  const Component = (as ?? 'section') as ElementType;
  return <Component className={cn('card', hoverable && 'card-hover', className)} {...rest} />;
}

export interface CardHeaderProps {
  title: ReactNode;
  description?: ReactNode;
  actions?: ReactNode;
  className?: string;
}

export function CardHeader({ title, description, actions, className }: CardHeaderProps) {
  return (
    <div className={cn('card-header items-start', className)}>
      <div className="min-w-0 space-y-1">
        <h2 className="text-md leading-tight">{title}</h2>
        {description ? (
          <p className="text-xs leading-snug text-content-subtle">{description}</p>
        ) : null}
      </div>
      {actions ? <div className="flex shrink-0 items-center gap-2">{actions}</div> : null}
    </div>
  );
}

export function CardBody({ className, ...rest }: ComponentPropsWithoutRef<'div'>) {
  return <div className={cn('card-body', className)} {...rest} />;
}

export function SectionLabel({ className, ...rest }: ComponentPropsWithoutRef<'h3'>) {
  return (
    <h3
      className={cn(
        'text-2xs font-semibold uppercase tracking-[0.1em] text-content-subtle',
        className,
      )}
      {...rest}
    />
  );
}

export interface PageHeaderProps {
  title: string;
  description?: string;
  actions?: ReactNode;
  className?: string;
}

export function PageHeader({ title, description, actions, className }: PageHeaderProps) {
  return (
    <header className={cn('flex flex-wrap items-end justify-between gap-4', className)}>
      <div className="space-y-1.5">
        <h1 className="text-2xl">{title}</h1>
        {description ? (
          <p className="max-w-2xl text-sm leading-relaxed text-content-muted">{description}</p>
        ) : null}
      </div>
      {actions ? <div className="flex flex-wrap items-center gap-2">{actions}</div> : null}
    </header>
  );
}

/* ------------------------------------------------------------------- forms */

export const Input = forwardRef<HTMLInputElement, ComponentPropsWithoutRef<'input'>>(
  function Input({ className, ...rest }, ref) {
    return <input ref={ref} className={cn('input', className)} {...rest} />;
  },
);

export const Textarea = forwardRef<HTMLTextAreaElement, ComponentPropsWithoutRef<'textarea'>>(
  function Textarea({ className, ...rest }, ref) {
    return <textarea ref={ref} className={cn('input', className)} {...rest} />;
  },
);

export const Select = forwardRef<HTMLSelectElement, ComponentPropsWithoutRef<'select'>>(
  function Select({ className, ...rest }, ref) {
    return <select ref={ref} className={cn('input', className)} {...rest} />;
  },
);

export interface FieldProps {
  label: ReactNode;
  htmlFor: string;
  hint?: ReactNode;
  error?: string | null;
  required?: boolean;
  className?: string;
  children: ReactNode;
}

export function Field({ label, htmlFor, hint, error, required, className, children }: FieldProps) {
  return (
    <div className={cn('min-w-0', className)}>
      <label htmlFor={htmlFor} className="label">
        {label}
        {required ? (
          <span aria-hidden className="ml-0.5 text-danger">
            *
          </span>
        ) : null}
      </label>
      {children}
      {error ? (
        <p id={`${htmlFor}-error`} role="alert" className="hint text-danger">
          {error}
        </p>
      ) : hint ? (
        <p id={`${htmlFor}-hint`} className="hint">
          {hint}
        </p>
      ) : null}
    </div>
  );
}

export interface CheckboxProps extends Omit<ComponentPropsWithoutRef<'input'>, 'type'> {
  label: ReactNode;
  description?: ReactNode;
}

export function Checkbox({ label, description, className, id, ...rest }: CheckboxProps) {
  const generated = useId();
  const inputId = id ?? generated;
  return (
    <div className={cn('flex gap-2.5', className)}>
      <input
        id={inputId}
        type="checkbox"
        className="mt-0.5 h-4 w-4 shrink-0 cursor-pointer rounded border-line-strong bg-surface-sunken accent-accent-500"
        {...rest}
      />
      <div className="min-w-0 space-y-0.5">
        <label htmlFor={inputId} className="cursor-pointer text-sm font-medium leading-snug text-content">
          {label}
        </label>
        {description ? (
          <p className="text-xs leading-relaxed text-content-subtle">{description}</p>
        ) : null}
      </div>
    </div>
  );
}

export interface ToggleProps {
  checked: boolean;
  onChange: (next: boolean) => void;
  label: string;
  disabled?: boolean;
  id?: string;
  tone?: 'accent' | 'warning' | 'success';
  className?: string;
}

const TOGGLE_ON: Record<NonNullable<ToggleProps['tone']>, string> = {
  accent: 'bg-accent-600',
  warning: 'bg-warning',
  success: 'bg-success',
};

export function Toggle({
  checked,
  onChange,
  label,
  disabled,
  id,
  tone = 'accent',
  className,
}: ToggleProps) {
  return (
    <button
      id={id}
      type="button"
      role="switch"
      aria-checked={checked}
      aria-label={label}
      disabled={disabled}
      onClick={() => onChange(!checked)}
      className={cn(
        'relative inline-flex h-5 w-9 shrink-0 items-center rounded-full border border-transparent transition duration-150 ease-snap disabled:cursor-not-allowed disabled:opacity-50',
        checked ? TOGGLE_ON[tone] : 'bg-line-strong',
        className,
      )}
    >
      <span
        aria-hidden
        className={cn(
          'ml-0.5 inline-block h-4 w-4 rounded-full bg-white shadow-sm transition-transform duration-150 ease-snap',
          checked ? 'translate-x-4' : 'translate-x-0',
        )}
      />
    </button>
  );
}

/* ---------------------------------------------------------------- feedback */

export function Skeleton({ className, ...rest }: ComponentPropsWithoutRef<'div'>) {
  return <div aria-hidden className={cn('skeleton', className)} {...rest} />;
}

export interface ProgressRingProps {
  value: number;
  max: number;
  size?: number;
  caption?: string;
  className?: string;
}

/** Daily-cap dial: turns amber near the cap and red once it is reached. */
export function ProgressRing({ value, max, size = 88, caption, className }: ProgressRingProps) {
  const safeMax = max > 0 ? max : 1;
  const ratio = Math.max(0, Math.min(1, value / safeMax));
  const stroke = 7;
  const radius = (size - stroke) / 2;
  const circumference = 2 * Math.PI * radius;
  const tone = ratio >= 1 ? 'stroke-danger' : ratio >= 0.75 ? 'stroke-warning' : 'stroke-accent-500';

  return (
    <div
      className={cn('relative shrink-0', className)}
      style={{ width: size, height: size }}
      role="img"
      aria-label={`${value} of ${max} ${caption ?? 'used'}`}
    >
      <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} className="-rotate-90">
        <circle
          cx={size / 2}
          cy={size / 2}
          r={radius}
          fill="none"
          strokeWidth={stroke}
          className="stroke-line"
        />
        <circle
          cx={size / 2}
          cy={size / 2}
          r={radius}
          fill="none"
          strokeWidth={stroke}
          strokeLinecap="round"
          strokeDasharray={circumference}
          strokeDashoffset={circumference * (1 - ratio)}
          className={cn(tone, 'transition-[stroke-dashoffset] duration-700 ease-snap')}
        />
      </svg>
      <div className="absolute inset-0 flex flex-col items-center justify-center">
        <span className="tabular text-xl font-semibold text-content">{value}</span>
        <span className="text-2xs uppercase tracking-wider text-content-subtle">
          {caption ?? `of ${max}`}
        </span>
      </div>
    </div>
  );
}

export interface NoteProps {
  tone?: 'neutral' | 'warning' | 'danger' | 'accent';
  icon?: ReactNode;
  children: ReactNode;
  className?: string;
}

const NOTE_TONE: Record<NonNullable<NoteProps['tone']>, string> = {
  neutral: 'border-line bg-surface-sunken text-content-muted',
  warning: 'border-warning/35 bg-warning/10 text-warning-strong',
  danger: 'border-danger/35 bg-danger/10 text-danger-strong',
  accent: 'border-accent-500/30 bg-accent-500/8 text-content-muted',
};

export function Note({ tone = 'neutral', icon, children, className }: NoteProps) {
  return (
    <div
      className={cn(
        'flex gap-2.5 rounded-lg border px-3.5 py-2.5 text-xs leading-relaxed',
        NOTE_TONE[tone],
        className,
      )}
    >
      {icon ? <span className="mt-px shrink-0">{icon}</span> : null}
      <div className="min-w-0">{children}</div>
    </div>
  );
}

/** Small key/value row used across detail panels. */
export function MetaRow({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="flex items-baseline justify-between gap-4 py-1.5">
      <dt className="text-xs text-content-subtle">{label}</dt>
      <dd className="min-w-0 text-right text-sm text-content">{children}</dd>
    </div>
  );
}
