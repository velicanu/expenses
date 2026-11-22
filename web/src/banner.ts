import { useSyncExternalStore } from "react";
import { ApiError } from "./api";

let message: string | null = null;
const listeners = new Set<() => void>();
const emit = () => listeners.forEach((l) => l());

export function showError(err: unknown): void {
  message = friendly(err);
  emit();
}

export function clearError(): void {
  message = null;
  emit();
}

export function useBanner(): string | null {
  return useSyncExternalStore(
    (l) => {
      listeners.add(l);
      return () => listeners.delete(l);
    },
    () => message,
  );
}

/** The API's own message, plus what to do about the cases a person can fix. */
export function friendly(err: unknown): string {
  if (err instanceof ApiError) {
    if (err.status === 409 && /no data/i.test(err.message)) return "There is no data yet. Upload a CSV first (Inputs, then upload data).";
    return err.message;
  }
  return err instanceof Error ? err.message : "Something went wrong.";
}
