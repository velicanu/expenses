import { useEffect, useRef, useState } from "react";
import { api } from "../api";
import { friendly } from "../banner";
import { pullOutcome, type Outcome } from "../plaidLink";

/**
 * Where the hand-login page sends you when you tap Done (/?refresh=venmo-dragos): you have just logged in to that
 * account, so fetch it now, with your own login to this app, and show the result on the page.
 */
export function LoginReturn({ alias, onDone }: { alias: string; onDone: (outcome: Outcome) => void }) {
  const started = useRef(false); // StrictMode runs effects twice: one fetch, one visit to the bank
  const [slow, setSlow] = useState(false);

  useEffect(() => {
    if (started.current) return;
    started.current = true;
    const later = setTimeout(() => setSlow(true), 15000);
    api
      .pull({ only: alias, after_login: true })
      .then((result) => onDone(pullOutcome(result)))
      .catch((e) => onDone({ kind: "error", text: `${alias}: ${friendly(e)}` }))
      .finally(() => clearTimeout(later));
  }, [alias, onDone]);

  return (
    <main className="oauth-return" aria-live="polite">
      <p className="spinner">Fetching {alias}…</p>
      {slow && (
        <p className="muted">
          Still working: it checks the login, then downloads the recent statements. That is usually under a minute; an account's very first fetch can take a couple of minutes.
        </p>
      )}
    </main>
  );
}
