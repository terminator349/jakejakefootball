"""Download the public nflverse data that data/real_league.py builds the real league from (task 4.4).

    python data/nflverse_fetch.py    # about 7 MB into data/nflverse/ (not committed)

nflverse (github.com/nflverse/nflverse-data) publishes free NFL data: rosters,
season stats, Pro Football Reference's advanced stats, snap counts and Over The
Cap's contracts. Only the builder needs these files; the game reads the
league_real.json it writes, so playing never downloads anything.
"""

import urllib.request
from pathlib import Path

SEASON = 2025
RAW_DIR = Path(__file__).parent / "nflverse"
BASE = "https://github.com/nflverse/nflverse-data/releases/download"

FILES = {
    f"roster_{SEASON}.csv": f"rosters/roster_{SEASON}.csv",
    f"stats_player_reg_{SEASON}.csv": f"stats_player/stats_player_reg_{SEASON}.csv",
    f"snap_counts_{SEASON}.csv": f"snap_counts/snap_counts_{SEASON}.csv",
    "advstats_season_def.csv": "pfr_advstats/advstats_season_def.csv",
    "advstats_season_pass.csv": "pfr_advstats/advstats_season_pass.csv",
    "advstats_season_rec.csv": "pfr_advstats/advstats_season_rec.csv",
    "advstats_season_rush.csv": "pfr_advstats/advstats_season_rush.csv",
    "historical_contracts.csv.gz": "contracts/historical_contracts.csv.gz",
}


def fetch(force: bool = False) -> None:
    RAW_DIR.mkdir(exist_ok=True)
    for name, path in FILES.items():
        out = RAW_DIR / name
        if out.exists() and not force:
            print(f"have {name}")
            continue
        request = urllib.request.Request(f"{BASE}/{path}", headers={"User-Agent": "front-office-course-project"})
        with urllib.request.urlopen(request, timeout=60) as response:
            data = response.read()
        out.write_bytes(data)
        print(f"got {name} ({len(data) / 1e6:.1f} MB)")


if __name__ == "__main__":
    fetch()
