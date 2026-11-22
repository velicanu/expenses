import { describe, expect, it } from "vitest";
import { paletteFor, themedFigure } from "./streamlitTheme";

// what the server sends: Streamlit's template with placeholder colors, plus the old app's own colors
const figure = {
  data: [
    {
      type: "pie",
      labels: ["Bills", "Payment", "Mystery"],
      marker: { colors: ["#FF6692", "#000008", "#000007"] },
    },
    { type: "bar", marker: { color: "#000001" }, name: "ten", line: "#000010" },
  ],
  layout: {
    title: { text: "Spending by category, total: 1.00", x: 0.5, xanchor: "center" },
    font: { size: 18, color: "#7f7f7f" },
    height: 600,
    template: { layout: { colorway: ["#000001", "#000002"] } },
  },
};

describe("themedFigure (what Streamlit's browser code did to the old charts)", () => {
  it("swaps the placeholders for the theme's categorical colors, in light and dark", () => {
    const light = themedFigure(figure, "light");
    const dark = themedFigure(figure, "dark");
    const lp = paletteFor("light");
    const dp = paletteFor("dark");
    // #000007 is the 7th color, #000008 the 8th (Payment and Mystery, which have no color of their own)
    expect((light.data[0] as { marker: { colors: string[] } }).marker.colors).toEqual(["#FF6692", lp[7], lp[6]]);
    expect((dark.data[0] as { marker: { colors: string[] } }).marker.colors).toEqual(["#FF6692", dp[7], dp[6]]);
    expect((light.data[1] as { marker: { color: string }; line: string }).marker.color).toBe(lp[0]);
    expect((light.data[1] as { line: string }).line).toBe(lp[9]); // #000010 is the tenth, not "#00001" + "0"
  });

  it("the palettes are Streamlit's (captured from the old app), and dark reorders them", () => {
    expect(paletteFor("light").slice(0, 3)).toEqual(["#0068c9", "#83c9ff", "#ff2b2b"]);
    expect(paletteFor("dark").slice(0, 3)).toEqual(["#83c9ff", "#0068c9", "#ffabab"]);
    expect(paletteFor("light")).toHaveLength(10);
  });

  it("leaves the server's own colors alone (those the old app gave to categories explicitly)", () => {
    const out = themedFigure(figure, "light");
    expect((out.data[0] as { marker: { colors: string[] } }).marker.colors[0]).toBe("#FF6692");
  });

  it("keeps the figure's own layout and replaces only the template, with a theme-filled one", () => {
    const out = themedFigure(figure, "dark");
    expect(out.layout.title).toEqual({ ...figure.layout.title, text: `<b>${figure.layout.title.text}</b>` });
    expect(out.layout.font).toEqual(figure.layout.font);
    expect(out.layout.height).toBe(600);
    const layout = (out.layout.template as { layout: Record<string, unknown> }).layout;
    expect(layout.paper_bgcolor).toBe("#0e1117"); // Streamlit's dark background
    expect(themedFigure(figure, "light").layout.template).not.toEqual(out.layout.template);
    expect(JSON.stringify(out.layout.template)).not.toMatch(/#0000(0[1-9]|10)\b/); // no placeholder is left
  });

  it("sets the chart title in bold, once, as Streamlit's front-end did", () => {
    expect(themedFigure(figure, "light").layout.title).toEqual({ text: "<b>Spending by category, total: 1.00</b>", x: 0.5, xanchor: "center" });
    const already = { ...figure, layout: { ...figure.layout, title: { text: "<b>x</b>" } } };
    expect(themedFigure(already, "light").layout.title).toEqual({ text: "<b>x</b>" });
    const untitled = { data: [], layout: { height: 10 } };
    expect(themedFigure(untitled, "light").layout).not.toHaveProperty("title");
  });

  it("does not modify its input", () => {
    const before = JSON.stringify(figure);
    themedFigure(figure, "light");
    expect(JSON.stringify(figure)).toBe(before);
  });
});
