import { X } from 'lucide-react';
import { useState } from 'react';
import type { KeyboardEvent } from 'react';

import { Input } from '@/components/primitives';

export interface TagEditorProps {
  id: string;
  tags: string[];
  onChange: (tags: string[]) => void;
  placeholder: string;
}

/**
 * A comma- or Enter-separated list of short strings.
 *
 * Lived inside the Profile page while skills were the only such list. The master
 * resume added several more — an experience's technologies, a project's, the
 * certifications — and each of them is the same control with the same keyboard
 * behaviour, so it moved out here rather than being reimplemented per section.
 */
export function TagEditor({ id, tags, onChange, placeholder }: TagEditorProps) {
  const [value, setValue] = useState('');

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
    <div>
      {tags.length > 0 ? (
        <ul className="mb-2 flex flex-wrap gap-1.5">
          {tags.map((tag) => (
            <li key={tag}>
              <span className="inline-flex items-center gap-1 rounded-full border border-accent-500/35 bg-accent-500/12 py-0.5 pl-2.5 pr-1 text-xs font-medium text-accent-400">
                {tag}
                <button
                  type="button"
                  onClick={() => onChange(tags.filter((entry) => entry !== tag))}
                  aria-label={`Remover ${tag}`}
                  className="rounded-full p-0.5 hover:bg-accent-500/20"
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
        onChange={(event) => setValue(event.target.value)}
        onKeyDown={onKeyDown}
        onBlur={add}
      />
    </div>
  );
}
