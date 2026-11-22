import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { api } from "./api";
import { clearError, friendly, showError, useBanner } from "./banner";
import { Charts } from "./components/Charts";
import { DataPanel } from "./components/DataPanel";
import { InputsPanel } from "./components/InputsPanel";
import { RulesPanel } from "./components/RulesPanel";
import { Sidebar } from "./components/Sidebar";
import { useAppState, useFigures, useMe, useMeta, useSqlDefault, useSqlRun } from "./hooks";
import { initialFilters, savedFilters } from "./model";
import type { AppState, Group, Meta, SqlFilters } from "./types";

export function App() {
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
  return <Page meta={meta.data} state={state.data} />;
}

function Page({ meta, state }: { meta: Meta; state: AppState }) {
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
        {banner && (
          <div className="alert error banner" role="alert">
            <span>{banner}</span>
            <button type="button" onClick={clearError} aria-label="Dismiss message">
              ×
            </button>
          </div>
        )}
        {inputsOpen && <InputsPanel />}
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
