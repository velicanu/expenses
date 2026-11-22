import { useMutation } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { api } from "../api";
import { showError } from "../banner";
import { useAccounts, useFiles, useRefreshAll } from "../hooks";
import type { PipelineResult, PullResult } from "../types";

const NOTICE_MS = 6000; // the old app cleared its messages after 2 seconds; these carry reasons, so a little longer

function pipelineLine(r: PipelineResult | null): string | null {
  if (!r) return null;
  return r.ran ? `Pipeline ran in ${r.seconds} s: ${r.count} transactions.` : "Nothing to process yet: no card files were found.";
}

function pullLine(r: PullResult): string {
  if (r.accounts.length === 0) return "No linked accounts to pull.";
  return r.accounts.map((a) => ("error" in a ? `${a.alias}: ${a.error}` : `${a.alias}: ${a.pulled} transactions`)).join("; ");
}

/** The old "Inputs" section: linked cards, run the pipeline, refresh from Plaid, upload CSVs, delete raw files. */
export function InputsPanel() {
  const accounts = useAccounts();
  const files = useFiles();
  const refresh = useRefreshAll();

  const [message, setMessage] = useState<{ kind: "success" | "error" | "info"; text: string }[]>([]);
  useEffect(() => {
    if (message.length === 0) return;
    const t = setTimeout(() => setMessage([]), NOTICE_MS);
    return () => clearTimeout(t);
  }, [message]);

  const [picked, setPicked] = useState<File[]>([]);
  const [pickerKey, setPickerKey] = useState(1); // the old app bumped this to clear the upload box
  const [deleting, setDeleting] = useState(false);
  const [toDelete, setToDelete] = useState<string[]>([]);

  const run = useMutation({
    mutationFn: () => api.runPipeline(),
    onSuccess: (r) => {
      setMessage([{ kind: "info", text: pipelineLine(r) ?? "" }]);
      void refresh();
    },
    onError: showError,
  });

  const pull = useMutation({
    mutationFn: api.pull,
    onSuccess: (r) => {
      const failed = r.accounts.some((a) => "error" in a);
      setMessage([{ kind: failed ? "error" : "success", text: [pullLine(r), pipelineLine(r.pipeline)].filter(Boolean).join(" ") }]);
      void refresh();
    },
    onError: showError,
  });

  const upload = useMutation({
    mutationFn: (selected: File[]) => api.upload(selected),
    onSuccess: (r) => {
      const next: typeof message = [];
      if (r.saved.length) next.push({ kind: "success", text: "Saved: " + r.saved.join("; ") });
      if (r.failed.length) next.push({ kind: "error", text: "Failed: " + r.failed.join("; ") });
      setMessage(next);
      setPicked([]);
      setPickerKey((k) => k + 1);
      void refresh();
    },
    onError: showError,
  });

  const remove = useMutation({
    mutationFn: async (names: string[]) => {
      for (const name of names) await api.deleteFile(name);
      return names;
    },
    onSuccess: (names) => {
      setMessage([{ kind: "info", text: `Deleted: ${names.join("; ")}. Run the pipeline to update the data.` }]);
      setToDelete([]);
      void refresh();
    },
    onError: (e) => {
      showError(e);
      void refresh();
    },
  });

  const busy = run.isPending || pull.isPending || upload.isPending || remove.isPending;
  const toggleDelete = (name: string, on: boolean) =>
    setToDelete((cur) => (on ? [...cur.filter((n) => n !== name), name] : cur.filter((n) => n !== name)));

  return (
    <section aria-label="Inputs" className="panel">
      <h3 className="subheader">Linked cards:</h3>
      {accounts.data && accounts.data.length > 0 ? (
        <table className="plain">
          <thead>
            <tr>
              <th>alias</th>
              <th>institution</th>
              <th>start_date</th>
            </tr>
          </thead>
          <tbody>
            {accounts.data.map((a) => (
              <tr key={a.alias}>
                <td>{a.alias}</td>
                <td>{a.institution}</td>
                <td>{a.start_date}</td>
              </tr>
            ))}
          </tbody>
        </table>
      ) : (
        <p className="muted">{accounts.isPending ? "Loading…" : "No linked accounts."}</p>
      )}

      <div className="cols cols-2-5-5">
        <div className="col stack">
          <button type="button" disabled={busy} onClick={() => run.mutate()}>
            Run pipeline
          </button>
          {run.isPending && <p className="spinner">Running pipeline...</p>}
          <button type="button" disabled={busy} onClick={() => pull.mutate()}>
            Refresh data
          </button>
          {pull.isPending && <p className="spinner">Pulling transactions…</p>}
          <button type="button" disabled title="Linking a new Plaid account is not available in the new app yet">
            Link account
          </button>
        </div>

        <div className="col stack">
          <label className="field">
            <span className="label">upload data</span>
            <input
              key={pickerKey}
              type="file"
              accept=".csv,text/csv"
              multiple
              onChange={(e) => setPicked(Array.from(e.target.files ?? []))}
            />
          </label>
          <button type="button" disabled={busy || picked.length === 0} onClick={() => upload.mutate(picked)}>
            Upload files
          </button>
          {upload.isPending && <p className="spinner">Uploading and running the pipeline…</p>}
        </div>

        <div className="col stack">
          <label className="check">
            <input type="checkbox" checked={deleting} onChange={(e) => setDeleting(e.target.checked)} />
            Delete files
          </label>
          {deleting &&
            (files.data ?? []).map((f) => (
              <label className="check" key={f.name}>
                <input type="checkbox" checked={toDelete.includes(f.name)} onChange={(e) => toggleDelete(f.name, e.target.checked)} />
                Delete {f.name}
              </label>
            ))}
          {deleting && toDelete.length > 0 && (
            <button type="button" disabled={busy} onClick={() => remove.mutate(toDelete)}>
              Confirm Delete
            </button>
          )}
        </div>
      </div>

      {message.map((m) => (
        <p key={m.text} className={`alert ${m.kind}`} role={m.kind === "error" ? "alert" : "status"}>
          {m.text}
        </p>
      ))}
    </section>
  );
}
