# PostgreSQL 18 with PostGIS 3.6 for local development and tests.
#
# Built from the official multi-arch postgres image (Debian) plus the PostgreSQL project's own
# PostGIS packages (apt.postgresql.org, already configured in the base image). It runs natively
# on amd64 and arm64 and uses glibc collations like Amazon RDS (PostgreSQL 18, PostGIS 3.6);
# the postgis/postgis image is amd64-only. btree_gist, pg_trgm and citext ship with PostgreSQL.
FROM postgres:18.7-trixie@sha256:9f4fd4aa918f52ae3d6f3b687f1de90d8f867cd4d520021545a9a50c120eae3b

# The server comes from the same apt run as PostGIS: the PostgreSQL project builds each PostGIS
# package against its newest 18.x, which the base image may not have yet (an extension built for
# 18.7 won't load into 18.6). The base image's version is the oldest this can be.
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        postgresql-18 postgresql-18-postgis-3 postgresql-18-postgis-3-scripts \
    && rm -rf /var/lib/apt/lists/*
