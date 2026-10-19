import { readFile } from "node:fs/promises";

import { API_LOG } from "./api-log";

interface LogLine {
  event?: string;
  phone?: string;
  code?: string;
}

/** A mobile number nobody else in the run uses: ten digits starting 6 to 9. */
export function newMobile(): string {
  const digits = Array.from({ length: 9 }, () => Math.floor(Math.random() * 10)).join("");
  return `9${digits}`;
}

/**
 * The newest sign-in code the API "sent" to `mobile`: the console sender logs it, with the number
 * masked to its last four digits (apps/api/src/app/modules/identity/adapters/console_otp.py).
 * Waits a little for the line to arrive.
 */
export async function codeSentTo(mobile: string, { after = 0 } = {}): Promise<string> {
  const lastFour = `******${mobile.slice(-4)}`;
  for (let attempt = 0; attempt < 50; attempt += 1) {
    const lines = (await readFile(API_LOG, "utf8")).split("\n").slice(after);
    for (const line of lines.reverse()) {
      if (!line.startsWith("{")) continue;
      const entry = JSON.parse(line) as LogLine;
      if (entry.event === "development sign-in code, not sent" && entry.phone === lastFour) {
        if (entry.code !== undefined) return entry.code;
      }
    }
    await new Promise((resolve) => setTimeout(resolve, 100));
  }
  throw new Error(`no sign-in code was logged for ${lastFour}`);
}

/** How many lines the API's log has now, to look only at what comes after. */
export async function logLength(): Promise<number> {
  return (await readFile(API_LOG, "utf8")).split("\n").length - 1;
}
