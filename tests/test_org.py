from typing import Any

from gitpulse.github_api import GitHubAPIError, GitHubClient
from gitpulse.org import collect_org
from gitpulse.report import compact, nice_ticks, render_html


def _repo(name: str, **extra: Any) -> dict[str, Any]:
    return {
        "name": name,
        "full_name": f"acme/{name}",
        "html_url": f"https://github.com/acme/{name}",
        "stargazers_count": 0,
        "forks_count": 0,
        **extra,
    }


class FakeClient:
    def __init__(self) -> None:
        self.repos = [
            _repo("api", language="Go", stargazers_count=40),
            _repo("web", language="TypeScript", stargazers_count=12, description="<b>site</b>"),
            _repo("secret", language="Go"),
            _repo("old", archived=True),
        ]

    def owner_profile(self, owner: str) -> dict[str, Any]:
        return {"login": owner, "name": "Acme Inc"}

    def list_owner_repositories(self, owner: str) -> list[dict[str, Any]]:
        return self.repos

    def traffic(self, owner: str, repo: str, metric: str) -> dict[str, Any]:
        if repo == "secret":
            raise GitHubAPIError("GitHub denied this request.", status=403)
        scale = 10 if repo == "api" else 1
        if metric == "referrers":
            return {"referrers": [{"referrer": "google.com", "count": 3 * scale, "uniques": scale}]}
        series = [
            {"timestamp": "2026-10-01T00:00:00Z", "count": 2 * scale, "uniques": scale},
            {"timestamp": "2026-10-03T00:00:00Z", "count": 4 * scale, "uniques": scale},
        ]
        return {"count": 6 * scale, "uniques": 2 * scale, metric: series}

    def release_downloads(self, owner: str, repo: str) -> tuple[int, list[dict[str, Any]]]:
        if repo == "api":
            return 1, [{"release": "v1", "name": "api.tar.gz", "download_count": 25}]
        return 0, []


def test_collect_org_aggregates_and_skips_archived() -> None:
    report = collect_org(FakeClient(), "acme")

    assert report.repos[0].name == "api"
    assert {repo.name for repo in report.repos} == {"api", "web", "secret"}
    assert report.total("views") == 66
    assert report.total("downloads") == 25
    assert report.referrers() == [("google.com", 33, 11)]
    assert report.languages()[0] == ("Go", 2)


def test_traffic_errors_are_recorded_per_repo() -> None:
    report = collect_org(FakeClient(), "acme")
    secret = next(repo for repo in report.repos if repo.name == "secret")

    assert secret.traffic_error
    assert len(report.traffic_repos) == 2


def test_daily_series_fills_missing_days() -> None:
    report = collect_org(FakeClient(), "acme")

    assert report.daily("views_daily") == [
        ("2026-10-01", 22),
        ("2026-10-02", 0),
        ("2026-10-03", 44),
    ]


def test_render_html_escapes_content() -> None:
    html = render_html(collect_org(FakeClient(), "acme"))

    assert html.startswith("<!doctype html>")
    assert "Acme Inc" in html
    assert "<b>site</b>" not in html
    assert "&lt;b&gt;site&lt;/b&gt;" in html
    assert "Traffic unavailable for 1 of 3" in html


def test_number_helpers() -> None:
    assert compact(1284) == "1,284"
    assert compact(12940) == "12.9K"
    assert compact(2_000_000) == "2M"
    assert nice_ticks(66) == [0, 20, 40, 60, 80]
    assert nice_ticks(0) == [0, 1]


def test_referrers_failure_keeps_views_and_clones() -> None:
    class NoReferrers(FakeClient):
        def traffic(self, owner: str, repo: str, metric: str) -> dict[str, Any]:
            if metric == "referrers":
                raise GitHubAPIError("Not Found", status=404)
            return super().traffic(owner, repo, metric)

    report = collect_org(NoReferrers(), "acme")

    assert report.total("views") == 66
    assert report.referrers() == []


def test_referrers_use_popular_endpoint() -> None:
    client = GitHubClient(token="test")
    requested: list[str] = []
    client.get = lambda path, params=None: requested.append(path) or []  # type: ignore[method-assign]

    client.traffic("acme", "api", "referrers")

    assert requested == ["/repos/acme/api/traffic/popular/referrers"]
