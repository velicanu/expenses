import Plotly from "plotly.js-basic-dist-min";
import { useEffect, useRef, useState } from "react";
import { colorScheme, themedFigure, type Scheme } from "../streamlitTheme";
import type { Figure } from "../types";

export const PLOT_CONFIG = { responsive: true, displaylogo: false };

/** The page's light or dark scheme, following the system setting (Streamlit did the same). */
function useColorScheme(): Scheme {
  const [scheme, setScheme] = useState<Scheme>(colorScheme);
  useEffect(() => {
    if (typeof window.matchMedia !== "function") return;
    const query = window.matchMedia("(prefers-color-scheme: dark)");
    const onChange = () => setScheme(colorScheme());
    query.addEventListener("change", onChange);
    return () => query.removeEventListener("change", onChange);
  }, []);
  return scheme;
}

/**
 * Draws a figure the server built with the old app's Plotly Express code. Nothing is recomputed or restyled
 * except what Streamlit's browser code did to every chart of the old app: the theme template and its palette
 * (see streamlitTheme.ts). Data and layout are copied because Plotly writes into what it is given.
 */
export function Plot({ figure, label }: { figure: Figure; label: string }) {
  const ref = useRef<HTMLDivElement>(null);
  const scheme = useColorScheme();

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const themed = themedFigure(figure, scheme);
    void Plotly.react(el, themed.data, themed.layout, PLOT_CONFIG);
  }, [figure, scheme]);

  useEffect(() => {
    const el = ref.current;
    return () => {
      if (el) Plotly.purge(el);
    };
  }, []);

  return <div ref={ref} className="plot" role="img" aria-label={label} />;
}
