"""
wnba_data.py — Core data-fetching and computation module.
All functions are pure or use explicit caching; no top-level execution.
"""

import json
import logging
import re
import time
import unicodedata
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


QUARTER_SECONDS = 600   # 10-minute WNBA quarters
OT_SECONDS      = 300   # 5-minute overtime periods


def period_length(period):
    """Length in seconds of a period (1–4 are quarters, 5+ are overtimes)."""
    return QUARTER_SECONDS if period <= 4 else OT_SECONDS


def elapsed_seconds(period, clock_secs):
    """Map period + clock-remaining → seconds elapsed in the game (2400 at end of regulation)."""
    if period <= 4:
        return (period - 1) * QUARTER_SECONDS + (QUARTER_SECONDS - clock_secs)
    return 4 * QUARTER_SECONDS + (period - 5) * OT_SECONDS + (OT_SECONDS - clock_secs)


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
    Raises RuntimeError if the schedule can't be fetched, so a blocked API
    fails the run instead of silently reporting zero games.
    """
    if season_types is None:
        season_types = ["Regular Season", "Playoffs"]

    all_rows = []
    for stype in season_types:
        log.info(f"Fetching {season} WNBA {stype} schedule…")
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

def _norm_minutes(minutes: str) -> str:
    """The API sometimes reports '29:60'; normalize to '30:00'."""
    m = re.match(r"^(\d+):(\d+)", minutes or "")
    if not m:
        return minutes
    mins, secs = int(m.group(1)), int(m.group(2))
    mins, secs = mins + secs // 60, secs % 60
    return f"{mins}:{secs:02d}"


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
        "personId":            "person_id",
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
                elif dst in ("person_id", "pts", "fgm", "fga", "reb", "ast", "stl", "blk", "to", "pf"):
                    entry[dst] = int(val)
                elif dst == "plus_minus":
                    entry[dst] = float(val)
                elif dst == "minutes":
                    entry[dst] = _norm_minutes(str(val))
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

# Plays that don't mean a player is on the court
NON_PLAYING_ACTIONS = {"period", "ejection", "timeout", "instant replay"}
NON_PLAYING_MARKERS = ("T.FOUL", "TECHNICAL", "EJECT")
SUB_RE = re.compile(r"SUB:\s+(.+?)\s+FOR\s+")
AST_RE = re.compile(r"\(([^()]+?)\s+\d+\s+AST\)")


def _person_id(value) -> int | None:
    try:
        pid = int(value)
    except (TypeError, ValueError):
        return None
    return pid if pid > 0 else None


class _Roster:
    """
    One team's players in a game, keyed by personId. Substitution text names
    the incoming player loosely ('Dojkic', 'K. Brown', 'Xu'), so names are
    resolved against every spelling seen in the PBP plus the box score.
    """

    def __init__(self, team_events: pd.DataFrame, team: str, box_score: list[dict]):
        self.short: dict[int, str] = {}      # personId -> playerName
        self.initial: dict[int, str] = {}    # personId -> playerNameI ("K. Brown")
        self.index: dict[str, set] = {}      # folded name -> {personId}
        for _, row in team_events.iterrows():
            pid = _person_id(row.get("personId"))
            name = str(row.get("playerName") or "").strip()
            if pid is None or not name:
                continue
            self.short.setdefault(pid, name)
            self.initial.setdefault(pid, str(row.get("playerNameI") or "").strip())
        for pid in self.short:
            self._add(self.short[pid], pid)
            self._add(self.initial[pid], pid)
        for b in box_score or []:
            pid = _person_id(b.get("person_id"))
            if b.get("team") != team or pid is None:
                continue
            first, last = b.get("first") or "", b.get("last") or ""
            for key in (last, first, f"{first} {last}", f"{first[:1]}. {last}"):
                self._add(key, pid)
            # Box-score-only players (e.g. no PBP plays) still need a name
            self.short.setdefault(pid, last)
            self.initial.setdefault(pid, f"{first[:1]}. {last}")
        self.unresolved: dict[str, str] = {}

    def _add(self, name: str, pid: int):
        if name and name.strip(". "):
            self.index.setdefault(_fold(name), set()).add(pid)

    def resolve(self, name: str):
        """personId for a name, or a stable 'name:...' key if it can't be pinned down."""
        ids = self.index.get(_fold(name), set())
        if len(ids) == 1:
            return next(iter(ids))
        self.unresolved.setdefault(_fold(name), name)
        return f"name:{_fold(name)}"

    def display(self, key) -> str:
        """Short name for a stint row; initials when teammates share a last name."""
        if isinstance(key, str):
            return self.unresolved.get(key[5:], key[5:])
        name = self.short.get(key, "")
        if sum(1 for n in self.short.values() if _fold(n) == _fold(name)) > 1:
            return self.initial.get(key) or name
        return name


def compute_stints(pbp_df: pd.DataFrame, box_score: list[dict] | None = None) -> list[dict]:
    """
    Compute player stint records from PBP substitution events.

    Players are tracked by personId. A period's starters are the players whose
    first appearance in it isn't being subbed in (a play, or being subbed
    out); anyone still missing is filled from the previous period's closing
    lineup if they never appear.
    Returns list of dicts: {player, person_id, team, period, clock_in,
                             clock_out, duration_sec, start_elapsed,
                             end_elapsed, stint_pts, ..., events}.
    """
    stints = []
    # actionId is chronological; actionNumber is not (subs are often numbered late)
    order = "actionId" if "actionId" in pbp_df else "actionNumber"
    pbp_df = pbp_df.sort_values(order, kind="stable").copy()
    pbp_df["_clock_secs"] = pbp_df["clock"].apply(clock_to_seconds)
    # Plain objects so missing ids stay None (a float column would turn them into NaN)
    pids = pbp_df["personId"] if "personId" in pbp_df else [None] * len(pbp_df)
    pbp_df["_pid"] = pd.Series([_person_id(v) for v in pids], index=pbp_df.index, dtype=object)

    # Skip events with no team (period markers, team rebounds, timeouts,
    # instant replays tagged with a referee's name); they aren't player stints.
    teams = pbp_df["teamTricode"].dropna().astype(str).str.strip()
    for team in teams[teams != ""].unique():
        team_events = pbp_df[pbp_df["teamTricode"] == team]
        roster = _Roster(team_events, team, box_score)
        team_stints = []
        prev_lineup: list = []   # on court at the end of the previous period

        def add_stint(key, period, clock_in, clock_out, guessed=False):
            if clock_in - clock_out <= 0:
                return  # e.g. subbed out at the very start of a period
            team_stints.append({
                "key":           key,
                "_guessed":      guessed,
                "team":          str(team),
                "period":        int(period),
                "clock_in":      float(clock_in),
                "clock_out":     float(clock_out),
                "duration_sec":  round(float(clock_in - clock_out), 1),
                "start_elapsed": elapsed_seconds(int(period), float(clock_in)),
                "end_elapsed":   elapsed_seconds(int(period), float(clock_out)),
            })

        for period in sorted(pbp_df["period"].unique()):
            period_events = team_events[team_events["period"] == period]
            if period_events.empty:
                continue
            p_start = float(period_length(int(period)))

            on_court: dict = {}      # player key -> clock when they came on
            starters: list = []
            touched: set = set()     # anyone subbed in/out or credited this period

            def start_period(key):
                # First sight of a player who wasn't subbed in: they started the period
                if key not in touched:
                    on_court[key] = p_start
                    starters.append(key)
                touched.add(key)

            for _, row in period_events.iterrows():
                action = str(row.get("actionType", "")).lower()
                desc = str(row.get("description", ""))
                name = str(row.get("playerName") or "").strip()
                key = row["_pid"] or (roster.resolve(name) if name else None)
                clock_secs = row["_clock_secs"]

                if action == "substitution":
                    if clock_secs is None or pd.isna(clock_secs):
                        continue
                    if key is not None:
                        start_period(key)
                        if key in on_court:
                            add_stint(key, period, on_court.pop(key), clock_secs)
                    m = SUB_RE.match(desc)
                    if m:
                        key_in = roster.resolve(m.group(1).strip())
                        touched.add(key_in)
                        on_court[key_in] = clock_secs
                    continue

                # Bench players can draw technicals or ejections without playing
                if action in NON_PLAYING_ACTIONS or any(k in desc.upper() for k in NON_PLAYING_MARKERS):
                    continue
                if key is not None and key not in touched:
                    start_period(key)
                # An assist is only named in the scorer's play, but still shows who's on court
                m = AST_RE.search(desc) if action == "made shot" else None
                if m:
                    key_ast = roster.resolve(m.group(1).strip())
                    if key_ast not in touched:
                        start_period(key_ast)

            # Players still on from last period who never appear in this one
            # (no plays, no subs) played the whole period.
            guessed = set()
            for key in prev_lineup:
                if len(on_court) >= 5:
                    break
                if key not in touched:
                    on_court[key] = p_start
                    starters.append(key)
                    touched.add(key)
                    guessed.add(key)

            if len(starters) != 5 or len(on_court) != 5:
                log.debug(f"  {team} P{period}: {len(starters)} starters, {len(on_court)} at end")

            prev_lineup = list(on_court)
            for key, clock_in in on_court.items():
                add_stint(key, period, clock_in, 0.0, key in guessed)

        _reconcile_guesses(team_stints, box_score, team)

        for st in team_stints:
            key = st.pop("key")
            st.pop("_guessed", None)
            st["player"] = roster.display(key)
            st["person_id"] = key if isinstance(key, int) else None
            _add_stint_stats(st, pbp_df, team)
            stints.append(st)

    return stints


def _reconcile_guesses(team_stints: list[dict], box_score: list[dict] | None, team: str) -> None:
    """
    Fix filled-in lineup spots using box-score minutes.

    When a player starts a period without appearing in the play-by-play, the
    spot is filled from the previous period's lineup, which is occasionally the
    wrong player. The box score says who actually played how long: if a guess
    leaves one player over by exactly that stint and a teammate short by the
    same amount, the stint belongs to the teammate.
    """
    minutes = {}
    for b in box_score or []:
        m = b.get("minutes") or ""
        pid = _person_id(b.get("person_id"))
        if b.get("team") != team or pid is None or ":" not in m:
            continue
        mm, ss = m.split(":")[:2]
        minutes[pid] = int(mm) * 60 + int(ss)
    if not minutes:
        return

    for guess in [st for st in team_stints if st["_guessed"]]:
        got = {}
        for st in team_stints:
            got[st["key"]] = got.get(st["key"], 0) + st["duration_sec"]
        dur = guess["duration_sec"]
        if got.get(guess["key"], 0) - minutes.get(guess["key"], 0) < dur - 1:
            continue  # this player's total is fine, so the guess stands
        busy = {st["key"] for st in team_stints
                if st["period"] == guess["period"] and st is not guess}
        short = [pid for pid, box in minutes.items()
                 if pid not in busy and box - got.get(pid, 0) >= dur - 1]
        if len(short) == 1:
            log.debug(f"  {team} P{guess['period']}: reassigned a filled stint "
                      f"from {guess['key']} to {short[0]}")
            guess["key"] = short[0]

    # A period can also come up a whole player short: someone was substituted in
    # between periods without a sub being logged and never touched the ball.
    for period in sorted({st["period"] for st in team_stints}):
        length = period_length(period)
        got = {}
        for st in team_stints:
            got[st["key"]] = got.get(st["key"], 0) + st["duration_sec"]
        covered = sum(st["duration_sec"] for st in team_stints if st["period"] == period)
        if 5 * length - covered < length - 1:
            continue
        busy = {st["key"] for st in team_stints if st["period"] == period}
        missing = [pid for pid, box in minutes.items()
                   if pid not in busy and box - got.get(pid, 0) >= length - 1]
        if len(missing) == 1:
            log.debug(f"  {team} P{period}: added a full period for {missing[0]}")
            team_stints.append({
                "key": missing[0], "_guessed": True, "team": str(team), "period": int(period),
                "clock_in": float(length), "clock_out": 0.0, "duration_sec": float(length),
                "start_elapsed": elapsed_seconds(int(period), float(length)),
                "end_elapsed": elapsed_seconds(int(period), 0.0),
            })


def _add_stint_stats(stint: dict, pbp_df: pd.DataFrame, team: str) -> None:
    """Fill stint_* counts and the play list for one stint."""
    player, pid = stint["player"], stint["person_id"]
    window = pbp_df[
        (pbp_df["period"] == stint["period"]) &
        (pbp_df["_clock_secs"] >= stint["clock_out"]) &
        (pbp_df["_clock_secs"] <= stint["clock_in"]) &
        (pbp_df["teamTricode"] == team)
    ]
    if pid is not None:
        player_ev = window[window["_pid"] == pid]
    else:
        player_ev = window[window["playerName"].map(lambda n: _fold(str(n or ""))) == _fold(player)]

    made_shots = player_ev[player_ev["actionType"] == "Made Shot"]
    pts = int(made_shots["shotValue"].fillna(0).sum())
    free_throws = player_ev[player_ev["actionType"] == "Free Throw"]
    pts += int((~free_throws["description"].str.upper().str.startswith("MISS")).sum())

    # Assists are only named in the scorer's description, e.g. "(Hiedeman 1 AST)"
    last = player.split(". ", 1)[-1]
    ast_pat = re.compile(rf"\({re.escape(last)}\s+\d+\s+AST\)", re.IGNORECASE)
    made_in_window = window[(window["actionType"] == "Made Shot") & (window["_pid"] != pid)]
    assisted = made_in_window[made_in_window["description"].str.contains(ast_pat, na=False)]

    stint["stint_pts"] = pts
    stint["stint_reb"] = int((player_ev["actionType"] == "Rebound").sum())
    stint["stint_ast"] = len(assisted)
    stint["stint_stl"] = int(player_ev["description"].str.contains("STEAL", case=False, na=False).sum())
    stint["stint_blk"] = int(player_ev["description"].str.contains("BLOCK", case=False, na=False).sum())
    stint["stint_to"] = int((player_ev["actionType"] == "Turnover").sum())

    event_types = {"Made Shot", "Missed Shot", "Free Throw", "Rebound", "Turnover", "Foul"}
    events = []
    for _, ev in player_ev.iterrows():
        action = str(ev.get("actionType", ""))
        desc = str(ev.get("description", ""))
        # Include known action types + steal/block events (which have empty actionType)
        if action in event_types or "STEAL" in desc.upper() or "BLOCK" in desc.upper():
            events.append({
                "clock": clock_display(ev.get("clock", "")),
                "type": action if action else ("Steal" if "STEAL" in desc.upper() else "Block"),
                "detail": desc,
            })
    for _, ev in assisted.iterrows():
        events.append({
            "clock": clock_display(ev.get("clock", "")),
            "type": "Assist",
            "detail": str(ev.get("description", "")),
        })
    # Game clock counts down
    events.sort(key=lambda e: clock_to_seconds_display(e["clock"]), reverse=True)
    stint["events"] = events


def clock_to_seconds_display(clock: str) -> int:
    """'6:13' → 373."""
    m, _, sec = clock.partition(":")
    try:
        return int(m) * 60 + int(sec)
    except ValueError:
        return 0


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


# ── Stint name → full name ───────────────────────────────────────────────────

def _fold(s: str) -> str:
    """Lowercase and strip accents ('Dojkić' → 'dojkic')."""
    s = unicodedata.normalize("NFD", s or "")
    return "".join(c for c in s if not unicodedata.combining(c)).lower().strip()


def resolve_full_name(pbp_name: str, team: str, box_score: list[dict]) -> str | None:
    """
    Map a PBP player name ('Wilson', 'K. Brown', 'Xu') to 'First Last' using
    the box score rows for that team. Returns None if there's no unique match.
    """
    rows = [b for b in box_score if b.get("team") == team]
    name = _fold(pbp_name)
    initial = None
    m = re.match(r"^(\w)\.\s+(.+)$", name)
    if m:
        initial, name = m.group(1), m.group(2)

    candidates = [b for b in rows if _fold(b.get("last")) == name]
    if initial:
        candidates = [b for b in candidates if _fold(b.get("first")).startswith(initial)]
    if not candidates:
        # Some players are listed family-name-first in PBP (e.g. 'Xu' for Xu Han)
        candidates = [b for b in rows if _fold(b.get("first")) == name]
    if len(candidates) != 1:
        return None
    b = candidates[0]
    return f"{b.get('first', '')} {b.get('last', '')}".strip() or None


def add_full_names(stints: list[dict], box_score: list[dict]) -> None:
    """Set stint['player_full'] for every stint whose player resolves uniquely."""
    by_id = {b["person_id"]: f"{b.get('first', '')} {b.get('last', '')}".strip()
             for b in box_score if b.get("person_id")}
    cache = {}
    for s in stints:
        if s.get("person_id") in by_id:
            s["player_full"] = by_id[s["person_id"]]
            continue
        key = (s["player"], s["team"])
        if key not in cache:
            cache[key] = resolve_full_name(s["player"], s["team"], box_score)
        if cache[key]:
            s["player_full"] = cache[key]


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
