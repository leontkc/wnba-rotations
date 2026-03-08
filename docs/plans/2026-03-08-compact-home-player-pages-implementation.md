# Compact Home & Player Pages Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Make home page more compact and add player view pages with mini Gantt charts.

**Architecture:** Static HTML generation via Python. Player pages generated from game stint data during build. Player search dropdown loads players.json manifest.

**Tech Stack:** Python 3, HTML/CSS/JS, SVG for mini Gantt charts

---

## Task 1: Compact Home Page CSS

**Files:**
- Modify: `docs/assets/site.css:64-81`

**Step 1: Update game row styles for compact layout**

Replace the existing `.game-row` and related styles (lines 64-81) with more compact versions:

```css
.game-row {
  display: flex; align-items: center; gap: 8px;
  padding: 4px 6px; border-radius: 4px;
  transition: background 0.12s;
  text-decoration: none; color: inherit;
  font-size: 0.78rem;
  border-bottom: 1px solid rgba(255,255,255,0.03);
}
.game-row:hover { background: rgba(255,255,255,0.04); }
.game-matchup { font-size: 0.78rem; font-weight: 500; color: #bbb; min-width: 85px; }
.game-score   { font-size: 0.78rem; color: #777; flex: 1; }
.game-score .winner { color: #aaa; font-weight: 600; }
.game-link {
  font-size: 0.7rem; color: #4a90d9; text-decoration: none;
  padding: 2px 6px; background: rgba(74,144,217,0.15);
  border-radius: 4px; white-space: nowrap;
  transition: background 0.12s;
}
.game-link:hover { background: rgba(74,144,217,0.25); }
```

**Step 2: Update date header for compactness**

Update `.date-group` and `.date-header` (lines 55-62):

```css
.date-group { margin-top: 16px; }
.date-header {
  font-size: 0.68rem; font-weight: 600; color: #555;
  text-transform: uppercase; letter-spacing: 0.1em;
  padding: 4px 0;
  border-bottom: 1px solid rgba(255,255,255,0.05);
  margin-bottom: 0;
}
```

**Step 3: Verify visually**

Open `docs/index.html` in browser. Should see ~6+ games visible without scrolling.

**Step 4: Commit**

```bash
git add docs/assets/site.css
git commit -m "style: compact home page game rows"
```

---

## Task 2: Add slugify helper and player link generation

**Files:**
- Modify: `docs/assets/viz.js:41-46` (after abbreviateName function)

**Step 1: Add slugify function after abbreviateName**

Insert after line 46 (after `abbreviateName` function):

```javascript
function slugify(name) {
  if (!name) return '';
  return name.toLowerCase()
    .normalize('NFD').replace(/[\u0300-\u036f]/g, '') // remove accents
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/(^-|-$)/g, '');
}

function playerPageUrl(name) {
  return `../players/${slugify(name)}.html`;
}
```

**Step 2: Verify function works**

Open browser console on any game page, test:
```javascript
slugify("A'ja Wilson")  // should return "a-ja-wilson"
slugify("Brionna Jones")  // should return "brionna-jones"
```

**Step 3: Commit**

```bash
git add docs/assets/viz.js
git commit -m "feat: add slugify helper for player page URLs"
```

---

## Task 3: Make Gantt player names clickable

**Files:**
- Modify: `docs/assets/viz.js:276-299` (player name text rendering)

**Step 1: Wrap player name text in SVG anchor**

Find the player name rendering code (around line 281-299). Replace:

```javascript
      el('text', {
        x: PAD_LEFT - 6, y: y + ROW_H / 2 + 4,
        fill: isHome ? '#e8a0aa' : '#8ab8e0',
        'font-size': nameFontSize, 'text-anchor': 'end',
        'font-family': 'Segoe UI, Arial, sans-serif'
      }).textContent = displayName;
```

With:

```javascript
      // Create clickable player name link
      const nameLink = el('a', {
        'href': playerPageUrl(row.player),
        style: 'cursor: pointer;'
      });
      const nameText = document.createElementNS(ns, 'text');
      nameText.setAttribute('x', PAD_LEFT - 6);
      nameText.setAttribute('y', y + ROW_H / 2 + 4);
      nameText.setAttribute('fill', isHome ? '#e8a0aa' : '#8ab8e0');
      nameText.setAttribute('font-size', nameFontSize);
      nameText.setAttribute('text-anchor', 'end');
      nameText.setAttribute('font-family', 'Segoe UI, Arial, sans-serif');
      nameText.textContent = displayName;
      nameLink.appendChild(nameText);
      svg.appendChild(nameLink);
```

Note: The `el()` helper appends to svg, but we need to append text to link first. Adjust the code to not auto-append.

**Step 2: Update el() helper or create separate elements**

Actually simpler approach - just create the elements directly without using `el()` for the name link:

```javascript
      // Create clickable player name link
      const nameLink = document.createElementNS(ns, 'a');
      nameLink.setAttributeNS('http://www.w3.org/1999/xlink', 'xlink:href', playerPageUrl(row.player));
      nameLink.setAttribute('style', 'cursor: pointer;');

      const nameText = document.createElementNS(ns, 'text');
      nameText.setAttribute('x', PAD_LEFT - 6);
      nameText.setAttribute('y', y + ROW_H / 2 + 4);
      nameText.setAttribute('fill', isHome ? '#e8a0aa' : '#8ab8e0');
      nameText.setAttribute('font-size', nameFontSize);
      nameText.setAttribute('text-anchor', 'end');
      nameText.setAttribute('font-family', 'Segoe UI, Arial, sans-serif');
      nameText.textContent = displayName;

      nameLink.appendChild(nameText);
      svg.appendChild(nameLink);
```

**Step 3: Add hover effect CSS**

In `docs/assets/viz.css`, add at the end:

```css
/* Clickable player names in Gantt */
#gantt-container svg a text:hover {
  fill: #fff !important;
  text-decoration: underline;
}
```

**Step 4: Test clicking player name**

Open a game page, click a player name. Should navigate to `/players/player-name.html` (404 is expected for now).

**Step 5: Commit**

```bash
git add docs/assets/viz.js docs/assets/viz.css
git commit -m "feat: make Gantt player names clickable"
```

---

## Task 4: Make box score player names clickable

**Files:**
- Modify: `docs/assets/viz.js:478-479` (player column formatter)
- Modify: `docs/assets/viz.js:552-555` (cell rendering)

**Step 1: Update player column formatter to return link HTML**

Find the cols definition (line 478-479):

```javascript
    { key: 'first',      label: 'Player', fmt: (r) => `${r.first} ${r.last}`, sort: ... },
```

Change to:

```javascript
    { key: 'first',      label: 'Player',
      fmt: (r) => `<a href="${playerPageUrl(r.first + ' ' + r.last)}" class="player-link">${r.first} ${r.last}</a>`,
      sort: (a, b) => `${a.last}${a.first}`.localeCompare(`${b.last}${b.first}`),
      isHtml: true },
```

**Step 2: Update cell rendering to handle HTML**

Find the cell rendering (around line 552-555):

```javascript
            const td = document.createElement('td');
            td.textContent = col.fmt(row);
            tr.appendChild(td);
```

Change to:

```javascript
            const td = document.createElement('td');
            if (col.isHtml) {
              td.innerHTML = col.fmt(row);
            } else {
              td.textContent = col.fmt(row);
            }
            tr.appendChild(td);
```

**Step 3: Add player link CSS**

In `docs/assets/viz.css`, add:

```css
/* Clickable player names in box score */
.player-link {
  color: inherit;
  text-decoration: none;
}
.player-link:hover {
  color: #fff;
  text-decoration: underline;
}
```

**Step 4: Test**

Open a game page, click player name in box score. Should navigate to player page URL.

**Step 5: Commit**

```bash
git add docs/assets/viz.js docs/assets/viz.css
git commit -m "feat: make box score player names clickable"
```

---

## Task 5: Create player page template

**Files:**
- Create: `templates/player.html`

**Step 1: Create the template**

```html
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>__PLAYER_NAME__ — wnbarotations</title>
<link rel="stylesheet" href="../assets/viz.css">
<link rel="stylesheet" href="../assets/player.css">
</head>
<body>
<nav id="game-nav">
  <a href="../index.html" id="nav-home">← wnbarotations</a>
  <div id="player-search">
    <input type="text" placeholder="Search players..." id="player-input">
    <div id="player-dropdown"></div>
  </div>
</nav>

<header class="player-header">
  <h1>__PLAYER_NAME__</h1>
  <p class="player-meta">__PLAYER_TEAM__ · __GAME_COUNT__ games</p>
</header>

<main id="player-games">
__GAMES_HTML__
</main>

<script>
const PLAYER_DATA = __PLAYER_DATA__;
</script>
<script src="../assets/player.js"></script>
</body>
</html>
```

**Step 2: Commit**

```bash
git add templates/player.html
git commit -m "feat: add player page template"
```

---

## Task 6: Create player page CSS

**Files:**
- Create: `docs/assets/player.css`

**Step 1: Create the CSS file**

```css
/* Player page styles */
.player-header {
  padding: 20px;
  border-bottom: 1px solid rgba(255,255,255,0.07);
}
.player-header h1 {
  font-size: 1.4rem;
  font-weight: 700;
  color: #fff;
  margin-bottom: 4px;
}
.player-meta {
  font-size: 0.82rem;
  color: #666;
}

#player-games {
  padding: 20px;
}

.player-game {
  background: #1a1d27;
  border-radius: 8px;
  padding: 12px;
  margin-bottom: 12px;
  cursor: pointer;
  transition: background 0.15s;
}
.player-game:hover {
  background: #1f2231;
}
.player-game-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-size: 0.82rem;
  color: #999;
  margin-bottom: 8px;
}
.player-game-header .game-result {
  font-weight: 600;
}
.player-game-header .game-result.win { color: #6fcf6f; }
.player-game-header .game-result.loss { color: #cf6f6f; }

.mini-gantt {
  height: 20px;
  background: #22263a;
  border-radius: 4px;
  position: relative;
  margin-bottom: 6px;
}
.mini-stint {
  position: absolute;
  height: 100%;
  border-radius: 3px;
  opacity: 0.8;
}
.mini-stint.home { background: #c8102e; }
.mini-stint.away { background: #4a90d9; }

.player-game-stats {
  display: flex;
  gap: 12px;
  font-size: 0.75rem;
  color: #888;
}
.player-game-stats .stat-val {
  color: #ccc;
  font-weight: 600;
}
.player-minutes {
  margin-left: auto;
  color: #666;
}

/* Player search dropdown */
#player-search {
  position: relative;
  width: 180px;
}
#player-input {
  width: 100%;
  padding: 6px 10px;
  background: #22263a;
  border: 1px solid #333;
  border-radius: 6px;
  color: #e0e0e0;
  font-size: 0.8rem;
  font-family: inherit;
}
#player-input:focus {
  outline: none;
  border-color: #4a90d9;
}
#player-dropdown {
  position: absolute;
  top: 100%;
  left: 0;
  right: 0;
  background: #1a1d27;
  border: 1px solid #333;
  border-radius: 6px;
  max-height: 200px;
  overflow-y: auto;
  display: none;
  z-index: 100;
  margin-top: 4px;
}
#player-dropdown.active {
  display: block;
}
.player-option {
  padding: 8px 10px;
  cursor: pointer;
  font-size: 0.8rem;
  color: #e0e0e0;
}
.player-option:hover {
  background: rgba(255,255,255,0.05);
}

/* Mobile responsive */
@media (max-width: 480px) {
  .player-header { padding: 14px; }
  .player-header h1 { font-size: 1.1rem; }
  #player-games { padding: 14px; }
  .player-game { padding: 10px; }
  .player-game-stats { flex-wrap: wrap; gap: 8px; }
  #player-search { width: 140px; }
}
```

**Step 2: Commit**

```bash
git add docs/assets/player.css
git commit -m "feat: add player page CSS"
```

---

## Task 7: Create player page JavaScript

**Files:**
- Create: `docs/assets/player.js`

**Step 1: Create the JS file**

```javascript
// Player page JavaScript

// Render mini Gantt charts for each game
(function renderMiniGantts() {
  document.querySelectorAll('.mini-gantt').forEach(container => {
    const stints = JSON.parse(container.dataset.stints || '[]');
    const isHome = container.dataset.ishome === 'true';
    const totalSec = 2400; // 40 minutes

    stints.forEach(stint => {
      const bar = document.createElement('div');
      bar.className = `mini-stint ${isHome ? 'home' : 'away'}`;
      bar.style.left = `${(stint.start / totalSec) * 100}%`;
      bar.style.width = `${((stint.end - stint.start) / totalSec) * 100}%`;
      container.appendChild(bar);
    });
  });
})();

// Click game to navigate
document.querySelectorAll('.player-game').forEach(el => {
  el.addEventListener('click', () => {
    window.location.href = el.dataset.href;
  });
});

// Player search dropdown
(function initPlayerSearch() {
  const input = document.getElementById('player-input');
  const dropdown = document.getElementById('player-dropdown');
  if (!input || !dropdown) return;

  let players = [];

  // Load players manifest
  fetch('../players/players.json')
    .then(r => r.json())
    .then(data => { players = data; })
    .catch(() => { console.warn('Could not load players.json'); });

  function slugify(name) {
    if (!name) return '';
    return name.toLowerCase()
      .normalize('NFD').replace(/[\u0300-\u036f]/g, '')
      .replace(/[^a-z0-9]+/g, '-')
      .replace(/(^-|-$)/g, '');
  }

  input.addEventListener('focus', () => {
    if (players.length) renderDropdown('');
  });

  input.addEventListener('input', () => {
    renderDropdown(input.value.trim().toLowerCase());
  });

  document.addEventListener('click', (e) => {
    if (!e.target.closest('#player-search')) {
      dropdown.classList.remove('active');
    }
  });

  function renderDropdown(filter) {
    const filtered = players.filter(p =>
      p.name.toLowerCase().includes(filter)
    ).slice(0, 20);

    if (!filtered.length) {
      dropdown.classList.remove('active');
      return;
    }

    dropdown.innerHTML = filtered.map(p =>
      `<div class="player-option" data-slug="${p.slug}">${p.name}</div>`
    ).join('');
    dropdown.classList.add('active');

    dropdown.querySelectorAll('.player-option').forEach(opt => {
      opt.addEventListener('click', () => {
        window.location.href = `../players/${opt.dataset.slug}.html`;
      });
    });
  }
})();
```

**Step 2: Commit**

```bash
git add docs/assets/player.js
git commit -m "feat: add player page JavaScript"
```

---

## Task 8: Create player page generator Python script

**Files:**
- Create: `pipeline/build_players.py`

**Step 1: Create the Python script**

```python
"""
build_players.py — Generate player pages from game data.

Scans all game HTML files, extracts player stint data, generates:
- docs/players/<slug>.html for each player
- docs/players/players.json manifest for search
"""

import json
import logging
import re
from collections import defaultdict
from pathlib import Path

from pipeline.config import DOCS_DIR, GAMES_DIR, TEMPLATES_DIR

log = logging.getLogger(__name__)

PLAYERS_DIR = DOCS_DIR / "players"


def slugify(name: str) -> str:
    """Convert player name to URL slug."""
    import unicodedata
    name = unicodedata.normalize('NFD', name)
    name = ''.join(c for c in name if not unicodedata.combining(c))
    name = re.sub(r'[^a-z0-9]+', '-', name.lower())
    return name.strip('-')


def extract_player_data_from_games() -> dict:
    """
    Scan all game HTML files and extract player data.
    Returns: {player_name: {name, team, games: [...]}}
    """
    players = defaultdict(lambda: {'name': '', 'team': '', 'games': []})

    for game_file in GAMES_DIR.glob('*.html'):
        try:
            content = game_file.read_text(encoding='utf-8')

            # Extract DATA JSON from script tag
            match = re.search(r'const DATA = ({.*?});', content, re.DOTALL)
            if not match:
                continue

            data = json.loads(match.group(1))
            game_info = data.get('game', {})
            stints = data.get('stints', [])
            box_score = data.get('box_score', [])

            game_id = game_info.get('id', game_file.stem)
            date = game_info.get('date', '')
            home_tc = game_info.get('home_tricode', '')
            away_tc = game_info.get('away_tricode', '')
            score_home = game_info.get('score_home', 0)
            score_away = game_info.get('score_away', 0)

            # Build box score lookup for full stats
            box_lookup = {}
            for row in box_score:
                full_name = f"{row.get('first', '')} {row.get('last', '')}".strip()
                if full_name:
                    box_lookup[full_name] = row

            # Group stints by player
            player_stints = defaultdict(list)
            for stint in stints:
                player = stint.get('player', '')
                team = stint.get('team', '')
                if not player or not team:
                    continue
                player_stints[player].append({
                    'start': stint.get('start_elapsed', 0),
                    'end': stint.get('end_elapsed', 0),
                    'pts': stint.get('stint_pts', 0),
                    'reb': stint.get('stint_reb', 0),
                    'ast': stint.get('stint_ast', 0),
                })
                # Set team
                if not players[player]['team']:
                    players[player]['team'] = team
                players[player]['name'] = player

            # Add game entry for each player
            for player, stint_list in player_stints.items():
                team = players[player]['team']
                is_home = team == home_tc
                opponent = away_tc if is_home else home_tc
                own_score = score_home if is_home else score_away
                opp_score = score_away if is_home else score_home
                won = own_score > opp_score

                # Aggregate stats from stints
                total_pts = sum(s['pts'] for s in stint_list)
                total_reb = sum(s['reb'] for s in stint_list)
                total_ast = sum(s['ast'] for s in stint_list)

                # Calculate total minutes
                total_sec = sum(s['end'] - s['start'] for s in stint_list)
                minutes = f"{int(total_sec // 60)}:{int(total_sec % 60):02d}"

                # Get full box score stats if available
                box_row = box_lookup.get(player, {})

                players[player]['games'].append({
                    'game_id': game_id,
                    'date': date,
                    'opponent': opponent,
                    'is_home': is_home,
                    'own_score': own_score,
                    'opp_score': opp_score,
                    'won': won,
                    'stints': [{'start': s['start'], 'end': s['end']} for s in stint_list],
                    'minutes': minutes,
                    'pts': box_row.get('pts', total_pts),
                    'reb': box_row.get('reb', total_reb),
                    'ast': box_row.get('ast', total_ast),
                })
        except Exception as e:
            log.warning(f"Error processing {game_file}: {e}")
            continue

    # Sort games by date (newest first)
    for player_data in players.values():
        player_data['games'].sort(key=lambda g: g['date'], reverse=True)

    return dict(players)


def generate_player_html(player_data: dict) -> str:
    """Generate HTML for a single player page."""
    template = (TEMPLATES_DIR / 'player.html').read_text(encoding='utf-8')

    name = player_data['name']
    team = player_data['team']
    games = player_data['games']

    # Build games HTML
    games_html_parts = []
    for g in games:
        result_class = 'win' if g['won'] else 'loss'
        result_text = 'W' if g['won'] else 'L'
        location = 'vs' if g['is_home'] else '@'

        stints_json = json.dumps(g['stints'])

        games_html_parts.append(f'''
<div class="player-game" data-href="../games/{g['game_id']}.html">
  <div class="player-game-header">
    <span>{g['date']} {location} {g['opponent']}</span>
    <span class="game-result {result_class}">{result_text} {g['own_score']}-{g['opp_score']}</span>
  </div>
  <div class="mini-gantt" data-stints='{stints_json}' data-ishome='{str(g["is_home"]).lower()}'></div>
  <div class="player-game-stats">
    <span><span class="stat-val">{g['pts']}</span> PTS</span>
    <span><span class="stat-val">{g['reb']}</span> REB</span>
    <span><span class="stat-val">{g['ast']}</span> AST</span>
    <span class="player-minutes">{g['minutes']}</span>
  </div>
</div>''')

    games_html = '\n'.join(games_html_parts)

    # Replace placeholders
    html = template.replace('__PLAYER_NAME__', name)
    html = html.replace('__PLAYER_TEAM__', team)
    html = html.replace('__GAME_COUNT__', str(len(games)))
    html = html.replace('__GAMES_HTML__', games_html)
    html = html.replace('__PLAYER_DATA__', json.dumps(player_data))

    return html


def generate_players_manifest(players: dict) -> list:
    """Generate players.json manifest for search."""
    manifest = []
    for name, data in sorted(players.items()):
        manifest.append({
            'name': name,
            'slug': slugify(name),
            'team': data['team'],
            'games': len(data['games']),
        })
    return manifest


def build_player_pages() -> None:
    """Main entry point: generate all player pages."""
    log.info("Extracting player data from games...")
    players = extract_player_data_from_games()

    if not players:
        log.warning("No player data found")
        return

    log.info(f"Found {len(players)} players")

    # Create players directory
    PLAYERS_DIR.mkdir(parents=True, exist_ok=True)

    # Generate player pages
    for name, data in players.items():
        if not data['games']:
            continue

        slug = slugify(name)
        html = generate_player_html(data)
        out_path = PLAYERS_DIR / f"{slug}.html"
        out_path.write_text(html, encoding='utf-8')

    log.info(f"Generated {len(players)} player pages")

    # Generate manifest
    manifest = generate_players_manifest(players)
    manifest_path = PLAYERS_DIR / 'players.json'
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding='utf-8')
    log.info(f"Generated players.json with {len(manifest)} entries")


if __name__ == '__main__':
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        datefmt="%H:%M:%S",
    )
    build_player_pages()
```

**Step 2: Test the script**

```bash
cd /Users/leonchiu/wnba-rotations
python -m pipeline.build_players
```

Expected: Creates `docs/players/` directory with player HTML files and `players.json`.

**Step 3: Commit**

```bash
git add pipeline/build_players.py
git commit -m "feat: add player page generator script"
```

---

## Task 9: Update build_season.py to call player generator

**Files:**
- Modify: `pipeline/build_season.py`

**Step 1: Import build_players module**

At the top of the file, add import:

```python
from pipeline.build_players import build_player_pages
```

**Step 2: Call build_player_pages after index generation**

Find where `generate_index` is called (near end of `main()` function). Add after it:

```python
    # Generate player pages
    log.info("Building player pages...")
    build_player_pages()
```

**Step 3: Test full pipeline**

```bash
python -m pipeline.build_season --seasons 2024
```

Verify player pages are generated.

**Step 4: Commit**

```bash
git add pipeline/build_season.py
git commit -m "feat: integrate player page generation into build pipeline"
```

---

## Task 10: Add player search to game pages

**Files:**
- Modify: `templates/game.html`
- Modify: `docs/assets/viz.js`

**Step 1: Add player search HTML to game template**

In `templates/game.html`, update the nav section (line 13-16):

```html
<nav id="game-nav">
  <a href="../index.html" id="nav-home">← wnbarotations</a>
  <div id="player-search">
    <input type="text" placeholder="Search players..." id="player-input">
    <div id="player-dropdown"></div>
  </div>
  <span id="nav-adjacent"></span>
</nav>
```

**Step 2: Add player search CSS to viz.css**

In `docs/assets/viz.css`, add at the end:

```css
/* Player search dropdown (game pages) */
#game-nav {
  display: flex;
  align-items: center;
  gap: 16px;
}
#player-search {
  position: relative;
  width: 160px;
  margin-left: auto;
}
#player-input {
  width: 100%;
  padding: 5px 10px;
  background: #22263a;
  border: 1px solid #333;
  border-radius: 6px;
  color: #e0e0e0;
  font-size: 0.78rem;
  font-family: inherit;
}
#player-input:focus {
  outline: none;
  border-color: #4a90d9;
}
#player-dropdown {
  position: absolute;
  top: 100%;
  left: 0;
  right: 0;
  background: #1a1d27;
  border: 1px solid #333;
  border-radius: 6px;
  max-height: 200px;
  overflow-y: auto;
  display: none;
  z-index: 100;
  margin-top: 4px;
}
#player-dropdown.active {
  display: block;
}
.player-option {
  padding: 8px 10px;
  cursor: pointer;
  font-size: 0.78rem;
  color: #e0e0e0;
}
.player-option:hover {
  background: rgba(255,255,255,0.05);
}
@media (max-width: 480px) {
  #player-search { width: 120px; }
}
```

**Step 3: Add player search JS to viz.js**

At the end of `docs/assets/viz.js`, add:

```javascript
// ─── Player Search Dropdown ──────────────────────────────────────────────────
(function initPlayerSearch() {
  const input = document.getElementById('player-input');
  const dropdown = document.getElementById('player-dropdown');
  if (!input || !dropdown) return;

  let players = [];

  // Load players manifest
  fetch('../players/players.json')
    .then(r => r.json())
    .then(data => { players = data; })
    .catch(() => { console.warn('Could not load players.json'); });

  input.addEventListener('focus', () => {
    if (players.length) renderDropdown('');
  });

  input.addEventListener('input', () => {
    renderDropdown(input.value.trim().toLowerCase());
  });

  document.addEventListener('click', (e) => {
    if (!e.target.closest('#player-search')) {
      dropdown.classList.remove('active');
    }
  });

  function renderDropdown(filter) {
    const filtered = players.filter(p =>
      p.name.toLowerCase().includes(filter)
    ).slice(0, 15);

    if (!filtered.length) {
      dropdown.classList.remove('active');
      return;
    }

    dropdown.innerHTML = filtered.map(p =>
      `<div class="player-option" data-slug="${p.slug}">${p.name} <span style="color:#666;font-size:0.7rem">(${p.team})</span></div>`
    ).join('');
    dropdown.classList.add('active');

    dropdown.querySelectorAll('.player-option').forEach(opt => {
      opt.addEventListener('click', () => {
        window.location.href = `../players/${opt.dataset.slug}.html`;
      });
    });
  }
})();
```

**Step 4: Regenerate game HTML files**

```bash
python -m pipeline.build_season --seasons 2024 --force
```

**Step 5: Test**

Open a game page, verify search dropdown works.

**Step 6: Commit**

```bash
git add templates/game.html docs/assets/viz.js docs/assets/viz.css
git commit -m "feat: add player search dropdown to game pages"
```

---

## Task 11: Integration test

**Step 1: Run full build**

```bash
cd /Users/leonchiu/wnba-rotations
python -m pipeline.build_season --seasons 2024 2025 --force
```

**Step 2: Test home page**

Open `docs/index.html` in browser:
- Verify compact layout (6+ games visible)
- Verify team filter works
- Verify search works

**Step 3: Test game page**

Open any game page:
- Verify player names in Gantt are clickable
- Verify player names in box score are clickable
- Verify player search dropdown works

**Step 4: Test player page**

Click any player name:
- Verify player page loads
- Verify mini Gantt charts render
- Verify clicking game navigates to game page
- Verify player search works

**Step 5: Test mobile**

Open Chrome DevTools, test on mobile viewport:
- Home page responsive
- Player page responsive
- Search dropdown usable on touch

**Step 6: Final commit**

```bash
git add -A
git commit -m "feat: complete compact home & player pages implementation"
```
