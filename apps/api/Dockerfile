# The API and worker image (docs/adr/0013-ci-and-supply-chain.md).
#
# uv installs the locked dependencies and the app itself (not editable) into a virtual environment.
# The runtime stage is slim Python with only that environment, the migrations and an unprivileged
# user. One image runs the API (the default command), the worker (`python -m app.worker`) and
# migrations (`alembic upgrade head`). Configuration comes from the environment only:
# .dockerignore admits an explicit list of files, so no .env file can ever be copied in.
# Base images are pinned by tag and digest.

FROM ghcr.io/astral-sh/uv:0.13.1@sha256:4a1f3666816dafadd20ceb71eac9a7d56d7ef30279f7d64048519ab901ada336 AS uv

FROM python:3.14.8-slim-trixie@sha256:a2b82f3c48559aa0a8446d9af49826b6e2b2016f4cd2afabfe6013ec53729170 AS build
COPY --from=uv /uv /usr/local/bin/uv
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    UV_PROJECT_ENVIRONMENT=/opt/venv
WORKDIR /build
# Dependencies first, so a code change reuses this layer.
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev --no-install-project
COPY src ./src
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev --no-editable

FROM python:3.14.8-slim-trixie@sha256:a2b82f3c48559aa0a8446d9af49826b6e2b2016f4cd2afabfe6013ec53729170 AS runtime
LABEL org.opencontainers.image.title="pg-platform-api" \
      org.opencontainers.image.description="API and background worker for the PG booking platform" \
      org.opencontainers.image.source="https://github.com/VatsalKhosla/pg_app" \
      org.opencontainers.image.licenses="Apache-2.0"
# The base image's pip is never used at run time (uv built the environment), and it carries its
# own older copies of urllib3 and msgpack, so it goes.
RUN python -m pip uninstall --yes --root-user-action=ignore pip \
    && groupadd --system --gid 10001 app \
    && useradd --system --uid 10001 --gid app --home-dir /app --shell /usr/sbin/nologin app
ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1
WORKDIR /app
# Owned by root and only readable by the app user, so a compromised process can't change code.
COPY --from=build /opt/venv /opt/venv
COPY alembic.ini ./
COPY migrations ./migrations
USER app:app
EXPOSE 8000
# Behind a load balancer, set FORWARDED_ALLOW_IPS to its addresses so client IPs are believed.
CMD ["uvicorn", "app.main:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--no-access-log"]
