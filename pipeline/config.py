from pathlib import Path

REPO_ROOT     = Path(__file__).parent.parent
DOCS_DIR      = REPO_ROOT / "docs"
GAMES_DIR     = DOCS_DIR / "games"
ASSETS_DIR    = DOCS_DIR / "assets"
TEMPLATES_DIR = REPO_ROOT / "templates"
DATA_DIR      = REPO_ROOT / "data"
RAW_DIR       = DATA_DIR / "raw"
MANIFEST_PATH = DATA_DIR / "manifest.json"
ERRORS_LOG    = DATA_DIR / "errors.log"

DELAY_SECONDS  = 1.2
RETRY_ATTEMPTS = 3
RETRY_BACKOFF  = [5, 15, 60]   # seconds before 1st, 2nd, 3rd retry
REQUEST_TIMEOUT = 60

SEASONS = ["2024", "2025", "2026"]
SEASON_TYPES = ["Regular Season", "Playoffs"]
LEAGUE_ID = "10"  # WNBA
