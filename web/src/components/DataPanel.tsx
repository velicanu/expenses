import { useMutation } from "@tanstack/react-query";
import { useEffect, useMemo, useState } from "react";
import { api } from "../api";
import { showError } from "../banner";
import { today } from "../format";
import { useRefreshAll } from "../hooks";
import {
  READ_ONLY_COLUMNS,
  ROW_PK,
  changedRows,
  displayValue,
  newRowState,
  rowRecords,
  setEdit,
  type Edits,
  type Editable,
} from "../model";
import type { Meta, SqlResult } from "../types";

const ROW_HEIGHT = 36;
const VIEW_HEIGHT = 400; // the old data editor was about this tall
const OVERSCAN = 4;
const ISO_DATE = /^\d{4}-\d{2}-\d{2}$/;

/** The old "Add a new row" form (`add_row`). */
function AddRow({ meta }: { meta: Meta }) {
  const refresh = useRefreshAll();
  const [date, setDate] = useState(today());
  const [description, setDescription] = useState("");
  const [amount, setAmount] = useState(0);
  const [category, setCategory] = useState<string | null>(null);
  const chosen = category && meta.categories.includes(category) ? category : (meta.categories[0] ?? "");
  const state = newRowState(description, amount);

  const save = useMutation({
    mutationFn: () => api.addTransaction({ date, description, amount, category: chosen }),
    onSuccess: () => void refresh(),
    onError: showError,
  });

  return (
    <div className="add-row">
      <p>Add a new row</p>
      <div className="cols cols-4">
        <label className="field">
          <span className="label">Date</span>
          <input type="date" value={date} onChange={(e) => setDate(e.target.value)} />
        </label>
        <label className="field">
          <span className="label">Description</span>
          <input type="text" value={description} onChange={(e) => setDescription(e.target.value)} />
        </label>
        <label className="field">
          <span className="label">Amount</span>
          <input type="number" step="0.01" value={amount} onChange={(e) => setAmount(Number(e.target.value))} />
        </label>
        <label className="field">
          <span className="label">Category</span>
          <select value={chosen} onChange={(e) => setCategory(e.target.value)}>
            {meta.categories.map((c) => (
              <option key={c}>{c}</option>
            ))}
          </select>
        </label>
      </div>
      <button type="button" disabled={state.disabled || save.isPending || !date} title={state.help} onClick={() => save.mutate()}>
        Save new row
      </button>
    </div>
  );
}

/** One editable cell: reads like plain text until focused, like the old grid. */
function Cell({
  column,
  pk,
  original,
  edited,
  categories,
  onEdit,
}: {
  column: string;
  pk: string;
  original: string | number | null;
  edited: string | number | undefined;
  categories: string[];
  onEdit: (column: Editable, value: string | number) => void;
}) {
  const label = `${column} of ${pk}`;
  const shown = edited ?? original;
  const key = `${pk}:${column}:${String(original)}`; // a new original (after a save or a rerun) remounts the input
  if (column === "category") {
    const options = categories.includes(String(shown)) ? categories : [String(shown), ...categories];
    return (
      <select key={key} className="cell" aria-label={label} defaultValue={String(shown ?? "")} onChange={(e) => onEdit("category", e.target.value)}>
        {options.map((c) => (
          <option key={c}>{c}</option>
        ))}
      </select>
    );
  }
  if (column === "amount") {
    return (
      <input
        key={key}
        className="cell num"
        type="number"
        step="0.01"
        aria-label={label}
        defaultValue={String(shown ?? "")}
        onChange={(e) => {
          const n = Number(e.target.value);
          if (e.target.value !== "" && Number.isFinite(n)) onEdit("amount", n);
        }}
      />
    );
  }
  if (column === "date") {
    // text, not a native date input: that shows the browser's locale (06/16/2026); the old grid showed 2026-01-12
    return (
      <input
        key={key}
        className="cell"
        type="text"
        inputMode="numeric"
        placeholder="YYYY-MM-DD"
        aria-label={label}
        defaultValue={String(shown ?? "")}
        onChange={(e) => ISO_DATE.test(e.target.value) && onEdit("date", e.target.value)}
      />
    );
  }
  return (
    <input key={key} className="cell wide" type="text" aria-label={label} defaultValue={String(shown ?? "")} onChange={(e) => onEdit("description", e.target.value)} />
  );
}

/** The editable table of the query's rows. Only the rows in view are rendered (there can be ten thousand). */
function DataEditor({ result, meta }: { result: SqlResult; meta: Meta }) {
  const refresh = useRefreshAll();
  const [edits, setEdits] = useState<Edits>({});
  const [scrollTop, setScrollTop] = useState(0);
  useEffect(() => setEdits({}), [result]);

  const { columns, rows } = result;
  const pkIndex = columns.indexOf(ROW_PK);
  const records = useMemo(() => rowRecords(columns, rows), [columns, rows]);
  const changed = changedRows(records, edits);

  const first = Math.max(0, Math.floor(scrollTop / ROW_HEIGHT) - OVERSCAN);
  const last = Math.min(rows.length, first + Math.ceil(VIEW_HEIGHT / ROW_HEIGHT) + 2 * OVERSCAN);
  const editable = (c: string) => ["date", "description", "amount", "category"].includes(c) && !READ_ONLY_COLUMNS.includes(c);

  const save = useMutation({
    mutationFn: async () => {
      const failed: string[] = [];
      let firstError: unknown = null;
      for (const c of changed) {
        try {
          await api.updateTransaction(c.pk, c.patch);
        } catch (e) {
          failed.push(c.pk);
          firstError ??= e;
        }
      }
      if (firstError) throw firstError;
    },
    onSuccess: () => void refresh(),
    onError: (e) => {
      showError(e);
      void refresh();
    },
  });

  return (
    <>
      <div className="grid" style={{ height: Math.min(VIEW_HEIGHT, (rows.length + 1) * ROW_HEIGHT + 2) }} onScroll={(e) => setScrollTop(e.currentTarget.scrollTop)}>
        <table>
          <thead>
            <tr>
              {columns.map((c) => (
                <th key={c}>{c}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {first > 0 && (
              <tr aria-hidden="true" style={{ height: first * ROW_HEIGHT }}>
                <td colSpan={columns.length} />
              </tr>
            )}
            {rows.slice(first, last).map((row) => {
              const pk = String(row[pkIndex]);
              return (
                <tr key={pk} style={{ height: ROW_HEIGHT }}>
                  {columns.map((c, i) =>
                    editable(c) ? (
                      <td key={c} className={c === "amount" ? "num" : undefined}>
                        <Cell
                          column={c}
                          pk={pk}
                          original={displayValue(c, row[i])}
                          edited={edits[pk]?.[c as Editable]}
                          categories={meta.data_categories}
                          onEdit={(col, value) => setEdits((cur) => setEdit(cur, records[pk], pk, col, value))}
                        />
                      </td>
                    ) : (
                      <td key={c} className={typeof row[i] === "number" ? "num" : undefined}>
                        {String(displayValue(c, row[i]) ?? "")}
                      </td>
                    ),
                  )}
                </tr>
              );
            })}
            {last < rows.length && (
              <tr aria-hidden="true" style={{ height: (rows.length - last) * ROW_HEIGHT }}>
                <td colSpan={columns.length} />
              </tr>
            )}
          </tbody>
        </table>
      </div>

      {changed.length > 0 && (
        <div className="unsaved">
          <p>Unsaved changes:</p>
          <table className="plain">
            <thead>
              <tr>
                {columns.map((c) => (
                  <th key={c}>{c}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {changed.map((c) => (
                <tr key={c.pk}>
                  {columns.map((col) => (
                    <td key={col}>{String(c.row[col] ?? "")}</td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
          <button type="button" disabled={save.isPending} onClick={() => save.mutate()}>
            Save Changes
          </button>
        </div>
      )}
    </>
  );
}

/** The old "Show data" section: the SQL box, the + / - button for a new row, and the editable rows. */
export function DataPanel({
  typed,
  onTyped,
  onRun,
  error,
  result,
  loading,
  meta,
}: {
  typed: string;
  onTyped: (sql: string) => void;
  onRun: () => void; // Enter or leaving the box
  error: string | null;
  result: SqlResult | undefined;
  loading: boolean;
  meta: Meta;
}) {
  const [newRowClosed, setNewRowClosed] = useState(true); // the old `new_row` flag: True shows "+"

  return (
    <section aria-label="Data" className="panel">
      <div className="sql-row">
        <input
          type="text"
          className="sql"
          aria-label="Input sql"
          value={typed}
          spellCheck={false}
          onChange={(e) => onTyped(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && onRun()}
          onBlur={onRun}
        />
        <button type="button" className="small-button" onClick={() => setNewRowClosed((c) => !c)}>
          {newRowClosed ? "+" : "-"}
        </button>
      </div>
      {error && (
        <p className="alert error" role="alert">
          {error}
        </p>
      )}
      {!newRowClosed && <AddRow meta={meta} />}
      {result ? <DataEditor result={result} meta={meta} /> : loading ? <p className="muted">Loading…</p> : null}
    </section>
  );
}
