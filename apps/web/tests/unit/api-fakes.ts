import { vi } from "vitest";

/** A fetch that answers with `respond` and remembers the requests it was given. */
export function fakeFetch(respond: (request: Request) => Response | Promise<Response>) {
  const requests: Request[] = [];
  const fetch = vi.fn((input: RequestInfo | URL) => {
    const request = input instanceof Request ? input : new Request(input);
    requests.push(request);
    return Promise.resolve(respond(request));
  });
  return { fetch, requests };
}

export function jsonResponse(body: unknown, init: ResponseInit = {}): Response {
  const headers = new Headers(init.headers);
  headers.set("content-type", "application/json");
  return new Response(JSON.stringify(body), { ...init, headers });
}

export function problemResponse(status: number, problem: Record<string, unknown>): Response {
  return new Response(JSON.stringify({ type: "about:blank", status, ...problem }), {
    status,
    headers: { "content-type": "application/problem+json", "x-request-id": "req-from-header" },
  });
}

/** A fetch that never answers: it rejects only when the call's signal aborts. */
export function hangingFetch() {
  const fetch = (_input: RequestInfo | URL, init?: RequestInit) =>
    new Promise<Response>((_, reject) => {
      const signal = init?.signal;
      signal?.addEventListener("abort", () => {
        reject(signal.reason as Error);
      });
    });
  return { fetch };
}
