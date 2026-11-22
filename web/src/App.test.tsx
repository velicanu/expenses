import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { App } from "./App";
import { DEFAULT_QUERY, FIGURES, META, STATE, appRoutes, callsTo, jsonResponse, mockApi, renderWithClient } from "./test-utils";

afterEach(() => vi.unstubAllGlobals());

const open = async (over = {}) => {
  const calls = mockApi(appRoutes(over));
  renderWithClient(<App />);
  await screen.findByLabelText("Start date");
  return calls;
};

describe("the page starts where the old one did", () => {
  it("applies the saved range and exclusions, clipped to the data, and queries with them", async () => {
    const calls = await open();
    expect(screen.getByLabelText("Start date")).toHaveValue("2026-01-01");
    expect(screen.getByLabelText("End date")).toHaveValue("2026-06-26");
    const notIn = screen.getByRole("combobox", { name: "Categories not in" });
    ["Transfer", "Taxes", "Income", "Payment"].forEach((c) => expect(within(notIn).getByText(c)).toBeInTheDocument());
    expect(within(screen.getByRole("combobox", { name: "Categories in" })).getByText("Choose options")).toBeInTheDocument();

    await waitFor(() => expect(callsTo(calls, "POST /api/figures")).toHaveLength(1));
    expect(callsTo(calls, "POST /api/sql/default")[0].body).toEqual({
      start: "2026-01-01",
      end: "2026-06-26",
      category_in: [],
      category_not_in: ["Transfer", "Taxes", "Income", "Payment"],
      description: "",
      sources: [],
    });
    expect(callsTo(calls, "POST /api/figures")[0].body).toEqual({ query: expect.stringContaining(DEFAULT_QUERY), group: "auto" });
  });

  it("uses the whole data range when nothing was saved, and drops saved categories that left the data", async () => {
    const calls = await open({
      "GET /api/state": { ...STATE, min_date: null, max_date: null, categories_not_in: ["Transfer", "Vanished"] },
    });
    expect(screen.getByLabelText("Start date")).toHaveValue(META.min_date);
    expect(screen.getByLabelText("End date")).toHaveValue(META.max_date);
    await waitFor(() => expect(callsTo(calls, "POST /api/sql/default")).toHaveLength(1));
    expect(callsTo(calls, "POST /api/sql/default")[0].body).toMatchObject({ category_not_in: ["Transfer"] });
  });

  it("shows the old layout: no tabs, the form, then Inputs / Rules / Show data", async () => {
    await open();
    expect(screen.queryByRole("tab")).toBeNull();
    expect(screen.getByRole("form", { name: "Filters" })).toBeInTheDocument();
    ["Date range", "Categories in", "Categories not in", "Description", "Source file"].forEach((l) =>
      expect(screen.getAllByText(l).length).toBeGreaterThan(0),
    );
    expect(screen.getByRole("button", { name: "Submit" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Inputs" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Rules" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Show data" })).toBeInTheDocument();
    expect(screen.getByRole("img", { name: "^ is and, + is or, ! is not, * is wildcard" })).toHaveAttribute("title", "^ is and, + is or, ! is not, * is wildcard");
  });

  it("says who is logged in only while Inputs is open", async () => {
    await open();
    expect(screen.queryByText("dragos logged in")).toBeNull();
    await userEvent.click(screen.getByRole("button", { name: "Inputs" }));
    expect(screen.getByText("dragos logged in")).toBeInTheDocument();
  });
});

describe("the filter form applies only on Submit", () => {
  it("changes nothing until Submit, then queries and saves the four filter keys", async () => {
    const calls = await open();
    await waitFor(() => expect(callsTo(calls, "POST /api/figures")).toHaveLength(1));

    await userEvent.type(screen.getByLabelText("Description"), "uber+lyft");
    await userEvent.click(screen.getByRole("combobox", { name: "Categories in" }));
    await userEvent.click(await screen.findByRole("option", { name: "Rent" }));
    fireEvent.change(screen.getByLabelText("Start date"), { target: { value: "2026-02-01" } });
    // typed, picked and dated: but nothing has been sent
    expect(callsTo(calls, "POST /api/sql/default")).toHaveLength(1);
    expect(callsTo(calls, "PUT /api/state")).toHaveLength(0);

    await userEvent.click(screen.getByRole("button", { name: "Submit" }));
    await waitFor(() => expect(callsTo(calls, "POST /api/sql/default")).toHaveLength(2));
    expect(callsTo(calls, "POST /api/sql/default")[1].body).toEqual({
      start: "2026-02-01",
      end: "2026-06-26",
      category_in: ["Rent"],
      category_not_in: ["Transfer", "Taxes", "Income", "Payment"],
      description: "uber+lyft",
      sources: [],
    });
    expect(callsTo(calls, "PUT /api/state")[0].body).toEqual({
      min_date: "2026-02-01",
      max_date: "2026-06-26",
      categories_in: ["Rent"],
      categories_not_in: ["Transfer", "Taxes", "Income", "Payment"],
    });
    // the charts follow the new default query
    await waitFor(() =>
      expect(callsTo(calls, "POST /api/figures").some((c) => (c.body as { query: string }).query.includes("uber+lyft"))).toBe(true),
    );
  });

  it("submits with Enter in the description box", async () => {
    const calls = await open();
    await userEvent.type(screen.getByLabelText("Description"), "rei{Enter}");
    await waitFor(() => expect(callsTo(calls, "POST /api/sql/default")).toHaveLength(2));
  });

  it("shows the old warning about the description in the sidebar", async () => {
    await open({
      "POST /api/sql/default": {
        query: DEFAULT_QUERY,
        description_warning: "invalid description, only one of + or ^ supported at a time",
      },
    });
    expect(await screen.findByText("invalid description, only one of + or ^ supported at a time")).toBeInTheDocument();
  });

  it("keeps the end date after the start date", async () => {
    await open();
    expect(screen.getByLabelText("Start date")).toHaveAttribute("max", "2026-06-26");
    expect(screen.getByLabelText("End date")).toHaveAttribute("min", "2026-01-01");
  });
});

describe("Rules and Show data buttons", () => {
  it("toggle the panels and save the flag server-side", async () => {
    const calls = await open();
    expect(screen.queryByRole("region", { name: "Rules" })).toBeNull();
    await userEvent.click(screen.getByRole("button", { name: "Rules" }));
    expect(await screen.findByRole("region", { name: "Rules" })).toBeInTheDocument();
    expect(callsTo(calls, "PUT /api/state")[0].body).toEqual({ rules_button: true });

    await userEvent.click(screen.getByRole("button", { name: "Show data" }));
    expect(await screen.findByRole("region", { name: "Data" })).toBeInTheDocument();
    expect(callsTo(calls, "PUT /api/state")[1].body).toEqual({ show_sql: true });
  });

  it("starts with the panels the server says were open", async () => {
    await open({ "GET /api/state": { ...STATE, rules_button: true, show_sql: true } });
    expect(await screen.findByRole("region", { name: "Rules" })).toBeInTheDocument();
    expect(await screen.findByRole("region", { name: "Data" })).toBeInTheDocument();
  });
});

describe("the SQL box", () => {
  const withSql = { "GET /api/state": { ...STATE, show_sql: true } };

  it("shows the default query and reruns only on Enter or on leaving the box", async () => {
    const calls = await open(withSql);
    const box = await screen.findByLabelText("Input sql");
    await waitFor(() => expect(box).toHaveValue(`${DEFAULT_QUERY} /*  */`));
    await waitFor(() => expect(callsTo(calls, "POST /api/figures")).toHaveLength(1));

    await userEvent.type(box, " LIMIT 5");
    expect(callsTo(calls, "POST /api/figures")).toHaveLength(1); // typing is not running

    await userEvent.type(box, "{Enter}");
    await waitFor(() => expect(callsTo(calls, "POST /api/figures")).toHaveLength(2));
    expect(callsTo(calls, "POST /api/figures")[1].body).toEqual({ query: `${DEFAULT_QUERY} /*  */ LIMIT 5`, group: "auto" });
    expect(callsTo(calls, "POST /api/sql/run").at(-1)?.body).toEqual({ query: `${DEFAULT_QUERY} /*  */ LIMIT 5` });

    await userEvent.type(box, " OFFSET 1");
    await userEvent.tab(); // leaving the box runs it too
    await waitFor(() => expect(callsTo(calls, "POST /api/figures")).toHaveLength(3));
    expect((callsTo(calls, "POST /api/figures")[2].body as { query: string }).query.endsWith("LIMIT 5 OFFSET 1")).toBe(true);
  });

  it("does not rerun when nothing changed", async () => {
    const calls = await open(withSql);
    const box = await screen.findByLabelText("Input sql");
    await waitFor(() => expect(callsTo(calls, "POST /api/figures")).toHaveLength(1));
    await userEvent.click(box);
    await userEvent.tab();
    await userEvent.type(box, "{Enter}");
    expect(callsTo(calls, "POST /api/figures")).toHaveLength(1);
  });

  it("a new default (after Submit) drops a hand edit, like Streamlit's text_input", async () => {
    await open(withSql);
    const box = await screen.findByLabelText("Input sql");
    await waitFor(() => expect(box).toHaveValue(`${DEFAULT_QUERY} /*  */`));
    await userEvent.type(box, " LIMIT 5{Enter}");
    await userEvent.type(screen.getByLabelText("Description"), "rei");
    await userEvent.click(screen.getByRole("button", { name: "Submit" }));
    await waitFor(() => expect(box).toHaveValue(`${DEFAULT_QUERY} /* rei */`));
  });

  it("explains a bad query under the box", async () => {
    await open({
      ...withSql,
      "POST /api/sql/run": () => jsonResponse({ detail: 'near "SELEC": syntax error' }, 422),
    });
    expect(await screen.findByText('near "SELEC": syntax error')).toBeInTheDocument();
  });

  it("charts follow the default query when Show data is closed", async () => {
    const calls = await open();
    await waitFor(() => expect(callsTo(calls, "POST /api/figures")).toHaveLength(1));
    expect(callsTo(calls, "POST /api/sql/run")).toHaveLength(0); // the rows are only fetched while they are shown
  });
});

describe("the charts", () => {
  it("renders the category table beside the pie, and the bar chart, from the server's figures", async () => {
    await open();
    const table = await screen.findByRole("table", { name: "Spending by category table" });
    expect(within(table).getByText("5964.17")).toBeInTheDocument(); // streamlit's plain number, not 5,964.17
    expect(within(table).getByText("7.17")).toBeInTheDocument();
    expect(screen.getByRole("img", { name: "Spending by category" })).toBeInTheDocument();
    expect(screen.getByRole("img", { name: "Spending over time" })).toBeInTheDocument();
  });

  it("the Time bin slider offers auto, year, month, week, day and refetches the figures", async () => {
    const calls = await open();
    const slider = await screen.findByRole("slider", { name: "Time bin" });
    expect(slider).toHaveAttribute("aria-valuetext", "auto");
    // like Streamlit's select_slider: only the current value, above the thumb
    expect(screen.getByText("auto")).toBeInTheDocument();
    expect(slider).toHaveAttribute("min", "0");
    expect(slider).toHaveAttribute("max", "4"); // auto, year, month, week, day
    fireEvent.change(slider, { target: { value: "2" } });
    await waitFor(() => expect(callsTo(calls, "POST /api/figures").at(-1)?.body).toMatchObject({ group: "month" }));
    expect(screen.getByRole("slider", { name: "Time bin" })).toHaveAttribute("aria-valuetext", "month");
  });

  it("says so when the selection is empty", async () => {
    await open({ "POST /api/figures": { ...FIGURES, rows: 0 } });
    expect(await screen.findByText("Current selection is empty.")).toBeInTheDocument();
    expect(screen.queryByRole("slider")).toBeNull();
  });

  it("says so when there is no data at all", async () => {
    await open({ "GET /api/meta": { ...META, count: 0, min_date: null, max_date: null, data_categories: [], sources: [] } });
    expect(await screen.findByText("Add some data and run the pipeline.")).toBeInTheDocument();
  });

  it("prints the old message instead of a chart when the server has one", async () => {
    await open({
      "POST /api/figures": {
        ...FIGURES,
        category: { ...FIGURES.category, message: "Missing category or amount columns.", figure: null },
      },
    });
    expect(await screen.findByText("Missing category or amount columns.")).toBeInTheDocument();
    expect(screen.queryByRole("img", { name: "Spending by category" })).toBeNull();
  });

  it("explains a refused query where the charts would be", async () => {
    await open({ "POST /api/figures": () => jsonResponse({ detail: "no such column: nope" }, 422) });
    expect(await screen.findByText("no such column: nope")).toBeInTheDocument();
  });
});

describe("on a phone", () => {
  it("the sidebar is a drawer opened by the ☰ button, closed again by Submit", async () => {
    await open();
    const button = screen.getByRole("button", { name: "Open filters" });
    expect(button).toHaveAttribute("aria-expanded", "false");
    await userEvent.click(button);
    expect(button).toHaveAttribute("aria-expanded", "true");
    expect(document.querySelector(".app")).toHaveClass("drawer-open");
    await userEvent.click(screen.getByRole("button", { name: "Submit" }));
    expect(document.querySelector(".app")).not.toHaveClass("drawer-open");
  });
});

describe("loading and errors", () => {
  it("explains a failed start instead of showing a blank page", async () => {
    mockApi(appRoutes({ "GET /api/meta": () => jsonResponse({ detail: "boom" }, 500) }));
    renderWithClient(<App />);
    expect(await screen.findByText(/Couldn't load the app: boom/)).toBeInTheDocument();
  });
});
