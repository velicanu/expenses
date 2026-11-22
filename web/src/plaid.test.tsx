import { act, fireEvent, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { StrictMode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { App } from "./App";
import { ALIAS_RULE, PENDING_KEY, defaultStartDate, savePending, type PlaidCreateOptions } from "./plaidLink";
import { META, appRoutes, callsTo, jsonResponse, mockApi, renderWithClient, type Call } from "./test-utils";
import type { AccountStatus, PendingLink } from "./types";

const TOKEN_LIKE = /access-(production|sandbox|development)-/;
const META_PLAID = { ...META, plaid_configured: true, plaid_oauth_ready: true };
const NOT_OAUTH_READY = "Banks that use OAuth (Capital One, Chase, Wealthfront) need a return address registered at Plaid.";

const CARD = { alias: "card", institution: "Capital One", start_date: "2025-12-31" };
const status = (over: Partial<AccountStatus> = {}): AccountStatus => ({
  ...CARD,
  ok: true,
  error_code: null,
  needs_reconnect: false,
  consent_expires: null,
  ...over,
});

/** A stand-in for Plaid Link: records what it was asked to do, and lets a test play the person's part. */
function fakePlaid() {
  const created: PlaidCreateOptions[] = [];
  const seenAtOpen: (string | null)[] = [];
  const handler = {
    open: vi.fn(() => seenAtOpen.push(localStorage.getItem(PENDING_KEY))),
    exit: vi.fn(),
    destroy: vi.fn(),
  };
  const create = vi.fn((options: PlaidCreateOptions) => {
    created.push(options);
    return handler;
  });
  window.Plaid = { create };
  return {
    created,
    handler,
    create,
    seenAtOpen,
    last: () => created[created.length - 1],
    success: (publicToken = "public-xyz") => act(async () => created[created.length - 1].onSuccess(publicToken)),
    exit: (error: Parameters<PlaidCreateOptions["onExit"]>[0] = null) => act(async () => created[created.length - 1].onExit(error)),
  };
}

beforeEach(() => {
  window.history.replaceState(null, "", "/");
});
afterEach(() => {
  delete window.Plaid;
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
  window.history.replaceState(null, "", "/");
});

async function openInputs(over: Record<string, unknown> = {}) {
  const calls = mockApi(appRoutes({ "GET /api/meta": META_PLAID, ...over }));
  renderWithClient(<App />);
  await screen.findByLabelText("Start date");
  await userEvent.click(screen.getByRole("button", { name: "Inputs" }));
  await screen.findByText("Linked cards:");
  return calls;
}

const inputs = () => screen.getByRole("region", { name: "Inputs" });

async function fillForm(alias: string) {
  await userEvent.click(screen.getByRole("button", { name: "Link account" }));
  await userEvent.type(screen.getByLabelText("Account alias"), alias);
}

const exchangeRoute = (institution: string | null = "Capital One") => ({
  "POST /api/plaid/exchange": (c: Call) =>
    jsonResponse({ alias: (c.body as { alias: string }).alias, institution, start_date: (c.body as { start_date?: string }).start_date ?? "2026-01-01" }, 201),
});

describe("the Link account form (the old wording)", () => {
  it("is disabled, with the reason, when the server has no Plaid keys, and shows no form", async () => {
    await openInputs({ "GET /api/meta": META });
    const button = screen.getByRole("button", { name: "Link account" });
    expect(button).toBeDisabled();
    expect(button).toHaveAttribute("title", "Plaid is not set up on the server (it cannot read its Plaid keys)");
    expect(screen.queryByLabelText("Account alias")).toBeNull();
  });

  it("asks for an alias first: 'Alias required to add token', and no Connect bank yet", async () => {
    await openInputs();
    await userEvent.click(screen.getByRole("button", { name: "Link account" }));
    expect(screen.getByLabelText("Account alias")).toHaveValue("");
    expect(screen.getByText("Alias required to add token")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Connect bank" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Custom start date" })).toBeNull();
    await userEvent.click(screen.getByRole("button", { name: "Link account" })); // toggles the form away again
    expect(screen.queryByLabelText("Account alias")).toBeNull();
  });

  it("explains an alias the server would refuse, and offers nothing until it is fine", async () => {
    await openInputs();
    await fillForm("Capital One");
    expect(screen.getByRole("alert")).toHaveTextContent(ALIAS_RULE);
    expect(screen.queryByRole("button", { name: "Connect bank" })).toBeNull();
    await userEvent.clear(screen.getByLabelText("Account alias"));
    await userEvent.type(screen.getByLabelText("Account alias"), "capital-one");
    expect(screen.queryByText(ALIAS_RULE)).toBeNull();
    expect(screen.getByRole("button", { name: "Connect bank" })).toBeEnabled();
  });

  it("starts the start date at January 1 of this year, behind 'Custom start date', with the old help text", async () => {
    await openInputs();
    await fillForm("capital-one");
    expect(screen.queryByLabelText(/Transaction start date/)).toBeNull();
    await userEvent.click(screen.getByRole("button", { name: "Custom start date" }));
    expect(screen.getByLabelText(/Transaction start date/)).toHaveValue(defaultStartDate());
    expect(
      screen.getByRole("img", {
        name: "Only pull transactions after this date. This is useful if you are combining manually uploaded CSVs with auto.",
      }),
    ).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Custom start date" }));
    expect(screen.queryByLabelText(/Transaction start date/)).toBeNull();
  });

  it("says Connect bank, not Get token", async () => {
    await openInputs();
    await fillForm("capital-one");
    expect(screen.queryByRole("button", { name: "Get token" })).toBeNull();
    expect(screen.getByRole("button", { name: "Connect bank" })).toBeInTheDocument();
  });

  it("notes that OAuth banks need a registered return address only when the server has none", async () => {
    await openInputs({ "GET /api/meta": { ...META_PLAID, plaid_oauth_ready: false } });
    await userEvent.click(screen.getByRole("button", { name: "Link account" }));
    expect(screen.getByText(NOT_OAUTH_READY)).toBeInTheDocument();
  });

  it("has no such note when the return address is set", async () => {
    await openInputs();
    await userEvent.click(screen.getByRole("button", { name: "Link account" }));
    expect(screen.queryByText(NOT_OAUTH_READY)).toBeNull();
  });
});

describe("linking a new bank", () => {
  it("makes a link token (no alias), keeps the pending link before Link opens, then exchanges the public token", async () => {
    const plaid = fakePlaid();
    const calls = await openInputs({ "POST /api/plaid/link-token": { link_token: "link-abc", mode: "new" }, ...exchangeRoute() });
    await fillForm("capital-one");
    await userEvent.click(screen.getByRole("button", { name: "Connect bank" }));

    await waitFor(() => expect(plaid.handler.open).toHaveBeenCalledTimes(1));
    expect(callsTo(calls, "POST /api/plaid/link-token")[0].body).toEqual({});
    expect(plaid.create).toHaveBeenCalledTimes(1);
    expect(plaid.last().token).toBe("link-abc");
    expect(plaid.last().receivedRedirectUri).toBeUndefined(); // only a return from a bank's OAuth login has one
    const saved = JSON.parse(plaid.seenAtOpen[0] ?? "null") as PendingLink; // already stored when Link opened
    expect(saved).toMatchObject({ link_token: "link-abc", mode: "new", alias: "capital-one", start_date: defaultStartDate() });
    expect(typeof saved.savedAt).toBe("number");
    expect(screen.getByText("Waiting for Plaid Link…")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Connect bank" })).toBeDisabled(); // not twice

    const accountsBefore = callsTo(calls, "GET /api/accounts").length;
    const statusBefore = callsTo(calls, "POST /api/accounts/status").length;
    await plaid.success("public-xyz");

    expect(await screen.findByText("Linked Capital One as capital-one. Run Refresh data to pull transactions.")).toBeInTheDocument();
    expect(callsTo(calls, "POST /api/plaid/exchange")[0].body).toEqual({
      public_token: "public-xyz",
      alias: "capital-one",
      start_date: defaultStartDate(),
    });
    expect(localStorage.getItem(PENDING_KEY)).toBeNull();
    expect(plaid.handler.destroy).toHaveBeenCalled();
    await waitFor(() => expect(callsTo(calls, "GET /api/accounts").length).toBeGreaterThan(accountsBefore));
    await waitFor(() => expect(callsTo(calls, "POST /api/accounts/status").length).toBeGreaterThan(statusBefore));
    expect(callsTo(calls, "POST /api/accounts/pull")).toHaveLength(0); // a new link does not pull on its own
    expect(screen.queryByText("Waiting for Plaid Link…")).toBeNull();
  });

  it("sends the custom start date", async () => {
    const plaid = fakePlaid();
    const calls = await openInputs({ "POST /api/plaid/link-token": { link_token: "link-abc", mode: "new" }, ...exchangeRoute() });
    await fillForm("capital-one");
    await userEvent.click(screen.getByRole("button", { name: "Custom start date" }));
    fireEvent.change(screen.getByLabelText(/Transaction start date/), { target: { value: "2025-12-31" } });
    await userEvent.click(screen.getByRole("button", { name: "Connect bank" }));
    await waitFor(() => expect(plaid.handler.open).toHaveBeenCalled());
    expect(JSON.parse(plaid.seenAtOpen[0] ?? "{}").start_date).toBe("2025-12-31");
    await plaid.success();
    await screen.findByText(/Linked Capital One/);
    expect(callsTo(calls, "POST /api/plaid/exchange")[0].body).toMatchObject({ alias: "capital-one", start_date: "2025-12-31" });
  });

  it("closing Link without an error is quiet: no message, the pending link is dropped, you can try again", async () => {
    const plaid = fakePlaid();
    await openInputs({ "POST /api/plaid/link-token": { link_token: "link-abc", mode: "new" } });
    await fillForm("capital-one");
    await userEvent.click(screen.getByRole("button", { name: "Connect bank" }));
    await waitFor(() => expect(plaid.handler.open).toHaveBeenCalled());
    await plaid.exit(null);
    expect(inputs().querySelector(".alert")).toBeNull();
    expect(localStorage.getItem(PENDING_KEY)).toBeNull();
    await waitFor(() => expect(screen.getByRole("button", { name: "Connect bank" })).toBeEnabled());
  });

  it("shows Plaid's own words when Link ends with an error", async () => {
    const plaid = fakePlaid();
    await openInputs({ "POST /api/plaid/link-token": { link_token: "link-abc", mode: "new" } });
    await fillForm("capital-one");
    await userEvent.click(screen.getByRole("button", { name: "Connect bank" }));
    await waitFor(() => expect(plaid.handler.open).toHaveBeenCalled());
    await plaid.exit({ error_code: "INSTITUTION_NOT_RESPONDING", error_message: "internal", display_message: "The bank is not responding. Try again later." });
    expect(await screen.findByText("The bank is not responding. Try again later.")).toBeInTheDocument();
    expect(localStorage.getItem(PENDING_KEY)).toBeNull();
  });

  it("falls back to Plaid's error_message when there is no display message", async () => {
    const plaid = fakePlaid();
    await openInputs({ "POST /api/plaid/link-token": { link_token: "link-abc", mode: "new" } });
    await fillForm("capital-one");
    await userEvent.click(screen.getByRole("button", { name: "Connect bank" }));
    await waitFor(() => expect(plaid.handler.open).toHaveBeenCalled());
    await plaid.exit({ error_code: "X", error_message: "the technical message", display_message: null });
    expect(await screen.findByText("the technical message")).toBeInTheDocument();
  });

  it("shows the server's message verbatim when Plaid refuses a link token (an unregistered redirect URI)", async () => {
    const plaid = fakePlaid();
    const detail =
      "Plaid: INVALID_FIELD: OAuth redirect URI must be configured in the developer dashboard. Add it under Allowed redirect URIs at https://dashboard.plaid.com/developers/api.";
    await openInputs({ "POST /api/plaid/link-token": () => jsonResponse({ detail, code: "INVALID_FIELD" }, 502) });
    await fillForm("capital-one");
    await userEvent.click(screen.getByRole("button", { name: "Connect bank" }));
    expect(await screen.findByText(detail)).toBeInTheDocument();
    expect(plaid.create).not.toHaveBeenCalled();
    expect(localStorage.getItem(PENDING_KEY)).toBeNull();
    expect(screen.getByRole("button", { name: "Connect bank" })).toBeEnabled();
  });

  it("says so when Plaid or bao is unreachable (503)", async () => {
    fakePlaid();
    await openInputs({ "POST /api/plaid/link-token": () => jsonResponse({ detail: "Plaid is unavailable: cannot read the Plaid keys from bao (URLError)" }, 503) });
    await fillForm("capital-one");
    await userEvent.click(screen.getByRole("button", { name: "Connect bank" }));
    expect(await screen.findByText("Plaid is unavailable: cannot read the Plaid keys from bao (URLError)")).toBeInTheDocument();
  });

  it("tells you when the alias is already linked (409) and keeps the error on screen", async () => {
    const plaid = fakePlaid();
    await openInputs({
      "POST /api/plaid/link-token": { link_token: "link-abc", mode: "new" },
      "POST /api/plaid/exchange": () => jsonResponse({ detail: "'capital-one' is already linked: use Reconnect, or pick another alias" }, 409),
    });
    await fillForm("capital-one");
    await userEvent.click(screen.getByRole("button", { name: "Connect bank" }));
    await waitFor(() => expect(plaid.handler.open).toHaveBeenCalled());
    await plaid.success();
    expect(await screen.findByText("'capital-one' is already linked: use Reconnect, or pick another alias")).toBeInTheDocument();
    vi.useFakeTimers();
    await act(async () => void vi.advanceTimersByTime(20_000));
    vi.useRealTimers();
    expect(screen.getByText(/already linked/)).toBeInTheDocument(); // errors do not fade like confirmations
  });

  it("says so when Plaid's script cannot load (blocked)", async () => {
    mockApi(appRoutes({ "GET /api/meta": META_PLAID, "POST /api/plaid/link-token": { link_token: "link-abc", mode: "new" } }));
    vi.spyOn(document.head, "appendChild").mockImplementation((node) => {
      setTimeout(() => (node as HTMLScriptElement).onerror?.(new Event("error")), 0);
      return node;
    });
    renderWithClient(<App />);
    await screen.findByLabelText("Start date");
    await userEvent.click(screen.getByRole("button", { name: "Inputs" }));
    await fillForm("capital-one");
    await userEvent.click(screen.getByRole("button", { name: "Connect bank" }));
    expect(await screen.findByText("Could not load Plaid Link (blocked?)")).toBeInTheDocument();
    expect(localStorage.getItem(PENDING_KEY)).toBeNull();
  });

  it("never puts an access token on the page or in a request; only the public token goes to the exchange", async () => {
    const plaid = fakePlaid();
    const calls = await openInputs({
      "GET /api/accounts": [CARD],
      "POST /api/accounts/status": [status()],
      "POST /api/plaid/link-token": { link_token: "link-abc", mode: "new" },
      ...exchangeRoute(),
    });
    await fillForm("second-card");
    await userEvent.click(screen.getByRole("button", { name: "Connect bank" }));
    await waitFor(() => expect(plaid.handler.open).toHaveBeenCalled());
    await plaid.success("public-production-123");
    await screen.findByText(/Linked Capital One as second-card/);
    expect(document.body.innerHTML).not.toMatch(TOKEN_LIKE);
    const bodies = calls.filter((c) => c.body !== undefined).map((c) => JSON.stringify(c.body));
    expect(bodies.join("\n")).not.toMatch(TOKEN_LIKE);
    const withPublic = calls.filter((c) => JSON.stringify(c.body ?? "").includes("public-production-123"));
    expect(withPublic.map((c) => `${c.method} ${c.url}`)).toEqual(["POST /api/plaid/exchange"]);
    expect(localStorage.getItem(PENDING_KEY) ?? "").not.toMatch(/public-/); // and it is not kept in the pending link
  });
});

describe("the status column", () => {
  it("asks Plaid once when the panel opens, not when you type", async () => {
    const calls = await openInputs({ "GET /api/accounts": [CARD], "POST /api/accounts/status": [status()] });
    await screen.findByText("OK");
    expect(callsTo(calls, "POST /api/accounts/status")).toHaveLength(1);
    await userEvent.click(screen.getByRole("button", { name: "Link account" }));
    await userEvent.type(screen.getByLabelText("Account alias"), "abc");
    expect(callsTo(calls, "POST /api/accounts/status")).toHaveLength(1);
  });

  it("does not ask again just because the page's data refreshed (running the pipeline)", async () => {
    const calls = await openInputs({ "GET /api/accounts": [CARD], "POST /api/accounts/status": [status()] });
    await screen.findByText("OK");
    await userEvent.click(screen.getByRole("button", { name: "Run pipeline" }));
    await screen.findByText(/Pipeline ran in/);
    await waitFor(() => expect(callsTo(calls, "GET /api/meta").length).toBeGreaterThan(1));
    expect(callsTo(calls, "POST /api/accounts/status")).toHaveLength(1);
  });

  it("shows OK, with the consent date when Plaid gave one", async () => {
    await openInputs({
      "GET /api/accounts": [CARD],
      "POST /api/accounts/status": [status({ consent_expires: "2027-01-26T02:53:53+00:00" })],
    });
    const row = (await screen.findByText("card")).closest("tr") as HTMLElement;
    expect(await within(row).findByText(/^OK/)).toBeInTheDocument();
    expect(within(row).getByText("(consent until 2027-01-26)")).toBeInTheDocument();
    expect(within(row).queryByRole("button", { name: "Reconnect" })).toBeNull();
    expect(screen.getByText("status")).toBeInTheDocument();
  });

  it("shows 'Needs reconnect' with a Reconnect button for an expired bank login", async () => {
    await openInputs({
      "GET /api/accounts": [CARD],
      "POST /api/accounts/status": [status({ ok: false, error_code: "ITEM_LOGIN_REQUIRED", needs_reconnect: true })],
    });
    const row = (await screen.findByText("card")).closest("tr") as HTMLElement;
    expect(await within(row).findByText(/Needs reconnect/)).toBeInTheDocument();
    expect(within(row).getByRole("button", { name: "Reconnect" })).toBeEnabled();
  });

  it("shows another error's code without a Reconnect button (reconnecting would not help)", async () => {
    await openInputs({
      "GET /api/accounts": [CARD],
      "POST /api/accounts/status": [status({ ok: false, error_code: "INSTITUTION_DOWN", needs_reconnect: false })],
    });
    const row = (await screen.findByText("card")).closest("tr") as HTMLElement;
    expect(await within(row).findByText("INSTITUTION_DOWN")).toBeInTheDocument();
    expect(within(row).queryByRole("button", { name: "Reconnect" })).toBeNull();
  });

  it("a failing status request does not break the panel: the table stays, with a note", async () => {
    await openInputs({
      "GET /api/accounts": [CARD],
      "POST /api/accounts/status": () => jsonResponse({ detail: "Plaid is unavailable: cannot read the Plaid keys" }, 503),
    });
    const row = (await screen.findByText("card")).closest("tr") as HTMLElement;
    expect(within(row).getByText("Capital One")).toBeInTheDocument();
    expect(await screen.findByText(/The connection status is not available right now \(Plaid is unavailable/)).toBeInTheDocument();
    expect(screen.queryByText("status")).toBeNull(); // no status column
    expect(screen.getByRole("button", { name: "Run pipeline" })).toBeEnabled();
  });

  it("disables Reconnect, with the reason, when the server has no Plaid keys", async () => {
    await openInputs({
      "GET /api/meta": META,
      "GET /api/accounts": [CARD],
      "POST /api/accounts/status": [status({ ok: false, error_code: "ITEM_LOGIN_REQUIRED", needs_reconnect: true })],
    });
    const row = (await screen.findByText("card")).closest("tr") as HTMLElement;
    const button = await within(row).findByRole("button", { name: "Reconnect" });
    expect(button).toBeDisabled();
    expect(button).toHaveAttribute("title", "Plaid is not set up on the server (it cannot read its Plaid keys)");
  });
});

describe("reconnecting", () => {
  const expired = { "GET /api/accounts": [CARD], "POST /api/accounts/status": [status({ ok: false, error_code: "ITEM_LOGIN_REQUIRED", needs_reconnect: true })] };

  it("uses the account's alias for the link token (update mode), then refreshes the data and the status, with no exchange", async () => {
    const plaid = fakePlaid();
    const calls = await openInputs({
      ...expired,
      "POST /api/plaid/link-token": { link_token: "link-update", mode: "update" },
      "POST /api/accounts/pull": { accounts: [{ alias: "card", pulled: 41 }], pipeline: { ran: true, seconds: 1.5, count: 12150 } },
    });
    const row = (await screen.findByText("card")).closest("tr") as HTMLElement;
    await userEvent.click(await within(row).findByRole("button", { name: "Reconnect" }));

    await waitFor(() => expect(plaid.handler.open).toHaveBeenCalledTimes(1));
    expect(callsTo(calls, "POST /api/plaid/link-token")[0].body).toEqual({ alias: "card" });
    expect(plaid.last().token).toBe("link-update");
    expect(plaid.last().receivedRedirectUri).toBeUndefined();
    expect(JSON.parse(plaid.seenAtOpen[0] ?? "{}")).toMatchObject({ mode: "update", alias: "card", start_date: null });

    const statusBefore = callsTo(calls, "POST /api/accounts/status").length;
    await plaid.success();
    expect(await screen.findByText(/card: 41 transactions Pipeline ran in 1\.5 s: 12150 transactions\./)).toBeInTheDocument();
    expect(callsTo(calls, "POST /api/accounts/pull")).toHaveLength(1);
    expect(callsTo(calls, "POST /api/plaid/exchange")).toHaveLength(0); // same access token: nothing to exchange
    expect(localStorage.getItem(PENDING_KEY)).toBeNull();
    await waitFor(() => expect(callsTo(calls, "POST /api/accounts/status").length).toBeGreaterThan(statusBefore));
  });

  it("quietly leaves things as they were if Link is closed", async () => {
    const plaid = fakePlaid();
    const calls = await openInputs({ ...expired, "POST /api/plaid/link-token": { link_token: "link-update", mode: "update" } });
    const row = (await screen.findByText("card")).closest("tr") as HTMLElement;
    await userEvent.click(await within(row).findByRole("button", { name: "Reconnect" }));
    await waitFor(() => expect(plaid.handler.open).toHaveBeenCalled());
    await plaid.exit(null);
    expect(inputs().querySelector(".alert")).toBeNull();
    expect(callsTo(calls, "POST /api/accounts/pull")).toHaveLength(0);
    expect(localStorage.getItem(PENDING_KEY)).toBeNull();
  });

  it("a pull that finds an expired login offers Reconnect next to its error", async () => {
    const plaid = fakePlaid();
    const calls = await openInputs({
      "GET /api/accounts": [{ ...CARD, alias: "chase-1" }],
      "POST /api/accounts/pull": {
        accounts: [{ alias: "chase-1", error: "ITEM_LOGIN_REQUIRED: the login details of this item have changed", code: "ITEM_LOGIN_REQUIRED", needs_reconnect: true }],
        pipeline: null,
      },
      "POST /api/plaid/link-token": { link_token: "link-update", mode: "update" },
    });
    await userEvent.click(screen.getByRole("button", { name: "Refresh data" }));
    const message = (await screen.findByText(/chase-1: ITEM_LOGIN_REQUIRED/)).closest("p") as HTMLElement;
    await userEvent.click(within(message).getByRole("button", { name: "Reconnect" }));
    await waitFor(() => expect(plaid.handler.open).toHaveBeenCalled());
    expect(callsTo(calls, "POST /api/plaid/link-token")[0].body).toEqual({ alias: "chase-1" });
  });

  it("keeps that Reconnect button on screen (it does not fade like a confirmation)", async () => {
    await openInputs({
      "GET /api/accounts": [CARD],
      "POST /api/accounts/pull": { accounts: [{ alias: "card", error: "ITEM_LOGIN_REQUIRED: x", code: "ITEM_LOGIN_REQUIRED", needs_reconnect: true }], pipeline: null },
    });
    await userEvent.click(screen.getByRole("button", { name: "Refresh data" }));
    const message = (await screen.findByText(/card: ITEM_LOGIN_REQUIRED/)).closest("p") as HTMLElement;
    vi.useFakeTimers();
    await act(async () => void vi.advanceTimersByTime(20_000));
    vi.useRealTimers();
    expect(within(message).getByRole("button", { name: "Reconnect" })).toBeInTheDocument();
  });

  it("offers no Reconnect for a pull that failed for another reason", async () => {
    await openInputs({
      "GET /api/accounts": [CARD],
      "POST /api/accounts/pull": { accounts: [{ alias: "card", error: "INSTITUTION_DOWN: the bank is down", code: "INSTITUTION_DOWN", needs_reconnect: false }], pipeline: null },
    });
    await userEvent.click(screen.getByRole("button", { name: "Refresh data" }));
    const message = (await screen.findByText(/card: INSTITUTION_DOWN/)).closest("p") as HTMLElement;
    expect(within(message).queryByRole("button", { name: "Reconnect" })).toBeNull();
  });
});

describe("coming back from a bank's OAuth login (/plaid-oauth)", () => {
  const pend = (over: Partial<PendingLink> = {}): PendingLink => ({
    link_token: "link-abc",
    mode: "new",
    alias: "capital-one",
    start_date: "2026-01-01",
    savedAt: Date.now(),
    ...over,
  });
  const arrive = (pending?: PendingLink | string) => {
    if (pending) localStorage.setItem(PENDING_KEY, typeof pending === "string" ? pending : JSON.stringify(pending));
    window.history.pushState(null, "", "/plaid-oauth?oauth_state_id=abc123");
  };

  it("shows only 'Finishing the bank connection…' (no sidebar), reopens Link with the pending token and the address it came back on", async () => {
    const plaid = fakePlaid();
    mockApi(appRoutes({ "GET /api/meta": META_PLAID, ...exchangeRoute() }));
    arrive(pend());
    const returnedTo = window.location.href;
    renderWithClient(<App />);
    expect(screen.getByText("Finishing the bank connection…")).toBeInTheDocument();
    expect(screen.queryByLabelText("Sidebar")).toBeNull();
    await waitFor(() => expect(plaid.handler.open).toHaveBeenCalledTimes(1));
    expect(plaid.create).toHaveBeenCalledTimes(1);
    expect(plaid.last().token).toBe("link-abc");
    expect(plaid.last().receivedRedirectUri).toBe(returnedTo);
    expect(plaid.last().receivedRedirectUri).toContain("oauth_state_id=abc123");
  });

  it("creates and opens Link once even under React StrictMode's double effects", async () => {
    const plaid = fakePlaid();
    mockApi(appRoutes({ "GET /api/meta": META_PLAID }));
    arrive(pend());
    renderWithClient(
      <StrictMode>
        <App />
      </StrictMode>,
    );
    await waitFor(() => expect(plaid.handler.open).toHaveBeenCalled());
    await new Promise((r) => setTimeout(r, 30));
    expect(plaid.create).toHaveBeenCalledTimes(1);
    expect(plaid.handler.open).toHaveBeenCalledTimes(1);
  });

  it("exchanges the public token with the pending alias and start date, goes back to '/', and shows the app with the result", async () => {
    const plaid = fakePlaid();
    const calls = mockApi(appRoutes({ "GET /api/meta": META_PLAID, ...exchangeRoute() }));
    const replace = vi.spyOn(window.history, "replaceState");
    arrive(pend({ alias: "capital-one", start_date: "2025-12-31" }));
    renderWithClient(<App />);
    await waitFor(() => expect(plaid.handler.open).toHaveBeenCalled());
    await plaid.success("public-xyz");

    expect(await screen.findByText("Linked Capital One as capital-one. Run Refresh data to pull transactions.")).toBeInTheDocument();
    expect(callsTo(calls, "POST /api/plaid/exchange")[0].body).toEqual({ public_token: "public-xyz", alias: "capital-one", start_date: "2025-12-31" });
    expect(replace).toHaveBeenCalledWith(null, "", "/");
    expect(window.location.pathname).toBe("/");
    expect(localStorage.getItem(PENDING_KEY)).toBeNull();
    await screen.findByLabelText("Start date"); // the normal page
    expect(screen.queryByText("Finishing the bank connection…")).toBeNull();
    await userEvent.click(screen.getByRole("button", { name: "Dismiss message" }));
    expect(screen.queryByText(/Linked Capital One/)).toBeNull();
  });

  it("a reconnect that comes back refreshes the data instead of exchanging", async () => {
    const plaid = fakePlaid();
    const calls = mockApi(
      appRoutes({
        "GET /api/meta": META_PLAID,
        "POST /api/accounts/pull": { accounts: [{ alias: "card", pulled: 7 }], pipeline: null },
      }),
    );
    arrive(pend({ mode: "update", alias: "card", start_date: null }));
    renderWithClient(<App />);
    await waitFor(() => expect(plaid.handler.open).toHaveBeenCalled());
    await plaid.success();
    expect(await screen.findByText("card: 7 transactions")).toBeInTheDocument();
    expect(callsTo(calls, "POST /api/plaid/exchange")).toHaveLength(0);
    expect(callsTo(calls, "POST /api/accounts/pull")).toHaveLength(1);
  });

  it("closing Link there goes back to the app without a message", async () => {
    const plaid = fakePlaid();
    mockApi(appRoutes({ "GET /api/meta": META_PLAID }));
    arrive(pend());
    renderWithClient(<App />);
    await waitFor(() => expect(plaid.handler.open).toHaveBeenCalled());
    await plaid.exit(null);
    await screen.findByLabelText("Start date");
    expect(window.location.pathname).toBe("/");
    expect(screen.queryByRole("button", { name: "Dismiss message" })).toBeNull();
    expect(localStorage.getItem(PENDING_KEY)).toBeNull();
  });

  it("an error in Link there is shown in the app", async () => {
    const plaid = fakePlaid();
    mockApi(appRoutes({ "GET /api/meta": META_PLAID }));
    arrive(pend());
    renderWithClient(<App />);
    await waitFor(() => expect(plaid.handler.open).toHaveBeenCalled());
    await plaid.exit({ display_message: "Your bank rejected the login." });
    expect(await screen.findByText("Your bank rejected the login.")).toBeInTheDocument();
    expect(window.location.pathname).toBe("/");
  });

  it("with no pending link there is nothing to finish, and a way back", async () => {
    const plaid = fakePlaid();
    const fetchSpy = vi.fn();
    vi.stubGlobal("fetch", fetchSpy);
    arrive();
    renderWithClient(<App />);
    expect(await screen.findByText("There is no bank connection to finish.")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Back to the app" })).toHaveAttribute("href", "/");
    expect(plaid.create).not.toHaveBeenCalled();
    expect(fetchSpy).not.toHaveBeenCalled();
  });

  it("a stale pending link (past the link token's 4 hours) is not used, and is dropped", async () => {
    const plaid = fakePlaid();
    vi.stubGlobal("fetch", vi.fn());
    arrive(pend({ savedAt: Date.now() - 5 * 60 * 60 * 1000 }));
    renderWithClient(<App />);
    expect(await screen.findByText("There is no bank connection to finish.")).toBeInTheDocument();
    expect(plaid.create).not.toHaveBeenCalled();
    expect(localStorage.getItem(PENDING_KEY)).toBeNull();
  });

  it("an unreadable pending link counts as none", async () => {
    fakePlaid();
    vi.stubGlobal("fetch", vi.fn());
    arrive("{not json");
    renderWithClient(<App />);
    expect(await screen.findByText("There is no bank connection to finish.")).toBeInTheDocument();
  });

  it("says so, and keeps the pending link, when Plaid's script cannot load", async () => {
    vi.stubGlobal("fetch", vi.fn());
    vi.spyOn(document.head, "appendChild").mockImplementation((node) => {
      setTimeout(() => (node as HTMLScriptElement).onerror?.(new Event("error")), 0);
      return node;
    });
    arrive(pend());
    renderWithClient(<App />);
    expect(await screen.findByText("Could not load Plaid Link (blocked?)")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Back to the app" })).toBeInTheDocument();
    expect(localStorage.getItem(PENDING_KEY)).not.toBeNull(); // the link token is still good: try again later
  });

  it("is an ordinary page at any other address (no resume, no Plaid)", async () => {
    const plaid = fakePlaid();
    savePending(pend());
    mockApi(appRoutes({ "GET /api/meta": META_PLAID }));
    renderWithClient(<App />);
    await screen.findByLabelText("Start date");
    expect(plaid.create).not.toHaveBeenCalled();
    expect(localStorage.getItem(PENDING_KEY)).not.toBeNull();
  });
});
