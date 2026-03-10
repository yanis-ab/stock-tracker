"""
streamlit_app.py — Dashboard web pour Stock Monitor (strategie GARP / Buffett).
Lancer avec : streamlit run dashboard/streamlit_app.py
"""

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import yaml
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import streamlit as st


def _inject_streamlit_secrets() -> None:
    try:
        secrets = st.secrets
        for key in ["DATABASE_URL", "EMAIL_SENDER", "EMAIL_PASSWORD",
                    "EMAIL_RECIPIENT", "TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID"]:
            if key in secrets and not os.environ.get(key):
                os.environ[key] = secrets[key]
    except Exception:
        pass


_inject_streamlit_secrets()

from app.database import init_db, get_all_latest_prices, get_price_history, get_all_alerts
from app.analyzer import compute_distance_to_target, compute_conviction_score
from app.fetcher import fetch_technicals, fetch_analyst_data, fetch_fundamentals
from app.valuation import compute_intrinsic_value

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

_BASE_DIR = Path(__file__).resolve().parent.parent
_CONFIG_PATH = _BASE_DIR / "config.yaml"

SUGGESTIONS = [
    {"ticker": "ASML.AS",  "name": "ASML",              "sector": "Semi-conducteurs",
     "thesis": "Monopole absolu sur les machines EUV, demande IA structurelle",
     "risk": "medium",
     "why_now": "Correction depuis pic 2024, valorisation plus raisonnable"},
    {"ticker": "STMPA.PA", "name": "STMicroelectronics", "sector": "Semi-conducteurs",
     "thesis": "Rebond de cycle, partenariat stratégique, SiC automobile",
     "risk": "high",
     "why_now": "Point bas de cycle, catalyseurs multiples en 2025-2026"},
    {"ticker": "AIR.PA",   "name": "Airbus",             "sector": "Aeronautique",
     "thesis": "Carnet de commandes record, duopole mondial avec Boeing",
     "risk": "low",
     "why_now": "Visibilite sur 10 ans, montee en cadence A320neo"},
    {"ticker": "SAF.PA",   "name": "Safran",             "sector": "Aeronautique",
     "thesis": "Moteurs LEAP, dividende croissant, MRO tres rentable",
     "risk": "low",
     "why_now": "Profite de la reprise du trafic aerien mondial"},
    {"ticker": "DSY.PA",   "name": "Dassault Systemes",  "sector": "Logiciels industriels",
     "thesis": "CATIA / 3DEXPERIENCE, sous-valorise apres correction 2024-2025",
     "risk": "medium",
     "why_now": "Retour a la croissance attendu en 2026"},
    {"ticker": "OR.PA",    "name": "L'Oreal",            "sector": "Luxe / Beaute",
     "thesis": "Leader mondial beaute, defensif, pricing power exceptionnel",
     "risk": "low",
     "why_now": "Correction possible sur exposition Asie / Chine"},
    {"ticker": "MC.PA",    "name": "LVMH",               "sector": "Luxe",
     "thesis": "Conglomerat luxe diversifie, rebond Chine attendu",
     "risk": "medium",
     "why_now": "Valorisation plus raisonnable post-correction 2024"},
    {"ticker": "BNP.PA",   "name": "BNP Paribas",        "sector": "Banque",
     "thesis": "Dividende genereux, beneficie des taux eleves europeens",
     "risk": "medium",
     "why_now": "PER bas, dividende >7%, solide bilan en Europe"},
    {"ticker": "TTE.PA",   "name": "TotalEnergies",      "sector": "Energie",
     "thesis": "Transition energetique + dividende solide + GNL mondial",
     "risk": "medium",
     "why_now": "Cash-flow solide meme a 70$/baril, rachat d'actions actif"},
    {"ticker": "DG.PA",    "name": "Dassault Aviation",  "sector": "Defense",
     "thesis": "Budgets defense europeens en forte hausse, carnet plein",
     "risk": "low",
     "why_now": "Contexte geopolitique structurellement favorable"},
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def load_config() -> dict:
    with open(_CONFIG_PATH, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def save_config(config: dict) -> None:
    with open(_CONFIG_PATH, "w", encoding="utf-8") as f:
        yaml.dump(config, f, allow_unicode=True, default_flow_style=False, sort_keys=False)


@st.cache_data(ttl=3600, show_spinner=False)
def _fetch_technicals_cached(ticker: str) -> dict:
    return fetch_technicals(ticker)


@st.cache_data(ttl=3600, show_spinner=False)
def _fetch_analyst_cached(ticker: str) -> dict:
    return fetch_analyst_data(ticker)


@st.cache_data(ttl=3600, show_spinner=False)
def _fetch_fundamentals_cached(ticker: str) -> dict:
    return fetch_fundamentals(ticker)


def _compute_valuation_cached(ticker: str, current: float, margin: float) -> dict:
    """Calcule la valorisation (pas mis en cache car depend du cours)."""
    fundamentals = _fetch_fundamentals_cached(ticker)
    return compute_intrinsic_value(fundamentals, current, margin)


def _score_color(score: int) -> str:
    return {5: "#27ae60", 4: "#27ae60", 3: "#2980b9",
            2: "#e67e22", 1: "#e74c3c", 0: "#95a5a6"}.get(score, "#95a5a6")


def _confidence_color(conf: str) -> str:
    return {"elevee": "#27ae60", "moyenne": "#e67e22",
            "faible": "#e74c3c", "manuelle": "#8e44ad",
            "insuffisante": "#95a5a6"}.get(conf or "", "#95a5a6")


def _signal_color(signal: str) -> str:
    return "#27ae60" if signal == "ACHAT" else "#e67e22"


def _score_stars(score: int) -> str:
    return "●" * score + "○" * (5 - score)


# ---------------------------------------------------------------------------
# Page : Vue d'ensemble
# ---------------------------------------------------------------------------

def page_overview(config: dict) -> None:
    st.title("Vue d'ensemble")

    watchlist = config.get("watchlist", [])
    if not watchlist:
        st.warning("Watchlist vide. Ajoutez des actions dans **Watchlist & Config**.")
        return

    tickers = [item["ticker"] for item in watchlist]
    prices_db = {p["ticker"]: p for p in get_all_latest_prices(tickers)}

    st.caption(
        "Valorisation calculee via Graham Number, Ben Graham Growth, DCF simplifie "
        "et consensus analystes. Indicateurs mis en cache 1h."
    )

    stock_data = []
    progress = st.progress(0, text="Chargement des valorisations...")
    for i, item in enumerate(watchlist):
        ticker = item["ticker"]
        margin = item.get("margin_of_safety", 0.20)
        alert_type = item.get("alert_type", "below")

        price_data = prices_db.get(ticker)
        current = price_data["close_price"] if price_data else None

        tech = _fetch_technicals_cached(ticker)
        analyst = _fetch_analyst_cached(ticker)

        # Prix cible : override manuel ou calcule automatiquement
        target_override = item.get("target_override")
        if target_override:
            valuation = {
                "target_price": float(target_override),
                "fair_value": None,
                "methods": {},
                "weights": {},
                "upside_to_fair": None,
                "upside_to_target": None,
                "margin_of_safety": margin,
                "confidence": "manuelle",
                "signal": "ACHAT" if (current and current < float(target_override)) else "ATTENDRE",
            }
        elif current:
            valuation = _compute_valuation_cached(ticker, current, margin)
        else:
            valuation = {"target_price": None, "fair_value": None, "confidence": "insuffisante",
                         "signal": "DONNEES MANQUANTES", "methods": {}, "upside_to_fair": None}

        target = valuation.get("target_price")

        conviction = None
        if current and target:
            conviction = compute_conviction_score(current, target, alert_type, tech, analyst)

        stock_data.append({
            "item": item, "current": current, "target": target,
            "valuation": valuation, "alert_type": alert_type,
            "tech": tech, "analyst": analyst, "conviction": conviction,
        })
        progress.progress((i + 1) / len(watchlist), text=f"Analyse {ticker}...")

    progress.empty()
    stock_data.sort(
        key=lambda x: x["conviction"]["score"] if x["conviction"] else -1,
        reverse=True,
    )

    # --- Tableau de synthese ---
    st.subheader("Tableau de synthese")
    rows = []
    for d in stock_data:
        ticker = d["item"]["ticker"]
        current = d["current"]
        val = d["valuation"]
        target = val.get("target_price")
        fair = val.get("fair_value")
        tech = d["tech"]
        analyst = d["analyst"]
        conviction = d["conviction"]

        upside_fair = val.get("upside_to_fair")
        rsi = tech.get("rsi")
        vs_ma200 = tech.get("pct_from_ma200")
        conf = val.get("confidence", "—")
        signal = val.get("signal", "—")

        rows.append({
            "Action":         f"{d['item'].get('name', ticker)} ({ticker})",
            "Cours":          f"{current:.2f}" if current else "—",
            "Fair Value":     f"{fair:.2f}" if fair else "—",
            "Cible achat":    f"{target:.2f}" if target else "—",
            "Upside/FV":      f"{upside_fair:+.1f}%" if upside_fair is not None else "—",
            "Confiance":      conf,
            "Signal":         signal,
            "RSI":            f"{rsi:.0f}" if rsi else "—",
            "vs MA200":       f"{vs_ma200:+.1f}%" if vs_ma200 is not None else "—",
            "Score /5":       conviction["score"] if conviction else "—",
            "Zone":           conviction["label"] if conviction else "—",
        })

    df = pd.DataFrame(rows)

    def color_score(val):
        try:
            return f"color: {_score_color(int(val))}; font-weight: bold;"
        except Exception:
            return ""

    def color_signal(val):
        return (f"color: {_signal_color(val)}; font-weight: bold;"
                if val in ("ACHAT", "ATTENDRE") else "")

    def color_zone(val):
        m = {
            "Zone d'achat forte": "color: #27ae60; font-weight: bold;",
            "Zone interessante":  "color: #2980b9; font-weight: bold;",
            "A surveiller":       "color: #e67e22;",
            "Attendre":           "color: #95a5a6;",
        }
        return m.get(val, "")

    styled = (df.style
              .map(color_score, subset=["Score /5"])
              .map(color_signal, subset=["Signal"])
              .map(color_zone, subset=["Zone"]))
    st.dataframe(styled, use_container_width=True, hide_index=True)

    # --- Detail par action ---
    st.subheader("Detail par action")
    ticker_labels = [
        f"{d['item'].get('name', d['item']['ticker'])} ({d['item']['ticker']})"
        for d in stock_data
    ]
    selected_label = st.selectbox("Voir le detail de :", ticker_labels)
    selected_idx = ticker_labels.index(selected_label)
    d = stock_data[selected_idx]
    conviction = d["conviction"]
    analyst = d["analyst"]
    tech = d["tech"]
    val = d["valuation"]

    # --- Score de conviction ---
    if conviction:
        col_score, col_val, col_fund = st.columns([1, 1, 2])

        with col_score:
            st.markdown(
                f"<div style='background:{conviction['color']};color:white;padding:16px;"
                f"border-radius:8px;text-align:center;'>"
                f"<div style='font-size:36px;font-weight:bold;'>{conviction['score']}/5</div>"
                f"<div style='font-size:14px;margin-top:4px;'>{conviction['label']}</div>"
                f"<div style='font-size:20px;margin-top:8px;letter-spacing:4px;'>"
                f"{_score_stars(conviction['score'])}</div>"
                f"</div>",
                unsafe_allow_html=True,
            )
            st.markdown("")
            st.markdown("**Les 5 criteres GARP :**")
            for criterion in conviction["criteria"]:
                icon = "✅" if criterion["ok"] else "❌"
                st.markdown(f"{icon} {criterion['label']}")

        # --- Valorisation ---
        with col_val:
            current = d["current"]
            fair = val.get("fair_value")
            target = val.get("target_price")
            conf = val.get("confidence", "—")
            signal = val.get("signal", "—")
            margin_pct = int(val.get("margin_of_safety", 0.20) * 100)
            conf_color = _confidence_color(conf)
            sig_color = _signal_color(signal)

            st.markdown(
                f"<div style='border:1px solid #ddd;border-radius:8px;padding:14px;'>"
                f"<div style='font-size:13px;color:#666;margin-bottom:8px;'>VALORISATION INTRINSEQUE</div>"
                f"<div style='font-size:22px;font-weight:bold;'>{fair:.2f} €</div>"
                f"<div style='font-size:12px;color:#666;'>fair value estimee</div>"
                f"<hr style='margin:8px 0;'/>"
                f"<div style='font-size:18px;font-weight:bold;color:#8e44ad;'>{target:.2f} €</div>"
                f"<div style='font-size:12px;color:#666;'>prix cible (−{margin_pct}% marge securite)</div>"
                f"<hr style='margin:8px 0;'/>"
                f"<span style='background:{sig_color};color:white;padding:3px 10px;"
                f"border-radius:4px;font-weight:bold;font-size:14px;'>{signal}</span>"
                f"&nbsp;&nbsp;"
                f"<span style='color:{conf_color};font-size:13px;'>confiance : {conf}</span>"
                f"</div>",
                unsafe_allow_html=True,
            ) if fair and target else st.info("Donnees insuffisantes pour valoriser cette action.")

            # Methodes utilisees
            methods = val.get("methods", {})
            weights = val.get("weights", {})
            if methods:
                st.markdown("")
                st.markdown("**Methodes de valorisation :**")
                method_labels = {
                    "graham_number": "Graham Number",
                    "graham_growth": "Graham Growth",
                    "dcf":           "DCF simplifie",
                    "analyst":       "Consensus analystes",
                }
                for k, v in methods.items():
                    w = weights.get(k, 0)
                    label = method_labels.get(k, k)
                    st.markdown(
                        f"<div style='display:flex;justify-content:space-between;"
                        f"font-size:13px;margin:2px 0;'>"
                        f"<span>📐 {label}</span>"
                        f"<span style='font-weight:bold;'>{v:.2f} €"
                        f"<span style='color:#999;font-weight:normal;'> ({w:.0f}%)</span></span>"
                        f"</div>",
                        unsafe_allow_html=True,
                    )

        # --- Fondamentaux & technique ---
        with col_fund:
            st.markdown("**Analystes Wall Street**")
            c1, c2, c3 = st.columns(3)
            c1.metric("Objectif moyen",
                      f"{analyst.get('target_mean'):.2f}" if analyst.get("target_mean") else "—")
            c2.metric("Upside",
                      f"{analyst.get('upside_pct'):+.1f}%" if analyst.get("upside_pct") is not None else "—")
            c3.metric("Nb analystes", analyst.get("nb_analysts") or "—")

            c4, c5 = st.columns(2)
            c4.metric("Fourchette",
                      f"{analyst.get('target_low'):.0f} – {analyst.get('target_high'):.0f}"
                      if analyst.get("target_low") and analyst.get("target_high") else "—")
            c5.metric("Consensus",
                      (analyst.get("recommendation") or "—").replace("_", " ").title())

            st.markdown("**Fondamentaux**")
            c6, c7, c8, c9 = st.columns(4)
            c6.metric("P/E",        analyst.get("pe_ratio") or "—")
            c7.metric("ROE",        f"{analyst.get('roe'):.1f}%" if analyst.get("roe") else "—")
            c8.metric("Marge nette",
                      f"{analyst.get('profit_margin'):.1f}%" if analyst.get("profit_margin") else "—")
            c9.metric("Croiss. CA",
                      f"{analyst.get('revenue_growth'):+.1f}%" if analyst.get("revenue_growth") is not None else "—")

            st.markdown("**Technique**")
            c10, c11, c12, c13 = st.columns(4)
            rsi = tech.get("rsi")
            c10.metric("RSI 14j", f"{rsi:.0f}" if rsi else "—",
                       delta="survendu" if rsi and rsi < 35 else ("surachat" if rsi and rsi > 70 else None))
            c11.metric("MA50",  f"{tech.get('ma50'):.0f}" if tech.get("ma50") else "—")
            c12.metric("MA200", f"{tech.get('ma200'):.0f}" if tech.get("ma200") else "—",
                       delta=f"{tech.get('pct_from_ma200'):+.1f}%"
                       if tech.get("pct_from_ma200") is not None else None)
            c13.metric("52w range",
                       f"{tech.get('week52_low'):.0f}–{tech.get('week52_high'):.0f}"
                       if tech.get("week52_low") and tech.get("week52_high") else "—")

    if d["item"].get("notes"):
        st.info(f"**These d'investissement :** {d['item']['notes']}")


# ---------------------------------------------------------------------------
# Page : Historique
# ---------------------------------------------------------------------------

def page_history(config: dict) -> None:
    st.title("Historique d'une action")

    watchlist = config.get("watchlist", [])
    if not watchlist:
        st.warning("Watchlist vide.")
        return

    ticker_options = [f"{item['ticker']} — {item['name']}" for item in watchlist]
    selected = st.selectbox("Choisir une action", ticker_options)
    idx = ticker_options.index(selected)
    item = watchlist[idx]
    ticker = item["ticker"]
    alert_type = item.get("alert_type", "below")
    margin = item.get("margin_of_safety", 0.20)

    period_labels = {"1M": 30, "3M": 90, "6M": 180, "1A": 365, "MAX": 9999}
    period_selected = st.radio("Periode", list(period_labels.keys()), horizontal=True)
    limit = period_labels[period_selected]

    history = get_price_history(ticker, limit=limit)
    if not history:
        st.info("Pas encore de donnees pour cette action. Lancez une verification.")
        return

    df = pd.DataFrame(history).sort_values("date")
    df["date"] = pd.to_datetime(df["date"])
    closes = df["close_price"]

    # MA50 / MA200
    df["ma50"]  = closes.rolling(50).mean()
    df["ma200"] = closes.rolling(200).mean()

    # RSI 14j
    delta = closes.diff()
    gain = delta.clip(lower=0).rolling(14).mean()
    loss = (-delta.clip(upper=0)).rolling(14).mean()
    rs = gain / loss.replace(0, float("inf"))
    df["rsi"] = 100 - (100 / (1 + rs))

    # Prix cible calcule
    current_price = float(closes.iloc[-1])
    target_override = item.get("target_override")
    if target_override:
        target = float(target_override)
        fair_value = None
        conf = "manuelle"
    else:
        val = _compute_valuation_cached(ticker, current_price, margin)
        target = val.get("target_price")
        fair_value = val.get("fair_value")
        conf = val.get("confidence", "—")

    # --- Graphique ---
    fig = make_subplots(
        rows=2, cols=1,
        shared_xaxes=True,
        row_heights=[0.72, 0.28],
        vertical_spacing=0.04,
        subplot_titles=[f"{item['name']} ({ticker})", "RSI 14j"],
    )

    fig.add_trace(go.Scatter(
        x=df["date"], y=df["close_price"],
        mode="lines", name="Cours",
        line={"color": "#2980b9", "width": 2},
        hovertemplate="<b>%{x|%d/%m/%Y}</b><br>Cloture : %{y:.2f}<extra></extra>",
    ), row=1, col=1)

    if df["ma50"].notna().any():
        fig.add_trace(go.Scatter(
            x=df["date"], y=df["ma50"],
            mode="lines", name="MA50",
            line={"color": "#e67e22", "width": 1.5, "dash": "dot"},
            hovertemplate="MA50 : %{y:.2f}<extra></extra>",
        ), row=1, col=1)

    if df["ma200"].notna().any():
        fig.add_trace(go.Scatter(
            x=df["date"], y=df["ma200"],
            mode="lines", name="MA200",
            line={"color": "#c0392b", "width": 1.5, "dash": "dash"},
            hovertemplate="MA200 : %{y:.2f}<extra></extra>",
        ), row=1, col=1)

    # Fair value
    if fair_value:
        fig.add_hline(
            y=fair_value, line_dash="dot", line_color="#27ae60", line_width=1.5,
            annotation_text=f"Fair value : {fair_value:.2f}",
            annotation_position="bottom right",
            row=1, col=1,
        )

    # Prix cible (avec marge de securite)
    if target:
        fig.add_hline(
            y=target, line_dash="dot", line_color="#8e44ad", line_width=2,
            annotation_text=f"Cible achat (−{int(margin*100)}%) : {target:.2f} [{conf}]",
            annotation_position="top right",
            row=1, col=1,
        )
        if alert_type == "below":
            fig.add_hrect(
                y0=float(closes.min()) * 0.98, y1=target,
                fillcolor="rgba(39,174,96,0.08)", line_width=0,
                annotation_text="Zone d'opportunite",
                annotation_position="top left",
                row=1, col=1,
            )

    # RSI
    fig.add_trace(go.Scatter(
        x=df["date"], y=df["rsi"],
        mode="lines", name="RSI",
        line={"color": "#8e44ad", "width": 1.5},
        hovertemplate="RSI : %{y:.1f}<extra></extra>",
        showlegend=False,
    ), row=2, col=1)

    fig.add_hrect(y0=70, y1=100, fillcolor="rgba(192,57,43,0.08)",  line_width=0, row=2, col=1)
    fig.add_hrect(y0=0,  y1=30,  fillcolor="rgba(39,174,96,0.08)",  line_width=0, row=2, col=1)
    fig.add_hline(y=70,  line_dash="dot", line_color="#c0392b", line_width=1, row=2, col=1)
    fig.add_hline(y=30,  line_dash="dot", line_color="#27ae60", line_width=1, row=2, col=1)

    fig.update_layout(
        hovermode="x unified",
        template="plotly_white",
        height=600,
        legend={"orientation": "h", "y": 1.02},
        margin={"t": 60},
    )
    fig.update_yaxes(title_text="Cours (EUR)", row=1, col=1)
    fig.update_yaxes(title_text="RSI", range=[0, 100], row=2, col=1)

    st.plotly_chart(fig, use_container_width=True)

    with st.expander("Donnees brutes OHLCV"):
        display_df = df[["date", "open_price", "close_price",
                          "high_price", "low_price", "volume"]].copy()
        display_df.columns = ["Date", "Ouverture", "Cloture", "Haut", "Bas", "Volume"]
        st.dataframe(display_df.sort_values("Date", ascending=False), hide_index=True)


# ---------------------------------------------------------------------------
# Page : Alertes
# ---------------------------------------------------------------------------

def page_alerts() -> None:
    st.title("Historique des alertes")

    alerts = get_all_alerts(limit=200)
    if not alerts:
        st.info("Aucune alerte declenchee pour le moment.")
        return

    df = pd.DataFrame(alerts)
    df["triggered_at"] = pd.to_datetime(df["triggered_at"]).dt.strftime("%d/%m/%Y %H:%M")
    df = df.rename(columns={
        "ticker": "Ticker", "triggered_at": "Date", "current_price": "Cours",
        "target_price": "Cible", "alert_type": "Type",
        "notification_sent": "Notifie", "channel": "Canal",
    })
    st.dataframe(
        df[["Ticker", "Date", "Cours", "Cible", "Type", "Canal", "Notifie"]],
        use_container_width=True, hide_index=True,
    )


# ---------------------------------------------------------------------------
# Page : Watchlist & Config
# ---------------------------------------------------------------------------

def page_watchlist_config(config: dict) -> None:
    st.title("Watchlist & Configuration")

    watchlist = config.get("watchlist", [])
    st.subheader("Actions surveillees")

    to_remove = []
    for i, item in enumerate(watchlist):
        with st.expander(f"{item['ticker']} — {item.get('name', '')}"):
            col1, col2 = st.columns(2)
            with col1:
                new_name = st.text_input("Nom", value=item.get("name", ""), key=f"name_{i}")
                new_type = st.selectbox(
                    "Type d'alerte", ["below", "above"],
                    index=0 if item.get("alert_type") == "below" else 1,
                    key=f"type_{i}",
                )
            with col2:
                new_margin = st.slider(
                    "Marge de securite",
                    min_value=0.05, max_value=0.50, step=0.05,
                    value=float(item.get("margin_of_safety", 0.20)),
                    format="%.0f%%",
                    key=f"margin_{i}",
                    help="Decote appliquee sur la valeur intrinseque pour obtenir le prix d'achat ideal (Buffett : 20-25%)",
                )
                new_override = st.number_input(
                    "Prix cible manuel (optionnel — 0 = calcul auto)",
                    min_value=0.0,
                    value=float(item.get("target_override") or 0.0),
                    key=f"override_{i}",
                    help="Laissez a 0 pour utiliser le calcul automatique",
                )
            new_notes = st.text_input(
                "These d'investissement", value=item.get("notes", "") or "", key=f"notes_{i}"
            )
            col_save, col_del = st.columns(2)
            with col_save:
                if st.button("Sauvegarder", key=f"save_{i}"):
                    watchlist[i].update({
                        "name": new_name,
                        "alert_type": new_type,
                        "margin_of_safety": round(new_margin, 2),
                        "target_override": new_override if new_override > 0 else None,
                        "notes": new_notes,
                    })
                    save_config(config)
                    st.cache_data.clear()
                    st.success("Sauvegarde!")
            with col_del:
                if st.button("Supprimer", key=f"del_{i}", type="secondary"):
                    to_remove.append(i)

    if to_remove:
        config["watchlist"] = [item for j, item in enumerate(watchlist) if j not in to_remove]
        save_config(config)
        st.rerun()

    st.subheader("Ajouter une action")
    with st.form("add_stock"):
        col1, col2 = st.columns(2)
        with col1:
            new_ticker  = st.text_input("Ticker Yahoo Finance (ex: AIR.PA)")
            new_name    = st.text_input("Nom (ex: Airbus)")
        with col2:
            new_margin  = st.slider("Marge de securite", 0.05, 0.50, 0.20, 0.05, format="%.0f%%")
            new_type    = st.selectbox("Type d'alerte", ["below", "above"])
        new_override = st.number_input(
            "Prix cible manuel (optionnel — 0 = calcul auto)", min_value=0.0, value=0.0
        )
        new_notes = st.text_input("These / Notes (optionnel)")
        if st.form_submit_button("Ajouter") and new_ticker:
            config["watchlist"].append({
                "ticker":            new_ticker.strip().upper(),
                "name":              new_name.strip(),
                "alert_type":        new_type,
                "margin_of_safety":  round(new_margin, 2),
                "target_override":   new_override if new_override > 0 else None,
                "notes":             new_notes.strip(),
            })
            save_config(config)
            st.success(f"{new_ticker.strip().upper()} ajoutee!")
            st.rerun()

    st.subheader("Notifications")
    with st.expander("Email (Gmail)"):
        e = config.get("email", {})
        enabled  = st.checkbox("Activer", value=e.get("enabled", False))
        sender   = st.text_input("Expediteur", value=e.get("sender", ""))
        password = st.text_input("Mot de passe d'application", value=e.get("password", ""), type="password")
        recipient = st.text_input("Destinataire", value=e.get("recipient", ""))
        if st.button("Sauvegarder config email"):
            config["email"] = {
                "enabled": enabled, "sender": sender, "password": password,
                "recipient": recipient,
                "smtp_host": e.get("smtp_host", "smtp.gmail.com"),
                "smtp_port": e.get("smtp_port", 587),
            }
            save_config(config)
            st.success("Sauvegarde!")

    with st.expander("Telegram"):
        t = config.get("telegram", {})
        tg_enabled = st.checkbox("Activer Telegram", value=t.get("enabled", False))
        bot_token  = st.text_input("Token du bot", value=t.get("bot_token", ""), type="password")
        chat_id    = st.text_input("Chat ID", value=t.get("chat_id", ""))
        if st.button("Sauvegarder config Telegram"):
            config["telegram"] = {"enabled": tg_enabled, "bot_token": bot_token, "chat_id": chat_id}
            save_config(config)
            st.success("Sauvegarde!")

    st.subheader("Planification")
    s = config.get("schedule", {})
    sched_time = st.text_input("Heure du check (HH:MM)", value=s.get("time", "09:00"))
    sched_tz   = st.text_input("Fuseau horaire", value=s.get("timezone", "Europe/Paris"))
    if st.button("Sauvegarder planification"):
        config["schedule"] = {"time": sched_time, "timezone": sched_tz}
        save_config(config)
        st.success("Sauvegarde! Redemarrez pour appliquer.")


# ---------------------------------------------------------------------------
# Page : Suggestions
# ---------------------------------------------------------------------------

def page_suggestions(config: dict) -> None:
    st.title("Suggestions PEA")
    st.markdown(
        "Actions europeennes eligibles PEA — these d'investissement long terme (GARP / Buffett). "
        "Ajoutez-les a votre watchlist pour calculer automatiquement leur valeur intrinseque."
    )

    watchlist_tickers = {item["ticker"] for item in config.get("watchlist", [])}
    risk_colors = {"low": "#27ae60", "medium": "#e67e22", "high": "#c0392b"}
    risk_labels = {"low": "Risque faible", "medium": "Risque moyen", "high": "Risque eleve"}

    for suggestion in SUGGESTIONS:
        already_in = suggestion["ticker"] in watchlist_tickers
        col1, col2 = st.columns([4, 1])
        with col1:
            rc = risk_colors.get(suggestion["risk"], "#999")
            rl = risk_labels.get(suggestion["risk"], suggestion["risk"])
            st.markdown(
                f"**{suggestion['name']}** ({suggestion['ticker']}) &nbsp;"
                f"<span style='background:{rc};color:white;padding:2px 8px;"
                f"border-radius:4px;font-size:12px;'>{rl}</span> &nbsp;"
                f"*{suggestion['sector']}*",
                unsafe_allow_html=True,
            )
            st.markdown(f"**These :** {suggestion['thesis']}")
            st.markdown(f"**Pourquoi maintenant :** {suggestion['why_now']}")
        with col2:
            if already_in:
                st.markdown("✓ Dans la watchlist")
            elif st.button("Ajouter", key=f"add_{suggestion['ticker']}"):
                config["watchlist"].append({
                    "ticker":           suggestion["ticker"],
                    "name":             suggestion["name"],
                    "alert_type":       "below",
                    "margin_of_safety": 0.20,
                    "notes":            suggestion["thesis"],
                })
                save_config(config)
                st.success(f"{suggestion['name']} ajoutee!")
                st.rerun()
        st.divider()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    st.set_page_config(page_title="Stock Monitor", page_icon="📈", layout="wide")

    init_db()
    config = load_config()

    with st.sidebar:
        st.title("📈 Stock Monitor")
        st.markdown("---")
        page = st.radio("Navigation", [
            "Vue d'ensemble", "Historique", "Alertes", "Watchlist & Config", "Suggestions",
        ], label_visibility="collapsed")
        st.markdown("---")
        if st.button("Lancer une verification", type="primary"):
            with st.spinner("Verification en cours..."):
                from app.scheduler import run_daily_check
                run_daily_check()
            st.cache_data.clear()
            st.success("Verification terminee!")
        st.caption("Valorisation et indicateurs mis en cache 1h.")

    if page == "Vue d'ensemble":
        page_overview(config)
    elif page == "Historique":
        page_history(config)
    elif page == "Alertes":
        page_alerts()
    elif page == "Watchlist & Config":
        page_watchlist_config(config)
    elif page == "Suggestions":
        page_suggestions(config)


if __name__ == "__main__":
    main()
