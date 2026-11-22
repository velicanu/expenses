// Hand-written from ../openapi.json (the API is small; no codegen).

export interface Me {
  user: string;
  email: string;
}

export interface Meta {
  min_date: string | null;
  max_date: string | null;
  count: number;
  categories: string[];
  sources: string[];
  colors: Record<string, string>;
  plaid_configured: boolean;
}

export interface Transaction {
  pk: string;
  date: string | null; // YYYY-MM-DD
  description: string | null;
  amount: number;
  category: string | null;
  source: string | null;
  source_file: string | null;
  edited: boolean;
}

export interface TransactionPage {
  total: number;
  sum: number;
  rows: Transaction[];
}

export interface TransactionUpdate {
  category?: string;
  description?: string;
  amount?: number;
  date?: string;
}

export interface TransactionCreate {
  date: string;
  description: string;
  amount: number;
  category: string;
}

export interface ByCategory {
  total: number;
  categories: { category: string; amount: number }[];
}

export interface OverTime {
  bin: "year" | "month" | "week" | "day";
  categories: string[];
  periods: { period: string; total: number; values: Record<string, number> }[];
}

export type Bin = "auto" | "year" | "month" | "week" | "day";

export interface Rules {
  description: Record<string, string>;
  category: Record<string, string>;
  new_categories: Record<string, string>;
}

export interface RawFile {
  name: string;
  size: number;
  modified: number; // unix seconds
}

export interface PipelineResult {
  ran: boolean;
  seconds: number;
  count: number;
}

export interface UploadResult {
  saved: string[];
  failed: string[];
  pipeline: PipelineResult | null;
}

export interface Account {
  alias: string;
  institution: string | null;
  start_date: string | null;
}

export interface PullResult {
  accounts: ({ alias: string; pulled: number } | { alias: string; error: string })[];
  pipeline: PipelineResult | null;
}

export type SortKey = "date" | "amount" | "category" | "description" | "source";
export type Order = "asc" | "desc";
