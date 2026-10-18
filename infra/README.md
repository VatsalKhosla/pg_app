# Infrastructure

- `docker-compose.yml`: local PostgreSQL with PostGIS, Redis, MinIO (S3) and Mailpit for `make dev` (step 0.2).
- `terraform/`: staging and production on AWS Mumbai, plus Vercel and Cloudflare settings (Phase 8). Until then, manual setup is documented in `docs/runbooks/`.
