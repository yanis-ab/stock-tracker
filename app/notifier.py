"""
notifier.py — Envoi des alertes par email (Gmail) et/ou Telegram.
"""

import logging
import smtplib
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Email
# ---------------------------------------------------------------------------

def _build_email_html(alerts: list[dict]) -> str:
    today = datetime.now().strftime("%d/%m/%Y %H:%M")
    rows = ""
    for a in alerts:
        distance_str = f"{a['distance_pct']:+.2f}%"
        direction = "sous" if a["alert_type"] == "below" else "au-dessus de"
        rows += f"""
        <tr>
            <td style="padding:8px;border:1px solid #ddd;"><strong>{a['name']}</strong><br>
                <span style="color:#666;font-size:12px;">{a['ticker']}</span></td>
            <td style="padding:8px;border:1px solid #ddd;text-align:right;">
                {a['current_price']:.2f} {a.get('currency','EUR')}</td>
            <td style="padding:8px;border:1px solid #ddd;text-align:right;">
                {a['target_price']:.2f} {a.get('currency','EUR')}</td>
            <td style="padding:8px;border:1px solid #ddd;text-align:center;
                color:{'#c0392b' if a['alert_type']=='below' else '#27ae60'};">
                {distance_str} {direction} la cible</td>
            <td style="padding:8px;border:1px solid #ddd;color:#666;font-size:12px;">
                {a.get('notes','') or '—'}</td>
        </tr>"""

    return f"""
    <html><body style="font-family:Arial,sans-serif;color:#333;">
    <h2 style="color:#2c3e50;">Stock Monitor — Alertes du {today}</h2>
    <p>{len(alerts)} alerte(s) detectee(s) :</p>
    <table style="border-collapse:collapse;width:100%;margin-top:12px;">
        <thead>
            <tr style="background:#2c3e50;color:white;">
                <th style="padding:10px;text-align:left;">Action</th>
                <th style="padding:10px;text-align:right;">Cours actuel</th>
                <th style="padding:10px;text-align:right;">Prix cible</th>
                <th style="padding:10px;text-align:center;">Distance</th>
                <th style="padding:10px;text-align:left;">Notes</th>
            </tr>
        </thead>
        <tbody>{rows}</tbody>
    </table>
    <p style="margin-top:20px;color:#999;font-size:12px;">
        Stock Monitor — surveillance automatique locale
    </p>
    </body></html>"""


def send_email(alerts: list[dict], email_config: dict) -> bool:
    """
    Envoie un email recapitulatif des alertes via Gmail (smtplib).
    Retourne True si l'envoi a reussi.
    """
    if not alerts:
        return True

    tickers_str = ", ".join(a["ticker"] for a in alerts)
    today_str = datetime.now().strftime("%d/%m/%Y")
    subject = f"[Stock Monitor] {len(alerts)} alerte(s) — {tickers_str} — {today_str}"

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = email_config["sender"]
    msg["To"] = email_config["recipient"]

    html_content = _build_email_html(alerts)
    msg.attach(MIMEText(html_content, "html"))

    try:
        with smtplib.SMTP(email_config["smtp_host"], email_config["smtp_port"]) as server:
            server.starttls()
            server.login(email_config["sender"], email_config["password"])
            server.sendmail(
                email_config["sender"],
                email_config["recipient"],
                msg.as_string(),
            )
        logger.info("Email envoye a %s (%d alerte(s))", email_config["recipient"], len(alerts))
        return True
    except Exception as exc:
        logger.error("Erreur envoi email : %s", exc)
        return False


# ---------------------------------------------------------------------------
# Telegram
# ---------------------------------------------------------------------------

def _build_telegram_message(alert: dict) -> str:
    direction = "sous" if alert["alert_type"] == "below" else "au-dessus de"
    date_str = (
        alert["date"].strftime("%d/%m/%Y")
        if hasattr(alert.get("date"), "strftime")
        else str(alert.get("date", ""))
    )
    lines = [
        "Alerte Stock Monitor",
        "",
        f"{alert['ticker']} — {alert['current_price']:.2f} {alert.get('currency','EUR')}",
        f"Prix cible atteint : {alert['target_price']:.2f} {alert.get('currency','EUR')} ({alert['alert_type']})",
        f"Distance : {alert['distance_pct']:+.2f}% {direction} la cible",
        f"{date_str}",
    ]
    if alert.get("notes"):
        lines += ["", f"Note : {alert['notes']}"]
    return "\n".join(lines)


async def _send_telegram_async(alerts: list[dict], telegram_config: dict) -> bool:
    """Envoi async (utilise python-telegram-bot v20+)."""
    try:
        from telegram import Bot
        bot = Bot(token=telegram_config["bot_token"])
        chat_id = telegram_config["chat_id"]
        async with bot:
            for alert in alerts:
                text = _build_telegram_message(alert)
                await bot.send_message(chat_id=chat_id, text=text)
                logger.info("Message Telegram envoye pour %s", alert["ticker"])
        return True
    except Exception as exc:
        logger.error("Erreur Telegram : %s", exc)
        return False


def send_telegram(alerts: list[dict], telegram_config: dict) -> bool:
    """
    Envoie les alertes via Telegram.
    Retourne True si tous les messages ont ete envoyes.
    """
    if not alerts:
        return True
    import asyncio
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            # Dans un contexte async (ex: Streamlit), creer une tache
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as pool:
                future = pool.submit(
                    asyncio.run, _send_telegram_async(alerts, telegram_config)
                )
                return future.result()
        else:
            return asyncio.run(_send_telegram_async(alerts, telegram_config))
    except Exception as exc:
        logger.error("Erreur envoi Telegram : %s", exc)
        return False


# ---------------------------------------------------------------------------
# Orchestrateur
# ---------------------------------------------------------------------------

def notify(alerts: list[dict], config: dict) -> str:
    """
    Envoie les notifications selon la configuration.
    Retourne le canal utilise ('email', 'telegram', 'both', 'none').
    """
    if not alerts:
        return "none"

    email_ok = False
    telegram_ok = False

    email_cfg = config.get("email", {})
    if email_cfg.get("enabled"):
        email_ok = send_email(alerts, email_cfg)

    telegram_cfg = config.get("telegram", {})
    if telegram_cfg.get("enabled"):
        telegram_ok = send_telegram(alerts, telegram_cfg)

    if email_ok and telegram_ok:
        return "both"
    elif email_ok:
        return "email"
    elif telegram_ok:
        return "telegram"
    else:
        return "none"
