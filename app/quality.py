"""
quality.py — Evaluation de la qualite fondamentale et du "Moat" (avantage concurrentiel).

Philosophie (Buffett / QGARP) :
  Avant de s'interroger sur le prix, on s'interroge sur la qualite de l'entreprise.
  Une entreprise de qualite se reconnait a sa capacite a generer des rendements
  eleves sur son capital de facon durable — c'est le signe d'un avantage concurrentiel.

Les 4 criteres retenus :
  1. ROE > 15%         : preuve d'un avantage concurrentiel (Buffett : >20% = fort moat)
  2. Marge nette > 10% : pricing power — l'entreprise impose ses prix
  3. FCF / Net Income  : qualite des benefices — evite les entreprises qui "fabriquent"
     > 0.75              des profits sans cash reel
  4. Levier maitrise   : bilan solide en cas de crise (D/E normalise < 1.5x)
"""

import logging
from typing import Optional

logger = logging.getLogger(__name__)


def compute_quality_score(fundamentals: dict) -> dict:
    """
    Calcule le score de qualite fondamentale (Moat) de l'entreprise.

    Parametres :
      fundamentals : dict issu de fetch_fundamentals() (yfinance info)

    Retourne :
      {
        score    : int 0-4,
        label    : "Qualite elevee" / "Qualite moyenne" / "Qualite faible",
        color    : hex color,
        criteria : list[{label, ok}],
      }
    """
    criteria = []
    score = 0

    # --- 1. ROE > 15% ---
    # Le ROE mesure combien l'entreprise gagne pour chaque euro investi par les actionnaires.
    # Buffett recherche ROE > 20% sur 5 ans. On utilise 15% comme seuil minimum.
    # Donne en decimal (0.32 = 32%)
    roe = fundamentals.get("roe")
    if roe is not None:
        ok = roe > 0.15
        if ok:
            score += 1
        roe_pct = roe * 100
        note = "fort avantage concurrentiel" if roe > 0.20 else ("moat modere" if ok else "insuffisant")
        criteria.append({
            "label": f"ROE {roe_pct:.1f}% — {note}",
            "ok": ok,
        })
    else:
        criteria.append({"label": "ROE — donnee indisponible", "ok": False})

    # --- 2. Marge nette > 10% ---
    # Une marge nette elevee signifie que l'entreprise peut imposer ses prix
    # sans sacrifier sa rentabilite (pricing power = signe de moat).
    # Donne en decimal (0.25 = 25%)
    margin = fundamentals.get("profit_margin")
    if margin is not None:
        ok = margin > 0.10
        if ok:
            score += 1
        margin_pct = margin * 100
        note = "pricing power exceptionnel" if margin > 0.20 else ("bon pricing power" if ok else "marges etroites")
        criteria.append({
            "label": f"Marge nette {margin_pct:.1f}% — {note}",
            "ok": ok,
        })
    else:
        criteria.append({"label": "Marge nette — donnee indisponible", "ok": False})

    # --- 3. Qualite des benefices : FCF / Net Income > 0.75 ---
    # Si le free cash flow est proche du benefice net, les profits sont "reels".
    # Un ecart important indique des manipulations comptables ou des investissements massifs
    # qui ne se traduisent pas en cash (signal d'alerte pour l'investisseur).
    fcf = fundamentals.get("free_cashflow")
    net_income = fundamentals.get("net_income")
    if fcf is not None and net_income and net_income > 0:
        ratio = fcf / net_income
        ok = ratio > 0.75
        if ok:
            score += 1
        note = "benefices solides et reels" if ratio > 1.0 else ("bonne qualite" if ok else "ecart FCF/resultat a surveiller")
        criteria.append({
            "label": f"Qualite benefices FCF/NI = {ratio:.2f}x — {note}",
            "ok": ok,
        })
    else:
        criteria.append({"label": "Qualite benefices — donnees insuffisantes", "ok": False})

    # --- 4. Levier financier maitrise : D/E normalise < 1.5x ---
    # yfinance retourne debtToEquity en decimal ratio x100 selon les sources.
    # On normalise : si valeur > 10, on suppose que c'est en % et on divise par 100.
    # Airbus et les industriels lourds peuvent avoir un levier plus eleve structurellement.
    de_raw = fundamentals.get("debt_to_equity")
    if de_raw is not None:
        # Normalisation : yfinance est inconsistant (ratio ou %)
        de_ratio = de_raw / 100.0 if de_raw > 10 else de_raw
        ok = de_ratio < 1.5
        if ok:
            score += 1
        note = "bilan tres solide" if de_ratio < 0.5 else ("bilan sain" if ok else "endettement eleve")
        criteria.append({
            "label": f"Levier D/E = {de_ratio:.2f}x — {note}",
            "ok": ok,
        })
    else:
        criteria.append({"label": "Levier — donnee indisponible", "ok": False})

    # --- Label et couleur ---
    if score >= 3:
        label, color = "Qualite elevee", "#27ae60"
    elif score == 2:
        label, color = "Qualite moyenne", "#e67e22"
    else:
        label, color = "Qualite faible", "#c0392b"

    logger.debug(
        "Qualite %s : score=%d/4 (%s)",
        fundamentals.get("ticker", "?"), score, label,
    )

    return {
        "score": score,
        "label": label,
        "color": color,
        "criteria": criteria,
    }
