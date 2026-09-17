// Player search dropdown, shared by every page.
// Markup: <div class="player-search" data-root="../"><input><div class="player-dropdown"></div></div>
// data-root is the path from the page to the site root.
(function initPlayerSearch() {
  const box = document.querySelector('.player-search');
  if (!box) return;
  const input = box.querySelector('input');
  const dropdown = box.querySelector('.player-dropdown');
  const root = box.dataset.root || '';

  let players = [];
  let highlighted = -1;
  fetch(`${root}players/players.json`)
    .then(r => r.json())
    .then(data => { players = data; })
    .catch(() => { console.warn('Could not load players.json'); });

  function fold(s) {
    return s.toLowerCase().normalize('NFD').replace(/[\u0300-\u036f]/g, '');
  }

  function escapeHtml(s) {
    return String(s).replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  }

  function render() {
    const q = fold(input.value.trim());
    if (!players.length) return;
    // Match on any word start ("wil" finds A'ja Wilson), most games first
    const matches = players
      .filter(p => !q || fold(p.name).split(/[\s'-]+/).some(w => w.startsWith(q)) || fold(p.name).startsWith(q))
      .sort((a, b) => b.games - a.games)
      .slice(0, 12);

    highlighted = -1;
    dropdown.innerHTML = matches.length
      ? matches.map(p =>
          `<a class="player-option" href="${root}players/${p.slug}.html">` +
          `<span>${escapeHtml(p.name)}</span><span class="team">${escapeHtml(p.team)}</span></a>`
        ).join('')
      : '<div class="player-empty">No players found</div>';
    dropdown.classList.add('active');
  }

  function move(delta) {
    const opts = [...dropdown.querySelectorAll('.player-option')];
    if (!opts.length) return;
    highlighted = (highlighted + delta + opts.length) % opts.length;
    opts.forEach((o, i) => o.classList.toggle('hl', i === highlighted));
    opts[highlighted].scrollIntoView({ block: 'nearest' });
  }

  input.addEventListener('focus', render);
  input.addEventListener('input', render);
  input.addEventListener('keydown', e => {
    if (e.key === 'ArrowDown') { e.preventDefault(); move(1); }
    else if (e.key === 'ArrowUp') { e.preventDefault(); move(-1); }
    else if (e.key === 'Enter') {
      const opts = dropdown.querySelectorAll('.player-option');
      const target = opts[Math.max(highlighted, 0)];
      if (target) window.location.href = target.href;
    } else if (e.key === 'Escape') {
      dropdown.classList.remove('active');
      input.blur();
    }
  });
  document.addEventListener('click', e => {
    if (!box.contains(e.target)) dropdown.classList.remove('active');
  });
})();
