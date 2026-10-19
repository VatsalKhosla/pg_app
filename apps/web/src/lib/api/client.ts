import { type ApiClient, createApiClient } from "@pg-platform/api-client";

import { ApiError } from "./errors";

export interface WebApiClientOptions {
  baseUrl: URL | string;
  /** Requests that take longer are aborted and reported as API_TIMEOUT. */
  timeoutMs: number;
  headers?: Record<string, string>;
  credentials?: RequestCredentials;
  /** Replaces the global fetch (tests). */
  fetch?: typeof globalThis.fetch;
}

/**
 * The typed client with this app's defaults: nothing cached, every request bounded by a timeout.
 * Use `unwrap` to turn its results into data or an ApiError.
 */
export function createWebApiClient(options: WebApiClientOptions): ApiClient {
  const fetchImpl = options.fetch ?? globalThis.fetch;
  return createApiClient({
    baseUrl: String(options.baseUrl).replace(/\/+$/, ""),
    headers: options.headers,
    credentials: options.credentials,
    cache: "no-store",
    fetch: (request) => fetchWithTimeout(request, options.timeoutMs, fetchImpl),
  });
}

async function fetchWithTimeout(
  request: Request,
  timeoutMs: number,
  fetchImpl: typeof globalThis.fetch,
): Promise<Response> {
  // AbortSignal.any would do this, but Safari only has it from 17.4.
  const controller = new AbortController();
  const onCallerAbort = () => {
    controller.abort(request.signal.reason);
  };
  if (request.signal.aborted) onCallerAbort();
  request.signal.addEventListener("abort", onCallerAbort, { once: true });
  const timer = setTimeout(() => {
    controller.abort(new DOMException("The API didn't answer in time", "TimeoutError"));
  }, timeoutMs);
  try {
    // The signal goes in `init` rather than a copied Request: undici links a copy's signal to its
    // source only weakly.
    return await fetchImpl(request, { signal: controller.signal });
  } finally {
    clearTimeout(timer);
    request.signal.removeEventListener("abort", onCallerAbort);
  }
}

/** What openapi-fetch resolves to: data on success, an error otherwise, and the response. */
interface Result {
  data?: unknown;
  error?: unknown;
  response: Response;
}

/** The data of a call's success. Taken from the result type as it is, not inferred from both
 * branches of the union, which would add the error branch's `undefined` (and lose arrays). */
type SuccessData<R extends Result> = Exclude<R["data"], undefined>;

function isCancellation(cause: unknown): boolean {
  return cause instanceof DOMException && cause.name === "AbortError";
}

/**
 * The data of a successful call. Error responses and failed requests become an ApiError; a call
 * the caller cancelled rejects with its AbortError unchanged.
 */
export async function unwrap<R extends Result>(call: Promise<R>): Promise<SuccessData<R>> {
  let result: R;
  try {
    result = await call;
  } catch (cause) {
    if (isCancellation(cause)) throw cause;
    throw ApiError.fromFailure(cause);
  }
  // An error response with an empty body has no `error`, so check the status as well.
  if (result.response.ok && result.error === undefined) {
    // openapi-fetch sets `data` exactly when the response succeeded (undefined for a 204), but a
    // generic result type keeps TypeScript from narrowing the union on `error`.
    return result.data as SuccessData<R>;
  }
  throw ApiError.fromResponse(result.response, result.error);
}
