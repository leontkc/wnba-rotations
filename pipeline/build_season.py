"""
build_season.py — Batch pipeline runner.

Usage:
  python -m pipeline.build_season --seasons 2024 2025 2026
  python -m pipeline.build_season --game-id 0022400235
  python -m pipeline.build_season --seasons 2024 --force
"""

import argparse
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

from pipeline.config import (
    DATA_DIR, ERRORS_LOG, GAMES_DIR, MANIFEST_PATH, SEASONS, TEMPLATES_DIR,
)
from pipeline.wnba_data import (
    build_payload, build_player_game_stats, compute_score_flow,
    compute_stints, fetch_boxscore, fetch_pbp, fetch_season_games,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)


# ── Manifest I/O ──────────────────────────────────────────────────────────────

def load_manifest() -> dict:
    if MANIFEST_PATH.exists():
        return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    return {"generated_at": "", "games": {}}


def save_manifest(manifest: dict) -> None:
    manifest["generated_at"] = datetime.now(timezone.utc).isoformat()
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    MANIFEST_PATH.write_text(json.dumps(manifest, indent=2), encoding="utf-8")


def log_error(game_id: str, date: str, matchup: str, error: str) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with ERRORS_LOG.open("a", encoding="utf-8") as f:
        ts = datetime.now(timezone.utc).isoformat()
        f.write(f"{ts}  {game_id}  {date}  {matchup}  ERROR: {error}\n")


# ── HTML generation ───────────────────────────────────────────────────────────

GAME_TEMPLATE: str = None  # loaded lazily


def _get_game_template() -> str:
    global GAME_TEMPLATE
    if GAME_TEMPLATE is None:
        GAME_TEMPLATE = (TEMPLATES_DIR / "game.html").read_text(encoding="utf-8")
    return GAME_TEMPLATE


def generate_game_html(payload: dict, nav: dict, game_id: str) -> None:
    """Render and write docs/games/{game_id}.html."""
    GAMES_DIR.mkdir(parents=True, exist_ok=True)
    html = _get_game_template()

    g = payload["game"]
    title = f"{g['away_tricode']} @ {g['home_tricode']}  ·  {g['date']}  ·  {g['home_tricode']} {g['score_home']} – {g['away_tricode']} {g['score_away']}"

    html = html.replace("__GAME_TITLE__", title)
    html = html.replace("__GAME_DATA__", json.dumps(payload))
    html = html.replace("__GAME_NAV__",  json.dumps(nav))

    out = GAMES_DIR / f"{game_id}.html"
    out.write_text(html, encoding="utf-8")
    log.info(f"  Written {out.name}")


# ── Single game pipeline ──────────────────────────────────────────────────────

def process_game(game_id: str, game_info: dict) -> dict | None:
    """
    Full pipeline for one game.
    Returns manifest entry dict on success, None on unrecoverable error.
    """
    date    = game_info["date"]
    matchup = game_info["matchup"]
    log.info(f"Processing {game_id}  {date}  {matchup}")

    # 1. Play-by-play
    pbp_df = fetch_pbp(game_id)
    if pbp_df.empty:
        log.info(f"  No PBP data for {game_id} (game not yet played or unavailable). Skipping.")
        return None

    # 2. Score flow + tricodes
    try:
        score_flow, home_tc, away_tc, score_home, score_away = compute_score_flow(pbp_df)
    except Exception as e:
        log.error(f"  compute_score_flow failed: {e}")
        log_error(game_id, date, matchup, str(e))
        return None

    # Override tricodes with those from game_info if available (more reliable)
    if game_info.get("home_tricode"):
        home_tc = game_info["home_tricode"]
    if game_info.get("away_tricode"):
        away_tc = game_info["away_tricode"]

    # 3. Player stints
    try:
        stints = compute_stints(pbp_df)
    except Exception as e:
        log.error(f"  compute_stints failed: {e}")
        log_error(game_id, date, matchup, str(e))
        return None

    # 4. Box score (non-fatal)
    box_score = fetch_boxscore(game_id)
    stint_players = {s["player"] for s in stints}
    player_game_stats = build_player_game_stats(box_score, stint_players)

    # 5. Build payload
    payload = build_payload(
        game_id=game_id,
        date=date,
        matchup=matchup,
        home_tc=home_tc,
        away_tc=away_tc,
        score_home=score_home,
        score_away=score_away,
        score_flow=score_flow,
        stints=stints,
        box_score=box_score,
        player_game_stats=player_game_stats,
    )

    return payload  # nav injected later in run_build after all games sorted


# ── Main orchestrator ─────────────────────────────────────────────────────────

def run_build(seasons: list[str], force_regen: bool = False, single_game_id: str = None) -> None:
    manifest = load_manifest()

    # Collect all games across requested seasons
    all_games: list[dict] = []

    if single_game_id:
        # Single-game mode: build minimal game_info from manifest if available
        existing = manifest["games"].get(single_game_id, {})
        game_info = {
            "game_id":      single_game_id,
            "date":         existing.get("date", ""),
            "matchup":      existing.get("matchup", ""),
            "home_tricode": existing.get("home_tricode", ""),
            "away_tricode": existing.get("away_tricode", ""),
            "season":       existing.get("season", ""),
        }
        all_games = [game_info]
    else:
        for season in seasons:
            games = fetch_season_games(season)
            for g in games:
                g["season"] = season
            all_games.extend(games)

    log.info(f"Total games to consider: {len(all_games)}")

    # Compute prev/next IDs for the full sorted list
    sorted_ids = [g["game_id"] for g in all_games]
    nav_map: dict[str, dict] = {}
    for idx, gid in enumerate(sorted_ids):
        nav_map[gid] = {
            "prev": sorted_ids[idx - 1] if idx > 0 else None,
            "next": sorted_ids[idx + 1] if idx < len(sorted_ids) - 1 else None,
        }

    processed = 0
    skipped   = 0
    errors    = 0

    for game_info in all_games:
        game_id = game_info["game_id"]
        html_path = GAMES_DIR / f"{game_id}.html"
        in_manifest = game_id in manifest["games"]

        if not force_regen and html_path.exists() and in_manifest:
            skipped += 1
            continue

        payload = process_game(game_id, game_info)
        if payload is None:
            errors += 1
            continue

        nav = nav_map.get(game_id, {"prev": None, "next": None})
        try:
            generate_game_html(payload, nav, game_id)
        except Exception as e:
            log.error(f"  generate_game_html failed for {game_id}: {e}")
            log_error(game_id, game_info["date"], game_info["matchup"], str(e))
            errors += 1
            continue

        g = payload["game"]
        manifest["games"][game_id] = {
            "game_id":      game_id,
            "date":         g["date"],
            "matchup":      game_info["matchup"],
            "home_tricode": g["home_tricode"],
            "away_tricode": g["away_tricode"],
            "score_home":   g["score_home"],
            "score_away":   g["score_away"],
            "season":       game_info.get("season", ""),
            "html_path":    f"games/{game_id}.html",
        }
        save_manifest(manifest)
        processed += 1

    log.info(f"Done. Processed: {processed}  Skipped: {skipped}  Errors: {errors}")

    # Regenerate index page
    if not single_game_id:
        from pipeline.build_index import generate_index
        from pipeline.config import DOCS_DIR
        generate_index(manifest["games"], DOCS_DIR / "index.html")
    else:
        log.info("Single-game mode: skipping index regeneration.")


# ── CLI ───────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Build wnbarotations static site")
    parser.add_argument("--seasons", nargs="+", default=SEASONS,
                        help="Seasons to process (e.g. 2024 2025)")
    parser.add_argument("--force", action="store_true",
                        help="Regenerate existing game HTML files")
    parser.add_argument("--game-id", dest="game_id",
                        help="Process a single game ID only")
    args = parser.parse_args()

    run_build(
        seasons=args.seasons,
        force_regen=args.force,
        single_game_id=args.game_id,
    )
