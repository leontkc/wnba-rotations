// Player page JavaScript

// Render mini Gantt charts for each game, labeling each stint with its stats
(function renderMiniGantts() {
  const totalSec = 2400; // 40 minutes
  const STATS = [['pts', 'p'], ['reb', 'r'], ['ast', 'a'], ['stl', 's'], ['blk', 'b']];

  // Elapsed seconds -> "Q2 4:31"; an end time on a quarter break is "Q2 0:00"
  function fmtClock(elapsed, isEnd = false) {
    const q = Math.max(1, Math.min(4, isEnd ? Math.ceil(elapsed / 600) : Math.floor(elapsed / 600) + 1));
    const left = Math.max(0, q * 600 - elapsed);
    return `Q${q} ${Math.floor(left / 60)}:${String(Math.round(left % 60)).padStart(2, '0')}`;
  }

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
    const isHome = container.dataset.ishome === 'true';

    stints.forEach(stint => {
      const bar = document.createElement('div');
      bar.className = `mini-stint ${isHome ? 'home' : 'away'}`;
      bar.style.left = `${(stint.start / totalSec) * 100}%`;
      bar.style.width = `${((stint.end - stint.start) / totalSec) * 100}%`;
      bar.title = tooltip(stint);
      bar.dataset.labels = JSON.stringify(labelOptions(stint));
      const label = document.createElement('span');
      label.className = 'mini-stint-label';
      bar.appendChild(label);
      container.appendChild(bar);
    });
  });

  fitLabels();
  let resizeTimer;
  window.addEventListener('resize', () => {
    clearTimeout(resizeTimer);
    resizeTimer = setTimeout(fitLabels, 150);
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
  fetch('players.json')
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
        window.location.href = `${opt.dataset.slug}.html`;
      });
    });
  }
})();
