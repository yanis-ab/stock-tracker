"""
fetcher.py — Recuperation des cours boursiers via yfinance.
"""

import logging
from datetime import date, timedelta

import yfinance as yf

logger = logging.getLogger(__name__)


def fetch_latest_price(ticker: str) -> dict | None:
    """
    Recupere le dernier cours connu pour un ticker.
    Retourne un dict compatible avec database.save_prices, ou None en cas d'erreur.
    """
    try:
        stock = yf.Ticker(ticker)
        # On demande 5 jours pour gerer les week-ends et jours feries
        hist = stock.history(period="5d")
        if hist.empty:
            logger.warning("Aucune donnee pour %s", ticker)
            return None

        last_row = hist.iloc[-1]
        last_date = hist.index[-1].date()

        info = stock.info
        currency = info.get("currency", "EUR")
        name = info.get("shortName") or info.get("longName") or ticker

        return {
            "ticker": ticker,
            "name": name,
            "date": last_date,
            "open": round(float(last_row.get("Open", 0) or 0), 4),
            "close": round(float(last_row.get("Close", 0) or 0), 4),
            "high": round(float(last_row.get("High", 0) or 0), 4),
            "low": round(float(last_row.get("Low", 0) or 0), 4),
            "volume": int(last_row.get("Volume", 0) or 0),
            "currency": currency,
        }
    except Exception as exc:
        logger.error("Erreur lors de la recuperation de %s : %s", ticker, exc)
        return None


def fetch_history(ticker: str, period: str = "1y") -> list[dict]:
    """
    Recupere l'historique de cours sur la periode demandee.
    period : '1mo', '3mo', '6mo', '1y', '2y', 'max'
    Retourne une liste de dicts compatibles avec database.save_prices.
    """
    try:
        stock = yf.Ticker(ticker)
        hist = stock.history(period=period)
        if hist.empty:
            logger.warning("Historique vide pour %s (periode=%s)", ticker, period)
            return []

        info = stock.info
        currency = info.get("currency", "EUR")
        name = info.get("shortName") or info.get("longName") or ticker

        records = []
        for ts, row in hist.iterrows():
            records.append({
                "ticker": ticker,
                "name": name,
                "date": ts.date(),
                "open": round(float(row.get("Open", 0) or 0), 4),
                "close": round(float(row.get("Close", 0) or 0), 4),
                "high": round(float(row.get("High", 0) or 0), 4),
                "low": round(float(row.get("Low", 0) or 0), 4),
                "volume": int(row.get("Volume", 0) or 0),
                "currency": currency,
            })
        logger.info("Historique recupere pour %s : %d points", ticker, len(records))
        return records
    except Exception as exc:
        logger.error("Erreur historique %s : %s", ticker, exc)
        return []


def fetch_all_watchlist(tickers: list[str]) -> list[dict]:
    """
    Recupere le dernier cours pour chaque ticker de la watchlist.
    Les erreurs individuelles sont loggees sans interrompre le processus.
    Retourne la liste des resultats (None exclus).
    """
    results = []
    for ticker in tickers:
        result = fetch_latest_price(ticker)
        if result:
            results.append(result)
        else:
            logger.warning("Donnees manquantes pour %s, ignoré.", ticker)
    logger.info(
        "Watchlist traitee : %d/%d tickers recuperes.", len(results), len(tickers)
    )
    return results
