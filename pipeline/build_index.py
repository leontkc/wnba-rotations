"""
build_index.py — Generate docs/index.html from the manifest.
"""

import json
import logging
from collections import defaultdict
from pathlib import Path

log = logging.getLogger(__name__)


def generate_index(games: dict, output_path: Path) -> None:
    """
    Build the index page from the manifest's games dict.
    games: {game_id: {date, matchup, home_tricode, away_tricode,
                       score_home, score_away, season, html_path}}
    """
    if not games:
        log.warning("No games in manifest — writing empty index.")

    # Group by season then by date (newest first within each season)
    by_season: dict[str, dict[str, list]] = defaultdict(lambda: defaultdict(list))
    all_tricodes: set = set()

    for gid, g in games.items():
        season = g.get("season", "unknown")
        date   = g.get("date", "")
        by_season[season][date].append(g)
        all_tricodes.add(g.get("home_tricode", ""))
        all_tricodes.add(g.get("away_tricode", ""))

    all_tricodes.discard("")
    sorted_tricodes = sorted(all_tricodes)
    sorted_seasons  = sorted(by_season.keys(), reverse=True)  # newest season first
    most_recent_season = sorted_seasons[0] if sorted_seasons else ""

    # Build season tab HTML
    tabs_html = "\n".join(
        f'    <span class="tab{" active" if s == most_recent_season else ""}" '
        f'data-season="{s}" onclick="switchSeason(\'{s}\')">{s}</span>'
        for s in sorted_seasons
    )

    # Build team filter options
    team_options = '\n'.join(
        f'      <option value="{tc}">{tc}</option>' for tc in sorted_tricodes
    )

    # Build game rows per season
    sections_html_parts = []
    manifest_for_js = []

    for season in sorted_seasons:
        dates = sorted(by_season[season].keys(), reverse=True)  # newest date first
        date_groups = []
        for date in dates:
            day_games = by_season[season][date]
            rows = []
            for g in day_games:
                gid        = g["game_id"]
                home_tc    = g["home_tricode"]
                away_tc    = g["away_tricode"]
                score_home = g["score_home"]
                score_away = g["score_away"]
                html_path  = g["html_path"]

                home_wins = score_home > score_away
                home_score_html = f'<span class="winner">{score_home}</span>' if home_wins else str(score_home)
                away_score_html = f'<span class="winner">{score_away}</span>' if not home_wins else str(score_away)

                rows.append(
                    f'        <div class="game-row" '
                    f'data-teams="{home_tc} {away_tc}" data-date="{date}">\n'
                    f'          <span class="game-matchup">{away_tc} @ {home_tc}</span>\n'
                    f'          <span class="game-score">Final: '
                    f'{home_tc} {home_score_html} – {away_tc} {away_score_html}</span>\n'
                    f'          <a class="game-link" href="{html_path}">View →</a>\n'
                    f'        </div>'
                )

                manifest_for_js.append({
                    "id":   gid,
                    "s":    season,
                    "d":    date,
                    "h":    home_tc,
                    "a":    away_tc,
                    "sh":   score_home,
                    "sa":   score_away,
                })

            formatted_date = _format_date(date)
            date_groups.append(
                f'      <div class="date-group" data-date="{date}">\n'
                f'        <div class="date-header">{formatted_date}</div>\n'
                + "\n".join(rows) + "\n"
                f"      </div>"
            )

        active_class = " active" if season == most_recent_season else ""
        sections_html_parts.append(
            f'    <div class="season-section{active_class}" id="season-{season}" data-season="{season}">\n'
            + "\n".join(date_groups) + "\n"
            f"    </div>"
        )

    sections_html = "\n".join(sections_html_parts)
    manifest_json = json.dumps(manifest_for_js)
    total_games = len(games)

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>wnbarotations — WNBA Game Flows</title>
<link rel="stylesheet" href="assets/site.css">
</head>
<body>
<header>
  <h1>wnbarotations</h1>
  <p class="subtitle">Score flow, player rotations &amp; box scores for every WNBA game</p>
  <div class="season-tabs">
{tabs_html}
  </div>
</header>

<div class="filters">
  <select id="team-filter" onchange="applyFilters()">
    <option value="">All Teams</option>
{team_options}
  </select>
  <input id="search-box" type="text" placeholder="🔍  Search team or date…" oninput="applyFilters()">
  <span id="game-count">{total_games} games</span>
</div>

<main id="game-list">
{sections_html}
  <div class="no-results" id="no-results" style="display:none">No games match your search.</div>
</main>

<script>
const MANIFEST = {manifest_json};

let currentSeason = '{most_recent_season}';

function switchSeason(season) {{
  currentSeason = season;
  document.querySelectorAll('.season-section').forEach(el => {{
    el.classList.toggle('active', el.dataset.season === season);
  }});
  document.querySelectorAll('.tab').forEach(el => {{
    el.classList.toggle('active', el.dataset.season === season);
  }});
  applyFilters();
}}

function applyFilters() {{
  const team   = document.getElementById('team-filter').value.trim().toUpperCase();
  const search = document.getElementById('search-box').value.trim().toUpperCase();

  const section = document.querySelector(`.season-section[data-season="${{currentSeason}}"]`);
  if (!section) return;

  let visible = 0;
  section.querySelectorAll('.game-row').forEach(row => {{
    const teams = (row.dataset.teams || '').toUpperCase();
    const date  = (row.dataset.date  || '').toUpperCase();
    const teamOk   = !team   || teams.includes(team);
    const searchOk = !search || teams.includes(search) || date.includes(search);
    const show = teamOk && searchOk;
    row.style.display = show ? '' : 'none';
    if (show) visible++;
  }});

  // Hide empty date groups
  section.querySelectorAll('.date-group').forEach(dg => {{
    const hasVisible = [...dg.querySelectorAll('.game-row')].some(r => r.style.display !== 'none');
    dg.style.display = hasVisible ? '' : 'none';
  }});

  document.getElementById('game-count').textContent = visible + ' game' + (visible !== 1 ? 's' : '');
  document.getElementById('no-results').style.display = visible === 0 ? '' : 'none';
}}
</script>
</body>
</html>
"""

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(html, encoding="utf-8")
    log.info(f"Index written → {output_path}  ({total_games} games)")


def _format_date(date_str: str) -> str:
    """'2024-09-19' → 'September 19, 2024'"""
    try:
        from datetime import date
        d = date.fromisoformat(date_str)
        return f"{d.strftime('%B')} {d.day}, {d.year}"
    except Exception:
        return date_str
