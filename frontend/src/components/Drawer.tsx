import { X } from 'lucide-react';
import { useCallback, useId, useRef } from 'react';
import type { ReactNode } from 'react';
import { createPortal } from 'react-dom';

import { cn } from '@/lib/utils';

import { useDismissableLayer } from './Modal';
import { Button } from './primitives';

export interface DrawerProps {
  open: boolean;
  onClose: () => void;
  title: ReactNode;
  description?: ReactNode;
  side?: 'left' | 'right';
  width?: string;
  footer?: ReactNode;
  children?: ReactNode;
  className?: string;
}

export function Drawer({
  open,
  onClose,
  title,
  description,
  side = 'right',
  width = 'max-w-md',
  footer,
  children,
  className,
}: DrawerProps) {
  const panelRef = useRef<HTMLDivElement>(null);
  const titleId = useId();
  const descriptionId = useId();

  const handleClose = useCallback(() => onClose(), [onClose]);
  useDismissableLayer(open, handleClose, panelRef);

  if (!open) return null;

  return createPortal(
    <div className="fixed inset-0 z-50">
      <div
        aria-hidden
        onClick={handleClose}
        className="absolute inset-0 bg-surface-sunken/80 backdrop-blur-[3px]"
      />
      <div
        ref={panelRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        aria-describedby={description ? descriptionId : undefined}
        tabIndex={-1}
        className={cn(
          'absolute inset-y-0 flex w-full flex-col bg-surface-raised shadow-lifted outline-none',
          side === 'right' ? 'right-0 border-l border-line' : 'left-0 border-r border-line',
          width,
          className,
        )}
      >
        <div className="flex items-start gap-3 border-b border-line px-4 py-3.5">
          <div className="min-w-0 flex-1 space-y-0.5">
            <h2 id={titleId} className="text-md">
              {title}
            </h2>
            {description ? (
              <p id={descriptionId} className="text-xs text-content-subtle">
                {description}
              </p>
            ) : null}
          </div>
          <Button variant="ghost" size="icon" onClick={handleClose} aria-label="Fechar painel">
            <X aria-hidden className="h-4 w-4" />
          </Button>
        </div>

        <div className="scroll-area min-h-0 flex-1 px-4 py-4">{children}</div>

        {footer ? (
          <div className="flex items-center justify-end gap-2 border-t border-line px-4 py-3">
            {footer}
          </div>
        ) : null}
      </div>
    </div>,
    document.body,
  );
}
