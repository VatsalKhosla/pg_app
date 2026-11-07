// The hold race (ARCHITECTURE §18): 50 students, each with their own quote for the same room and
// move-in, hold at the same moment. The exclusion constraint lets no bed go twice: every answer is
// a hold or BED_UNAVAILABLE, at least one wins, none fails. SLO: p95 under 400 ms.
import { check } from "k6";
import { Counter } from "k6/metrics";
import http from "k6/http";

import { API, json, places, signIn, visitor } from "./common.js";

const STUDENTS = Number(__ENV.STUDENTS || 50);
const won = new Counter("holds_won");
const refused = new Counter("holds_refused");

export const options = {
  setupTimeout: "5m",
  scenarios: {
    race: { executor: "per-vu-iterations", vus: STUDENTS, iterations: 1, maxDuration: "2m" },
  },
  thresholds: {
    holds_won: ["count>=1"],
    "http_req_duration{kind:hold}": ["p(95)<400"],
    "checks{kind:hold}": ["rate==1"],
  },
};

export function setup() {
  const slug = places().samples[0];
  const room = http.get(`${API}/v1/properties/${slug}`, { headers: visitor() }).json()
    .categories[0].id;
  const moveIn = new Date(Date.now() + 30 * 86_400_000).toISOString().slice(0, 10);
  const students = [];
  for (let index = 0; index < STUDENTS; index += 1) {
    // Fictional numbers, a fresh block each run.
    const phone = `9${String(Date.now()).slice(-5)}${String(index).padStart(4, "0")}`;
    const student = signIn(phone);
    const quote = http.post(
      `${API}/v1/quotes`,
      JSON.stringify({ roomCategory: room, moveIn, stayMonths: 11 }),
      json(student.headers, student.cookies),
    );
    students.push({ ...student, quote: quote.json().id });
  }
  return { students };
}

export default function (data) {
  const me = data.students[__VU - 1];
  const tags = { kind: "hold" };
  // A key of each student's own, as the web app sends with every hold (safe to retry).
  const key = { "Idempotency-Key": `hold-${__VU}-${Date.now()}` };
  const answer = http.post(`${API}/v1/bookings`, JSON.stringify({ quote: me.quote }), {
    ...json({ ...me.headers, ...key }, me.cookies),
    tags,
  });
  if (answer.status === 201) won.add(1);
  if (answer.status === 409) refused.add(1);
  if (answer.status !== 201 && answer.status !== 409) {
    console.warn(`hold answered ${answer.status}: ${String(answer.body).slice(0, 300)}`);
  }
  check(
    answer,
    { "a hold, or the bed already taken": (r) => r.status === 201 || r.status === 409 },
    tags,
  );
}
