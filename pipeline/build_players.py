"""
build_players.py — Generate player pages from game data.

Scans all game HTML files, extracts player stint data, generates:
- docs/players/<slug>.html for each player
- docs/players/players.json manifest for search
"""

import json
import logging
import re
import unicodedata
from collections import defaultdict
from pathlib import Path

from pipeline.config import DOCS_DIR, GAMES_DIR, TEMPLATES_DIR

log = logging.getLogger(__name__)

PLAYERS_DIR = DOCS_DIR / "players"


def slugify(name: str) -> str:
    """Convert player name to URL slug."""
    name = unicodedata.normalize('NFD', name)
    name = ''.join(c for c in name if not unicodedata.combining(c))
    name = re.sub(r'[^a-z0-9]+', '-', name.lower())
    return name.strip('-')


def extract_player_data_from_games() -> dict:
    """
    Scan all game HTML files and extract player data.
    Returns: {player_name: {name, team, games: [...]}}
    """
    players = defaultdict(lambda: {'name': '', 'team': '', 'games': []})

    for game_file in GAMES_DIR.glob('*.html'):
        try:
            content = game_file.read_text(encoding='utf-8')

            # Extract DATA JSON from script tag
            match = re.search(r'const DATA = ({.*?});\s*\nconst NAV', content, re.DOTALL)
            if not match:
                continue

            data = json.loads(match.group(1))
            game_info = data.get('game', {})
            stints = data.get('stints', [])
            box_score = data.get('box_score', [])

            game_id = game_info.get('id', game_file.stem)
            date = game_info.get('date', '')
            home_tc = game_info.get('home_tricode', '')
            away_tc = game_info.get('away_tricode', '')
            score_home = game_info.get('score_home', 0)
            score_away = game_info.get('score_away', 0)

            # Build box score lookup for full stats
            box_lookup = {}
            for row in box_score:
                full_name = f"{row.get('first', '')} {row.get('last', '')}".strip()
                if full_name:
                    box_lookup[full_name] = row

            # Group stints by player
            player_stints = defaultdict(list)
            player_teams = {}
            for stint in stints:
                player = stint.get('player', '')
                team = stint.get('team', '')
                if not player or not team:
                    continue
                player_stints[player].append({
                    'start': stint.get('start_elapsed', 0),
                    'end': stint.get('end_elapsed', 0),
                    'pts': stint.get('stint_pts', 0),
                    'reb': stint.get('stint_reb', 0),
                    'ast': stint.get('stint_ast', 0),
                })
                player_teams[player] = team

            # Add game entry for each player
            for player, stint_list in player_stints.items():
                team = player_teams.get(player, '')
                if not team:
                    continue

                # Set player info
                if not players[player]['name']:
                    players[player]['name'] = player
                    players[player]['team'] = team

                is_home = team == home_tc
                opponent = away_tc if is_home else home_tc
                own_score = score_home if is_home else score_away
                opp_score = score_away if is_home else score_home
                won = own_score > opp_score

                # Aggregate stats from stints
                total_pts = sum(s['pts'] for s in stint_list)
                total_reb = sum(s['reb'] for s in stint_list)
                total_ast = sum(s['ast'] for s in stint_list)

                # Calculate total minutes
                total_sec = sum(s['end'] - s['start'] for s in stint_list)
                minutes = f"{int(total_sec // 60)}:{int(total_sec % 60):02d}"

                # Get full box score stats if available
                box_row = box_lookup.get(player, {})

                players[player]['games'].append({
                    'game_id': game_id,
                    'date': date,
                    'opponent': opponent,
                    'is_home': is_home,
                    'own_score': own_score,
                    'opp_score': opp_score,
                    'won': won,
                    'stints': [{'start': s['start'], 'end': s['end']} for s in stint_list],
                    'minutes': minutes,
                    'pts': box_row.get('pts', total_pts),
                    'reb': box_row.get('reb', total_reb),
                    'ast': box_row.get('ast', total_ast),
                })
        except Exception as e:
            log.warning(f"Error processing {game_file}: {e}")
            continue

    # Sort games by date (newest first)
    for player_data in players.values():
        player_data['games'].sort(key=lambda g: g['date'], reverse=True)

    return dict(players)


def generate_player_html(player_data: dict) -> str:
    """Generate HTML for a single player page."""
    template = (TEMPLATES_DIR / 'player.html').read_text(encoding='utf-8')

    name = player_data['name']
    team = player_data['team']
    games = player_data['games']

    # Build games HTML
    games_html_parts = []
    for g in games:
        result_class = 'win' if g['won'] else 'loss'
        result_text = 'W' if g['won'] else 'L'
        location = 'vs' if g['is_home'] else '@'

        stints_json = json.dumps(g['stints'])

        games_html_parts.append(f'''
<div class="player-game" data-href="../games/{g['game_id']}.html">
  <div class="player-game-header">
    <span>{g['date']} {location} {g['opponent']}</span>
    <span class="game-result {result_class}">{result_text} {g['own_score']}-{g['opp_score']}</span>
  </div>
  <div class="mini-gantt" data-stints='{stints_json}' data-ishome='{str(g["is_home"]).lower()}'></div>
  <div class="player-game-stats">
    <span><span class="stat-val">{g['pts']}</span> PTS</span>
    <span><span class="stat-val">{g['reb']}</span> REB</span>
    <span><span class="stat-val">{g['ast']}</span> AST</span>
    <span class="player-minutes">{g['minutes']}</span>
  </div>
</div>''')

    games_html = '\n'.join(games_html_parts)

    # Replace placeholders
    html = template.replace('__PLAYER_NAME__', name)
    html = html.replace('__PLAYER_TEAM__', team)
    html = html.replace('__GAME_COUNT__', str(len(games)))
    html = html.replace('__GAMES_HTML__', games_html)
    html = html.replace('__PLAYER_DATA__', json.dumps(player_data))

    return html


def generate_players_manifest(players: dict) -> list:
    """Generate players.json manifest for search."""
    manifest = []
    for name, data in sorted(players.items()):
        if data['games']:  # Only include players with games
            manifest.append({
                'name': name,
                'slug': slugify(name),
                'team': data['team'],
                'games': len(data['games']),
            })
    return manifest


def build_player_pages() -> None:
    """Main entry point: generate all player pages."""
    log.info("Extracting player data from games...")
    players = extract_player_data_from_games()

    if not players:
        log.warning("No player data found")
        return

    log.info(f"Found {len(players)} players")

    # Create players directory
    PLAYERS_DIR.mkdir(parents=True, exist_ok=True)

    # Generate player pages
    generated = 0
    for name, data in players.items():
        if not data['games']:
            continue

        slug = slugify(name)
        html = generate_player_html(data)
        out_path = PLAYERS_DIR / f"{slug}.html"
        out_path.write_text(html, encoding='utf-8')
        generated += 1

    log.info(f"Generated {generated} player pages")

    # Generate manifest
    manifest = generate_players_manifest(players)
    manifest_path = PLAYERS_DIR / 'players.json'
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding='utf-8')
    log.info(f"Generated players.json with {len(manifest)} entries")


if __name__ == '__main__':
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        datefmt="%H:%M:%S",
    )
    build_player_pages()
