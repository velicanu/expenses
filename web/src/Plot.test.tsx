import Plotly from "plotly.js-basic-dist-min";
import { render } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { PLOT_CONFIG, Plot } from "./components/Plot";
import { themedFigure } from "./streamlitTheme";

const figure = {
  data: [{ type: "pie", labels: ["Bills"], values: { dtype: "f8", bdata: "AAAAAAAA8D8=" }, marker: { colors: ["#FF6692"] } }],
  layout: { title: { text: "Spending by category, total: 1.00" }, height: 600, font: { size: 18, color: "#7f7f7f" } },
};

describe("Plot", () => {
  beforeEach(() => vi.clearAllMocks());

  it("hands Plotly the server's figure with Streamlit's theme applied, and the responsive config", () => {
    const { container } = render(<Plot figure={figure} label="Spending by category" />);
    const div = container.querySelector(".plot");
    const themed = themedFigure(figure, "light"); // jsdom has no dark preference
    expect(Plotly.react).toHaveBeenCalledTimes(1);
    expect(Plotly.react).toHaveBeenCalledWith(div, themed.data, themed.layout, { responsive: true, displaylogo: false });
    expect(themed.data).toEqual(figure.data); // nothing here has a placeholder: the data is the server's
    expect(themed.layout.title).toEqual({ ...figure.layout.title, text: `<b>${figure.layout.title.text}</b>` });
    expect(PLOT_CONFIG).toEqual({ responsive: true, displaylogo: false });
  });

  it("passes copies, so what Plotly writes into them never reaches the cached figure", () => {
    render(<Plot figure={figure} label="x" />);
    const [, data, layout] = vi.mocked(Plotly.react).mock.calls[0];
    expect(data).not.toBe(figure.data);
    expect(layout).not.toBe(figure.layout);
    expect(figure.layout).not.toHaveProperty("template");
  });

  it("draws again when the figure changes", () => {
    const { rerender } = render(<Plot figure={figure} label="x" />);
    const next = { ...figure, layout: { ...figure.layout, height: 700 } };
    rerender(<Plot figure={next} label="x" />);
    expect(Plotly.react).toHaveBeenCalledTimes(2);
    expect(vi.mocked(Plotly.react).mock.calls[1][2]).toEqual(themedFigure(next, "light").layout);
  });

  it("purges the chart on unmount", () => {
    const { container, unmount } = render(<Plot figure={figure} label="x" />);
    const div = container.querySelector(".plot");
    unmount();
    expect(Plotly.purge).toHaveBeenCalledWith(div);
  });

  it("is a labelled image for screen readers", () => {
    const { getByRole } = render(<Plot figure={figure} label="Spending by category" />);
    expect(getByRole("img", { name: "Spending by category" })).toBeInTheDocument();
  });
});
