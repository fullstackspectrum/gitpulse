"""Render an OrgReport as a self-contained HTML dashboard in the Full-Stack-Spectrum style.

Everything is inline except the two web fonts, which fall back to system fonts offline.
"""

from __future__ import annotations

import json
import math
from html import escape
from typing import Any

from gitpulse.org import OrgReport, RepoStats

# Categorical slots follow the five-colour spectrum, cool to hot; a sixth slot is "Other".
SERIES = 6


def compact(value: float) -> str:
    """Format 1284 -> 1,284 and 12940 -> 12.9K."""
    for threshold, divisor, suffix in ((1e9, 1e9, "B"), (1e6, 1e6, "M"), (1e4, 1e3, "K")):
        if abs(value) >= threshold:
            return f"{value / divisor:.1f}".rstrip("0").rstrip(".") + suffix
    return f"{int(value):,}"


def nice_ticks(maximum: int, count: int = 4) -> list[int]:
    """Round axis ticks from zero up to a clean value at or above MAXIMUM."""
    if maximum <= 0:
        return [0, 1]
    raw = maximum / count
    magnitude = 10 ** math.floor(math.log10(raw))
    step = next(m * magnitude for m in (1, 2, 2.5, 5, 10) if m * magnitude >= raw)
    step = max(1, int(step))
    top = step * math.ceil(maximum / step)
    return list(range(0, top + 1, step))


def _attr(text: Any) -> str:
    return escape(str(text), quote=True)


def _short_date(day: str) -> str:
    months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
    return f"{months[int(day[5:7]) - 1]} {int(day[8:10])}"


def _stat_tile(label: str, value: int, note: str = "") -> str:
    note_html = f'<div class="tile-note">{escape(note)}</div>' if note else ""
    return (
        f'<div class="tile"><div class="tile-label">{escape(label)}</div>'
        f'<div class="tile-value" title="{value:,}">{compact(value)}</div>{note_html}</div>'
    )


def _bar_list(rows: list[tuple[str, int, str, str]], empty: str) -> str:
    """Horizontal bars. Each row is (label, value, link, tooltip)."""
    if not rows:
        return f'<p class="empty">{escape(empty)}</p>'
    peak = max(value for _, value, _, _ in rows) or 1
    items = []
    for label, value, link, tip in rows:
        name = (
            f'<a href="{_attr(link)}" target="_blank" rel="noopener">{escape(label)}</a>'
            if link
            else escape(label)
        )
        width = max(0.5, value / peak * 100)
        items.append(
            f'<li class="bar-row" tabindex="0" data-tip="{_attr(tip)}">'
            f'<span class="bar-label">{name}</span>'
            f'<span class="bar-track"><span class="bar" style="width:{width:.2f}%"></span></span>'
            f'<span class="bar-value">{compact(value)}</span></li>'
        )
    return f'<ul class="bars">{"".join(items)}</ul>'


def _line_chart(series: list[tuple[str, str, list[tuple[str, int]]]]) -> str:
    """Daily views/clones on one count axis. Each series is (name, css var, [(day, count)])."""
    days = [day for day, _ in series[0][2]] if series and series[0][2] else []
    if not days:
        return '<p class="empty">No traffic data available. The token may lack Administration: Read.</p>'
    width, height = 1000, 300
    peak = max((count for _, _, points in series for _, count in points), default=0)
    ticks = nice_ticks(peak)
    top = ticks[-1]
    step_x = width / max(1, len(days) - 1)

    def xy(i: int, count: int) -> tuple[float, float]:
        return i * step_x, height - (count / top * height)

    grid = "".join(
        f'<line class="grid" x1="0" x2="{width}" y1="{height - t / top * height:.1f}" '
        f'y2="{height - t / top * height:.1f}" />'
        for t in ticks
    )
    paths, end_labels, legend = [], [], []
    for index, (name, var, points) in enumerate(series):
        coords = [xy(i, count) for i, (_, count) in enumerate(points)]
        line = " ".join(f"{x:.1f},{y:.1f}" for x, y in coords)
        area = f"0,{height} {line} {width},{height}"
        if index == 0:
            paths.append(f'<polygon class="area" points="{area}" style="fill:var({var})" />')
        paths.append(f'<polyline class="line" points="{line}" style="stroke:var({var})" />')
        last = points[-1][1]
        end_labels.append(
            f'<span class="end-label" style="top:{(1 - last / top) * 100:.2f}%">'
            f'{compact(last)}</span>'
        )
        legend.append(
            f'<span class="legend-item"><span class="key-line" style="background:var({var})"></span>'
            f"{escape(name)}</span>"
        )
    y_labels = "".join(
        f'<span class="y-tick" style="top:{(1 - t / top) * 100:.2f}%">{compact(t)}</span>'
        for t in ticks
    )
    label_every = max(1, math.ceil(len(days) / 7))
    # Every other label carries .alt so narrow screens can drop it.
    x_labels = "".join(
        f'<span class="x-tick{" alt" if (len(days) - 1 - i) // label_every % 2 else ""}" '
        f'style="left:{i / max(1, len(days) - 1) * 100:.2f}%">{_short_date(day)}</span>'
        for i, day in enumerate(days)
        if (len(days) - 1 - i) % label_every == 0
    )
    data = {
        "days": days,
        "top": top,
        "series": [
            {"name": name, "var": var, "values": [count for _, count in points]}
            for name, var, points in series
        ],
    }
    return f"""
<div class="legend">{"".join(legend)}</div>
<div class="linechart" data-chart='{_attr(json.dumps(data))}'>
  <div class="y-axis">{y_labels}</div>
  <div class="plot" tabindex="0" aria-label="Daily views and clones across all repositories">
    <svg viewBox="0 0 {width} {height}" preserveAspectRatio="none" aria-hidden="true">
      {grid}{"".join(paths)}
    </svg>
    <div class="end-labels">{"".join(end_labels)}</div>
    <div class="crosshair" hidden></div>
  </div>
  <div class="x-axis">{x_labels}</div>
</div>"""


def _languages(report: OrgReport) -> str:
    langs = report.languages()
    if not langs:
        return '<p class="empty">No repositories.</p>'
    shown = langs[: SERIES - 1]
    other = sum(count for _, count in langs[SERIES - 1 :])
    if other:
        shown.append(("Other", other))
    total = sum(count for _, count in shown)
    blocks, legend = [], []
    for slot, (name, count) in enumerate(shown, start=1):
        var = "--muted-fill" if name == "Other" else f"--series-{slot}"
        share = count / total * 100
        ink = " other" if name == "Other" else ""
        label = f"{share:.0f}%" if share >= 9 else ""
        blocks.append(
            f'<span class="segment{ink}" tabindex="0" style="flex:{count};background:var({var})" '
            f'data-tip="{_attr(f"{name}: {count} repos ({share:.0f}%)")}">{label}</span>'
        )
        legend.append(
            f'<span class="legend-item"><span class="swatch" style="background:var({var})"></span>'
            f"{escape(name)} <span class='muted'>{count}</span></span>"
        )
    return (
        f'<div class="segmented" role="img" aria-label="Repositories by primary language">'
        f'{"".join(blocks)}</div><div class="legend wrap">{"".join(legend)}</div>'
    )


def _sparkline(values: list[int]) -> str:
    if not values or not any(values):
        return '<span class="muted">—</span>'
    peak = max(values)
    step = 100 / max(1, len(values) - 1)
    points = " ".join(f"{i * step:.1f},{22 - v / peak * 20:.1f}" for i, v in enumerate(values))
    return (
        '<svg class="spark" viewBox="0 0 100 24" preserveAspectRatio="none" aria-hidden="true">'
        f'<polyline points="{points}" /></svg>'
    )


def _repo_row(repo: RepoStats, days: list[str]) -> str:
    def num(value: int, available: bool = True) -> str:
        if not available:
            return '<td class="num muted" data-sort="-1">n/a</td>'
        return f'<td class="num" data-sort="{value}">{value:,}</td>'

    traffic = repo.traffic_error is None
    badges = "".join(
        f'<span class="badge">{label}</span>'
        for label, on in (("private", repo.private), ("fork", repo.fork), ("archived", repo.archived))
        if on
    )
    spark = _sparkline([repo.views_daily.get(day, 0) for day in days]) if traffic else ""
    return f"""<tr>
<td data-sort="{_attr(repo.name.lower())}"><a href="{_attr(repo.url)}" target="_blank" rel="noopener">{escape(repo.name)}</a>{badges}
<div class="desc">{escape(repo.description)}</div></td>
<td data-sort="{_attr(repo.language.lower())}">{escape(repo.language) or '<span class="muted">—</span>'}</td>
{num(repo.stars)}{num(repo.forks)}{num(repo.open_issues)}
{num(repo.views, traffic)}{num(repo.view_uniques, traffic)}{num(repo.clones, traffic)}
{num(repo.downloads, repo.releases_error is None)}
<td class="spark-cell">{spark}</td>
<td data-sort="{_attr(repo.pushed_at)}" class="nowrap">{escape(repo.pushed_at[:10])}</td>
</tr>"""


def render_html(report: OrgReport) -> str:
    owner = report.owner
    profile = report.profile
    display = profile.get("name") or owner
    views_daily = report.daily("views_daily")
    clones_daily = report.daily("clones_daily")
    days = [day for day, _ in views_daily]
    window = f"{_short_date(days[0])} – {_short_date(days[-1])}" if days else "no traffic data"
    traffic_count = len(report.traffic_repos)
    missing = [repo for repo in report.repos if repo.traffic_error]
    avatar = profile.get("avatar_url")
    avatar_html = f'<img class="avatar" src="{_attr(avatar)}" alt="" />' if avatar else ""
    generated = report.generated_at.strftime("%Y-%m-%d %H:%M UTC")

    tiles = "".join(
        [
            _stat_tile("Unique visitors", report.total("view_uniques"), "summed per repo"),
            _stat_tile("Clones", report.total("clones"), f"{report.total('clone_uniques'):,} unique cloners"),
            _stat_tile("Stars", report.total("stars")),
            _stat_tile("Forks", report.total("forks")),
            _stat_tile("Release downloads", report.total("downloads"), "all-time, uploaded assets"),
            _stat_tile("Open issues & PRs", report.total("open_issues")),
        ]
    )

    def repo_bars(attr: str, unit: str) -> list[tuple[str, int, str, str]]:
        return [
            (repo.name, getattr(repo, attr), repo.url, f"{repo.full_name}: {getattr(repo, attr):,} {unit}")
            for repo in report.top(attr)
        ]

    referrer_rows = [
        (name, count, "", f"{name}: {count:,} views, {uniques:,} unique (summed per repo)")
        for name, count, uniques in report.referrers()
    ]
    rows = "".join(_repo_row(repo, days) for repo in report.repos)
    missing_html = ""
    if missing:
        items = "".join(
            f"<li><strong>{escape(repo.full_name)}</strong>: {escape(repo.traffic_error or '')}</li>"
            for repo in missing
        )
        missing_html = (
            f'<details class="card notice"><summary>Traffic unavailable for {len(missing)} of '
            f"{len(report.repos)} repositories</summary><ul>{items}</ul></details>"
        )

    line = _line_chart(
        [("Views", "--blue", views_daily), ("Clones", "--orange", clones_daily)]
    )
    return TEMPLATE.format(
        title=escape(f"{display} · GitPulse"),
        avatar=avatar_html,
        display=escape(display),
        owner=escape(owner),
        owner_url=_attr(profile.get("html_url") or f"https://github.com/{owner}"),
        generated=generated,
        repo_count=len(report.repos),
        traffic_count=traffic_count,
        window=window,
        hero=compact(report.total("views")),
        hero_full=f"{report.total('views'):,}",
        tiles=tiles,
        line=line,
        top_views=_bar_list(repo_bars("views", "views"), "No views in the traffic window."),
        top_stars=_bar_list(repo_bars("stars", "stars"), "No stars yet."),
        languages=_languages(report),
        referrers=_bar_list(referrer_rows, "No referrers in the traffic window."),
        downloads=_bar_list(repo_bars("downloads", "downloads"), "No release asset downloads."),
        rows=rows,
        missing=missing_html,
        css=CSS,
        js=JS,
    )


CSS = """
:root {
  color-scheme: dark;
  /* Full-Stack-Spectrum tokens (fullstackspectrum.com). Dark only, by design. */
  --bg: #0a0d12; --bg-elev: #10151d; --bg-card: #121821;
  --line: #222b38; --line-strong: #2f3a4b;
  --text: #eef1f6; --text-dim: #9aa4b2; --text-faint: #646f7f;
  --blue: #4f8cff; --blue-soft: #8fb4ff; --yellow: #f5c84c; --orange: #ff8a3d; --red: #ff4d5e;
  --wash: rgba(255,255,255,0.04); --muted-fill: #646f7f;
  /* Categorical slots run the spectrum cool to hot. */
  --series-1: var(--blue); --series-2: var(--blue-soft); --series-3: var(--yellow);
  --series-4: var(--orange); --series-5: var(--red);
  --font-display: "Space Grotesk", system-ui, -apple-system, "Segoe UI", sans-serif;
  --font-mono: "JetBrains Mono", ui-monospace, SFMono-Regular, Menlo, monospace;
}
* { box-sizing: border-box; }
body { margin: 0; color: var(--text); background-color: var(--bg);
  background-image: radial-gradient(circle at 1px 1px, rgba(255,255,255,0.07) 1px, transparent 0);
  background-size: 28px 28px;
  font: 15px/1.6 var(--font-display); -webkit-font-smoothing: antialiased; }
a { color: inherit; text-decoration: none; transition: color .15s; }
a:hover { color: var(--blue-soft); }
:focus-visible { outline: 2px solid var(--blue); outline-offset: 3px; border-radius: 4px; }
::selection { background: var(--red); color: var(--bg); }
.wrap-page { max-width: 1160px; margin: 0 auto; padding: 48px clamp(16px, 4vw, 40px) 64px; }
.spectrum { display: flex; gap: 6px; margin-bottom: 28px; }
.spectrum span { width: 28px; height: 8px; border-radius: 1px; }
.spectrum span:nth-child(1) { background: var(--blue); }
.spectrum span:nth-child(2) { background: var(--blue-soft); }
.spectrum span:nth-child(3) { background: var(--yellow); }
.spectrum span:nth-child(4) { background: var(--orange); }
.spectrum span:nth-child(5) { background: var(--red); }
header { display: flex; align-items: center; gap: 20px; margin-bottom: 32px; }
.eyebrow { font: 13px/1.4 var(--font-mono); color: var(--red); letter-spacing: .04em; margin-bottom: 8px; }
.eyebrow::before { content: "// "; color: var(--text-faint); }
.avatar { width: 64px; height: 64px; border-radius: 10px; border: 1px solid var(--line-strong); }
h1 { font-size: 40px; line-height: 1.05; margin: 0; font-weight: 700; letter-spacing: -0.03em; }
h2 { font-size: 19px; line-height: 1.3; margin: 0 0 4px; font-weight: 700; letter-spacing: -0.01em; }
.sub { color: var(--text-dim); font: 13px/1.6 var(--font-mono); margin-top: 8px; }
.card { background: var(--bg-card); border: 1px solid var(--line); border-radius: 10px; padding: 24px; }
.card-sub { color: var(--text-dim); font-size: 13px; margin-bottom: 18px; }
.overview { display: grid; grid-template-columns: minmax(220px, 1fr) 3fr; gap: 16px; margin-bottom: 16px; }
.hero-label, .tile-label { color: var(--text-dim); font: 12px/1.4 var(--font-mono); text-transform: lowercase; }
.hero-value { font-size: 64px; font-weight: 700; line-height: 1; letter-spacing: -0.04em; margin: 14px 0 10px; }
.tiles { display: grid; grid-template-columns: repeat(3, 1fr); gap: 1px; background: var(--line);
  border-radius: 10px; overflow: hidden; border: 1px solid var(--line); }
.tile { background: var(--bg-card); padding: 18px 22px; }
.tile-value { font-size: 28px; font-weight: 700; letter-spacing: -0.02em; margin-top: 4px; }
.tile-note { color: var(--text-dim); font-size: 12px; }
.grid-2 { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; margin-top: 16px; }
.full { margin-top: 16px; }
.legend { display: flex; gap: 16px; font: 12px/1.4 var(--font-mono); color: var(--text-dim); margin-bottom: 12px; }
.legend.wrap { flex-wrap: wrap; gap: 6px 16px; margin: 14px 0 0; }
.legend-item { display: inline-flex; align-items: center; gap: 6px; }
.key-line { width: 14px; height: 2px; border-radius: 1px; }
.swatch { width: 10px; height: 10px; border-radius: 2px; }
.muted { color: var(--text-dim); }
.empty { color: var(--text-dim); margin: 24px 0; text-align: center; }
.linechart { display: grid; grid-template-columns: 44px 1fr; grid-template-rows: 240px auto; }
.y-axis { position: relative; }
.y-tick, .end-label, .x-tick { position: absolute; font: 11px/1.4 var(--font-mono); color: var(--text-dim);
  font-variant-numeric: tabular-nums; white-space: nowrap; }
.y-tick { right: 8px; transform: translateY(-50%); }
.plot { position: relative; outline: none; margin-right: 40px; }
.plot svg { width: 100%; height: 100%; display: block; overflow: visible; }
.plot .grid { stroke: var(--line); stroke-width: 1; vector-effect: non-scaling-stroke; }
.plot .line { fill: none; stroke-width: 2; stroke-linejoin: round; stroke-linecap: round;
  vector-effect: non-scaling-stroke; }
.plot .area { opacity: 0.12; }
.end-labels { position: absolute; top: 0; bottom: 0; left: 100%; }
.end-label { left: 8px; transform: translateY(-50%); color: var(--text); }
.x-axis { grid-column: 2; position: relative; height: 22px; margin-right: 40px; }
.x-tick { top: 6px; transform: translateX(-50%); }
.crosshair { position: absolute; top: 0; bottom: 0; width: 1px; background: var(--line-strong); pointer-events: none; }
.dot { position: absolute; width: 10px; height: 10px; border-radius: 50%; transform: translate(-50%, -50%);
  box-shadow: 0 0 0 2px var(--bg-card); pointer-events: none; }
.bars { list-style: none; margin: 0; padding: 0; display: grid; gap: 2px; }
.bar-row { display: grid; grid-template-columns: minmax(90px, min(34%, 220px)) 1fr 52px; align-items: center; gap: 10px;
  padding: 5px 6px; border-radius: 6px; outline: none; }
.bar-row:hover, .bar-row:focus-visible { background: var(--wash); }
.bar-label { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; color: var(--text-dim); font-size: 14px; }
.bar-track { height: 10px; }
.bar { display: block; height: 100%; background: var(--blue); border-radius: 0 2px 2px 0; }
.bar-value { text-align: right; font: 13px/1.4 var(--font-mono); font-variant-numeric: tabular-nums; }
.segmented { display: flex; gap: 2px; height: 28px; }
.segment { min-width: 3px; border-radius: 4px; color: var(--bg); font: 600 12px/1 var(--font-mono);
  padding-left: 8px; display: flex; align-items: center; overflow: hidden; outline: none; }
.segment.other { color: var(--text); }
.segment:hover, .segment:focus-visible { filter: brightness(1.08); }
.table-head { display: flex; align-items: end; justify-content: space-between; gap: 12px; flex-wrap: wrap; }
.search { background: var(--bg); color: var(--text); border: 1px solid var(--line-strong); border-radius: 8px;
  padding: 8px 12px; font: 13px/1.4 var(--font-mono); min-width: 240px; }
.search::placeholder { color: var(--text-dim); }
.search:focus-visible { border-color: var(--blue); }
.table-scroll { overflow-x: auto; margin-top: 14px; }
table { width: 100%; border-collapse: collapse; font-size: 14px; }
th { text-align: left; font: 500 12px/1.4 var(--font-mono); text-transform: lowercase; color: var(--text-dim);
  padding: 8px 10px; border-bottom: 1px solid var(--line-strong); cursor: pointer; user-select: none; white-space: nowrap; }
th:hover, th[aria-sort] { color: var(--text); }
th.num { text-align: right; }
th[aria-sort]::after { content: " ↓"; color: var(--red); }
th[aria-sort="ascending"]::after { content: " ↑"; }
td { padding: 10px; border-bottom: 1px solid var(--line); vertical-align: top; }
td.num { text-align: right; font: 13px/1.6 var(--font-mono); font-variant-numeric: tabular-nums; }
tr:hover td { background: var(--wash); }
td a { font-weight: 600; }
.desc { color: var(--text-dim); font-size: 13px; max-width: 360px; overflow: hidden; text-overflow: ellipsis;
  white-space: nowrap; }
.badge { font: 600 10px/1.3 var(--font-mono); letter-spacing: .04em; color: var(--text-dim); background: var(--bg-elev);
  border: 1px solid var(--line); border-radius: 4px; padding: 2px 6px; margin-left: 8px; vertical-align: 2px; }
.nowrap { white-space: nowrap; font: 13px/1.6 var(--font-mono); color: var(--text-dim); }
.spark-cell { width: 110px; }
.spark { width: 100px; height: 24px; display: block; }
.spark polyline { fill: none; stroke: var(--blue); stroke-width: 1.5; vector-effect: non-scaling-stroke; }
.notice { margin-top: 16px; color: var(--text-dim); font-size: 14px; }
.notice summary { cursor: pointer; color: var(--text); }
.notice summary::marker { color: var(--yellow); }
.notice li { margin: 4px 0; }
footer { color: var(--text-dim); font-size: 13px; margin-top: 40px; padding-top: 24px; border-top: 1px solid var(--line); }
footer p { margin: 0 0 20px; max-width: 80ch; }
.foot-row { display: flex; align-items: center; justify-content: space-between; gap: 12px 24px; flex-wrap: wrap;
  font: 13px/1.4 var(--font-mono); }
.brand { display: inline-flex; align-items: center; gap: 12px; color: var(--text); font: 700 15px/1 var(--font-display);
  letter-spacing: -0.01em; }
/* Layered Core mark: the front square with a red core; offset shadows draw the yellow and blue layers behind it. */
.mark { --s: 18px; --b: 2.25px; --o: 4.5px; --core: 6px;
  width: var(--s); height: var(--s); flex: none; margin: calc(var(--o) * 2) calc(var(--o) * 2) 0 0;
  display: grid; place-items: center; background: var(--bg); border: var(--b) solid var(--text);
  border-radius: calc(var(--s) * 0.214);
  box-shadow: var(--o) calc(var(--o) * -1) 0 calc(var(--b) * -1) var(--bg), var(--o) calc(var(--o) * -1) 0 0 var(--yellow),
    calc(var(--o) * 2) calc(var(--o) * -2) 0 calc(var(--b) * -1) var(--bg), calc(var(--o) * 2) calc(var(--o) * -2) 0 0 var(--blue); }
.mark::after { content: ""; width: var(--core); height: var(--core); background: var(--red); border-radius: 1px; }
#tooltip { position: fixed; z-index: 10; pointer-events: none; background: var(--bg-elev); color: var(--text);
  border: 1px solid var(--line-strong); border-radius: 8px; padding: 8px 10px; font: 12px/1.5 var(--font-mono);
  max-width: 300px; }
#tooltip .tt-row { display: flex; align-items: center; gap: 6px; }
#tooltip .tt-val { margin-left: auto; padding-left: 12px; font-variant-numeric: tabular-nums; font-weight: 600; }
@media (max-width: 860px) {
  .overview, .grid-2 { grid-template-columns: 1fr; }
  .tiles { grid-template-columns: repeat(2, 1fr); }
}
@media (max-width: 520px) {
  .wrap-page { padding: 28px 16px 48px; }
  .hero-value { font-size: 52px; }
  .search { min-width: 0; width: 100%; }
  h1 { font-size: 28px; }
  .avatar { width: 44px; height: 44px; }
  .x-tick.alt { display: none; }
}
@media (prefers-reduced-motion: reduce) {
  * { transition: none !important; }
}
"""

JS = r"""
(() => {
  const tip = document.getElementById('tooltip');
  const fmt = (n) => n.toLocaleString();
  const show = (html, x, y) => {
    tip.innerHTML = html; tip.hidden = false;
    const r = tip.getBoundingClientRect();
    tip.style.left = Math.min(x + 14, innerWidth - r.width - 8) + 'px';
    tip.style.top = Math.max(8, y - r.height - 10) + 'px';
  };
  const hide = () => { tip.hidden = true; };
  const esc = (s) => s.replace(/[&<>"]/g, (c) => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));

  document.querySelectorAll('[data-tip]').forEach((el) => {
    const at = (e) => show(esc(el.dataset.tip), e.clientX, e.clientY);
    el.addEventListener('mousemove', at);
    el.addEventListener('mouseleave', hide);
    el.addEventListener('focus', () => { const r = el.getBoundingClientRect(); show(esc(el.dataset.tip), r.left, r.top); });
    el.addEventListener('blur', hide);
  });

  document.querySelectorAll('.linechart').forEach((chart) => {
    const data = JSON.parse(chart.dataset.chart);
    const plot = chart.querySelector('.plot');
    const cross = chart.querySelector('.crosshair');
    const dots = data.series.map((s) => {
      const d = document.createElement('div');
      d.className = 'dot'; d.hidden = true; d.style.background = `var(${s.var})`;
      plot.appendChild(d); return d;
    });
    const n = data.days.length;
    let idx = n - 1;
    const render = () => {
      const r = plot.getBoundingClientRect();
      const x = n > 1 ? idx / (n - 1) : 0;
      cross.hidden = false; cross.style.left = (x * 100) + '%';
      data.series.forEach((s, i) => {
        dots[i].hidden = false;
        dots[i].style.left = (x * 100) + '%';
        dots[i].style.top = ((1 - s.values[idx] / data.top) * 100) + '%';
      });
      const rows = data.series.map((s) =>
        `<div class="tt-row"><span class="key-line" style="background:var(${s.var})"></span>${s.name}` +
        `<span class="tt-val">${fmt(s.values[idx])}</span></div>`).join('');
      const day = new Date(data.days[idx] + 'T00:00:00Z').toLocaleDateString(undefined,
        { weekday: 'short', month: 'short', day: 'numeric', timeZone: 'UTC' });
      show(`<div class="muted">${day}</div>${rows}`, r.left + x * r.width, r.top + 20);
    };
    const clear = () => { cross.hidden = true; dots.forEach((d) => d.hidden = true); hide(); };
    plot.addEventListener('mousemove', (e) => {
      const r = plot.getBoundingClientRect();
      idx = Math.max(0, Math.min(n - 1, Math.round((e.clientX - r.left) / r.width * (n - 1))));
      render();
    });
    plot.addEventListener('mouseleave', clear);
    plot.addEventListener('focus', render);
    plot.addEventListener('blur', clear);
    plot.addEventListener('keydown', (e) => {
      if (e.key === 'ArrowLeft') { idx = Math.max(0, idx - 1); render(); e.preventDefault(); }
      if (e.key === 'ArrowRight') { idx = Math.min(n - 1, idx + 1); render(); e.preventDefault(); }
    });
  });

  const table = document.querySelector('#repos table');
  const body = table.tBodies[0];
  table.querySelectorAll('th').forEach((th, col) => {
    th.addEventListener('click', () => {
      const asc = th.getAttribute('aria-sort') === 'descending';
      table.querySelectorAll('th').forEach((h) => h.removeAttribute('aria-sort'));
      th.setAttribute('aria-sort', asc ? 'ascending' : 'descending');
      const numeric = th.classList.contains('num');
      const key = (row) => row.cells[col].dataset.sort ?? row.cells[col].textContent;
      const rows = [...body.rows].sort((a, b) => {
        const [x, y] = [key(a), key(b)];
        const cmp = numeric ? Number(x) - Number(y) : x.localeCompare(y);
        return asc ? cmp : -cmp;
      });
      rows.forEach((r) => body.appendChild(r));
    });
  });
  document.querySelector('.search').addEventListener('input', (e) => {
    const q = e.target.value.toLowerCase();
    [...body.rows].forEach((r) => { r.hidden = q && !r.textContent.toLowerCase().includes(q); });
  });
})();
"""

TEMPLATE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>{title}</title>
<meta name="theme-color" content="#0a0d12" />
<link rel="preconnect" href="https://fonts.googleapis.com" />
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin />
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;500;600&family=Space+Grotesk:wght@400;500;600;700&display=swap" />
<style>{css}</style>
</head>
<body>
<div class="wrap-page">
  <div class="spectrum" aria-hidden="true"><span></span><span></span><span></span><span></span><span></span></div>
  <header>
    {avatar}
    <div>
      <div class="eyebrow">gitpulse</div>
      <h1><a href="{owner_url}" target="_blank" rel="noopener">{display}</a></h1>
      <div class="sub">@{owner} · {repo_count} repositories · traffic {window} · generated {generated}</div>
    </div>
  </header>

  <section class="overview">
    <div class="card">
      <div class="hero-label">Views, last 14 days</div>
      <div class="hero-value" title="{hero_full}">{hero}</div>
      <div class="card-sub">across {traffic_count} of {repo_count} repositories with traffic access</div>
    </div>
    <div class="tiles">{tiles}</div>
  </section>

  <section class="card">
    <h2>Daily traffic</h2>
    <div class="card-sub">Views and clones per day, summed across repositories</div>
    {line}
  </section>

  <div class="grid-2">
    <section class="card">
      <h2>Most viewed</h2>
      <div class="card-sub">Views in the last 14 days</div>
      {top_views}
    </section>
    <section class="card">
      <h2>Most starred</h2>
      <div class="card-sub">All-time stargazers</div>
      {top_stars}
    </section>
  </div>

  <div class="grid-2">
    <section class="card">
      <h2>Languages</h2>
      <div class="card-sub">Repositories by primary language</div>
      {languages}
    </section>
    <section class="card">
      <h2>Top referrers</h2>
      <div class="card-sub">Views from each source, summed across repositories</div>
      {referrers}
    </section>
  </div>

  <section class="card full">
    <h2>Release downloads</h2>
    <div class="card-sub">All-time downloads of uploaded release assets (not Homebrew installs)</div>
    {downloads}
  </section>

  <section class="card full" id="repos">
    <div class="table-head">
      <div><h2>All repositories</h2><div class="card-sub" style="margin:0">Click a column to sort</div></div>
      <input class="search" type="search" placeholder="Filter repositories…" aria-label="Filter repositories" />
    </div>
    <div class="table-scroll">
      <table>
        <thead><tr>
          <th>Repository</th><th>Language</th><th class="num">Stars</th><th class="num">Forks</th>
          <th class="num">Issues</th><th class="num" aria-sort="descending">Views</th>
          <th class="num">Unique</th><th class="num">Clones</th><th class="num">Downloads</th>
          <th>14-day views</th><th>Last push</th>
        </tr></thead>
        <tbody>{rows}</tbody>
      </table>
    </div>
  </section>

  {missing}

  <footer>
    <p>GitHub reports aggregate traffic for roughly the last 14 days and never identifies individual visitors.
    Unique counts are summed per repository and per day, so one person can be counted more than once.</p>
    <div class="foot-row">
      <a class="brand" href="https://fullstackspectrum.com" target="_blank" rel="noopener"><span class="mark"></span><span>Full-Stack-Spectrum</span></a>
      <a href="https://github.com/fullstackspectrum/gitpulse" target="_blank" rel="noopener">generated by gitpulse ↗</a>
    </div>
  </footer>
</div>
<div id="tooltip" role="tooltip" hidden></div>
<script>{js}</script>
</body>
</html>
"""
