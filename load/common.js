// Shared by the load tests (step 8.2, scripts/load-test.sh).
import http from "k6/http";

export const API = __ENV.API || "http://127.0.0.1:8300";

// Each request comes from an address of its own, as visitors do through the load balancer: the
// API trusts forwarded addresses here, so per-address limits apply per visitor, not to the test.
export function visitor() {
  const part = () => Math.floor(Math.random() * 254) + 1;
  return { "X-Forwarded-For": `10.${part()}.${part()}.${part()}` };
}

// A cookie's value as the API set it: quoted when it holds characters a bare value can't.
export function cookie(response, name) {
  return response.cookies[name][0].value.replace(/^"|"$/gu, "");
}

// A JSON request's params: a visitor's own address, and cookies that replace whatever k6's cookie
// jar holds, since the jar would add copies the API refuses as a forged CSRF pair.
export function json(headers = {}, cookies = {}) {
  const scoped = Object.fromEntries(
    Object.entries(cookies).map(([name, value]) => [name, { value, replace: true }]),
  );
  return {
    headers: { "Content-Type": "application/json", ...visitor(), ...headers },
    cookies: scoped,
  };
}

// The campuses, localities and sample PGs the scenarios pick from.
export function places() {
  const get = (path) => http.get(`${API}${path}`, { headers: visitor() }).json();
  const campuses = get("/v1/campuses").items.map((campus) => campus.slug);
  const localities = get("/v1/localities").items.map((locality) => locality.slug);
  const samples = get("/v1/search/properties?q=fictional%20sample&limit=10").items.map(
    (card) => card.slug,
  );
  return { campuses, localities, samples };
}

export function pick(items) {
  return items[Math.floor(Math.random() * items.length)];
}

// Signs a fictional student in with the code a local API hands back, and returns what their requests
// need: the CSRF header, and the session and CSRF cookies.
export function signIn(phone) {
  // A jar of this student's own: one holding another's session would end it, as signing in ends
  // the session it arrives with (ASVS 7.2.4).
  const jar = new http.CookieJar();
  const anonymous = cookie(
    http.get(`${API}/v1/auth/csrf`, { headers: visitor(), jar }),
    "__Secure-csrf",
  );
  const before = { ...json({ "X-CSRF-Token": anonymous }, { "__Secure-csrf": anonymous }), jar };
  const asked = http
    .post(`${API}/v1/auth/otp/request`, JSON.stringify({ phone, humanCheckToken: "load" }), before)
    .json();
  const notice = http.get(`${API}/v1/privacy-notice`, { headers: visitor() }).json();
  const signedIn = http.post(
    `${API}/v1/auth/otp/verify`,
    JSON.stringify({
      challengeId: asked.challengeId,
      code: asked.developmentCode,
      consent: { noticeVersion: notice.version, purposes: ["account"] },
    }),
    before,
  );
  const token = signedIn.json().csrfToken;
  return {
    headers: { "X-CSRF-Token": token },
    cookies: { "__Secure-csrf": token, "__Secure-session": cookie(signedIn, "__Secure-session") },
  };
}
