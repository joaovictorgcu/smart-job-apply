import { Check } from 'lucide-react';

import { cn } from '@/lib/utils';

export interface ChipOption {
  value: string;
  label: string;
}

export interface ChipGroupProps {
  /** Used as the group's accessible name and to key the inputs. */
  legend: string;
  options: ChipOption[];
  selected: string[];
  onChange: (next: string[]) => void;
  hint?: string;
  className?: string;
}

/**
 * A multiple-choice question answered by tapping, not by opening a menu.
 *
 * Real checkboxes underneath: a `<select multiple>` is close to unusable on a
 * phone and a row of `<button>`s tells a screen reader nothing about what is
 * chosen. The visible chip is the checkbox's label, so a keyboard reaches every
 * option and the checked state is announced.
 *
 * Selecting nothing is a legitimate answer everywhere this is used — it means
 * "no preference", which never rules a posting out — so there is no "any"
 * option to pick.
 */
export function ChipGroup({
  legend,
  options,
  selected,
  onChange,
  hint,
  className,
}: ChipGroupProps) {
  const toggle = (value: string) =>
    onChange(
      selected.includes(value)
        ? selected.filter((entry) => entry !== value)
        : [...selected, value],
    );

  return (
    <fieldset className={className}>
      <legend className="label">{legend}</legend>
      <div className="flex flex-wrap gap-2">
        {options.map((option) => {
          const isSelected = selected.includes(option.value);
          return (
            <label
              key={option.value}
              className={cn(
                'inline-flex cursor-pointer items-center gap-1.5 rounded-full border px-3 py-1.5 text-xs font-medium transition-colors duration-150',
                isSelected
                  ? 'border-accent-500/50 bg-accent-500/12 text-accent-400'
                  : 'border-line bg-surface-sunken text-content-muted hover:border-line-strong hover:text-content',
              )}
            >
              <input
                type="checkbox"
                className="sr-only"
                checked={isSelected}
                onChange={() => toggle(option.value)}
              />
              {isSelected ? <Check aria-hidden className="h-3 w-3" /> : null}
              {option.label}
            </label>
          );
        })}
      </div>
      {hint ? <p className="hint mt-2">{hint}</p> : null}
    </fieldset>
  );
}
