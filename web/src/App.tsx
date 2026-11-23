import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useCallback, useEffect, useState } from "react";
import { api } from "./api";
import { clearError, friendly, showError, useBanner } from "./banner";
import { Charts } from "./components/Charts";
import { DataPanel } from "./components/DataPanel";
import { InputsPanel } from "./components/InputsPanel";
import { LoginReturn } from "./components/LoginReturn";
import { OAuthReturn } from "./components/OAuthReturn";
import { RulesPanel } from "./components/RulesPanel";
import { Sidebar } from "./components/Sidebar";
import { useAppState, useFigures, useMe, useMeta, useSqlDefault, useSqlRun } from "./hooks";
import { initialFilters, savedFilters } from "./model";
import { OAUTH_PATH, type Outcome } from "./plaidLink";
import type { AppState, Group, Meta, SqlFilters } from "./types";

export function App() {
  // Plaid sends the browser back to /plaid-oauth after a bank's OAuth login: finish the link there, then show the app
  const [returning, setReturning] = useState(() => window.location.pathname === OAUTH_PATH);
  // The hand-login page's Done sends the browser to /?refresh=<account>: fetch that account now, then show the app
  const [fetching, setFetching] = useState(() => new URLSearchParams(window.location.search).get("refresh"));
  const [notice, setNotice] = useState<Outcome | null>(null);
  const done = useCallback((outcome: Outcome | null) => {
    window.history.replaceState(null, "", "/"); // also drops ?refresh, so a reload does not fetch again
    if (outcome) setNotice(outcome);
    setReturning(false);
    setFetching(null);
  }, []);
  if (returning) return <OAuthReturn onDone={done} />;
  if (fetching) return <LoginReturn alias={fetching} onDone={done} />;
  return <Loaded notice={notice} onDismissNotice={() => setNotice(null)} />;
}

function Loaded({ notice, onDismissNotice }: { notice: Outcome | null; onDismissNotice: () => void }) {
  const meta = useMeta();
  const state = useAppState();
  if (meta.isError || state.isError) {
    return (
      <p className="alert error" role="alert">
        Couldn't load the app: {friendly(meta.error ?? state.error)}
      </p>
    );
  }
  if (!meta.data || !state.data) return <p className="muted loading">Loading…</p>;
  return <Page meta={meta.data} state={state.data} notice={notice} onDismissNotice={onDismissNotice} />;
}

function Page({
  meta,
  state,
  notice,
  onDismissNotice,
}: {
  meta: Meta;
  state: AppState;
  notice: Outcome | null;
  onDismissNotice: () => void;
}) {
  const client = useQueryClient();
  const me = useMe();
  const banner = useBanner();

  // The submitted filters start from what was saved last time (on any device), clipped to the data.
  const [filters, setFilters] = useState<SqlFilters>(() => initialFilters(state, meta));
  const [inputsOpen, setInputsOpen] = useState(false); // session only, like the old `expand`
  const [group, setGroup] = useState<Group>("auto");
  const [drawer, setDrawer] = useState(false);

  const saveState = useMutation({
    mutationFn: (patch: Partial<AppState>) => api.putState(patch),
    onMutate: (patch) => {
      const before = client.getQueryData<AppState>(["state"]);
      client.setQueryData<AppState>(["state"], (cur) => (cur ? { ...cur, ...patch } : cur));
      return { before };
    },
    onSuccess: (saved) => client.setQueryData(["state"], saved),
    onError: (e, _patch, ctx) => {
      if (ctx?.before) client.setQueryData(["state"], ctx.before);
      showError(e);
    },
  });

  // The query behind everything: the SQL the form builds, or what the user typed over it in "Show data".
  const sqlDefault = useSqlDefault(filters);
  const defaultQuery = sqlDefault.data?.query;
  const [typed, setTyped] = useState("");
  const [committed, setCommitted] = useState<string | undefined>(undefined);
  useEffect(() => {
    // like Streamlit's text_input: a new default, or the box being hidden and shown again, drops a hand edit
    setTyped(defaultQuery ?? "");
    setCommitted(defaultQuery);
  }, [defaultQuery, state.show_sql]);
  const query = (state.show_sql ? committed : undefined) ?? defaultQuery;

  const rows = useSqlRun(query, state.show_sql);
  const figures = useFigures(query, group);

  const submit = (next: SqlFilters) => {
    setFilters(next);
    setDrawer(false);
    saveState.mutate(savedFilters(next));
  };
  const runTyped = () => {
    if (typed !== committed) setCommitted(typed);
  };

  return (
    <div className={drawer ? "app drawer-open" : "app"}>
      <div className="topbar">
        <button type="button" aria-label="Open filters" aria-expanded={drawer} onClick={() => setDrawer((d) => !d)}>
          ☰
        </button>
        <span>Expense app</span>
      </div>
      <aside className="sidebar" aria-label="Sidebar">
        <Sidebar
          user={me.data?.user}
          meta={meta}
          filters={filters}
          warning={sqlDefault.data?.description_warning ?? null}
          inputsOpen={inputsOpen}
          rulesOpen={state.rules_button}
          sqlOpen={state.show_sql}
          onSubmit={submit}
          onToggleInputs={() => setInputsOpen((v) => !v)}
          onToggleRules={() => saveState.mutate({ rules_button: !state.rules_button })}
          onToggleSql={() => saveState.mutate({ show_sql: !state.show_sql })}
        />
      </aside>
      <div className="scrim" onClick={() => setDrawer(false)} />
      <main className="main">
        {notice && (
          <p className={`alert ${notice.kind} banner`} role={notice.kind === "error" ? "alert" : "status"}>
            <span>{notice.text}</span>
            {(notice.login ?? []).map((target) => (
              <a key={target.alias} className="inline" href={target.url} target="_blank" rel="noopener noreferrer">
                Log in to {target.alias} by hand
              </a>
            ))}
            <button type="button" onClick={onDismissNotice} aria-label="Dismiss message">
              ×
            </button>
          </p>
        )}
        {banner && (
          <div className="alert error banner" role="alert">
            <span>{banner}</span>
            <button type="button" onClick={clearError} aria-label="Dismiss message">
              ×
            </button>
          </div>
        )}
        {inputsOpen && <InputsPanel plaidConfigured={meta.plaid_configured} oauthReady={meta.plaid_oauth_ready} />}
        {state.rules_button && <RulesPanel dataCategories={meta.data_categories} />}
        {state.show_sql && (
          <DataPanel
            typed={typed}
            onTyped={setTyped}
            onRun={runTyped}
            error={rows.error ? friendly(rows.error) : null}
            result={rows.data}
            loading={rows.isPending}
            meta={meta}
          />
        )}
        <Charts
          figures={figures.data}
          loading={figures.isFetching}
          error={figures.error}
          dataCount={meta.count}
          group={group}
          onGroup={setGroup}
        />
      </main>
    </div>
  );
}
