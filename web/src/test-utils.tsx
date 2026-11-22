import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render } from "@testing-library/react";
import type { ReactElement } from "react";
import { vi } from "vitest";

export function renderWithClient(ui: ReactElement) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false, staleTime: 0 }, mutations: { retry: false } } });
  return render(<QueryClientProvider client={client}>{ui}</QueryClientProvider>);
}

export const jsonResponse = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });

export interface Call {
  method: string;
  url: string; // path and query
  body: unknown; // parsed JSON, or the FormData
}

type Handler = (call: Call) => Response | Promise<Response>;

/**
 * Replaces fetch. `routes` maps "GET /api/files" (method + path, no query) to a handler; an unmatched
 * request fails the test loudly. Returns the list of calls made, in order.
 */
export function mockApi(routes: Record<string, Handler | unknown>): Call[] {
  const calls: Call[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: RequestInfo | URL, init: RequestInit = {}) => {
      const url = String(input);
      const method = (init.method ?? "GET").toUpperCase();
      const body = init.body instanceof FormData ? init.body : typeof init.body === "string" ? JSON.parse(init.body) : undefined;
      const call = { method, url, body };
      calls.push(call);
      const route = routes[`${method} ${url.split("?")[0]}`];
      if (route === undefined) throw new Error(`unexpected request: ${method} ${url}`);
      if (typeof route === "function") return (route as Handler)(call);
      return jsonResponse(route);
    }),
  );
  return calls;
}

// --- fixtures: a small version of the real thing (the old UI's default view on real data) -----------

export const META = {
  min_date: "2019-01-01",
  max_date: "2026-09-09",
  count: 11034,
  categories: ["Bills", "Dining", "Income", "Payment", "Rent", "Taxes", "Transfer", "Travel"],
  data_categories: ["Bills", "Dining", "Income", "Payment", "Rent", "Taxes", "Transfer"],
  sources: ["amex.csv", "citi.csv"],
  plaid_configured: false,
  plaid_oauth_ready: false,
};

export const STATE = {
  min_date: "2026-01-01",
  max_date: "2026-06-26",
  categories_in: [] as string[],
  categories_not_in: ["Transfer", "Taxes", "Income", "Payment"],
  show_sql: false,
  rules_button: false,
};

export const RULES = {
  description: { rei: "Shopping", uber: "Rideshare" },
  category: { food: "Dining" },
  new_categories: { Kids: "#47129c" },
};

export const FIGURES = {
  rows: 3,
  category: {
    message: null,
    total: 35174.28,
    table: [
      { category: "Bills", amount: 5964.169999999 },
      { category: "Dining", amount: 7.17 },
    ],
    figure: { data: [{ type: "pie", labels: ["Bills", "Dining"] }], layout: { title: { text: "Spending by category, total: 35174.28" }, height: 600 } },
  },
  over_time: {
    message: null,
    group: "auto",
    figure: { data: [{ type: "bar", name: "Bills" }], layout: { title: { text: "Monthly spending" } } },
  },
};

export const SQL_COLUMNS = ["date", "description", "amount", "category", "source", "source_file", "old_category", "pk", "line"];
export const SQL_RESULT = {
  columns: SQL_COLUMNS,
  rows: [
    ["2026-01-12 00:00:00", "DUANE READE", 9.994, "Dining", "citi", "citi.csv", "", "citi.csv-1", 1],
    ["2026-02-06 00:00:00", "Points Redeemed", -109.06, "Bills", "citi", "citi.csv", "", "citi.csv-2", 2],
  ],
  count: 2,
};

export const DEFAULT_QUERY = 'SELECT * FROM expenses WHERE date >= "2026-01-01"';

/** Every endpoint the page uses, answering like the real server; `over` replaces or adds routes. */
export function appRoutes(over: Record<string, Handler | unknown> = {}): Record<string, Handler | unknown> {
  // the saved state lives on the "server": GET returns it, PUT merges into it (as the real one does)
  const { "GET /api/state": initialState, ...rest } = over;
  let saved = { ...STATE, ...((initialState as object | undefined) ?? {}) };
  return {
    "GET /api/me": { user: "dragos", email: "d@example.com" },
    "GET /api/meta": META,
    "GET /api/state": () => jsonResponse(saved),
    "PUT /api/state": (c: Call) => {
      saved = { ...saved, ...(c.body as object) };
      return jsonResponse(saved);
    },
    "POST /api/sql/default": (c: Call) =>
      jsonResponse({ query: `${DEFAULT_QUERY} /* ${(c.body as { description: string }).description} */`, description_warning: null }),
    "POST /api/sql/run": SQL_RESULT,
    "POST /api/figures": FIGURES,
    "GET /api/rules": RULES,
    "PUT /api/rules": (c: Call) => jsonResponse(c.body),
    "GET /api/files": [{ name: "amex.csv", size: 10, modified: 0 }, { name: "citi.csv", size: 10, modified: 0 }],
    "GET /api/accounts": [],
    "POST /api/accounts/status": [],
    "POST /api/pipeline/run": { ran: true, seconds: 1.5, count: 11034 },
    "POST /api/accounts/pull": { accounts: [], pipeline: null },
    "POST /api/files": { saved: ["amex.csv: amex"], failed: [], pipeline: { ran: true, seconds: 1, count: 3 } },
    "DELETE /api/files/amex.csv": () => new Response(null, { status: 204 }),
    "PATCH /api/transactions/citi.csv-1": { pk: "citi.csv-1" },
    "POST /api/transactions": { pk: "input-0" },
    ...rest,
  };
}

/** Calls to one endpoint, in order. */
export const callsTo = (calls: Call[], route: string) => calls.filter((c) => `${c.method} ${c.url.split("?")[0]}` === route);
