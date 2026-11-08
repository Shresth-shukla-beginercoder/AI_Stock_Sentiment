import axios, { AxiosError, type AxiosRequestConfig } from "axios";

/**
 * Centralized API client.
 *
 * - Same-origin base "/api" in production (Nginx proxies to the backend);
 *   Vite dev proxy mirrors that. No host, port or secret is ever baked in.
 * - The admin key is attached ONLY to admin-protected calls, via
 *   withAdminKey() — it is never logged and never persisted by this module.
 */
const client = axios.create({
  baseURL: "/api",
  timeout: 15_000,
});

export { client };

export class ApiHttpError extends Error {
  readonly httpStatus: number | null;
  readonly body: unknown;

  constructor(httpStatus: number | null, body: unknown, message: string) {
    super(message);
    this.name = "ApiHttpError";
    this.httpStatus = httpStatus;
    this.body = body;
  }

  /** The stable error code from the backend's single error envelope, if any. */
  get code(): string {
    const b = this.body as { error?: { code?: string } } | undefined;
    return b?.error?.code ?? "network_error";
  }
}

/** Unwrap an axios error into our ApiHttpError with a human-readable message. */
export function normalizeAxiosError(err: AxiosError): ApiHttpError {
  const status = err.response?.status ?? null;
  const body = err.response?.data;
  const msg =
    status === null
      ? "Backend unreachable (network error)"
      : err.message || `HTTP ${status}`;
  return new ApiHttpError(status, body, msg);
}

export type { AxiosRequestConfig };
