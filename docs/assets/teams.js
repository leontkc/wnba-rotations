// Team names and chart colors, shared by game and player pages.
// Colors are official (TruColor): [main, second]. Indiana and Las Vegas list
// a visible official color first because navy/black vanish on the dark theme
// (keep in sync with the .t-XXX rules in base.css).

const TEAM_NAMES = {
  ATL: 'Atlanta Dream', CHI: 'Chicago Sky', CON: 'Connecticut Sun', DAL: 'Dallas Wings',
  GSV: 'Golden State Valkyries', IND: 'Indiana Fever', LAS: 'Los Angeles Sparks',
  LVA: 'Las Vegas Aces', MIN: 'Minnesota Lynx', NYL: 'New York Liberty', PDX: 'Portland Fire',
  PHO: 'Phoenix Mercury', PHX: 'Phoenix Mercury', SEA: 'Seattle Storm', TOR: 'Toronto Tempo',
  WAS: 'Washington Mystics',
};
const teamName = tc => TEAM_NAMES[tc] || tc;

const TEAM_COLORS = {
  ATL: ['#C8102E', '#418FDE'],
  CHI: ['#418FDE', '#FFCD00'],
  CON: ['#FC4C02', '#0C2340'],
  DAL: ['#C4D600', '#00A9E0'],
  GSV: ['#AD96DC', '#010101'],
  IND: ['#C8102E', '#FFCD00'],
  LAS: ['#702F8A', '#FFC72C'],
  LVA: ['#A7A8A9', '#010101'],
  MIN: ['#236192', '#78BE21'],
  NYL: ['#6ECEB2', '#C07D59'],
  PDX: ['#C8102E', '#E93CAC'],
  PHO: ['#582C83', '#FC4C02'],
  PHX: ['#582C83', '#FC4C02'],
  SEA: ['#2C5234', '#FBE122'],
  TOR: ['#612C51', '#B8CCEA'],
  WAS: ['#C8102E', '#8D9093'],
};

const TeamColors = (function () {
  const SURFACE = [20, 24, 33];          // --surface, the chart background
  const MIN_CONTRAST = 3;                // WCAG non-text contrast
  const MIN_DISTANCE = 25;               // CIELAB ΔE below which two colors read as the same

  const rgb = hex => {
    const n = parseInt(hex.replace('#', ''), 16);
    return [(n >> 16) & 255, (n >> 8) & 255, n & 255];
  };
  const toHex = c => '#' + c.map(v => Math.round(v).toString(16).padStart(2, '0')).join('');
  const lin = v => { v /= 255; return v <= 0.04045 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4; };
  const luminance = c => 0.2126 * lin(c[0]) + 0.7152 * lin(c[1]) + 0.0722 * lin(c[2]);
  const contrast = (a, b) => {
    const [x, y] = [luminance(a), luminance(b)].sort((p, q) => q - p);
    return (x + 0.05) / (y + 0.05);
  };
  const lab = c => {
    const [r, g, b] = c.map(lin);
    const f = t => (t > 0.008856 ? Math.cbrt(t) : 7.787 * t + 16 / 116);
    const x = f((r * 0.4124 + g * 0.3576 + b * 0.1805) / 0.95047);
    const y = f(r * 0.2126 + g * 0.7152 + b * 0.0722);
    const z = f((r * 0.0193 + g * 0.1192 + b * 0.9505) / 1.08883);
    return [116 * y - 16, 500 * (x - y), 200 * (y - z)];
  };
  const distance = (a, b) => Math.hypot(...lab(a).map((v, i) => v - lab(b)[i]));

  // Mix toward white until the color stands out from the chart background
  function readable(hex) {
    let c = rgb(hex);
    for (let i = 0; i < 20 && contrast(c, SURFACE) < MIN_CONTRAST; i++) {
      c = c.map(v => v + (255 - v) * 0.12);
    }
    return toHex(c);
  }

  // Text color (dark or white) that reads on top of a filled bar
  function textOn(hex) {
    return luminance(rgb(hex)) > 0.35 ? 'rgba(10,12,18,0.9)' : 'rgba(255,255,255,0.95)';
  }

  function forTeam(tc, fallback = '#8089a0') {
    const pair = TEAM_COLORS[tc];
    return pair ? readable(pair[0]) : fallback;
  }

  // Home keeps its main color; the away team switches to its second color
  // (then to the default away blue) if the two would look alike.
  function forMatchup(home, away, fallbackHome = '#e0364f', fallbackAway = '#4a90d9') {
    const h = forTeam(home, fallbackHome);
    const options = [
      ...(TEAM_COLORS[away] || []).map(readable),
      fallbackAway,
      fallbackHome,
    ];
    const a = options.find(c => distance(rgb(c), rgb(h)) >= MIN_DISTANCE) || fallbackAway;
    return { home: h, away: a };
  }

  return { forTeam, forMatchup, textOn };
})();
