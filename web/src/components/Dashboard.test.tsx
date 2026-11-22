import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { EMPTY_FILTERS } from "../filters";
import { jsonResponse, mockApi, renderWithClient } from "../test-utils";
import type { Meta } from "../types";
import { Dashboard } from "./Dashboard";
import { FilterBar } from "./FilterBar";

const meta: Meta = {
  min_date: "2024-01-01",
  max_date: "2024-03-31",
  count: 3,
  categories: ["Dining", "Rent"],
  sources: ["a.csv", "b.csv"],
  colors: { Dining: "#112233" },
  plaid_configured: false,
};
afterEach(() => vi.unstubAllGlobals());

describe("Dashboard", () => {
  it("shows the legend with signed amounts, and a click hides a category from the total", async () => {
    mockApi({
      "GET /api/summary/by-category": { total: -90, categories: [{ category: "Dining", amount: -120 }, { category: "Rent", amount: 30 }] },
      "GET /api/summary/over-time": { bin: "month", categories: ["Dining", "Rent"], periods: [{ period: "2024-01-01", total: -90, values: { Dining: -120, Rent: 30 } }] },
    });
    renderWithClient(<Dashboard filters={EMPTY_FILTERS} meta={meta} />);
    const dining = (await screen.findAllByRole("button", { name: /Dining/ }))[0];
    expect(dining).toHaveTextContent("-120.00");
    expect(dining).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByText("-90.00")).toBeInTheDocument(); // the donut's total

    await userEvent.click(dining);
    expect(dining).toHaveAttribute("aria-pressed", "false");
    expect(screen.getByText("30.00", { selector: "strong" })).toBeInTheDocument();
  });

  it("says so when nothing matches, and explains a refused filter", async () => {
    mockApi({
      "GET /api/summary/by-category": { total: 0, categories: [] },
      "GET /api/summary/over-time": () => jsonResponse({ detail: "unknown bin" }, 422),
    });
    renderWithClient(<Dashboard filters={EMPTY_FILTERS} meta={meta} />);
    expect(await screen.findByText("No transactions match these filters.")).toBeInTheDocument();
    expect(await screen.findByRole("alert")).toHaveTextContent("unknown bin");
  });
});

describe("FilterBar", () => {
  it("defaults the dates to the data's range, reports changes, and warns about + with ^", async () => {
    const onChange = vi.fn();
    const onReset = vi.fn();
    const { rerender } = renderWithClient(<FilterBar filters={EMPTY_FILTERS} meta={meta} onChange={onChange} onReset={onReset} />);
    expect(screen.getByLabelText("From")).toHaveValue("2024-01-01");
    expect(screen.getByLabelText("To")).toHaveValue("2024-03-31");
    expect(screen.getByText(/matches a or b/)).toBeInTheDocument();

    await userEvent.type(screen.getByLabelText("Description"), "x");
    expect(onChange).toHaveBeenCalledWith({ q: "x" });
    await userEvent.click(screen.getByText("Categories in", { selector: "summary" }));
    await userEvent.click(within(screen.getByRole("group", { name: "Categories in" })).getByLabelText("Rent"));
    expect(onChange).toHaveBeenCalledWith({ categoryIn: ["Rent"] });
    await userEvent.click(screen.getByRole("button", { name: "Reset" }));
    expect(onReset).toHaveBeenCalled();

    rerender(<FilterBar filters={{ ...EMPTY_FILTERS, q: "a+b^c" }} meta={meta} onChange={onChange} onReset={onReset} />);
    expect(screen.getByRole("alert")).toHaveTextContent("not both");
  });
});
