import { FileText, Upload, X } from 'lucide-react';
import { useRef, useState } from 'react';
import type { DragEvent } from 'react';

import { useUploadResume } from '@/hooks/useApi';
import { formatBytes } from '@/lib/format';
import { cn } from '@/lib/utils';
import { errorMessage } from '@/services/client';

import { Button } from './primitives';
import { useToast } from './ToastProvider';

const MAX_BYTES = 5 * 1024 * 1024;

export interface ResumeUploaderProps {
  filename: string | null;
  className?: string;
}

export function ResumeUploader({ filename, className }: ResumeUploaderProps) {
  const toast = useToast();
  const inputRef = useRef<HTMLInputElement>(null);
  const [dragging, setDragging] = useState(false);
  const [localError, setLocalError] = useState<string | null>(null);

  const upload = useUploadResume({
    onSuccess: (profile) =>
      toast.success('Currículo enviado', profile.resume_filename ?? undefined),
    onError: (error) => toast.error('Falha no envio', errorMessage(error)),
  });

  const accept = (file: File | undefined) => {
    setLocalError(null);
    if (!file) return;

    const isPdf =
      file.type === 'application/pdf' || file.name.toLowerCase().endsWith('.pdf');
    if (!isPdf) {
      setLocalError('Apenas arquivos PDF são aceitos.');
      return;
    }
    if (file.size > MAX_BYTES) {
      setLocalError(`Esse arquivo tem ${formatBytes(file.size)}. O limite é ${formatBytes(MAX_BYTES)}.`);
      return;
    }
    upload.mutate(file);
  };

  const onDrop = (event: DragEvent<HTMLDivElement>) => {
    event.preventDefault();
    setDragging(false);
    accept(event.dataTransfer.files?.[0]);
  };

  return (
    <div className={className}>
      <div
        onDragOver={(event) => {
          event.preventDefault();
          setDragging(true);
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={onDrop}
        className={cn(
          'rounded-xl border border-dashed px-4 py-6 text-center transition-colors duration-150',
          dragging ? 'border-accent-500 bg-accent-500/[0.07]' : 'border-line-strong bg-surface-sunken',
        )}
      >
        <span
          aria-hidden
          className="mx-auto grid h-10 w-10 place-items-center rounded-xl border border-line bg-surface-raised text-content-subtle"
        >
          <Upload className="h-4 w-4" />
        </span>
        <p className="mt-2.5 text-sm font-medium text-content">Solte o seu currículo aqui</p>
        <p className="mt-1 text-xs text-content-subtle">
          Apenas PDF, até {formatBytes(MAX_BYTES)}. Ele é enviado ao LinkedIn como está.
        </p>

        <input
          ref={inputRef}
          id="resume-file"
          type="file"
          accept="application/pdf,.pdf"
          className="sr-only"
          onChange={(event) => {
            accept(event.target.files?.[0]);
            event.target.value = '';
          }}
        />
        <Button
          size="sm"
          className="mt-3"
          loading={upload.isPending}
          onClick={() => inputRef.current?.click()}
        >
          Escolher um PDF
        </Button>
      </div>

      {localError ? (
        <p role="alert" className="mt-2 flex items-center gap-1.5 text-xs text-danger">
          <X aria-hidden className="h-3.5 w-3.5" />
          {localError}
        </p>
      ) : null}

      {filename ? (
        <div className="mt-3 flex items-center gap-2.5 rounded-lg border border-line bg-surface-sunken px-3 py-2.5">
          <FileText aria-hidden className="h-4 w-4 shrink-0 text-accent-400" />
          <div className="min-w-0 flex-1">
            <p className="truncate text-sm font-medium text-content" title={filename}>
              {filename}
            </p>
            <p className="text-2xs text-content-subtle">Armazenado no servidor e anexado às candidaturas.</p>
          </div>
        </div>
      ) : (
        <p className="mt-3 text-xs text-content-subtle">
          Nenhum currículo armazenado ainda. Candidaturas que exigem o envio de arquivo vão falhar até você adicionar um.
        </p>
      )}
    </div>
  );
}
