"""Render an OrgReport as a self-contained HTML dashboard (no external scripts or styles)."""

from __future__ import annotations

import json
import math
from html import escape
from typing import Any

from gitpulse.org import OrgReport, RepoStats

# Categorical slots in fixed order; slot 4 (yellow) takes dark ink for labels inside it.
SERIES = 8
DARK_INK_SLOTS = {4}


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
        ink = " dark-ink" if slot in DARK_INK_SLOTS and name != "Other" else ""
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
        [("Views", "--series-1", views_daily), ("Clones", "--series-2", clones_daily)]
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
  color-scheme: light;
  --page: #f9f9f7; --surface: #fcfcfb; --text: #0b0b0b; --text-2: #52514e; --muted: #898781;
  --grid: #e1e0d9; --axis: #c3c2b7; --border: rgba(11,11,11,0.10); --wash: rgba(11,11,11,0.04);
  --accent: #2a78d6; --muted-fill: #b4b2a9;
  --series-1: #2a78d6; --series-2: #eb6834; --series-3: #1baf7a; --series-4: #eda100;
  --series-5: #e87ba4; --series-6: #008300; --series-7: #6250d6; --series-8: #e34948;
}
@media (prefers-color-scheme: dark) {
  :root:not([data-theme="light"]) {
    color-scheme: dark;
    --page: #0d0d0d; --surface: #1a1a19; --text: #f0efec; --text-2: #c3c2b7; --muted: #898781;
    --grid: #2c2c2a; --axis: #383835; --border: rgba(255,255,255,0.10); --wash: rgba(255,255,255,0.05);
    --accent: #3987e5; --muted-fill: #5f5e5a;
    --series-1: #3987e5; --series-2: #d95926; --series-3: #199e70; --series-4: #c98500;
    --series-5: #d55181; --series-6: #008300; --series-7: #9085e9; --series-8: #e66767;
  }
}
:root[data-theme="dark"] {
  color-scheme: dark;
  --page: #0d0d0d; --surface: #1a1a19; --text: #f0efec; --text-2: #c3c2b7; --muted: #898781;
  --grid: #2c2c2a; --axis: #383835; --border: rgba(255,255,255,0.10); --wash: rgba(255,255,255,0.05);
  --accent: #3987e5; --muted-fill: #5f5e5a;
  --series-1: #3987e5; --series-2: #d95926; --series-3: #199e70; --series-4: #c98500;
  --series-5: #d55181; --series-6: #008300; --series-7: #9085e9; --series-8: #e66767;
}
* { box-sizing: border-box; }
body { margin: 0; background: var(--page); color: var(--text);
  font: 14px/1.5 system-ui, -apple-system, "Segoe UI", sans-serif; }
a { color: inherit; text-decoration: none; }
a:hover { text-decoration: underline; }
.wrap-page { max-width: 1200px; margin: 0 auto; padding: 32px 24px 64px; }
header { display: flex; align-items: center; gap: 16px; margin-bottom: 28px; }
.avatar { width: 56px; height: 56px; border-radius: 12px; border: 1px solid var(--border); }
h1 { font-size: 24px; margin: 0; font-weight: 650; letter-spacing: -0.01em; }
h2 { font-size: 15px; margin: 0 0 4px; font-weight: 600; }
.sub { color: var(--text-2); font-size: 13px; }
.theme-toggle { margin-left: auto; flex-shrink: 0; white-space: nowrap; background: var(--surface); color: var(--text-2);
  border: 1px solid var(--border); border-radius: 8px; padding: 6px 12px; font: inherit; cursor: pointer; }
.theme-toggle:hover { background: var(--wash); }
.card { background: var(--surface); border: 1px solid var(--border); border-radius: 14px; padding: 20px; }
.card-sub { color: var(--muted); font-size: 12px; margin-bottom: 16px; }
.overview { display: grid; grid-template-columns: minmax(220px, 1fr) 3fr; gap: 16px; margin-bottom: 16px; }
.hero-label { color: var(--text-2); font-size: 13px; }
.hero-value { font-size: 56px; font-weight: 650; line-height: 1.1; letter-spacing: -0.02em; margin: 6px 0; }
.tiles { display: grid; grid-template-columns: repeat(3, 1fr); gap: 1px; background: var(--border);
  border-radius: 14px; overflow: hidden; border: 1px solid var(--border); }
.tile { background: var(--surface); padding: 16px 20px; }
.tile-label { color: var(--text-2); font-size: 13px; }
.tile-value { font-size: 26px; font-weight: 600; margin-top: 2px; }
.tile-note { color: var(--muted); font-size: 12px; }
.grid-2 { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; margin-top: 16px; }
.full { margin-top: 16px; }
.legend { display: flex; gap: 16px; font-size: 12px; color: var(--text-2); margin-bottom: 10px; }
.legend.wrap { flex-wrap: wrap; gap: 6px 16px; margin: 12px 0 0; }
.legend-item { display: inline-flex; align-items: center; gap: 6px; }
.key-line { width: 14px; height: 2px; border-radius: 1px; }
.swatch { width: 10px; height: 10px; border-radius: 3px; }
.muted { color: var(--muted); }
.empty { color: var(--muted); margin: 24px 0; text-align: center; }
.linechart { display: grid; grid-template-columns: 44px 1fr; grid-template-rows: 240px auto; }
.y-axis { position: relative; }
.y-tick { position: absolute; right: 8px; transform: translateY(-50%); font-size: 11px;
  color: var(--muted); font-variant-numeric: tabular-nums; }
.plot { position: relative; outline: none; margin-right: 40px; }
.plot svg { width: 100%; height: 100%; display: block; overflow: visible; }
.plot .grid { stroke: var(--grid); stroke-width: 1; vector-effect: non-scaling-stroke; }
.plot .line { fill: none; stroke-width: 2; stroke-linejoin: round; stroke-linecap: round;
  vector-effect: non-scaling-stroke; }
.plot .area { opacity: 0.10; }
.end-labels { position: absolute; top: 0; bottom: 0; left: 100%; }
.end-label { position: absolute; left: 8px; transform: translateY(-50%); font-size: 11px;
  color: var(--text-2); font-variant-numeric: tabular-nums; }
.x-axis { grid-column: 2; position: relative; height: 22px; margin-right: 40px; }
.x-tick { position: absolute; top: 6px; transform: translateX(-50%); font-size: 11px; color: var(--muted);
  white-space: nowrap; }
.crosshair { position: absolute; top: 0; bottom: 0; width: 1px; background: var(--axis); pointer-events: none; }
.dot { position: absolute; width: 10px; height: 10px; border-radius: 50%; transform: translate(-50%, -50%);
  box-shadow: 0 0 0 2px var(--surface); pointer-events: none; }
.bars { list-style: none; margin: 0; padding: 0; display: grid; gap: 2px; }
.bar-row { display: grid; grid-template-columns: minmax(90px, min(34%, 220px)) 1fr 52px; align-items: center; gap: 10px;
  padding: 5px 6px; border-radius: 6px; outline: none; }
.bar-row:hover, .bar-row:focus-visible { background: var(--wash); }
.bar-label { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; color: var(--text-2); }
.bar-track { height: 12px; }
.bar { display: block; height: 100%; background: var(--series-1); border-radius: 0 4px 4px 0; }
.bar-value { text-align: right; font-variant-numeric: tabular-nums; }
.segmented { display: flex; gap: 2px; height: 28px; }
.segment { min-width: 3px; border-radius: 4px; color: #fff; font-size: 12px; font-weight: 600;
  padding-left: 8px; display: flex; align-items: center; overflow: hidden; outline: none; }
.segment.dark-ink { color: #0b0b0b; }
.segment:hover, .segment:focus-visible { filter: brightness(1.08); }
.table-head { display: flex; align-items: end; justify-content: space-between; gap: 12px; flex-wrap: wrap; }
.search { background: var(--page); color: var(--text); border: 1px solid var(--border); border-radius: 8px;
  padding: 7px 10px; font: inherit; min-width: 220px; }
.table-scroll { overflow-x: auto; margin-top: 12px; }
table { width: 100%; border-collapse: collapse; font-size: 13px; }
th { text-align: left; font-weight: 600; color: var(--text-2); font-size: 12px; padding: 8px 10px;
  border-bottom: 1px solid var(--axis); cursor: pointer; user-select: none; white-space: nowrap; }
th.num { text-align: right; }
th[aria-sort]::after { content: " ↓"; color: var(--muted); }
th[aria-sort="ascending"]::after { content: " ↑"; }
td { padding: 9px 10px; border-bottom: 1px solid var(--grid); vertical-align: top; }
td.num { text-align: right; font-variant-numeric: tabular-nums; }
tr:hover td { background: var(--wash); }
.desc { color: var(--muted); font-size: 12px; max-width: 360px; overflow: hidden; text-overflow: ellipsis;
  white-space: nowrap; }
.badge { font-size: 10px; color: var(--text-2); border: 1px solid var(--border); border-radius: 999px;
  padding: 0 6px; margin-left: 6px; vertical-align: 1px; }
.nowrap { white-space: nowrap; }
.spark-cell { width: 110px; }
.spark { width: 100px; height: 24px; display: block; }
.spark polyline { fill: none; stroke: var(--series-1); stroke-width: 1.5; vector-effect: non-scaling-stroke; }
.notice { margin-top: 16px; color: var(--text-2); font-size: 13px; }
.notice summary { cursor: pointer; }
.notice li { margin: 4px 0; }
footer { color: var(--muted); font-size: 12px; margin-top: 24px; }
#tooltip { position: fixed; z-index: 10; pointer-events: none; background: var(--surface); color: var(--text);
  border: 1px solid var(--border); border-radius: 8px; padding: 8px 10px; font-size: 12px;
  box-shadow: 0 4px 16px rgba(0,0,0,0.12); max-width: 280px; }
#tooltip .tt-row { display: flex; align-items: center; gap: 6px; }
#tooltip .tt-val { margin-left: auto; padding-left: 12px; font-variant-numeric: tabular-nums; font-weight: 600; }
@media (max-width: 860px) {
  .overview, .grid-2 { grid-template-columns: 1fr; }
  .tiles { grid-template-columns: repeat(2, 1fr); }
}
@media (max-width: 520px) {
  .wrap-page { padding: 20px 16px 48px; }
  .hero-value { font-size: 48px; }
  .search { min-width: 0; width: 100%; }
  h1 { font-size: 20px; }
  .avatar { width: 40px; height: 40px; }
  .theme-toggle { padding: 5px 9px; font-size: 12px; }
  .x-tick.alt { display: none; }
}
"""

JS = r"""
(() => {
  const root = document.documentElement;
  const toggle = document.querySelector('.theme-toggle');
  const prefersDark = () => matchMedia('(prefers-color-scheme: dark)').matches;
  const current = () => root.dataset.theme || (prefersDark() ? 'dark' : 'light');
  try { const saved = localStorage.getItem('gitpulse-theme'); if (saved) root.dataset.theme = saved; } catch (e) {}
  const label = () => { toggle.textContent = current() === 'dark' ? 'Light mode' : 'Dark mode'; };
  toggle.addEventListener('click', () => {
    root.dataset.theme = current() === 'dark' ? 'light' : 'dark';
    try { localStorage.setItem('gitpulse-theme', root.dataset.theme); } catch (e) {}
    label();
  });
  label();

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
<style>{css}</style>
</head>
<body>
<div class="wrap-page">
  <header>
    {avatar}
    <div>
      <h1><a href="{owner_url}" target="_blank" rel="noopener">{display}</a></h1>
      <div class="sub">@{owner} · {repo_count} repositories · traffic {window} · generated {generated}</div>
    </div>
    <button class="theme-toggle" type="button">Dark mode</button>
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
    Generated by GitPulse. GitHub reports aggregate traffic for roughly the last 14 days and never identifies
    individual visitors. Unique counts are summed per repository and per day, so one person can be counted
    more than once.
  </footer>
</div>
<div id="tooltip" role="tooltip" hidden></div>
<script>{js}</script>
</body>
</html>
"""
