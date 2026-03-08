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
