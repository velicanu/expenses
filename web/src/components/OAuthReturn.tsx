import { useEffect, useRef, useState } from "react";
import { friendly } from "../banner";
import { resumeLink, type Outcome } from "../plaidLink";

/**
 * The page Plaid returns to after a bank's OAuth login (/plaid-oauth?oauth_state_id=...). It picks up the link
 * that was pending when the browser left, reopens Plaid Link with the address it came back on, and hands the
 * outcome on; the app then goes back to "/" and shows it.
 */
export function OAuthReturn({ onDone }: { onDone: (outcome: Outcome | null) => void }) {
  const started = useRef(false); // StrictMode runs effects twice: Link must be created and opened once
  const [state, setState] = useState<"working" | "none" | "error">("working");
  const [error, setError] = useState("");

  useEffect(() => {
    if (started.current) return;
    started.current = true;
    resumeLink(onDone)
      .then((found) => {
        if (!found) setState("none");
      })
      .catch((e) => {
        setError(friendly(e));
        setState("error");
      });
  }, [onDone]);

  return (
    <main className="oauth-return" aria-live="polite">
      {state === "working" && <p className="spinner">Finishing the bank connection…</p>}
      {state === "none" && <p>There is no bank connection to finish.</p>}
      {state === "error" && (
        <p className="alert error" role="alert">
          {error}
        </p>
      )}
      {state !== "working" && <a href="/">Back to the app</a>}
    </main>
  );
}
