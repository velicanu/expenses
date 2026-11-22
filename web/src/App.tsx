import { useState } from "react";
import { clearError, useBanner } from "./banner";
import { Dashboard } from "./components/Dashboard";
import { DataView } from "./components/DataView";
import { FilterBar } from "./components/FilterBar";
import { RulesView } from "./components/RulesView";
import { Transactions } from "./components/Transactions";
import { useFilters } from "./filters";
import { useMe, useMeta } from "./hooks";

const TABS = ["Dashboard", "Transactions", "Rules", "Data"] as const;
type Tab = (typeof TABS)[number];

export function App() {
  const [tab, setTab] = useState<Tab>("Dashboard");
  const [filters, patch, reset] = useFilters();
  const me = useMe();
  const meta = useMeta();
  const banner = useBanner();
  const filtered = tab === "Dashboard" || tab === "Transactions";

  return (
    <>
      <header className="top">
        <h1>Expenses</h1>
        <nav aria-label="Sections">
          <ul className="tabs">
            {TABS.map((t) => (
              <li key={t}>
                <button type="button" aria-current={tab === t ? "page" : undefined} onClick={() => setTab(t)}>
                  {t}
                </button>
              </li>
            ))}
          </ul>
        </nav>
        <span className="who muted">{me.data?.user}</span>
      </header>
      {banner && (
        <div className="banner" role="alert">
          <span>{banner}</span>
          <button type="button" onClick={clearError} aria-label="Dismiss message">
            ×
          </button>
        </div>
      )}
      <main>
        {filtered && <FilterBar filters={filters} meta={meta.data} onChange={patch} onReset={reset} />}
        {meta.isError && (
          <p className="error" role="alert">
            Couldn't load the data summary: {meta.error.message}
          </p>
        )}
        {meta.data?.count === 0 && filtered && (
          <p className="notice">
            There is no data yet. Upload a CSV export in the <button type="button" className="link" onClick={() => setTab("Data")}>Data</button> tab.
          </p>
        )}
        {tab === "Dashboard" && <Dashboard filters={filters} meta={meta.data} />}
        {tab === "Transactions" && <Transactions filters={filters} meta={meta.data} />}
        {tab === "Rules" && <RulesView meta={meta.data} />}
        {tab === "Data" && <DataView meta={meta.data} />}
      </main>
    </>
  );
}
