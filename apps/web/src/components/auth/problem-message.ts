import { ApiError } from "@/lib/api/errors";

/** Codes whose message the API completes with something only it knows ("2 attempts left."). */
const WITH_DETAIL: readonly string[] = ["OTP_INVALID"];

/**
 * What to tell someone about a failed call: our message for the API's error code, or the general
 * one with the request's reference, which support can look up in the API's logs. For the codes in
 * `withDetail`, the API's detail follows our message.
 */
export function problemMessage(
  error: unknown,
  messages: Record<string, string>,
  withDetail: readonly string[] = WITH_DETAIL,
): string {
  const general = messages.generic ?? "";
  if (!(error instanceof ApiError)) return general;
  const known = messages[error.code];
  if (known === undefined) {
    return error.requestId === undefined ? general : `${general} (${error.requestId})`;
  }
  const detail = error.problem?.detail;
  return withDetail.includes(error.code) && detail ? `${known} ${detail}` : known;
}
