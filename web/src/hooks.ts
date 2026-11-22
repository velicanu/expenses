import { QueryClient, keepPreviousData, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, ApiError } from "./api";
import type { Group, SqlFilters } from "./types";

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
export const useAppState = () => useQuery({ queryKey: ["state"], queryFn: api.state, staleTime: Infinity });
export const useRules = () => useQuery({ queryKey: ["rules"], queryFn: api.rules });
export const useFiles = () => useQuery({ queryKey: ["files"], queryFn: api.files });
export const useAccounts = () => useQuery({ queryKey: ["accounts"], queryFn: api.accounts });

/** The old SQL text built from the sidebar form; also says when the description box is invalid. */
export const useSqlDefault = (filters: SqlFilters) =>
  useQuery({ queryKey: ["sqlDefault", filters], queryFn: () => api.sqlDefault(filters) });

/** The rows of the query (only needed while "Show data" is open). */
export const useSqlRun = (query: string | undefined, enabled: boolean) =>
  useQuery({
    queryKey: ["sqlRun", query],
    queryFn: () => api.sqlRun(query as string),
    enabled: enabled && !!query,
    placeholderData: keepPreviousData,
  });

/** Both charts, built by the server from the query. */
export const useFigures = (query: string | undefined, group: Group) =>
  useQuery({
    queryKey: ["figures", query, group],
    queryFn: () => api.figures(query as string, group),
    enabled: !!query,
    placeholderData: keepPreviousData,
  });

/** After anything that changes the data, the rules or the files: every view refetches (the old app reran the page). */
export function useRefreshAll() {
  const client = useQueryClient();
  return () => client.invalidateQueries();
}
