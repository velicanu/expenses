import { friendly } from "../banner";
import { GROUPS, plainNumber } from "../model";
import type { FiguresResponse, Group } from "../types";
import { Plot } from "./Plot";

/**
 * The old charts section. The figures arrive ready-made from the server (the old Plotly Express code), so this
 * only places them: the category table beside the pie (3:10), the "Time bin" slider, the bar chart.
 */
export function Charts({
  figures,
  loading,
  error,
  dataCount,
  group,
  onGroup,
}: {
  figures: FiguresResponse | undefined;
  loading: boolean;
  error: unknown;
  dataCount: number;
  group: Group;
  onGroup: (g: Group) => void;
}) {
  if (dataCount === 0) return <p>Add some data and run the pipeline.</p>;
  if (error && !figures) {
    return (
      <p className="alert error" role="alert">
        {friendly(error)}
      </p>
    );
  }
  if (!figures) return loading ? <p className="muted">Loading…</p> : null;
  if (figures.rows === 0) {
    return (
      <p className="alert warning" role="status">
        Current selection is empty.
      </p>
    );
  }

  const { category, over_time: time } = figures;
  const index = Math.max(0, GROUPS.indexOf(group));

  return (
    <div className={loading ? "charts stale" : "charts"}>
      {category.message ? (
        <>
          <p>
            <strong>Spending by category</strong>
          </p>
          <p>{category.message}</p>
        </>
      ) : (
        <div className="cols cols-3-10">
          <div className="col">
            <table className="plain category-table" aria-label="Spending by category table">
              <thead>
                <tr>
                  <th>category</th>
                  <th className="num">amount</th>
                </tr>
              </thead>
              <tbody>
                {category.table.map((r) => (
                  <tr key={r.category}>
                    <td>{r.category}</td>
                    <td className="num">{plainNumber(r.amount)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="col">{category.figure && <Plot figure={category.figure} label="Spending by category" />}</div>
        </div>
      )}

      {time.message ? (
        <>
          <p>
            <strong>Spending over time</strong>
          </p>
          <p>{time.message}</p>
        </>
      ) : (
        <>
          <div className="slider">
            <label htmlFor="time-bin" className="label">
              Time bin
            </label>
            <span className="value" aria-hidden="true" style={{ left: `calc(${(index / (GROUPS.length - 1)) * 100}% + ${8 - (index / (GROUPS.length - 1)) * 16}px)` }}>
              {group}
            </span>
            <input
              id="time-bin"
              type="range"
              min={0}
              max={GROUPS.length - 1}
              step={1}
              value={index}
              aria-valuetext={GROUPS[index]}
              onChange={(e) => onGroup(GROUPS[Number(e.target.value)])}
            />
          </div>
          {time.figure && <Plot figure={time.figure} label="Spending over time" />}
        </>
      )}
    </div>
  );
}
