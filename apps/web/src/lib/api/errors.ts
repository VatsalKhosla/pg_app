import type { Schemas } from "@pg-platform/api-client";

export type ProblemDetail = Schemas["ProblemDetail"];
export type FieldError = Schemas["FieldError"];

/**
 * Codes for failures the API never reported itself: it couldn't be reached, didn't answer in time,
 * or answered without problem details. The API's own codes are in ARCHITECTURE §15.
 */
export const CLIENT_ERROR_CODES = {
  unreachable: "API_UNREACHABLE",
  timeout: "API_TIMEOUT",
  unexpected: "UNEXPECTED_RESPONSE",
} as const;

/** Whether `value` is an RFC 9457 problem as the API sends it (title, status and code at least). */
export function isProblemDetail(value: unknown): value is ProblemDetail {
  return (
    typeof value === "object" &&
    value !== null &&
    "title" in value &&
    typeof value.title === "string" &&
    "status" in value &&
    typeof value.status === "number" &&
    "code" in value &&
    typeof value.code === "string"
  );
}

interface ApiErrorInit {
  message: string;
  status: number;
  code: string;
  problem?: ProblemDetail | undefined;
  requestId?: string | undefined;
  cause?: unknown;
}

/** A failed API call: an error response from the API, or a request that never got one. */
export class ApiError extends Error {
  override readonly name = "ApiError";
  /** The HTTP status, or 0 when no response arrived. */
  readonly status: number;
  /** The API's stable error code, or one of CLIENT_ERROR_CODES. */
  readonly code: string;
  /** The problem details the API sent, if any. */
  readonly problem: ProblemDetail | undefined;
  /** Matches the API's log lines for this request. */
  readonly requestId: string | undefined;

  constructor({ message, status, code, problem, requestId, cause }: ApiErrorInit) {
    super(message, { cause });
    this.status = status;
    this.code = code;
    this.problem = problem;
    this.requestId = requestId;
  }

  /** Invalid inputs, to show next to the form fields they belong to. */
  get fieldErrors(): readonly FieldError[] {
    return this.problem?.errors ?? [];
  }

  static fromResponse(response: Response, body: unknown): ApiError {
    const requestId = response.headers.get("x-request-id") ?? undefined;
    if (isProblemDetail(body)) {
      return new ApiError({
        message: body.detail ?? body.title,
        status: response.status,
        code: body.code,
        problem: body,
        requestId: body.requestId ?? requestId,
      });
    }
    return new ApiError({
      message: `The API answered ${String(response.status)} without problem details`,
      status: response.status,
      code: CLIENT_ERROR_CODES.unexpected,
      requestId,
    });
  }

  static fromFailure(cause: unknown): ApiError {
    const timedOut = cause instanceof DOMException && cause.name === "TimeoutError";
    return new ApiError({
      message: timedOut ? "The API didn't answer in time" : "The API couldn't be reached",
      status: 0,
      code: timedOut ? CLIENT_ERROR_CODES.timeout : CLIENT_ERROR_CODES.unreachable,
      cause,
    });
  }
}
