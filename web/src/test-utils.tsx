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
