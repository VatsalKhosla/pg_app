// PostHog's stand-in for the browser tests (step 3.9, ADR 0035), started by playwright.config.ts:
// it keeps every batch sent to it, by the web server's /api/events and by the API's worker, and
// hands them back to the tests at GET /events.
import { createServer } from "node:http";

const port = Number(process.env.E2E_POSTHOG_PORT ?? "8200");
const PROJECT_KEY = "phc_e2e";
const events = [];

function json(response, status, body) {
  response.writeHead(status, { "content-type": "application/json" });
  response.end(JSON.stringify(body));
}

createServer((request, response) => {
  if (request.method === "GET" && request.url === "/healthz") return json(response, 200, "ok");
  if (request.method === "GET" && request.url === "/events") return json(response, 200, events);
  if (request.method !== "POST" || request.url !== "/batch/") return json(response, 404, null);
  const chunks = [];
  request.on("data", (chunk) => chunks.push(chunk));
  request.on("end", () => {
    try {
      const body = JSON.parse(Buffer.concat(chunks).toString("utf8"));
      if (body.api_key !== PROJECT_KEY || !Array.isArray(body.batch)) {
        return json(response, 401, { error: "not this project's" });
      }
      events.push(...body.batch);
      return json(response, 200, { status: "Ok" });
    } catch {
      return json(response, 400, { error: "not JSON" });
    }
  });
}).listen(port, "127.0.0.1");
