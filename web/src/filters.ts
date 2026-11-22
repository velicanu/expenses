import { useCallback, useEffect, useState } from "react";

export interface Filters {
  start: string; // "" = from the first transaction
  end: string; // "" = to the last
  categoryIn: string[];
  categoryNotIn: string[];
  sources: string[];
  q: string;
}

export const EMPTY_FILTERS: Filters = { start: "", end: "", categoryIn: [], categoryNotIn: [], sources: [], q: "" };

export const STORAGE_KEY = "expenses.filters.v1";

export const DESCRIPTION_HELP =
  "a+b matches a or b, a^b matches a and b (not both kinds in one box), !a excludes a, * matches anything. Not case-sensitive.";

/** The query-string parameters the API understands (empty ones are dropped by buildQuery). */
export function filtersToParams(f: Filters) {
  return {
    start: f.start || undefined,
    end: f.end || undefined,
    category_in: f.categoryIn,
    category_not_in: f.categoryNotIn,
    source: f.sources,
    q: f.q.trim() || undefined,
  };
}

/** The API refuses + and ^ together; say so before sending. */
export function descriptionProblem(q: string): string | null {
  return q.includes("+") && q.includes("^") ? "Use either + (or) or ^ (and) in the description, not both." : null;
}

const strings = (v: unknown): string[] => (Array.isArray(v) ? v.filter((x): x is string => typeof x === "string") : []);
const text = (v: unknown): string => (typeof v === "string" ? v : "");

/** Whatever is in localStorage may be old or hand-edited: take only what has the right shape. */
export function loadFilters(storage: Pick<Storage, "getItem"> = localStorage): Filters {
  try {
    const raw = JSON.parse(storage.getItem(STORAGE_KEY) ?? "null") as Record<string, unknown> | null;
    if (!raw || typeof raw !== "object") return EMPTY_FILTERS;
    return {
      start: text(raw.start),
      end: text(raw.end),
      categoryIn: strings(raw.categoryIn),
      categoryNotIn: strings(raw.categoryNotIn),
      sources: strings(raw.sources),
      q: text(raw.q),
    };
  } catch {
    return EMPTY_FILTERS;
  }
}

export function saveFilters(f: Filters, storage: Pick<Storage, "setItem"> = localStorage): void {
  try {
    storage.setItem(STORAGE_KEY, JSON.stringify(f));
  } catch {
    /* private mode or full: the filters just do not persist */
  }
}

export function useFilters(): [Filters, (patch: Partial<Filters>) => void, () => void] {
  const [filters, setFilters] = useState<Filters>(() => loadFilters());
  useEffect(() => saveFilters(filters), [filters]);
  const patch = useCallback((p: Partial<Filters>) => setFilters((f) => ({ ...f, ...p })), []);
  const reset = useCallback(() => setFilters(EMPTY_FILTERS), []);
  return [filters, patch, reset];
}

export function filtersKey(f: Filters): string {
  return JSON.stringify(f);
}
