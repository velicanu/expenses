import { useMutation } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { api } from "../api";
import { friendly, showError } from "../banner";
import { useAccountStatus, useAccounts, useFiles, useRefreshAll, useRefreshStatus } from "../hooks";
import { ALIAS_RULE, beginLink, defaultStartDate, pipelineLine, pullOutcome, validAlias, type Outcome } from "../plaidLink";
import type { AccountStatus } from "../types";

const NOTICE_MS = 6000; // the old app cleared its messages after 2 seconds; these carry reasons, so a little longer
const NOT_CONFIGURED = "Plaid is not set up on the server (it cannot read its Plaid keys)";
const HELP_START_DATE =
  "Only pull transactions after this date. This is useful if you are combining manually uploaded CSVs with auto.";

/** The old "Inputs" section: linked cards, run the pipeline, refresh from Plaid, upload CSVs, delete raw files. */
export function InputsPanel({ plaidConfigured, oauthReady }: { plaidConfigured: boolean; oauthReady: boolean }) {
  const accounts = useAccounts();
  const status = useAccountStatus();
  const files = useFiles();
  const refresh = useRefreshAll();
  const refreshStatus = useRefreshStatus();

  const [message, setMessage] = useState<Outcome[]>([]);
  useEffect(() => {
    // plain confirmations fade, as in the old app; an error, or a Reconnect button, stays until the next action
    if (message.length === 0 || message.some((m) => m.kind === "error" || m.reconnect?.length || m.login?.length)) return;
    const t = setTimeout(() => setMessage([]), NOTICE_MS);
    return () => clearTimeout(t);
  }, [message]);

  // linking a bank / reconnecting one (Plaid Link opens over the page)
  const [linking, setLinking] = useState(false);
  const [formOpen, setFormOpen] = useState(false);
  const [alias, setAlias] = useState("");
  const [customStart, setCustomStart] = useState(false);
  const [startDate, setStartDate] = useState(() => defaultStartDate());
  const link = (request: { alias: string; startDate: string | null; reconnect: boolean }) => {
    setLinking(true);
    beginLink(request, (outcome) => {
      setLinking(false);
      if (outcome) {
        setMessage([outcome]);
        void refresh();
        refreshStatus();
      }
    }).catch((e) => {
      setLinking(false);
      setMessage([{ kind: "error", text: friendly(e) }]);
    });
  };
  const reconnect = (target: string) => link({ alias: target, startDate: null, reconnect: true });
  const linkDisabled = !plaidConfigured || linking;

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
      setMessage([pullOutcome(r)]);
      void refresh();
      refreshStatus();
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
              {!status.isError && <th>status</th>}
            </tr>
          </thead>
          <tbody>
            {accounts.data.map((a) => (
              <tr key={a.alias}>
                <td>{a.alias}</td>
                <td>{a.institution}</td>
                <td>{a.start_date}</td>
                {!status.isError && (
                  <td>
                    <StatusCell
                      status={status.data?.find((s) => s.alias === a.alias)}
                      checking={status.isPending}
                      disabled={linkDisabled}
                      title={plaidConfigured ? undefined : NOT_CONFIGURED}
                      onReconnect={() => reconnect(a.alias)}
                    />
                  </td>
                )}
              </tr>
            ))}
          </tbody>
        </table>
      ) : (
        <p className="muted">{accounts.isPending ? "Loading…" : "No linked accounts."}</p>
      )}
      {status.isError && accounts.data && accounts.data.length > 0 && (
        <p className="muted">The connection status is not available right now ({friendly(status.error)}).</p>
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
          <button
            type="button"
            disabled={linkDisabled}
            title={plaidConfigured ? undefined : NOT_CONFIGURED}
            aria-expanded={plaidConfigured ? formOpen : undefined}
            onClick={() => setFormOpen((open) => !open)}
          >
            Link account
          </button>
          {plaidConfigured && formOpen && (
            <div className="link-form">
              <label className="field">
                <span className="label">Account alias</span>
                <input type="text" value={alias} autoComplete="off" onChange={(e) => setAlias(e.target.value)} />
              </label>
              {alias === "" ? (
                <p className="muted">Alias required to add token</p>
              ) : !validAlias(alias) ? (
                <p className="alert error" role="alert">
                  {ALIAS_RULE}
                </p>
              ) : (
                <>
                  <button type="button" aria-pressed={customStart} onClick={() => setCustomStart((c) => !c)}>
                    Custom start date
                  </button>
                  {customStart && (
                    <label className="field">
                      <span className="label with-help">
                        Transaction start date
                        <span className="help" title={HELP_START_DATE} role="img" aria-label={HELP_START_DATE}>
                          ?
                        </span>
                      </span>
                      <input type="date" value={startDate} onChange={(e) => setStartDate(e.target.value)} />
                    </label>
                  )}
                  <button
                    type="button"
                    disabled={linking || (customStart && !startDate)}
                    onClick={() => link({ alias, startDate: customStart ? startDate : defaultStartDate(), reconnect: false })}
                  >
                    Connect bank
                  </button>
                </>
              )}
              {!oauthReady && (
                <p className="muted">
                  Banks that use OAuth (Capital One, Chase, Wealthfront) need a return address registered at Plaid.
                </p>
              )}
            </div>
          )}
          {linking && <p className="spinner">Waiting for Plaid Link…</p>}
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
          {(m.reconnect ?? []).map((target) => (
            <button
              key={target}
              type="button"
              className="inline"
              disabled={linkDisabled}
              title={`Reconnect ${target}`}
              onClick={() => reconnect(target)}
            >
              Reconnect
            </button>
          ))}
          {(m.login ?? []).map((target) => (
            <a key={target.alias} className="inline" href={target.url} target="_blank" rel="noopener noreferrer">
              Log in to {target.alias} by hand
            </a>
          ))}
        </p>
      ))}
    </section>
  );
}

/** One account's row in the Linked cards table: healthy, needs the bank login again, or some other problem. */
function StatusCell({
  status,
  checking,
  disabled,
  title,
  onReconnect,
}: {
  status: AccountStatus | undefined;
  checking: boolean;
  disabled: boolean;
  title: string | undefined;
  onReconnect: () => void;
}) {
  if (!status) return <span className="muted">{checking ? "Checking…" : "Unknown"}</span>;
  if (status.ok) {
    return (
      <span>
        OK{status.consent_expires ? <span className="muted"> (consent until {status.consent_expires.slice(0, 10)})</span> : null}
      </span>
    );
  }
  if (status.needs_reconnect) {
    return (
      <span>
        Needs reconnect{" "}
        <button type="button" className="inline" disabled={disabled} title={title} onClick={onReconnect}>
          Reconnect
        </button>
      </span>
    );
  }
  return <span>{status.error_code ?? "Unknown problem"}</span>;
}
