# syntax=docker/dockerfile:1

FROM python:3.13-slim AS build
WORKDIR /src
RUN pip install --no-cache-dir build
COPY pyproject.toml README.md LICENSE ./
COPY src ./src
RUN python -m build --wheel --outdir /dist

FROM python:3.13-slim
ARG VERSION=dev
LABEL org.opencontainers.image.title="gitpulse" \
      org.opencontainers.image.description="GitHub traffic, clones, referrers, and release downloads, with org-wide HTML dashboards" \
      org.opencontainers.image.source="https://github.com/fullstackspectrum/gitpulse" \
      org.opencontainers.image.licenses="MIT" \
      org.opencontainers.image.version="${VERSION}"

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    GITPULSE_DB=/data/gitpulse.sqlite3

COPY --from=build /dist/*.whl /tmp/
RUN pip install --no-cache-dir /tmp/*.whl && rm /tmp/*.whl \
    && useradd --create-home --uid 1000 gitpulse \
    && mkdir /data && chown gitpulse:gitpulse /data

USER gitpulse
# Dashboards and snapshot history land here; mount a volume to keep them.
WORKDIR /data
VOLUME ["/data"]
ENTRYPOINT ["gitpulse"]
CMD ["--help"]
