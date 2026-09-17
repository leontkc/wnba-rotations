"""
build_index.py — Generate docs/index.html from the manifest.
"""

import json
import logging
from collections import defaultdict
from html import escape
from pathlib import Path

log = logging.getLogger(__name__)

TEAM_NAMES = {
    "ATL": "Atlanta Dream",
    "CHI": "Chicago Sky",
    "CON": "Connecticut Sun",
    "DAL": "Dallas Wings",
    "GSV": "Golden State Valkyries",
    "IND": "Indiana Fever",
    "LAS": "Los Angeles Sparks",
    "LVA": "Las Vegas Aces",
    "MIN": "Minnesota Lynx",
    "NYL": "New York Liberty",
    "PDX": "Portland Fire",
    "PHO": "Phoenix Mercury",
    "PHX": "Phoenix Mercury",
    "SEA": "Seattle Storm",
    "TOR": "Toronto Tempo",
    "WAS": "Washington Mystics",
}

# Older seasons use a different code for the same franchise; the team filter
# treats them as one team.
TRICODE_ALIASES = {"PHO": "PHX"}


def team_name(tc: str) -> str:
    return TEAM_NAMES.get(tc, tc)


def generate_index(games: dict, output_path: Path) -> None:
    """
    Build the index page from the manifest's games dict.
    games: {game_id: {date, matchup, home_tricode, away_tricode,
                       score_home, score_away, season, html_path}}
    Games without a season (e.g. one-off test games) are left off the index.
    """
    if not games:
        log.warning("No games in manifest — writing empty index.")

    # Group by season then by date (newest first within each season)
    by_season: dict[str, dict[str, list]] = defaultdict(lambda: defaultdict(list))
    all_tricodes: set = set()

    for g in games.values():
        season = g.get("season", "")
        if not season:
            continue
        by_season[season][g.get("date", "")].append(g)
        for tc in (g.get("home_tricode", ""), g.get("away_tricode", "")):
            all_tricodes.add(TRICODE_ALIASES.get(tc, tc))

    all_tricodes.discard("")
    sorted_seasons = sorted(by_season.keys(), reverse=True)  # newest season first
    most_recent_season = sorted_seasons[0] if sorted_seasons else ""
    season_counts = {s: sum(len(v) for v in by_season[s].values()) for s in sorted_seasons}

    tabs_html = "\n".join(
        f'      <button type="button" class="tab{" active" if s == most_recent_season else ""}" '
        f'data-season="{s}" role="tab" aria-selected="{"true" if s == most_recent_season else "false"}">'
        f'{s}</button>'
        for s in sorted_seasons
    )

    team_options = "\n".join(
        f'        <option value="{tc}">{escape(team_name(tc))}</option>'
        for tc in sorted(all_tricodes, key=team_name)
    )

    sections_html_parts = []
    for season in sorted_seasons:
        date_groups = []
        for date in sorted(by_season[season].keys(), reverse=True):  # newest date first
            day_games = sorted(by_season[season][date], key=lambda g: g["game_id"])
            cards = "\n".join(_game_card(g, date) for g in day_games)
            n = len(day_games)
            date_groups.append(
                f'      <section class="date-group" data-date="{date}">\n'
                f'        <h2 class="date-header"><span>{_format_date(date)}</span>'
                f'<span class="date-count">{n} game{"s" if n != 1 else ""}</span></h2>\n'
                f'        <div class="game-grid">\n{cards}\n        </div>\n'
                f"      </section>"
            )

        active_class = " active" if season == most_recent_season else ""
        sections_html_parts.append(
            f'    <div class="season-section{active_class}" id="season-{season}" data-season="{season}">\n'
            + "\n".join(date_groups) + "\n"
            f"    </div>"
        )

    sections_html = "\n".join(sections_html_parts)
    total_games = sum(season_counts.values())
    initial_count = season_counts.get(most_recent_season, 0)

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>wnbarotations — WNBA rotations, game flow &amp; box scores</title>
<meta name="description" content="Score flow, player rotations and box scores for every WNBA game.">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap">
<link rel="stylesheet" href="assets/base.css">
<link rel="stylesheet" href="assets/site.css">
</head>
<body>
<header class="topbar">
  <div class="topbar-inner">
    <a class="brand" href="index.html"><span class="brand-mark" aria-hidden="true"></span>wnba<span class="dim">rotations</span></a>
    <div class="player-search" data-root="">
      <input type="search" placeholder="Find a player" aria-label="Find a player" autocomplete="off">
      <div class="player-dropdown"></div>
    </div>
  </div>
</header>

<main class="page">
  <div class="hero">
    <h1>Every WNBA game, minute by minute</h1>
    <p class="subtitle">Who was on the floor, how the lead swung, and what each stint produced.</p>
  </div>

  <div class="toolbar">
    <div class="season-tabs" role="tablist" aria-label="Season">
{tabs_html}
    </div>
    <div class="filters">
      <select id="team-filter" aria-label="Filter by team">
        <option value="">All teams</option>
{team_options}
      </select>
      <input id="search-box" type="search" placeholder="Team or date" aria-label="Search by team or date">
      <span id="game-count">{initial_count} games</span>
    </div>
  </div>

  <div id="game-list">
{sections_html}
    <div class="no-results" id="no-results" hidden>No games match your filters.</div>
  </div>
</main>

<footer class="site-footer">
  {total_games} games · Play-by-play and box scores from NBA Stats, updated daily.
</footer>

<script>
let currentSeason = '{most_recent_season}';

document.querySelectorAll('.tab').forEach(tab => {{
  tab.addEventListener('click', () => switchSeason(tab.dataset.season));
}});
document.getElementById('team-filter').addEventListener('change', applyFilters);
document.getElementById('search-box').addEventListener('input', applyFilters);

function switchSeason(season) {{
  currentSeason = season;
  document.querySelectorAll('.season-section').forEach(el => {{
    el.classList.toggle('active', el.dataset.season === season);
  }});
  document.querySelectorAll('.tab').forEach(el => {{
    const on = el.dataset.season === season;
    el.classList.toggle('active', on);
    el.setAttribute('aria-selected', on);
  }});
  applyFilters();
}}

function applyFilters() {{
  const team   = document.getElementById('team-filter').value.trim().toUpperCase();
  const search = document.getElementById('search-box').value.trim().toUpperCase();

  const section = document.querySelector(`.season-section[data-season="${{currentSeason}}"]`);
  if (!section) return;

  let visible = 0;
  section.querySelectorAll('.game-card').forEach(card => {{
    const teams = card.dataset.teams.toUpperCase();
    const date  = card.dataset.date;
    const teamOk   = !team   || teams.split(' ').includes(team);
    const searchOk = !search || teams.includes(search) || date.includes(search);
    const show = teamOk && searchOk;
    card.hidden = !show;
    if (show) visible++;
  }});

  section.querySelectorAll('.date-group').forEach(dg => {{
    dg.hidden = !dg.querySelector('.game-card:not([hidden])');
  }});

  document.getElementById('game-count').textContent = visible + ' game' + (visible !== 1 ? 's' : '');
  document.getElementById('no-results').hidden = visible !== 0;
}}
</script>
<script src="assets/search.js"></script>
</body>
</html>
"""

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(html, encoding="utf-8")
    log.info(f"Index written → {output_path}  ({total_games} games)")


def _game_card(g: dict, date: str) -> str:
    home_tc, away_tc = g["home_tricode"], g["away_tricode"]
    score_home, score_away = g["score_home"], g["score_away"]
    home_wins = score_home > score_away
    search_codes = {home_tc, away_tc} | {TRICODE_ALIASES.get(t, t) for t in (home_tc, away_tc)}

    def row(tc, score, won, side):
        return (
            f'            <div class="gc-team {side}{" won" if won else ""}">'
            f'<span class="gc-tc">{tc}</span>'
            f'<span class="gc-name">{escape(team_name(tc))}</span>'
            f'<span class="gc-score">{score}</span></div>'
        )

    return (
        f'          <a class="game-card" href="{g["html_path"]}" '
        f'data-teams="{" ".join(sorted(search_codes))}" data-date="{date}" '
        f'aria-label="{escape(team_name(away_tc))} {score_away} at {escape(team_name(home_tc))} {score_home}">\n'
        f'{row(away_tc, score_away, not home_wins, "away")}\n'
        f'{row(home_tc, score_home, home_wins, "home")}\n'
        f'            <div class="gc-foot"><span>Final</span><span class="gc-go">Rotations →</span></div>\n'
        f'          </a>'
    )


def _format_date(date_str: str) -> str:
    """'2024-09-19' → 'Thursday, September 19'"""
    try:
        from datetime import date
        d = date.fromisoformat(date_str)
        return f"{d.strftime('%A')}, {d.strftime('%B')} {d.day}"
    except Exception:
        return date_str
