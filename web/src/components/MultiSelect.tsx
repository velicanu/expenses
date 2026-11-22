import { useId } from "react";

interface Props {
  label: string;
  options: string[];
  selected: string[];
  onChange: (next: string[]) => void;
}

/** A dropdown of checkboxes: works with a thumb, unlike <select multiple>. */
export function MultiSelect({ label, options, selected, onChange }: Props) {
  const id = useId();
  const toggle = (option: string) =>
    onChange(selected.includes(option) ? selected.filter((s) => s !== option) : [...selected, option]);
  return (
    <details className="multiselect">
      <summary aria-label={`${label}: ${selected.length ? `${selected.length} selected` : "any"}`}>
        {label}
        {selected.length > 0 && <span className="count">{selected.length}</span>}
      </summary>
      <div className="menu" role="group" aria-labelledby={id}>
        <span id={id} className="visually-hidden">
          {label}
        </span>
        {options.length === 0 && <p className="muted">Nothing to choose from yet.</p>}
        {options.map((option) => (
          <label key={option} className="check">
            <input type="checkbox" checked={selected.includes(option)} onChange={() => toggle(option)} />
            {option}
          </label>
        ))}
        {selected.length > 0 && (
          <button type="button" className="link" onClick={() => onChange([])}>
            Clear
          </button>
        )}
      </div>
    </details>
  );
}
