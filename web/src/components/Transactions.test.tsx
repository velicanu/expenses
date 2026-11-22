import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { clearError } from "../banner";
import { EMPTY_FILTERS } from "../filters";
import { jsonResponse, mockApi, renderWithClient, type Call } from "../test-utils";
import type { Meta, Transaction, TransactionPage } from "../types";
import { PAGE_SIZE, Transactions } from "./Transactions";

const meta: Meta = {
  min_date: "2024-01-01",
  max_date: "2024-03-31",
  count: 2,
  categories: ["Dining", "Groceries", "Rent"],
  sources: ["chase.csv"],
  colors: {},
  plaid_configured: false,
};

const row = (over: Partial<Transaction>): Transaction => ({
  pk: "chase.csv-1",
  date: "2024-03-01",
  description: "COFFEE SHOP",
  amount: -4.5,
  category: "Dining",
  source: "chase",
  source_file: "chase.csv",
  edited: false,
  ...over,
});

const page = (rows: Transaction[], total = rows.length): TransactionPage => ({ total, sum: -1234.5, rows });
const two = page([row({}), row({ pk: "chase.csv-2", description: "GROCER", amount: 20, category: "Groceries", edited: true })]);

const listCalls = (calls: Call[]) => calls.filter((c) => c.method === "GET" && c.url.startsWith("/api/transactions"));

beforeEach(() => clearError());
afterEach(() => vi.unstubAllGlobals());

describe("Transactions", () => {
  it("renders rows with formatted amounts, the filtered sum, and an edited marker", async () => {
    mockApi({ "GET /api/transactions": two });
    renderWithClient(<Transactions filters={EMPTY_FILTERS} meta={meta} />);
    expect(await screen.findByText("COFFEE SHOP")).toBeInTheDocument();
    expect(screen.getByText("-4.50")).toBeInTheDocument();
    expect(screen.getByText("20.00")).toBeInTheDocument();
    expect(screen.getByText(/1–2 of 2/)).toBeInTheDocument();
    expect(screen.getByText("-1,234.50")).toBeInTheDocument();
    expect(screen.getAllByText("edited")).toHaveLength(1); // only the second row
  });

  it("asks the server for filters, sort and page", async () => {
    const calls = mockApi({ "GET /api/transactions": page([row({})], 250) });
    renderWithClient(<Transactions filters={{ ...EMPTY_FILTERS, categoryIn: ["Dining", "Rent"], q: "coffee" }} meta={meta} />);
    await screen.findByText("COFFEE SHOP");
    expect(listCalls(calls)[0].url).toBe(
      `/api/transactions?category_in=Dining&category_in=Rent&q=coffee&sort=date&order=desc&offset=0&limit=${PAGE_SIZE}`,
    );
    expect(screen.getByText(/1–100 of 250/)).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: "Next" }));
    await screen.findByText(/101–200 of 250/);
    expect(listCalls(calls).at(-1)!.url).toContain("offset=100");
  });

  it("sorts by a clicked header, then flips the direction", async () => {
    const calls = mockApi({ "GET /api/transactions": two });
    renderWithClient(<Transactions filters={EMPTY_FILTERS} meta={meta} />);
    await screen.findByText("COFFEE SHOP");

    await userEvent.click(screen.getByRole("button", { name: /^Amount/ }));
    await waitFor(() => expect(listCalls(calls).at(-1)!.url).toContain("sort=amount&order=desc"));
    expect(screen.getByRole("columnheader", { name: /Amount/ })).toHaveAttribute("aria-sort", "descending");

    await userEvent.click(screen.getByRole("button", { name: /^Amount/ }));
    await waitFor(() => expect(listCalls(calls).at(-1)!.url).toContain("sort=amount&order=asc"));

    await userEvent.click(screen.getByRole("button", { name: /^Category/ }));
    await waitFor(() => expect(listCalls(calls).at(-1)!.url).toContain("sort=category&order=asc"));
  });

  it("edits a row: sends only what changed, and closes on success", async () => {
    const calls = mockApi({ "GET /api/transactions": two, "PATCH /api/transactions/chase.csv-1": { pk: "chase.csv-1" } });
    renderWithClient(<Transactions filters={EMPTY_FILTERS} meta={meta} />);
    await userEvent.click(await screen.findByRole("button", { name: "Edit COFFEE SHOP" }));

    const amount = screen.getByLabelText("Amount");
    await userEvent.clear(amount);
    await userEvent.type(amount, "-5.25");
    await userEvent.selectOptions(screen.getByLabelText("Category"), "Groceries");
    await userEvent.click(screen.getByRole("button", { name: "Save" }));

    await waitFor(() => expect(calls.find((c) => c.method === "PATCH")).toBeDefined());
    expect(calls.find((c) => c.method === "PATCH")!.body).toEqual({ amount: -5.25, category: "Groceries" });
    await waitFor(() => expect(screen.queryByRole("button", { name: "Save" })).not.toBeInTheDocument());
  });

  it("keeps the editor open and shows the server's message when the edit is refused", async () => {
    mockApi({
      "GET /api/transactions": two,
      "PATCH /api/transactions/chase.csv-1": () => jsonResponse({ detail: "no such transaction" }, 404),
    });
    renderWithClient(<Transactions filters={EMPTY_FILTERS} meta={meta} />);
    await userEvent.click(await screen.findByRole("button", { name: "Edit COFFEE SHOP" }));
    await userEvent.clear(screen.getByLabelText("Description"));
    await userEvent.type(screen.getByLabelText("Description"), "COFFEE");
    await userEvent.click(screen.getByRole("button", { name: "Save" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("no such transaction");
    expect(screen.getByRole("button", { name: "Save" })).toBeInTheDocument();
  });

  it("does not call the API when nothing changed, and rejects a non-number", async () => {
    const calls = mockApi({ "GET /api/transactions": two });
    renderWithClient(<Transactions filters={EMPTY_FILTERS} meta={meta} />);
    await userEvent.click(await screen.findByRole("button", { name: "Edit COFFEE SHOP" }));
    await userEvent.click(screen.getByRole("button", { name: "Save" }));
    expect(calls.some((c) => c.method === "PATCH")).toBe(false);
    expect(screen.queryByRole("button", { name: "Save" })).not.toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: "Edit COFFEE SHOP" }));
    await userEvent.clear(screen.getByLabelText("Amount"));
    await userEvent.click(screen.getByRole("button", { name: "Save" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Amount must be a number");
  });

  it("deletes only after the confirm step", async () => {
    const calls = mockApi({ "GET /api/transactions": two, "DELETE /api/transactions/chase.csv-1": () => new Response(null, { status: 204 }) });
    renderWithClient(<Transactions filters={EMPTY_FILTERS} meta={meta} />);
    await userEvent.click(await screen.findByRole("button", { name: "Delete COFFEE SHOP" }));
    expect(screen.getByText("This removes it from the views.")).toBeInTheDocument();
    expect(calls.some((c) => c.method === "DELETE")).toBe(false);

    await userEvent.click(screen.getByRole("button", { name: "Keep" }));
    expect(calls.some((c) => c.method === "DELETE")).toBe(false);

    await userEvent.click(screen.getByRole("button", { name: "Delete COFFEE SHOP" }));
    await userEvent.click(screen.getByRole("button", { name: "Remove" }));
    await waitFor(() => expect(calls.some((c) => c.method === "DELETE" && c.url === "/api/transactions/chase.csv-1")).toBe(true));
  });

  it("adds a transaction, validating the amount first", async () => {
    const calls = mockApi({ "GET /api/transactions": two, "POST /api/transactions": () => jsonResponse({ pk: "input-0" }, 201) });
    renderWithClient(<Transactions filters={EMPTY_FILTERS} meta={meta} />);
    await userEvent.click(await screen.findByRole("button", { name: "Add transaction" }));
    const form = screen.getByRole("form", { name: "Add transaction" });
    await userEvent.type(within(form).getByLabelText("Description"), "cash");
    await userEvent.type(within(form).getByLabelText("Amount"), "0");
    await userEvent.click(within(form).getByRole("button", { name: "Add" }));
    expect(await within(form).findByRole("alert")).toHaveTextContent("other than 0");
    expect(calls.some((c) => c.method === "POST")).toBe(false);

    await userEvent.clear(within(form).getByLabelText("Amount"));
    await userEvent.type(within(form).getByLabelText("Amount"), "-12.5");
    await userEvent.click(within(form).getByRole("button", { name: "Add" }));
    await waitFor(() => expect(calls.find((c) => c.method === "POST")).toBeDefined());
    expect(calls.find((c) => c.method === "POST")!.body).toMatchObject({ description: "cash", amount: -12.5, category: "Dining" });
    expect(await within(form).findByRole("status")).toHaveTextContent("Added.");
  });

  it("explains a filter the API refuses, in place", async () => {
    mockApi({ "GET /api/transactions": () => jsonResponse({ detail: "use either + (or) or ^ (and)" }, 422) });
    renderWithClient(<Transactions filters={{ ...EMPTY_FILTERS, q: "a+b^c" }} meta={meta} />);
    expect(await screen.findByRole("alert")).toHaveTextContent("These filters can't be used: use either + (or) or ^ (and)");
  });
});
