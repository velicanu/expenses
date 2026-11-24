import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { StrictMode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { App } from "./App";
import { appRoutes, callsTo, jsonResponse, mockApi, renderWithClient } from "./test-utils";

beforeEach(() => window.history.replaceState(null, "", "/"));
afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
  window.history.replaceState(null, "", "/");
});

const arrive = (alias = "venmo-dragos") => window.history.pushState(null, "", `/?refresh=${alias}`);
const pulled = (n: number) => ({ accounts: [{ alias: "venmo-dragos", pulled: n, months: 2 }], pipeline: { ran: true, seconds: 1.2, count: 12190 } });

describe("arriving from the hand-login page's Done (/?refresh=<account>)", () => {
  it("fetches just that account as a fresh login, then shows the app with the result", async () => {
    const calls = mockApi(appRoutes({ "POST /api/accounts/pull": pulled(14) }));
    arrive();
    renderWithClient(<App />);
    expect(screen.getByText("Fetching venmo-dragos…")).toBeInTheDocument();
    expect(screen.queryByLabelText("Sidebar")).toBeNull(); // only the fetch, no page behind it yet
    expect(await screen.findByText(/venmo-dragos: 14 transactions/)).toBeInTheDocument();
    expect(callsTo(calls, "POST /api/accounts/pull")).toHaveLength(1);
    expect(callsTo(calls, "POST /api/accounts/pull")[0].body).toEqual({ only: "venmo-dragos", after_login: true });
    await screen.findByLabelText("Start date"); // the normal page is up, with the result in its banner
    expect(window.location.search).toBe(""); // ?refresh is gone: a reload must not fetch again
    expect(screen.queryByText("Fetching venmo-dragos…")).toBeNull();
  });

  it("fetches once even under React StrictMode's double effects (one visit to the bank)", async () => {
    const calls = mockApi(appRoutes({ "POST /api/accounts/pull": pulled(0) }));
    arrive();
    renderWithClient(
      <StrictMode>
        <App />
      </StrictMode>,
    );
    await screen.findByText(/venmo-dragos: 0 transactions/);
    await new Promise((r) => setTimeout(r, 30));
    expect(callsTo(calls, "POST /api/accounts/pull")).toHaveLength(1);
  });

  it("says so, with the link, when Done was tapped before the login worked", async () => {
    mockApi(
      appRoutes({
        "POST /api/accounts/pull": {
          accounts: [{ alias: "venmo-dragos", login_needed: "Venmo is asking for a login; log in by hand to fetch it", login_url: "https://fetch.velicanu.com/login?account=venmo-dragos" }],
          pipeline: null,
        },
      }),
    );
    arrive();
    renderWithClient(<App />);
    expect(await screen.findByText(/venmo-dragos: Venmo is asking for a login/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Log in to venmo-dragos by hand" })).toHaveAttribute("href", "https://fetch.velicanu.com/login?account=venmo-dragos");
    expect(screen.queryByRole("alert")).toBeNull();
  });

  it("shows a failed fetch as an error on the page instead of leaving the spinner", async () => {
    mockApi(appRoutes({ "POST /api/accounts/pull": () => jsonResponse({ detail: "a pull or rebuild is already running" }, 409) }));
    arrive();
    renderWithClient(<App />);
    expect(await screen.findByText(/venmo-dragos: a pull or rebuild is already running/)).toBeInTheDocument();
    await screen.findByLabelText("Start date");
    expect(screen.queryByText("Fetching venmo-dragos…")).toBeNull();
  });

  it("the result banner can be dismissed", async () => {
    mockApi(appRoutes({ "POST /api/accounts/pull": pulled(3) }));
    arrive();
    renderWithClient(<App />);
    await screen.findByText(/venmo-dragos: 3 transactions/);
    await userEvent.click(await screen.findByRole("button", { name: "Dismiss message" }));
    await waitFor(() => expect(screen.queryByText(/venmo-dragos: 3 transactions/)).toBeNull());
  });

  it("says what is going on if the fetch is slow, without claiming a year of data", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    try {
      mockApi(appRoutes({ "POST /api/accounts/pull": () => new Promise<Response>(() => {}) })); // never answers
      arrive();
      renderWithClient(<App />);
      expect(screen.getByText("Fetching venmo-dragos…")).toBeInTheDocument();
      expect(screen.queryByText(/Still working/)).toBeNull(); // not at first
      await vi.advanceTimersByTimeAsync(16000);
      const hint = await screen.findByText(/Still working/);
      expect(hint).toHaveTextContent("checks the login, then downloads the recent statements");
      expect(hint.textContent).not.toMatch(/year/i);
    } finally {
      vi.useRealTimers();
    }
  });

  it("the ordinary page, without ?refresh, fetches nothing on load", async () => {
    const calls = mockApi(appRoutes({}));
    renderWithClient(<App />);
    await screen.findByLabelText("Start date");
    expect(callsTo(calls, "POST /api/accounts/pull")).toHaveLength(0);
  });
});
