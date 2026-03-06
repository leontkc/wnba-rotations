"""
WNBA Play-by-Play Data Accessibility Test via nba_api
Tests whether play-by-play data for WNBA games can be retrieved.
"""

import time
import sys

# ---------------------------------------------------------------------------
# Dependency check / install hint
# ---------------------------------------------------------------------------
try:
    import pandas as pd
    from nba_api.stats.endpoints import (
        LeagueGameFinder,
        PlayByPlayV3,
    )
    from nba_api.stats.static import teams as nba_teams_static
except ImportError as e:
    print(f"[ERROR] Missing dependency: {e}")
    print("Install with:  pip install nba_api pandas")
    sys.exit(1)

DELAY = 1  # seconds between API calls – respect rate limits

# ---------------------------------------------------------------------------
# 1. List all WNBA teams
# ---------------------------------------------------------------------------
print("=" * 60)
print("STEP 1 – WNBA Teams")
print("=" * 60)

# nba_api exposes WNBA teams via the same static helper;
# WNBA teams carry an 'is_wnba_team' flag (or we filter by id range).
all_teams = nba_teams_static.get_teams()

# WNBA team IDs all start with '1611' in the nba_api dataset.
wnba_teams = [t for t in all_teams if str(t["id"]).startswith("1611")]

if not wnba_teams:
    # Fallback: nba_api also ships a dedicated wnba teams module in newer builds
    try:
        from nba_api.stats.static import teams as wnba_mod  # noqa: F401
        # Try the dedicated helper if available
        wnba_teams = nba_teams_static.get_wnba_teams()
    except AttributeError:
        pass

if not wnba_teams:
    print("[WARN] Could not detect WNBA teams from static data – continuing anyway.")
else:
    print(f"Found {len(wnba_teams)} WNBA team(s):\n")
    for t in wnba_teams:
        print(f"  {t['id']:>12}  {t['abbreviation']:<6}  {t['full_name']}")

print()
time.sleep(DELAY)

# ---------------------------------------------------------------------------
# 2. Find a game from the 2024 WNBA season
# ---------------------------------------------------------------------------
print("=" * 60)
print("STEP 2 – Find a 2024 WNBA Game  (LeagueGameFinder, league_id='10')")
print("=" * 60)

try:
    finder = LeagueGameFinder(
        season_nullable="2024",
        league_id_nullable="10",          # 10 = WNBA
        season_type_nullable="Regular Season",
        timeout=60,
    )
    games_df = finder.get_data_frames()[0]
except Exception as e:
    print(f"[ERROR] LeagueGameFinder failed: {e}")
    sys.exit(1)

print(f"Total game-rows returned: {len(games_df)}")

if games_df.empty:
    print("[ERROR] No games found – cannot continue.")
    sys.exit(1)

# Each game appears twice (one row per team); grab the first unique GAME_ID.
game_id = games_df["GAME_ID"].iloc[0]
game_date = games_df["GAME_DATE"].iloc[0]
matchup = games_df["MATCHUP"].iloc[0]

print(f"\nUsing game:  {game_id}  |  {game_date}  |  {matchup}\n")
print(games_df[["GAME_ID", "GAME_DATE", "MATCHUP", "TEAM_ABBREVIATION"]].head(4).to_string(index=False))
print()
time.sleep(DELAY)

# ---------------------------------------------------------------------------
# 3. Pull PlayByPlayV3 for that game
# ---------------------------------------------------------------------------
print("=" * 60)
print(f"STEP 3 – PlayByPlayV3  (game_id={game_id})")
print("=" * 60)

try:
    pbp = PlayByPlayV3(game_id=game_id, timeout=60)
    pbp_df = pbp.get_data_frames()[0]
except Exception as e:
    print(f"[ERROR] PlayByPlayV3 failed: {e}")
    sys.exit(1)

print(f"Total play-by-play rows: {len(pbp_df)}")
print(f"Columns: {list(pbp_df.columns)}\n")
time.sleep(DELAY)

# ---------------------------------------------------------------------------
# 4. Filter substitution events
#    V2 schema: EVENTMSGTYPE == 8
#    V3 schema: actionType == 'substitution'
# ---------------------------------------------------------------------------
print("=" * 60)
print("STEP 4 – Substitution Events")
print("=" * 60)

# Detect which schema V3 returned
cols = pbp_df.columns.tolist()
print(f"Schema detected – first few columns: {cols[:8]}\n")

if "actionType" in cols:
    # ---- PlayByPlayV3 schema ----
    # Each sub row = one player (going OUT); incoming player is in description
    # e.g. "SUB: Davis FOR Onyenwere"
    schema = "v3"
    subs_df = pbp_df[pbp_df["actionType"].str.lower() == "substitution"].copy()

    p1_col     = "playerName"   # player going OUT
    p2_col     = None           # parsed from description below
    period_col = "period"
    clock_col  = "clock"
    desc_col   = "description"

elif "EVENTMSGTYPE" in cols:
    # ---- PlayByPlayV2 schema (fallback) ----
    schema = "v2"
    subs_df = pbp_df[pbp_df["EVENTMSGTYPE"] == 8].copy()
    p1_col, p2_col = "PLAYER1_NAME", "PLAYER2_NAME"
    period_col, clock_col = "PERIOD", "PCTIMESTRING"
    desc_col = "HOMEDESCRIPTION"

else:
    print("[ERROR] Unrecognised play-by-play schema – cannot filter substitutions.")
    print(f"All columns: {cols}")
    sys.exit(1)

print(f"Schema: {schema.upper()}  |  Total substitution events: {len(subs_df)}\n")
total_subs = len(subs_df)

if subs_df.empty:
    print("[WARN] No substitution events found in this game.")
else:
    print("First 10 substitution events:")
    print("-" * 60)
    import re as _re
    for _, row in subs_df.head(10).iterrows():
        period = row.get(period_col, "?") if period_col != "?" else "?"
        clock  = row.get(clock_col,  "?") if clock_col  != "?" else "?"
        p1     = row.get(p1_col, "N/A") if p1_col else "N/A"
        desc   = row.get(desc_col, "") if desc_col else ""

        # V3: parse "SUB: PlayerIn FOR PlayerOut" to get incoming player
        if schema == "v3":
            m = _re.match(r"SUB:\s+(.+?)\s+FOR\s+", str(desc))
            p2 = m.group(1) if m else "N/A"
        else:
            p2 = row.get(p2_col, "N/A") if p2_col else "N/A"

        # V3: convert "PT06M13.00S" → "6:13.00"
        if isinstance(clock, str) and clock.startswith("PT"):
            m = _re.match(r"PT(\d+)M([\d.]+)S", clock)
            clock = f"{m.group(1)}:{float(m.group(2)):05.2f}" if m else clock

        print(f"  Q{period} {str(clock):>8}  |  OUT: {str(p1):<25}  IN: {str(p2):<25}  | {desc}")

print()

# ---------------------------------------------------------------------------
# 5. Summary
# ---------------------------------------------------------------------------
print("=" * 60)
print("STEP 5 – Summary")
print("=" * 60)

total_events = len(pbp_df)

# Resolve name columns for whichever schema was returned
_p1_col = p1_col if p1_col and p1_col in pbp_df.columns else None
# V3: incoming player is embedded in description, not a dedicated column
_p2_col = p2_col if (p2_col and p2_col in pbp_df.columns) else (
    "description" if schema == "v3" else None
)

def _count_populated(df, col):
    if col is None or col not in df.columns:
        return 0
    return (df[col].notna() & (df[col].astype(str).str.strip() != "")).sum()

p1_populated = _count_populated(pbp_df, _p1_col)
p2_populated = _count_populated(pbp_df, _p2_col)

p1_pct = 100 * p1_populated / total_events if total_events else 0
p2_pct = 100 * p2_populated / total_events if total_events else 0

p1_ok = bool(_p1_col and p1_populated > 0)
p2_ok = bool(_p2_col and p2_populated > 0)

print(f"  Schema used         : PlayByPlayV3 ({schema.upper()})")
print(f"  Game ID examined    : {game_id}")
print(f"  Game date / matchup : {game_date}  {matchup}")
print(f"  Total PBP events    : {total_events}")
print(f"  Total substitutions : {total_subs}")
print(f"  {_p1_col or 'PLAYER1'} populated : {'YES' if p1_ok else 'NO'}  ({p1_populated} rows, {p1_pct:.1f}%)")
print(f"  {_p2_col or 'PLAYER2'} populated : {'YES' if p2_ok else 'NO'}  ({p2_populated} rows, {p2_pct:.1f}%)")

print()
if total_events == 0:
    print("[RESULT] PlayByPlayV3 returned NO data for this WNBA game.")
elif p1_ok:
    print("[RESULT] WNBA play-by-play data with player names is ACCESSIBLE via PlayByPlayV3.")
else:
    print("[RESULT] PlayByPlayV3 returned rows but player name fields are EMPTY.")
