import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError, api, buildQuery, detailMessage, hooks } from "./api";
import { EMPTY_FILTERS } from "./filters";
import { jsonResponse, mockApi } from "./test-utils";

describe("buildQuery", () => {
  it("repeats the key for arrays and skips empty values", () => {
    const q = buildQuery({ category_in: ["Dining", "Rent & Bills"], source: [], q: "", start: "2024-01-01", offset: 0 });
    expect(q).toBe("?category_in=Dining&category_in=Rent+%26+Bills&start=2024-01-01&offset=0");
  });

  it("is empty when there is nothing to send", () => {
    expect(buildQuery({ q: undefined, source: [] })).toBe("");
  });
});

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

describe("request handling", () => {
  beforeEach(() => {
    hooks.reload = vi.fn();
  });
  afterEach(() => vi.unstubAllGlobals());

  it("sends same-origin credentials and never puts anything but filters in the URL", async () => {
    const calls = mockApi({ "GET /api/transactions": { total: 0, sum: 0, rows: [] } });
    await api.transactions({ ...EMPTY_FILTERS, categoryIn: ["Dining", "Rent"], q: " uber+lyft ", sources: ["a.csv"] }, "amount", "asc", 100);
    expect(calls[0].url).toBe(
      "/api/transactions?category_in=Dining&category_in=Rent&source=a.csv&q=uber%2Blyft&sort=amount&order=asc&offset=100&limit=100",
    );
    expect(vi.mocked(fetch).mock.calls[0][1]).toMatchObject({ credentials: "same-origin" });
  });

  it("surfaces the API's detail message", async () => {
    mockApi({ "GET /api/meta": () => jsonResponse({ detail: "no such thing" }, 404) });
    await expect(api.meta()).rejects.toMatchObject({ name: "ApiError", status: 404, message: "no such thing" });
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

  it("sends the upload as multipart with the field name `files`", async () => {
    const calls = mockApi({ "POST /api/files": { saved: [], failed: [], pipeline: null } });
    await api.upload([new File(["a"], "one.csv"), new File(["b"], "two.csv")]);
    const form = calls[0].body as FormData;
    expect(form.getAll("files").map((f) => (f as File).name)).toEqual(["one.csv", "two.csv"]);
    expect(vi.mocked(fetch).mock.calls[0][1]?.headers).toBeUndefined(); // the browser sets the boundary
  });

  it("encodes primary keys and file names into the path", async () => {
    const calls = mockApi({
      "DELETE /api/transactions/amex%20blue.csv-1%2F2": () => new Response(null, { status: 204 }),
      "DELETE /api/files/a%20b.csv": () => new Response(null, { status: 204 }),
    });
    await api.deleteTransaction("amex blue.csv-1/2");
    await api.deleteFile("a b.csv");
    expect(calls.map((c) => c.method)).toEqual(["DELETE", "DELETE"]);
  });
});
