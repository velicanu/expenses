import { DESCRIPTION_HELP, descriptionProblem, type Filters } from "../filters";
import type { Meta } from "../types";
import { MultiSelect } from "./MultiSelect";

interface Props {
  filters: Filters;
  meta: Meta | undefined;
  onChange: (patch: Partial<Filters>) => void;
  onReset: () => void;
}

export function FilterBar({ filters, meta, onChange, onReset }: Props) {
  const problem = descriptionProblem(filters.q);
  return (
    <form className="filters" role="search" aria-label="Filters" onSubmit={(e) => e.preventDefault()}>
      <label>
        From
        <input
          type="date"
          value={filters.start || meta?.min_date || ""}
          min={meta?.min_date ?? undefined}
          max={meta?.max_date ?? undefined}
          onChange={(e) => onChange({ start: e.target.value })}
        />
      </label>
      <label>
        To
        <input
          type="date"
          value={filters.end || meta?.max_date || ""}
          min={meta?.min_date ?? undefined}
          max={meta?.max_date ?? undefined}
          onChange={(e) => onChange({ end: e.target.value })}
        />
      </label>
      <MultiSelect
        label="Categories in"
        options={meta?.categories ?? []}
        selected={filters.categoryIn}
        onChange={(categoryIn) => onChange({ categoryIn })}
      />
      <MultiSelect
        label="Categories not in"
        options={meta?.categories ?? []}
        selected={filters.categoryNotIn}
        onChange={(categoryNotIn) => onChange({ categoryNotIn })}
      />
      <MultiSelect label="Source file" options={meta?.sources ?? []} selected={filters.sources} onChange={(sources) => onChange({ sources })} />
      <label className="grow">
        Description
        <input
          type="search"
          value={filters.q}
          maxLength={200}
          placeholder="uber+lyft, !refund, whole*foods"
          aria-describedby="q-help"
          aria-invalid={problem ? true : undefined}
          onChange={(e) => onChange({ q: e.target.value })}
        />
      </label>
      <button type="button" onClick={onReset}>
        Reset
      </button>
      <p id="q-help" className={problem ? "error" : "muted small"} role={problem ? "alert" : undefined}>
        {problem ?? DESCRIPTION_HELP}
      </p>
    </form>
  );
}
