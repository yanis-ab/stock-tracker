"""
analyzer.py — Detection des alertes et score de conviction GARP.

Le prix cible n'est plus fixe manuellement : il est calcule a partir
de la valeur intrinseque de l'entreprise (module valuation.py).
Un prix cible manuel peut toutefois etre force via 'target_override' dans config.yaml.
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


def compute_conviction_score(
    current_price: float,
    target_price: float,
    alert_type: str,
    technicals: dict,
    analyst_data: dict,
) -> dict:
    """
    Calcule un score de conviction 0-6 pour une action (strategie QGARP long terme).

    Les 6 criteres :
      1. Cours sous le prix cible calcule (valeur intrinseque - marge securite)
      2. RSI < 40 (pression vendeuse, potentiel rebond)
      3. Cours sous la MA200 (decote sur tendance long terme)
      4. Upside analystes > 15% (les pros voient de la valeur)
      5. Consensus analystes = buy ou strong_buy
      6. PEG Ratio <= 1.5 (Peter Lynch : croissance a un prix raisonnable)

    Retourne : {score, label, color, criteria}
    """
    criteria = []
    score = 0

    # 1. Cours dans la zone d'achat (valeur intrinseque - marge de securite)
    if alert_type == "below":
        ok = current_price < target_price
        label = f"Cours sous le prix cible calcule ({target_price:.0f} \u20ac)"
    else:
        ok = current_price > target_price
        label = f"Cours au-dessus du prix cible calcule ({target_price:.0f} \u20ac)"
    if ok:
        score += 1
    criteria.append({"label": label, "ok": ok})

    # 2. RSI < 40
    rsi = technicals.get("rsi")
    if rsi is not None:
        ok = rsi < 40
        if ok:
            score += 1
        rsi_msg = "— survendu, pression baissi\u00e8re" if ok else "— pas encore survendu"
        criteria.append({
            "label": f"RSI {rsi:.0f} {rsi_msg}",
            "ok": ok,
        })
    else:
        criteria.append({"label": "RSI — donn\u00e9e indisponible", "ok": False})

    # 3. Cours sous la MA200
    ma200 = technicals.get("ma200")
    pct = technicals.get("pct_from_ma200")
    if ma200:
        ok = current_price < ma200
        if ok:
            score += 1
        pct_str = f" ({pct:+.1f}%)" if pct is not None else ""
        criteria.append({
            "label": f"Cours {'sous' if ok else 'au-dessus de'} la MA200 ({ma200:.0f}){pct_str}",
            "ok": ok,
        })
    else:
        criteria.append({"label": "MA200 — donn\u00e9e insuffisante (< 200 jours)", "ok": False})

    # 4. Upside analystes > 15%
    upside = analyst_data.get("upside_pct")
    nb = analyst_data.get("nb_analysts") or 0
    if upside is not None:
        ok = upside > 15
        if ok:
            score += 1
        nb_str = f" ({nb} analystes)" if nb else ""
        criteria.append({
            "label": f"Upside analystes {upside:+.1f}%{nb_str} {'— attractive' if ok else '— insuffisant'}",
            "ok": ok,
        })
    else:
        criteria.append({"label": "Objectif analystes — non couvert", "ok": False})

    # 5. Consensus buy / strong_buy
    reco = (analyst_data.get("recommendation") or "").lower()
    ok = reco in ("buy", "strong_buy")
    if ok:
        score += 1
    reco_display = {
        "strong_buy": "Achat fort",
        "buy": "Achat",
        "hold": "Conserver",
        "sell": "Vente",
        "strong_sell": "Vente forte",
    }.get(reco, reco or "N/A")
    criteria.append({
        "label": f"Consensus analystes : {reco_display}",
        "ok": ok,
    })

    # 6. PEG Ratio <= 1.5 (Peter Lynch)
    # PEG = P/E / taux_croissance_benefices
    # PEG <= 1.0 : action bon marche par rapport a sa croissance
    # PEG <= 1.5 : croissance a un prix raisonnable
    # PEG >  2.0 : attention, croissance surevaluee
    peg = analyst_data.get("peg_ratio")
    if peg is not None and peg > 0:
        ok = peg <= 1.5
        if ok:
            score += 1
        note = "bon marche vs croissance" if peg <= 1.0 else ("raisonnable" if ok else "croissance surevaluee")
        criteria.append({
            "label": f"PEG Ratio {peg:.2f} — {note}",
            "ok": ok,
        })
    else:
        criteria.append({"label": "PEG Ratio — donn\u00e9e indisponible", "ok": False})

    # Label et couleur (seuils adaptes au score sur 6)
    if score >= 5:
        label, color = "Zone d'achat forte", "#27ae60"
    elif score == 4:
        label, color = "Zone interessante", "#2980b9"
    elif score in (2, 3):
        label, color = "A surveiller", "#e67e22"
    else:
        label, color = "Attendre", "#95a5a6"

    return {"score": score, "label": label, "color": color, "criteria": criteria}


def check_alerts(watchlist: list[dict], prices: list[dict]) -> list[dict]:
    """
    Analyse les cours et retourne la liste des alertes a declencher.

    Le prix cible est calcule intelligemment via la valeur intrinseque
    (Graham Number, Graham Growth, DCF, consensus analystes).
    Un 'target_override' dans config.yaml permet de forcer un prix manuel.
    """
    from app.fetcher import fetch_fundamentals
    from app.valuation import compute_intrinsic_value

    price_by_ticker: dict[str, dict] = {p["ticker"]: p for p in prices}
    alerts_to_send = []

    for item in watchlist:
        ticker = item.get("ticker")
        alert_type = item.get("alert_type", "below")
        margin = item.get("margin_of_safety", 0.20)

        if not ticker:
            logger.warning("Item watchlist invalide : %s", item)
            continue

        price_data = price_by_ticker.get(ticker)
        if not price_data:
            logger.warning("Pas de cours disponible pour %s", ticker)
            continue

        current = price_data.get("close") or price_data.get("open")
        if current is None or current == 0:
            continue

        # --- Prix cible : manuel (override) ou calcule automatiquement ---
        target_override = item.get("target_override")
        if target_override:
            target = float(target_override)
            valuation = {"target_price": target, "fair_value": None,
                         "confidence": "manuelle", "signal": "—",
                         "methods": {}, "upside_to_fair": None}
            logger.info("%s : prix cible manuel force = %.2f", ticker, target)
        else:
            fundamentals = fetch_fundamentals(ticker)
            valuation = compute_intrinsic_value(fundamentals, current, margin)
            target = valuation.get("target_price")

        if target is None:
            logger.warning(
                "%s : impossible de calculer le prix cible (donnees insuffisantes), ignore.",
                ticker,
            )
            continue

        triggered = (alert_type == "below" and current < target) or \
                    (alert_type == "above" and current > target)

        logger.info(
            "Verif %s : cours=%.2f | cible=%.2f (fair=%.2f, conf=%s) | type=%s → %s",
            ticker, current, target,
            valuation.get("fair_value") or 0,
            valuation.get("confidence", "?"),
            alert_type,
            "ALERTE" if triggered else "pas declenche",
        )

        if not triggered:
            continue

        if alert_already_triggered_today(ticker):
            logger.info("Alerte pour %s deja declenchee aujourd'hui, ignoree.", ticker)
            continue

        distance = compute_distance_to_target(current, target)
        alert = {
            "ticker": ticker,
            "name": item.get("name", ticker),
            "current_price": current,
            "target_price": target,
            "fair_value": valuation.get("fair_value"),
            "valuation_methods": valuation.get("methods", {}),
            "valuation_confidence": valuation.get("confidence"),
            "upside_to_fair": valuation.get("upside_to_fair"),
            "margin_of_safety": margin,
            "alert_type": alert_type,
            "distance_pct": distance,
            "notes": item.get("notes", ""),
            "date": price_data.get("date"),
            "currency": price_data.get("currency", "EUR"),
        }
        alerts_to_send.append(alert)
        logger.info(
            "ALERTE : %s cours=%.2f cible=%.2f fair=%.2f distance=%.2f%%",
            ticker, current, target,
            valuation.get("fair_value") or 0, distance,
        )

    return alerts_to_send
