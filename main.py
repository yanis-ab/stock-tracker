"""
main.py — Point d'entree de Stock Monitor.

Lance :
  1. Le scheduler APScheduler (thread daemon) pour la tache quotidienne
  2. Le dashboard Streamlit en sous-processus
  3. Ouvre automatiquement http://localhost:8501 dans le navigateur
"""

import logging
import logging.handlers
import subprocess
import sys
import time
import webbrowser
from pathlib import Path

from app.database import init_db
from app.scheduler import start_scheduler

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

_BASE_DIR = Path(__file__).resolve().parent
_LOG_DIR = _BASE_DIR / "logs"
_LOG_DIR.mkdir(exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.handlers.TimedRotatingFileHandler(
            _LOG_DIR / "monitor.log",
            when="W0",          # rotation chaque lundi
            backupCount=4,
            encoding="utf-8",
        ),
    ],
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    logger.info("=== Demarrage de Stock Monitor ===")

    # Initialiser la BDD
    init_db()

    # Demarrer le scheduler
    scheduler = start_scheduler()

    # Lancer le dashboard Streamlit en sous-processus
    dashboard_path = _BASE_DIR / "dashboard" / "streamlit_app.py"
    streamlit_cmd = [
        sys.executable, "-m", "streamlit", "run",
        str(dashboard_path),
        "--server.headless", "true",
        "--server.port", "8501",
    ]

    logger.info("Lancement du dashboard Streamlit...")
    streamlit_proc = subprocess.Popen(
        streamlit_cmd,
        cwd=str(_BASE_DIR),
    )

    # Attendre quelques secondes puis ouvrir le navigateur
    time.sleep(3)
    url = "http://localhost:8501"
    logger.info("Ouverture du navigateur : %s", url)
    webbrowser.open(url)

    logger.info("Stock Monitor actif. Ctrl+C pour arreter.")
    logger.info("Dashboard : %s", url)

    try:
        while True:
            if streamlit_proc.poll() is not None:
                logger.warning("Le processus Streamlit s'est arrete, redemarrage...")
                streamlit_proc = subprocess.Popen(
                    streamlit_cmd,
                    cwd=str(_BASE_DIR),
                )
            time.sleep(10)
    except KeyboardInterrupt:
        logger.info("Arret demande par l'utilisateur.")
    finally:
        streamlit_proc.terminate()
        scheduler.shutdown(wait=False)
        logger.info("Stock Monitor arrete.")


if __name__ == "__main__":
    main()
