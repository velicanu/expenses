import { useMutation } from "@tanstack/react-query";
import { useRef, useState, type DragEvent } from "react";
import { api } from "../api";
import { showError } from "../banner";
import { formatBytes, formatUnix } from "../format";
import { useAccounts, useFiles, useRefreshData } from "../hooks";
import type { Meta, PipelineResult, PullResult, UploadResult } from "../types";
import { QueryStatus } from "./Status";

const describe = (p: PipelineResult | null): string | null =>
  p === null ? null : p.ran ? `Pipeline ran: ${p.count.toLocaleString("en-US")} transactions in ${p.seconds}s.` : "Pipeline had nothing to run.";

export function DataView({ meta }: { meta: Meta | undefined }) {
  const refresh = useRefreshData();
  const files = useFiles();
  const accounts = useAccounts();
  const [upload, setUpload] = useState<UploadResult | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [pull, setPull] = useState<PullResult | null>(null);
  const [deleting, setDeleting] = useState<string | null>(null);
  const [needsRerun, setNeedsRerun] = useState(false);
  const [dragging, setDragging] = useState(false);
  const picker = useRef<HTMLInputElement>(null);

  const send = useMutation({
    mutationFn: (list: File[]) => api.upload(list),
    onError: showError,
    onSuccess: async (result) => {
      setUpload(result);
      setMessage(describe(result.pipeline));
      await refresh();
    },
  });

  const run = useMutation({
    mutationFn: (rulesOnly: boolean) => api.runPipeline(rulesOnly),
    onError: showError,
    onSuccess: async (result) => {
      setMessage(describe(result));
      setNeedsRerun(false);
      await refresh();
    },
  });

  const del = useMutation({
    mutationFn: (name: string) => api.deleteFile(name),
    onError: showError,
    onSuccess: async () => {
      setDeleting(null);
      setNeedsRerun(true);
      await refresh();
    },
  });

  const plaid = useMutation({
    mutationFn: api.pull,
    onError: showError,
    onSuccess: async (result) => {
      setPull(result);
      setMessage(describe(result.pipeline));
      await refresh();
    },
  });

  const choose = (list: FileList | File[] | null) => {
    const csvs = Array.from(list ?? []).filter((f) => f.name.toLowerCase().endsWith(".csv"));
    if (csvs.length === 0) return showError(new Error("Choose one or more .csv files."));
    setUpload(null);
    send.mutate(csvs);
  };
  const drop = (e: DragEvent) => {
    e.preventDefault();
    setDragging(false);
    choose(e.dataTransfer.files);
  };
  const busy = send.isPending || run.isPending || plaid.isPending;

  return (
    <div className="data">
      <section aria-labelledby="h-upload">
        <h2 id="h-upload">Upload</h2>
        <div
          className={`dropzone${dragging ? " over" : ""}`}
          onDragOver={(e) => {
            e.preventDefault();
            setDragging(true);
          }}
          onDragLeave={() => setDragging(false)}
          onDrop={drop}
        >
          <p>Drop CSV exports here, or</p>
          <input ref={picker} id="csv-input" type="file" accept=".csv,text/csv" multiple className="visually-hidden" onChange={(e) => choose(e.target.files)} />
          <label htmlFor="csv-input" className="button">
            Choose CSV files
          </label>
          {send.isPending && <p role="status">Uploading and running the pipeline…</p>}
        </div>
        {upload && (
          <div className="results" role="status">
            {upload.saved.length > 0 && (
              <>
                <h3>Saved</h3>
                <ul>
                  {upload.saved.map((s) => (
                    <li key={s}>{s}</li>
                  ))}
                </ul>
              </>
            )}
            {upload.failed.length > 0 && (
              <>
                <h3>Not saved</h3>
                <ul className="error-list">
                  {upload.failed.map((s) => (
                    <li key={s}>{s}</li>
                  ))}
                </ul>
                <p className="muted small">Files are kept only if their columns match a known bank or card export.</p>
              </>
            )}
          </div>
        )}
      </section>

      <section aria-labelledby="h-files">
        <div className="section-head">
          <h2 id="h-files">Files</h2>
          <div className="actions">
            <button type="button" className={needsRerun ? "primary" : ""} disabled={busy} onClick={() => run.mutate(false)}>
              {run.isPending ? "Running…" : "Run pipeline"}
            </button>
          </div>
        </div>
        {needsRerun && <p className="notice">A file was removed. Run the pipeline to rebuild the data without it.</p>}
        {message && (
          <p role="status" className="notice">
            {message}
          </p>
        )}
        <QueryStatus query={files} empty={files.data?.length === 0 ? "No files yet." : undefined} />
        {files.data && files.data.length > 0 && (
          <table className="files">
            <thead>
              <tr>
                <th scope="col">Name</th>
                <th scope="col" className="num">
                  Size
                </th>
                <th scope="col">Modified</th>
                <th scope="col">
                  <span className="visually-hidden">Actions</span>
                </th>
              </tr>
            </thead>
            <tbody>
              {files.data.map((f) => (
                <tr key={f.name}>
                  <td data-label="Name">{f.name}</td>
                  <td data-label="Size" className="num">
                    {formatBytes(f.size)}
                  </td>
                  <td data-label="Modified">{formatUnix(f.modified)}</td>
                  <td className="actions">
                    {deleting === f.name ? (
                      <span className="confirm" role="group" aria-label="Confirm delete">
                        <span className="small">Delete this file?</span>
                        <button type="button" className="danger" disabled={del.isPending} onClick={() => del.mutate(f.name)}>
                          Delete
                        </button>
                        <button type="button" onClick={() => setDeleting(null)}>
                          Keep
                        </button>
                      </span>
                    ) : (
                      <button type="button" onClick={() => setDeleting(f.name)} aria-label={`Delete ${f.name}`}>
                        Delete
                      </button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>

      <section aria-labelledby="h-accounts">
        <div className="section-head">
          <h2 id="h-accounts">Linked accounts</h2>
          {meta?.plaid_configured && (
            <button type="button" disabled={busy || (accounts.data?.length ?? 0) === 0} onClick={() => plaid.mutate()}>
              {plaid.isPending ? "Refreshing from Plaid…" : "Refresh from Plaid"}
            </button>
          )}
        </div>
        <QueryStatus query={accounts} empty={accounts.data?.length === 0 ? "No linked accounts." : undefined} />
        {accounts.data && accounts.data.length > 0 && (
          <ul className="rule-list">
            {accounts.data.map((a) => (
              <li key={a.alias}>
                <strong>{a.alias}</strong> {a.institution && <span className="muted">{a.institution}</span>}
                {a.start_date && <span className="muted small"> · pulls from {a.start_date}</span>}
              </li>
            ))}
          </ul>
        )}
        {!meta?.plaid_configured && (accounts.data?.length ?? 0) > 0 && (
          <p className="muted small">Plaid refresh is unavailable: the Plaid keys aren't configured for this server.</p>
        )}
        {pull && (
          <ul className="results" role="status">
            {pull.accounts.map((a) => (
              <li key={a.alias} className={"error" in a ? "error" : ""}>
                {a.alias}: {"error" in a ? a.error : `${a.pulled} transactions pulled`}
              </li>
            ))}
          </ul>
        )}
        <p className="muted small">Run pipeline rebuilds from the files above; “Save and apply” on the Rules tab only re-categorizes.</p>
      </section>
    </div>
  );
}
