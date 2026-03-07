# Mobile-Friendly Visualizations Design

**Date:** 2026-03-07
**Status:** Approved

## Overview

Make the WNBA Rotations visualizations mobile-friendly across all mobile screen sizes (320-768px) using CSS media queries and touch event handling.

## Requirements

- **Screen targets:** All mobile sizes (320-768px) with responsive breakpoints
- **Gantt player names:** Reduce left padding & abbreviate names on mobile
- **Touch interactions:** Tap to show tooltip, tap outside to dismiss
- **Box score table:** Horizontal scroll with sticky player column

## Architecture

### Files Modified
- `docs/assets/viz.css` - Add ~60 lines of media queries
- `docs/assets/viz.js` - Add ~40 lines for touch handling + mobile detection

### Breakpoints
```
Mobile small:  max-width: 480px
Mobile large:  481px - 768px
Tablet+:       769px+ (unchanged)
```

## Component Designs

### 1. Gantt Chart

| Property | Desktop (769px+) | Tablet (481-768px) | Mobile (≤480px) |
|----------|------------------|-------------------|-----------------|
| Left padding | 130px | 100px | 70px |
| Player name length | 18 chars | 14 chars | Abbreviated (e.g., "A. Wilson") |
| Row height | 18px | 16px | 14px |
| Header height | 22px | 20px | 18px |
| Font size (names) | 11px | 10px | 9px |
| Font size (stats on bars) | 9px | 8px | Hide on narrow bars |

**Player name abbreviation:**
```javascript
function abbreviateName(name) {
  const parts = name.split(' ');
  if (parts.length < 2) return name;
  return parts[0][0] + '. ' + parts.slice(1).join(' ');
}
```

**Bar stat visibility:** Hide "pts · reb+ast" text when bar width < 30px.

**SVG scaling:** Use dynamic `viewBox` so SVG scales naturally; width becomes `100%` on mobile.

### 2. Touch Interactions

**Detection:**
```javascript
'ontouchstart' in window || navigator.maxTouchPoints > 0
```

**Event handling:**
- Desktop: Keep existing `mousemove` / `mouseleave` behavior
- Mobile: Use `touchstart` on stint bars, `touchstart` on document to dismiss

```javascript
// On stint bar
rect.addEventListener('touchstart', (e) => {
  e.preventDefault();
  e.stopPropagation();
  showTooltip(e.touches[0], stintData);
});

// On document (dismiss)
document.addEventListener('touchstart', (e) => {
  if (!tooltip.contains(e.target) && !e.target.closest('rect')) {
    hideTooltip();
  }
});
```

**Tooltip positioning on mobile:**
- Center horizontally on screen
- Position below the tapped bar with 12px gap
- Ensure tooltip doesn't overflow viewport edges

**Visual feedback:** Subtle scale animation (transform: scale(1.05)) on tap.

### 3. Box Score Table

**Sticky column:**
```css
@media (max-width: 768px) {
  #box-score-container {
    position: relative;
  }

  table th:first-child,
  table td:first-child {
    position: sticky;
    left: 0;
    background: #22263a;
    z-index: 1;
  }

  table th:first-child::after,
  table td:first-child::after {
    content: '';
    position: absolute;
    right: -8px;
    top: 0;
    bottom: 0;
    width: 8px;
    background: linear-gradient(to right, rgba(0,0,0,0.15), transparent);
  }
}
```

**Adjustments:**

| Property | Desktop | Mobile (≤480px) |
|----------|---------|-----------------|
| Font size | 0.82rem | 0.72rem |
| Cell padding | 6px 10px | 4px 6px |
| Team column | visible | hidden |

### 4. Score Flow Chart

| Property | Desktop | Mobile (≤480px) |
|----------|---------|-----------------|
| Chart height | 300px | 220px |
| Y-axis title | visible | hidden |
| Legend font size | 12px | 10px |
| Legend box width | 40px | 12px |
| Quarter label font | 11px | 9px |

## Testing

### Manual Testing Checklist

1. **Device/viewport testing:**
   - Chrome DevTools (iPhone SE, iPhone 12, Pixel 5, iPad)
   - Landscape and portrait orientations

2. **Interaction testing:**
   - Tap stint bars → tooltip appears
   - Tap outside → tooltip dismisses
   - Scroll table horizontally → player column stays sticky

3. **Edge cases:**
   - Very long player names
   - Games with many players (12+ per team)
   - Overtime games
   - Narrow stint bars (< 30px)

4. **Performance:**
   - Smooth scrolling
   - No jank on orientation change
   - Instant tooltip on tap
