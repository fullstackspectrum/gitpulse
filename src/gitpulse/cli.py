"""Command-line interface for GitPulse."""

from __future__ import annotations

from typing import Any

import typer
from rich.console import Console
from rich.table import Table

from gitpulse.github_api import GitHubAPIError, GitHubClient
from gitpulse.storage import SnapshotStore

app = typer.Typer(
    name="gitpulse",
    help="Local GitHub repository traffic and release analytics.",
    no_args_is_help=True,
)
console = Console()


def _client() -> GitHubClient:
    try:
        return GitHubClient()
    except GitHubAPIError as exc:
        console.print(f"[red]Error:[/red] {exc}")
        raise typer.Exit(code=1) from exc


def _run(action: Any) -> Any:
    try:
        return action()
    except GitHubAPIError as exc:
        console.print(f"[red]Error:[/red] {exc}")
        raise typer.Exit(code=1) from exc


def _repo_parts(repository: str) -> tuple[str, str]:
    parts = repository.strip("/").split("/")
    if len(parts) != 2 or not all(parts):
        raise typer.BadParameter("Use the OWNER/REPO format, for example octocat/Hello-World")
    return parts[0], parts[1]


def _traffic_table(owner: str, repo: str, metric: str, data: dict[str, Any]) -> Table:
    table = Table(title=f"{owner}/{repo} · {metric}", header_style="bold cyan")
    if metric in {"views", "clones"}:
        table.add_column("Date")
        table.add_column("Count", justify="right")
        table.add_column("Unique", justify="right")
        for item in data.get("views", data.get("clones", [])):
            table.add_row(str(item.get("timestamp", ""))[:10], str(item.get("count", 0)), str(item.get("uniques", 0)))
        if not table.row_count:
            table.add_row("No recent data", "0", "0")
    elif metric == "referrers":
        table.add_column("Referrer")
        table.add_column("Views", justify="right")
        table.add_column("Unique", justify="right")
        for item in data.get("referrers", []):
            table.add_row(str(item.get("referrer", "")), str(item.get("count", 0)), str(item.get("uniques", 0)))
        if not table.row_count:
            table.add_row("No recent data", "0", "0")
    else:
        table.add_column("Path")
        table.add_column("Title")
        table.add_column("Views", justify="right")
        table.add_column("Unique", justify="right")
        for item in data.get("popular/paths", []):
            table.add_row(str(item.get("path", "")), str(item.get("title", "")), str(item.get("count", 0)), str(item.get("uniques", 0)))
        if not table.row_count:
            table.add_row("No recent data", "", "0", "0")
    return table


@app.command("repos")
def list_repos(
    all_repos: bool = typer.Option(False, "--all", help="Include forks and archived repositories."),
) -> None:
    """List repositories the authenticated account can access."""
    repos = _run(_client().list_repositories)
    if not all_repos:
        repos = [repo for repo in repos if not repo.get("fork") and not repo.get("archived")]
    table = Table(title="Your repositories", header_style="bold cyan")
    table.add_column("Repository")
    table.add_column("Visibility")
    table.add_column("Stars", justify="right")
    table.add_column("Forks", justify="right")
    table.add_column("Updated")
    for repo in repos:
        table.add_row(
            repo.get("full_name", ""),
            "private" if repo.get("private") else "public",
            str(repo.get("stargazers_count", 0)),
            str(repo.get("forks_count", 0)),
            str(repo.get("updated_at", ""))[:10],
        )
    console.print(table)
    console.print(f"[dim]{len(repos)} repositories[/dim]")


@app.command()
def traffic(
    repository: str = typer.Argument(..., help="Repository in OWNER/REPO format."),
    metric: str = typer.Option("views", "--metric", "-m", help="views, clones, referrers, or popular/paths"),
    save: bool = typer.Option(False, "--save", help="Save this response to local history."),
) -> None:
    """Show recent views, clones, referrers, or popular paths."""
    owner, repo = _repo_parts(repository)
    if metric not in {"views", "clones", "referrers", "popular/paths"}:
        raise typer.BadParameter("Choose views, clones, referrers, or popular/paths")
    client = _client()
    data = _run(lambda: client.traffic(owner, repo, metric))
    console.print(_traffic_table(owner, repo, metric, data))
    if save and metric in {"views", "clones"}:
        SnapshotStore().save(owner, repo, metric, data)
        console.print("[green]Snapshot saved locally.[/green]")
    console.print("[dim]GitHub provides aggregate traffic data, not visitor identities; traffic history is typically limited to 14 days.[/dim]")


@app.command()
def snapshot(
    repository: str = typer.Argument(..., help="Repository in OWNER/REPO format."),
) -> None:
    """Fetch and save today's views and clone traffic snapshots."""
    owner, repo = _repo_parts(repository)
    client = _client()
    store = SnapshotStore()
    for metric in ("views", "clones"):
        data = _run(lambda metric=metric: client.traffic(owner, repo, metric))
        store.save(owner, repo, metric, data)
        console.print(_traffic_table(owner, repo, metric, data))
    console.print("[green]Snapshots saved. Run this regularly to build longer-term history.[/green]")


@app.command()
def history(
    repository: str = typer.Argument(..., help="Repository in OWNER/REPO format."),
    metric: str = typer.Option("views", "--metric", "-m", help="views or clones"),
    limit: int = typer.Option(30, min=1, max=1000, help="Number of saved snapshots to show."),
) -> None:
    """Show snapshots collected on this machine."""
    owner, repo = _repo_parts(repository)
    if metric not in {"views", "clones"}:
        raise typer.BadParameter("History is available for views or clones")
    rows = SnapshotStore().history(owner, repo, metric, limit)
    table = Table(title=f"Local history · {owner}/{repo} · {metric}", header_style="bold cyan")
    table.add_column("Collected at")
    table.add_column("14-day total", justify="right")
    table.add_column("Sum of daily uniques*", justify="right")
    series_key = metric
    found = False
    for row in rows:
        series = row.get(series_key, [])
        total = sum(item.get("count", 0) for item in series)
        uniques = sum(item.get("uniques", 0) for item in series)
        table.add_row(row.get("fetched_at", ""), str(total), str(uniques))
        found = True
    if not found:
        console.print("No snapshots yet. Run `gitpulse snapshot OWNER/REPO` to start collecting history.")
    else:
        console.print(table)
        console.print("[dim]*Daily unique counts can overlap; this is not a distinct-visitor total.[/dim]")


@app.command("downloads")
def release_downloads(
    repository: str = typer.Argument(..., help="Repository in OWNER/REPO format."),
) -> None:
    """Show GitHub release asset download counts (not Homebrew install counts)."""
    owner, repo = _repo_parts(repository)
    release_count, assets = _run(lambda: _client().release_downloads(owner, repo))
    table = Table(title=f"Release asset downloads · {owner}/{repo}", header_style="bold cyan")
    table.add_column("Release")
    table.add_column("Asset")
    table.add_column("Downloads", justify="right")
    for asset in assets:
        table.add_row(asset["release"], asset["name"], str(asset["download_count"]))
    if not release_count:
        console.print("No releases found.")
    elif not assets:
        console.print(
            f"Found {release_count} release(s), but none have uploaded assets. GitHub does not "
            "report download counts for the automatic source code archives."
        )
    else:
        console.print(table)
    console.print("[dim]Release asset counts do not indicate Homebrew formula installs or identify downloaders.[/dim]")


if __name__ == "__main__":
    app()
