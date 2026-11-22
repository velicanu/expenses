import { ApiError } from "../api";
import { friendly } from "../banner";

/** In-place state of a query: a filter that the API refuses (422) is explained where the data would be. */
export function QueryStatus({ query, empty }: { query: { isPending: boolean; isError: boolean; error: unknown }; empty?: string }) {
  if (query.isPending) return <p className="muted" role="status">Loading…</p>;
  if (query.isError) {
    const prefix = query.error instanceof ApiError && query.error.status === 422 ? "These filters can't be used: " : "";
    return (
      <p className="error" role="alert">
        {prefix}
        {friendly(query.error)}
      </p>
    );
  }
  return empty ? <p className="muted">{empty}</p> : null;
}
