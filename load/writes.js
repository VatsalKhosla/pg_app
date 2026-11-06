// Peak-season writes (ARCHITECTURE §18): 20 a second, as quotes for the sample PGs' rooms, each from
// a visitor of its own. SLO: p95 under 400 ms.
import { check } from "k6";
import http from "k6/http";

import { API, cookie, json, pick, places, visitor } from "./common.js";

export const options = {
  scenarios: {
    quotes: {
      executor: "constant-arrival-rate",
      rate: Number(__ENV.WRITES_PER_SECOND || 20),
      timeUnit: "1s",
      duration: __ENV.DURATION || "2m",
      preAllocatedVUs: 20,
      maxVUs: 100,
    },
  },
  thresholds: {
    "http_req_duration{kind:quote}": ["p(95)<400"],
    "checks{kind:quote}": ["rate>0.99"],
  },
};

export function setup() {
  const rooms = places().samples.flatMap((slug) =>
    http
      .get(`${API}/v1/properties/${slug}`, { headers: visitor() })
      .json()
      .categories.map((c) => c.id),
  );
  return { rooms };
}

// A move-in two to eight weeks out, as YYYY-MM-DD.
function moveIn() {
  const day = new Date(Date.now() + (14 + Math.floor(Math.random() * 42)) * 86_400_000);
  return day.toISOString().slice(0, 10);
}

let csrf = null;

export default function (data) {
  if (csrf === null) {
    // Each virtual visitor's anonymous CSRF token, once.
    csrf = cookie(http.get(`${API}/v1/auth/csrf`, { headers: visitor() }), "__Secure-csrf");
  }
  const tags = { kind: "quote" };
  const body = { roomCategory: pick(data.rooms), moveIn: moveIn(), stayMonths: 11 };
  const answer = http.post(`${API}/v1/quotes`, JSON.stringify(body), {
    ...json({ "X-CSRF-Token": csrf }, { "__Secure-csrf": csrf }),
    tags,
  });
  check(answer, { "a quote is made": (r) => r.status === 201 }, tags);
}
