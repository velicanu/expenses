import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { api } from "../api";
import { showError } from "../banner";
import { useRefreshAll, useRules } from "../hooks";
import {
  deleteState,
  saveCategoryState,
  saveRuleState,
  targetCategories,
  withCategory,
  withRule,
  withoutSelections,
} from "../model";
import type { Rules } from "../types";
import { MultiSelect } from "./MultiSelect";

/** The old Rules panel (`add_rules`): four columns of widgets that edit the category and description rules. */
export function RulesPanel({ dataCategories }: { dataCategories: string[] }) {
  const rulesQuery = useRules();
  const client = useQueryClient();
  const refresh = useRefreshAll();

  const [deleteCategory, setDeleteCategory] = useState<string[]>([]);
  const [deleteDescription, setDeleteDescription] = useState<string[]>([]);
  const [deleteNew, setDeleteNew] = useState<string[]>([]);
  const [categoryRule, setCategoryRule] = useState("");
  const [descriptionRule, setDescriptionRule] = useState("");
  const [target, setTarget] = useState<string | null>(null);
  const [newCategory, setNewCategory] = useState("");
  const [color, setColor] = useState("#ffffff");
  const [listRules, setListRules] = useState(false);
  const [applied, setApplied] = useState<string | null>(null);

  const save = useMutation({
    mutationFn: (rules: Rules) => api.putRules(rules),
    onSuccess: (rules) => {
      client.setQueryData(["rules"], rules);
      void refresh(); // categories and colors changed: the charts and the lists refetch
    },
    onError: showError,
  });

  const apply = useMutation({
    mutationFn: () => api.runPipeline(true),
    onSuccess: (r) => {
      setApplied(r.ran ? `Rules applied (${r.count} transactions).` : "Nothing to apply yet: no card files were found.");
      void refresh();
    },
    onError: showError,
  });

  if (!rulesQuery.data) {
    return (
      <section aria-label="Rules" className="panel">
        <p className="muted">{rulesQuery.isError ? "Couldn't load the rules." : "Loading…"}</p>
      </section>
    );
  }
  const rules = rulesQuery.data;
  const targets = targetCategories(dataCategories, rules);
  const chosenTarget = target && targets.includes(target) ? target : (targets[0] ?? "");

  const saveRule = saveRuleState(categoryRule, descriptionRule);
  const saveCategory = saveCategoryState(newCategory);
  const nothingSelected = deleteCategory.length === 0 && deleteDescription.length === 0 && deleteNew.length === 0;
  const del = deleteState(nothingSelected);

  return (
    <section aria-label="Rules" className="panel">
      <div className="cols cols-4">
        <div className="col stack">
          <MultiSelect label="Delete category rule" options={Object.keys(rules.category)} value={deleteCategory} onChange={setDeleteCategory} />
          <MultiSelect
            label="Delete description rule"
            options={Object.keys(rules.description)}
            value={deleteDescription}
            onChange={setDeleteDescription}
          />
          <MultiSelect label="Delete new category" options={Object.keys(rules.new_categories)} value={deleteNew} onChange={setDeleteNew} />
        </div>

        <div className="col stack">
          <label className="field">
            <span className="label">Create category rule</span>
            <input type="text" value={categoryRule} onChange={(e) => setCategoryRule(e.target.value)} />
          </label>
          <label className="field">
            <span className="label">Create description rule</span>
            <input type="text" value={descriptionRule} onChange={(e) => setDescriptionRule(e.target.value)} />
          </label>
          <label className="field">
            <span className="label">Target category</span>
            <select value={chosenTarget} onChange={(e) => setTarget(e.target.value)}>
              {targets.map((c) => (
                <option key={c}>{c}</option>
              ))}
            </select>
          </label>
        </div>

        <div className="col stack">
          <label className="field">
            <span className="label">Create new category</span>
            <input type="text" value={newCategory} onChange={(e) => setNewCategory(e.target.value)} />
          </label>
          <label className="field">
            <span className="label">Pick A Color</span>
            <input type="color" value={color} onChange={(e) => setColor(e.target.value)} />
          </label>
        </div>

        <div className="col stack buttons">
          <button
            type="button"
            disabled={saveRule.disabled || save.isPending}
            title={saveRule.help}
            onClick={() => save.mutate(withRule(rules, { categoryRule, descriptionRule, target: chosenTarget }))}
          >
            Save rule
          </button>
          <button type="button" disabled={apply.isPending} onClick={() => apply.mutate()}>
            Apply rules
          </button>
          <button type="button" aria-pressed={listRules} onClick={() => setListRules((v) => !v)}>
            List rules
          </button>
          <button
            type="button"
            disabled={saveCategory.disabled || save.isPending}
            title={saveCategory.help}
            onClick={() => save.mutate(withCategory(rules, newCategory, color))}
          >
            Save category
          </button>
          <button
            type="button"
            disabled={del.disabled || save.isPending}
            title={del.help}
            onClick={() => {
              save.mutate(withoutSelections(rules, { categoryRules: deleteCategory, descriptionRules: deleteDescription, newCategories: deleteNew }));
              setDeleteCategory([]);
              setDeleteDescription([]);
              setDeleteNew([]);
            }}
          >
            Delete selections
          </button>
        </div>
      </div>
      {apply.isPending && <p className="spinner">Applying rules…</p>}
      {applied && !apply.isPending && (
        <p className="alert info" role="status">
          {applied}
        </p>
      )}
      {listRules && <pre className="json" aria-label="Rules as JSON">{JSON.stringify(rules, null, 2)}</pre>}
    </section>
  );
}
