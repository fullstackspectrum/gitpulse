# GitPulse

A local Python CLI for GitHub repository traffic and release asset download stats. GitPulse can build a dashboard for a whole organization, and it keeps SQLite snapshots so you have history beyond GitHub's short traffic window.

> **What GitHub can tell you:** aggregate daily views and clones, unique counts, popular paths, referrers, and release-asset download totals. It does **not** identify individual visitors or people who cloned a repository. GitHub's traffic data is generally available for the most recent 14 days. Release asset downloads are not Homebrew formula install counts.

![GitPulse organization dashboard](docs/screenshots/dashboard-light.png)

## Requirements

- Python 3.10+
- A GitHub token with access to the repositories you want to inspect. Classic tokens need the `repo` scope for private repositories. For fine-grained tokens, grant these repository permissions:

  | Permission | Needed for |
  | --- | --- |
  | **Metadata: read** | All commands (always included) |
  | **Contents: read** | `downloads`, and release downloads in `org` |
  | **Administration: read** | `traffic`, `snapshot`, and traffic in `org` |

  A fine-grained token only covers repositories owned by its resource owner, so org-owned repositories need a token whose resource owner is that org. Without a required permission, GitHub returns `Resource not accessible by personal access token`.

Traffic endpoints only work for repositories you have push access to. Public visibility alone does not grant access to traffic analytics.

## Install

From the project directory, create a virtual environment and install the project in editable mode:

```sh
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e '.[dev]'
```

Set a token in your shell. `GITHUB_TOKEN` and `GH_TOKEN` are both supported. GitPulse never saves the token:

```sh
export GITHUB_TOKEN="github_pat_..."
```

If you use the [GitHub CLI](https://cli.github.com/) and are signed in with `gh auth login`, you can reuse its token instead:

```sh
export GITHUB_TOKEN="$(gh auth token)"
```

## Organization dashboard

```sh
gitpulse org ORG                                   # terminal summary + gitpulse-ORG.html
gitpulse org ORG --open                            # also open the dashboard in your browser
gitpulse org ORG --save                            # also save views/clones snapshots for `history`
gitpulse org ORG --all --output reports/org.html   # include forks and archived repos, custom path
```

`org` works for an organization or a user account. It fetches every repository in parallel (`--workers`, default 8), then prints a summary in the terminal: totals, daily sparklines, a table of every repository, and the top referrers.

![Terminal summary from gitpulse org](docs/screenshots/terminal.png)

It also writes a self-contained HTML dashboard to `gitpulse-ORG.html` in the current directory, or to the path you pass with `--output`. The dashboard shows:

- Totals for views, unique visitors, clones, stars, forks, release downloads, and open issues and PRs
- Daily views and clones summed across repositories, with a hover readout for each day
- The most viewed and most starred repositories, a language breakdown, top referrers, and release downloads by repository
- A sortable, filterable table of every repository with a 14-day views sparkline

Styles, charts, and scripts are all inline, so it works offline (only the owner's avatar loads from GitHub). It follows your system's light or dark theme, and has a toggle to switch.

![Dashboard in dark mode](docs/screenshots/dashboard-dark.png)

By default, forks and archived repositories are skipped; `--all` includes them. When your token can't read traffic for a repository, its stars, forks, and downloads still appear, and the dashboard lists which repositories are missing traffic and why. Unique visitor and cloner counts are summed per repository, so one person who visits two repositories is counted twice.

*Screenshots show sample data.*

## Repository commands

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

Snapshots are stored at `~/.local/share/gitpulse/gitpulse.sqlite3`. The database contains repository names and traffic responses, but no GitHub token. To use another location, set `GITPULSE_DB` to a SQLite file path.

Generated dashboards contain repository names, descriptions, and traffic numbers, including for private repositories. Treat them like any other internal report before sharing. `gitpulse-*.html` files are ignored by git.

## Homebrew tap usage

For tap repositories, clone traffic and unique cloners can be useful directional signals, but they are not install totals. A tap clone, formula installation, and binary download are distinct events. GitHub does not expose an install-by-user report for formulae through these traffic endpoints.

## Development

Run tests with `pytest` and lint with `ruff check .`.
