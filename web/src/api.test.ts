import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError, api, detailMessage, hooks } from "./api";
import { jsonResponse, mockApi } from "./test-utils";

describe("detailMessage", () => {
  it("uses a string detail", () => expect(detailMessage({ detail: "no data yet" }, "x")).toBe("no data yet"));
  it("joins FastAPI validation errors, naming the field", () => {
    const body = { detail: [{ loc: ["body", "amount"], msg: "Input should be a valid number", type: "x" }, { loc: ["query", "limit"], msg: "too big" }] };
    expect(detailMessage(body, "x")).toBe("amount: Input should be a valid number; limit: too big");
  });
  it("falls back when there is nothing usable", () => {
    expect(detailMessage(null, "fallback")).toBe("fallback");
    expect(detailMessage({ detail: [] }, "fallback")).toBe("fallback");
  });
});

describe("endpoints", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("reads and patches the saved state", async () => {
    const state = { min_date: "2026-01-01", max_date: null, categories_in: [], categories_not_in: ["Transfer"], show_sql: true, rules_button: false };
    const calls = mockApi({ "GET /api/state": state, "PUT /api/state": state });
    expect(await api.state()).toEqual(state);
    await api.putState({ min_date: "2026-02-01", categories_not_in: ["Taxes"] });
    expect(calls[1]).toMatchObject({ method: "PUT", body: { min_date: "2026-02-01", categories_not_in: ["Taxes"] } });
    expect(vi.mocked(fetch).mock.calls[1][1]?.headers).toEqual({ "Content-Type": "application/json" });
  });

  it("posts the form's filters for the default SQL, and the query for run and figures", async () => {
    const calls = mockApi({
      "POST /api/sql/default": { query: "SELECT 1", description_warning: null },
      "POST /api/sql/run": { columns: ["a"], rows: [[1]], count: 1 },
      "POST /api/figures": { rows: 1, category: {}, over_time: {} },
    });
    const filters = { start: "2026-01-01", end: null, category_in: [], category_not_in: ["Taxes"], description: "uber+lyft", sources: ["a.csv"] };
    await api.sqlDefault(filters);
    await api.sqlRun("SELECT 1");
    await api.figures("SELECT 1", "month");
    expect(calls.map((c) => [c.method, c.url, c.body])).toEqual([
      ["POST", "/api/sql/default", filters],
      ["POST", "/api/sql/run", { query: "SELECT 1" }],
      ["POST", "/api/figures", { query: "SELECT 1", group: "month" }],
    ]);
  });

  it("patches a transaction by its (encoded) pk and posts a new one", async () => {
    const calls = mockApi({
      "PATCH /api/transactions/amex%20blue.csv-1%2F2": { pk: "x" },
      "POST /api/transactions": { pk: "input-0" },
    });
    await api.updateTransaction("amex blue.csv-1/2", { category: "Rent" });
    await api.addTransaction({ date: "2026-01-02", description: "cash", amount: -3, category: "Dining" });
    expect(calls[0].body).toEqual({ category: "Rent" });
    expect(calls[1].body).toEqual({ date: "2026-01-02", description: "cash", amount: -3, category: "Dining" });
  });

  it("runs the pipeline for rules only, or in full", async () => {
    const calls = mockApi({ "POST /api/pipeline/run": { ran: true, seconds: 1, count: 3 } });
    await api.runPipeline(true);
    await api.runPipeline();
    expect(calls.map((c) => c.body)).toEqual([{ rules_only: true }, { rules_only: false }]);
  });

  it("sends the upload as multipart with the field name `files`", async () => {
    const calls = mockApi({ "POST /api/files": { saved: [], failed: [], pipeline: null } });
    await api.upload([new File(["a"], "one.csv"), new File(["b"], "two.csv")]);
    const form = calls[0].body as FormData;
    expect(form.getAll("files").map((f) => (f as File).name)).toEqual(["one.csv", "two.csv"]);
    expect(vi.mocked(fetch).mock.calls[0][1]?.headers).toBeUndefined(); // the browser sets the boundary
  });

  it("encodes file names into the path", async () => {
    const calls = mockApi({ "DELETE /api/files/a%20b.csv": () => new Response(null, { status: 204 }) });
    await api.deleteFile("a b.csv");
    expect(calls[0].method).toBe("DELETE");
  });
});

describe("request handling", () => {
  beforeEach(() => {
    hooks.reload = vi.fn();
  });
  afterEach(() => vi.unstubAllGlobals());

  it("sends same-origin credentials", async () => {
    mockApi({ "GET /api/meta": {} });
    await api.meta();
    expect(vi.mocked(fetch).mock.calls[0][1]).toMatchObject({ credentials: "same-origin" });
  });

  it("surfaces the API's detail message", async () => {
    mockApi({ "GET /api/meta": () => jsonResponse({ detail: "no such thing" }, 404) });
    await expect(api.meta()).rejects.toMatchObject({ name: "ApiError", status: 404, message: "no such thing" });
  });

  it("surfaces a bad query's message (422)", async () => {
    mockApi({ "POST /api/sql/run": () => jsonResponse({ detail: 'near "SELEC": syntax error' }, 422) });
    await expect(api.sqlRun("SELEC")).rejects.toMatchObject({ status: 422, message: 'near "SELEC": syntax error' });
  });

  it("falls back to the status when the error body is not JSON", async () => {
    mockApi({ "GET /api/meta": () => new Response("<html>bad gateway</html>", { status: 502 }) });
    await expect(api.meta()).rejects.toThrow("Request failed (502)");
  });

  it("reloads once on a 401, then stops so a persistent 401 cannot loop", async () => {
    mockApi({ "GET /api/me": () => jsonResponse({ detail: "not logged in" }, 401) });
    await expect(api.me()).rejects.toBeInstanceOf(ApiError);
    expect(hooks.reload).toHaveBeenCalledTimes(1);
    await expect(api.me()).rejects.toThrow(/login expired/i);
    expect(hooks.reload).toHaveBeenCalledTimes(1);
  });

  it("allows another reload after a request has succeeded", async () => {
    let status = 401;
    mockApi({ "GET /api/me": () => (status === 401 ? jsonResponse({}, 401) : jsonResponse({ user: "u", email: "e" })) });
    await expect(api.me()).rejects.toBeInstanceOf(ApiError);
    status = 200;
    await api.me();
    status = 401;
    await expect(api.me()).rejects.toBeInstanceOf(ApiError);
    expect(hooks.reload).toHaveBeenCalledTimes(2);
  });
});
