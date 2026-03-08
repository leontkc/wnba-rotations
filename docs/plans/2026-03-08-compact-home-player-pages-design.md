# Compact Home & Player Pages Design

**Date:** 2026-03-08
**Status:** Approved

## Overview

Two features to improve navigation and reduce visual clutter:
1. Replace large game cards on home page with a compact table layout
2. Add player view pages showing all games for a specific player with mini Gantt charts

## Requirements

- **Home page:** Compact table with ~6 games visible without scrolling
- **Player pages:** Static HTML at `docs/players/<slug>.html` with mini Gantt charts
- **Navigation:** Both searchable dropdown AND clickable player names in game pages

## Architecture

### Approach: Static Generation

- Python build script extracts player data from game stints
- Generates player HTML pages during build
- Creates `players.json` manifest for search dropdown
- No runtime data fetching needed

### Files Modified/Created

**Modified:**
- `docs/assets/site.css` - Compact table styles
- `docs/index.html` - New table layout structure
- `docs/assets/viz.js` - Player name links, search dropdown
- `docs/assets/viz.css` - Player search styles
- `scripts/generate_pages.py` - Player page generation

**Created:**
- `docs/players/*.html` - One per player
- `docs/players/players.json` - Player manifest for search

## Component Designs

### 1. Compact Table Layout (Home Page)

**Structure:**
```
┌─────────────────────────────────────────────┐
│ Jun 15, 2024                                │
│ LVA 92 - PHO 78              [View Game →]  │
│ SEA 85 - MIN 91              [View Game →]  │
├─────────────────────────────────────────────┤
│ Jun 14, 2024                                │
│ NYL 78 - CHI 82              [View Game →]  │
└─────────────────────────────────────────────┘
```

**CSS:**
```css
.game-row {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 4px 6px;
  font-size: 0.78rem;
  border-bottom: 1px solid rgba(255,255,255,0.03);
}
.game-row:hover {
  background: rgba(255,255,255,0.02);
}
.game-matchup {
  font-size: 0.78rem;
  font-weight: 500;
  min-width: 85px;
  color: #bbb;
}
.game-score {
  font-size: 0.78rem;
  flex: 1;
  color: #777;
}
.game-link {
  font-size: 0.7rem;
  padding: 2px 6px;
  background: rgba(74,144,217,0.15);
  border-radius: 4px;
  color: #4a90d9;
  text-decoration: none;
}
.date-group {
  margin-top: 20px;
}
.date-header {
  font-size: 0.68rem;
  color: #666;
  text-transform: uppercase;
  letter-spacing: 0.1em;
  padding: 4px 0;
  margin-bottom: 0;
  border-bottom: 1px solid rgba(255,255,255,0.05);
}
```

### 2. Player Pages

**URL Pattern:** `docs/players/<player-slug>.html` (e.g., `aja-wilson.html`)

**Page Structure:**
```
┌─────────────────────────────────────────┐
│  ← Back to Home    [Player Search ▼]    │
├─────────────────────────────────────────┤
│  A'ja Wilson                            │
│  Las Vegas Aces · 15 games              │
├─────────────────────────────────────────┤
│  Jun 15 vs PHO (W 92-78)                │
│  ████████  ████  ██████████  28:42      │
│  32 PTS · 8 REB · 2 AST                 │
├─────────────────────────────────────────┤
│  Jun 12 @ SEA (L 85-91)                 │
│  ██████████████  ████████    31:15      │
│  25 PTS · 11 REB · 4 AST                │
└─────────────────────────────────────────┘
```

**Mini Gantt Chart:**
- Single row per game showing player's stints
- Same color coding as full Gantt
- Click game row → navigates to full game page
- Total minutes on right, stats below

**CSS:**
```css
.player-game {
  background: #1a1d27;
  border-radius: 8px;
  padding: 12px;
  margin-bottom: 12px;
  cursor: pointer;
}
.player-game:hover {
  background: #1f2231;
}
.player-game-header {
  font-size: 0.82rem;
  color: #999;
  margin-bottom: 8px;
}
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
}
.player-stats {
  font-size: 0.75rem;
  color: #888;
}
.player-minutes {
  float: right;
  color: #666;
}
```

**Data Extraction:**
```python
def extract_player_games(games):
    players = {}
    for game in games:
        for team in ['home', 'away']:
            for stint in game['stints'][team]:
                name = stint['player']
                if name not in players:
                    players[name] = {'name': name, 'team': team_abbrev, 'games': []}
                players[name]['games'].append({
                    'game_id': game['id'],
                    'date': game['date'],
                    'opponent': opponent,
                    'result': result,
                    'stints': stint['intervals'],
                    'stats': box_score_stats
                })
    return players
```

### 3. Navigation

**Player Search Dropdown (All Pages):**
```html
<div id="player-search">
  <input type="text" placeholder="Search players..." id="player-input">
  <div id="player-dropdown"></div>
</div>
```

```css
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
}
#player-dropdown.active {
  display: block;
}
.player-option {
  padding: 8px 10px;
  cursor: pointer;
  font-size: 0.8rem;
}
.player-option:hover {
  background: rgba(255,255,255,0.05);
}
```

**Clickable Player Names (Game Pages):**
- Gantt chart player names → links to player page
- Box score table player names → links to player page

```javascript
// Slugify function
function slugify(name) {
  return name.toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/(^-|-$)/g, '');
}

// In Gantt rendering - wrap name in link
const nameLink = document.createElementNS(svgNS, 'a');
nameLink.setAttributeNS('http://www.w3.org/1999/xlink', 'href',
  `../players/${slugify(player.name)}.html`);
```

## Testing

### Manual Testing Checklist

1. **Home page:**
   - Compact table displays ~6+ games without scrolling
   - Date grouping correct
   - "View Game" links work
   - Team filter still works
   - Search still works

2. **Player pages:**
   - All players have pages generated
   - Mini Gantt shows correct stints
   - Stats match box score
   - Click navigates to game page
   - Back link works

3. **Navigation:**
   - Search dropdown filters as you type
   - Clicking player navigates correctly
   - Player names in Gantt are clickable
   - Player names in box score are clickable

4. **Mobile:**
   - Compact table readable on mobile
   - Player pages responsive
   - Search dropdown works on touch
