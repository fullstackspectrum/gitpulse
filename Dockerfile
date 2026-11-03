# syntax=docker/dockerfile:1

# Docker Hardened Images (https://dhi.io), Alpine variant: a minimal, non-root Python
# runtime with no shell or package manager. Pulling them needs `docker login dhi.io`
# with a Docker account.
ARG PYTHON_VERSION=3.13

FROM dhi.io/python:${PYTHON_VERSION}-alpine-dev AS build
WORKDIR /src
COPY pyproject.toml README.md LICENSE ./
COPY src ./src
# The venv is created without pip so the runtime image ships only GitPulse and its
# dependencies; the build stage's pip installs into it from outside.
RUN python3 -m venv --without-pip /opt/venv \
    && pip --python /opt/venv/bin/python install --no-cache-dir . \
    && mkdir /data

FROM dhi.io/python:${PYTHON_VERSION}-alpine
ARG VERSION=dev
LABEL org.opencontainers.image.title="gitpulse" \
      org.opencontainers.image.description="GitHub traffic, clones, referrers, and release downloads, with org-wide HTML dashboards" \
      org.opencontainers.image.source="https://github.com/fullstackspectrum/gitpulse" \
      org.opencontainers.image.licenses="MIT" \
      org.opencontainers.image.version="${VERSION}"

ENV PATH=/opt/venv/bin:$PATH \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    GITPULSE_DB=/data/gitpulse.sqlite3

COPY --from=build /opt/venv /opt/venv
# The runtime image has no shell, so /data is created in the build stage.
COPY --from=build --chown=65532:65532 /data /data

# The base image already runs as the non-root user 65532; this makes it explicit.
USER 65532:65532
# Dashboards and snapshot history land here; mount a volume to keep them.
WORKDIR /data
VOLUME ["/data"]
ENTRYPOINT ["gitpulse"]
CMD ["--help"]
