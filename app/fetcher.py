"""
fetcher.py — Recuperation des cours boursiers via yfinance.
"""

import logging
from datetime import date

import pandas as pd
import yfinance as yf

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Cours de base
# ---------------------------------------------------------------------------

def fetch_latest_price(ticker: str) -> dict | None:
    """
    Recupere le dernier cours connu pour un ticker.
    Retourne un dict compatible avec database.save_prices, ou None en cas d'erreur.
    """
    try:
        stock = yf.Ticker(ticker)
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
    """Recupere le dernier cours pour chaque ticker de la watchlist."""
    results = []
    for ticker in tickers:
        result = fetch_latest_price(ticker)
        if result:
            results.append(result)
        else:
            logger.warning("Donnees manquantes pour %s, ignore.", ticker)
    logger.info("Watchlist traitee : %d/%d tickers recuperes.", len(results), len(tickers))
    return results


# ---------------------------------------------------------------------------
# Indicateurs techniques (calcules localement depuis l'historique)
# ---------------------------------------------------------------------------

def _compute_rsi(closes: pd.Series, period: int = 14) -> float | None:
    """Calcule le RSI sur la periode donnee."""
    if len(closes) < period + 1:
        return None
    delta = closes.diff().dropna()
    gain = delta.clip(lower=0).rolling(period).mean()
    loss = (-delta.clip(upper=0)).rolling(period).mean()
    rs = gain / loss.replace(0, float("inf"))
    rsi = 100 - (100 / (1 + rs))
    val = rsi.iloc[-1]
    return round(float(val), 1) if not pd.isna(val) else None


def fetch_technicals(ticker: str) -> dict:
    """
    Calcule les indicateurs techniques depuis l'historique 1 an.

    Retourne :
      ticker, rsi, ma50, ma200, pct_from_ma200,
      week52_low, week52_high, pct_from_52w_low
    """
    result = {"ticker": ticker, "rsi": None, "ma50": None, "ma200": None,
              "pct_from_ma200": None, "week52_low": None, "week52_high": None,
              "pct_from_52w_low": None}
    try:
        stock = yf.Ticker(ticker)
        # 2 ans pour avoir assez de donnees pour la MA200
        hist = stock.history(period="2y")
        if hist.empty:
            return result

        closes = hist["Close"].dropna()
        current = float(closes.iloc[-1])

        result["rsi"] = _compute_rsi(closes)

        if len(closes) >= 50:
            result["ma50"] = round(float(closes.rolling(50).mean().iloc[-1]), 2)
        if len(closes) >= 200:
            ma200 = float(closes.rolling(200).mean().iloc[-1])
            result["ma200"] = round(ma200, 2)
            result["pct_from_ma200"] = round((current - ma200) / ma200 * 100, 1)

        # 52 semaines = 252 jours de bourse, on prend les 252 derniers points
        last_year = closes.tail(252)
        result["week52_low"] = round(float(last_year.min()), 2)
        result["week52_high"] = round(float(last_year.max()), 2)
        if result["week52_low"] and result["week52_low"] > 0:
            result["pct_from_52w_low"] = round(
                (current - result["week52_low"]) / result["week52_low"] * 100, 1
            )

    except Exception as exc:
        logger.error("Erreur indicateurs techniques %s : %s", ticker, exc)

    return result


# ---------------------------------------------------------------------------
# Donnees analystes (Yahoo Finance via yfinance)
# ---------------------------------------------------------------------------

def fetch_analyst_data(ticker: str) -> dict:
    """
    Recupere les donnees analystes et fondamentaux depuis yfinance.

    Retourne :
      ticker, target_mean, target_low, target_high, upside_pct,
      recommendation, nb_analysts,
      pe_ratio, roe, profit_margin, revenue_growth
    """
    result = {
        "ticker": ticker,
        "target_mean": None, "target_low": None, "target_high": None,
        "upside_pct": None, "recommendation": None, "nb_analysts": None,
        "pe_ratio": None, "roe": None, "profit_margin": None, "revenue_growth": None,
        "peg_ratio": None,
    }
    try:
        info = yf.Ticker(ticker).info

        current = info.get("currentPrice") or info.get("regularMarketPrice")
        target_mean = info.get("targetMeanPrice")

        result["target_mean"] = target_mean
        result["target_low"] = info.get("targetLowPrice")
        result["target_high"] = info.get("targetHighPrice")
        result["recommendation"] = (info.get("recommendationKey") or "").lower()
        result["nb_analysts"] = info.get("numberOfAnalystOpinions")

        if target_mean and current and current > 0:
            result["upside_pct"] = round((target_mean - current) / current * 100, 1)

        pe = info.get("trailingPE")
        result["pe_ratio"] = round(pe, 1) if pe else None

        roe = info.get("returnOnEquity")
        result["roe"] = round(roe * 100, 1) if roe else None

        pm = info.get("profitMargins")
        result["profit_margin"] = round(pm * 100, 1) if pm else None

        rg = info.get("revenueGrowth")
        result["revenue_growth"] = round(rg * 100, 1) if rg else None

        peg = info.get("pegRatio")
        result["peg_ratio"] = round(peg, 2) if peg else None

    except Exception as exc:
        logger.error("Erreur donnees analystes %s : %s", ticker, exc)

    return result


def fetch_fundamentals(ticker: str) -> dict:
    """
    Recupere les donnees fondamentales brutes necessaires au calcul de
    la valeur intrinseque (module valuation.py).

    Retourne :
      trailing_eps, forward_eps, book_value_per_share,
      free_cashflow, shares_outstanding,
      earnings_growth, revenue_growth, analyst_target_mean
    """
    result = {
        "ticker": ticker,
        "trailing_eps": None,
        "forward_eps": None,
        "book_value_per_share": None,
        "free_cashflow": None,
        "shares_outstanding": None,
        "earnings_growth": None,
        "revenue_growth": None,
        "analyst_target_mean": None,
    }
    try:
        info = yf.Ticker(ticker).info

        # Benefices par action
        result["trailing_eps"] = info.get("trailingEps")
        result["forward_eps"] = info.get("forwardEps")

        # Valeur comptable par action
        result["book_value_per_share"] = info.get("bookValue")

        # Free cash-flow et actions en circulation (pour FCF/action)
        result["free_cashflow"] = info.get("freeCashflow")
        result["shares_outstanding"] = (
            info.get("sharesOutstanding") or info.get("impliedSharesOutstanding")
        )

        # Taux de croissance (decimaux : 0.12 = 12%)
        eg = info.get("earningsGrowth")
        rg = info.get("revenueGrowth")
        result["earnings_growth"] = eg
        result["revenue_growth"] = rg

        # Objectif prix analystes
        result["analyst_target_mean"] = info.get("targetMeanPrice")

        # --- Donnees qualite / Moat ---
        # ROE (Return on Equity) — proxy du moat selon Buffett
        result["roe"] = info.get("returnOnEquity")  # decimal ex: 0.32 = 32%

        # Marge nette — pricing power
        result["profit_margin"] = info.get("profitMargins")  # decimal

        # Benefice net — pour le ratio FCF/Net Income (qualite des benefices)
        result["net_income"] = info.get("netIncomeToCommon")

        # Levier financier — solidite du bilan
        # yfinance retourne debtToEquity en % (ex: 50.5 = 0.505x D/E ratio)
        result["debt_to_equity"] = info.get("debtToEquity")

        # PEG Ratio (Peter Lynch) — P/E divise par taux de croissance
        # PEG <= 1.5 = action raisonnablement valorisee compte tenu de sa croissance
        result["peg_ratio"] = info.get("pegRatio")

    except Exception as exc:
        logger.error("Erreur fondamentaux %s : %s", ticker, exc)

    return result


def fetch_full_data(ticker: str) -> dict:
    """
    Agregat complet : cours + indicateurs techniques + donnees analystes + fondamentaux.
    Utilise pour la vue d'ensemble du dashboard.
    """
    price = fetch_latest_price(ticker) or {"ticker": ticker}
    technicals = fetch_technicals(ticker)
    analyst = fetch_analyst_data(ticker)
    fundamentals = fetch_fundamentals(ticker)
    return {**price, **technicals, **analyst, **fundamentals}
