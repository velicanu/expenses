import themes from "./streamlitTheme.json";
import type { Figure } from "./types";

/**
 * What Streamlit's browser code did to every Plotly chart of the old app (st.plotly_chart's default
 * theme="streamlit"), so the charts look as they did.
 *
 * The server builds each figure with Streamlit's Plotly template, whose colors are placeholders:
 * #000001 .. #000010 stand for the theme's ten categorical colors. In the old app, Streamlit's frontend
 * replaced the figure's template with one filled in for the current light or dark theme (background, fonts, grid,
 * legend, hover label) and swapped the placeholders for the palette. That is why a category with no color of its
 * own got Streamlit's palette instead of Plotly's.
 *
 * streamlitTheme.json holds the two filled-in templates, captured from the old app running in a real browser
 * (Chrome, light and dark); the palette is the `colorway` inside them. The figure's own layout (title, fonts it
 * sets, sizes) still wins over the template, exactly as in Plotly.
 */
export type Scheme = "light" | "dark";

const PLACEHOLDER = /#0000(0[1-9]|10)\b/g;

export function colorScheme(): Scheme {
  const dark = typeof window !== "undefined" && typeof window.matchMedia === "function" && window.matchMedia("(prefers-color-scheme: dark)").matches;
  return dark ? "dark" : "light";
}

export function paletteFor(scheme: Scheme): string[] {
  return themes[scheme].layout.colorway;
}

/** Streamlit's front-end set every chart title in bold (the live old page had `<b>…</b>` around it). */
function boldTitle(layout: Record<string, unknown>): Record<string, unknown> {
  const title = layout.title as { text?: string } | undefined;
  if (!title?.text || title.text.startsWith("<b>")) return layout;
  return { ...layout, title: { ...title, text: `<b>${title.text}</b>` } };
}

/** A themed copy of `figure`; the input is not modified. */
export function themedFigure(figure: Figure, scheme: Scheme): Figure {
  const palette = paletteFor(scheme);
  const swap = (_: string, n: string) => palette[Number(n) - 1];
  const data = JSON.parse(JSON.stringify(figure.data).replace(PLACEHOLDER, swap)) as unknown[];
  const layout = boldTitle({ ...structuredClone(figure.layout), template: structuredClone(themes[scheme]) });
  return { data, layout };
}
