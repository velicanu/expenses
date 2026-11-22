import { useEffect, useId, useRef, useState } from "react";

/** Streamlit's multiselect: tags in a box ("Choose options" when empty), a list of the other options to pick from. */
export function MultiSelect({
  label,
  options,
  value,
  onChange,
}: {
  label: string;
  options: string[];
  value: string[];
  onChange: (next: string[]) => void;
}) {
  const [open, setOpen] = useState(false);
  const [filter, setFilter] = useState("");
  const root = useRef<HTMLDivElement>(null);
  const id = useId();

  useEffect(() => {
    if (!open) return;
    const close = (e: MouseEvent) => {
      if (root.current && !root.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", close);
    return () => document.removeEventListener("mousedown", close);
  }, [open]);

  const remaining = options.filter((o) => !value.includes(o) && o.toLowerCase().includes(filter.toLowerCase()));

  return (
    <div className="field" ref={root}>
      <span className="label" id={`${id}-label`}>
        {label}
      </span>
      <div
        className="ms"
        role="combobox"
        tabIndex={0}
        aria-labelledby={`${id}-label`}
        aria-haspopup="listbox"
        aria-expanded={open}
        aria-controls={`${id}-list`}
        onClick={(e) => {
          if ((e.target as HTMLElement).closest("button")) return;
          setOpen((o) => !o);
        }}
        onKeyDown={(e) => {
          if (e.target !== e.currentTarget) return;
          if (e.key === "Enter" || e.key === " " || e.key === "ArrowDown") {
            e.preventDefault();
            setOpen(true);
          } else if (e.key === "Escape") setOpen(false);
          else if (e.key === "Backspace" && value.length) onChange(value.slice(0, -1));
        }}
      >
        <span className="tags">
          {value.length === 0 && <span className="placeholder">Choose options</span>}
          {value.map((v) => (
            <span className="tag" key={v}>
              {v}
              <button type="button" aria-label={`Remove ${v}`} onClick={() => onChange(value.filter((x) => x !== v))}>
                ×
              </button>
            </span>
          ))}
        </span>
        {value.length > 0 && (
          <button type="button" className="clear" aria-label={`Clear ${label}`} onClick={() => onChange([])}>
            ⊗
          </button>
        )}
        <span className="chevron" aria-hidden="true">
          ⌄
        </span>
      </div>
      {open && (
        <div className="ms-list">
          <input
            type="text"
            aria-label={`Filter ${label}`}
            placeholder="Type to filter"
            value={filter}
            autoFocus
            onChange={(e) => setFilter(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Escape") setOpen(false);
              if (e.key === "Enter") e.preventDefault(); // inside a form: do not submit it
            }}
          />
          <ul role="listbox" id={`${id}-list`} aria-label={label}>
            {remaining.length === 0 && <li className="none">No results</li>}
            {remaining.map((o) => (
              <li key={o} role="option" aria-selected={false} onClick={() => onChange([...value, o])}>
                {o}
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
