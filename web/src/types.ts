// Hand-written against the server's API (see ../openapi.json for the older endpoints).

export interface Me {
  user: string;
  email: string;
}

export interface Meta {
  min_date: string | null; // the data's own range, YYYY-MM-DD
  max_date: string | null;
  count: number;
  categories: string[]; // data + defaults + new categories: what a transaction can be set to
  data_categories: string[]; // categories present in the data, sorted
  sources: string[];
  colors?: Record<string, string>; // ignored: the server colors the charts
  plaid_configured: boolean;
}

/** The saved filters (config.json min_date / max_date / "categories in" / "categories not in" / show_sql / rules_button). */
export interface AppState {
  min_date: string | null;
  max_date: string | null;
  categories_in: string[];
  categories_not_in: string[];
  show_sql: boolean;
  rules_button: boolean;
}

/** What the sidebar form holds: the old app's widgets. */
export interface SqlFilters {
  start: string | null;
  end: string | null;
  category_in: string[];
  category_not_in: string[];
  description: string;
  sources: string[];
}

export interface SqlDefault {
  query: string;
  description_warning: string | null;
}

export type Cell = string | number | null;

export interface SqlResult {
  columns: string[];
  rows: Cell[][];
  count: number;
}

export interface Figure {
  data: unknown[];
  layout: Record<string, unknown>;
}

export type Group = "auto" | "year" | "month" | "week" | "day";

export interface FiguresResponse {
  rows: number;
  category: {
    message: string | null;
    total: number;
    table: { category: string; amount: number }[];
    figure: Figure | null;
  };
  over_time: {
    message: string | null;
    group: string;
    figure: Figure | null;
  };
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
