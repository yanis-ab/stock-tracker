"""
analyzer.py — Detection des alertes de cours.
"""

import logging
from app.database import alert_already_triggered_today

logger = logging.getLogger(__name__)


def compute_distance_to_target(current: float, target: float) -> float:
    """
    Retourne le pourcentage d'ecart entre le cours actuel et le prix cible.
    Positif = cours au-dessus de la cible, negatif = cours en dessous.
    Exemple : cours=800, cible=750 -> +6.67%
    """
    if target == 0:
        return 0.0
    return round((current - target) / target * 100, 2)


def check_alerts(watchlist: list[dict], prices: list[dict]) -> list[dict]:
    """
    Analyse les cours et retourne la liste des alertes a declencher.

    watchlist : liste d'items de config.yaml (ticker, target_price, alert_type, notes...)
    prices    : liste de dicts retournes par fetcher.fetch_all_watchlist

    Retourne une liste de dicts decrivant chaque alerte a envoyer :
    {
        ticker, name, current_price, target_price, alert_type,
        distance_pct, notes, date
    }
    """
    # Indexer les prix par ticker pour acces rapide
    price_by_ticker: dict[str, dict] = {p["ticker"]: p for p in prices}

    alerts_to_send = []

    for item in watchlist:
        ticker = item.get("ticker")
        target = item.get("target_price")
        alert_type = item.get("alert_type", "below")

        if not ticker or target is None:
            logger.warning("Item watchlist invalide : %s", item)
            continue

        price_data = price_by_ticker.get(ticker)
        if not price_data:
            logger.warning("Pas de cours disponible pour %s", ticker)
            continue

        current = price_data.get("close") or price_data.get("open")
        if current is None or current == 0:
            logger.warning("Cours nul ou absent pour %s", ticker)
            continue

        triggered = False
        if alert_type == "below" and current < target:
            triggered = True
        elif alert_type == "above" and current > target:
            triggered = True

        if not triggered:
            distance = compute_distance_to_target(current, target)
            logger.debug(
                "%s : pas d'alerte (cours=%.2f, cible=%.2f, distance=%.2f%%)",
                ticker, current, target, distance
            )
            continue

        # Eviter les doublons : ne pas renvoyer si alerte deja declenchee aujourd'hui
        if alert_already_triggered_today(ticker):
            logger.info("Alerte pour %s deja declenchee aujourd'hui, ignorée.", ticker)
            continue

        distance = compute_distance_to_target(current, target)
        alert = {
            "ticker": ticker,
            "name": item.get("name", ticker),
            "current_price": current,
            "target_price": target,
            "alert_type": alert_type,
            "distance_pct": distance,
            "notes": item.get("notes", ""),
            "date": price_data.get("date"),
            "currency": price_data.get("currency", "EUR"),
        }
        alerts_to_send.append(alert)
        logger.info(
            "ALERTE : %s cours=%.2f cible=%.2f (%s) distance=%.2f%%",
            ticker, current, target, alert_type, distance
        )

    return alerts_to_send
