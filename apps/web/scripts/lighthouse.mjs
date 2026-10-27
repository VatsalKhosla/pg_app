// `make lighthouse`: Lighthouse's mobile audit (its default: a mid-range phone on slow 4G) of the
// home page, served by a production build. Fails unless every category scores at least 90
// (BUILD_PLAN 0.5). Scores vary from run to run, so it audits three times (LIGHTHOUSE_RUNS), each
// in a fresh browser, and judges the median, as Lighthouse CI does. The median run's reports land
// in test-results/lighthouse/.
//
// `make lighthouse-pg` audits a sample PG's page instead (LIGHTHOUSE_PATH), at 85 (BUILD_PLAN
// 3.4: LIGHTHOUSE_MIN_SCORE), against the browser tests' API (scripts/lighthouse-pg.sh).
//
// Lighthouse drives Playwright's Chromium (installed by `make setup`) over the DevTools protocol.
import { spawn } from "node:child_process";
import { once } from "node:events";
import { mkdir, mkdtemp, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { fileURLToPath } from "node:url";

import { chromium } from "@playwright/test";
import lighthouse from "lighthouse";

const minimumScore = Number(process.env.LIGHTHOUSE_MIN_SCORE ?? "0.9");
const page = process.env.LIGHTHOUSE_PATH ?? "/";
const reportName = process.env.LIGHTHOUSE_REPORT ?? "home";
const runs = Number(process.env.LIGHTHOUSE_RUNS ?? "3");
const timeLimitMs = 10 * 60_000;
const appPort = Number(process.env.LIGHTHOUSE_APP_PORT ?? "3200");
const debuggingPort = Number(process.env.LIGHTHOUSE_DEBUGGING_PORT ?? "9333");
const origin = `http://127.0.0.1:${appPort}/`;
const url = new URL(page, origin).toString();
const debuggingUrl = `http://127.0.0.1:${debuggingPort}/json/version`;
const reportDir = fileURLToPath(new URL("../test-results/lighthouse/", import.meta.url));

/** Processes and browser profiles to remove however the script ends. */
const running = new Set();
const profiles = new Set();

async function stop(child) {
  running.delete(child);
  if (child.exitCode !== null || child.signalCode !== null) return;
  const exited = once(child, "exit");
  child.kill();
  await exited;
}

async function removeProfile(profile) {
  // Called only after the browser has exited: Chromium writes to its profile until then.
  await rm(profile, { recursive: true, force: true, maxRetries: 5, retryDelay: 200 });
  profiles.delete(profile);
}

async function cleanUp() {
  await Promise.all([...running].map(stop));
  await Promise.all([...profiles].map(removeProfile));
}

function fail(message) {
  console.error(`lighthouse: ${message}`);
  process.exitCode = 1;
}

async function responds(target) {
  try {
    return (await fetch(target)).ok;
  } catch {
    return false;
  }
}

/** Wait until `target` answers, failing early if the process that should serve it has exited. */
async function waitFor(target, child, what) {
  const deadline = Date.now() + 60_000;
  while (Date.now() < deadline) {
    if (child.exitCode !== null) throw new Error(`${what} exited (code ${child.exitCode})`);
    if (await responds(target)) return;
    await new Promise((resolve) => setTimeout(resolve, 250));
  }
  throw new Error(`${what} did not start within a minute`);
}

function start(command, args) {
  const child = spawn(command, args, { stdio: ["ignore", "ignore", "inherit"] });
  running.add(child);
  return child;
}

/** One audit in a browser of its own: reusing a browser makes later runs measurably slower. */
async function audit() {
  const profile = await mkdtemp(join(tmpdir(), "lighthouse-chromium-"));
  profiles.add(profile);
  const browser = start(chromium.executablePath(), [
    "--headless",
    `--remote-debugging-port=${debuggingPort}`,
    `--user-data-dir=${profile}`,
    // Without these, Chromium asks the desktop keyring (over D-Bus) for its cookie key, which
    // hangs every page load on a machine without one, such as a server or CI runner.
    "--password-store=basic",
    "--use-mock-keychain",
    "--no-first-run",
    "--no-default-browser-check",
    // This browser only ever loads the local build under test.
    "--no-sandbox",
    "about:blank",
  ]);
  try {
    await waitFor(debuggingUrl, browser, "Chromium");
    const result = await lighthouse(url, {
      port: debuggingPort,
      hostname: "127.0.0.1",
      output: ["html", "json"],
      logLevel: process.env.LIGHTHOUSE_LOG_LEVEL ?? "error",
    });
    if (result === undefined) throw new Error("Lighthouse returned no result");
    if (result.lhr.runtimeError !== undefined) throw new Error(result.lhr.runtimeError.message);
    return result;
  } finally {
    await stop(browser);
    await removeProfile(profile);
  }
}

for (const signal of ["SIGINT", "SIGTERM"]) {
  process.once(signal, () => {
    void cleanUp().finally(() => process.exit(130));
  });
}
setTimeout(() => {
  fail(`gave up after ${timeLimitMs / 60_000} minutes`);
  void cleanUp().finally(() => process.exit(1));
}, timeLimitMs).unref();

try {
  // Something already listening would be audited (or driven) instead of this build.
  for (const [target, name] of [
    [origin, `LIGHTHOUSE_APP_PORT (${appPort})`],
    [debuggingUrl, `LIGHTHOUSE_DEBUGGING_PORT (${debuggingPort})`],
  ]) {
    if (await responds(target))
      throw new Error(`${name} is already in use; free it or pick another`);
  }

  const nextBin = fileURLToPath(import.meta.resolve("next/dist/bin/next"));
  const server = start(process.execPath, [
    nextBin,
    "start",
    "--hostname",
    "127.0.0.1",
    "--port",
    String(appPort),
  ]);
  await waitFor(origin, server, "The web app");

  const results = [];
  for (let run = 0; run < runs; run += 1) {
    try {
      results.push(await audit());
    } catch (error) {
      // Chromium now and then fails to record a trace (NO_NAVSTART); once more is enough.
      console.error(`lighthouse: run ${String(run + 1)} failed, trying again: ${String(error)}`);
      results.push(await audit());
    }
  }

  const scoreOf = (result, id) => result.lhr.categories[id]?.score ?? 0;
  const median = (values) => values.toSorted((a, b) => a - b)[Math.floor(values.length / 2)];
  const percent = (value) => String(Math.round(value * 100));
  for (const [id, category] of Object.entries(results[0].lhr.categories)) {
    const scores = results.map((result) => scoreOf(result, id));
    const score = median(scores);
    const passed = score >= minimumScore;
    console.log(
      `${passed ? "pass" : "FAIL"} ${percent(score).padStart(4)}  ${category.title} (runs: ${scores.map(percent).join(", ")})`,
    );
    if (!passed) fail(`${category.title} scored below ${minimumScore * 100}`);
  }

  // Keep the reports of the run with the median performance score.
  const byPerformance = results.toSorted(
    (a, b) => scoreOf(a, "performance") - scoreOf(b, "performance"),
  );
  const { report } = byPerformance[Math.floor(byPerformance.length / 2)];
  await mkdir(reportDir, { recursive: true });
  const [html, json] = Array.isArray(report) ? report : [report, ""];
  await writeFile(join(reportDir, `${reportName}.html`), html);
  await writeFile(join(reportDir, `${reportName}.json`), json);
  console.log(`Report: ${join(reportDir, `${reportName}.html`)}`);
} catch (error) {
  fail(error instanceof Error ? error.message : String(error));
} finally {
  await cleanUp();
}
