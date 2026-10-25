# The settings of the browser tests' API, its worker and their operator commands: sourced by
# scripts/e2e-api.sh and scripts/e2e-manage.sh, so all three use one database and one storage.
#
# Everything that matters is set here, so a developer's apps/api/.env can't change the tests. The
# tests have their own database (platform_e2e), Valkey database (1) and buckets; development data
# is never touched.

api_port="${E2E_API_PORT:-8100}"
web_port="${E2E_PORT:-3100}"
database=platform_e2e

export APP_ENV=local
export LOG_LEVEL=INFO
export LOG_FORMAT=json
export DATABASE_URL="postgresql+asyncpg://platform:platform@127.0.0.1:${POSTGRES_PORT:-5432}/$database"
export REDIS_URL="redis://:platform@127.0.0.1:${VALKEY_PORT:-6379}/1"
export SECRET_KEY="e2e-only-secret-key-0123456789abcdef"
export SITE_URL="http://127.0.0.1:$web_port"
export API_URL="http://127.0.0.1:$api_port"
export CORS_ALLOWED_ORIGINS="$SITE_URL"
export SESSION_COOKIE_DOMAIN=
export OTP_SENDER=console
export TURNSTILE_SECRET_KEY=
export GOOGLE_CLIENT_ID=
export GOOGLE_CLIENT_SECRET=
export STAFF_GOOGLE_DOMAINS=
export STAFF_GOOGLE_EMAILS=
export PRIVACY_NOTICE_VERSION=draft-1
export SENTRY_DSN=
export OTEL_EXPORTER_OTLP_ENDPOINT=
# Local SeaweedFS with its development identity (infra/seaweedfs/s3.json), in buckets of its own.
export S3_ENDPOINT_URL="http://127.0.0.1:${S3_PORT:-8333}"
export S3_REGION=ap-south-1
export S3_ACCESS_KEY_ID=pg-platform-dev
export S3_SECRET_ACCESS_KEY=pg-platform-dev-only
export MEDIA_PRIVATE_BUCKET=pg-platform-e2e-private
export MEDIA_PUBLIC_BUCKET=pg-platform-e2e-media
export MEDIA_PUBLIC_BASE_URL="$S3_ENDPOINT_URL/$MEDIA_PUBLIC_BUCKET"
# Operator commands print as they go, so a test can answer a prompt.
export PYTHONUNBUFFERED=1
