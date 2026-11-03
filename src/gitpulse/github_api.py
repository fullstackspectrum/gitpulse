"""Small GitHub REST API client for GitPulse."""

from __future__ import annotations

import os
from typing import Any

import requests

from gitpulse import __version__


class GitHubAPIError(RuntimeError):
    """An error returned by the GitHub API or the local HTTP client."""

    def __init__(self, message: str, status: int | None = None) -> None:
        super().__init__(message)
        self.status = status


class GitHubClient:
    """Authenticated client for GitHub's REST API."""

    def __init__(self, token: str | None = None, base_url: str = "https://api.github.com") -> None:
        self.token = token or os.getenv("GITHUB_TOKEN") or os.getenv("GH_TOKEN")
        if not self.token:
            raise GitHubAPIError(
                "No GitHub token found. Set GITHUB_TOKEN or GH_TOKEN to a personal access token."
            )
        self.base_url = base_url.rstrip("/")
        self.session = requests.Session()
        self.session.headers.update(
            {
                "Accept": "application/vnd.github+json",
                "Authorization": f"Bearer {self.token}",
                "X-GitHub-Api-Version": "2022-11-28",
                "User-Agent": f"gitpulse/{__version__}",
            }
        )

    def get(self, path: str, params: dict[str, Any] | None = None) -> Any:
        url = path if path.startswith("http") else f"{self.base_url}{path}"
        try:
            response = self.session.get(url, params=params, timeout=20)
        except requests.RequestException as exc:
            raise GitHubAPIError(f"Could not connect to GitHub: {exc}") from exc

        if response.status_code == 403 and response.headers.get("X-RateLimit-Remaining") == "0":
            reset = response.headers.get("X-RateLimit-Reset")
            hint = f" Rate limit resets at Unix time {reset}." if reset else ""
            raise GitHubAPIError(f"GitHub API rate limit exceeded.{hint}")
        detail = ""
        if not response.ok:
            try:
                detail = response.json().get("message", "")
            except (ValueError, AttributeError):
                pass
        suffix = f" GitHub said: {detail}" if detail else ""
        is_traffic = "/traffic/" in url

        if response.status_code == 404:
            hint = (
                "your token may lack permission to view its traffic data."
                if is_traffic
                else "your token may not have access to it."
            )
            raise GitHubAPIError(
                f"GitHub returned 404. The repository may not exist, or {hint}{suffix}",
                status=404,
            )
        if response.status_code == 403:
            sso = response.headers.get("X-GitHub-SSO")
            if sso:
                raise GitHubAPIError(
                    "GitHub denied this request because the organization requires SAML SSO. "
                    f"Authorize your token for the organization ({sso}).{suffix}",
                    status=403,
                )
            hint = (
                "Traffic endpoints need a token with Administration: Read on this repository "
                "(classic tokens: the repo scope and push or admin access)."
                if is_traffic
                else "Check that your token includes this repository and has Contents: Read "
                "(classic tokens: the repo scope)."
            )
            raise GitHubAPIError(f"GitHub denied this request. {hint}{suffix}", status=403)
        if not response.ok:
            raise GitHubAPIError(
                f"GitHub API returned HTTP {response.status_code}.{suffix}",
                status=response.status_code,
            )
        try:
            return response.json()
        except ValueError as exc:
            raise GitHubAPIError("GitHub returned an invalid JSON response.") from exc

    def _paginate(self, path: str, params: dict[str, Any]) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        page = 1
        while True:
            batch = self.get(path, params={**params, "per_page": 100, "page": page})
            if not isinstance(batch, list) or not batch:
                break
            items.extend(batch)
            if len(batch) < 100:
                break
            page += 1
        return items

    def list_repositories(self) -> list[dict[str, Any]]:
        return self._paginate(
            "/user/repos",
            {"sort": "updated", "affiliation": "owner,collaborator,organization_member"},
        )

    def owner_profile(self, owner: str) -> dict[str, Any]:
        """Return the organization or user profile for OWNER."""
        result = self.get(f"/users/{owner}")
        return result if isinstance(result, dict) else {}

    def list_owner_repositories(self, owner: str) -> list[dict[str, Any]]:
        """List every repository owned by an organization or user that the token can see."""
        try:
            return self._paginate(f"/orgs/{owner}/repos", {"type": "all", "sort": "pushed"})
        except GitHubAPIError as exc:
            if exc.status != 404:
                raise
        # Not an organization. For the authenticated user, /user/repos includes private repos.
        me = self.get("/user")
        if isinstance(me, dict) and str(me.get("login", "")).lower() == owner.lower():
            repos = self._paginate("/user/repos", {"affiliation": "owner", "sort": "pushed"})
            return [r for r in repos if r.get("owner", {}).get("login", "").lower() == owner.lower()]
        return self._paginate(f"/users/{owner}/repos", {"type": "owner", "sort": "pushed"})

    def traffic(self, owner: str, repo: str, metric: str) -> dict[str, Any]:
        if metric not in {"views", "clones", "popular/paths", "referrers"}:
            raise ValueError(f"Unsupported traffic metric: {metric}")
        # GitHub serves referrers under traffic/popular/referrers.
        path = "popular/referrers" if metric == "referrers" else metric
        result = self.get(f"/repos/{owner}/{repo}/traffic/{path}")
        if isinstance(result, list):
            key = "popular/paths" if metric == "popular/paths" else "referrers"
            return {key: result}
        return result if isinstance(result, dict) else {}

    def release_downloads(self, owner: str, repo: str) -> tuple[int, list[dict[str, Any]]]:
        """Return the number of releases and a row per uploaded release asset."""
        releases = self.get(f"/repos/{owner}/{repo}/releases", params={"per_page": 100})
        if not isinstance(releases, list):
            releases = []
        results: list[dict[str, Any]] = []
        for release in releases:
            for asset in release.get("assets", []):
                results.append(
                    {
                        "release": release.get("tag_name", ""),
                        "name": asset.get("name", ""),
                        "download_count": asset.get("download_count", 0),
                        "created_at": asset.get("created_at", ""),
                    }
                )
        return len(releases), results
