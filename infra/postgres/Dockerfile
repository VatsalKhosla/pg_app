# PostgreSQL 18 with PostGIS 3.6 for local development and tests.
#
# Built from the official multi-arch postgres image (Debian) plus the PostgreSQL project's own
# PostGIS packages (apt.postgresql.org, already configured in the base image). It runs natively
# on amd64 and arm64 and uses glibc collations like Amazon RDS (PostgreSQL 18, PostGIS 3.6);
# the postgis/postgis image is amd64-only. btree_gist, pg_trgm and citext ship with PostgreSQL.
FROM postgres:18.6-trixie@sha256:74935e72241653ca55e0414067e6d8763aceb8a810eb51b452253ec3dcfc4336

RUN apt-get update \
    && apt-get install -y --no-install-recommends postgresql-18-postgis-3 postgresql-18-postgis-3-scripts \
    && rm -rf /var/lib/apt/lists/*
