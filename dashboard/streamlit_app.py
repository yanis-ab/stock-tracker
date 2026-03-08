"""
streamlit_app.py — Dashboard web local pour Stock Monitor.
Lancer avec : streamlit run dashboard/streamlit_app.py
"""

import os
import sys
from pathlib import Path

# Assurer que le projet est dans le path Python
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import yaml
import pandas as pd
import plotly.graph_objects as go
import streamlit as st


def _inject_streamlit_secrets() -> None:
    """
    Sur Streamlit Community Cloud, injecte les secrets dans les variables
    d'environnement pour que database.py et scheduler.py puissent les lire.
    """
    try:
        secrets = st.secrets
        for key in ["DATABASE_URL", "EMAIL_SENDER", "EMAIL_PASSWORD",
                    "EMAIL_RECIPIENT", "TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID"]:
            if key in secrets and not os.environ.get(key):
                os.environ[key] = secrets[key]
    except Exception:
        pass  # Pas de secrets configures, mode local


_inject_streamlit_secrets()

from app.database import (
    init_db, get_all_latest_prices, get_price_history, get_all_alerts,
    save_alert,
)
from app.analyzer import compute_distance_to_target

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

_BASE_DIR = Path(__file__).resolve().parent.parent
_CONFIG_PATH = _BASE_DIR / "config.yaml"

SUGGESTIONS = [
    {
        "ticker": "ASML.AS", "name": "ASML", "sector": "Semi-conducteurs",
        "thesis": "Monopole absolu sur les machines EUV, demande IA structurelle",
        "risk": "medium", "watch_price": 750.0,
        "why_now": "Correction depuis pic 2024, valorisation raisonnable",
    },
    {
        "ticker": "STM.MI", "name": "STMicroelectronics", "sector": "Semi-conducteurs",
        "thesis": "Rebond de cycle, partenariat AWS, SiC automobile",
        "risk": "high", "watch_price": 22.0,
        "why_now": "Point bas de cycle, catalyseurs multiples en 2025-2026",
    },
    {
        "ticker": "AIR.PA", "name": "Airbus", "sector": "Aeronautique",
        "thesis": "Carnet de commandes record, duopole mondial",
        "risk": "low", "watch_price": 155.0,
        "why_now": "Visibilite sur 10 ans, montee en cadence A320",
    },
    {
        "ticker": "SAF.PA", "name": "Safran", "sector": "Aeronautique",
        "thesis": "Moteurs LEAP, dividende croissant, MRO",
        "risk": "low", "watch_price": 200.0,
        "why_now": "Profite de la reprise du trafic aerien mondial",
    },
    {
        "ticker": "DSY.PA", "name": "Dassault Systemes", "sector": "Logiciels industriels",
        "thesis": "CATIA/3DEXPERIENCE, sous-valorise apres -29% en 2025",
        "risk": "medium", "watch_price": 28.0,
        "why_now": "Retour a la croissance attendu en 2026",
    },
    {
        "ticker": "OR.PA", "name": "L'Oreal", "sector": "Luxe / Beaute",
        "thesis": "Leader mondial beaute, defensif, pricing power",
        "risk": "low", "watch_price": 350.0,
        "why_now": "Correction possible sur exposition Chine",
    },
    {
        "ticker": "MC.PA", "name": "LVMH", "sector": "Luxe",
        "thesis": "Conglomerat luxe diversifie, rebond Chine attendu",
        "risk": "medium", "watch_price": 600.0,
        "why_now": "Valorisation plus raisonnable post-correction 2024",
    },
    {
        "ticker": "BNP.PA", "name": "BNP Paribas", "sector": "Banque",
        "thesis": "Dividende genereux, beneficie des taux eleves",
        "risk": "medium", "watch_price": 65.0,
        "why_now": "PER bas, dividende >7%, solide en Europe",
    },
    {
        "ticker": "TTE.PA", "name": "TotalEnergies", "sector": "Energie",
        "thesis": "Transition + dividende solide + GNL",
        "risk": "medium", "watch_price": 58.0,
        "why_now": "Cash-flow solide, rachat d'actions actif",
    },
    {
        "ticker": "DG.PA", "name": "Safran Defence (Dassault Aviation)", "sector": "Defense",
        "thesis": "Budgets defense europeens en hausse, carnet plein",
        "risk": "low", "watch_price": 220.0,
        "why_now": "Contexte geopolitique favorable sur le long terme",
    },
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


def status_badge(distance_pct: float, alert_type: str) -> str:
    if alert_type == "below":
        if distance_pct < 0:
            return "ALERTE"
        elif distance_pct < 5:
            return "Proche"
        else:
            return "OK"
    else:  # above
        if distance_pct > 0:
            return "ALERTE"
        elif distance_pct > -5:
            return "Proche"
        else:
            return "OK"


def badge_color(status: str) -> str:
    return {"ALERTE": "#c0392b", "Proche": "#e67e22", "OK": "#27ae60"}.get(status, "#999")


# ---------------------------------------------------------------------------
# Pages
# ---------------------------------------------------------------------------

def page_overview(config: dict) -> None:
    st.title("Vue d'ensemble")
    st.markdown("Tableau de toutes les actions surveillees avec leur statut en temps reel.")

    watchlist = config.get("watchlist", [])
    if not watchlist:
        st.warning("Watchlist vide. Ajoutez des actions dans l'onglet **Watchlist & Config**.")
        return

    tickers = [item["ticker"] for item in watchlist]
    prices = {p["ticker"]: p for p in get_all_latest_prices(tickers)}

    rows = []
    for item in watchlist:
        ticker = item["ticker"]
        price_data = prices.get(ticker)
        current = price_data["close_price"] if price_data else None
        target = item.get("target_price")
        alert_type = item.get("alert_type", "below")

        if current and target:
            dist = compute_distance_to_target(current, target)
            status = status_badge(dist, alert_type)
        else:
            dist = None
            status = "N/A"

        rows.append({
            "Ticker": ticker,
            "Nom": item.get("name", ticker),
            "Cours actuel": f"{current:.2f}" if current else "—",
            "Prix cible": f"{target:.2f}" if target else "—",
            "Distance": f"{dist:+.2f}%" if dist is not None else "—",
            "Type": alert_type,
            "Statut": status,
            "Notes": item.get("notes", "") or "",
        })

    df = pd.DataFrame(rows)

    # Coloration selon statut
    def highlight_status(val):
        color = badge_color(val)
        return f"color: {color}; font-weight: bold;"

    styled = df.style.map(highlight_status, subset=["Statut"])
    st.dataframe(styled, use_container_width=True, hide_index=True)


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
    target = item.get("target_price")
    alert_type = item.get("alert_type", "below")

    period_labels = {"1M": 30, "3M": 90, "6M": 180, "1A": 365, "MAX": 9999}
    period_selected = st.radio("Periode", list(period_labels.keys()), horizontal=True)
    limit = period_labels[period_selected]

    history = get_price_history(ticker, limit=limit)
    if not history:
        st.info("Pas encore de donnees pour cette action. Lancez une verification.")
        return

    df = pd.DataFrame(history).sort_values("date")
    df["date"] = pd.to_datetime(df["date"])

    fig = go.Figure()

    # Courbe du cours de cloture
    fig.add_trace(go.Scatter(
        x=df["date"], y=df["close_price"],
        mode="lines",
        name="Cours de cloture",
        line={"color": "#2980b9", "width": 2},
        hovertemplate=(
            "<b>%{x|%d/%m/%Y}</b><br>"
            "Cloture : %{y:.2f}<br>"
            "<extra></extra>"
        ),
    ))

    # Zone coloree verte si cours sous la cible (alert_type=below)
    if target:
        fig.add_hline(
            y=target,
            line_dash="dot",
            line_color="red",
            annotation_text=f"Cible : {target:.2f}",
            annotation_position="bottom right",
        )
        if alert_type == "below":
            fig.add_hrect(
                y0=df["close_price"].min() * 0.98,
                y1=target,
                fillcolor="rgba(39,174,96,0.1)",
                line_width=0,
                annotation_text="Zone d'opportunite",
                annotation_position="top left",
            )

    fig.update_layout(
        title=f"{item['name']} ({ticker})",
        xaxis_title="Date",
        yaxis_title=f"Cours ({item.get('currency','EUR')})",
        hovermode="x unified",
        template="plotly_white",
        height=500,
    )
    st.plotly_chart(fig, use_container_width=True)

    # Tableau OHLCV
    with st.expander("Donnees brutes OHLCV"):
        display_df = df[["date", "open_price", "close_price", "high_price", "low_price", "volume"]].copy()
        display_df.columns = ["Date", "Ouverture", "Cloture", "Haut", "Bas", "Volume"]
        st.dataframe(display_df.sort_values("Date", ascending=False), hide_index=True)


def page_alerts() -> None:
    st.title("Historique des alertes")

    alerts = get_all_alerts(limit=200)
    if not alerts:
        st.info("Aucune alerte declenchee pour le moment.")
        return

    df = pd.DataFrame(alerts)
    df["triggered_at"] = pd.to_datetime(df["triggered_at"]).dt.strftime("%d/%m/%Y %H:%M")
    df = df.rename(columns={
        "ticker": "Ticker",
        "triggered_at": "Date declenchement",
        "current_price": "Cours",
        "target_price": "Cible",
        "alert_type": "Type",
        "notification_sent": "Notifie",
        "channel": "Canal",
    })
    cols = ["Ticker", "Date declenchement", "Cours", "Cible", "Type", "Canal", "Notifie"]
    st.dataframe(df[cols], use_container_width=True, hide_index=True)


def page_watchlist_config(config: dict) -> None:
    st.title("Watchlist & Configuration")

    watchlist = config.get("watchlist", [])

    # --- Afficher / Modifier la watchlist ---
    st.subheader("Actions surveillees")

    to_remove = []
    for i, item in enumerate(watchlist):
        with st.expander(f"{item['ticker']} — {item.get('name', '')}"):
            col1, col2 = st.columns(2)
            with col1:
                new_name = st.text_input("Nom", value=item.get("name", ""), key=f"name_{i}")
                new_target = st.number_input(
                    "Prix cible", value=float(item.get("target_price", 0)), key=f"target_{i}"
                )
            with col2:
                new_type = st.selectbox(
                    "Type d'alerte",
                    ["below", "above"],
                    index=0 if item.get("alert_type") == "below" else 1,
                    key=f"type_{i}",
                )
                new_notes = st.text_input("Notes", value=item.get("notes", "") or "", key=f"notes_{i}")

            col_save, col_del = st.columns([1, 1])
            with col_save:
                if st.button("Sauvegarder", key=f"save_{i}"):
                    watchlist[i]["name"] = new_name
                    watchlist[i]["target_price"] = new_target
                    watchlist[i]["alert_type"] = new_type
                    watchlist[i]["notes"] = new_notes
                    config["watchlist"] = watchlist
                    save_config(config)
                    st.success("Sauvegarde!")
            with col_del:
                if st.button("Supprimer", key=f"del_{i}", type="secondary"):
                    to_remove.append(i)

    if to_remove:
        config["watchlist"] = [item for j, item in enumerate(watchlist) if j not in to_remove]
        save_config(config)
        st.rerun()

    # --- Ajouter une action ---
    st.subheader("Ajouter une action")
    with st.form("add_stock"):
        col1, col2 = st.columns(2)
        with col1:
            new_ticker = st.text_input("Ticker Yahoo Finance (ex: AIR.PA)")
            new_name = st.text_input("Nom (ex: Airbus)")
        with col2:
            new_target = st.number_input("Prix cible", min_value=0.01, value=100.0)
            new_type = st.selectbox("Type d'alerte", ["below", "above"])
        new_notes = st.text_input("Notes (optionnel)")
        submitted = st.form_submit_button("Ajouter")

        if submitted and new_ticker:
            config["watchlist"].append({
                "ticker": new_ticker.strip().upper(),
                "name": new_name.strip(),
                "target_price": new_target,
                "alert_type": new_type,
                "notes": new_notes.strip(),
            })
            save_config(config)
            st.success(f"{new_ticker} ajoutee a la watchlist!")
            st.rerun()

    # --- Config notifications ---
    st.subheader("Notifications")
    with st.expander("Email (Gmail)"):
        email_cfg = config.get("email", {})
        enabled = st.checkbox("Activer email", value=email_cfg.get("enabled", False))
        sender = st.text_input("Expediteur", value=email_cfg.get("sender", ""))
        password = st.text_input("Mot de passe d'application", value=email_cfg.get("password", ""), type="password")
        recipient = st.text_input("Destinataire", value=email_cfg.get("recipient", ""))
        if st.button("Sauvegarder config email"):
            config["email"] = {
                "enabled": enabled, "sender": sender, "password": password,
                "recipient": recipient,
                "smtp_host": email_cfg.get("smtp_host", "smtp.gmail.com"),
                "smtp_port": email_cfg.get("smtp_port", 587),
            }
            save_config(config)
            st.success("Config email sauvegardee!")

    with st.expander("Telegram"):
        tg_cfg = config.get("telegram", {})
        tg_enabled = st.checkbox("Activer Telegram", value=tg_cfg.get("enabled", False))
        bot_token = st.text_input("Token du bot", value=tg_cfg.get("bot_token", ""), type="password")
        chat_id = st.text_input("Chat ID", value=tg_cfg.get("chat_id", ""))
        if st.button("Sauvegarder config Telegram"):
            config["telegram"] = {
                "enabled": tg_enabled,
                "bot_token": bot_token,
                "chat_id": chat_id,
            }
            save_config(config)
            st.success("Config Telegram sauvegardee!")

    # --- Schedule ---
    st.subheader("Planification")
    schedule_cfg = config.get("schedule", {})
    sched_time = st.text_input("Heure du check (HH:MM)", value=schedule_cfg.get("time", "09:00"))
    sched_tz = st.text_input("Fuseau horaire", value=schedule_cfg.get("timezone", "Europe/Paris"))
    if st.button("Sauvegarder planification"):
        config["schedule"] = {"time": sched_time, "timezone": sched_tz}
        save_config(config)
        st.success("Planification sauvegardee! Redemarrez l'application pour appliquer.")


def page_suggestions(config: dict) -> None:
    st.title("Suggestions")
    st.markdown(
        "Actions europeennes eligibles PEA selectionnees avec leur these d'investissement. "
        "Cliquez sur **Ajouter a ma watchlist** pour les surveiller."
    )

    watchlist_tickers = {item["ticker"] for item in config.get("watchlist", [])}

    risk_colors = {"low": "#27ae60", "medium": "#e67e22", "high": "#c0392b"}
    risk_labels = {"low": "Faible", "medium": "Moyen", "high": "Eleve"}

    for suggestion in SUGGESTIONS:
        already_in = suggestion["ticker"] in watchlist_tickers
        with st.container():
            col1, col2 = st.columns([4, 1])
            with col1:
                risk_color = risk_colors.get(suggestion["risk"], "#999")
                risk_label = risk_labels.get(suggestion["risk"], suggestion["risk"])
                st.markdown(
                    f"**{suggestion['name']}** ({suggestion['ticker']}) &nbsp; "
                    f"<span style='background:{risk_color};color:white;padding:2px 8px;"
                    f"border-radius:4px;font-size:12px;'>{risk_label}</span> &nbsp; "
                    f"*{suggestion['sector']}*",
                    unsafe_allow_html=True,
                )
                st.markdown(f"**These :** {suggestion['thesis']}")
                st.markdown(f"**Pourquoi maintenant :** {suggestion['why_now']}")
                st.markdown(f"Prix de surveillance suggere : **{suggestion['watch_price']:.2f} EUR**")
            with col2:
                if already_in:
                    st.markdown("✓ Dans la watchlist")
                else:
                    if st.button("Ajouter", key=f"add_{suggestion['ticker']}"):
                        config["watchlist"].append({
                            "ticker": suggestion["ticker"],
                            "name": suggestion["name"],
                            "target_price": suggestion["watch_price"],
                            "alert_type": "below",
                            "notes": suggestion["thesis"],
                        })
                        save_config(config)
                        st.success(f"{suggestion['name']} ajoutee!")
                        st.rerun()
            st.divider()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    st.set_page_config(
        page_title="Stock Monitor",
        page_icon="📈",
        layout="wide",
        initial_sidebar_state="expanded",
    )

    init_db()
    config = load_config()

    with st.sidebar:
        st.title("📈 Stock Monitor")
        st.markdown("---")
        page = st.radio(
            "Navigation",
            [
                "Vue d'ensemble",
                "Historique",
                "Alertes",
                "Watchlist & Config",
                "Suggestions",
            ],
            label_visibility="collapsed",
        )
        st.markdown("---")
        st.caption("Surveillance automatique de cours boursiers")

        if st.button("Lancer une verification maintenant", type="primary"):
            with st.spinner("Verification en cours..."):
                from app.scheduler import run_daily_check
                run_daily_check()
            st.success("Verification terminee!")

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
