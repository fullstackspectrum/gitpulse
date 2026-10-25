"""Small GitHub REST API client for GitPulse."""

from __future__ import annotations

import os
from typing import Any

import requests


class GitHubAPIError(RuntimeError):
    """An error returned by the GitHub API or the local HTTP client."""


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
                "User-Agent": "gitpulse/0.1.0",
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
                f"GitHub returned 404. The repository may not exist, or {hint}{suffix}"
            )
        if response.status_code == 403:
            sso = response.headers.get("X-GitHub-SSO")
            if sso:
                raise GitHubAPIError(
                    "GitHub denied this request because the organization requires SAML SSO. "
                    f"Authorize your token for the organization ({sso}).{suffix}"
                )
            hint = (
                "Traffic endpoints need a token with Administration: Read on this repository "
                "(classic tokens: the repo scope and push or admin access)."
                if is_traffic
                else "Check that your token includes this repository and has Contents: Read "
                "(classic tokens: the repo scope)."
            )
            raise GitHubAPIError(f"GitHub denied this request. {hint}{suffix}")
        if not response.ok:
            raise GitHubAPIError(f"GitHub API returned HTTP {response.status_code}.{suffix}")
        try:
            return response.json()
        except ValueError as exc:
            raise GitHubAPIError("GitHub returned an invalid JSON response.") from exc

    def list_repositories(self) -> list[dict[str, Any]]:
        repos: list[dict[str, Any]] = []
        page = 1
        while True:
            batch = self.get(
                "/user/repos",
                params={
                    "per_page": 100,
                    "page": page,
                    "sort": "updated",
                    "affiliation": "owner,collaborator,organization_member",
                },
            )
            if not isinstance(batch, list) or not batch:
                break
            repos.extend(batch)
            if len(batch) < 100:
                break
            page += 1
        return repos

    def traffic(self, owner: str, repo: str, metric: str) -> dict[str, Any]:
        if metric not in {"views", "clones", "popular/paths", "referrers"}:
            raise ValueError(f"Unsupported traffic metric: {metric}")
        result = self.get(f"/repos/{owner}/{repo}/traffic/{metric}")
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
