import type { ByCategory, OverTime } from "./types";

// Used for categories the API has no color for. Chosen to stay readable on light and dark backgrounds.
export const FALLBACK_PALETTE = [
  "#4e79a7",
  "#f28e2b",
  "#59a14f",
  "#b07aa1",
  "#76b7b2",
  "#edc948",
  "#9c755f",
  "#ff9da7",
  "#8cd17d",
  "#86bcb6",
  "#d37295",
  "#a0cbe8",
];

/** The same category gets the same color everywhere: its API color, else a stable pick from the palette. */
export function colorFor(category: string, colors: Record<string, string>): string {
  if (colors[category]) return colors[category];
  let h = 0;
  for (let i = 0; i < category.length; i++) h = (h * 31 + category.charCodeAt(i)) >>> 0;
  return FALLBACK_PALETTE[h % FALLBACK_PALETTE.length];
}

export interface Slice {
  name: string;
  value: number; // magnitude, what the pie draws
  signed: number; // what the legend and tooltip show
  color: string;
}

/** A pie cannot draw negative areas: it draws |amount| and keeps the signed value for the labels. */
export function pieSlices(data: ByCategory, colors: Record<string, string>, hidden: ReadonlySet<string> = new Set()): Slice[] {
  return data.categories
    .filter((c) => c.amount !== 0 && !hidden.has(c.category))
    .map((c) => ({ name: c.category, value: Math.abs(c.amount), signed: c.amount, color: colorFor(c.category, colors) }))
    .sort((a, b) => b.value - a.value);
}

export function visibleTotal(data: ByCategory, hidden: ReadonlySet<string> = new Set()): number {
  const sum = data.categories.filter((c) => !hidden.has(c.category)).reduce((s, c) => s + c.amount, 0);
  return Math.round(sum * 100) / 100;
}

export type BarRow = { period: string; total: number } & Record<string, number | string>;

export function barRows(data: OverTime, hidden: ReadonlySet<string> = new Set()): BarRow[] {
  return data.periods.map((p) => {
    const row: BarRow = { period: p.period, total: 0 };
    let total = 0;
    for (const category of data.categories) {
      if (hidden.has(category)) continue;
      const v = p.values[category] ?? 0;
      row[category] = v;
      total += v;
    }
    row.total = Math.round(total * 100) / 100;
    return row;
  });
}

/** x-axis text for a period start: the year, the month, or the day, depending on the bin. */
export function periodLabel(period: string, bin: OverTime["bin"]): string {
  if (bin === "year") return period.slice(0, 4);
  if (bin === "month") return period.slice(0, 7);
  return period;
}
