# GitPulse

A local Python CLI for viewing GitHub repository traffic and release asset download stats, with SQLite snapshots for keeping history beyond GitHub's short traffic window.

> **What GitHub can tell you:** aggregate daily views and clones, unique counts, popular paths, referrers, and release-asset download totals. It does **not** identify individual visitors or people who cloned a repository. GitHub's traffic data is generally available for the most recent 14 days. Release asset downloads are not Homebrew formula install counts.

## Requirements

- Python 3.10+
- A GitHub personal access token with access to the repositories you want to inspect. Classic tokens generally need `repo` for private repositories. For fine-grained tokens, grant these repository permissions:

  | Permission | Needed for |
  | --- | --- |
  | **Metadata: read** | All commands (always included) |
  | **Contents: read** | `downloads` (release assets) |
  | **Administration: read** | `traffic` and `snapshot` |

  A fine-grained token only covers repositories owned by its resource owner, so org-owned repositories need a token whose resource owner is that org. Without a required permission, GitHub returns `Resource not accessible by personal access token`.

Traffic endpoints only work for repositories you have suitable administrator access to. Public visibility alone does not grant access to traffic analytics.

## Install

From the project directory, create a virtual environment and install the project in editable mode:

```sh
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e '.[dev]'
```

Set a token in your shell. `GITHUB_TOKEN` and `GH_TOKEN` are both supported; the token is never saved by GitPulse:

```sh
export GITHUB_TOKEN="github_pat_..."
```

## Commands

```sh
gitpulse --help
gitpulse repos
gitpulse repos --all
gitpulse traffic OWNER/REPO
gitpulse traffic OWNER/REPO --metric clones
gitpulse traffic OWNER/REPO --metric referrers
gitpulse traffic OWNER/REPO --metric popular/paths
gitpulse traffic OWNER/REPO --metric views --save
gitpulse snapshot OWNER/REPO
gitpulse history OWNER/REPO --metric views
gitpulse history OWNER/REPO --metric clones
gitpulse downloads OWNER/REPO
```

`repos` lists repositories accessible to the authenticated account and filters forks and archived repositories by default. `--all` includes them.

`traffic` displays GitHub's recent traffic response. `snapshot` fetches views and clones and saves both responses locally. Run it on a schedule (for example, daily) to build a history beyond GitHub's 14-day window. `history` displays saved snapshots; it does not backfill earlier data.

`downloads` lists release asset download counts. It does not measure Homebrew formula installation.

## Local data and privacy

Snapshots are stored at `~/.local/share/gitpulse/gitpulse.sqlite3` on macOS and other Unix-like systems. The database contains repository names and traffic responses, but no GitHub token. It is excluded from version control. To use another location, set `GITPULSE_DB` to a SQLite file path.

## Homebrew tap usage

For tap repositories, clone traffic and unique cloners can be useful directional signals, but they are not install totals. A tap clone, formula installation, and binary download are distinct events. GitHub does not expose an install-by-user report for formulae through these traffic endpoints.

## Development

Run tests with `pytest` and lint with `ruff check .`.
