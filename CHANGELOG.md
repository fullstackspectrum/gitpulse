# Changelog

All notable changes to GitPulse are documented here. The format is based on
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project follows
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.2.1] - 2026-11-03

### Security

- The Docker image is now built on the Alpine variant of
  [Docker Hardened Images](https://dhi.io) for Python instead of `python:3.13-slim`.
  Trivy findings drop from 193 (50 High, none fixable in Debian) to 0.
- The runtime image has no shell or package manager. GitPulse runs from its own
  virtualenv containing only GitPulse and its dependencies, with no pip.
- `urllib3` is 2.8.0 in the Docker image and the Homebrew formula, fixing
  CVE-2026-97687, CVE-2026-97688, and CVE-2026-97689.

### Changed

- The container runs as the non-root UID 65532 instead of 1000.
- The Docker image is 105 MB, down from 227 MB.

### Upgrading

If you kept snapshot history in a Docker volume or bind mount with 0.2.0, its files
belong to UID 1000. Saving with 0.2.1 then fails with
`attempt to write a readonly database`. Give the files to the new user once; your
history is kept:

```sh
docker run --rm -v gitpulse-data:/data alpine chown -R 65532:65532 /data
```

For a bind mount, run `sudo chown -R 65532:65532 DIR` on the host, or keep the old UID
with `--user 1000:1000`.

## [0.2.0] - 2026-11-03

First public release.

### Added

- `gitpulse org ORG` builds a dashboard for a whole organization or user account. It
  prints a Rich summary in the terminal and writes a self-contained HTML dashboard
  with daily traffic, the most viewed and most starred repositories, languages,
  referrers, release downloads, and a sortable, filterable table of every repository.
- Per-repository commands: `repos`, `traffic`, `snapshot`, `history`, and `downloads`.
- Local SQLite snapshots to keep traffic history beyond GitHub's 14-day window.
- `gitpulse --version`.
- Releases on PyPI as `gitpulse-analytics`, in the
  [`fullstackspectrum/gitpulse`](https://github.com/fullstackspectrum/homebrew-gitpulse)
  Homebrew tap, and as the multi-arch `fullstackspectrum/gitpulse` Docker image.

[Unreleased]: https://github.com/fullstackspectrum/gitpulse/compare/v0.2.1...HEAD
[0.2.1]: https://github.com/fullstackspectrum/gitpulse/compare/v0.2.0...v0.2.1
[0.2.0]: https://github.com/fullstackspectrum/gitpulse/releases/tag/v0.2.0
