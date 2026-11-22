import { useEffect, useState, type FormEvent } from "react";
import { HELP_DESCRIPTION } from "../model";
import type { Meta, SqlFilters } from "../types";
import { MultiSelect } from "./MultiSelect";

/**
 * The old sidebar: the form `my_form` (applies only on Submit, like st.form), then the Inputs / Rules / Show data
 * buttons. `filters` are the submitted ones; the form edits its own copy until Submit.
 */
export function Sidebar({
  user,
  meta,
  filters,
  warning,
  inputsOpen,
  rulesOpen,
  sqlOpen,
  onSubmit,
  onToggleInputs,
  onToggleRules,
  onToggleSql,
}: {
  user: string | undefined;
  meta: Meta;
  filters: SqlFilters;
  warning: string | null;
  inputsOpen: boolean;
  rulesOpen: boolean;
  sqlOpen: boolean;
  onSubmit: (filters: SqlFilters) => void;
  onToggleInputs: () => void;
  onToggleRules: () => void;
  onToggleSql: () => void;
}) {
  const [draft, setDraft] = useState(filters);
  useEffect(() => setDraft(filters), [filters]);
  const patch = (p: Partial<SqlFilters>) => setDraft((d) => ({ ...d, ...p }));
  const hasData = !!meta.min_date && !!meta.max_date;

  const submit = (e: FormEvent) => {
    e.preventDefault();
    onSubmit(draft);
  };

  return (
    <>
      {inputsOpen && user && <p className="logged-in">{user} logged in</p>}
      <form className="my-form" aria-label="Filters" onSubmit={submit}>
        <div className="field">
          <span className="label" id="date-range-label">
            Date range
          </span>
          <div className="dates" role="group" aria-labelledby="date-range-label">
            <input
              type="date"
              aria-label="Start date"
              value={draft.start ?? ""}
              min={meta.min_date ?? undefined}
              max={draft.end ?? meta.max_date ?? undefined}
              disabled={!hasData}
              onChange={(e) => patch({ start: e.target.value || null })}
            />
            <input
              type="date"
              aria-label="End date"
              value={draft.end ?? ""}
              min={draft.start ?? meta.min_date ?? undefined}
              max={meta.max_date ?? undefined}
              disabled={!hasData}
              onChange={(e) => patch({ end: e.target.value || null })}
            />
          </div>
        </div>
        <MultiSelect label="Categories in" options={meta.data_categories} value={draft.category_in} onChange={(v) => patch({ category_in: v })} />
        <MultiSelect
          label="Categories not in"
          options={meta.data_categories}
          value={draft.category_not_in}
          onChange={(v) => patch({ category_not_in: v })}
        />
        <div className="field">
          <div className="label with-help">
            <label htmlFor="description-box">Description</label>
            <span className="help" title={HELP_DESCRIPTION} role="img" aria-label={HELP_DESCRIPTION}>
              ?
            </span>
          </div>
          <input id="description-box" type="text" value={draft.description} onChange={(e) => patch({ description: e.target.value })} />
        </div>
        <MultiSelect label="Source file" options={meta.sources} value={draft.sources} onChange={(v) => patch({ sources: v })} />
        <button type="submit">Submit</button>
      </form>
      {warning && (
        <p className="warning" role="alert">
          {warning}
        </p>
      )}
      <div className="side-buttons">
        <button type="button" aria-pressed={inputsOpen} onClick={onToggleInputs}>
          Inputs
        </button>
        <button type="button" aria-pressed={rulesOpen} onClick={onToggleRules}>
          Rules
        </button>
        <button type="button" aria-pressed={sqlOpen} onClick={onToggleSql}>
          Show data
        </button>
      </div>
    </>
  );
}
