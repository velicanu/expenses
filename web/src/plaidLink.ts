import { api } from "./api";
import { friendly } from "./banner";
import type { PendingLink, PullAccount, PullResult } from "./types";

/**
 * Plaid Link, in the browser. Link itself is Plaid's script, loaded from their CDN only when someone starts to
 * link or resume a connection (never bundled); the server makes the link token and keeps every access token.
 *
 * A bank that uses OAuth (Capital One, Chase, Wealthfront ...) takes the browser away from this page and sends
 * it back to /plaid-oauth. What the page needs to pick up where it left off is kept in localStorage meanwhile.
 */

export const PLAID_SCRIPT = "https://cdn.plaid.com/link/v2/stable/link-initialize.js";
export const PENDING_KEY = "plaid-link-pending";
export const LINK_TOKEN_LIFETIME_MS = 4 * 60 * 60 * 1000; // Plaid: a link token is valid for 4 hours
export const OAUTH_PATH = "/plaid-oauth";
export const ALIAS_RULE = "Use lowercase letters, digits and hyphens (up to 48), starting with a letter or digit.";
const ALIAS_RE = /^[a-z0-9][a-z0-9-]{0,47}$/;

export const validAlias = (alias: string) => ALIAS_RE.test(alias);

/** The old app's default start date: January 1 of this year. */
export const defaultStartDate = (now = new Date()) => `${now.getFullYear()}-01-01`;

// --- the bits of Plaid Link that are used (https://plaid.com/docs/link/web/) -------------------------

export interface PlaidLinkError {
  error_code?: string;
  error_message?: string;
  display_message?: string | null;
}

export interface PlaidHandler {
  open(): void;
  exit(options?: { force?: boolean }): void;
  destroy(): void;
}

export interface PlaidCreateOptions {
  token: string;
  receivedRedirectUri?: string;
  onSuccess(publicToken: string, metadata?: unknown): void;
  onExit(error: PlaidLinkError | null, metadata?: unknown): void;
  onEvent?(name: string, metadata?: unknown): void;
}

export interface PlaidGlobal {
  create(options: PlaidCreateOptions): PlaidHandler;
}

declare global {
  interface Window {
    Plaid?: PlaidGlobal;
  }
}

let loading: Promise<PlaidGlobal> | null = null;

/** Plaid's script, loaded once. A failed load can be retried. */
export function loadPlaid(): Promise<PlaidGlobal> {
  if (window.Plaid) return Promise.resolve(window.Plaid);
  if (loading) return loading;
  loading = new Promise<PlaidGlobal>((resolve, reject) => {
    const script = document.createElement("script");
    script.src = PLAID_SCRIPT;
    script.async = true;
    script.onload = () => (window.Plaid ? resolve(window.Plaid) : reject(new Error("Could not load Plaid Link (blocked?)")));
    script.onerror = () => reject(new Error("Could not load Plaid Link (blocked?)"));
    document.head.appendChild(script);
  }).then(
    (plaid) => {
      loading = null; // from here window.Plaid answers
      return plaid;
    },
    (e) => {
      loading = null; // a failed load can be retried
      throw e;
    },
  );
  return loading;
}

// --- the pending link --------------------------------------------------------------------------------

export function savePending(pending: PendingLink): void {
  localStorage.setItem(PENDING_KEY, JSON.stringify(pending));
}

export function clearPending(): void {
  localStorage.removeItem(PENDING_KEY);
}

/** The pending link, or null if there is none, it is garbled, or its link token has expired (cleared then). */
export function readPending(now = Date.now()): PendingLink | null {
  const raw = localStorage.getItem(PENDING_KEY);
  if (!raw) return null;
  try {
    const p = JSON.parse(raw) as Partial<PendingLink>;
    const ok =
      typeof p.link_token === "string" &&
      (p.mode === "new" || p.mode === "update") &&
      typeof p.alias === "string" &&
      typeof p.savedAt === "number" &&
      now - p.savedAt < LINK_TOKEN_LIFETIME_MS;
    if (ok) return p as PendingLink;
  } catch {
    /* garbled: dropped below */
  }
  clearPending();
  return null;
}

// --- outcomes ----------------------------------------------------------------------------------------

export interface Outcome {
  kind: "success" | "error" | "info";
  text: string;
  reconnect?: string[]; // aliases whose bank login expired: offer a Reconnect button for each
  login?: { alias: string; url: string }[]; // browser-pulled accounts whose saved login lapsed: link to the hand login
}

export function pipelineLine(r: PullResult["pipeline"] | null): string | null {
  if (!r) return null;
  return r.ran ? `Pipeline ran in ${r.seconds} s: ${r.count} transactions.` : "Nothing to process yet: no card files were found.";
}

const failed = (a: PullAccount): a is Extract<PullAccount, { error: string }> => "error" in a;

const skipped = (a: PullAccount): a is Extract<PullAccount, { skipped: string }> => "skipped" in a;
const loginNeeded = (a: PullAccount): a is Extract<PullAccount, { login_needed: string }> => "login_needed" in a;

export function pullLine(r: PullResult): string {
  if (r.accounts.length === 0) return "No linked accounts to pull.";
  return r.accounts
    .map((a) =>
      failed(a)
        ? `${a.alias}: ${a.error}`
        : skipped(a)
          ? `${a.alias}: ${a.skipped}`
          : loginNeeded(a)
            ? `${a.alias}: ${a.login_needed}`
            : `${a.alias}: ${a.pulled} transactions${a.auto_login === "ok" ? " (logged in automatically)" : ""}`,
    )
    .join("; ");
}

/** What Refresh data says, including which accounts need a Reconnect. */
export function pullOutcome(r: PullResult): Outcome {
  const bad = r.accounts.filter(failed);
  // an account whose saved login lapsed is information, not a failure: the accounts whose login persists were pulled
  const login = r.accounts.flatMap((a) => (loginNeeded(a) && a.login_url ? [{ alias: a.alias, url: a.login_url }] : []));
  return {
    kind: bad.length ? "error" : login.length ? "info" : "success",
    text: [pullLine(r), pipelineLine(r.pipeline)].filter(Boolean).join(" "),
    reconnect: bad.filter((a) => a.needs_reconnect).map((a) => a.alias),
    ...(login.length ? { login } : {}), // only when there is a hand login to link to
  };
}

/** Plaid's own wording for why Link ended with an error. */
export const exitText = (e: PlaidLinkError) =>
  e.display_message || e.error_message || e.error_code || "Plaid Link ended with an error.";

/** Link handed back a public token: make it a linked account (new), or refresh the reconnected one (update). */
export async function finishSuccess(pending: PendingLink, publicToken: string): Promise<Outcome> {
  try {
    if (pending.mode === "update") {
      clearPending();
      return pullOutcome(await api.pull());
    }
    const linked = await api.exchange({
      public_token: publicToken,
      alias: pending.alias,
      ...(pending.start_date ? { start_date: pending.start_date } : {}),
    });
    clearPending();
    return {
      kind: "success",
      text: `Linked ${linked.institution ?? linked.alias} as ${linked.alias}. Run Refresh data to pull transactions.`,
    };
  } catch (e) {
    return { kind: "error", text: friendly(e) };
  }
}

/**
 * Opens Plaid Link for `pending`. `onDone` gets the outcome once, or null if the person just closed Link.
 * `receivedRedirectUri` is only for resuming after a bank's OAuth login.
 */
export function openLink(plaid: PlaidGlobal, pending: PendingLink, onDone: (o: Outcome | null) => void, receivedRedirectUri?: string): void {
  let finished = false;
  const done = (o: Outcome | null) => {
    if (finished) return;
    finished = true;
    onDone(o);
  };
  const handler = plaid.create({
    token: pending.link_token,
    ...(receivedRedirectUri ? { receivedRedirectUri } : {}),
    onSuccess: (publicToken) => {
      void finishSuccess(pending, publicToken).then((o) => {
        handler.destroy();
        done(o);
      });
    },
    onExit: (error) => {
      clearPending();
      handler.destroy();
      done(error ? { kind: "error", text: exitText(error) } : null);
    },
  });
  handler.open();
}

/** Starts a link (alias + start date for a new bank) or a reconnect (the alias of a linked one). */
export async function beginLink(request: { alias: string; startDate: string | null; reconnect: boolean }, onDone: (o: Outcome | null) => void): Promise<void> {
  const token = await api.linkToken(request.reconnect ? request.alias : undefined);
  const plaid = await loadPlaid();
  const pending: PendingLink = {
    link_token: token.link_token,
    mode: token.mode,
    alias: request.alias,
    start_date: token.mode === "new" ? request.startDate : null,
    savedAt: Date.now(),
  };
  savePending(pending); // before Link opens: an OAuth bank leaves this page
  openLink(plaid, pending, onDone);
}

/** The /plaid-oauth page: pick up the pending link where the bank's login left it. */
export async function resumeLink(onDone: (o: Outcome | null) => void): Promise<boolean> {
  const pending = readPending();
  if (!pending) return false;
  const plaid = await loadPlaid();
  openLink(plaid, pending, onDone, window.location.href);
  return true;
}

