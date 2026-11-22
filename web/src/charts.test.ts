import { describe, expect, it } from "vitest";
import { FALLBACK_PALETTE, barRows, colorFor, periodLabel, pieSlices, visibleTotal } from "./charts";
import type { ByCategory, OverTime } from "./types";

const byCategory: ByCategory = {
  total: -90.5,
  categories: [
    { category: "Dining", amount: -120.25 },
    { category: "Refunds", amount: 40 },
    { category: "Zero", amount: 0 },
    { category: "Mystery", amount: -10.25 },
  ],
};

describe("colorFor", () => {
  it("prefers the API's color and otherwise picks a stable one from the palette", () => {
    expect(colorFor("Dining", { Dining: "#123456" })).toBe("#123456");
    const a = colorFor("Mystery", {});
    expect(FALLBACK_PALETTE).toContain(a);
    expect(colorFor("Mystery", {})).toBe(a);
  });
});

describe("pieSlices", () => {
  it("draws magnitudes, keeps the signed amount for labels, and drops zeros", () => {
    const slices = pieSlices(byCategory, { Dining: "#111111" });
    expect(slices.map((s) => [s.name, s.value, s.signed])).toEqual([
      ["Dining", 120.25, -120.25],
      ["Refunds", 40, 40],
      ["Mystery", 10.25, -10.25],
    ]);
    expect(slices[0].color).toBe("#111111");
    expect(FALLBACK_PALETTE).toContain(slices[1].color);
  });

  it("leaves out hidden categories, and the total follows", () => {
    const hidden = new Set(["Dining"]);
    expect(pieSlices(byCategory, {}, hidden).map((s) => s.name)).toEqual(["Refunds", "Mystery"]);
    expect(visibleTotal(byCategory, hidden)).toBe(29.75);
    expect(visibleTotal(byCategory)).toBe(-90.5);
  });
});

describe("barRows", () => {
  const data: OverTime = {
    bin: "month",
    categories: ["Dining", "Refunds"],
    periods: [
      { period: "2024-01-01", total: -80, values: { Dining: -120, Refunds: 40 } },
      { period: "2024-02-01", total: -5, values: { Dining: -5 } },
    ],
  };

  it("makes one row per period with every category present, and a total", () => {
    expect(barRows(data)).toEqual([
      { period: "2024-01-01", total: -80, Dining: -120, Refunds: 40 },
      { period: "2024-02-01", total: -5, Dining: -5, Refunds: 0 },
    ]);
  });

  it("recomputes the total without hidden categories", () => {
    expect(barRows(data, new Set(["Refunds"]))[0]).toEqual({ period: "2024-01-01", total: -120, Dining: -120 });
  });

  it("labels the axis by bin", () => {
    expect(periodLabel("2024-03-01", "year")).toBe("2024");
    expect(periodLabel("2024-03-01", "month")).toBe("2024-03");
    expect(periodLabel("2024-03-01", "week")).toBe("2024-03-01");
  });
});
