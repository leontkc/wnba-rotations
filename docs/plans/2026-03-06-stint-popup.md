# Stint Hover Popup Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add a rich tooltip popup on stint bar hover showing stat summary + chronological timestamped PBP events (shots, assists, rebounds, steals, blocks, turnovers, fouls).

**Architecture:** Extend `compute_stints()` to attach a per-stint `events` list from raw PBP data. Update `viz.js` tooltip from plain text to HTML with a stat header and scrollable event log. Update `viz.css` for popup styling.

**Tech Stack:** Python (pandas), vanilla JS, SVG, CSS

---

### Task 1: Add per-stint events to compute_stints()

**Files:**
- Modify: `pipeline/wnba_data.py:345-383` (the per-stint stats loop)

**Step 1: Add event extraction inside the existing per-stint loop**

In `compute_stints()`, after the existing stat computation (line 380-382), add event extraction. Replace the entire stats loop (lines 345-383) with:

```python
    # Compute per-stint stats and events from PBP
    pbp_df = pbp_df.copy()
    pbp_df["_clock_secs"] = pbp_df["clock"].apply(clock_to_seconds)

    for stint in stints:
        player   = stint["player"]
        period   = stint["period"]
        clock_in = stint["clock_in"]
        clock_out = stint["clock_out"]

        if not player:
            stint.update({"stint_pts": 0, "stint_reb": 0, "stint_ast": 0, "stint_stl": 0, "stint_to": 0, "events": []})
            continue

        window_mask = (
            (pbp_df["period"] == period) &
            (pbp_df["_clock_secs"] >= clock_out) &
            (pbp_df["_clock_secs"] <= clock_in)
        )
        window = pbp_df[window_mask]
        player_ev = window[window["playerName"] == player]

        made_shots = player_ev[player_ev["actionType"] == "Made Shot"]
        pts = int(made_shots["shotValue"].fillna(0).sum())

        free_throws = player_ev[player_ev["actionType"] == "Free Throw"]
        pts += int((~free_throws["description"].str.upper().str.startswith("MISS")).sum())

        reb = int((player_ev["actionType"] == "Rebound").sum())

        ast_pat = re.compile(rf"\({re.escape(player)}\s+\d+\s+AST\)", re.IGNORECASE)
        made_in_window = window[window["actionType"] == "Made Shot"]
        ast = int(made_in_window["description"].apply(
            lambda d: bool(ast_pat.search(str(d)))).sum())

        stl = int(player_ev["description"].str.contains("STEAL", case=False, na=False).sum())
        blk = int(player_ev["description"].str.contains("BLOCK", case=False, na=False).sum())
        to = int((player_ev["actionType"] == "Turnover").sum())

        stint["stint_pts"] = pts
        stint["stint_reb"] = reb
        stint["stint_ast"] = ast
        stint["stint_stl"] = stl
        stint["stint_blk"] = blk
        stint["stint_to"]  = to

        # Collect timestamped events for this player during the stint
        event_types = {"Made Shot", "Missed Shot", "Free Throw", "Rebound", "Turnover", "Foul"}
        events = []

        for _, ev in player_ev.iterrows():
            action = str(ev.get("actionType", ""))
            desc = str(ev.get("description", ""))

            # Include known action types + steal/block events (which have empty actionType)
            if action in event_types or "STEAL" in desc.upper() or "BLOCK" in desc.upper():
                events.append({
                    "clock": clock_display(ev.get("clock", "")),
                    "type": action if action else ("Steal" if "STEAL" in desc.upper() else "Block"),
                    "detail": desc,
                })

        # Also find assists: made shots by teammates where this player is credited
        for _, ev in made_in_window.iterrows():
            desc = str(ev.get("description", ""))
            if ast_pat.search(desc):
                events.append({
                    "clock": clock_display(ev.get("clock", "")),
                    "type": "Assist",
                    "detail": desc,
                })

        # Sort events by clock descending (game clock counts down)
        events.sort(key=lambda e: e["clock"], reverse=True)
        stint["events"] = events

    return stints
```

**Step 2: Verify locally with one game**

Run:
```bash
cd "C:/Users/leont/WNBA Rotations"
python -c "
from pipeline.wnba_data import fetch_pbp, compute_stints
import json
pbp = fetch_pbp('1022400001')
stints = compute_stints(pbp)
# Show first stint with events
for s in stints:
    if s.get('events'):
        print(json.dumps(s, indent=2))
        break
"
```
Expected: A stint dict with an `events` array containing timestamped plays.

**Step 3: Commit**

```bash
git add pipeline/wnba_data.py
git commit -m "feat: add per-stint PBP events to compute_stints output"
```

---

### Task 2: Update tooltip CSS

**Files:**
- Modify: `docs/assets/viz.css:31-36` (the `#gantt-tooltip` rule)

**Step 1: Replace the gantt-tooltip CSS with rich popup styles**

Replace lines 31-36 with:

```css
/* Gantt tooltip — rich stint popup */
#gantt-tooltip {
  position: fixed; background: rgba(20,22,35,0.97); border: 1px solid #555;
  border-radius: 8px; padding: 0; font-size: 0.78rem; color: #e0e0e0;
  pointer-events: none; display: none; z-index: 999;
  min-width: 260px; max-width: 340px; max-height: 300px;
  box-shadow: 0 4px 20px rgba(0,0,0,0.5);
  overflow: hidden;
}
#gantt-tooltip .tip-header {
  padding: 8px 12px; border-bottom: 1px solid #333;
  font-weight: 600; font-size: 0.82rem; color: #fff;
}
#gantt-tooltip .tip-header .tip-time {
  font-weight: 400; color: #999; font-size: 0.75rem;
}
#gantt-tooltip .tip-stats {
  padding: 6px 12px; border-bottom: 1px solid #333;
  display: flex; gap: 10px; font-size: 0.75rem; color: #bbb;
}
#gantt-tooltip .tip-stats span { white-space: nowrap; }
#gantt-tooltip .tip-stats .stat-val { color: #fff; font-weight: 600; }
#gantt-tooltip .tip-events {
  max-height: 180px; overflow-y: auto; padding: 4px 0;
}
#gantt-tooltip .tip-events::-webkit-scrollbar { width: 4px; }
#gantt-tooltip .tip-events::-webkit-scrollbar-thumb { background: #444; border-radius: 2px; }
#gantt-tooltip .tip-ev {
  padding: 2px 12px; font-size: 0.72rem; display: flex; gap: 8px;
  border-bottom: 1px solid rgba(255,255,255,0.04);
}
#gantt-tooltip .tip-ev:hover { background: rgba(255,255,255,0.03); }
#gantt-tooltip .tip-ev .ev-clock { color: #888; min-width: 32px; flex-shrink: 0; }
#gantt-tooltip .tip-ev .ev-type { min-width: 70px; flex-shrink: 0; font-weight: 500; }
#gantt-tooltip .tip-ev .ev-detail { color: #aaa; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
#gantt-tooltip .tip-ev.ev-made { color: #6fcf6f; }
#gantt-tooltip .tip-ev.ev-miss { color: #cf6f6f; }
#gantt-tooltip .tip-ev.ev-ast { color: #6fb3cf; }
#gantt-tooltip .tip-ev.ev-to { color: #cf9f6f; }
#gantt-tooltip .tip-ev.ev-stl, #gantt-tooltip .tip-ev.ev-blk { color: #b094d6; }
```

**Step 2: Commit**

```bash
git add docs/assets/viz.css
git commit -m "feat: add rich stint popup CSS styles"
```

---

### Task 3: Update tooltip JS in viz.js

**Files:**
- Modify: `docs/assets/viz.js:251-287` (the tooltip event handlers in renderStints)

**Step 1: Replace tooltip rendering logic**

Replace lines 251-287 (from `const tooltip = ...` through the `mouseleave` handler inside the `stints.forEach`) with:

```javascript
  const tooltip = document.getElementById('gantt-tooltip');
  function fmtClock(secs) {
    const m = Math.floor(secs / 60), s2 = Math.round(secs % 60);
    return `${m}:${String(s2).padStart(2, '0')}`;
  }

  function evClass(type) {
    if (type === 'Made Shot' || type === 'Free Throw') return 'ev-made';
    if (type === 'Missed Shot') return 'ev-miss';
    if (type === 'Assist') return 'ev-ast';
    if (type === 'Turnover') return 'ev-to';
    if (type === 'Steal' || type === 'Block') return 'ev-stl';
    return '';
  }

  function buildTooltipHTML(s) {
    const dMin = Math.floor(s.duration_sec / 60);
    const dSec = Math.round(s.duration_sec % 60);
    const dur = `${dMin}:${String(dSec).padStart(2, '0')}`;

    let html = `<div class="tip-header">${s.player} <span style="color:${s.team === homeTC ? HOME_COLOR : AWAY_COLOR}">(${s.team})</span>`
      + `<br><span class="tip-time">Q${s.period} ${fmtClock(s.clock_in)} → ${fmtClock(s.clock_out)}  ·  ${dur}</span></div>`;

    html += `<div class="tip-stats">`
      + `<span><span class="stat-val">${s.stint_pts || 0}</span> PTS</span>`
      + `<span><span class="stat-val">${s.stint_reb || 0}</span> REB</span>`
      + `<span><span class="stat-val">${s.stint_ast || 0}</span> AST</span>`
      + `<span><span class="stat-val">${s.stint_stl || 0}</span> STL</span>`
      + `<span><span class="stat-val">${s.stint_blk || 0}</span> BLK</span>`
      + `<span><span class="stat-val">${s.stint_to || 0}</span> TO</span>`
      + `</div>`;

    const events = s.events || [];
    if (events.length) {
      html += `<div class="tip-events">`;
      events.forEach(ev => {
        html += `<div class="tip-ev ${evClass(ev.type)}">`
          + `<span class="ev-clock">${ev.clock}</span>`
          + `<span class="ev-type">${ev.type}</span>`
          + `<span class="ev-detail">${ev.detail}</span>`
          + `</div>`;
      });
      html += `</div>`;
    }

    return html;
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

    const tipHTML = buildTooltipHTML(s);

    rect.addEventListener('mousemove', e => {
      tooltip.innerHTML = tipHTML;
      tooltip.style.display = 'block';
      // Position: prefer right of cursor, flip if near right edge
      const tx = (e.clientX + 16 + 340 > window.innerWidth) ? e.clientX - 350 : e.clientX + 16;
      const ty = Math.min(e.clientY + 12, window.innerHeight - 320);
      tooltip.style.left = tx + 'px';
      tooltip.style.top  = ty + 'px';
    });
    rect.addEventListener('mouseleave', () => { tooltip.style.display = 'none'; });
```

Note: the rest of the stint loop (clipPath + stat text on bars, lines ~289-304) stays unchanged.

**Step 2: Commit**

```bash
git add docs/assets/viz.js
git commit -m "feat: render rich HTML stint popup with PBP events"
```

---

### Task 4: Regenerate all game HTML files

**Step 1: Run pipeline with --force**

```bash
cd "C:/Users/leont/WNBA Rotations"
python -m pipeline.build_season --seasons 2024 2025 --force
```

This will regenerate all 427 HTML files with the new payload (including `events` arrays and `stint_stl`/`stint_blk`/`stint_to` fields).

**Step 2: Verify a game page**

Open `docs/games/1022400001.html` in a browser and hover over a stint bar. Should see:
- Header with player name, team, period, time range
- Stat summary line (PTS/REB/AST/STL/BLK/TO)
- Scrollable chronological event list

**Step 3: Commit and push**

```bash
git add docs/ data/manifest.json
git commit -m "feat: regenerate all games with stint event data"
git push
```
