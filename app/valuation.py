"""
valuation.py — Calcul de la valeur intrinseque (strategie Warren Buffett / GARP).

Philosophie :
  Un bon investisseur n'achete pas une action a un prix fixe arbitraire.
  Il estime la valeur reelle de l'entreprise via les fondamentaux,
  puis applique une marge de securite pour absorber l'incertitude.

Methodes implementees :
  1. Graham Number        : sqrt(22.5 x EPS x BVPS) — plancher de valeur actifs
  2. Formule de croissance: EPS x (8.5 + 2g) — Ben Graham, croissance intégree
  3. DCF simplifie        : FCF actualise sur 10 ans + valeur terminale
  4. Consensus analystes  : objectif moyen Wall Street (signal de marche)

Prix cible = moyenne ponderee des methodes x (1 - marge_de_securite)
"""

import logging
from typing import Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constantes
# ---------------------------------------------------------------------------

DEFAULT_MARGIN_OF_SAFETY = 0.20  # 20% — minimum Buffett pour une entreprise de qualite
DISCOUNT_RATE = 0.09             # 9% — cout du capital (Buffett utilise 9-10%)
TERMINAL_GROWTH_RATE = 0.03      # 3% — croissance perpetuelle conservatrice
MAX_GROWTH_RATE = 0.15           # 15% — plafond croissance DCF (prudence)
MAX_GRAHAM_GROWTH = 20.0         # 20% — plafond formule Graham

# Poids de base par methode (normalises sur les methodes disponibles)
BASE_WEIGHTS = {
    "graham_number":  0.15,  # conservateur, base sur les actifs
    "graham_growth":  0.25,  # integre la croissance attendue
    "dcf":            0.30,  # methode roi (cash-flows actualises)
    "analyst":        0.30,  # sagesse collective du marche
}


# ---------------------------------------------------------------------------
# Methodes individuelles
# ---------------------------------------------------------------------------

def _graham_number(eps: float, bvps: float) -> Optional[float]:
    """
    Graham Number = sqrt(22.5 x EPS x BVPS).

    Represente le prix maximum qu'un investisseur value devrait payer
    pour une action dont les fondamentaux sont sains.
    Valide uniquement si EPS > 0 et BVPS > 0.
    """
    if eps and bvps and eps > 0 and bvps > 0:
        return (22.5 * eps * bvps) ** 0.5
    return None


def _graham_growth_formula(eps: float, growth_pct: float) -> Optional[float]:
    """
    Formule de croissance de Ben Graham :
      Valeur = EPS x (8.5 + 2 x taux_de_croissance_%)

    - 8.5 = P/E d'une action sans croissance
    - 2g  = prime de croissance
    - Le taux de croissance est plafonne a 20% (Buffett : mefiez-vous
      des entreprises qui promettent plus de 15-20% indefiniment).
    """
    if eps and eps > 0 and growth_pct is not None:
        g = min(max(growth_pct, 0.0), MAX_GRAHAM_GROWTH)
        val = eps * (8.5 + 2 * g)
        return val if val > 0 else None
    return None


def _dcf_simple(
    fcf_per_share: float,
    growth_rate: float,
    discount_rate: float = DISCOUNT_RATE,
    terminal_growth: float = TERMINAL_GROWTH_RATE,
    years: int = 10,
) -> Optional[float]:
    """
    DCF simplifie (Owner Earnings — approche Buffett) :
      - Projette les FCF sur `years` ans avec un taux de croissance
      - Actualise chaque flux au taux d'actualisation
      - Ajoute la valeur terminale (Gordon Growth Model)

    Le taux de croissance est plafonne a 15% pour rester conservateur.
    """
    if not fcf_per_share or fcf_per_share <= 0:
        return None
    if discount_rate <= terminal_growth:
        return None  # Gordon Growth Model instable

    g = min(max(growth_rate, 0.0), MAX_GROWTH_RATE)

    # Valeur actuelle des FCF sur `years` ans
    pv_fcf = 0.0
    fcf = fcf_per_share
    for year in range(1, years + 1):
        fcf *= (1 + g)
        pv_fcf += fcf / (1 + discount_rate) ** year

    # Valeur terminale (Gordon Growth Model)
    terminal_fcf = fcf * (1 + terminal_growth)
    terminal_value = terminal_fcf / (discount_rate - terminal_growth)
    pv_terminal = terminal_value / (1 + discount_rate) ** years

    total = pv_fcf + pv_terminal
    return total if total > 0 else None


# ---------------------------------------------------------------------------
# Agregateur principal
# ---------------------------------------------------------------------------

def compute_intrinsic_value(
    fundamentals: dict,
    current_price: float,
    margin_of_safety: float = DEFAULT_MARGIN_OF_SAFETY,
) -> dict:
    """
    Calcule la valeur intrinseque et le prix cible d'achat.

    Parametres :
      fundamentals    : dict issu de fetch_fundamentals() (yfinance info)
      current_price   : cours actuel de l'action
      margin_of_safety: decote appliquee sur la fair value (ex: 0.20 = 20%)

    Retourne :
      {
        target_price    : prix d'achat recommande (fair_value x (1 - marge)),
        fair_value      : valeur intrinseque estimee (moyenne ponderee),
        methods         : {graham_number, graham_growth, dcf, analyst} — valeurs calculees,
        weights         : poids effectivement utilises (normalises),
        upside_to_fair  : % d'upside depuis le cours actuel vers la fair value,
        upside_to_target: % d'upside depuis le cours actuel vers le prix cible,
        margin_of_safety: marge appliquee,
        confidence      : "elevee" / "moyenne" / "faible" selon nb de methodes,
        signal          : "ACHAT" si cours < prix_cible, "ATTENDRE" sinon,
      }
    """
    methods_values = {}
    weights_available = {}

    # --- Extraction des donnees fondamentales ---
    eps = fundamentals.get("trailing_eps") or fundamentals.get("forward_eps")
    bvps = fundamentals.get("book_value_per_share")
    fcf_total = fundamentals.get("free_cashflow")
    shares = fundamentals.get("shares_outstanding")
    analyst_target = fundamentals.get("analyst_target_mean")

    # Taux de croissance : earnings > revenue (plus direct)
    earnings_growth = fundamentals.get("earnings_growth")  # decimal ex: 0.12 = 12%
    revenue_growth = fundamentals.get("revenue_growth")    # decimal ex: 0.08 = 8%
    growth_dec = earnings_growth if earnings_growth is not None else (revenue_growth or 0.0)
    growth_pct = growth_dec * 100  # en pourcentage

    # --- 1. Graham Number ---
    gn = _graham_number(eps, bvps)
    if gn and gn > 0:
        methods_values["graham_number"] = round(gn, 2)
        weights_available["graham_number"] = BASE_WEIGHTS["graham_number"]
        logger.debug("Graham Number : %.2f (EPS=%.2f, BVPS=%.2f)", gn, eps or 0, bvps or 0)

    # --- 2. Formule de croissance Ben Graham ---
    gg = _graham_growth_formula(eps, growth_pct)
    if gg and gg > 0:
        methods_values["graham_growth"] = round(gg, 2)
        weights_available["graham_growth"] = BASE_WEIGHTS["graham_growth"]
        logger.debug(
            "Graham Growth : %.2f (EPS=%.2f, g=%.1f%%)", gg, eps or 0, growth_pct
        )

    # --- 3. DCF simplifie ---
    if fcf_total and shares and shares > 0:
        fcf_ps = fcf_total / shares
        dcf_val = _dcf_simple(fcf_ps, growth_dec)
        if dcf_val and dcf_val > 0:
            methods_values["dcf"] = round(dcf_val, 2)
            weights_available["dcf"] = BASE_WEIGHTS["dcf"]
            logger.debug(
                "DCF : %.2f (FCF/action=%.2f, g=%.1f%%)", dcf_val, fcf_ps, growth_pct
            )

    # --- 4. Consensus analystes ---
    if analyst_target and analyst_target > 0:
        methods_values["analyst"] = round(analyst_target, 2)
        weights_available["analyst"] = BASE_WEIGHTS["analyst"]
        logger.debug("Consensus analystes : %.2f", analyst_target)

    # --- Aucune donnee disponible ---
    if not methods_values:
        logger.warning(
            "Impossible de calculer la valeur intrinseque : donnees insuffisantes."
        )
        return {
            "target_price": None,
            "fair_value": None,
            "methods": {},
            "weights": {},
            "upside_to_fair": None,
            "upside_to_target": None,
            "margin_of_safety": margin_of_safety,
            "confidence": "insuffisante",
            "signal": "DONNEES MANQUANTES",
        }

    # --- Moyenne ponderee normalisee ---
    total_weight = sum(weights_available.values())
    fair_value = sum(
        methods_values[k] * weights_available[k] for k in methods_values
    ) / total_weight

    # --- Prix cible = fair value x (1 - marge de securite) ---
    target_price = fair_value * (1 - margin_of_safety)

    # --- Upside ---
    upside_to_fair = None
    upside_to_target = None
    if current_price and current_price > 0:
        upside_to_fair = round((fair_value - current_price) / current_price * 100, 1)
        upside_to_target = round((target_price - current_price) / current_price * 100, 1)

    # --- Confiance selon nombre de methodes ---
    n = len(methods_values)
    confidence = "elevee" if n >= 3 else ("moyenne" if n == 2 else "faible")

    # --- Signal d'achat ---
    signal = "ACHAT" if (current_price and current_price < target_price) else "ATTENDRE"

    # Poids effectifs (normalises pour affichage)
    weights_display = {
        k: round(weights_available[k] / total_weight * 100, 1)
        for k in weights_available
    }

    logger.info(
        "Valorisation : fair_value=%.2f | target=%.2f (marge=%.0f%%) | "
        "upside_fair=%.1f%% | confiance=%s | signal=%s",
        fair_value, target_price, margin_of_safety * 100,
        upside_to_fair or 0, confidence, signal,
    )

    return {
        "target_price": round(target_price, 2),
        "fair_value": round(fair_value, 2),
        "methods": methods_values,
        "weights": weights_display,
        "upside_to_fair": upside_to_fair,
        "upside_to_target": upside_to_target,
        "margin_of_safety": margin_of_safety,
        "confidence": confidence,
        "signal": signal,
    }
