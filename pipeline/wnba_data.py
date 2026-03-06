"""
wnba_data.py — Core data-fetching and computation module.
All functions are pure or use explicit caching; no top-level execution.
"""

import json
import logging
import re
import time
from pathlib import Path

import pandas as pd
from nba_api.stats.endpoints import BoxScoreTraditionalV3, LeagueGameFinder, PlayByPlayV3

from pipeline.config import (
    DELAY_SECONDS, LEAGUE_ID, RAW_DIR, REQUEST_TIMEOUT,
    RETRY_ATTEMPTS, RETRY_BACKOFF,
)

log = logging.getLogger(__name__)


# ── Clock helpers ─────────────────────────────────────────────────────────────

def clock_to_seconds(clock_str):
    """'PT06M13.00S' → total seconds remaining (float). Returns None on bad input."""
    if not isinstance(clock_str, str):
        return None
    m = re.match(r"PT(\d+)M([\d.]+)S", clock_str)
    if not m:
        return None
    return int(m.group(1)) * 60 + float(m.group(2))


def clock_display(clock_str):
    """'PT06M13.00S' → '6:13'."""
    if not isinstance(clock_str, str):
        return str(clock_str)
    m = re.match(r"PT(\d+)M([\d.]+)S", clock_str)
    if not m:
        return clock_str
    return f"{int(m.group(1))}:{int(float(m.group(2))):02d}"


def elapsed_seconds(period, clock_secs):
    """Map period + clock-remaining → 0–2400 s elapsed in the game."""
    return (period - 1) * 600 + (600 - clock_secs)


# ── API retry wrapper ─────────────────────────────────────────────────────────

def api_call_with_retry(fn, *args, **kwargs):
    """
    Call fn(*args, **kwargs) with exponential backoff.
    Sleeps DELAY_SECONDS after each successful call.
    Raises RuntimeError after RETRY_ATTEMPTS failures.
    """
    last_err = None
    for attempt in range(RETRY_ATTEMPTS):
        try:
            result = fn(*args, **kwargs)
            time.sleep(DELAY_SECONDS)
            return result
        except Exception as e:
            last_err = e
            wait = RETRY_BACKOFF[attempt] if attempt < len(RETRY_BACKOFF) else RETRY_BACKOFF[-1]
            log.warning(f"API call {fn.__name__} failed (attempt {attempt+1}/{RETRY_ATTEMPTS}): {e}. Retrying in {wait}s…")
            time.sleep(wait)
    raise RuntimeError(f"API call failed after {RETRY_ATTEMPTS} attempts: {last_err}") from last_err


# ── Raw cache helpers ─────────────────────────────────────────────────────────

def _raw_path(game_id: str, kind: str) -> Path:
    return RAW_DIR / game_id / f"{kind}.json"


def _load_raw(game_id: str, kind: str):
    p = _raw_path(game_id, kind)
    if p.exists():
        return json.loads(p.read_text(encoding="utf-8"))
    return None


def _save_raw(game_id: str, kind: str, data) -> None:
    p = _raw_path(game_id, kind)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data), encoding="utf-8")


# ── Season game list ──────────────────────────────────────────────────────────

def fetch_season_games(season: str, season_types=None) -> list[dict]:
    """
    Fetch all WNBA games for a season from LeagueGameFinder.
    Returns deduplicated list (one entry per game) sorted by date ascending:
      [{game_id, date, home_tricode, away_tricode, matchup}, ...]
    """
    if season_types is None:
        season_types = ["Regular Season", "Playoffs"]

    all_rows = []
    for stype in season_types:
        log.info(f"Fetching {season} WNBA {stype} schedule…")
        try:
            finder = api_call_with_retry(
                LeagueGameFinder,
                season_nullable=season,
                league_id_nullable=LEAGUE_ID,
                season_type_nullable=stype,
                timeout=REQUEST_TIMEOUT,
            )
            df = finder.get_data_frames()[0]
            if not df.empty:
                all_rows.append(df)
        except Exception as e:
            log.error(f"LeagueGameFinder failed for {season} {stype}: {e}")

    if not all_rows:
        return []

    games_df = pd.concat(all_rows, ignore_index=True)

    # LeagueGameFinder returns two rows per game (one per team).
    # The home team's row has MATCHUP like "CON vs. CHI".
    # Filter to home-team rows only for deduplication.
    home_rows = games_df[games_df["MATCHUP"].str.contains(r" vs\. ", na=False)].copy()

    result = []
    for _, row in home_rows.iterrows():
        matchup = str(row["MATCHUP"])  # e.g. "CON vs. CHI"
        parts = matchup.split(" vs. ")
        home_tc = parts[0].strip()
        away_tc = parts[1].strip() if len(parts) > 1 else ""
        result.append({
            "game_id":      str(row["GAME_ID"]),
            "date":         str(row["GAME_DATE"]),
            "home_tricode": home_tc,
            "away_tricode": away_tc,
            "matchup":      f"{away_tc} @ {home_tc}",
        })

    # Sort by date ascending (oldest first)
    result.sort(key=lambda g: g["date"])
    log.info(f"  Found {len(result)} games for {season}")
    return result


# ── Play-by-play ──────────────────────────────────────────────────────────────

def fetch_pbp(game_id: str) -> pd.DataFrame:
    """
    Fetch PlayByPlayV3 for game_id. Uses raw cache if available.
    Returns DataFrame. Returns empty DataFrame on failure.
    """
    cached = _load_raw(game_id, "pbp")
    if cached is not None:
        log.debug(f"  PBP {game_id}: loaded from cache")
        return pd.DataFrame(cached)

    log.info(f"  Fetching PBP {game_id}…")
    try:
        pbp = api_call_with_retry(PlayByPlayV3, game_id=game_id, timeout=REQUEST_TIMEOUT)
        df = pbp.get_data_frames()[0]
        _save_raw(game_id, "pbp", df.to_dict(orient="records"))
        return df
    except Exception as e:
        log.error(f"  PlayByPlayV3 failed for {game_id}: {e}")
        return pd.DataFrame()


# ── Box score ─────────────────────────────────────────────────────────────────

def fetch_boxscore(game_id: str) -> list[dict]:
    """
    Fetch BoxScoreTraditionalV3 for game_id. Uses raw cache if available.
    Returns list of player stat dicts. Returns [] on failure (non-fatal).
    """
    cached = _load_raw(game_id, "boxscore")
    if cached is not None:
        log.debug(f"  Boxscore {game_id}: loaded from cache")
        return cached

    log.info(f"  Fetching boxscore {game_id}…")
    col_map = {
        "firstName":           "first",
        "familyName":          "last",
        "teamTricode":         "team",
        "minutes":             "minutes",
        "points":              "pts",
        "fieldGoalsMade":      "fgm",
        "fieldGoalsAttempted": "fga",
        "reboundsTotal":       "reb",
        "assists":             "ast",
        "steals":              "stl",
        "blocks":              "blk",
        "turnovers":           "to",
        "foulsPersonal":       "pf",
        "plusMinusPoints":     "plus_minus",
    }
    try:
        box = api_call_with_retry(BoxScoreTraditionalV3, game_id=game_id, timeout=REQUEST_TIMEOUT)
        player_stats = box.get_data_frames()[0]
        result = []
        for _, row in player_stats.iterrows():
            entry = {}
            for src, dst in col_map.items():
                val = row.get(src, None)
                if val is None or (isinstance(val, float) and pd.isna(val)):
                    entry[dst] = None
                elif dst in ("pts", "fgm", "fga", "reb", "ast", "stl", "blk", "to", "pf"):
                    entry[dst] = int(val)
                elif dst == "plus_minus":
                    entry[dst] = float(val)
                else:
                    entry[dst] = str(val)
            result.append(entry)
        _save_raw(game_id, "boxscore", result)
        return result
    except Exception as e:
        log.warning(f"  BoxScoreTraditionalV3 failed for {game_id}: {e} (box score will be empty)")
        return []


# ── Score flow ────────────────────────────────────────────────────────────────

def compute_score_flow(pbp_df: pd.DataFrame):
    """
    Extract score-change events from PBP DataFrame.
    Returns (score_flow, home_tricode, away_tricode, final_home, final_away).
    score_flow is a list of dicts: {elapsed_sec, period, clock_display, score_home, score_away}.
    """
    score_df = pbp_df[["actionNumber", "period", "clock", "scoreHome", "scoreAway"]].dropna(
        subset=["scoreHome"]
    ).copy()
    score_df = score_df[score_df["scoreHome"].astype(str).str.strip() != ""]

    score_flow = []
    for _, row in score_df.iterrows():
        clk_secs = clock_to_seconds(row["clock"])
        if clk_secs is None:
            continue
        period = int(row["period"])
        score_flow.append({
            "elapsed_sec":   int(elapsed_seconds(period, clk_secs)),
            "period":        period,
            "clock_display": clock_display(row["clock"]),
            "score_home":    int(row["scoreHome"]),
            "score_away":    int(row["scoreAway"]),
        })

    final_home = score_flow[-1]["score_home"] if score_flow else 0
    final_away = score_flow[-1]["score_away"] if score_flow else 0

    # Derive tricodes from the matchup column or PBP teamTricode values
    tricodes = [t for t in pbp_df["teamTricode"].dropna().unique() if t]
    home_tc = tricodes[0] if tricodes else "HOME"
    away_tc = tricodes[1] if len(tricodes) > 1 else "AWAY"

    return score_flow, home_tc, away_tc, final_home, final_away


# ── Player stints ─────────────────────────────────────────────────────────────

def compute_stints(pbp_df: pd.DataFrame) -> list[dict]:
    """
    Compute player stint records from PBP substitution events.
    Returns list of dicts: {player, team, period, clock_in, clock_out,
                             duration_sec, start_elapsed, end_elapsed,
                             stint_pts, stint_reb, stint_ast}.
    """
    stints = []

    for team in pbp_df["teamTricode"].dropna().unique():
        team_events = pbp_df[pbp_df["teamTricode"] == team].copy()
        team_events = team_events.sort_values("actionNumber")

        for period in sorted(pbp_df["period"].unique()):
            period_events = team_events[team_events["period"] == period]
            if period_events.empty:
                continue

            # Infer starters
            first_sub_idx = period_events[
                period_events["actionType"].str.lower() == "substitution"
            ].index.min()

            if pd.isna(first_sub_idx):
                pre_sub = period_events[
                    ~period_events["actionType"].str.lower().isin({"period", "substitution"})
                ]
            else:
                pre_sub = period_events[period_events.index < first_sub_idx]
                pre_sub = pre_sub[
                    ~pre_sub["actionType"].str.lower().isin({"period", "substitution"})
                ]

            starters = pre_sub["playerName"].dropna().unique().tolist()
            p_start = 600.0  # 10-min WNBA quarters
            on_court = {p: p_start for p in starters}

            for _, row in period_events.iterrows():
                action = str(row.get("actionType", "")).lower()
                if action != "substitution":
                    continue

                clock_str = row.get("clock", "")
                clock_secs = clock_to_seconds(clock_str)
                desc = str(row.get("description", ""))

                player_out = row.get("playerName")
                m = re.match(r"SUB:\s+(.+?)\s+FOR\s+", desc)
                player_in = m.group(1).strip() if m else None

                if player_out and player_out in on_court:
                    clock_in = on_court.pop(player_out)
                    if clock_secs is not None:
                        stints.append({
                            "player":        player_out,
                            "team":          str(team),
                            "period":        int(period),
                            "clock_in":      float(clock_in),
                            "clock_out":     float(clock_secs),
                            "duration_sec":  round(float(clock_in - clock_secs), 1),
                            "start_elapsed": elapsed_seconds(int(period), float(clock_in)),
                            "end_elapsed":   elapsed_seconds(int(period), float(clock_secs)),
                        })

                if player_in and clock_secs is not None:
                    on_court[player_in] = clock_secs

            # Close open stints at period end
            for player, clock_in in on_court.items():
                stints.append({
                    "player":        player,
                    "team":          str(team),
                    "period":        int(period),
                    "clock_in":      float(clock_in),
                    "clock_out":     0.0,
                    "duration_sec":  round(float(clock_in), 1),
                    "start_elapsed": elapsed_seconds(int(period), float(clock_in)),
                    "end_elapsed":   elapsed_seconds(int(period), 0.0),
                })

    # Compute per-stint stats from PBP events
    pbp_df = pbp_df.copy()
    pbp_df["_clock_secs"] = pbp_df["clock"].apply(clock_to_seconds)

    for stint in stints:
        player   = stint["player"]
        period   = stint["period"]
        clock_in = stint["clock_in"]
        clock_out = stint["clock_out"]

        if not player:
            stint.update({"stint_pts": 0, "stint_reb": 0, "stint_ast": 0})
            continue

        window_mask = (
            (pbp_df["period"] == period) &
            (pbp_df["_clock_secs"] >= clock_out) &
            (pbp_df["_clock_secs"] <= clock_in)
        )
        window = pbp_df[window_mask]
        player_ev = window[window["playerName"] == player]

        made_shots = player_ev[player_ev["actionType"] == "Made Shot"]
        pts = int(made_shots["shotValue"].fillna(0).sum())

        free_throws = player_ev[player_ev["actionType"] == "Free Throw"]
        pts += int((~free_throws["description"].str.upper().str.startswith("MISS")).sum())

        reb = int((player_ev["actionType"] == "Rebound").sum())

        ast_pat = re.compile(rf"\({re.escape(player)}\s+\d+\s+AST\)", re.IGNORECASE)
        made_in_window = window[window["actionType"] == "Made Shot"]
        ast = int(made_in_window["description"].apply(
            lambda d: bool(ast_pat.search(str(d)))).sum())

        stint["stint_pts"] = pts
        stint["stint_reb"] = reb
        stint["stint_ast"] = ast

    return stints


# ── Box score → player_game_stats lookup ─────────────────────────────────────

def build_player_game_stats(box_score: list[dict], stint_players: set) -> dict:
    """
    Build {player_name: {pts, reb, ast, stl}} from box score entries.
    Falls back to last-name matching for stint players not directly found.
    """
    player_game_stats = {}
    for entry in box_score:
        full_name = f"{entry.get('first', '')} {entry.get('last', '')}".strip()
        player_game_stats[full_name] = {
            "pts": entry.get("pts") or 0,
            "reb": entry.get("reb") or 0,
            "ast": entry.get("ast") or 0,
            "stl": entry.get("stl") or 0,
        }

    last_name_map = {}
    for full_name, stat in player_game_stats.items():
        last = full_name.split()[-1]
        last_name_map.setdefault(last, stat)

    for sp in stint_players:
        if not sp or sp in player_game_stats:
            continue
        parts = sp.split()
        if parts and parts[-1] in last_name_map:
            player_game_stats[sp] = last_name_map[parts[-1]]

    return player_game_stats


# ── Payload assembly ──────────────────────────────────────────────────────────

def build_payload(game_id: str, date: str, matchup: str,
                  home_tc: str, away_tc: str,
                  score_home: int, score_away: int,
                  score_flow: list, stints: list,
                  box_score: list, player_game_stats: dict) -> dict:
    """Assemble the DATA payload dict for template injection."""
    return {
        "game": {
            "id":           game_id,
            "date":         date,
            "matchup":      matchup,
            "home_tricode": home_tc,
            "away_tricode": away_tc,
            "score_home":   score_home,
            "score_away":   score_away,
        },
        "score_flow":       score_flow,
        "stints":           stints,
        "box_score":        box_score,
        "player_game_stats": player_game_stats,
    }
