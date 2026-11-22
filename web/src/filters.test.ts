import { renderHook, act } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { DESCRIPTION_HELP, EMPTY_FILTERS, STORAGE_KEY, descriptionProblem, filtersToParams, loadFilters, saveFilters, useFilters } from "./filters";

describe("persistence", () => {
  it("round-trips through localStorage", () => {
    const f = { start: "2024-01-01", end: "", categoryIn: ["Dining"], categoryNotIn: ["Rent"], sources: ["a.csv"], q: "uber" };
    saveFilters(f);
    expect(loadFilters()).toEqual(f);
  });

  it("starts empty when nothing is stored or the value is garbage", () => {
    expect(loadFilters()).toEqual(EMPTY_FILTERS);
    for (const junk of ["not json", "null", "[1]", '"s"', '{"categoryIn": "Dining", "q": 5, "sources": [1, "a"]}']) {
      localStorage.setItem(STORAGE_KEY, junk);
      const f = loadFilters();
      expect(Array.isArray(f.categoryIn)).toBe(true);
      expect(typeof f.q).toBe("string");
    }
    expect(loadFilters().sources).toEqual(["a"]);
  });

  it("the hook saves every change and Reset clears it", () => {
    const { result } = renderHook(() => useFilters());
    act(() => result.current[1]({ q: "uber", categoryIn: ["Dining"] }));
    expect(JSON.parse(localStorage.getItem(STORAGE_KEY)!)).toMatchObject({ q: "uber", categoryIn: ["Dining"] });
    act(() => result.current[2]());
    expect(loadFilters()).toEqual(EMPTY_FILTERS);
  });

  it("a new session picks up the saved filters", () => {
    saveFilters({ ...EMPTY_FILTERS, q: "lyft" });
    const { result } = renderHook(() => useFilters());
    expect(result.current[0].q).toBe("lyft");
  });
});

describe("filtersToParams", () => {
  it("maps names to the API's and trims the description", () => {
    expect(filtersToParams({ ...EMPTY_FILTERS, categoryNotIn: ["Rent"], sources: ["x.csv"], q: "  a^b " })).toEqual({
      start: undefined,
      end: undefined,
      category_in: [],
      category_not_in: ["Rent"],
      source: ["x.csv"],
      q: "a^b",
    });
  });
});

describe("description help", () => {
  it("explains the syntax", () => {
    for (const bit of ["a+b", "a^b", "!a", "*"]) expect(DESCRIPTION_HELP).toContain(bit);
  });
  it("flags mixing + and ^ before the request is made", () => {
    expect(descriptionProblem("a+b^c")).toMatch(/not both/);
    expect(descriptionProblem("a+b")).toBeNull();
    expect(descriptionProblem("a^!b")).toBeNull();
  });
});
