"""Collect and aggregate statistics for every repository owned by an organization or user."""

from __future__ import annotations

from collections import Counter, defaultdict
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from typing import Any

from gitpulse.github_api import GitHubAPIError, GitHubClient


@dataclass
class RepoStats:
    """Metadata, recent traffic, and release downloads for one repository."""

    name: str
    full_name: str
    url: str
    description: str = ""
    private: bool = False
    fork: bool = False
    archived: bool = False
    language: str = ""
    stars: int = 0
    forks: int = 0
    open_issues: int = 0
    pushed_at: str = ""
    views: int = 0
    view_uniques: int = 0
    clones: int = 0
    clone_uniques: int = 0
    views_daily: dict[str, int] = field(default_factory=dict)
    clones_daily: dict[str, int] = field(default_factory=dict)
    referrers: list[dict[str, Any]] = field(default_factory=list)
    releases: int = 0
    downloads: int = 0
    traffic_error: str | None = None
    releases_error: str | None = None
    raw_traffic: dict[str, dict[str, Any]] = field(default_factory=dict)

    @property
    def owner(self) -> str:
        return self.full_name.split("/", 1)[0]

    @classmethod
    def from_api(cls, repo: dict[str, Any]) -> RepoStats:
        return cls(
            name=repo.get("name", ""),
            full_name=repo.get("full_name", ""),
            url=repo.get("html_url", ""),
            description=repo.get("description") or "",
            private=bool(repo.get("private")),
            fork=bool(repo.get("fork")),
            archived=bool(repo.get("archived")),
            language=repo.get("language") or "",
            stars=int(repo.get("stargazers_count") or 0),
            forks=int(repo.get("forks_count") or 0),
            open_issues=int(repo.get("open_issues_count") or 0),
            pushed_at=str(repo.get("pushed_at") or ""),
        )


@dataclass
class OrgReport:
    """Aggregated statistics across an owner's repositories."""

    owner: str
    profile: dict[str, Any]
    repos: list[RepoStats]
    generated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def total(self, attr: str) -> int:
        return sum(getattr(repo, attr) for repo in self.repos)

    @property
    def traffic_repos(self) -> list[RepoStats]:
        return [repo for repo in self.repos if repo.traffic_error is None]

    def daily(self, attr: str) -> list[tuple[str, int]]:
        """Sum a daily series across repos, filling gaps with zeros."""
        totals: dict[str, int] = defaultdict(int)
        for repo in self.repos:
            for day, count in getattr(repo, attr).items():
                totals[day] += count
        if not totals:
            return []
        start = date.fromisoformat(min(totals))
        end = date.fromisoformat(max(totals))
        days = [(start + timedelta(days=i)).isoformat() for i in range((end - start).days + 1)]
        return [(day, totals.get(day, 0)) for day in days]

    def languages(self) -> list[tuple[str, int]]:
        counts = Counter(repo.language or "Unspecified" for repo in self.repos)
        return counts.most_common()

    def referrers(self, limit: int = 10) -> list[tuple[str, int, int]]:
        views: Counter[str] = Counter()
        uniques: Counter[str] = Counter()
        for repo in self.repos:
            for item in repo.referrers:
                name = str(item.get("referrer", ""))
                views[name] += int(item.get("count", 0))
                uniques[name] += int(item.get("uniques", 0))
        return [(name, count, uniques[name]) for name, count in views.most_common(limit)]

    def top(self, attr: str, limit: int = 10) -> list[RepoStats]:
        ranked = sorted(self.repos, key=lambda repo: getattr(repo, attr), reverse=True)
        return [repo for repo in ranked[:limit] if getattr(repo, attr) > 0]


def _daily(series: list[dict[str, Any]]) -> dict[str, int]:
    return {str(item.get("timestamp", ""))[:10]: int(item.get("count", 0)) for item in series}


def collect_repo(client: GitHubClient, stats: RepoStats) -> RepoStats:
    """Fill in traffic and release data. Permission errors are recorded, not raised."""
    owner, repo = stats.full_name.split("/", 1)
    try:
        views = client.traffic(owner, repo, "views")
        clones = client.traffic(owner, repo, "clones")
    except GitHubAPIError as exc:
        stats.traffic_error = str(exc)
    else:
        stats.raw_traffic = {"views": views, "clones": clones}
        stats.views = int(views.get("count", 0))
        stats.view_uniques = int(views.get("uniques", 0))
        stats.clones = int(clones.get("count", 0))
        stats.clone_uniques = int(clones.get("uniques", 0))
        stats.views_daily = _daily(views.get("views", []))
        stats.clones_daily = _daily(clones.get("clones", []))
        # Referrers are a nice-to-have; a failure here must not discard views and clones.
        try:
            stats.referrers = client.traffic(owner, repo, "referrers").get("referrers", [])
        except GitHubAPIError:
            stats.referrers = []
    try:
        release_count, assets = client.release_downloads(owner, repo)
    except GitHubAPIError as exc:
        stats.releases_error = str(exc)
    else:
        stats.releases = release_count
        stats.downloads = sum(int(asset["download_count"]) for asset in assets)
    return stats


def collect_org(
    client: GitHubClient,
    owner: str,
    include_all: bool = False,
    workers: int = 8,
    on_start: Callable[[int], None] | None = None,
    on_repo: Callable[[RepoStats], None] | None = None,
) -> OrgReport:
    """Fetch every repository for OWNER and collect its stats concurrently."""
    profile = client.owner_profile(owner)
    repos = [RepoStats.from_api(repo) for repo in client.list_owner_repositories(owner)]
    if not include_all:
        repos = [repo for repo in repos if not repo.fork and not repo.archived]
    if on_start:
        on_start(len(repos))
    collected: list[RepoStats] = []
    with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        futures = [pool.submit(collect_repo, client, repo) for repo in repos]
        for future in as_completed(futures):
            stats = future.result()
            collected.append(stats)
            if on_repo:
                on_repo(stats)
    collected.sort(key=lambda repo: (repo.views, repo.stars), reverse=True)
    return OrgReport(owner=profile.get("login") or owner, profile=profile, repos=collected)
