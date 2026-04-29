export const REQUEST_ID_HEADER = "X-SKU-Lens-Request-Id";
const BROWSER_DEBUG_KEY = "sku-lens:debug";
const FIELD_ORDER = [
  "request_id",
  "response_request_id",
  "job_id",
  "method",
  "path",
  "status",
  "duration_ms",
  "route",
  "queue_name",
  "shop_domain",
  "shop_id",
  "product_id",
  "window",
  "stat_date",
  "channel",
  "accepted",
  "enqueued",
  "processed",
  "restored",
  "event_count",
  "session_id",
  "visitor_id",
  "error",
  "message",
] as const;

type LogLevel = "debug" | "info" | "warn" | "error";
type LogFields = Record<string, unknown>;

export function generateRequestId(): string {
  if (typeof globalThis.crypto?.randomUUID === "function") {
    return globalThis.crypto.randomUUID();
  }

  return `${Date.now()}-${Math.random().toString(36).slice(2, 10)}`;
}

export function requestIdFromHeaders(headers: Headers): string {
  return headers.get(REQUEST_ID_HEADER) ?? generateRequestId();
}

export function browserDebugEnabled(): boolean {
  if (typeof window === "undefined") {
    return false;
  }

  try {
    return window.localStorage.getItem(BROWSER_DEBUG_KEY) === "1";
  } catch {
    return false;
  }
}

export function logServerEvent(level: LogLevel, event: string, fields: LogFields): void {
  emit(level, formatLogLine(level, "web", "api", event, fields));
}

export function logSsrEvent(level: LogLevel, event: string, fields: LogFields): void {
  emit(level, formatLogLine(level, "web", "ssr", event, fields));
}

export function logBrowserEvent(level: LogLevel, event: string, fields: LogFields): void {
  if (!browserDebugEnabled()) {
    return;
  }

  emit(level, formatLogLine(level, "web", "browser", event, fields));
}

export function formatLogLine(
  level: LogLevel,
  app: string,
  surface: string,
  event: string,
  fields: LogFields,
): string {
  const timestamp = new Date().toISOString();
  const normalized = Object.fromEntries(
    Object.entries(fields).filter(([, value]) => value !== undefined && value !== null && value !== ""),
  );

  const orderedEntries: Array<[string, unknown]> = [];
  const remaining = new Map(Object.entries(normalized));

  for (const key of FIELD_ORDER) {
    if (remaining.has(key)) {
      orderedEntries.push([key, remaining.get(key)]);
      remaining.delete(key);
    }
  }

  for (const key of Array.from(remaining.keys()).sort()) {
    orderedEntries.push([key, remaining.get(key)]);
  }

  const segments = orderedEntries.map(([key, value]) => `${key}=${formatValue(value)}`);
  return `${timestamp} ${levelLabel(level)} [${app}][${surface}][${event}]${segments.length ? ` ${segments.join(" ")}` : ""}`;
}

function emit(level: LogLevel, line: string): void {
  const logger =
    level === "debug" ? console.debug :
    level === "info" ? console.info :
    level === "warn" ? console.warn :
    console.error;
  logger(line);
}

function levelLabel(level: LogLevel): string {
  return level.toUpperCase();
}

function formatValue(value: unknown): string {
  if (typeof value === "boolean" || typeof value === "number" || typeof value === "bigint") {
    return String(value);
  }

  if (value instanceof Date) {
    return value.toISOString();
  }

  if (typeof value === "object") {
    return JSON.stringify(value);
  }

  const text = String(value);
  if (!text) {
    return '""';
  }

  if (/\s|["'=]/.test(text)) {
    return JSON.stringify(text);
  }

  return text;
}
