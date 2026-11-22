import type {
  Account,
  ByCategory,
  Bin,
  Me,
  Meta,
  Order,
  OverTime,
  PipelineResult,
  PullResult,
  RawFile,
  Rules,
  SortKey,
  TransactionCreate,
  TransactionPage,
  TransactionUpdate,
  UploadResult,
} from "./types";
import { filtersToParams, type Filters } from "./filters";

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

/** Replaceable in tests. */
export const hooks = {
  reload: () => window.location.reload(),
};

const RELOADED = "expenses.reloaded-after-401";

/** FastAPI sends `detail` as a string, or (for 422 validation) a list of {loc, msg}. */
export function detailMessage(body: unknown, fallback: string): string {
  const detail = (body as { detail?: unknown } | null)?.detail;
  if (typeof detail === "string" && detail) return detail;
  if (Array.isArray(detail)) {
    const parts = detail
      .map((d) => {
        const msg = (d as { msg?: unknown }).msg;
        const loc = (d as { loc?: unknown }).loc;
        if (typeof msg !== "string") return null;
        const field = Array.isArray(loc) ? loc.filter((p) => p !== "body" && p !== "query").join(".") : "";
        return field ? `${field}: ${msg}` : msg;
      })
      .filter((p): p is string => !!p);
    if (parts.length) return parts.join("; ");
  }
  return fallback;
}

/** Repeats a key for arrays (`category_in=a&category_in=b`), skips empty values. */
export function buildQuery(params: Record<string, string | number | undefined | string[]>): string {
  const q = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value === undefined || value === "") continue;
    if (Array.isArray(value)) value.forEach((v) => q.append(key, v));
    else q.append(key, String(value));
  }
  const s = q.toString();
  return s ? `?${s}` : "";
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const response = await fetch(path, { credentials: "same-origin", ...init });
  if (response.status === 401) {
    // The login (oauth2-proxy cookie) expired: sign in again by reloading, but only once, so a
    // persistent 401 shows a message instead of looping.
    if (!sessionStorage.getItem(RELOADED)) {
      sessionStorage.setItem(RELOADED, "1");
      hooks.reload();
    }
    throw new ApiError(401, "Your login expired. Reload the page to sign in again.");
  }
  sessionStorage.removeItem(RELOADED);
  if (!response.ok) {
    let body: unknown = null;
    try {
      body = await response.json();
    } catch {
      /* not JSON */
    }
    throw new ApiError(response.status, detailMessage(body, `Request failed (${response.status})`));
  }
  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

const json = (method: string, body: unknown): RequestInit => ({
  method,
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify(body),
});

export const api = {
  me: () => request<Me>("/api/me"),
  meta: () => request<Meta>("/api/meta"),

  transactions: (f: Filters, sort: SortKey, order: Order, offset: number, limit = 100) =>
    request<TransactionPage>(`/api/transactions${buildQuery({ ...filtersToParams(f), sort, order, offset, limit })}`),
  byCategory: (f: Filters) => request<ByCategory>(`/api/summary/by-category${buildQuery(filtersToParams(f))}`),
  overTime: (f: Filters, bin: Bin) =>
    request<OverTime>(`/api/summary/over-time${buildQuery({ ...filtersToParams(f), bin })}`),

  addTransaction: (body: TransactionCreate) => request<{ pk: string }>("/api/transactions", json("POST", body)),
  updateTransaction: (pk: string, body: TransactionUpdate) =>
    request<{ pk: string }>(`/api/transactions/${encodeURIComponent(pk)}`, json("PATCH", body)),
  deleteTransaction: (pk: string) =>
    request<void>(`/api/transactions/${encodeURIComponent(pk)}`, { method: "DELETE" }),

  rules: () => request<Rules>("/api/rules"),
  putRules: (rules: Rules) => request<Rules>("/api/rules", json("PUT", rules)),

  files: () => request<RawFile[]>("/api/files"),
  upload: (files: File[]) => {
    const form = new FormData();
    files.forEach((f) => form.append("files", f, f.name));
    return request<UploadResult>("/api/files", { method: "POST", body: form });
  },
  deleteFile: (name: string) => request<void>(`/api/files/${encodeURIComponent(name)}`, { method: "DELETE" }),
  runPipeline: (rulesOnly = false) => request<PipelineResult>("/api/pipeline/run", json("POST", { rules_only: rulesOnly })),

  accounts: () => request<Account[]>("/api/accounts"),
  pull: () => request<PullResult>("/api/accounts/pull", { method: "POST" }),
};
