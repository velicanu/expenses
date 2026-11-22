import { QueryClient, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, ApiError } from "./api";
import type { Filters } from "./filters";
import type { Bin, Order, SortKey } from "./types";

export function makeQueryClient(): QueryClient {
  return new QueryClient({
    defaultOptions: {
      queries: {
        staleTime: 15_000,
        refetchOnWindowFocus: false,
        // a 4xx is the answer, not a hiccup; one retry for network and 5xx errors
        retry: (count, err) => !(err instanceof ApiError && err.status < 500) && count < 1,
      },
    },
  });
}

export const useMe = () => useQuery({ queryKey: ["me"], queryFn: api.me, staleTime: Infinity });
export const useMeta = () => useQuery({ queryKey: ["meta"], queryFn: api.meta });
export const useByCategory = (f: Filters) => useQuery({ queryKey: ["summary", "category", f], queryFn: () => api.byCategory(f) });
export const useOverTime = (f: Filters, bin: Bin) =>
  useQuery({ queryKey: ["summary", "time", f, bin], queryFn: () => api.overTime(f, bin) });
export const useTransactions = (f: Filters, sort: SortKey, order: Order, page: number, limit: number) =>
  useQuery({
    queryKey: ["transactions", f, sort, order, page, limit],
    queryFn: () => api.transactions(f, sort, order, page * limit, limit),
    placeholderData: (previous) => previous,
  });
export const useRules = () => useQuery({ queryKey: ["rules"], queryFn: api.rules });
export const useFiles = () => useQuery({ queryKey: ["files"], queryFn: api.files });
export const useAccounts = () => useQuery({ queryKey: ["accounts"], queryFn: api.accounts });

/** After anything that changes the data: every view that shows transactions or totals refetches. */
export function useRefreshData() {
  const client = useQueryClient();
  return () =>
    Promise.all(["transactions", "summary", "meta", "files", "accounts"].map((key) => client.invalidateQueries({ queryKey: [key] })));
}
