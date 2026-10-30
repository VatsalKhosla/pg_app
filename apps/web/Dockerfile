# The web app's image, for a host that runs containers: staging on a free host (ADR 0047).
# Production goes to Vercel (ARCHITECTURE §3), which builds from the repository itself.
#
# pnpm installs the locked dependencies of the web app and the API client only. Next.js builds
# its standalone server, whose output tracing keeps just the files the server uses. The runtime
# stage is slim Node with that server, its static files and an unprivileged user.
#
# NEXT_PUBLIC_ values are inlined at build time, so each environment builds its own image; the
# server's secrets (REVALIDATE_SECRET) come from the environment at run time. The build context
# is the repository, and Dockerfile.dockerignore admits an explicit list of files from it, so no
# .env file can be copied in. Base images are pinned by tag and digest.

FROM node:24.22.0-trixie-slim@sha256:a6155384446670e9719bdc4fd0ebe4d4b29fb32a8d6aa523da3547a6cfbcf22c AS build
ENV NEXT_TELEMETRY_DISABLED=1 \
    PNPM_HOME=/pnpm \
    PATH="/pnpm:$PATH"
# The pnpm version package.json names (packageManager).
RUN npm install --global --no-fund --no-audit pnpm@12.12.0
WORKDIR /repo
# Dependencies first, so a code change reuses this layer.
COPY package.json pnpm-lock.yaml pnpm-workspace.yaml ./
COPY apps/web/package.json apps/web/
COPY packages/api-client/package.json packages/api-client/
RUN --mount=type=cache,id=pnpm-store,target=/pnpm/store \
    pnpm install --frozen-lockfile --filter "@pg-platform/web..."
COPY tsconfig.base.json ./
COPY packages/api-client packages/api-client
COPY apps/web apps/web
ARG NEXT_PUBLIC_APP_ENV \
    NEXT_PUBLIC_SITE_URL \
    NEXT_PUBLIC_API_URL \
    NEXT_PUBLIC_MEDIA_URL \
    NEXT_PUBLIC_UPLOAD_ORIGIN \
    NEXT_PUBLIC_TURNSTILE_SITE_KEY \
    NEXT_PUBLIC_SENTRY_DSN \
    NEXT_PUBLIC_MAP_TILES_URL \
    NEXT_PUBLIC_MAP_TILES_ATTRIBUTION
ENV NEXT_PUBLIC_APP_ENV=$NEXT_PUBLIC_APP_ENV \
    NEXT_PUBLIC_SITE_URL=$NEXT_PUBLIC_SITE_URL \
    NEXT_PUBLIC_API_URL=$NEXT_PUBLIC_API_URL \
    NEXT_PUBLIC_MEDIA_URL=$NEXT_PUBLIC_MEDIA_URL \
    NEXT_PUBLIC_UPLOAD_ORIGIN=$NEXT_PUBLIC_UPLOAD_ORIGIN \
    NEXT_PUBLIC_TURNSTILE_SITE_KEY=$NEXT_PUBLIC_TURNSTILE_SITE_KEY \
    NEXT_PUBLIC_SENTRY_DSN=$NEXT_PUBLIC_SENTRY_DSN \
    NEXT_PUBLIC_MAP_TILES_URL=$NEXT_PUBLIC_MAP_TILES_URL \
    NEXT_PUBLIC_MAP_TILES_ATTRIBUTION=$NEXT_PUBLIC_MAP_TILES_ATTRIBUTION
WORKDIR /repo/apps/web
RUN NEXT_OUTPUT=standalone pnpm exec next build

FROM node:24.22.0-trixie-slim@sha256:a6155384446670e9719bdc4fd0ebe4d4b29fb32a8d6aa523da3547a6cfbcf22c AS runtime
LABEL org.opencontainers.image.title="pg-platform-web" \
      org.opencontainers.image.description="Web app for the PG booking platform (staging)" \
      org.opencontainers.image.source="https://github.com/VatsalKhosla/pg_app" \
      org.opencontainers.image.licenses="Apache-2.0"
ENV NODE_ENV=production \
    NEXT_TELEMETRY_DISABLED=1 \
    HOSTNAME=0.0.0.0 \
    PORT=3000
WORKDIR /app
# Owned by root and only readable by the node user, so a compromised process can't change code.
COPY --from=build /repo/apps/web/.next/standalone ./
COPY --from=build /repo/apps/web/.next/static ./apps/web/.next/static
USER node:node
EXPOSE 3000
CMD ["node", "apps/web/server.js"]
