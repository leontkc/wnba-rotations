"""
WNBA Visualizer — Data Generator
Fetches game data from nba_api, assembles payload, writes wnba_viz.html.
Open wnba_viz.html in any browser — no server needed.
"""

import json
import re
import sys
import time
from pathlib import Path

try:
    import pandas as pd
    from nba_api.stats.endpoints import LeagueGameFinder, PlayByPlayV3
    from nba_api.stats.endpoints import BoxScoreTraditionalV3
except ImportError as e:
    print(f"[ERROR] Missing dependency: {e}")
    print("Install with:  pip install nba_api pandas")
    sys.exit(1)

DELAY = 1  # seconds between API calls

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def clock_to_seconds(clock_str):
    """Convert 'PT06M13.00S' → total seconds remaining (float)."""
    if not isinstance(clock_str, str):
        return None
    m = re.match(r"PT(\d+)M([\d.]+)S", clock_str)
    if not m:
        return None
    return int(m.group(1)) * 60 + float(m.group(2))


def clock_display(clock_str):
    """Convert 'PT06M13.00S' → '6:13'."""
    if not isinstance(clock_str, str):
        return str(clock_str)
    m = re.match(r"PT(\d+)M([\d.]+)S", clock_str)
    if not m:
        return clock_str
    mins = int(m.group(1))
    secs = int(float(m.group(2)))
    return f"{mins}:{secs:02d}"


def elapsed_seconds(period, clock_secs):
    """Map period + clock-remaining to 0–2400 s elapsed."""
    return (period - 1) * 600 + (600 - clock_secs)


# ---------------------------------------------------------------------------
# Step 1 — Pick a game
# ---------------------------------------------------------------------------
print("Fetching 2024 WNBA Regular Season game list …")
try:
    finder = LeagueGameFinder(
        season_nullable="2024",
        league_id_nullable="10",
        season_type_nullable="Regular Season",
        timeout=60,
    )
    games_df = finder.get_data_frames()[0]
except Exception as e:
    print(f"[ERROR] LeagueGameFinder failed: {e}")
    sys.exit(1)

if games_df.empty:
    print("[ERROR] No games found.")
    sys.exit(1)

game_id   = games_df["GAME_ID"].iloc[0]
game_date = games_df["GAME_DATE"].iloc[0]
matchup   = games_df["MATCHUP"].iloc[0]
print(f"  Game: {game_id}  |  {game_date}  |  {matchup}")
time.sleep(DELAY)

# ---------------------------------------------------------------------------
# Step 2 — PlayByPlayV3
# ---------------------------------------------------------------------------
print("Fetching PlayByPlayV3 …")
try:
    pbp = PlayByPlayV3(game_id=game_id, timeout=60)
    pbp_df = pbp.get_data_frames()[0]
except Exception as e:
    print(f"[ERROR] PlayByPlayV3 failed: {e}")
    sys.exit(1)
print(f"  PBP rows: {len(pbp_df)}")
time.sleep(DELAY)

# ---------------------------------------------------------------------------
# Step 3 — Score flow
# ---------------------------------------------------------------------------
print("Computing score flow …")
score_df = pbp_df[["actionNumber", "period", "clock", "scoreHome", "scoreAway"]].dropna(
    subset=["scoreHome"]
).copy()
score_df = score_df[score_df["scoreHome"].astype(str).str.strip() != ""]

score_flow = []
for _, row in score_df.iterrows():
    clk_secs = clock_to_seconds(row["clock"])
    if clk_secs is None:
        continue
    period = int(row["period"])
    score_flow.append({
        "elapsed_sec": int(elapsed_seconds(period, clk_secs)),
        "period": period,
        "clock_display": clock_display(row["clock"]),
        "score_home": int(row["scoreHome"]),
        "score_away": int(row["scoreAway"]),
    })

print(f"  Scoring events: {len(score_flow)}")

# Derive final score and tricodes
final_home = score_flow[-1]["score_home"] if score_flow else 0
final_away = score_flow[-1]["score_away"] if score_flow else 0

# Derive home/away tricodes from matchup string ("WAS vs. IND" or "WAS @ IND")
matchup_str = str(matchup)
if " vs. " in matchup_str:
    home_tc = matchup_str.split(" vs. ")[0].strip()
    away_tc = matchup_str.split(" vs. ")[1].strip()
elif " @ " in matchup_str:
    away_tc = matchup_str.split(" @ ")[0].strip()
    home_tc = matchup_str.split(" @ ")[1].strip()
else:
    tricodes = [t for t in pbp_df["teamTricode"].dropna().unique() if t]
    home_tc = tricodes[0] if len(tricodes) > 0 else "HOME"
    away_tc = tricodes[1] if len(tricodes) > 1 else "AWAY"

# ---------------------------------------------------------------------------
# Step 4 — Player stints  (same algorithm as wnba_data_validator.py)
# ---------------------------------------------------------------------------
print("Computing player stints …")
stints = []

for team in pbp_df["teamTricode"].dropna().unique():
    team_events = pbp_df[pbp_df["teamTricode"] == team].copy()
    team_events = team_events.sort_values("actionNumber")

    for period in sorted(pbp_df["period"].unique()):
        period_events = team_events[team_events["period"] == period]
        if period_events.empty:
            continue

        # Infer starters: players in non-sub events before first substitution
        first_sub_idx = period_events[
            period_events["actionType"].str.lower() == "substitution"
        ].index.min()

        if pd.isna(first_sub_idx):
            pre_sub = period_events[
                ~period_events["actionType"].str.lower().isin({"period", "substitution"})
            ]
        else:
            pre_sub = period_events[period_events.index < first_sub_idx]
            pre_sub = pre_sub[
                ~pre_sub["actionType"].str.lower().isin({"period", "substitution"})
            ]

        starters = pre_sub["playerName"].dropna().unique().tolist()

        p_start = 600  # 10-min WNBA quarters
        on_court = {p: p_start for p in starters}

        for _, row in period_events.iterrows():
            action = str(row.get("actionType", "")).lower()
            if action != "substitution":
                continue

            clock_str = row.get("clock", "")
            clock_secs = clock_to_seconds(clock_str)
            desc = str(row.get("description", ""))

            player_out = row.get("playerName")
            m = re.match(r"SUB:\s+(.+?)\s+FOR\s+", desc)
            player_in = m.group(1).strip() if m else None

            if player_out and player_out in on_court:
                clock_in = on_court.pop(player_out)
                if clock_secs is not None:
                    duration = clock_in - clock_secs
                    stints.append({
                        "player": player_out,
                        "team": str(team),
                        "period": int(period),
                        "clock_in": float(clock_in),
                        "clock_out": float(clock_secs),
                        "duration_sec": round(float(duration), 1),
                        "start_elapsed": elapsed_seconds(int(period), float(clock_in)),
                        "end_elapsed": elapsed_seconds(int(period), float(clock_secs)),
                    })

            if player_in and clock_secs is not None:
                on_court[player_in] = clock_secs

        # Close open stints at period end
        for player, clock_in in on_court.items():
            stints.append({
                "player": player,
                "team": str(team),
                "period": int(period),
                "clock_in": float(clock_in),
                "clock_out": 0.0,
                "duration_sec": round(float(clock_in), 1),
                "start_elapsed": elapsed_seconds(int(period), float(clock_in)),
                "end_elapsed": elapsed_seconds(int(period), 0.0),
            })

print(f"  Stint records: {len(stints)}")

# ---------------------------------------------------------------------------
# Per-stint stats from PBP
# ---------------------------------------------------------------------------
print("Computing per-stint stats …")
pbp_df['_clock_secs'] = pbp_df['clock'].apply(clock_to_seconds)

for stint in stints:
    player    = stint['player']
    period    = stint['period']
    clock_in  = stint['clock_in']
    clock_out = stint['clock_out']

    if not player:
        stint.update({'stint_pts': 0, 'stint_reb': 0, 'stint_ast': 0})
        continue

    # All events in this stint's time window
    window_mask = (
        (pbp_df['period'] == period) &
        (pbp_df['_clock_secs'] >= clock_out) &
        (pbp_df['_clock_secs'] <= clock_in)
    )
    window = pbp_df[window_mask]
    player_ev = window[window['playerName'] == player]

    # Points: Made Shot uses shotValue (2 or 3); Free Throw = 1 if not "MISS"
    made_shots = player_ev[player_ev['actionType'] == 'Made Shot']
    pts = int(made_shots['shotValue'].fillna(0).sum())

    free_throws = player_ev[player_ev['actionType'] == 'Free Throw']
    pts += int((~free_throws['description'].str.upper().str.startswith('MISS')).sum())

    # Rebounds: personal only (team rebounds have empty playerName)
    reb = int((player_ev['actionType'] == 'Rebound').sum())

    # Assists: parse "(Player N AST)" from Made Shot descriptions in window
    ast_pat = re.compile(rf'\({re.escape(player)}\s+\d+\s+AST\)', re.IGNORECASE)
    made_in_window = window[window['actionType'] == 'Made Shot']
    ast = int(made_in_window['description'].apply(
        lambda d: bool(ast_pat.search(str(d)))).sum())

    stint['stint_pts'] = pts
    stint['stint_reb'] = reb
    stint['stint_ast'] = ast

print("  Done")
time.sleep(DELAY)

# ---------------------------------------------------------------------------
# Step 5 — BoxScoreTraditionalV3
# ---------------------------------------------------------------------------
print("Fetching BoxScoreTraditionalV3 …")
box_score = []
try:
    box = BoxScoreTraditionalV3(game_id=game_id, timeout=60)
    player_stats = box.get_data_frames()[0]
    col_map = {
        "firstName":          "first",
        "familyName":         "last",
        "teamTricode":        "team",
        "minutes":            "minutes",
        "points":             "pts",
        "fieldGoalsMade":     "fgm",
        "fieldGoalsAttempted":"fga",
        "reboundsTotal":      "reb",
        "assists":            "ast",
        "steals":             "stl",
        "blocks":             "blk",
        "turnovers":          "to",
        "foulsPersonal":      "pf",
        "plusMinusPoints":    "plus_minus",
    }
    for _, row in player_stats.iterrows():
        entry = {}
        for src, dst in col_map.items():
            val = row.get(src, None)
            if val is None or (isinstance(val, float) and pd.isna(val)):
                entry[dst] = None
            elif dst in ("pts", "fgm", "fga", "reb", "ast", "stl", "blk", "to", "pf"):
                entry[dst] = int(val) if val is not None else 0
            elif dst == "plus_minus":
                entry[dst] = float(val) if val is not None else 0.0
            else:
                entry[dst] = str(val) if val is not None else ""
        box_score.append(entry)
    print(f"  Player rows: {len(box_score)}")
except Exception as e:
    print(f"  [WARN] BoxScoreTraditionalV3 failed: {e}  (box score will be empty)")

# Build player_game_stats lookup keyed by PBP playerName
# Box score uses firstName + familyName; PBP uses playerName (usually "First Last")
player_game_stats = {}
stint_players = set(s["player"] for s in stints)
for entry in box_score:
    full_name = f"{entry['first']} {entry['last']}".strip()
    stat = {
        "pts": entry.get("pts") or 0,
        "reb": entry.get("reb") or 0,
        "ast": entry.get("ast") or 0,
        "stl": entry.get("stl") or 0,
    }
    player_game_stats[full_name] = stat

# Fallback: match by last name for any stint player not yet matched
last_name_map = {}
for full_name, stat in player_game_stats.items():
    last = full_name.split()[-1]
    last_name_map.setdefault(last, stat)

for sp in stint_players:
    if not sp or sp in player_game_stats:
        continue
    parts = sp.split()
    if parts:
        last = parts[-1]
        if last in last_name_map:
            player_game_stats[sp] = last_name_map[last]

# ---------------------------------------------------------------------------
# Assemble payload
# ---------------------------------------------------------------------------
payload = {
    "game": {
        "id": game_id,
        "date": str(game_date),
        "matchup": str(matchup),
        "home_tricode": home_tc,
        "away_tricode": away_tc,
        "score_home": final_home,
        "score_away": final_away,
    },
    "score_flow": score_flow,
    "stints": stints,
    "box_score": box_score,
    "player_game_stats": player_game_stats,
}

# ---------------------------------------------------------------------------
# HTML template
# ---------------------------------------------------------------------------
HTML_TEMPLATE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>WNBA Game Visualizer</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.3/dist/chart.umd.min.js"></script>
<style>
  *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
  body { background: #0f1117; color: #e0e0e0; font-family: 'Segoe UI', Arial, sans-serif; padding: 16px; }
  h1 { font-size: 1.3rem; font-weight: 600; color: #fff; margin-bottom: 20px; text-align: center; letter-spacing: 0.03em; }
  h2 { font-size: 1rem; font-weight: 600; color: #aaa; margin-bottom: 10px; text-transform: uppercase; letter-spacing: 0.08em; }
  section { background: #1a1d27; border-radius: 10px; padding: 20px; margin-bottom: 24px; }
  canvas { display: block; width: 100% !important; }
  svg text { font-family: 'Segoe UI', Arial, sans-serif; }

  /* Box score table */
  #box-score-container { overflow-x: auto; }
  table { border-collapse: collapse; width: 100%; font-size: 0.82rem; }
  th, td { padding: 6px 10px; text-align: right; white-space: nowrap; }
  th:first-child, td:first-child { text-align: left; }
  th:nth-child(2), td:nth-child(2) { text-align: left; }
  th { color: #bbb; font-weight: 600; cursor: pointer; user-select: none; background: #22263a; position: sticky; top: 0; }
  th:hover { color: #fff; }
  tr:hover td { background: rgba(255,255,255,0.04); }
  .sort-asc::after { content: " ▲"; font-size: 0.7em; }
  .sort-desc::after { content: " ▼"; font-size: 0.7em; }

  /* Gantt tooltip */
  #gantt-tooltip {
    position: fixed; background: rgba(20,22,35,0.95); border: 1px solid #444;
    border-radius: 6px; padding: 6px 10px; font-size: 0.78rem; color: #e0e0e0;
    pointer-events: none; display: none; z-index: 999;
  }
</style>
</head>
<body>
<div id="gantt-tooltip"></div>

<h1 id="game-title">Loading …</h1>

<section>
  <h2>Score Flow</h2>
  <div style="position:relative;height:300px;">
    <canvas id="scoreChart"></canvas>
  </div>
</section>

<section>
  <h2>Player Stints</h2>
  <div id="gantt-container"></div>
</section>

<section>
  <h2>Box Score</h2>
  <div id="box-score-container"></div>
</section>

<script>
const DATA = __GAME_DATA__;

// ─── helpers ────────────────────────────────────────────────────────────────
function minLabel(sec) {
  return (sec / 60).toFixed(1);
}

const HOME_COLOR  = '#c8102e';  // crimson
const AWAY_COLOR  = '#4a90d9';  // steel blue
const HOME_LIGHT  = 'rgba(200,16,46,0.12)';
const AWAY_LIGHT  = 'rgba(74,144,217,0.12)';

function teamColor(tc) {
  return tc === DATA.game.home_tricode ? HOME_COLOR : AWAY_COLOR;
}

// ─── title ──────────────────────────────────────────────────────────────────
const g = DATA.game;
document.getElementById('game-title').textContent =
  `${g.home_tricode} vs. ${g.away_tricode}  ·  ${g.date}  ·  ` +
  `Final: ${g.home_tricode} ${g.score_home} – ${g.away_tricode} ${g.score_away}`;

// ─── 1. Score Flow ──────────────────────────────────────────────────────────
(function renderScoreFlow() {
  const flow = DATA.score_flow;
  if (!flow.length) return;

  const homeData = flow.map(d => ({ x: d.elapsed_sec / 60, y: d.score_home }));
  const awayData = flow.map(d => ({ x: d.elapsed_sec / 60, y: d.score_away }));

  // Quarter divider plugin
  const quarterLines = {
    id: 'quarterLines',
    afterDraw(chart) {
      const { ctx, chartArea: { top, bottom }, scales: { x } } = chart;
      [10, 20, 30].forEach((min, i) => {
        const xPx = x.getPixelForValue(min);
        ctx.save();
        ctx.strokeStyle = 'rgba(255,255,255,0.18)';
        ctx.lineWidth = 1;
        ctx.setLineDash([4, 4]);
        ctx.beginPath();
        ctx.moveTo(xPx, top);
        ctx.lineTo(xPx, bottom);
        ctx.stroke();
        ctx.setLineDash([]);
        ctx.fillStyle = 'rgba(255,255,255,0.45)';
        ctx.font = '11px Segoe UI, Arial, sans-serif';
        ctx.fillText(`Q${i + 2}`, xPx + 4, top + 14);
        ctx.restore();
      });
    }
  };

  new Chart(document.getElementById('scoreChart'), {
    type: 'line',
    data: {
      datasets: [
        {
          label: g.home_tricode,
          data: homeData,
          borderColor: HOME_COLOR,
          backgroundColor: 'transparent',
          tension: 0.3,
          pointRadius: 0,
          borderWidth: 2,
          stepped: false,
        },
        {
          label: g.away_tricode,
          data: awayData,
          borderColor: AWAY_COLOR,
          backgroundColor: 'transparent',
          tension: 0.3,
          pointRadius: 0,
          borderWidth: 2,
          stepped: false,
        }
      ]
    },
    options: {
      animation: false,
      responsive: true,
      maintainAspectRatio: false,
      interaction: { mode: 'index', intersect: false },
      scales: {
        x: {
          type: 'linear',
          min: 0,
          max: 40,
          title: { display: true, text: 'Game Time (min)', color: '#888' },
          ticks: { color: '#888', stepSize: 5 },
          grid: { color: 'rgba(255,255,255,0.06)' },
        },
        y: {
          title: { display: true, text: 'Score', color: '#888' },
          ticks: { color: '#888' },
          grid: { color: 'rgba(255,255,255,0.06)' },
        }
      },
      plugins: {
        legend: { labels: { color: '#ccc' } },
        tooltip: {
          callbacks: {
            title(items) {
              const elSec = items[0].parsed.x * 60;
              const ev = flow.find(d => d.elapsed_sec >= elSec - 5 && d.elapsed_sec <= elSec + 5);
              if (ev) return `Q${ev.period} ${ev.clock_display}`;
              const period = Math.floor(items[0].parsed.x / 10) + 1;
              return `Q${Math.min(period, 4)} ${(items[0].parsed.x % 10).toFixed(1)} min`;
            },
            label(item) {
              const tc = item.dataset.label;
              return ` ${tc}: ${item.parsed.y}`;
            }
          },
          backgroundColor: 'rgba(20,22,35,0.95)',
          titleColor: '#ddd',
          bodyColor: '#bbb',
          borderColor: '#444',
          borderWidth: 1,
        }
      }
    },
    plugins: [quarterLines]
  });
})();

// ─── 2. Player Stint Gantt ───────────────────────────────────────────────────
function renderStints(data) {
  const stints = data.stints;
  if (!stints.length) {
    document.getElementById('gantt-container').textContent = 'No stint data.';
    return;
  }

  const homeTC = data.game.home_tricode;
  const awayTC = data.game.away_tricode;

  // Collect unique players ordered: home first then away, by first appearance
  const seen = new Map(); // player -> team
  stints.forEach(s => { if (!seen.has(s.player)) seen.set(s.player, s.team); });

  const homePlayers = [...seen.entries()].filter(([,t]) => t === homeTC).map(([p]) => p);
  const awayPlayers = [...seen.entries()].filter(([,t]) => t !== homeTC).map(([p]) => p);

  // Build row list with team header sentinel rows
  // Each item: { type: 'header', team } or { type: 'player', player, team }
  const rows = [
    { type: 'header', team: homeTC },
    ...homePlayers.map(p => ({ type: 'player', player: p, team: homeTC })),
    { type: 'header', team: awayTC },
    ...awayPlayers.map(p => ({ type: 'player', player: p, team: awayTC })),
  ];

  // Map player name → row index (only player rows)
  const playerRowIndex = new Map();
  rows.forEach((r, i) => { if (r.type === 'player') playerRowIndex.set(r.player, i); });

  const ROW_H      = 18;
  const HEADER_H   = 22;
  const PAD_TOP    = 28;  // space for quarter labels at top
  const PAD_BOT    = 10;
  const PAD_LEFT   = 130;
  const PAD_RIGHT  = 20;
  const svgW = Math.max(800, (document.getElementById('gantt-container').clientWidth || 900) - 4);
  const chartW = svgW - PAD_LEFT - PAD_RIGHT;

  // Compute total height from row list
  let totalContentH = 0;
  const rowOffsets = rows.map(r => {
    const y = totalContentH;
    totalContentH += r.type === 'header' ? HEADER_H : ROW_H;
    return y;
  });
  const svgH = PAD_TOP + totalContentH + PAD_BOT;

  function xOf(elSec) { return PAD_LEFT + (elSec / 2400) * chartW; }

  const ns = 'http://www.w3.org/2000/svg';
  const svg = document.createElementNS(ns, 'svg');
  svg.setAttribute('width', svgW);
  svg.setAttribute('height', svgH);
  svg.style.display = 'block';

  function el(tag, attrs = {}, parent = svg) {
    const e = document.createElementNS(ns, tag);
    for (const [k, v] of Object.entries(attrs)) e.setAttribute(k, v);
    parent.appendChild(e);
    return e;
  }

  // Background
  el('rect', { x: 0, y: 0, width: svgW, height: svgH, fill: '#1a1d27' });

  // defs for clip paths
  const defs = el('defs', {});

  // Quarter band backgrounds (alternating shading Q1–Q4)
  const quarterShades = ['rgba(255,255,255,0.02)', 'rgba(255,255,255,0.05)',
                         'rgba(255,255,255,0.02)', 'rgba(255,255,255,0.05)'];
  [0,1,2,3].forEach(q => {
    const x1 = xOf(q * 600);
    const x2 = xOf((q + 1) * 600);
    el('rect', {
      x: x1, y: PAD_TOP, width: x2 - x1, height: totalContentH,
      fill: quarterShades[q]
    });
    // Quarter label centered in band, at top
    el('text', {
      x: (x1 + x2) / 2, y: PAD_TOP - 8,
      fill: '#777', 'font-size': '12', 'font-weight': '600',
      'text-anchor': 'middle', 'font-family': 'Segoe UI, Arial, sans-serif'
    }).textContent = `Q${q + 1}`;
  });

  // Quarter boundary lines
  [0, 10, 20, 30, 40].forEach(min => {
    const x = xOf(min * 60);
    el('line', {
      x1: x, y1: PAD_TOP, x2: x, y2: PAD_TOP + totalContentH,
      stroke: 'rgba(255,255,255,0.2)', 'stroke-width': min === 0 || min === 40 ? 1 : 1,
    });
  });

  // Row backgrounds + player name labels + team headers
  rows.forEach((row, i) => {
    const y = PAD_TOP + rowOffsets[i];
    const isHome = row.team === homeTC;
    const color = isHome ? HOME_COLOR : AWAY_COLOR;

    if (row.type === 'header') {
      // Team header band
      el('rect', { x: 0, y, width: svgW, height: HEADER_H,
        fill: isHome ? 'rgba(200,16,46,0.18)' : 'rgba(74,144,217,0.18)' });
      el('rect', { x: 0, y, width: 4, height: HEADER_H, fill: color });
      el('text', {
        x: 12, y: y + HEADER_H / 2 + 5,
        fill: color, 'font-size': '12', 'font-weight': '700',
        'font-family': 'Segoe UI, Arial, sans-serif', 'letter-spacing': '0.06em'
      }).textContent = row.team;
    } else {
      // Player row
      el('rect', {
        x: 0, y, width: svgW, height: ROW_H - 1,
        fill: isHome ? 'rgba(200,16,46,0.03)' : 'rgba(74,144,217,0.03)'
      });
      el('text', {
        x: PAD_LEFT - 6, y: y + ROW_H / 2 + 4,
        fill: isHome ? '#e8a0aa' : '#8ab8e0',
        'font-size': '11', 'text-anchor': 'end',
        'font-family': 'Segoe UI, Arial, sans-serif'
      }).textContent = row.player.length > 18 ? row.player.slice(0, 17) + '…' : row.player;

    }
  });

  // Stint rectangles
  const tooltip = document.getElementById('gantt-tooltip');
  function fmtClock(secs) {
    const m = Math.floor(secs / 60), s2 = Math.round(secs % 60);
    return `${m}:${String(s2).padStart(2, '0')}`;
  }

  let clipIdx = 0;
  stints.forEach(s => {
    const i = playerRowIndex.get(s.player);
    if (i === undefined) return;
    const x1 = xOf(s.start_elapsed);
    const x2 = xOf(s.end_elapsed);
    const barW = Math.max(1, x2 - x1);
    const y = PAD_TOP + rowOffsets[i] + 1;
    const barH = ROW_H - 3;
    const isHome = s.team === homeTC;
    const color = isHome ? HOME_COLOR : AWAY_COLOR;

    const rect = el('rect', {
      x: x1, y, width: barW, height: barH,
      fill: color, opacity: '0.75', rx: '2',
      style: 'cursor:pointer'
    });

    const dMin = Math.floor(s.duration_sec / 60);
    const dSec = Math.round(s.duration_sec % 60);
    const tip = `${s.player} (${s.team})  Q${s.period} ` +
      `${fmtClock(s.clock_in)}→${fmtClock(s.clock_out)}  ` +
      `${dMin}:${String(dSec).padStart(2, '0')}`;

    rect.addEventListener('mousemove', e => {
      tooltip.textContent = tip;
      tooltip.style.display = 'block';
      tooltip.style.left = (e.clientX + 12) + 'px';
      tooltip.style.top  = (e.clientY + 12) + 'px';
    });
    rect.addEventListener('mouseleave', () => { tooltip.style.display = 'none'; });

    // Stat label clipped to bar bounds (per-stint stats)
    const combo = (s.stint_reb || 0) + (s.stint_ast || 0);
    const cid = `cs${clipIdx++}`;
    const cp = document.createElementNS(ns, 'clipPath');
    cp.setAttribute('id', cid);
    const cr = document.createElementNS(ns, 'rect');
    cr.setAttribute('x', x1 + 2); cr.setAttribute('y', y);
    cr.setAttribute('width', Math.max(0, barW - 4)); cr.setAttribute('height', barH);
    cp.appendChild(cr);
    defs.appendChild(cp);

    el('text', {
      x: x1 + 4, y: y + barH / 2 + 4,
      fill: 'rgba(255,255,255,0.92)', 'font-size': '9', 'font-weight': '600',
      'text-anchor': 'start', 'font-family': 'Segoe UI, Arial, sans-serif',
      'pointer-events': 'none', 'clip-path': `url(#${cid})`
    }).textContent = `${s.stint_pts || 0} · ${combo}`;
  });

  document.getElementById('gantt-container').appendChild(svg);
}

renderStints(DATA);

// ─── 3. Box Score ────────────────────────────────────────────────────────────
function renderBoxScore(data) {
  const rows = data.box_score;
  if (!rows.length) {
    document.getElementById('box-score-container').textContent = 'No box score data.';
    return;
  }

  const cols = [
    { key: 'first',       label: 'Player',  fmt: (r) => `${r.first} ${r.last}`, sort: (a, b) => `${a.last}${a.first}`.localeCompare(`${b.last}${b.first}`) },
    { key: 'team',        label: 'Team',    fmt: (r) => r.team,       sort: (a, b) => a.team.localeCompare(b.team) },
    { key: 'minutes',     label: 'Min',     fmt: (r) => r.minutes,    sort: (a, b) => minutesToNum(a.minutes) - minutesToNum(b.minutes) },
    { key: 'pts',         label: 'Pts',     fmt: (r) => r.pts ?? '-', sort: (a, b) => (a.pts ?? 0) - (b.pts ?? 0) },
    { key: 'fgm',         label: 'FGM',     fmt: (r) => r.fgm ?? '-', sort: (a, b) => (a.fgm ?? 0) - (b.fgm ?? 0) },
    { key: 'fga',         label: 'FGA',     fmt: (r) => r.fga ?? '-', sort: (a, b) => (a.fga ?? 0) - (b.fga ?? 0) },
    { key: 'reb',         label: 'Reb',     fmt: (r) => r.reb ?? '-', sort: (a, b) => (a.reb ?? 0) - (b.reb ?? 0) },
    { key: 'ast',         label: 'Ast',     fmt: (r) => r.ast ?? '-', sort: (a, b) => (a.ast ?? 0) - (b.ast ?? 0) },
    { key: 'stl',         label: 'Stl',     fmt: (r) => r.stl ?? '-', sort: (a, b) => (a.stl ?? 0) - (b.stl ?? 0) },
    { key: 'blk',         label: 'Blk',     fmt: (r) => r.blk ?? '-', sort: (a, b) => (a.blk ?? 0) - (b.blk ?? 0) },
    { key: 'to',          label: 'TO',      fmt: (r) => r.to  ?? '-', sort: (a, b) => (a.to  ?? 0) - (b.to  ?? 0) },
    { key: 'pf',          label: 'PF',      fmt: (r) => r.pf  ?? '-', sort: (a, b) => (a.pf  ?? 0) - (b.pf  ?? 0) },
    { key: 'plus_minus',  label: '+/-',     fmt: (r) => r.plus_minus != null ? (r.plus_minus > 0 ? '+' : '') + r.plus_minus : '-',
                                              sort: (a, b) => (a.plus_minus ?? 0) - (b.plus_minus ?? 0) },
  ];

  function minutesToNum(min) {
    if (!min) return 0;
    const parts = String(min).split(':');
    return parseInt(parts[0] || 0) * 60 + parseInt(parts[1] || 0);
  }

  let sortKey = 'pts';
  let sortDir = -1; // -1 = desc, 1 = asc

  const container = document.getElementById('box-score-container');
  const table = document.createElement('table');
  const thead = table.createTHead();
  const tbody = table.createTBody();
  container.appendChild(table);

  const homeTC = data.game.home_tricode;

  function buildHeader() {
    const tr = document.createElement('tr');
    cols.forEach(col => {
      const th = document.createElement('th');
      th.textContent = col.label;
      if (col.key === sortKey) {
        th.classList.add(sortDir === -1 ? 'sort-desc' : 'sort-asc');
      }
      th.addEventListener('click', () => {
        if (sortKey === col.key) sortDir *= -1;
        else { sortKey = col.key; sortDir = -1; }
        buildAll();
      });
      tr.appendChild(th);
    });
    thead.innerHTML = '';
    thead.appendChild(tr);
  }

  function buildBody() {
    const sortCol = cols.find(c => c.key === sortKey);
    tbody.innerHTML = '';

    const homeRows = rows.filter(r => r.team === homeTC).sort((a, b) => sortCol.sort(a, b) * sortDir);
    const awayRows = rows.filter(r => r.team !== homeTC).sort((a, b) => sortCol.sort(a, b) * sortDir);

    [[homeTC, homeRows, HOME_COLOR, HOME_LIGHT], [data.game.away_tricode, awayRows, AWAY_COLOR, AWAY_LIGHT]]
      .forEach(([tc, teamRows, color, light]) => {
        // Team header row
        const htr = document.createElement('tr');
        const htd = document.createElement('td');
        htd.colSpan = cols.length;
        htd.textContent = tc;
        htd.style.cssText = `color:${color};font-weight:700;font-size:0.8rem;` +
          `background:${light};padding:4px 10px;letter-spacing:0.06em;`;
        htr.appendChild(htd);
        tbody.appendChild(htr);

        teamRows.forEach(row => {
          const tr = document.createElement('tr');
          tr.style.background = light;
          cols.forEach(col => {
            const td = document.createElement('td');
            td.textContent = col.fmt(row);
            tr.appendChild(td);
          });
          tbody.appendChild(tr);
        });
      });
  }

  function buildAll() { buildHeader(); buildBody(); }
  buildAll();
}

renderBoxScore(DATA);
</script>
</body>
</html>
"""

# ---------------------------------------------------------------------------
# Write HTML
# ---------------------------------------------------------------------------
html = HTML_TEMPLATE.replace("__GAME_DATA__", json.dumps(payload, indent=2))
out_path = Path("wnba_viz.html")
out_path.write_text(html, encoding="utf-8")
print(f"\nWritten {out_path.resolve()}")
print("Open wnba_viz.html in Chrome/Edge to view the visualizations.")
