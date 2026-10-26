import { spawn } from "node:child_process";
import { createHmac } from "node:crypto";
import path from "node:path";

import { expect, type Page } from "@playwright/test";

import { codeSentTo, logLength, newMobile } from "./sign-in-codes";

/** scripts/e2e-manage.sh: operator commands against the tests' API (Playwright runs in apps/web). */
const MANAGE = path.resolve(process.cwd(), "../../scripts/e2e-manage.sh");

export interface StaffAccount {
  mobile: string;
  /** The authenticator's setup key, as an operator reads it out (base32). */
  secret: string;
}

/**
 * Run an operator command. `answer` sees the output so far and may return a line to type in,
 * once, as a person at the prompt would.
 */
function manage(args: string[], answer?: (output: string) => string | undefined): Promise<string> {
  return new Promise((resolve, reject) => {
    const child = spawn(MANAGE, args, { stdio: ["pipe", "pipe", "pipe"] });
    let output = "";
    let answered = false;
    child.stdout.on("data", (chunk: Buffer) => {
      output += chunk.toString();
      const line = answered || answer === undefined ? undefined : answer(output);
      if (line !== undefined) {
        answered = true;
        child.stdin.write(`${line}\n`);
      }
    });
    child.stderr.on("data", (chunk: Buffer) => {
      output += chunk.toString();
    });
    child.on("error", reject);
    child.on("close", (status) => {
      if (status === 0) resolve(output);
      else reject(new Error(`manage ${args.join(" ")} failed (${String(status)}):\n${output}`));
    });
  });
}

function base32(text: string): Buffer {
  const alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZ234567";
  // Base32 is ASCII, so code units are characters here.
  const bits = Array.from(text.replace(/[\s=]/gu, "").toUpperCase(), (character) =>
    alphabet.indexOf(character).toString(2).padStart(5, "0"),
  ).join("");
  const bytes = [];
  for (let index = 0; index + 8 <= bits.length; index += 8) {
    bytes.push(Number.parseInt(bits.slice(index, index + 8), 2));
  }
  return Buffer.from(bytes);
}

/** The authenticator's code for a 30-second step (RFC 6238, as the API checks it). */
export function totp(secret: string, step = Math.floor(Date.now() / 30_000)): string {
  const counter = Buffer.alloc(8);
  counter.writeBigUInt64BE(BigInt(step));
  const digest = createHmac("sha1", base32(secret)).update(counter).digest();
  const offset = (digest.at(-1) ?? 0) & 0x0f;
  return String((digest.readUInt32BE(offset) & 0x7fffffff) % 1_000_000).padStart(6, "0");
}

/** A new staff member with these roles and an authenticator app, as an operator sets one up. */
export async function newStaff(roles: readonly string[], name = "Test Ops"): Promise<StaffAccount> {
  const mobile = newMobile();
  await manage([
    "staff",
    "add",
    mobile,
    ...roles.flatMap((role) => ["--role", role]),
    "--name",
    name,
  ]);
  let secret = "";
  await manage(["staff", "enrol-authenticator", mobile], (output) => {
    // The setup key comes in groups of four on the line after the instructions.
    const key = /setup key[^\n]*\n\s+([A-Z2-7 ]+)\n/u.exec(output)?.[1];
    if (key === undefined || !output.includes("Code from the app")) return undefined;
    secret = key.replaceAll(" ", "");
    return totp(secret);
  });
  return { mobile, secret };
}

/**
 * Sign in on the staff sign-in page without Google: the phone code, consent the first time, then
 * the authenticator. Its code is the next step's: the enrolment just used this step's, and each
 * step's code works once (the API allows one step of clock drift).
 */
export async function signInAsStaff(page: Page, account: StaffAccount): Promise<void> {
  await page.getByLabel("Mobile number", { exact: true }).fill(account.mobile);
  const from = await logLength();
  await page.getByRole("button", { name: "Send code" }).click();
  await page
    .getByLabel("Six-digit code", { exact: true })
    .fill(await codeSentTo(account.mobile, { after: from }));
  await page.getByRole("button", { name: "Continue" }).click();
  const consent = page.getByRole("heading", { name: "Before we create your account" });
  const authenticator = page.getByRole("heading", { name: "Your authenticator code" });
  await expect(consent.or(authenticator)).toBeVisible();
  if (await consent.isVisible()) {
    await page.getByRole("checkbox", { name: /^I agree/ }).check();
    await page.getByRole("button", { name: "Agree and continue" }).click();
  }
  await expect(authenticator).toBeVisible();
  await page
    .getByLabel("Authenticator code", { exact: true })
    .fill(totp(account.secret, Math.floor(Date.now() / 30_000) + 1));
  await page.getByRole("button", { name: "Sign in to staff tools" }).click();
}
