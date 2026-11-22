import { describe, expect, it } from "vitest";
import {
  changedRows,
  defaultRange,
  deleteState,
  initialFilters,
  newRowState,
  onlyValid,
  plainNumber,
  pyTitle,
  rowRecords,
  saveCategoryState,
  saveRuleState,
  savedFilters,
  setEdit,
  targetCategories,
  withCategory,
  withRule,
  withoutSelections,
} from "./model";
import type { AppState, Rules } from "./types";

const data = { min_date: "2019-01-01", max_date: "2026-09-09" };
const state = (over: Partial<AppState> = {}): AppState => ({
  min_date: "2026-01-01",
  max_date: "2026-06-26",
  categories_in: [],
  categories_not_in: ["Transfer", "Taxes", "Income", "Payment", "Gone"],
  show_sql: true,
  rules_button: true,
  ...over,
});

describe("the date range default (old add_date_range_widget)", () => {
  it("uses the saved range when it is inside the data", () => {
    expect(defaultRange(state(), data)).toEqual({ start: "2026-01-01", end: "2026-06-26" });
  });
  it("clips the saved range to the data: max of the mins, min of the maxes", () => {
    expect(defaultRange({ min_date: "2010-01-01", max_date: "2030-01-01" }, data)).toEqual({ start: "2019-01-01", end: "2026-09-09" });
  });
  it("is the whole data range when nothing is saved", () => {
    expect(defaultRange({ min_date: null, max_date: null }, data)).toEqual({ start: "2019-01-01", end: "2026-09-09" });
    expect(defaultRange({ min_date: "2026-03-01", max_date: null }, data)).toEqual({ start: "2026-03-01", end: "2026-09-09" });
  });
  it("falls back to the whole data range when the saved range is entirely outside it", () => {
    expect(defaultRange({ min_date: "2030-01-01", max_date: "2031-01-01" }, data)).toEqual({ start: "2019-01-01", end: "2026-09-09" });
  });
  it("has no range when there is no data", () => {
    expect(defaultRange(state(), { min_date: null, max_date: null })).toEqual({ start: null, end: null });
  });
});

describe("the initial filters", () => {
  it("drops saved categories that are no longer in the data", () => {
    const f = initialFilters(state(), { ...data, data_categories: ["Dining", "Payment", "Taxes", "Income", "Transfer"] });
    expect(f.category_not_in).toEqual(["Transfer", "Taxes", "Income", "Payment"]);
    expect(f).toMatchObject({ category_in: [], description: "", sources: [], start: "2026-01-01", end: "2026-06-26" });
  });
  it("onlyValid keeps order and drops the rest", () => expect(onlyValid(["b", "x", "a"], ["a", "b"])).toEqual(["b", "a"]));
  it("saves the four keys the old app saved", () => {
    const f = initialFilters(state(), { ...data, data_categories: ["Taxes"] });
    expect(savedFilters({ ...f, description: "x", sources: ["a.csv"] })).toEqual({
      min_date: "2026-01-01",
      max_date: "2026-06-26",
      categories_in: [],
      categories_not_in: ["Taxes"],
    });
  });
});

describe("pyTitle (python's str.title)", () => {
  it.each([
    ["maurice", "Maurice"],
    ["hello WORLD", "Hello World"],
    ["o'neil", "O'Neil"],
    ["abc1def", "Abc1Def"],
    ["", ""],
  ])("%s -> %s", (a, b) => expect(pyTitle(a)).toBe(b));
});

const rules = (): Rules => ({ description: { rei: "Shopping" }, category: { food: "Dining" }, new_categories: { Kids: "#47129c" } });

describe("the Rules panel", () => {
  it("Save rule needs exactly one rule", () => {
    expect(saveRuleState("", "")).toEqual({ disabled: true, help: "No rule specified" });
    expect(saveRuleState("a", "b")).toEqual({ disabled: true, help: "Specify only one rule" });
    expect(saveRuleState("a", "")).toEqual({ disabled: false, help: "" });
    expect(saveRuleState("", "b")).toEqual({ disabled: false, help: "" });
  });
  it("Save category and Delete selections have their help texts", () => {
    expect(saveCategoryState("")).toEqual({ disabled: true, help: "No category specified" });
    expect(saveCategoryState("Pets").disabled).toBe(false);
    expect(deleteState(true)).toEqual({ disabled: true, help: "Nothing to delete" });
    expect(deleteState(false).disabled).toBe(false);
  });
  it("a description rule goes to description, a category rule to category; the input is not mutated", () => {
    const before = rules();
    const a = withRule(before, { categoryRule: "", descriptionRule: "uber", target: "Rideshare" });
    expect(a.description).toEqual({ rei: "Shopping", uber: "Rideshare" });
    expect(a.category).toEqual({ food: "Dining" });
    const b = withRule(before, { categoryRule: "gas", descriptionRule: "", target: "Car" });
    expect(b.category).toEqual({ food: "Dining", gas: "Car" });
    expect(before).toEqual(rules());
  });
  it("a new category is stripped and title-cased, with its color", () => {
    expect(withCategory(rules(), "  pet food ", "#ff0000").new_categories).toEqual({ Kids: "#47129c", "Pet Food": "#ff0000" });
  });
  it("Delete selections removes the chosen rules and categories", () => {
    const out = withoutSelections(rules(), { categoryRules: ["food"], descriptionRules: [], newCategories: ["Kids"] });
    expect(out).toEqual({ description: { rei: "Shopping" }, category: {}, new_categories: {} });
  });
  it("target categories are the data's plus the new ones, sorted and unique", () => {
    expect(targetCategories(["Rent", "Dining", "Kids"], rules())).toEqual(["Dining", "Kids", "Rent"]);
  });
});

describe("Save new row", () => {
  it("explains what is missing, like the old help text", () => {
    expect(newRowState("", 0)).toEqual({ disabled: true, help: "No description, amount is 0" });
    expect(newRowState("", 5)).toEqual({ disabled: true, help: "No description" });
    expect(newRowState("cash", 0)).toEqual({ disabled: true, help: "Amount is 0" });
    expect(newRowState("cash", -3)).toEqual({ disabled: false, help: "" });
  });
});

describe("the data editor", () => {
  const columns = ["date", "description", "amount", "category", "source", "source_file", "old_category", "pk", "line"];
  const rows = [
    ["2026-01-12 00:00:00", "DUANE READE", 9.994, "Groceries", "citi", "citi.csv", "", "citi.csv-1", 1],
    ["2026-02-06 00:00:00", "Points", -109.06, "Fees", "citi", "citi.csv", "", "citi.csv-2", 2],
  ];
  const records = rowRecords(columns, rows);

  it("shows dates as YYYY-MM-DD and amounts rounded to 2 decimals", () => {
    expect(records["citi.csv-1"]).toMatchObject({ date: "2026-01-12", amount: 9.99 });
  });
  it("keeps only real edits: setting a cell back removes the edit", () => {
    let edits = setEdit({}, records["citi.csv-1"], "citi.csv-1", "category", "Dining");
    expect(edits).toEqual({ "citi.csv-1": { category: "Dining" } });
    edits = setEdit(edits, records["citi.csv-1"], "citi.csv-1", "category", "Groceries");
    expect(edits).toEqual({});
  });
  it("reports changed rows with the whole row and a patch of only the changed fields", () => {
    let edits = setEdit({}, records["citi.csv-1"], "citi.csv-1", "category", "Dining");
    edits = setEdit(edits, records["citi.csv-1"], "citi.csv-1", "amount", 10);
    edits = setEdit(edits, records["citi.csv-2"], "citi.csv-2", "date", "2026-02-07");
    const changed = changedRows(records, edits);
    expect(changed.map((c) => [c.pk, c.patch])).toEqual([
      ["citi.csv-1", { category: "Dining", amount: 10 }],
      ["citi.csv-2", { date: "2026-02-07" }],
    ]);
    expect(changed[0].row).toMatchObject({ description: "DUANE READE", category: "Dining", amount: 10, pk: "citi.csv-1" });
  });
  it("ignores edits for rows that are no longer there", () => {
    expect(changedRows(records, { "gone-1": { category: "X" } })).toEqual([]);
  });
});

describe("plainNumber", () => {
  it.each([
    [5964.169999999, "5964.17"],
    [53.5, "53.5"],
    [42, "42"],
    [-109.06, "-109.06"],
  ])("%s -> %s", (n, s) => expect(plainNumber(n)).toBe(s));
});
