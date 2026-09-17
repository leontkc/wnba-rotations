// wnbarotations — shared visualization script
// DATA and NAV are injected by the game HTML shell before this script loads;
// teams.js (TEAM_NAMES, TeamColors) loads first.

// ─── Theme ───────────────────────────────────────────────────────────────────
const CSS = getComputedStyle(document.documentElement);
const cssVar = (name, fallback) => (CSS.getPropertyValue(name) || '').trim() || fallback;

// Chart colors come from the two teams (see teams.js); CSS vars follow them
const { home: HOME_COLOR, away: AWAY_COLOR } = TeamColors.forMatchup(
  DATA.game.home_tricode, DATA.game.away_tricode,
  cssVar('--home', '#e0364f'), cssVar('--away', '#4a90d9'));
document.documentElement.style.setProperty('--home', HOME_COLOR);
document.documentElement.style.setProperty('--away', AWAY_COLOR);
const SURFACE    = cssVar('--surface', '#141821');
const TEXT_2     = cssVar('--text-2', '#b4bacb');
const MUTED      = cssVar('--muted', '#8089a0');
const FAINT      = cssVar('--faint', '#5a6378');
const FONT       = cssVar('--font', 'Inter, system-ui, sans-serif');

// "#e0364f" -> "rgba(224,54,79,a)"
function withAlpha(hex, a) {
  const n = parseInt(hex.replace('#', ''), 16);
  return `rgba(${(n >> 16) & 255},${(n >> 8) & 255},${n & 255},${a})`;
}

// ─── Prev / Next nav ────────────────────────────────────────────────────────
(function renderNav() {
  const adjacent = document.getElementById('nav-adjacent');
  if (!adjacent || typeof NAV === 'undefined' || !NAV) return;
  const link = (id, text) => id
    ? `<a href="${id}.html">${text}</a>`
    : `<a class="disabled" aria-disabled="true">${text}</a>`;
  adjacent.innerHTML = link(NAV.prev, '← <span class="label">Prev game</span>') +
                       link(NAV.next, '<span class="label">Next game</span> →');
})();

// ─── Helpers ─────────────────────────────────────────────────────────────────
function isMobile() {
  return window.innerWidth <= 768;
}

function isSmallMobile() {
  return window.innerWidth <= 480;
}

function isTouchDevice() {
  return 'ontouchstart' in window || navigator.maxTouchPoints > 0;
}

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

// The API sometimes reports "29:60"; show it as "30:00"
function normMinutes(min) {
  if (!min) return min;
  const m = String(min).match(/^(\d+):(\d+)/);
  if (!m) return min;
  let mins = parseInt(m[1], 10), secs = parseInt(m[2], 10);
  if (secs >= 60) { mins += Math.floor(secs / 60); secs %= 60; }
  return `${mins}:${String(secs).padStart(2, '0')}`;
}

// ─── Title + scoreboard ──────────────────────────────────────────────────────
const g = DATA.game;
document.getElementById('game-title').textContent =
  `${teamName(g.away_tricode)} ${g.score_away} at ${teamName(g.home_tricode)} ${g.score_home}, ${g.date}`;

(function renderScoreboard() {
  const el = document.getElementById('scoreboard');
  if (!el) return;
  const homeWon = g.score_home > g.score_away;
  let dateText = g.date;
  if (g.date) {
    const d = new Date(`${g.date}T12:00:00`);
    dateText = d.toLocaleDateString('en-US', { weekday: 'short', month: 'short', day: 'numeric', year: 'numeric' });
  }
  const side = (tc, score, won, cls, label) => `
    <div class="sb-team ${cls} t-${tc}${won ? ' won' : ''}">
      <div class="sb-id">
        <span class="sb-tc"><span class="team-chip" aria-hidden="true" style="background:${cls === 'home' ? HOME_COLOR : AWAY_COLOR}"></span>${tc}</span>
        <span class="sb-name">${teamName(tc)}</span>
        <span class="sb-side">${label}</span>
      </div>
      <span class="sb-score">${score}</span>
    </div>`;
  const margin = Math.abs(g.score_home - g.score_away);
  el.innerHTML =
    side(g.away_tricode, g.score_away, !homeWon, 'away', 'Away') +
    `<div class="sb-mid"><span class="sb-status">Final</span><span class="sb-date">${dateText}</span>` +
    `<span class="sb-margin">${homeWon ? g.home_tricode : g.away_tricode} by ${margin}</span></div>` +
    side(g.home_tricode, g.score_home, homeWon, 'home', 'Home');
})();

// ─── 1. Game Momentum (Score Margin) ─────────────────────────────────────────
(function renderGameMomentum() {
  const flow = DATA.score_flow;
  if (!flow.length) return;

  // Parse clock display (e.g., "5:30") to seconds remaining in quarter
  function clockToSec(clock) {
    const parts = clock.split(':');
    return parseInt(parts[0]) * 60 + parseInt(parts[1]);
  }

  // Auto-detect quarter length from first entry's clock
  const firstClock = clockToSec(flow[0].clock_display);
  const quarterLen = firstClock; // 720 for NBA (12:00), 600 for WNBA (10:00)
  const OT_LEN = 300;             // 5-minute overtimes

  // Calculate margin: positive = home leading, negative = away leading
  const marginData = flow.map(d => {
    const clockSec = clockToSec(d.clock_display);
    const periodLen = d.period <= 4 ? quarterLen : OT_LEN;
    const periodStart = d.period <= 4 ? (d.period - 1) * quarterLen : 4 * quarterLen + (d.period - 5) * OT_LEN;
    const elapsedMin = (periodStart + (periodLen - clockSec)) / 60;
    return {
      x: elapsedMin,
      y: d.score_home - d.score_away,
      scoreHome: d.score_home,
      scoreAway: d.score_away,
      period: d.period,
      clock: d.clock_display
    };
  });

  const lastMin = Math.max(...marginData.map(d => d.x));
  const periods = GamePeriods.list(Math.max(4 * quarterLen, lastMin * 60), quarterLen, OT_LEN);
  const totalGameMin = periods[periods.length - 1].end / 60; // 40 for WNBA, more with overtime

  // Find max margin for symmetric y-axis
  const maxMargin = Math.max(
    Math.abs(Math.min(...marginData.map(d => d.y))),
    Math.abs(Math.max(...marginData.map(d => d.y))),
    10 // minimum range
  );

  const quarterLines = {
    id: 'quarterLines',
    afterDraw(chart) {
      const { ctx, chartArea: { top, bottom }, scales: { x } } = chart;
      periods.slice(1).forEach(p => {
        const xPx = x.getPixelForValue(p.start / 60);
        ctx.save();
        ctx.strokeStyle = 'rgba(255,255,255,0.14)';
        ctx.lineWidth = 1;
        ctx.setLineDash([4, 4]);
        ctx.beginPath();
        ctx.moveTo(xPx, top);
        ctx.lineTo(xPx, bottom);
        ctx.stroke();
        ctx.setLineDash([]);
        ctx.fillStyle = MUTED;
        ctx.font = `600 ${isSmallMobile() ? 9 : 11}px ${FONT}`;
        ctx.fillText(GamePeriods.label(p.period), xPx + 4, top + 14);
        ctx.restore();
      });
    }
  };

  // Plugin to fill above/below zero with different colors
  const splitFill = {
    id: 'splitFill',
    beforeDatasetsDraw(chart) {
      const { ctx, chartArea: { left, right, top, bottom }, scales: { x, y } } = chart;
      const dataset = chart.data.datasets[0];
      const meta = chart.getDatasetMeta(0);
      const points = meta.data;

      if (points.length < 2) return;

      const zeroY = y.getPixelForValue(0);

      ctx.save();

      // Draw home (above zero) fill
      ctx.beginPath();
      ctx.moveTo(points[0].x, zeroY);
      points.forEach((pt, i) => {
        const yVal = marginData[i].y;
        if (yVal >= 0) {
          ctx.lineTo(pt.x, pt.y);
        } else {
          ctx.lineTo(pt.x, zeroY);
        }
      });
      ctx.lineTo(points[points.length - 1].x, zeroY);
      ctx.closePath();
      ctx.fillStyle = withAlpha(HOME_COLOR, 0.28);
      ctx.fill();

      // Draw away (below zero) fill
      ctx.beginPath();
      ctx.moveTo(points[0].x, zeroY);
      points.forEach((pt, i) => {
        const yVal = marginData[i].y;
        if (yVal <= 0) {
          ctx.lineTo(pt.x, pt.y);
        } else {
          ctx.lineTo(pt.x, zeroY);
        }
      });
      ctx.lineTo(points[points.length - 1].x, zeroY);
      ctx.closePath();
      ctx.fillStyle = withAlpha(AWAY_COLOR, 0.28);
      ctx.fill();

      ctx.restore();
    }
  };

  const legend = document.getElementById('flow-legend');
  if (legend) {
    legend.innerHTML = [[g.home_tricode, HOME_COLOR], [g.away_tricode, AWAY_COLOR]]
      .map(([tc, c]) => `<span class="legend-item"><span class="legend-swatch" style="background:${withAlpha(c, 0.55)};box-shadow:inset 0 0 0 1px ${c}"></span>${tc} leads</span>`)
      .join('');
  }

  Chart.defaults.font.family = FONT;
  Chart.defaults.color = MUTED;

  new Chart(document.getElementById('scoreChart'), {
    type: 'line',
    data: {
      datasets: [
        {
          label: 'Margin',
          data: marginData,
          borderColor: TEXT_2,
          backgroundColor: 'transparent',
          tension: 0,
          stepped: 'after',
          pointRadius: 0,
          borderWidth: 2,
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
          max: totalGameMin,
          title: { display: !isSmallMobile(), text: 'Minutes played', color: FAINT },
          ticks: { color: MUTED, stepSize: 5 },
          grid: { color: 'rgba(255,255,255,0.05)' },
          border: { display: false },
        },
        y: {
          min: -Math.ceil(maxMargin / 5) * 5,
          max: Math.ceil(maxMargin / 5) * 5,
          title: { display: false },
          border: { display: false },
          ticks: {
            color: MUTED,
            callback: (val) => val === 0 ? 'TIE' : (val > 0 ? `+${val}` : val)
          },
          grid: {
            color: (ctx) => ctx.tick.value === 0 ? 'rgba(255,255,255,0.35)' : 'rgba(255,255,255,0.05)',
            lineWidth: (ctx) => ctx.tick.value === 0 ? 2 : 1
          },
        }
      },
      plugins: {
        legend: { display: false },
        tooltip: {
          callbacks: {
            title(items) {
              const d = marginData[items[0].dataIndex];
              return `${GamePeriods.label(d.period)} ${d.clock}`;
            },
            label(item) {
              const d = marginData[item.dataIndex];
              const leader = d.y > 0 ? g.home_tricode : d.y < 0 ? g.away_tricode : 'Tied';
              const lead = d.y === 0 ? '' : ` by ${Math.abs(d.y)}`;
              return [
                `${leader}${lead}`,
                `${g.home_tricode} ${d.scoreHome} - ${g.away_tricode} ${d.scoreAway}`
              ];
            }
          },
          backgroundColor: cssVar('--surface-2', '#1b2030'),
          titleColor: '#fff',
          bodyColor: TEXT_2,
          borderColor: 'rgba(255,255,255,0.14)',
          borderWidth: 1,
          padding: 10,
          cornerRadius: 8,
          displayColors: false,
        }
      }
    },
    plugins: [splitFill, quarterLines]
  });
})();

// ─── 2. Player Stint Gantt ────────────────────────────────────────────────────
function renderStints(data) {
  const stints = data.stints;
  if (!stints.length) {
    document.getElementById('gantt-container').textContent = 'No stint data.';
    return;
  }

  const homeTC = data.game.home_tricode;
  const awayTC = data.game.away_tricode;

  // Rows are keyed by team + player id (or name on older data): both teams can have a "Howard"
  const rowKey = s => `${s.team}|${s.person_id || s.player}`;
  const seen = new Map();
  stints.forEach(s => { if (!seen.has(rowKey(s))) seen.set(rowKey(s), s); });

  const playersFor = tc => [...seen.values()].filter(s => s.team === tc)
    .map(s => ({ type: 'player', key: rowKey(s), player: s.player, team: tc }));

  const rows = [
    { type: 'header', team: homeTC },
    ...playersFor(homeTC),
    { type: 'header', team: awayTC },
    ...playersFor(awayTC),
  ];

  const playerRowIndex = new Map();
  rows.forEach((r, i) => { if (r.type === 'player') playerRowIndex.set(r.key, i); });

  // Responsive dimensions
  const smallMobile = isSmallMobile();
  const mobile = isMobile();

  const ROW_H    = smallMobile ? 14 : mobile ? 16 : 18;
  const HEADER_H = smallMobile ? 18 : mobile ? 20 : 22;
  const PAD_TOP  = smallMobile ? 24 : 28;
  const PAD_BOT  = 10;
  const PAD_LEFT = smallMobile ? 90 : mobile ? 120 : 155;
  const PAD_RIGHT = smallMobile ? 115 : mobile ? 160 : 210;

  // Build player totals and display names from box_score or stints
  const playerTotals = new Map();
  const playerDisplayNames = new Map(); // Maps row key (team|stint name) -> full name
  if (data.box_score && data.box_score.length) {
    data.box_score.forEach(b => {
      const fullName = `${b.first} ${b.last}`;
      const stats = {
        min: normMinutes(b.minutes) || '0:00',
        pts: b.pts ?? 0,
        reb: b.reb ?? 0,
        ast: b.ast ?? 0,
        stl: b.stl ?? 0,
        blk: b.blk ?? 0,
      };
      // Key by full name, plus team|last name (stints often use last name only)
      playerTotals.set(fullName, stats);
      playerTotals.set(`${b.team}|${b.last}`, stats);
      playerDisplayNames.set(`${b.team}|${b.last}`, fullName);
      if (b.person_id) {
        playerTotals.set(`${b.team}|${b.person_id}`, stats);
        playerDisplayNames.set(`${b.team}|${b.person_id}`, fullName);
      }
    });
  } else {
    // Fallback: sum from stints
    stints.forEach(s => {
      const t = playerTotals.get(rowKey(s)) || { min: 0, pts: 0, reb: 0, ast: 0, stl: 0, blk: 0 };
      t.min += s.duration_sec || 0;
      t.pts += s.stint_pts || 0;
      t.reb += s.stint_reb || 0;
      t.ast += s.stint_ast || 0;
      t.stl += s.stint_stl || 0;
      t.blk += s.stint_blk || 0;
      playerTotals.set(rowKey(s), t);
    });
    // Convert seconds to MM:SS for fallback
    playerTotals.forEach((t, name) => {
      if (typeof t.min === 'number') {
        const m = Math.floor(t.min / 60);
        const s = Math.round(t.min % 60);
        t.min = `${m}:${String(s).padStart(2, '0')}`;
      }
    });
  }
  // Resolved full names from the pipeline take precedence over last-name keys
  stints.forEach(s => { if (s.player_full) playerDisplayNames.set(rowKey(s), s.player_full); });

  const containerW = document.getElementById('gantt-container').clientWidth || 900;
  const svgW = Math.max(smallMobile ? 320 : 600, containerW - 4);
  const chartW = svgW - PAD_LEFT - PAD_RIGHT;

  let totalContentH = 0;
  const rowOffsets = rows.map(r => {
    const y = totalContentH;
    totalContentH += r.type === 'header' ? HEADER_H : ROW_H;
    return y;
  });
  const svgH = PAD_TOP + totalContentH + PAD_BOT;

  const periods = GamePeriods.list(Math.max(2400, ...stints.map(s => s.end_elapsed)));
  const gameEnd = periods[periods.length - 1].end;
  function xOf(elSec) { return PAD_LEFT + (elSec / gameEnd) * chartW; }

  const ns = 'http://www.w3.org/2000/svg';
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

  function el(tag, attrs = {}, parent = svg) {
    const e = document.createElementNS(ns, tag);
    for (const [k, v] of Object.entries(attrs)) e.setAttribute(k, v);
    parent.appendChild(e);
    return e;
  }

  el('rect', { x: 0, y: 0, width: svgW, height: svgH, fill: SURFACE });

  const defs = el('defs', {});

  const quarterShades = ['rgba(255,255,255,0.02)', 'rgba(255,255,255,0.05)',
                         'rgba(255,255,255,0.02)', 'rgba(255,255,255,0.05)'];
  periods.forEach((p, q) => {
    const x1 = xOf(p.start);
    const x2 = xOf(p.end);
    el('rect', { x: x1, y: PAD_TOP, width: x2 - x1, height: totalContentH, fill: quarterShades[q % quarterShades.length] });
    el('text', {
      x: (x1 + x2) / 2, y: PAD_TOP - 8,
      fill: MUTED, 'font-size': '11', 'font-weight': '700',
      'text-anchor': 'middle', 'font-family': FONT
    }).textContent = GamePeriods.label(p.period);
  });

  // Totals column headers - MIN left-aligned, stats right-aligned
  const minHeaderX = svgW - PAD_RIGHT + (smallMobile ? 6 : 8);
  el('text', {
    x: minHeaderX, y: PAD_TOP - 8,
    fill: FAINT, 'font-size': smallMobile ? '7' : '9', 'font-weight': '600',
    'text-anchor': 'start', 'font-family': FONT,
  }).textContent = 'MIN';

  const statsHeaderX = svgW - (smallMobile ? 4 : 8);
  el('text', {
    x: statsHeaderX, y: PAD_TOP - 8,
    fill: FAINT, 'font-size': smallMobile ? '7' : '9', 'font-weight': '600',
    'text-anchor': 'end', 'font-family': FONT,
    'letter-spacing': '0.04em'
  }).textContent = smallMobile ? 'PTS REB AST STK' : 'PTS   REB   AST   STL   BLK';

  [0, ...periods.map(p => p.end)].forEach(sec => {
    const x = xOf(sec);
    el('line', {
      x1: x, y1: PAD_TOP, x2: x, y2: PAD_TOP + totalContentH,
      stroke: 'rgba(255,255,255,0.12)', 'stroke-width': 1,
    });
  });

  rows.forEach((row, i) => {
    const y = PAD_TOP + rowOffsets[i];
    const isHome = row.team === homeTC;
    const color = isHome ? HOME_COLOR : AWAY_COLOR;

    if (row.type === 'header') {
      el('rect', { x: 0, y, width: svgW, height: HEADER_H,
        fill: withAlpha(color, 0.16) });
      el('rect', { x: 0, y, width: 4, height: HEADER_H, fill: color });
      el('text', {
        x: 12, y: y + HEADER_H / 2 + 5,
        fill: color, 'font-size': '11', 'font-weight': '800',
        'font-family': FONT, 'letter-spacing': '0.06em'
      }).textContent = row.team;
    } else {
      el('rect', {
        x: 0, y, width: svgW, height: ROW_H - 1,
        fill: i % 2 ? 'rgba(255,255,255,0.015)' : 'transparent'
      });
      // Responsive player name display
      const nameFontSize = smallMobile ? '9' : mobile ? '10' : '11';
      const maxLen = smallMobile ? 12 : mobile ? 16 : 22;
      // Use mapped full name if available, otherwise fall back to stint name
      const fullName = playerDisplayNames.get(row.key) || row.player;
      let displayName = fullName;

      if (displayName.length > maxLen) {
        displayName = displayName.slice(0, maxLen - 1) + '…';
      }

      // Create clickable player name link
      const nameLink = document.createElementNS(ns, 'a');
      nameLink.setAttributeNS('http://www.w3.org/1999/xlink', 'xlink:href', playerPageUrl(fullName));
      nameLink.setAttribute('style', 'cursor: pointer;');

      const nameText = document.createElementNS(ns, 'text');
      nameText.setAttribute('x', PAD_LEFT - 6);
      nameText.setAttribute('y', y + ROW_H / 2 + 4);
      nameText.setAttribute('fill', TEXT_2);
      nameText.setAttribute('font-size', nameFontSize);
      nameText.setAttribute('text-anchor', 'end');
      nameText.setAttribute('font-family', FONT);
      nameText.textContent = displayName;

      nameLink.appendChild(nameText);
      svg.appendChild(nameLink);

      // Add player totals on the right side
      const totals = playerTotals.get(fullName) || playerTotals.get(row.key);
      if (totals) {
        const totalsFontSize = smallMobile ? '8' : mobile ? '9' : '10';
        const totalsY = y + ROW_H / 2 + (smallMobile ? 3 : 4);
        const valColor = TEXT_2;
        const lblColor = FAINT;

        // Minutes - left aligned after Gantt chart
        const minX = svgW - PAD_RIGHT + (smallMobile ? 6 : 8);
        el('text', {
          x: minX, y: totalsY,
          fill: valColor, 'font-size': totalsFontSize, 'font-weight': '500',
          'text-anchor': 'start', 'font-family': FONT
        }).textContent = totals.min;

        // Stats - right aligned at edge
        const statsX = svgW - (smallMobile ? 4 : 8);
        const statsText = document.createElementNS(ns, 'text');
        statsText.setAttribute('x', statsX);
        statsText.setAttribute('y', totalsY);
        statsText.setAttribute('text-anchor', 'end');
        statsText.setAttribute('font-family', FONT);
        statsText.setAttribute('font-size', totalsFontSize);

        const addSpan = (text, fill, weight = '400') => {
          const tspan = document.createElementNS(ns, 'tspan');
          tspan.setAttribute('fill', fill);
          tspan.setAttribute('font-weight', weight);
          tspan.textContent = text;
          statsText.appendChild(tspan);
        };

        const stocks = (totals.stl || 0) + (totals.blk || 0);

        if (smallMobile) {
          addSpan(String(totals.pts), valColor, '600');
          addSpan('p ', lblColor);
          addSpan(String(totals.reb), valColor);
          addSpan('r ', lblColor);
          addSpan(String(totals.ast), valColor);
          addSpan('a ', lblColor);
          addSpan(String(stocks), valColor);
          addSpan('s', lblColor);
        } else {
          addSpan(String(totals.pts), valColor, '600');
          addSpan(' pts  ', lblColor);
          addSpan(String(totals.reb), valColor);
          addSpan(' reb  ', lblColor);
          addSpan(String(totals.ast), valColor);
          addSpan(' ast  ', lblColor);
          addSpan(String(totals.stl || 0), valColor);
          addSpan(' stl  ', lblColor);
          addSpan(String(totals.blk || 0), valColor);
          addSpan(' blk', lblColor);
        }

        svg.appendChild(statsText);
      }
    }
  });

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

    let html = `<div class="tip-header">${s.player_full || s.player}<span class="tip-team" style="color:${s.team === homeTC ? HOME_COLOR : AWAY_COLOR}">${s.team}</span>`
      + `<span class="tip-time">${GamePeriods.label(s.period)} ${fmtClock(s.clock_in)} → ${fmtClock(s.clock_out)} · ${dur} on court</span></div>`;

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
    const i = playerRowIndex.get(rowKey(s));
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
      fill: color, opacity: '0.85', rx: '3',
      style: 'cursor:pointer'
    });

    const tipHTML = buildTooltipHTML(s);

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
        setTimeout(() => { rect.style.opacity = '0.85'; }, 150);
      }, { passive: false });
    }

    const combo = (s.stint_reb || 0) + (s.stint_ast || 0);
    const cid = `cs${clipIdx++}`;
    const cp = document.createElementNS(ns, 'clipPath');
    cp.setAttribute('id', cid);
    const cr = document.createElementNS(ns, 'rect');
    cr.setAttribute('x', x1 + 2); cr.setAttribute('y', y);
    cr.setAttribute('width', Math.max(0, barW - 4)); cr.setAttribute('height', barH);
    cp.appendChild(cr);
    defs.appendChild(cp);

    // Hide stats on narrow bars (mobile)
    const minBarWidthForStats = smallMobile ? 35 : 30;
    const statsFontSize = smallMobile ? '8' : '9';

    if (barW >= minBarWidthForStats) {
      el('text', {
        x: x1 + 3, y: y + barH / 2 + (smallMobile ? 3 : 4),
        fill: TeamColors.textOn(color), 'font-size': statsFontSize, 'font-weight': '600',
        'text-anchor': 'start', 'font-family': FONT,
        'pointer-events': 'none', 'clip-path': `url(#${cid})`
      }).textContent = `${s.stint_pts || 0} · ${combo}`;
    }
  });

  document.getElementById('gantt-container').appendChild(svg);

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
}

renderStints(DATA);

// Re-render gantt on resize (debounced)
let _ganttResizeTimer;
window.addEventListener('resize', () => {
  clearTimeout(_ganttResizeTimer);
  _ganttResizeTimer = setTimeout(() => {
    const container = document.getElementById('gantt-container');
    container.innerHTML = '';
    renderStints(DATA);
  }, 150);
});

// ─── 3. Box Score ─────────────────────────────────────────────────────────────
function renderBoxScore(data) {
  const rows = data.box_score;
  if (!rows.length) {
    document.getElementById('box-score-container').textContent = 'No box score data.';
    return;
  }

  // Players with 0 minutes show dashes for all stat columns
  function dnp(r) { return !r.minutes; }

  const cols = [
    { key: 'first',      label: 'Player',
      fmt: (r) => `<a href="${playerPageUrl(r.first + ' ' + r.last)}" class="player-link">${r.first} ${r.last}</a>`,
      sort: (a, b) => `${a.last}${a.first}`.localeCompare(`${b.last}${b.first}`),
      isHtml: true },
    { key: 'team',       label: 'Team',   fmt: (r) => r.team,       sort: (a, b) => a.team.localeCompare(b.team) },
    { key: 'minutes',    label: 'Min',    fmt: (r) => normMinutes(r.minutes) || 'DNP', sort: (a, b) => minutesToNum(a.minutes) - minutesToNum(b.minutes) },
    { key: 'pts',        label: 'Pts',    fmt: (r) => dnp(r) ? '-' : r.pts ?? '-', sort: (a, b) => (a.pts ?? 0) - (b.pts ?? 0) },
    { key: 'fgm',        label: 'FGM',   fmt: (r) => dnp(r) ? '-' : r.fgm ?? '-', sort: (a, b) => (a.fgm ?? 0) - (b.fgm ?? 0) },
    { key: 'fga',        label: 'FGA',   fmt: (r) => dnp(r) ? '-' : r.fga ?? '-', sort: (a, b) => (a.fga ?? 0) - (b.fga ?? 0) },
    { key: 'reb',        label: 'Reb',   fmt: (r) => dnp(r) ? '-' : r.reb ?? '-', sort: (a, b) => (a.reb ?? 0) - (b.reb ?? 0) },
    { key: 'ast',        label: 'Ast',   fmt: (r) => dnp(r) ? '-' : r.ast ?? '-', sort: (a, b) => (a.ast ?? 0) - (b.ast ?? 0) },
    { key: 'stl',        label: 'Stl',   fmt: (r) => dnp(r) ? '-' : r.stl ?? '-', sort: (a, b) => (a.stl ?? 0) - (b.stl ?? 0) },
    { key: 'blk',        label: 'Blk',   fmt: (r) => dnp(r) ? '-' : r.blk ?? '-', sort: (a, b) => (a.blk ?? 0) - (b.blk ?? 0) },
    { key: 'to',         label: 'TO',    fmt: (r) => dnp(r) ? '-' : r.to  ?? '-', sort: (a, b) => (a.to  ?? 0) - (b.to  ?? 0) },
    { key: 'pf',         label: 'PF',    fmt: (r) => dnp(r) ? '-' : r.pf  ?? '-', sort: (a, b) => (a.pf  ?? 0) - (b.pf  ?? 0) },
    { key: 'plus_minus', label: '+/-',   fmt: (r) => dnp(r) ? '-' : r.plus_minus != null ? (r.plus_minus > 0 ? '+' : '') + r.plus_minus : '-',
                                          sort: (a, b) => (a.plus_minus ?? 0) - (b.plus_minus ?? 0) },
  ];

  function minutesToNum(min) {
    if (!min) return 0;
    const parts = String(normMinutes(min)).split(':');
    return parseInt(parts[0] || 0) * 60 + parseInt(parts[1] || 0);
  }

  let sortKey = 'pts';
  let sortDir = -1;

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

    [[homeTC, homeRows, 'home'], [data.game.away_tricode, awayRows, 'away']]
      .forEach(([tc, teamRows, side]) => {
        const htr = document.createElement('tr');
        htr.className = `team-row ${side}`;
        const htd = document.createElement('td');
        htd.colSpan = cols.length;
        htd.textContent = teamName(tc).toUpperCase();
        htr.appendChild(htd);
        tbody.appendChild(htr);

        teamRows.forEach(row => {
          const tr = document.createElement('tr');
          if (dnp(row)) tr.className = 'dnp';
          cols.forEach(col => {
            const td = document.createElement('td');
            td.className = `col-${col.key}`;
            if (col.isHtml) {
              td.innerHTML = col.fmt(row);
            } else {
              td.textContent = col.fmt(row);
            }
            if (col.key === 'plus_minus' && !dnp(row) && row.plus_minus) {
              td.classList.add(row.plus_minus > 0 ? 'pm-pos' : 'pm-neg');
            }
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
