import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState, type FormEvent } from "react";
import { api } from "../api";
import { friendly, showError } from "../banner";
import { filtersKey, type Filters } from "../filters";
import { formatMoney, today } from "../format";
import { useRefreshData, useTransactions } from "../hooks";
import type { Meta, Order, SortKey, Transaction, TransactionPage, TransactionUpdate } from "../types";
import { QueryStatus } from "./Status";

export const PAGE_SIZE = 100;

const COLUMNS: { key: SortKey; label: string; numeric?: boolean }[] = [
  { key: "date", label: "Date" },
  { key: "description", label: "Description" },
  { key: "amount", label: "Amount", numeric: true },
  { key: "category", label: "Category" },
  { key: "source", label: "Source" },
];

export function Transactions({ filters, meta }: { filters: Filters; meta: Meta | undefined }) {
  const [sort, setSort] = useState<SortKey>("date");
  const [order, setOrder] = useState<Order>("desc");
  const [page, setPage] = useState(0);
  const key = filtersKey(filters);
  useEffect(() => setPage(0), [key]);

  const query = useTransactions(filters, sort, order, page, PAGE_SIZE);
  const client = useQueryClient();
  const refresh = useRefreshData();

  const update = useMutation({
    mutationFn: ({ pk, body }: { pk: string; body: TransactionUpdate }) => api.updateTransaction(pk, body),
    // Show the edit at once; put the old rows back if the server says no.
    onMutate: async ({ pk, body }) => {
      await client.cancelQueries({ queryKey: ["transactions"] });
      const snapshots = client.getQueriesData<TransactionPage>({ queryKey: ["transactions"] });
      client.setQueriesData<TransactionPage>({ queryKey: ["transactions"] }, (old) =>
        old && { ...old, rows: old.rows.map((r) => (r.pk === pk ? { ...r, ...body, edited: true } : r)) },
      );
      return { snapshots };
    },
    onError: (_err, _vars, ctx) => ctx?.snapshots.forEach(([k, data]) => client.setQueryData(k, data)),
    onSettled: () => refresh(),
  });

  const remove = useMutation({
    mutationFn: (pk: string) => api.deleteTransaction(pk),
    onError: showError,
    onSettled: () => refresh(),
  });

  const sortBy = (next: SortKey) => {
    if (next === sort) setOrder(order === "asc" ? "desc" : "asc");
    else {
      setSort(next);
      setOrder(next === "date" || next === "amount" ? "desc" : "asc");
    }
    setPage(0);
  };

  const data = query.data;
  const pages = data ? Math.max(1, Math.ceil(data.total / PAGE_SIZE)) : 1;
  const from = data && data.total ? page * PAGE_SIZE + 1 : 0;
  const to = data ? Math.min(data.total, (page + 1) * PAGE_SIZE) : 0;
  const categories = meta?.categories ?? [];

  return (
    <div className="transactions">
      <AddTransaction categories={categories} />
      <QueryStatus query={query} />
      {data && (
        <>
          <p className="summary" aria-live="polite">
            {data.total === 0 ? "No transactions match these filters." : `${from}–${to} of ${data.total.toLocaleString("en-US")}`}
            {data.total > 0 && (
              <>
                {" · sum "}
                <strong className="num">{formatMoney(data.sum)}</strong>
              </>
            )}
          </p>
          {data.rows.length > 0 && (
            <table className="tx">
              <thead>
                <tr>
                  {COLUMNS.map((c) => (
                    <th key={c.key} scope="col" className={c.numeric ? "num" : ""} aria-sort={sort === c.key ? (order === "asc" ? "ascending" : "descending") : "none"}>
                      <button type="button" className="sort" onClick={() => sortBy(c.key)}>
                        {c.label}
                        <span aria-hidden="true">{sort === c.key ? (order === "asc" ? " ▲" : " ▼") : ""}</span>
                      </button>
                    </th>
                  ))}
                  <th scope="col">
                    <span className="visually-hidden">Actions</span>
                  </th>
                </tr>
              </thead>
              <tbody>
                {data.rows.map((row) => (
                  <Row
                    key={row.pk}
                    row={row}
                    categories={categories}
                    onSave={(body) => update.mutateAsync({ pk: row.pk, body })}
                    onDelete={() => remove.mutate(row.pk)}
                  />
                ))}
              </tbody>
            </table>
          )}
          {pages > 1 && (
            <nav className="pager" aria-label="Pages">
              <button type="button" disabled={page === 0} onClick={() => setPage(page - 1)}>
                Previous
              </button>
              <span>
                Page {page + 1} of {pages}
              </span>
              <button type="button" disabled={page + 1 >= pages} onClick={() => setPage(page + 1)}>
                Next
              </button>
            </nav>
          )}
        </>
      )}
    </div>
  );
}

function Row({
  row,
  categories,
  onSave,
  onDelete,
}: {
  row: Transaction;
  categories: string[];
  onSave: (body: TransactionUpdate) => Promise<unknown>;
  onDelete: () => void;
}) {
  const [editing, setEditing] = useState(false);
  const [confirming, setConfirming] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [draft, setDraft] = useState({ date: "", description: "", amount: "", category: "" });

  const start = () => {
    setDraft({ date: row.date ?? "", description: row.description ?? "", amount: String(row.amount), category: row.category ?? "" });
    setError(null);
    setEditing(true);
  };

  const save = async (e: FormEvent) => {
    e.preventDefault();
    const body: TransactionUpdate = {};
    const amount = Number(draft.amount);
    if (draft.amount.trim() === "" || !Number.isFinite(amount)) return setError("Amount must be a number.");
    if (!draft.description.trim()) return setError("Description can't be empty.");
    if (draft.date && draft.date !== row.date) body.date = draft.date;
    if (draft.description.trim() !== row.description) body.description = draft.description.trim();
    if (amount !== row.amount) body.amount = amount;
    if (draft.category && draft.category !== row.category) body.category = draft.category;
    if (Object.keys(body).length === 0) return setEditing(false);
    setSaving(true);
    setError(null);
    try {
      await onSave(body);
      setEditing(false);
    } catch (err) {
      setError(friendly(err));
    } finally {
      setSaving(false);
    }
  };

  if (editing) {
    const options = draft.category && !categories.includes(draft.category) ? [draft.category, ...categories] : categories;
    return (
      <tr className="editing">
        <td colSpan={6}>
          <form className="row-form" onSubmit={save}>
            <label>
              Date
              <input type="date" value={draft.date} onChange={(e) => setDraft({ ...draft, date: e.target.value })} />
            </label>
            <label className="grow">
              Description
              <input value={draft.description} maxLength={500} onChange={(e) => setDraft({ ...draft, description: e.target.value })} />
            </label>
            <label>
              Amount
              <input type="number" step="0.01" inputMode="decimal" value={draft.amount} onChange={(e) => setDraft({ ...draft, amount: e.target.value })} />
            </label>
            <label>
              Category
              <select value={draft.category} onChange={(e) => setDraft({ ...draft, category: e.target.value })}>
                {options.map((c) => (
                  <option key={c} value={c}>
                    {c}
                  </option>
                ))}
              </select>
            </label>
            <div className="actions">
              <button type="submit" className="primary" disabled={saving}>
                {saving ? "Saving…" : "Save"}
              </button>
              <button type="button" disabled={saving} onClick={() => setEditing(false)}>
                Cancel
              </button>
            </div>
            {error && (
              <p className="error" role="alert">
                {error}
              </p>
            )}
          </form>
        </td>
      </tr>
    );
  }

  return (
    <tr>
      <td data-label="Date">{row.date ?? "?"}</td>
      <td data-label="Description">
        {row.description}
        {row.edited && (
          <span className="edited" title="You changed this transaction">
            {" "}
            ✎<span className="visually-hidden"> edited</span>
          </span>
        )}
      </td>
      <td data-label="Amount" className="num">
        {formatMoney(row.amount)}
      </td>
      <td data-label="Category">{row.category}</td>
      <td data-label="Source">{row.source_file}</td>
      <td className="actions">
        {confirming ? (
          <span className="confirm" role="group" aria-label="Confirm delete">
            <span className="small">This removes it from the views.</span>
            <button type="button" className="danger" onClick={onDelete}>
              Remove
            </button>
            <button type="button" onClick={() => setConfirming(false)}>
              Keep
            </button>
          </span>
        ) : (
          <>
            <button type="button" onClick={start} aria-label={`Edit ${row.description ?? "transaction"}`}>
              Edit
            </button>
            <button type="button" onClick={() => setConfirming(true)} aria-label={`Delete ${row.description ?? "transaction"}`}>
              Delete
            </button>
          </>
        )}
      </td>
    </tr>
  );
}

function AddTransaction({ categories }: { categories: string[] }) {
  const refresh = useRefreshData();
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState({ date: today(), description: "", amount: "", category: "" });
  const [problem, setProblem] = useState<string | null>(null);
  const [added, setAdded] = useState(false);

  const add = useMutation({
    mutationFn: api.addTransaction,
    onError: showError,
    onSuccess: () => {
      setForm((f) => ({ ...f, description: "", amount: "" }));
      setAdded(true);
      return refresh();
    },
  });

  const submit = (e: FormEvent) => {
    e.preventDefault();
    const amount = Number(form.amount);
    setAdded(false);
    if (!form.description.trim()) return setProblem("Add a description.");
    if (form.amount.trim() === "" || !Number.isFinite(amount) || amount === 0) return setProblem("Amount must be a number other than 0.");
    setProblem(null);
    add.mutate({ date: form.date, description: form.description.trim(), amount, category: form.category || categories[0] || "Other" });
  };

  if (!open) {
    return (
      <button type="button" className="add-toggle" onClick={() => setOpen(true)}>
        Add transaction
      </button>
    );
  }
  return (
    <form className="add-form" onSubmit={submit} aria-label="Add transaction">
      <label>
        Date
        <input type="date" value={form.date} onChange={(e) => setForm({ ...form, date: e.target.value })} required />
      </label>
      <label className="grow">
        Description
        <input value={form.description} maxLength={500} onChange={(e) => setForm({ ...form, description: e.target.value })} />
      </label>
      <label>
        Amount
        <input type="number" step="0.01" inputMode="decimal" value={form.amount} onChange={(e) => setForm({ ...form, amount: e.target.value })} />
      </label>
      <label>
        Category
        <select value={form.category || categories[0] || ""} onChange={(e) => setForm({ ...form, category: e.target.value })}>
          {categories.map((c) => (
            <option key={c} value={c}>
              {c}
            </option>
          ))}
        </select>
      </label>
      <div className="actions">
        <button type="submit" className="primary" disabled={add.isPending}>
          {add.isPending ? "Adding…" : "Add"}
        </button>
        <button type="button" onClick={() => setOpen(false)}>
          Close
        </button>
      </div>
      {problem && (
        <p className="error" role="alert">
          {problem}
        </p>
      )}
      {added && <p role="status">Added.</p>}
    </form>
  );
}
