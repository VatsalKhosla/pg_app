// Peak-season reads (ARCHITECTURE §18): 300 a second, the way people browse. Search (45%), the
// map's pins (35%) and PG pages (20%), each from a visitor of its own. SLO: p95 under 300 ms.
import { check } from "k6";
import http from "k6/http";

import { API, pick, places, visitor } from "./common.js";

export const options = {
  scenarios: {
    reads: {
      executor: "constant-arrival-rate",
      rate: Number(__ENV.READS_PER_SECOND || 300),
      timeUnit: "1s",
      duration: __ENV.DURATION || "2m",
      preAllocatedVUs: 100,
      maxVUs: 600,
    },
  },
  thresholds: {
    "http_req_duration{kind:search}": ["p(95)<300"],
    "http_req_duration{kind:pins}": ["p(95)<300"],
    "http_req_duration{kind:pg}": ["p(95)<300"],
    "checks{kind:search}": ["rate>0.99"],
    "checks{kind:pins}": ["rate>0.99"],
    "checks{kind:pg}": ["rate>0.99"],
  },
};

export function setup() {
  return places();
}

// Delhi, where the seeded PGs are; a box a map shows, 4 to 10 km across.
const CITY = { west: 77.05, south: 28.55, east: 77.3, north: 28.75 };

function box() {
  const size = 0.04 + Math.random() * 0.06;
  const west = CITY.west + Math.random() * (CITY.east - CITY.west - size);
  const south = CITY.south + Math.random() * (CITY.north - CITY.south - size);
  return [west, south, west + size, south + size].map((value) => value.toFixed(4)).join(",");
}

export default function (data) {
  const roll = Math.random();
  const headers = visitor();
  if (roll < 0.45) {
    const query =
      Math.random() < 0.6
        ? `campus=${pick(data.campuses)}&sort=distance`
        : `locality=${pick(data.localities)}&sort=recommended`;
    const tags = { kind: "search" };
    const answer = http.get(`${API}/v1/search/properties?${query}`, { headers, tags });
    check(answer, { "search answers": (r) => r.status === 200 }, tags);
  } else if (roll < 0.8) {
    const tags = { kind: "pins" };
    const zoom = 12 + Math.floor(Math.random() * 3);
    const answer = http.get(`${API}/v1/map/pins?bbox=${box()}&zoom=${zoom}`, { headers, tags });
    check(answer, { "pins answer": (r) => r.status === 200 }, tags);
  } else {
    const tags = { kind: "pg" };
    const answer = http.get(`${API}/v1/properties/${pick(data.samples)}`, { headers, tags });
    check(answer, { "a PG answers": (r) => r.status === 200 }, tags);
  }
}
