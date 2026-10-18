/**
 * Masking personal data before it leaves the browser or the web server (error reports and
 * analytics). Phone numbers are masked to their last four digits (CLAUDE.md, ARCHITECTURE §17).
 *
 * The pattern is the API's (apps/api/src/app/core/pii.py), so both sides mask the same things:
 * international numbers (+91 98765 43210) and Indian mobile numbers without the plus sign
 * (919876543210, 98765 43210, 09876543210). Digits glued to letters or to more digits (ids,
 * hashes, longer numbers) are left alone.
 */
const PHONE = /(?<![\w+])(?:\+\d[\d -]{8,16}\d|(?:91[ -]?|0)?[6-9]\d{4}[ -]?\d{5})(?!\w)/g;

export function maskPhoneNumbers(text: string): string {
  return text.replace(PHONE, (match) => `******${match.replace(/\D/g, "").slice(-4)}`);
}

function maskValue(value: unknown): unknown {
  if (typeof value === "string") {
    return maskPhoneNumbers(value);
  }
  if (Array.isArray(value)) {
    return value.map(maskValue);
  }
  if (value !== null && typeof value === "object") {
    return Object.fromEntries(Object.entries(value).map(([key, item]) => [key, maskValue(item)]));
  }
  return value;
}

/** A copy of `value` with every phone number masked, looking inside objects and arrays. */
export function maskPii<T>(value: T): T {
  // maskValue keeps the shape and only rewrites strings, so the copy has the same type.
  return maskValue(value) as T;
}
