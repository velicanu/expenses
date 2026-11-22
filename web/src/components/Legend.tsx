import { colorFor } from "../charts";
import { formatMoney } from "../format";

interface Props {
  items: { name: string; signed?: number }[];
  colors: Record<string, string>;
  hidden: ReadonlySet<string>;
  onToggle: (name: string) => void;
}

/** Buttons rather than a chart-drawn legend, so it works from the keyboard and a touch screen. */
export function Legend({ items, colors, hidden, onToggle }: Props) {
  return (
    <ul className="legend">
      {items.map((item) => {
        const off = hidden.has(item.name);
        return (
          <li key={item.name}>
            <button type="button" aria-pressed={!off} onClick={() => onToggle(item.name)} className={off ? "off" : ""}>
              <span className="swatch" style={{ background: colorFor(item.name, colors) }} aria-hidden="true" />
              {item.name}
              {item.signed !== undefined && <span className="amount">{formatMoney(item.signed)}</span>}
            </button>
          </li>
        );
      })}
    </ul>
  );
}
