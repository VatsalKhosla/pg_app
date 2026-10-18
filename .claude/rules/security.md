---
paths:
  - "apps/**"
  - "infra/**"
  - ".github/**"
---

# Security rules

- **Deny by default.** Every new route gets a policy check and an entry in the authorization matrix test. Another user's resource returns 404.
- **Validate everything** at the edge (Pydantic `extra="forbid"`, Zod) and enforce size limits. Trust no client-sent price, amount, role or id.
- **Auth**: OTP codes hashed, short-lived, attempt-limited and rate-limited; sessions are opaque tokens in `HttpOnly; Secure; SameSite=Lax` cookies; CSRF token on state-changing requests; staff need domain-restricted Google sign-in.
- **Secrets** come from the environment only. Never print, log, commit or hardcode them; keep `.env.example` complete but with dummy values. Test and live payment keys are always separate.
- **Personal data**: collect the minimum; never store Aadhaar numbers; encrypt KYC fields and documents; mask phone numbers in logs; respect retention rules and consent records (DPDP).
- **Webhooks**: verify the signature on the raw body before parsing; reject unsigned or stale events; store, acknowledge, then process asynchronously.
- **Files**: presigned uploads with type and size allowlists, magic-byte checks, EXIF/GPS stripping, no SVG, private buckets plus short-lived signed URLs for documents.
- **Headers**: strict CSP with nonces, HSTS, nosniff, `frame-ancestors 'none'`, a tight Permissions-Policy. CORS allows exact origins only.
- **Abuse**: rate limits on OTP, login, visits, holds, search and map pins; one active hold per user; Turnstile before OTP sends.
- **Supply chain**: pin dependencies; pin GitHub Actions by SHA; no `curl | sh` in CI or Dockerfiles; minimal, non-root container images.
- **Infra**: no public database; least-privilege IAM and security groups; OIDC from CI to the cloud, no long-lived keys.
- **Audit**: staff, owner and money actions write to the append-only audit log.
