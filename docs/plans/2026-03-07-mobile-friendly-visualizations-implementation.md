# Mobile-Friendly Visualizations Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Make WNBA Rotations visualizations responsive and touch-friendly across all mobile screen sizes (320-768px).

**Architecture:** CSS media queries for layout changes at 480px and 768px breakpoints. JavaScript for mobile detection, touch event handling, and responsive Gantt rendering. No new files—all changes to existing `viz.css` and `viz.js`.

**Tech Stack:** Vanilla CSS media queries, Vanilla JS touch events, Chart.js responsive options.

---

## Task 1: Add Mobile Detection Helper

**Files:**
- Modify: `docs/assets/viz.js:14-26` (after existing helpers)

**Step 1: Add the mobile detection helper**

Add after line 26 (after `teamColor` function):

```javascript
// ─── Mobile Detection ───────────────────────────────────────────────────────
function isMobile() {
  return window.innerWidth <= 768;
}

function isSmallMobile() {
  return window.innerWidth <= 480;
}

function isTouchDevice() {
  return 'ontouchstart' in window || navigator.maxTouchPoints > 0;
}

function abbreviateName(name) {
  if (!name) return '';
  const parts = name.trim().split(' ');
  if (parts.length < 2) return name;
  return parts[0][0] + '. ' + parts.slice(1).join(' ');
}
```

**Step 2: Verify no syntax errors**

Open browser console, load any game page, run:
```javascript
console.log('isMobile:', isMobile(), 'isTouch:', isTouchDevice());
```
Expected: No errors, outputs boolean values.

**Step 3: Commit**

```bash
git add docs/assets/viz.js
git commit -m "feat(mobile): add mobile detection and name abbreviation helpers"
```

---

## Task 2: Add Box Score Table Mobile CSS

**Files:**
- Modify: `docs/assets/viz.css` (append to end of file)

**Step 1: Add the media queries**

Append to end of `viz.css`:

```css
/* ═══════════════════════════════════════════════════════════════════════════
   MOBILE RESPONSIVE STYLES
   ═══════════════════════════════════════════════════════════════════════════ */

/* ── Tablet: 481-768px ── */
@media (max-width: 768px) {
  body { padding: 12px; }
  h1 { font-size: 1.1rem; margin-bottom: 16px; }
  section { padding: 14px; margin-bottom: 18px; }

  /* Box score: sticky player column */
  #box-score-container { position: relative; }

  table th:first-child,
  table td:first-child {
    position: sticky;
    left: 0;
    z-index: 2;
    min-width: 100px;
  }

  table th:first-child { background: #22263a; }
  table td:first-child { background: inherit; }

  /* Shadow hint for horizontal scroll */
  table th:first-child::after,
  table td:first-child::after {
    content: '';
    position: absolute;
    right: -8px;
    top: 0;
    bottom: 0;
    width: 8px;
    background: linear-gradient(to right, rgba(0,0,0,0.2), transparent);
    pointer-events: none;
  }

  /* Hide Team column on mobile (redundant with team headers) */
  table th:nth-child(2),
  table td:nth-child(2) { display: none; }
}

/* ── Small Mobile: ≤480px ── */
@media (max-width: 480px) {
  body { padding: 8px; }
  h1 { font-size: 0.95rem; margin-bottom: 12px; }
  h2 { font-size: 0.85rem; }
  section { padding: 10px; margin-bottom: 14px; border-radius: 8px; }

  /* Box score: smaller text */
  table { font-size: 0.72rem; }
  th, td { padding: 4px 6px; }
  table th:first-child,
  table td:first-child { min-width: 80px; }

  /* Score chart: reduce height */
  section:has(#scoreChart) > div { height: 220px !important; }

  /* Gantt tooltip: mobile positioning */
  #gantt-tooltip {
    left: 50% !important;
    transform: translateX(-50%);
    max-width: calc(100vw - 20px);
    min-width: auto;
  }
  #gantt-tooltip .tip-stats {
    flex-wrap: wrap;
    gap: 6px 10px;
  }
}
```

**Step 2: Verify in browser**

1. Open any game page in Chrome
2. Open DevTools (F12) → Toggle device toolbar (Ctrl+Shift+M)
3. Select iPhone SE (375px)
4. Expected: Smaller fonts, sticky player column, Team column hidden

**Step 3: Commit**

```bash
git add docs/assets/viz.css
git commit -m "feat(mobile): add responsive CSS for box score table"
```

---

## Task 3: Update Gantt Dimensions for Mobile

**Files:**
- Modify: `docs/assets/viz.js:166-173`

**Step 1: Replace fixed dimensions with responsive values**

Replace lines 166-173:

```javascript
  const ROW_H    = 18;
  const HEADER_H = 22;
  const PAD_TOP  = 28;
  const PAD_BOT  = 10;
  const PAD_LEFT = 130;
  const PAD_RIGHT = 20;
  const svgW = Math.max(800, (document.getElementById('gantt-container').clientWidth || 900) - 4);
  const chartW = svgW - PAD_LEFT - PAD_RIGHT;
```

With:

```javascript
  // Responsive dimensions
  const smallMobile = isSmallMobile();
  const mobile = isMobile();

  const ROW_H    = smallMobile ? 14 : mobile ? 16 : 18;
  const HEADER_H = smallMobile ? 18 : mobile ? 20 : 22;
  const PAD_TOP  = smallMobile ? 24 : 28;
  const PAD_BOT  = 10;
  const PAD_LEFT = smallMobile ? 70 : mobile ? 100 : 130;
  const PAD_RIGHT = smallMobile ? 10 : 20;

  const containerW = document.getElementById('gantt-container').clientWidth || 900;
  const svgW = Math.max(smallMobile ? 320 : 600, containerW - 4);
  const chartW = svgW - PAD_LEFT - PAD_RIGHT;
```

**Step 2: Verify in browser**

1. Load game page in mobile view (375px)
2. Expected: Gantt chart fits screen, less left padding
3. Resize to desktop (1200px)
4. Expected: Full padding restored

**Step 3: Commit**

```bash
git add docs/assets/viz.js
git commit -m "feat(mobile): responsive Gantt chart dimensions"
```

---

## Task 4: Update Player Name Display for Mobile

**Files:**
- Modify: `docs/assets/viz.js:242-247`

**Step 1: Replace player name rendering**

Replace lines 242-247:

```javascript
      el('text', {
        x: PAD_LEFT - 6, y: y + ROW_H / 2 + 4,
        fill: isHome ? '#e8a0aa' : '#8ab8e0',
        'font-size': '11', 'text-anchor': 'end',
        'font-family': 'Segoe UI, Arial, sans-serif'
      }).textContent = row.player.length > 18 ? row.player.slice(0, 17) + '…' : row.player;
```

With:

```javascript
      // Responsive player name display
      const nameFontSize = smallMobile ? '9' : mobile ? '10' : '11';
      const maxLen = smallMobile ? 10 : mobile ? 14 : 18;
      let displayName = row.player;

      if (smallMobile) {
        displayName = abbreviateName(row.player);
      }
      if (displayName.length > maxLen) {
        displayName = displayName.slice(0, maxLen - 1) + '…';
      }

      el('text', {
        x: PAD_LEFT - 6, y: y + ROW_H / 2 + 4,
        fill: isHome ? '#e8a0aa' : '#8ab8e0',
        'font-size': nameFontSize, 'text-anchor': 'end',
        'font-family': 'Segoe UI, Arial, sans-serif'
      }).textContent = displayName;
```

**Step 2: Verify in browser**

1. Load game page at 375px width
2. Expected: Player names show as "A. Wilson", "B. Stewart", etc.
3. Load at 600px width
4. Expected: Names show as "Alyssa Wilson" (truncated if needed)

**Step 3: Commit**

```bash
git add docs/assets/viz.js
git commit -m "feat(mobile): abbreviate player names on small screens"
```

---

## Task 5: Update Bar Stats Display for Mobile

**Files:**
- Modify: `docs/assets/viz.js:340-345`

**Step 1: Replace bar stats rendering**

Replace lines 340-345:

```javascript
    el('text', {
      x: x1 + 4, y: y + barH / 2 + 4,
      fill: 'rgba(255,255,255,0.92)', 'font-size': '9', 'font-weight': '600',
      'text-anchor': 'start', 'font-family': 'Segoe UI, Arial, sans-serif',
      'pointer-events': 'none', 'clip-path': `url(#${cid})`
    }).textContent = `${s.stint_pts || 0} · ${combo}`;
```

With:

```javascript
    // Hide stats on narrow bars (mobile)
    const minBarWidthForStats = smallMobile ? 35 : 30;
    const statsFontSize = smallMobile ? '8' : '9';

    if (barW >= minBarWidthForStats) {
      el('text', {
        x: x1 + 3, y: y + barH / 2 + (smallMobile ? 3 : 4),
        fill: 'rgba(255,255,255,0.92)', 'font-size': statsFontSize, 'font-weight': '600',
        'text-anchor': 'start', 'font-family': 'Segoe UI, Arial, sans-serif',
        'pointer-events': 'none', 'clip-path': `url(#${cid})`
      }).textContent = `${s.stint_pts || 0} · ${combo}`;
    }
```

**Step 2: Verify in browser**

1. Load game page at 375px
2. Find a short stint bar (< 35px wide)
3. Expected: No stats text visible (prevents overflow)
4. Find a longer stint bar
5. Expected: Stats show with smaller font

**Step 3: Commit**

```bash
git add docs/assets/viz.js
git commit -m "feat(mobile): hide bar stats on narrow stints"
```

---

## Task 6: Add Touch Event Handling

**Files:**
- Modify: `docs/assets/viz.js:319-328`

**Step 1: Replace tooltip event handlers**

Replace lines 319-328:

```javascript
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

With:

```javascript
    // Desktop: mousemove/mouseleave
    if (!isTouchDevice()) {
      rect.addEventListener('mousemove', e => {
        tooltip.innerHTML = tipHTML;
        tooltip.style.display = 'block';
        const tx = (e.clientX + 16 + 340 > window.innerWidth) ? e.clientX - 350 : e.clientX + 16;
        const ty = Math.min(e.clientY + 12, window.innerHeight - 320);
        tooltip.style.left = tx + 'px';
        tooltip.style.top  = ty + 'px';
      });
      rect.addEventListener('mouseleave', () => { tooltip.style.display = 'none'; });
    } else {
      // Mobile: tap to show
      rect.addEventListener('touchstart', e => {
        e.preventDefault();
        e.stopPropagation();

        // Hide any existing tooltip first
        tooltip.style.display = 'none';

        // Show this tooltip
        tooltip.innerHTML = tipHTML;
        tooltip.style.display = 'block';

        // Position: centered horizontally, below the tap point
        const touch = e.touches[0];
        const tooltipRect = tooltip.getBoundingClientRect();
        const viewportW = window.innerWidth;
        const viewportH = window.innerHeight;

        // Center horizontally
        let tx = Math.max(10, Math.min(viewportW - tooltipRect.width - 10,
                 (viewportW - tooltipRect.width) / 2));
        // Position below tap, with fallback to above if too close to bottom
        let ty = touch.clientY + 20;
        if (ty + tooltipRect.height > viewportH - 10) {
          ty = touch.clientY - tooltipRect.height - 20;
        }

        tooltip.style.left = tx + 'px';
        tooltip.style.top = Math.max(10, ty) + 'px';

        // Visual feedback
        rect.style.opacity = '1';
        setTimeout(() => { rect.style.opacity = '0.75'; }, 150);
      }, { passive: false });
    }
```

**Step 2: Add document-level dismiss handler**

Add after line 349 (after `document.getElementById('gantt-container').appendChild(svg);`):

```javascript
  // Mobile: tap outside to dismiss tooltip
  if (isTouchDevice()) {
    document.addEventListener('touchstart', e => {
      const tooltip = document.getElementById('gantt-tooltip');
      if (tooltip.style.display !== 'none' &&
          !tooltip.contains(e.target) &&
          !e.target.closest('#gantt-container rect')) {
        tooltip.style.display = 'none';
      }
    });
  }
```

**Step 3: Verify on mobile or touch emulation**

1. Open Chrome DevTools, toggle device toolbar
2. Tap a stint bar
3. Expected: Tooltip appears centered
4. Tap outside the tooltip
5. Expected: Tooltip dismisses

**Step 4: Commit**

```bash
git add docs/assets/viz.js
git commit -m "feat(mobile): add touch event handling for Gantt tooltips"
```

---

## Task 7: Update Score Flow Chart for Mobile

**Files:**
- Modify: `docs/assets/viz.js:91-136`

**Step 1: Make chart options responsive**

Replace lines 91-136 (the `options` and `plugins` configuration):

```javascript
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
          title: { display: !isSmallMobile(), text: 'Score', color: '#888' },
          ticks: { color: '#888' },
          grid: { color: 'rgba(255,255,255,0.06)' },
        }
      },
      plugins: {
        legend: {
          labels: {
            color: '#ccc',
            font: { size: isSmallMobile() ? 10 : 12 },
            boxWidth: isSmallMobile() ? 12 : 40
          }
        },
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
```

**Step 2: Update quarter lines font size**

In the `quarterLines` plugin (around line 58), update:

```javascript
        ctx.font = `${isSmallMobile() ? 9 : 11}px Segoe UI, Arial, sans-serif`;
```

**Step 3: Verify in browser**

1. Load game page at 375px
2. Expected: Chart height ~220px, no Y-axis "Score" label, smaller legend
3. Load at desktop width
4. Expected: Full height, "Score" label visible

**Step 4: Commit**

```bash
git add docs/assets/viz.js
git commit -m "feat(mobile): responsive score flow chart options"
```

---

## Task 8: Add SVG Width 100% for Mobile

**Files:**
- Modify: `docs/assets/viz.js:186-189`

**Step 1: Make SVG responsive**

Replace lines 186-189:

```javascript
  const svg = document.createElementNS(ns, 'svg');
  svg.setAttribute('width', svgW);
  svg.setAttribute('height', svgH);
  svg.style.display = 'block';
```

With:

```javascript
  const svg = document.createElementNS(ns, 'svg');
  svg.setAttribute('viewBox', `0 0 ${svgW} ${svgH}`);
  svg.setAttribute('preserveAspectRatio', 'xMinYMin meet');
  if (mobile) {
    svg.style.width = '100%';
    svg.style.height = 'auto';
  } else {
    svg.setAttribute('width', svgW);
    svg.setAttribute('height', svgH);
  }
  svg.style.display = 'block';
```

**Step 2: Verify in browser**

1. Load game page at 375px
2. Rotate to landscape
3. Expected: SVG scales smoothly without horizontal scroll
4. Rotate back to portrait
5. Expected: SVG fits within viewport

**Step 3: Commit**

```bash
git add docs/assets/viz.js
git commit -m "feat(mobile): use viewBox for responsive SVG scaling"
```

---

## Task 9: Final Integration Test

**Files:** None (manual testing only)

**Step 1: Test on iPhone SE (375 x 667)**

1. Load index page
2. Navigate to any game
3. Verify:
   - [ ] Page fits without horizontal scroll
   - [ ] Score chart visible and interactive
   - [ ] Gantt chart shows abbreviated names
   - [ ] Tap stint bar → tooltip appears centered
   - [ ] Tap outside → tooltip dismisses
   - [ ] Box score scrolls horizontally, Player column sticky
   - [ ] Team column hidden

**Step 2: Test on iPhone 12 (390 x 844)**

Repeat all checks from Step 1.

**Step 3: Test on iPad (768 x 1024)**

1. Verify tablet-specific styles:
   - [ ] Larger padding than mobile
   - [ ] Player names truncated but not abbreviated
   - [ ] Box score Team column hidden
   - [ ] Touch interactions work

**Step 4: Test on Desktop (1280px+)**

1. Verify desktop experience unchanged:
   - [ ] Full padding on Gantt
   - [ ] Full player names
   - [ ] Mouse hover tooltips work
   - [ ] All table columns visible

**Step 5: Test Orientation Changes**

1. On mobile, rotate device
2. Verify Gantt re-renders correctly
3. No layout breaking

**Step 6: Final Commit**

```bash
git add -A
git commit -m "feat(mobile): complete mobile-friendly visualizations

- Responsive Gantt chart with abbreviated names
- Touch-based tooltip interactions
- Sticky player column in box score
- Responsive score flow chart
- CSS media queries at 480px and 768px breakpoints"
```

---

## Summary

| Task | Description | Files |
|------|-------------|-------|
| 1 | Mobile detection helpers | viz.js |
| 2 | Box score table CSS | viz.css |
| 3 | Gantt responsive dimensions | viz.js |
| 4 | Player name abbreviation | viz.js |
| 5 | Bar stats visibility | viz.js |
| 6 | Touch event handling | viz.js |
| 7 | Score chart responsive | viz.js |
| 8 | SVG viewBox scaling | viz.js |
| 9 | Integration testing | (manual) |

**Estimated changes:** ~100 lines CSS, ~80 lines JS
