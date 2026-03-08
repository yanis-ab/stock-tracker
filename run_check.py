"""
run_check.py — Point d'entree pour GitHub Actions.
Lance la verification quotidienne une seule fois (pas de scheduler).
"""

import logging
import sys

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)

from app.database import init_db
from app.scheduler import run_daily_check

if __name__ == "__main__":
    init_db()
    run_daily_check()
