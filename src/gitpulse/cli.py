"""Command-line interface for GitPulse."""

from __future__ import annotations

import webbrowser
from pathlib import Path
from typing import Any

import typer
from rich import box
from rich.console import Console
from rich.panel import Panel
from rich.progress import (
    BarColumn,
    MofNCompleteColumn,
    Progress,
    SpinnerColumn,
    TextColumn,
    TimeElapsedColumn,
)
from rich.table import Table

from gitpulse.github_api import GitHubAPIError, GitHubClient
from gitpulse.org import OrgReport, collect_org
from gitpulse.report import render_html
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


SPARK_CHARS = "▁▂▃▄▅▆▇█"


def _spark(values: list[int]) -> str:
    peak = max(values, default=0)
    if not peak:
        return "[dim]" + "·" * len(values) + "[/dim]"
    # Scale min..max so day-to-day movement shows even when traffic never drops to zero.
    low = min(values)
    span = (peak - low) or 1
    return "".join(SPARK_CHARS[round((v - low) / span * (len(SPARK_CHARS) - 1))] for v in values)


def _org_summary(report: OrgReport) -> None:
    views = report.daily("views_daily")
    days = [day for day, _ in views]
    window = f"{days[0]} → {days[-1]}" if days else "no traffic data"
    name = report.profile.get("name") or report.owner
    console.print(
        Panel.fit(
            f"[bold]{name}[/bold] [dim]@{report.owner}[/dim]\n"
            f"{len(report.repos)} repositories · traffic {window}",
            border_style="cyan",
        )
    )

    def tile(label: str, value: int, style: str = "bold") -> Panel:
        return Panel(f"[{style}]{value:,}[/{style}]\n[dim]{label}[/dim]", expand=True, border_style="dim")

    tiles = [
        tile("views · 14d", report.total("views"), "bold cyan"),
        tile("unique visitors*", report.total("view_uniques")),
        tile("clones · 14d", report.total("clones"), "bold magenta"),
        tile("stars", report.total("stars"), "bold yellow"),
        tile("forks", report.total("forks")),
        tile("release downloads", report.total("downloads"), "bold green"),
    ]
    grid = Table.grid(expand=True, padding=(0, 1))
    for _ in range(3):
        grid.add_column(ratio=1)
    grid.add_row(*tiles[:3])
    grid.add_row(*tiles[3:])
    console.print(grid)
    if views:
        console.print(f"  [dim]daily views[/dim]  [cyan]{_spark([c for _, c in views])}[/cyan]")
        clones = [c for _, c in report.daily("clones_daily")]
        console.print(f"  [dim]daily clones[/dim] [magenta]{_spark(clones)}[/magenta]\n")

    table = Table(header_style="bold cyan", box=box.SIMPLE_HEAD, expand=True)
    table.add_column("Repository", overflow="fold")
    table.add_column("Lang", style="dim")
    for column in ("Stars", "Forks", "Views", "Unique", "Clones", "Downloads"):
        table.add_column(column, justify="right")
    table.add_column("14-day views")
    for repo in report.repos:
        ok = repo.traffic_error is None
        na = "[dim]n/a[/dim]"
        table.add_row(
            repo.name + (" [dim](private)[/dim]" if repo.private else ""),
            repo.language or "—",
            f"{repo.stars:,}",
            f"{repo.forks:,}",
            f"{repo.views:,}" if ok else na,
            f"{repo.view_uniques:,}" if ok else na,
            f"{repo.clones:,}" if ok else na,
            f"{repo.downloads:,}" if repo.releases_error is None else na,
            f"[cyan]{_spark([repo.views_daily.get(d, 0) for d in days])}[/cyan]" if ok and days else "",
        )
    console.print(table)

    referrers = report.referrers(limit=5)
    if referrers:
        ref_table = Table(title="Top referrers", header_style="bold cyan", box=box.SIMPLE_HEAD)
        ref_table.add_column("Source")
        ref_table.add_column("Views", justify="right")
        ref_table.add_column("Unique*", justify="right")
        for source, count, uniques in referrers:
            ref_table.add_row(source, f"{count:,}", f"{uniques:,}")
        console.print(ref_table)

    missing = [repo for repo in report.repos if repo.traffic_error]
    if missing:
        console.print(
            f"[yellow]Traffic unavailable for {len(missing)} of {len(report.repos)} repositories[/yellow] "
            "[dim](the token needs Administration: Read or push access). See the dashboard for details.[/dim]"
        )
    console.print("[dim]*Unique counts are summed per repository, so one person can be counted more than once.[/dim]")


@app.command("org")
def org_dashboard(
    owner: str = typer.Argument(..., help="Organization or user login."),
    output: str = typer.Option(
        "", "--output", "-o", help="HTML file to write. Defaults to gitpulse-OWNER.html."
    ),
    all_repos: bool = typer.Option(False, "--all", help="Include forks and archived repositories."),
    open_browser: bool = typer.Option(False, "--open", help="Open the dashboard in your browser."),
    save: bool = typer.Option(False, "--save", help="Also save views and clones snapshots to local history."),
    workers: int = typer.Option(8, min=1, max=32, help="Repositories to fetch in parallel."),
) -> None:
    """Build an HTML dashboard of traffic, stars, and downloads across an organization."""
    client = _client()
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        MofNCompleteColumn(),
        TimeElapsedColumn(),
        console=console,
        transient=True,
    ) as progress:
        task = progress.add_task(f"Listing repositories for {owner}", total=None)
        report = _run(
            lambda: collect_org(
                client,
                owner,
                include_all=all_repos,
                workers=workers,
                on_start=lambda count: progress.update(
                    task, total=count, description=f"Fetching stats for {owner}"
                ),
                on_repo=lambda repo: progress.update(task, advance=1, description=repo.name),
            )
        )
    if not report.repos:
        console.print(f"No repositories found for [bold]{owner}[/bold].")
        raise typer.Exit(code=1)

    _org_summary(report)

    if save:
        store = SnapshotStore()
        saved = 0
        for repo in report.traffic_repos:
            for metric, payload in repo.raw_traffic.items():
                store.save(repo.owner, repo.name, metric, payload)
            saved += 1
        console.print(f"[green]Saved snapshots for {saved} repositories.[/green]")

    path = Path(output or f"gitpulse-{report.owner}.html").expanduser().resolve()
    path.write_text(render_html(report), encoding="utf-8")
    console.print(f"\n[bold green]✓[/bold green] Dashboard written to [link={path.as_uri()}]{path}[/link]")
    if open_browser:
        webbrowser.open(path.as_uri())


if __name__ == "__main__":
    app()
