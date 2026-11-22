// The old Streamlit app's logic that does not need a browser, ported from src/main.py.
import type { AppState, Cell, Group, Meta, Rules, SqlFilters, TransactionUpdate } from "./types";

export const GROUPS: Group[] = ["auto", "year", "month", "week", "day"];

export const HELP_DESCRIPTION = "^ is and, + is or, ! is not, * is wildcard";

/** Python's str.title(): the first letter of every run of letters upper case, the rest lower. */
export function pyTitle(s: string): string {
  return s.replace(/\p{L}+/gu, (w) => w[0].toUpperCase() + w.slice(1).toLowerCase());
}

// --- the sidebar form -----------------------------------------------------------------------------

/**
 * old add_date_range_widget: the saved dates, clipped to the data's range
 * (min_default = max(data_min, saved_min); max_default = min(data_max, saved_max)); the whole data range if nothing
 * is saved. A saved range entirely outside the data would be empty: use the whole data range then.
 */
export function defaultRange(
  saved: Pick<AppState, "min_date" | "max_date">,
  data: Pick<Meta, "min_date" | "max_date">,
): { start: string | null; end: string | null } {
  if (!data.min_date || !data.max_date) return { start: null, end: null };
  const start = saved.min_date && saved.min_date > data.min_date ? saved.min_date : data.min_date;
  const end = saved.max_date && saved.max_date < data.max_date ? saved.max_date : data.max_date;
  return start > end ? { start: data.min_date, end: data.max_date } : { start, end };
}

/** old: `[v for v in config_value if v in valid_options]` */
export function onlyValid(selected: string[], options: string[]): string[] {
  return selected.filter((v) => options.includes(v));
}

export function initialFilters(state: AppState, meta: Pick<Meta, "min_date" | "max_date" | "data_categories">): SqlFilters {
  const { start, end } = defaultRange(state, meta);
  return {
    start,
    end,
    category_in: onlyValid(state.categories_in, meta.data_categories),
    category_not_in: onlyValid(state.categories_not_in, meta.data_categories),
    description: "",
    sources: [],
  };
}

/** What the old app wrote back to config.json after every render. */
export function savedFilters(f: SqlFilters): Pick<AppState, "min_date" | "max_date" | "categories_in" | "categories_not_in"> {
  return { min_date: f.start, max_date: f.end, categories_in: f.category_in, categories_not_in: f.category_not_in };
}

// --- the Rules panel (old add_rules) --------------------------------------------------------------

/** The "Save rule" button: one rule, either kind, not both. */
export function saveRuleState(categoryRule: string, descriptionRule: string): { disabled: boolean; help: string } {
  if (!categoryRule && !descriptionRule) return { disabled: true, help: "No rule specified" };
  if (categoryRule && descriptionRule) return { disabled: true, help: "Specify only one rule" };
  return { disabled: false, help: "" };
}

export function saveCategoryState(newCategory: string): { disabled: boolean; help: string } {
  return newCategory ? { disabled: false, help: "" } : { disabled: true, help: "No category specified" };
}

export function deleteState(nothingSelected: boolean): { disabled: boolean; help: string } {
  return nothingSelected ? { disabled: true, help: "Nothing to delete" } : { disabled: false, help: "" };
}

/** old save_rule */
export function withRule(rules: Rules, rule: { categoryRule: string; descriptionRule: string; target: string }): Rules {
  const next = structuredClone(rules);
  if (rule.descriptionRule) next.description[rule.descriptionRule] = rule.target;
  if (rule.categoryRule) next.category[rule.categoryRule] = rule.target;
  return next;
}

/** old save_category: `category.strip().title()` */
export function withCategory(rules: Rules, name: string, color: string): Rules {
  const next = structuredClone(rules);
  next.new_categories[pyTitle(name.trim())] = color;
  return next;
}

/** old delete_selections */
export function withoutSelections(
  rules: Rules,
  gone: { categoryRules: string[]; descriptionRules: string[]; newCategories: string[] },
): Rules {
  const next = structuredClone(rules);
  gone.categoryRules.forEach((r) => delete next.category[r]);
  gone.descriptionRules.forEach((r) => delete next.description[r]);
  gone.newCategories.forEach((c) => delete next.new_categories[c]);
  return next;
}

/** old: `sorted(set(df_initial["category"].unique().tolist() + list(new_categories)))` */
export function targetCategories(dataCategories: string[], rules: Rules): string[] {
  return [...new Set([...dataCategories, ...Object.keys(rules.new_categories)])].sort();
}

// --- add a new row (old add_row) -------------------------------------------------------------------

export function newRowState(description: string, amount: number): { disabled: boolean; help: string } {
  let help = "";
  if (!description) help = "No description";
  if (amount === 0) help = help ? `${help}, amount is 0` : "Amount is 0";
  return { disabled: !description || amount === 0, help };
}

// --- the data editor --------------------------------------------------------------------------------

export const READ_ONLY_COLUMNS = ["pk", "source_file", "line"];
export const EDITABLE = ["date", "description", "amount", "category"] as const;
export type Editable = (typeof EDITABLE)[number];
export type Edits = Record<string, Partial<Record<Editable, string | number>>>;

export const ROW_PK = "pk";

/** The rows of a query result, as the editor shows them: amounts rounded to 2 decimals, dates as YYYY-MM-DD. */
export function displayValue(column: string, value: Cell): string | number | null {
  if (column === "amount" && typeof value === "number") return Math.round(value * 100) / 100;
  if (column === "date" && typeof value === "string") return value.slice(0, 10);
  return value;
}

/** Records by pk with their displayed values. */
export function rowRecords(columns: string[], rows: Cell[][]): Record<string, Record<string, string | number | null>> {
  const out: Record<string, Record<string, string | number | null>> = {};
  for (const row of rows) {
    const rec: Record<string, string | number | null> = {};
    columns.forEach((c, i) => (rec[c] = displayValue(c, row[i])));
    out[String(rec[ROW_PK])] = rec;
  }
  return out;
}

/** Sets one cell's edit; setting it back to what it was removes the edit. */
export function setEdit(
  edits: Edits,
  original: Record<string, string | number | null>,
  pk: string,
  column: Editable,
  value: string | number,
): Edits {
  const next: Edits = { ...edits, [pk]: { ...edits[pk] } };
  if (value === original[column]) delete next[pk][column];
  else next[pk][column] = value;
  if (Object.keys(next[pk]).length === 0) delete next[pk];
  return next;
}

export interface Changed {
  pk: string;
  row: Record<string, string | number | null>; // the whole row with the edits applied (old: changed_row)
  patch: TransactionUpdate; // only what changed, among category / description / amount / date
}

export function changedRows(records: Record<string, Record<string, string | number | null>>, edits: Edits): Changed[] {
  const out: Changed[] = [];
  for (const [pk, change] of Object.entries(edits)) {
    const original = records[pk];
    if (!original || Object.keys(change).length === 0) continue;
    out.push({
      pk,
      row: { ...original, ...change },
      patch: change as TransactionUpdate,
    });
  }
  return out;
}

/** Streamlit's default number display: no thousands separators, no trailing zeros. */
export function plainNumber(n: number): string {
  return String(Math.round(n * 10000) / 10000);
}
