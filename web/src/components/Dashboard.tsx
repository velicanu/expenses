import { useState } from "react";
import { Bar, CartesianGrid, ComposedChart, Cell, LabelList, Line, Pie, PieChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { barRows, colorFor, pieSlices, periodLabel, visibleTotal, type Slice } from "../charts";
import type { Filters } from "../filters";
import { formatMoney } from "../format";
import { useByCategory, useOverTime } from "../hooks";
import type { Bin, Meta } from "../types";
import { Legend } from "./Legend";
import { QueryStatus } from "./Status";

const BINS: Bin[] = ["auto", "year", "month", "week", "day"];

export function Dashboard({ filters, meta }: { filters: Filters; meta: Meta | undefined }) {
  const [bin, setBin] = useState<Bin>("auto");
  const [hidden, setHidden] = useState<ReadonlySet<string>>(new Set());
  const byCategory = useByCategory(filters);
  const overTime = useOverTime(filters, bin);
  const colors = meta?.colors ?? {};
  const toggle = (name: string) =>
    setHidden((h) => {
      const next = new Set(h);
      if (!next.delete(name)) next.add(name);
      return next;
    });

  const cat = byCategory.data;
  const time = overTime.data;
  const slices = cat ? pieSlices(cat, colors, hidden) : [];
  const legendItems = cat ? cat.categories.filter((c) => c.amount !== 0).map((c) => ({ name: c.category, signed: c.amount })) : [];
  const rows = time ? barRows(time, hidden) : [];

  return (
    <div className="dashboard">
      <section aria-labelledby="by-cat">
        <h2 id="by-cat">Spending by category</h2>
        <QueryStatus query={byCategory} />
        {cat && cat.categories.length === 0 && <p className="muted">No transactions match these filters.</p>}
        {cat && cat.categories.length > 0 && (
          <>
            <div className="chart pie" role="img" aria-label={`Spending by category, total ${formatMoney(cat.total)}`}>
              <ResponsiveContainer width="100%" height={300}>
                <PieChart>
                  <Pie data={slices} dataKey="value" nameKey="name" innerRadius="55%" outerRadius="90%" isAnimationActive={false}>
                    {slices.map((s) => (
                      <Cell key={s.name} fill={s.color} />
                    ))}
                  </Pie>
                  <Tooltip content={<SliceTip />} />
                </PieChart>
              </ResponsiveContainer>
              <div className="pie-total">
                <span className="muted small">Total</span>
                <strong>{formatMoney(visibleTotal(cat, hidden))}</strong>
              </div>
            </div>
            <Legend items={legendItems} colors={colors} hidden={hidden} onToggle={toggle} />
          </>
        )}
      </section>

      <section aria-labelledby="over-time">
        <div className="section-head">
          <h2 id="over-time">Over time</h2>
          <label>
            Time bin
            <select value={bin} onChange={(e) => setBin(e.target.value as Bin)}>
              {BINS.map((b) => (
                <option key={b} value={b}>
                  {b === "auto" && time ? `auto (${time.bin})` : b}
                </option>
              ))}
            </select>
          </label>
        </div>
        <QueryStatus query={overTime} />
        {time && time.periods.length === 0 && <p className="muted">No transactions match these filters.</p>}
        {time && time.periods.length > 0 && (
          <div className="chart bars" role="img" aria-label={`Spending per ${time.bin}, stacked by category`}>
            <ResponsiveContainer width="100%" height={340}>
              <ComposedChart data={rows} margin={{ top: 24, right: 8, bottom: 0, left: 0 }}>
                <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="var(--grid)" />
                <XAxis dataKey="period" tickFormatter={(p: string) => periodLabel(p, time.bin)} tick={{ fill: "var(--muted)", fontSize: 12 }} minTickGap={16} />
                <YAxis tickFormatter={(v: number) => compact(v)} tick={{ fill: "var(--muted)", fontSize: 12 }} width={56} />
                <Tooltip formatter={(v: number) => formatMoney(v)} labelFormatter={(p: string) => periodLabel(p, time.bin)} contentStyle={{ background: "var(--panel)", border: "1px solid var(--border)" }} />
                {time.categories
                  .filter((c) => !hidden.has(c))
                  .map((c) => (
                    <Bar key={c} dataKey={c} stackId="spend" fill={colorFor(c, colors)} isAnimationActive={false} />
                  ))}
                <Line dataKey="total" stroke="transparent" dot={false} activeDot={false} legendType="none" isAnimationActive={false}>
                  <LabelList dataKey="total" position="top" formatter={(v: number) => compact(v)} fill="var(--muted)" fontSize={11} />
                </Line>
              </ComposedChart>
            </ResponsiveContainer>
          </div>
        )}
        {time && time.categories.length > 0 && (
          <Legend items={time.categories.map((name) => ({ name }))} colors={colors} hidden={hidden} onToggle={toggle} />
        )}
      </section>
    </div>
  );
}

function SliceTip({ active, payload }: { active?: boolean; payload?: { payload: Slice }[] }) {
  if (!active || !payload?.length) return null;
  const s = payload[0].payload;
  return (
    <div className="tip">
      <strong>{s.name}</strong> {formatMoney(s.signed)}
    </div>
  );
}

function compact(v: number): string {
  const a = Math.abs(v);
  if (a >= 1_000_000) return `${(v / 1_000_000).toFixed(1)}M`;
  if (a >= 10_000) return `${Math.round(v / 1000)}k`;
  if (a >= 1000) return `${(v / 1000).toFixed(1)}k`;
  return String(Math.round(v));
}
