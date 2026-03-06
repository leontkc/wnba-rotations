"""
WNBA Popcornmachine Data Validator
Verifies that player stints, score flow, and box scores can be reconstructed
from nba_api for WNBA games.
"""

import re
import sys
import time

try:
    import pandas as pd
    from nba_api.stats.endpoints import LeagueGameFinder, PlayByPlayV3
    from nba_api.stats.endpoints import BoxScoreTraditionalV3
except ImportError as e:
    print(f"[ERROR] Missing dependency: {e}")
    print("Install with:  pip install nba_api pandas")
    sys.exit(1)

DELAY = 1  # seconds between API calls


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def clock_to_seconds(clock_str):
    """Convert 'PT06M13.00S' → total seconds remaining (float)."""
    if not isinstance(clock_str, str):
        return None
    m = re.match(r"PT(\d+)M([\d.]+)S", clock_str)
    if not m:
        return None
    return int(m.group(1)) * 60 + float(m.group(2))


def clock_display(clock_str):
    """Convert 'PT06M13.00S' → '6:13'."""
    if not isinstance(clock_str, str):
        return str(clock_str)
    m = re.match(r"PT(\d+)M([\d.]+)S", clock_str)
    if not m:
        return clock_str
    mins = int(m.group(1))
    secs = int(float(m.group(2)))
    return f"{mins}:{secs:02d}"


def period_start_seconds(period):
    """Clock seconds at start of a period (counts down from 10:00 in WNBA)."""
    return 10 * 60  # 10-minute WNBA quarters


# ---------------------------------------------------------------------------
# Step 1 — Pick a game
# ---------------------------------------------------------------------------
print("=" * 60)
print("STEP 1 – Find a 2024 WNBA Regular Season game")
print("=" * 60)

try:
    finder = LeagueGameFinder(
        season_nullable="2024",
        league_id_nullable="10",
        season_type_nullable="Regular Season",
        timeout=60,
    )
    games_df = finder.get_data_frames()[0]
except Exception as e:
    print(f"[ERROR] LeagueGameFinder failed: {e}")
    sys.exit(1)

if games_df.empty:
    print("[ERROR] No games found.")
    sys.exit(1)

game_id = games_df["GAME_ID"].iloc[0]
game_date = games_df["GAME_DATE"].iloc[0]
matchup = games_df["MATCHUP"].iloc[0]
print(f"Using game: {game_id}  |  {game_date}  |  {matchup}\n")
time.sleep(DELAY)


# ---------------------------------------------------------------------------
# Step 2 — Fetch PlayByPlayV3
# ---------------------------------------------------------------------------
print("=" * 60)
print(f"STEP 2 – PlayByPlayV3  (game_id={game_id})")
print("=" * 60)

try:
    pbp = PlayByPlayV3(game_id=game_id, timeout=60)
    pbp_df = pbp.get_data_frames()[0]
except Exception as e:
    print(f"[ERROR] PlayByPlayV3 failed: {e}")
    sys.exit(1)

print(f"Total PBP rows: {len(pbp_df)}")
print(f"Columns: {list(pbp_df.columns)}\n")
time.sleep(DELAY)


# ---------------------------------------------------------------------------
# Step 3 — Compute player stints
# ---------------------------------------------------------------------------
print("=" * 60)
print("STEP 3 – Computing player stints")
print("=" * 60)

stints = []

for team in pbp_df["teamTricode"].dropna().unique():
    team_events = pbp_df[pbp_df["teamTricode"] == team].copy()
    team_events = team_events.sort_values("actionNumber")

    for period in sorted(pbp_df["period"].unique()):
        period_events = team_events[team_events["period"] == period]
        if period_events.empty:
            continue

        # --- Infer starters ---
        # Players who appear in non-sub events before first substitution
        first_sub_idx = period_events[
            period_events["actionType"].str.lower() == "substitution"
        ].index.min()

        if pd.isna(first_sub_idx):
            # No subs this period; use any player appearing in this period
            pre_sub = period_events[
                ~period_events["actionType"].str.lower().isin({"period", "substitution"})
            ]
        else:
            # Use boolean index comparison (avoids non-contiguous label issues)
            pre_sub = period_events[period_events.index < first_sub_idx]
            pre_sub = pre_sub[
                ~pre_sub["actionType"].str.lower().isin({"period", "substitution"})
            ]

        starters = pre_sub["playerName"].dropna().unique().tolist()

        # on_court: dict player -> clock_in (seconds)
        p_start = period_start_seconds(period)
        on_court = {p: p_start for p in starters}

        # Walk events in order
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

            # Close stint for player_out
            if player_out and player_out in on_court:
                clock_in = on_court.pop(player_out)
                duration = clock_in - clock_secs if clock_secs is not None else None
                stints.append({
                    "player": player_out,
                    "team": team,
                    "period": period,
                    "clock_in": clock_in,
                    "clock_out": clock_secs,
                    "duration_sec": round(duration, 1) if duration is not None else None,
                })

            # Open stint for player_in
            if player_in and clock_secs is not None:
                on_court[player_in] = clock_secs

        # Close all remaining open stints at period end (clock = 0)
        for player, clock_in in on_court.items():
            duration = clock_in  # clock_out = 0
            stints.append({
                "player": player,
                "team": team,
                "period": period,
                "clock_in": clock_in,
                "clock_out": 0.0,
                "duration_sec": round(duration, 1),
            })

stints_df = pd.DataFrame(stints)
if not stints_df.empty:
    stints_df = stints_df.sort_values(["period", "clock_in"], ascending=[True, False])


# ---------------------------------------------------------------------------
# Step 4 — Compute score flow (no extra API call)
# ---------------------------------------------------------------------------
print("STEP 4 – Score flow from PlayByPlayV3")

score_df = pbp_df[["actionNumber", "period", "clock", "scoreHome", "scoreAway"]].dropna(
    subset=["scoreHome"]
).copy()
score_df = score_df[score_df["scoreHome"].astype(str).str.strip() != ""]

print(f"Total scoring events: {len(score_df)}")
print("\nFirst 20 scoring events:")
print("-" * 60)
for _, row in score_df.head(20).iterrows():
    clk = clock_display(row["clock"])
    print(f"  Q{row['period']}  {clk:>5}  | Home {row['scoreHome']} – Away {row['scoreAway']}")
print()
time.sleep(DELAY)


# ---------------------------------------------------------------------------
# Step 5 — Fetch BoxScoreTraditionalV3
# ---------------------------------------------------------------------------
print("=" * 60)
print(f"STEP 5 – BoxScoreTraditionalV3  (game_id={game_id})")
print("=" * 60)

box_ok = False
player_stats = pd.DataFrame()

try:
    box = BoxScoreTraditionalV3(game_id=game_id, timeout=60)
    player_stats = box.get_data_frames()[0]
    box_ok = not player_stats.empty
except Exception as e:
    print(f"[ERROR] BoxScoreTraditionalV3 failed: {e}")

print(f"WNBA data accessible: {'YES' if box_ok else 'NO'}")
if box_ok:
    print(f"Columns present: {list(player_stats.columns)}")
    # Build a tidy display with the camelCase column names from V3
    display_cols = {
        "firstName": "first",
        "familyName": "last",
        "teamTricode": "team",
        "minutes": "min",
        "points": "pts",
        "reboundsTotal": "reb",
        "assists": "ast",
        "plusMinusPoints": "+/-",
    }
    available = {k: v for k, v in display_cols.items() if k in player_stats.columns}
    top6 = (
        player_stats.sort_values("points", ascending=False)
        .head(6)[list(available.keys())]
        .rename(columns=available)
    )
    print("\nSample rows (top 6 by pts):")
    print(top6.to_string(index=False))
print()


# ---------------------------------------------------------------------------
# Step 6 — Validation summary
# ---------------------------------------------------------------------------
stints_ok = not stints_df.empty and len(stints_df) > 0
score_ok = not score_df.empty and len(score_df) > 0

print("=" * 60)
print("=== PLAYER STINTS ===")
print("=" * 60)
if stints_ok:
    print(f"Total stint records : {len(stints_df)}")
    print(f"Unique players      : {stints_df['player'].nunique()}")
    avg_dur = stints_df["duration_sec"].dropna().mean()
    print(f"Avg stint duration  : {avg_dur:.1f} sec")
    print("\nSample (first 10 stints, sorted by period then clock_in desc):")
    for _, r in stints_df.head(10).iterrows():
        ci = f"{int(r['clock_in']//60)}:{int(r['clock_in']%60):02d}" if r['clock_in'] is not None else "?"
        co = f"{int(r['clock_out']//60)}:{int(r['clock_out']%60):02d}" if r['clock_out'] is not None else "?"
        print(f"  Q{r['period']} {ci}->{co}  {r['team']}  {r['player']}")
else:
    print("  No stints computed.")

print()
print("=== SCORE FLOW ===")
print("=" * 60)
if score_ok:
    first = score_df.iloc[0]
    last = score_df.iloc[-1]
    print(f"Total scoring events : {len(score_df)}")
    print(f"First score : Q{first['period']}  {clock_display(first['clock'])}  "
          f"Home {first['scoreHome']} – Away {first['scoreAway']}")
    print(f"Final score : Home {last['scoreHome']} – Away {last['scoreAway']}")
    print("\nSample (every 20th scoring event):")
    sample_indices = list(range(0, len(score_df), 20))
    for i in sample_indices:
        row = score_df.iloc[i]
        clk = clock_display(row["clock"])
        print(f"  Q{row['period']}  {clk:>5}  | Home {row['scoreHome']} – Away {row['scoreAway']}")
else:
    print("  No scoring events found.")

print()
print("=== BOX SCORE (BoxScoreTraditionalV3) ===")
print("=" * 60)
print(f"WNBA data accessible: {'YES' if box_ok else 'NO'}")
if box_ok:
    print(f"Columns present: {list(player_stats.columns)}")
    display_cols = {
        "firstName": "first",
        "familyName": "last",
        "teamTricode": "team",
        "minutes": "min",
        "points": "pts",
        "reboundsTotal": "reb",
        "assists": "ast",
        "plusMinusPoints": "+/-",
    }
    available = {k: v for k, v in display_cols.items() if k in player_stats.columns}
    top6 = (
        player_stats.sort_values("points", ascending=False)
        .head(6)[list(available.keys())]
        .rename(columns=available)
    )
    print("\nSample rows (top 6 by pts):")
    print(top6.to_string(index=False))

print()
print("=== OVERALL RESULT ===")
print("=" * 60)
print(f"[{'X' if stints_ok else ' '}] Player stints computable from PlayByPlayV3")
print(f"[{'X' if score_ok  else ' '}] Score flow computable from PlayByPlayV3")
print(f"[{'X' if box_ok    else ' '}] BoxScoreTraditionalV3 returns WNBA data")
