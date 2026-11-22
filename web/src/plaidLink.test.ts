import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  ALIAS_RULE,
  LINK_TOKEN_LIFETIME_MS,
  PENDING_KEY,
  PLAID_SCRIPT,
  clearPending,
  defaultStartDate,
  exitText,
  finishSuccess,
  loadPlaid,
  pullOutcome,
  readPending,
  savePending,
  validAlias,
} from "./plaidLink";
import { jsonResponse, mockApi } from "./test-utils";
import type { PendingLink, PullResult } from "./types";

const pending = (over: Partial<PendingLink> = {}): PendingLink => ({
  link_token: "link-abc",
  mode: "new",
  alias: "capital-one",
  start_date: "2026-01-01",
  savedAt: Date.now(),
  ...over,
});

beforeEach(() => {
  delete window.Plaid;
});
afterEach(() => {
  delete window.Plaid;
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("alias and start date", () => {
  it.each(["a", "capital-one-dragos-venture-x", "0abc", "a-b-c", "x".repeat(48)])("accepts %s", (alias) => {
    expect(validAlias(alias)).toBe(true);
  });
  it.each(["", "Capital", "has space", "-lead", "x".repeat(49), "../etc", "under_score", "ünï"])("rejects %j", (alias) => {
    expect(validAlias(alias)).toBe(false);
  });
  it("says the rule in plain words", () => expect(ALIAS_RULE).toMatch(/lowercase letters, digits and hyphens/));
  it("defaults to January 1 of the current year, like the old app", () => {
    expect(defaultStartDate(new Date(2026, 10, 22))).toBe("2026-01-01");
    expect(defaultStartDate(new Date(2027, 0, 5))).toBe("2027-01-01");
  });
});

describe("the pending link", () => {
  it("round-trips and clears", () => {
    savePending(pending());
    expect(readPending()?.link_token).toBe("link-abc");
    clearPending();
    expect(readPending()).toBeNull();
    expect(localStorage.getItem(PENDING_KEY)).toBeNull();
  });

  it("is ignored, and removed, once its link token (4 hours) has expired", () => {
    const now = 1_000_000_000_000;
    savePending(pending({ savedAt: now - LINK_TOKEN_LIFETIME_MS + 1000 }));
    expect(readPending(now)).not.toBeNull();
    savePending(pending({ savedAt: now - LINK_TOKEN_LIFETIME_MS }));
    expect(readPending(now)).toBeNull();
    expect(localStorage.getItem(PENDING_KEY)).toBeNull();
  });

  it.each([["not json"], ["{}"], [JSON.stringify({ link_token: 1, mode: "new", alias: "a", savedAt: 1 })], [JSON.stringify({ link_token: "x", mode: "other", alias: "a", savedAt: Date.now() })]])(
    "ignores and removes garbled content %j",
    (raw) => {
      localStorage.setItem(PENDING_KEY, raw);
      expect(readPending()).toBeNull();
      expect(localStorage.getItem(PENDING_KEY)).toBeNull();
    },
  );
});

describe("loading Plaid Link", () => {
  it("uses Plaid if it is already on the page, without adding a script", async () => {
    const plaid = { create: vi.fn() };
    window.Plaid = plaid;
    const append = vi.spyOn(document.head, "appendChild");
    await expect(loadPlaid()).resolves.toBe(plaid);
    expect(append).not.toHaveBeenCalled();
  });

  it("adds Plaid's script once, however many callers wait for it", async () => {
    let script: HTMLScriptElement | undefined;
    const append = vi.spyOn(document.head, "appendChild").mockImplementation((node) => {
      script = node as HTMLScriptElement;
      return node;
    });
    const a = loadPlaid();
    const b = loadPlaid();
    expect(append).toHaveBeenCalledTimes(1);
    expect(script?.src).toBe(PLAID_SCRIPT);
    const plaid = { create: vi.fn() };
    window.Plaid = plaid;
    script?.onload?.(new Event("load"));
    await expect(a).resolves.toBe(plaid);
    await expect(b).resolves.toBe(plaid);
  });

  it("says so when the script cannot load (blocked), and lets the next attempt try again", async () => {
    const scripts: HTMLScriptElement[] = [];
    vi.spyOn(document.head, "appendChild").mockImplementation((node) => {
      scripts.push(node as HTMLScriptElement);
      return node;
    });
    const first = loadPlaid();
    scripts[0].onerror?.(new Event("error"));
    await expect(first).rejects.toThrow("Could not load Plaid Link (blocked?)");
    const second = loadPlaid();
    expect(scripts).toHaveLength(2);
    scripts[1].onload?.(new Event("load")); // loaded, but Plaid is not defined: still a clear failure
    await expect(second).rejects.toThrow("Could not load Plaid Link (blocked?)");
  });
});

describe("outcomes", () => {
  it("prefers Plaid's own words for why Link ended", () => {
    expect(exitText({ display_message: "Try again later", error_message: "x", error_code: "Y" })).toBe("Try again later");
    expect(exitText({ display_message: null, error_message: "the message", error_code: "CODE" })).toBe("the message");
    expect(exitText({ error_code: "CODE" })).toBe("CODE");
    expect(exitText({})).toBe("Plaid Link ended with an error.");
  });

  it("a pull outcome lists the accounts that need a reconnect, and only those", () => {
    const r: PullResult = {
      accounts: [
        { alias: "a", pulled: 3 },
        { alias: "b", error: "ITEM_LOGIN_REQUIRED: login", code: "ITEM_LOGIN_REQUIRED", needs_reconnect: true },
        { alias: "c", error: "INSTITUTION_DOWN: down", code: "INSTITUTION_DOWN", needs_reconnect: false },
      ],
      pipeline: null,
    };
    const o = pullOutcome(r);
    expect(o.kind).toBe("error");
    expect(o.reconnect).toEqual(["b"]);
    expect(o.text).toBe("a: 3 transactions; b: ITEM_LOGIN_REQUIRED: login; c: INSTITUTION_DOWN: down");
    expect(pullOutcome({ accounts: [{ alias: "a", pulled: 3 }], pipeline: { ran: true, seconds: 2, count: 9 } })).toEqual({
      kind: "success",
      text: "a: 3 transactions Pipeline ran in 2 s: 9 transactions.",
      reconnect: [],
    });
  });
});

describe("finishSuccess", () => {
  it("a new link trades the public token for the account (alias and start date from the form) and clears the pending link", async () => {
    savePending(pending());
    const calls = mockApi({
      "POST /api/plaid/exchange": () => jsonResponse({ alias: "capital-one", institution: "Capital One", start_date: "2026-01-01" }, 201),
    });
    const o = await finishSuccess(pending(), "public-xyz");
    expect(calls[0].body).toEqual({ public_token: "public-xyz", alias: "capital-one", start_date: "2026-01-01" });
    expect(o).toEqual({ kind: "success", text: "Linked Capital One as capital-one. Run Refresh data to pull transactions." });
    expect(readPending()).toBeNull();
  });

  it("falls back to the alias when Plaid gave no institution name, and omits a missing start date", async () => {
    const calls = mockApi({ "POST /api/plaid/exchange": () => jsonResponse({ alias: "x", institution: null, start_date: "2026-01-01" }, 201) });
    const o = await finishSuccess(pending({ alias: "x", start_date: null }), "public-xyz");
    expect(calls[0].body).toEqual({ public_token: "public-xyz", alias: "x" });
    expect(o.text).toBe("Linked x as x. Run Refresh data to pull transactions.");
  });

  it("a reconnect does not exchange anything: it refreshes the data", async () => {
    savePending(pending({ mode: "update", alias: "card", start_date: null }));
    const calls = mockApi({ "POST /api/accounts/pull": { accounts: [{ alias: "card", pulled: 12 }], pipeline: null } });
    const o = await finishSuccess(pending({ mode: "update", alias: "card", start_date: null }), "public-xyz");
    expect(calls.map((c) => c.url)).toEqual(["/api/accounts/pull"]);
    expect(o).toEqual({ kind: "success", text: "card: 12 transactions", reconnect: [] });
    expect(readPending()).toBeNull();
  });

  it("reports the server's reason (alias in use, Plaid unavailable) and keeps the pending link for another try", async () => {
    savePending(pending());
    mockApi({ "POST /api/plaid/exchange": () => jsonResponse({ detail: "'capital-one' is already linked: use Reconnect, or pick another alias" }, 409) });
    const o = await finishSuccess(pending(), "public-xyz");
    expect(o).toEqual({ kind: "error", text: "'capital-one' is already linked: use Reconnect, or pick another alias" });
    expect(readPending()).not.toBeNull();
  });
});

