// Player page JavaScript

// Render mini Gantt charts for each game, labeling each stint with its stats
(function renderMiniGantts() {
  const STATS = [['pts', 'p'], ['reb', 'r'], ['ast', 'a'], ['stl', 's'], ['blk', 'b']];

  const fmtClock = (elapsed, isEnd) => GamePeriods.clockAt(elapsed, isEnd);

  // Candidate labels, longest first: "6p 2r 1a", then just the first stat
  function labelOptions(stint) {
    const parts = STATS.filter(([k]) => stint[k]).map(([k, abbr]) => `${stint[k]}${abbr}`);
    if (!parts.length) return ['–'];
    return parts.length > 1 ? [parts.join(' '), parts[0]] : parts;
  }

  function tooltip(stint) {
    const dur = stint.end - stint.start;
    const mins = `${Math.floor(dur / 60)}:${String(Math.round(dur % 60)).padStart(2, '0')}`;
    const stats = `${stint.pts || 0} PTS · ${stint.reb || 0} REB · ${stint.ast || 0} AST · ` +
      `${stint.stl || 0} STL · ${stint.blk || 0} BLK · ${stint.to || 0} TO`;
    return `${fmtClock(stint.start)} → ${fmtClock(stint.end, true)} (${mins})\n${stats}`;
  }

  // Use the longest label that fits inside the bar
  function fitLabels() {
    document.querySelectorAll('.mini-stint').forEach(bar => {
      const label = bar.firstChild;
      const options = JSON.parse(bar.dataset.labels);
      label.textContent = '';
      for (const text of options) {
        label.textContent = text;
        if (label.scrollWidth <= bar.clientWidth) return;
      }
      label.textContent = '';
    });
  }

  document.querySelectorAll('.mini-gantt').forEach(container => {
    const stints = JSON.parse(container.dataset.stints || '[]');
    const isHome = container.classList.contains('home');
    const color = TeamColors.forTeam(container.dataset.team, '');
    // Overtime games get a longer track
    const periods = GamePeriods.list(Math.max(2400, ...stints.map(s => s.end)));
    const totalSec = periods[periods.length - 1].end;
    container.querySelectorAll('.q-mark').forEach(m => m.remove());
    periods.slice(1).forEach(p => {
      const mark = document.createElement('span');
      mark.className = 'q-mark';
      mark.style.left = `${(p.start / totalSec) * 100}%`;
      container.appendChild(mark);
    });

    stints.forEach(stint => {
      const bar = document.createElement('div');
      bar.className = `mini-stint ${isHome ? 'home' : 'away'}`;
      bar.style.left = `${(stint.start / totalSec) * 100}%`;
      bar.style.width = `${((stint.end - stint.start) / totalSec) * 100}%`;
      if (color) {
        bar.style.background = color;
        bar.style.color = TeamColors.textOn(color);
      }
      bar.title = tooltip(stint);
      bar.dataset.labels = JSON.stringify(labelOptions(stint));
      const label = document.createElement('span');
      label.className = 'mini-stint-label';
      bar.appendChild(label);
      container.appendChild(bar);
    });
  });

  window.fitStintLabels = fitLabels;
  fitLabels();
  let resizeTimer;
  window.addEventListener('resize', () => {
    clearTimeout(resizeTimer);
    resizeTimer = setTimeout(fitLabels, 150);
  });
})();

// Season tabs: filter the game log and recompute per-game averages
(function initSeasonFilter() {
  const games = (typeof PLAYER_DATA !== 'undefined' && PLAYER_DATA.games) || [];
  const cards = [...document.querySelectorAll('.player-game')];
  const tabs = [...document.querySelectorAll('.season-tabs .tab[data-season]')];

  const toSec = m => {
    const [mm, ss] = String(m || '0:00').split(':').map(Number);
    return (mm || 0) * 60 + (ss || 0);
  };
  const setStat = (key, val) => {
    const el = document.querySelector(`[data-stat="${key}"]`);
    if (el) el.textContent = val;
  };

  function apply(season) {
    const list = season ? games.filter(g => g.date.startsWith(season)) : games;
    const n = list.length || 1;
    const avg = key => (list.reduce((t, g) => t + (g[key] || 0), 0) / n).toFixed(1);
    const minSec = Math.round(list.reduce((t, g) => t + toSec(g.minutes), 0) / n);
    setStat('gp', list.length);
    setStat('min', list.length ? `${Math.floor(minSec / 60)}:${String(minSec % 60).padStart(2, '0')}` : '–');
    setStat('pts', list.length ? avg('pts') : '–');
    setStat('reb', list.length ? avg('reb') : '–');
    setStat('ast', list.length ? avg('ast') : '–');
    setStat('stints', list.length ? (list.reduce((t, g) => t + g.stints.length, 0) / n).toFixed(1) : '–');

    cards.forEach(c => { c.hidden = !!season && c.dataset.season !== season; });
    tabs.forEach(t => {
      const on = t.dataset.season === season;
      t.classList.toggle('active', on);
      t.setAttribute('aria-selected', on);
    });
    window.fitStintLabels();
  }

  tabs.forEach(t => t.addEventListener('click', () => apply(t.dataset.season)));
  apply('');
})();
