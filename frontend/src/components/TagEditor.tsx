import { X } from 'lucide-react';
import { useState } from 'react';
import type { KeyboardEvent } from 'react';

import { Input } from '@/components/primitives';
import { cn } from '@/lib/utils';

export interface TagEditorProps {
  id: string;
  tags: string[];
  onChange: (tags: string[]) => void;
  placeholder: string;
  disabled?: boolean;
  className?: string;
  /** Marked with the accent treatment — what this posting asked for. */
  highlight?: string[];
}

/**
 * A list of short strings: skills, technologies, languages.
 *
 * Enter or a comma commits, backspace on an empty field removes the last tag,
 * and blur commits whatever was typed — leaving the field with unsaved text is
 * the mistake people actually make.
 *
 * `highlight` exists for the per-application resume: the terms the posting
 * asked for are shown in accent so re-ordering is visible as *prioritisation*
 * rather than as an arbitrary shuffle.
 */
export function TagEditor({
  id,
  tags,
  onChange,
  placeholder,
  disabled,
  className,
  highlight,
}: TagEditorProps) {
  const [value, setValue] = useState('');
  const highlighted = new Set((highlight ?? []).map((item) => item.toLowerCase()));

  const add = () => {
    const parts = value
      .split(',')
      .map((part) => part.trim())
      .filter((part) => part.length > 0 && !tags.includes(part));
    if (parts.length > 0) onChange([...tags, ...parts]);
    setValue('');
  };

  const onKeyDown = (event: KeyboardEvent<HTMLInputElement>) => {
    if (event.key === 'Enter' || event.key === ',') {
      event.preventDefault();
      add();
    } else if (event.key === 'Backspace' && value === '' && tags.length > 0) {
      onChange(tags.slice(0, -1));
    }
  };

  return (
    <div className={className}>
      {tags.length > 0 ? (
        <ul className="mb-2 flex flex-wrap gap-1.5">
          {tags.map((tag) => (
            <li key={tag}>
              <span
                className={cn(
                  'inline-flex items-center gap-1 rounded-full border py-0.5 pl-2.5 pr-1 text-xs font-medium',
                  highlighted.has(tag.toLowerCase())
                    ? 'border-accent-500/35 bg-accent-500/12 text-accent-400'
                    : 'border-line bg-surface-sunken text-content-muted',
                )}
              >
                {tag}
                <button
                  type="button"
                  disabled={disabled}
                  onClick={() => onChange(tags.filter((entry) => entry !== tag))}
                  aria-label={`Remover ${tag}`}
                  className="rounded-full p-0.5 hover:bg-accent-500/20 disabled:cursor-not-allowed disabled:opacity-50"
                >
                  <X aria-hidden className="h-3 w-3" />
                </button>
              </span>
            </li>
          ))}
        </ul>
      ) : null}
      <Input
        id={id}
        value={value}
        placeholder={placeholder}
        disabled={disabled}
        onChange={(event) => setValue(event.target.value)}
        onKeyDown={onKeyDown}
        onBlur={add}
      />
    </div>
  );
}
