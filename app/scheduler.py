"""
scheduler.py — Planification de la tache quotidienne via APScheduler.
"""

import logging
from pathlib import Path

import yaml
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

logger = logging.getLogger(__name__)

_BASE_DIR = Path(__file__).resolve().parent.parent
_CONFIG_PATH = _BASE_DIR / "config.yaml"


def load_config() -> dict:
    with open(_CONFIG_PATH, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def run_daily_check() -> None:
    """
    Tache quotidienne principale :
    1. Charge la config
    2. Recupere les cours
    3. Sauvegarde en base
    4. Analyse les alertes
    5. Envoie les notifications
    6. Enregistre les alertes en base
    """
    from app.fetcher import fetch_all_watchlist, fetch_history
    from app.database import init_db, save_prices, save_alert, get_latest_price
    from app.analyzer import check_alerts
    from app.notifier import notify

    logger.info("=== Debut de la tache quotidienne ===")

    config = load_config()
    watchlist = config.get("watchlist", [])
    tickers = [item["ticker"] for item in watchlist]

    if not tickers:
        logger.warning("Watchlist vide, rien a faire.")
        return

    # Premier lancement : peupler l'historique si la BDD est vide
    for ticker in tickers:
        if get_latest_price(ticker) is None:
            logger.info("Premier lancement : recuperation de l'historique 1 an pour %s", ticker)
            history = fetch_history(ticker, period="1y")
            if history:
                save_prices(history)

    # Recuperer les cours du jour
    prices = fetch_all_watchlist(tickers)
    if not prices:
        logger.warning("Aucun cours recupere, fin de la tache.")
        return

    # Sauvegarder en base
    save_prices(prices)

    # Analyser les alertes
    alerts = check_alerts(watchlist, prices)
    logger.info("%d alerte(s) detectee(s).", len(alerts))

    if not alerts:
        logger.info("Aucune alerte a envoyer.")
        logger.info("=== Fin de la tache quotidienne ===")
        return

    # Envoyer les notifications
    channel = notify(alerts, config)
    notification_sent = channel != "none"

    # Enregistrer les alertes en base
    for alert in alerts:
        save_alert({
            "ticker": alert["ticker"],
            "current_price": alert["current_price"],
            "target_price": alert["target_price"],
            "alert_type": alert["alert_type"],
            "notification_sent": notification_sent,
            "channel": channel,
        })

    logger.info("=== Fin de la tache quotidienne ===")


def start_scheduler(scheduler: BackgroundScheduler | None = None) -> BackgroundScheduler:
    """
    Demarre le scheduler APScheduler avec un CronTrigger base sur config.yaml.
    Retourne l'instance du scheduler.
    """
    config = load_config()
    schedule_cfg = config.get("schedule", {})
    time_str = schedule_cfg.get("time", "09:00")
    timezone = schedule_cfg.get("timezone", "Europe/Paris")

    hour, minute = time_str.split(":")

    if scheduler is None:
        scheduler = BackgroundScheduler(timezone=timezone)

    trigger = CronTrigger(hour=int(hour), minute=int(minute), timezone=timezone)
    scheduler.add_job(
        run_daily_check,
        trigger=trigger,
        id="daily_check",
        name="Verification quotidienne des cours",
        replace_existing=True,
        misfire_grace_time=3600,  # tolerance de 1h si l'ordi etait eteint
    )

    scheduler.start()
    logger.info(
        "Scheduler demarre — tache quotidienne a %s (%s)", time_str, timezone
    )
    return scheduler
