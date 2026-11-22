import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState, type FormEvent } from "react";
import { api } from "../api";
import { showError } from "../banner";
import { titleCase } from "../format";
import { useRefreshData, useRules } from "../hooks";
import type { Meta, Rules } from "../types";
import { QueryStatus } from "./Status";

type RuleKind = "description" | "category";

export function RulesView({ meta }: { meta: Meta | undefined }) {
  const query = useRules();
  const client = useQueryClient();
  const refresh = useRefreshData();
  const [draft, setDraft] = useState<Rules | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  useEffect(() => {
    if (query.data && draft === null) setDraft(structuredClone(query.data));
  }, [query.data, draft]);

  const save = useMutation({
    mutationFn: async ({ rules, apply }: { rules: Rules; apply: boolean }) => {
      const saved = await api.putRules(rules);
      const pipeline = apply ? await api.runPipeline(true) : null;
      return { saved, pipeline };
    },
    onError: showError,
    onSuccess: async ({ saved, pipeline }) => {
      client.setQueryData(["rules"], saved);
      setDraft(structuredClone(saved));
      setNotice(
        pipeline
          ? pipeline.ran
            ? `Saved and applied: ${pipeline.count.toLocaleString("en-US")} transactions in ${pipeline.seconds}s.`
            : "Saved. Nothing to apply yet: upload a CSV in the Data tab."
          : "Saved. Use “Save and apply” to re-categorize existing transactions.",
      );
      await refresh();
    },
  });

  if (!draft) return <QueryStatus query={query} />;

  const dirty = JSON.stringify(draft) !== JSON.stringify(query.data);
  const targets = [...new Set([...(meta?.categories ?? []), ...Object.keys(draft.new_categories)])].sort();
  const edit = (next: Rules) => {
    setDraft(next);
    setNotice(null);
  };

  return (
    <div className="rules">
      <p className="muted">
        A rule moves matching transactions into a category. Description rules match text in the description; category rules match the
        category the bank gave. Neither is case-sensitive. Later rules win, and description rules win over category rules.
      </p>
      <RuleSection
        title="Description rules"
        kind="description"
        entries={draft.description}
        targets={targets}
        onChange={(description) => edit({ ...draft, description })}
      />
      <RuleSection
        title="Category rules"
        kind="category"
        entries={draft.category}
        targets={targets}
        onChange={(category) => edit({ ...draft, category })}
      />
      <NewCategories entries={draft.new_categories} onChange={(new_categories) => edit({ ...draft, new_categories })} />
      <div className="actions sticky">
        <button type="button" disabled={!dirty || save.isPending} onClick={() => save.mutate({ rules: draft, apply: false })}>
          Save
        </button>
        <button type="button" className="primary" disabled={save.isPending} onClick={() => save.mutate({ rules: draft, apply: true })}>
          {save.isPending ? "Working…" : "Save and apply"}
        </button>
        {dirty && <span className="muted small">Unsaved changes</span>}
      </div>
      {notice && (
        <p role="status" className="notice">
          {notice}
        </p>
      )}
    </div>
  );
}

function RuleSection({
  title,
  kind,
  entries,
  targets,
  onChange,
}: {
  title: string;
  kind: RuleKind;
  entries: Record<string, string>;
  targets: string[];
  onChange: (next: Record<string, string>) => void;
}) {
  const [text, setText] = useState("");
  const [target, setTarget] = useState("");
  const chosen = target || targets[0] || "";
  const submit = (e: FormEvent) => {
    e.preventDefault();
    if (!text.trim() || !chosen) return;
    onChange({ ...entries, [text.trim()]: chosen });
    setText("");
  };
  const names = Object.keys(entries);
  return (
    <section aria-labelledby={`h-${kind}`}>
      <h2 id={`h-${kind}`}>{title}</h2>
      {names.length === 0 && <p className="muted">None yet.</p>}
      <ul className="rule-list">
        {names.map((name) => (
          <li key={name}>
            <span className="rule-text">“{name}”</span> → <strong>{entries[name]}</strong>
            <button
              type="button"
              className="link"
              aria-label={`Delete ${kind} rule ${name}`}
              onClick={() => {
                const next = { ...entries };
                delete next[name];
                onChange(next);
              }}
            >
              Delete
            </button>
          </li>
        ))}
      </ul>
      <form className="inline-form" onSubmit={submit} aria-label={`Add ${kind} rule`}>
        <label className="grow">
          {kind === "description" ? "Description contains" : "Bank category contains"}
          <input value={text} maxLength={200} onChange={(e) => setText(e.target.value)} />
        </label>
        <label>
          Move to
          <select value={chosen} onChange={(e) => setTarget(e.target.value)}>
            {targets.map((t) => (
              <option key={t} value={t}>
                {t}
              </option>
            ))}
          </select>
        </label>
        <button type="submit" disabled={!text.trim() || !chosen}>
          Add {kind} rule
        </button>
      </form>
    </section>
  );
}

function NewCategories({ entries, onChange }: { entries: Record<string, string>; onChange: (next: Record<string, string>) => void }) {
  const [name, setName] = useState("");
  const [color, setColor] = useState("#4e79a7");
  const clean = titleCase(name);
  const submit = (e: FormEvent) => {
    e.preventDefault();
    if (!clean) return;
    onChange({ ...entries, [clean]: color });
    setName("");
  };
  return (
    <section aria-labelledby="h-newcat">
      <h2 id="h-newcat">New categories</h2>
      {Object.keys(entries).length === 0 && <p className="muted">None yet.</p>}
      <ul className="rule-list">
        {Object.entries(entries).map(([n, c]) => (
          <li key={n}>
            <span className="swatch" style={{ background: c }} aria-hidden="true" /> <strong>{n}</strong> <span className="muted small">{c}</span>
            <button
              type="button"
              className="link"
              aria-label={`Delete category ${n}`}
              onClick={() => {
                const next = { ...entries };
                delete next[n];
                onChange(next);
              }}
            >
              Delete
            </button>
          </li>
        ))}
      </ul>
      <form className="inline-form" onSubmit={submit} aria-label="Add category">
        <label className="grow">
          Category name
          <input value={name} maxLength={64} onChange={(e) => setName(e.target.value)} />
        </label>
        <label>
          Color
          <input type="color" value={color} onChange={(e) => setColor(e.target.value)} />
        </label>
        <button type="submit" disabled={!clean}>
          Add category
        </button>
      </form>
    </section>
  );
}
