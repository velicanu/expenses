const money = new Intl.NumberFormat("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });

/** 1234.5 -> "1,234.50", -3 -> "-3.00". Signs are shown as the API sends them. */
export function formatMoney(n: number): string {
  return money.format(n);
}

export function formatBytes(n: number): string {
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  return `${(n / (1024 * 1024)).toFixed(1)} MB`;
}

export function formatUnix(seconds: number): string {
  return new Date(seconds * 1000).toISOString().slice(0, 10);
}

/** Today as YYYY-MM-DD in the browser's timezone. */
export function today(): string {
  const d = new Date();
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
}

export function titleCase(s: string): string {
  return s.trim().replace(/\w\S*/g, (w) => w[0].toUpperCase() + w.slice(1).toLowerCase());
}
