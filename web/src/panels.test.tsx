import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { App } from "./App";
import { STATE, appRoutes, callsTo, jsonResponse, mockApi, renderWithClient } from "./test-utils";

afterEach(() => vi.unstubAllGlobals());

async function open(over: Record<string, unknown> = {}, state: Partial<typeof STATE> = {}) {
  const calls = mockApi(appRoutes({ "GET /api/state": { ...STATE, ...state }, ...over }));
  renderWithClient(<App />);
  await screen.findByLabelText("Start date");
  return calls;
}

describe("Inputs", () => {
  const inputs = async (over: Record<string, unknown> = {}) => {
    const calls = await open(over);
    await userEvent.click(screen.getByRole("button", { name: "Inputs" }));
    await screen.findByText("Linked cards:");
    return calls;
  };

  it("lists the linked cards without anything secret", async () => {
    await inputs({ "GET /api/accounts": [{ alias: "chase-1", institution: "Chase", start_date: "2026-01-01" }] });
    const table = within(screen.getByRole("region", { name: "Inputs" })).getByRole("table");
    expect(within(table).getByText("chase-1")).toBeInTheDocument();
    expect(within(table).getByText("Chase")).toBeInTheDocument();
    ["alias", "institution", "start_date"].forEach((h) => expect(within(table).getByText(h)).toBeInTheDocument());
  });

  it("says when nothing is linked", async () => {
    await inputs();
    expect(await screen.findByText("No linked accounts.")).toBeInTheDocument();
  });

  it("Run pipeline runs the whole pipeline and then reloads everything", async () => {
    const calls = await inputs();
    await userEvent.click(screen.getByRole("button", { name: "Run pipeline" }));
    expect(await screen.findByText("Pipeline ran in 1.5 s: 11034 transactions.")).toBeInTheDocument();
    expect(callsTo(calls, "POST /api/pipeline/run")[0].body).toEqual({ rules_only: false });
    await waitFor(() => expect(callsTo(calls, "GET /api/meta").length).toBeGreaterThan(1)); // the page reran
  });

  it("Refresh data pulls from Plaid and reports an account that failed", async () => {
    const calls = await inputs({
      "POST /api/accounts/pull": { accounts: [{ alias: "chase-1", error: "ITEM_LOGIN_REQUIRED: login again" }], pipeline: null },
    });
    await userEvent.click(screen.getByRole("button", { name: "Refresh data" }));
    expect(await screen.findByText(/chase-1: ITEM_LOGIN_REQUIRED: login again/)).toBeInTheDocument();
    expect(callsTo(calls, "POST /api/accounts/pull")).toHaveLength(1);
  });

  it("Refresh data pulls what it can and tells, without alarm, which account needs a hand login", async () => {
    await inputs({
      "POST /api/accounts/pull": {
        accounts: [
          { alias: "capital-one", pulled: 3 },
          {
            alias: "venmo-dragos",
            login_needed: "the saved login has probably expired (last seen logged in 3 h ago); log in by hand to fetch it",
            login_url: "https://fetch.velicanu.com/login?account=venmo-dragos",
          },
        ],
        pipeline: null,
      },
    });
    await userEvent.click(screen.getByRole("button", { name: "Refresh data" }));
    expect(await screen.findByText(/capital-one: 3 transactions/)).toBeInTheDocument();
    expect(screen.getByText(/venmo-dragos: the saved login has probably expired/)).toBeInTheDocument();
    const link = screen.getByRole("link", { name: "Log in to venmo-dragos by hand" });
    expect(link).toHaveAttribute("href", "https://fetch.velicanu.com/login?account=venmo-dragos");
    expect(link).toHaveAttribute("target", "_blank");
    expect(link).toHaveAttribute("rel", expect.stringContaining("noopener"));
    expect(screen.queryByRole("alert")).not.toBeInTheDocument(); // information, not a failure
    expect(screen.getByRole("status")).toBeInTheDocument();
  });

  it("Refresh data says when an account's saved login had lapsed and it logged itself in", async () => {
    await inputs({
      "POST /api/accounts/pull": { accounts: [{ alias: "wealthfront-dragos", pulled: 5, months: 2, auto_login: "ok" }], pipeline: null },
    });
    await userEvent.click(screen.getByRole("button", { name: "Refresh data" }));
    expect(await screen.findByText(/wealthfront-dragos: 5 transactions \(logged in automatically\)/)).toBeInTheDocument();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("an automatic login that did not get in is information with the hand-login link, not an alert", async () => {
    await inputs({
      "POST /api/accounts/pull": {
        accounts: [
          {
            alias: "wealthfront-dragos",
            login_needed: "the automatic login did not get in (Wealthfront is asking for a login, HTTP 200 at www.wealthfront.com/login); log in by hand to fetch it",
            login_url: "https://fetch.velicanu.com/login?account=wealthfront-dragos",
            auto_login: "failed",
          },
        ],
        pipeline: null,
      },
    });
    await userEvent.click(screen.getByRole("button", { name: "Refresh data" }));
    expect(await screen.findByText(/the automatic login did not get in/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Log in to wealthfront-dragos by hand" })).toHaveAttribute("href", "https://fetch.velicanu.com/login?account=wealthfront-dragos");
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("a login problem that comes with a real failure is still an alert, and still links", async () => {
    await inputs({
      "POST /api/accounts/pull": {
        accounts: [
          { alias: "chase-1", error: "ITEM_LOGIN_REQUIRED: login again" },
          { alias: "venmo-dragos", login_needed: "log in by hand to fetch it", login_url: "https://fetch.velicanu.com/login?account=venmo-dragos" },
        ],
        pipeline: null,
      },
    });
    await userEvent.click(screen.getByRole("button", { name: "Refresh data" }));
    expect(await screen.findByRole("alert")).toHaveTextContent(/chase-1: ITEM_LOGIN_REQUIRED/);
    expect(screen.getByRole("link", { name: "Log in to venmo-dragos by hand" })).toBeInTheDocument();
  });

  it("Refresh data reports an account left alone because it was just fetched, without calling it a failure", async () => {
    await inputs({
      "POST /api/accounts/pull": {
        accounts: [{ alias: "venmo-dragos", skipped: "fetched moments ago; it can be fetched again in about 8 min" }],
        pipeline: null,
      },
    });
    await userEvent.click(screen.getByRole("button", { name: "Refresh data" }));
    expect(await screen.findByText(/venmo-dragos: fetched moments ago; it can be fetched again in about 8 min/)).toBeInTheDocument();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: /by hand/ })).not.toBeInTheDocument();
  });

  it("a login-needed result without a link is shown, just without the link", async () => {
    await inputs({
      "POST /api/accounts/pull": { accounts: [{ alias: "venmo-dragos", login_needed: "log in by hand to fetch it", login_url: null }], pipeline: null },
    });
    await userEvent.click(screen.getByRole("button", { name: "Refresh data" }));
    expect(await screen.findByText(/venmo-dragos: log in by hand to fetch it/)).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: /by hand/ })).not.toBeInTheDocument();
  });

  it("the plain Refresh data button sends no account and no after_login", async () => {
    const calls = await inputs({ "POST /api/accounts/pull": { accounts: [], pipeline: null } });
    await userEvent.click(screen.getByRole("button", { name: "Refresh data" }));
    await screen.findByText(/No linked accounts to pull/);
    expect(callsTo(calls, "POST /api/accounts/pull")[0].body).toBeUndefined();
  });

  it("shows why Plaid is unavailable in the banner", async () => {
    await inputs({ "POST /api/accounts/pull": () => jsonResponse({ detail: "Plaid is unavailable: cannot read the Plaid keys" }, 503) });
    await userEvent.click(screen.getByRole("button", { name: "Refresh data" }));
    expect(await screen.findByText("Plaid is unavailable: cannot read the Plaid keys")).toBeInTheDocument();
  });

  it("Link account is disabled, with the reason, when the server has no Plaid keys", async () => {
    await inputs();
    const button = screen.getByRole("button", { name: "Link account" });
    expect(button).toBeDisabled();
    expect(button).toHaveAttribute("title", "Plaid is not set up on the server (it cannot read its Plaid keys)");
  });

  it("uploads the chosen CSVs as `files` and shows what was saved and what failed", async () => {
    const calls = await inputs({
      "POST /api/files": {
        saved: ["amex.csv: amex"],
        failed: ["notes.csv: not a layout of any known card"],
        pipeline: { ran: true, seconds: 1, count: 3 },
      },
    });
    const upload = screen.getByRole("button", { name: "Upload files" });
    expect(upload).toBeDisabled(); // nothing chosen yet
    const files = [new File(["a"], "amex.csv", { type: "text/csv" }), new File(["b"], "notes.csv", { type: "text/csv" })];
    await userEvent.upload(screen.getByLabelText("upload data"), files);
    await userEvent.click(upload);

    const form = (await waitFor(() => callsTo(calls, "POST /api/files")[0])).body as FormData;
    expect(form.getAll("files").map((f) => (f as File).name)).toEqual(["amex.csv", "notes.csv"]);
    expect(await screen.findByText("Saved: amex.csv: amex")).toBeInTheDocument();
    expect(screen.getByText("Failed: notes.csv: not a layout of any known card")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Upload files" })).toBeDisabled(); // the picker was cleared
  });

  it("deletes the ticked raw files after Confirm Delete, and says to run the pipeline", async () => {
    const calls = await inputs();
    expect(screen.queryByLabelText("Delete amex.csv")).toBeNull();
    await userEvent.click(screen.getByLabelText("Delete files"));
    expect(screen.queryByRole("button", { name: "Confirm Delete" })).toBeNull(); // nothing ticked
    await userEvent.click(await screen.findByLabelText("Delete amex.csv"));
    expect(screen.getByLabelText("Delete citi.csv")).not.toBeChecked();
    await userEvent.click(screen.getByRole("button", { name: "Confirm Delete" }));
    expect(await screen.findByText(/Deleted: amex.csv\. Run the pipeline/)).toBeInTheDocument();
    expect(callsTo(calls, "DELETE /api/files/amex.csv")).toHaveLength(1);
    expect(callsTo(calls, "DELETE /api/files/citi.csv")).toHaveLength(0);
  });
});

describe("Rules", () => {
  const rules = async (over: Record<string, unknown> = {}) => {
    const calls = await open(over, { rules_button: true });
    await screen.findByRole("region", { name: "Rules" });
    await screen.findByLabelText("Create category rule");
    return calls;
  };

  it("has the old widgets", async () => {
    await rules();
    ["Delete category rule", "Delete description rule", "Delete new category"].forEach((l) =>
      expect(screen.getByRole("combobox", { name: l })).toBeInTheDocument(),
    );
    ["Create category rule", "Create description rule", "Create new category", "Target category", "Pick A Color"].forEach((l) =>
      expect(screen.getByLabelText(l)).toBeInTheDocument(),
    );
    ["Save rule", "Apply rules", "List rules", "Save category", "Delete selections"].forEach((b) =>
      expect(screen.getByRole("button", { name: b })).toBeInTheDocument(),
    );
    expect(screen.getByLabelText("Pick A Color")).toHaveValue("#ffffff");
  });

  it("the target category lists the data's categories and the new ones, sorted", async () => {
    await rules();
    const options = within(screen.getByLabelText("Target category")).getAllByRole("option").map((o) => o.textContent);
    expect(options).toEqual(["Bills", "Dining", "Income", "Kids", "Payment", "Rent", "Taxes", "Transfer"]);
  });

  it("Save rule is disabled until exactly one rule is typed, with the old help texts", async () => {
    await rules();
    const save = screen.getByRole("button", { name: "Save rule" });
    expect(save).toBeDisabled();
    expect(save).toHaveAttribute("title", "No rule specified");
    await userEvent.type(screen.getByLabelText("Create description rule"), "lyft");
    expect(save).toBeEnabled();
    await userEvent.type(screen.getByLabelText("Create category rule"), "gas");
    expect(save).toBeDisabled();
    expect(save).toHaveAttribute("title", "Specify only one rule");
  });

  it("saves a description rule for the chosen target, keeping the other rules", async () => {
    const calls = await rules();
    await userEvent.type(screen.getByLabelText("Create description rule"), "lyft");
    await userEvent.selectOptions(screen.getByLabelText("Target category"), "Rent");
    await userEvent.click(screen.getByRole("button", { name: "Save rule" }));
    await waitFor(() => expect(callsTo(calls, "PUT /api/rules")).toHaveLength(1));
    expect(callsTo(calls, "PUT /api/rules")[0].body).toEqual({
      description: { rei: "Shopping", uber: "Rideshare", lyft: "Rent" },
      category: { food: "Dining" },
      new_categories: { Kids: "#47129c" },
    });
  });

  it("saves a category rule", async () => {
    const calls = await rules();
    await userEvent.type(screen.getByLabelText("Create category rule"), "gas");
    await userEvent.click(screen.getByRole("button", { name: "Save rule" }));
    await waitFor(() => expect(callsTo(calls, "PUT /api/rules")).toHaveLength(1));
    expect((callsTo(calls, "PUT /api/rules")[0].body as { category: object }).category).toEqual({ food: "Dining", gas: "Bills" });
  });

  it("Save category is disabled when empty, and saves a stripped, title-cased name with its color", async () => {
    const calls = await rules();
    const save = screen.getByRole("button", { name: "Save category" });
    expect(save).toBeDisabled();
    expect(save).toHaveAttribute("title", "No category specified");
    await userEvent.type(screen.getByLabelText("Create new category"), "  pet food ");
    fireEvent.change(screen.getByLabelText("Pick A Color"), { target: { value: "#ff0000" } });
    await userEvent.click(save);
    await waitFor(() => expect(callsTo(calls, "PUT /api/rules")).toHaveLength(1));
    expect((callsTo(calls, "PUT /api/rules")[0].body as { new_categories: object }).new_categories).toEqual({
      Kids: "#47129c",
      "Pet Food": "#ff0000",
    });
  });

  it("Delete selections is disabled until something is selected, then removes exactly that", async () => {
    const calls = await rules();
    const del = screen.getByRole("button", { name: "Delete selections" });
    expect(del).toBeDisabled();
    expect(del).toHaveAttribute("title", "Nothing to delete");
    await userEvent.click(screen.getByRole("combobox", { name: "Delete description rule" }));
    await userEvent.click(within(await screen.findByRole("listbox", { name: "Delete description rule" })).getByRole("option", { name: "uber" }));
    await userEvent.click(screen.getByRole("combobox", { name: "Delete new category" }));
    await userEvent.click(within(await screen.findByRole("listbox", { name: "Delete new category" })).getByRole("option", { name: "Kids" }));
    expect(del).toBeEnabled();
    await userEvent.click(del);
    await waitFor(() => expect(callsTo(calls, "PUT /api/rules")).toHaveLength(1));
    expect(callsTo(calls, "PUT /api/rules")[0].body).toEqual({
      description: { rei: "Shopping" },
      category: { food: "Dining" },
      new_categories: {},
    });
  });

  it("Apply rules reruns only the rules step; List rules toggles the JSON", async () => {
    const calls = await rules();
    await userEvent.click(screen.getByRole("button", { name: "Apply rules" }));
    expect(await screen.findByText("Rules applied (11034 transactions).")).toBeInTheDocument();
    expect(callsTo(calls, "POST /api/pipeline/run")[0].body).toEqual({ rules_only: true });

    expect(screen.queryByLabelText("Rules as JSON")).toBeNull();
    await userEvent.click(screen.getByRole("button", { name: "List rules" }));
    expect(screen.getByLabelText("Rules as JSON").textContent).toContain('"uber": "Rideshare"');
    await userEvent.click(screen.getByRole("button", { name: "List rules" }));
    expect(screen.queryByLabelText("Rules as JSON")).toBeNull();
  });

  it("shows the server's refusal, e.g. a bad color", async () => {
    await rules({ "PUT /api/rules": () => jsonResponse({ detail: "Hobbies: color must look like #1a2b3c" }, 422) });
    await userEvent.type(screen.getByLabelText("Create new category"), "hobbies");
    await userEvent.click(screen.getByRole("button", { name: "Save category" }));
    expect(await screen.findByText("Hobbies: color must look like #1a2b3c")).toBeInTheDocument();
  });
});

describe("Show data: the table", () => {
  const data = async (over: Record<string, unknown> = {}) => {
    const calls = await open(over, { show_sql: true });
    await screen.findByLabelText("category of citi.csv-1");
    return calls;
  };

  it("shows the query's rows with the old columns, dates and 2-decimal amounts", async () => {
    await data();
    const grid = screen.getByRole("region", { name: "Data" });
    ["date", "description", "amount", "category", "source", "source_file", "old_category", "pk", "line"].forEach((c) =>
      expect(within(grid).getByRole("columnheader", { name: c })).toBeInTheDocument(),
    );
    expect(screen.getByLabelText("date of citi.csv-1")).toHaveValue("2026-01-12");
    expect(screen.getByLabelText("amount of citi.csv-1")).toHaveValue(9.99);
    expect(screen.getByLabelText("description of citi.csv-1")).toHaveValue("DUANE READE");
    expect(screen.queryByLabelText("pk of citi.csv-1")).toBeNull(); // pk, source_file and line are read-only text
    expect(within(grid).getByText("citi.csv-1")).toBeInTheDocument();
  });

  it("an invalid date typed into a cell is not an edit", async () => {
    await data();
    const cell = screen.getByLabelText("date of citi.csv-2");
    await userEvent.clear(cell);
    await userEvent.type(cell, "2026-02-3");
    expect(screen.queryByText("Unsaved changes:")).toBeNull();
    await userEvent.type(cell, "0");
    expect(await screen.findByText("Unsaved changes:")).toBeInTheDocument();
  });

  it("the category cell is a select of the categories in the data", async () => {
    await data();
    const options = within(screen.getByLabelText("category of citi.csv-1")).getAllByRole("option").map((o) => o.textContent);
    expect(options).toEqual(["Bills", "Dining", "Income", "Payment", "Rent", "Taxes", "Transfer"]);
  });

  it("an edit shows under 'Unsaved changes:' and Save Changes patches only what changed", async () => {
    const calls = await data({ "PATCH /api/transactions/citi.csv-2": { pk: "citi.csv-2" } });
    expect(screen.queryByText("Unsaved changes:")).toBeNull();

    await userEvent.selectOptions(screen.getByLabelText("category of citi.csv-1"), "Rent");
    const amount = screen.getByLabelText("amount of citi.csv-1");
    await userEvent.clear(amount);
    await userEvent.type(amount, "12.5");
    fireEvent.change(screen.getByLabelText("date of citi.csv-2"), { target: { value: "2026-02-07" } });

    expect(await screen.findByText("Unsaved changes:")).toBeInTheDocument();
    const unsaved = screen.getByText("Unsaved changes:").parentElement as HTMLElement;
    expect(within(unsaved).getByText("Rent")).toBeInTheDocument();
    expect(within(unsaved).getByText("12.5")).toBeInTheDocument();
    expect(within(unsaved).getByText("2026-02-07")).toBeInTheDocument();
    expect(callsTo(calls, "PATCH /api/transactions/citi.csv-1")).toHaveLength(0); // nothing sent before Save

    await userEvent.click(screen.getByRole("button", { name: "Save Changes" }));
    await waitFor(() => expect(callsTo(calls, "PATCH /api/transactions/citi.csv-1")).toHaveLength(1));
    expect(callsTo(calls, "PATCH /api/transactions/citi.csv-1")[0].body).toEqual({ category: "Rent", amount: 12.5 });
    expect(callsTo(calls, "PATCH /api/transactions/citi.csv-2")[0].body).toEqual({ date: "2026-02-07" });
  });

  it("an edit put back to its original value is not a change", async () => {
    await data();
    await userEvent.selectOptions(screen.getByLabelText("category of citi.csv-1"), "Rent");
    expect(await screen.findByText("Unsaved changes:")).toBeInTheDocument();
    await userEvent.selectOptions(screen.getByLabelText("category of citi.csv-1"), "Dining");
    await waitFor(() => expect(screen.queryByText("Unsaved changes:")).toBeNull());
  });

  it("keeps the edits and shows the error when a save fails", async () => {
    await data({ "PATCH /api/transactions/citi.csv-1": () => jsonResponse({ detail: "no such transaction" }, 404) });
    await userEvent.selectOptions(screen.getByLabelText("category of citi.csv-1"), "Rent");
    await userEvent.click(await screen.findByRole("button", { name: "Save Changes" }));
    expect(await screen.findByText("no such transaction")).toBeInTheDocument();
  });

  it("renders only the rows in view when there are thousands", async () => {
    const rows = Array.from({ length: 5000 }, (_, i) => [`2026-01-01 00:00:00`, `row ${i}`, 1, "Dining", "citi", "citi.csv", "", `citi.csv-${i}`, i]);
    await open({ "POST /api/sql/run": { columns: ["date", "description", "amount", "category", "source", "source_file", "old_category", "pk", "line"], rows, count: 5000 } }, { show_sql: true });
    await screen.findByLabelText("description of citi.csv-0");
    expect(screen.getAllByLabelText(/^description of /).length).toBeLessThan(40);
  });
});

describe("Show data: add a new row", () => {
  const addRow = async (over: Record<string, unknown> = {}) => {
    const calls = await open(over, { show_sql: true });
    await screen.findByLabelText("category of citi.csv-1");
    return calls;
  };

  it("starts closed with '+', and '-' opens the form", async () => {
    await addRow();
    expect(screen.queryByText("Add a new row")).toBeNull();
    await userEvent.click(screen.getByRole("button", { name: "+" }));
    expect(screen.getByText("Add a new row")).toBeInTheDocument();
    ["Date", "Description", "Amount", "Category"].forEach((l) =>
      expect(within(screen.getByText("Add a new row").parentElement as HTMLElement).getByLabelText(l)).toBeInTheDocument(),
    );
    await userEvent.click(screen.getByRole("button", { name: "-" }));
    expect(screen.queryByText("Add a new row")).toBeNull();
  });

  it("Save new row needs a description and an amount, with the old help texts, then posts the row", async () => {
    const calls = await addRow();
    await userEvent.click(screen.getByRole("button", { name: "+" }));
    const form = screen.getByText("Add a new row").parentElement as HTMLElement;
    const save = within(form).getByRole("button", { name: "Save new row" });
    expect(save).toBeDisabled();
    expect(save).toHaveAttribute("title", "No description, amount is 0");
    await userEvent.type(within(form).getByLabelText("Description"), "cash");
    expect(save).toHaveAttribute("title", "Amount is 0");
    fireEvent.change(within(form).getByLabelText("Amount"), { target: { value: "-12.5" } });
    fireEvent.change(within(form).getByLabelText("Date"), { target: { value: "2026-03-04" } });
    await userEvent.selectOptions(within(form).getByLabelText("Category"), "Travel");
    expect(save).toBeEnabled();
    await userEvent.click(save);
    await waitFor(() => expect(callsTo(calls, "POST /api/transactions")).toHaveLength(1));
    expect(callsTo(calls, "POST /api/transactions")[0].body).toEqual({ date: "2026-03-04", description: "cash", amount: -12.5, category: "Travel" });
  });
});
