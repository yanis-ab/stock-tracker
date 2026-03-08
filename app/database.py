"""
database.py — Modeles SQLAlchemy et operations sur la base de donnees.
Supporte SQLite (local) et PostgreSQL (cloud via DATABASE_URL).
"""

import os
import logging
from datetime import datetime, date
from pathlib import Path

from sqlalchemy import (
    create_engine, Column, Integer, Text, Date, DateTime,
    Float, Boolean, UniqueConstraint
)
from sqlalchemy.orm import DeclarativeBase, Session

logger = logging.getLogger(__name__)

_BASE_DIR = Path(__file__).resolve().parent.parent
DB_PATH = _BASE_DIR / "data" / "stock_monitor.db"

# PostgreSQL en cloud (DATABASE_URL), SQLite en local
_db_url = os.environ.get("DATABASE_URL", "")
if _db_url:
    # Supabase/Heroku utilisent postgres://, SQLAlchemy requiert postgresql://
    if _db_url.startswith("postgres://"):
        _db_url = _db_url.replace("postgres://", "postgresql://", 1)
    DB_URL = _db_url
    logger.info("Base de donnees : PostgreSQL (cloud)")
else:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    DB_URL = f"sqlite:///{DB_PATH}"
    logger.info("Base de donnees : SQLite (local)")

engine = create_engine(DB_URL, echo=False)


class Base(DeclarativeBase):
    pass


class StockPrice(Base):
    __tablename__ = "stock_prices"

    id = Column(Integer, primary_key=True, autoincrement=True)
    ticker = Column(Text, nullable=False)
    name = Column(Text)
    date = Column(Date, nullable=False)
    open_price = Column(Float)
    close_price = Column(Float)
    high_price = Column(Float)
    low_price = Column(Float)
    volume = Column(Integer)
    currency = Column(Text)
    fetched_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint("ticker", "date", name="uq_ticker_date"),
    )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "ticker": self.ticker,
            "name": self.name,
            "date": self.date.isoformat() if self.date else None,
            "open_price": self.open_price,
            "close_price": self.close_price,
            "high_price": self.high_price,
            "low_price": self.low_price,
            "volume": self.volume,
            "currency": self.currency,
            "fetched_at": self.fetched_at.isoformat() if self.fetched_at else None,
        }


class Alert(Base):
    __tablename__ = "alerts"

    id = Column(Integer, primary_key=True, autoincrement=True)
    ticker = Column(Text, nullable=False)
    triggered_at = Column(DateTime, default=datetime.utcnow)
    current_price = Column(Float)
    target_price = Column(Float)
    alert_type = Column(Text)          # 'below' ou 'above'
    notification_sent = Column(Boolean, default=False)
    channel = Column(Text)             # 'email', 'telegram', 'both', 'none'

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "ticker": self.ticker,
            "triggered_at": self.triggered_at.isoformat() if self.triggered_at else None,
            "current_price": self.current_price,
            "target_price": self.target_price,
            "alert_type": self.alert_type,
            "notification_sent": self.notification_sent,
            "channel": self.channel,
        }


def init_db() -> None:
    """Cree les tables si elles n'existent pas."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    Base.metadata.create_all(engine)
    logger.info("Base de donnees initialisee : %s", DB_PATH)


# ---------------------------------------------------------------------------
# Operations sur stock_prices
# ---------------------------------------------------------------------------

def save_prices(price_records: list[dict]) -> int:
    """
    Insere ou ignore les enregistrements de cours.
    Retourne le nombre de lignes inserees.
    """
    inserted = 0
    with Session(engine) as session:
        for rec in price_records:
            # Evite les doublons via UNIQUE(ticker, date)
            existing = (
                session.query(StockPrice)
                .filter_by(ticker=rec["ticker"], date=rec["date"])
                .first()
            )
            if existing:
                continue
            row = StockPrice(
                ticker=rec["ticker"],
                name=rec.get("name"),
                date=rec["date"],
                open_price=rec.get("open"),
                close_price=rec.get("close"),
                high_price=rec.get("high"),
                low_price=rec.get("low"),
                volume=rec.get("volume"),
                currency=rec.get("currency"),
                fetched_at=datetime.utcnow(),
            )
            session.add(row)
            inserted += 1
        session.commit()
    logger.info("%d cours enregistres en base.", inserted)
    return inserted


def get_latest_price(ticker: str) -> dict | None:
    """Retourne le dernier cours connu pour un ticker."""
    with Session(engine) as session:
        row = (
            session.query(StockPrice)
            .filter_by(ticker=ticker)
            .order_by(StockPrice.date.desc())
            .first()
        )
        return row.to_dict() if row else None


def get_price_history(ticker: str, limit: int = 365) -> list[dict]:
    """Retourne l'historique de cours pour un ticker, du plus recent au plus ancien."""
    with Session(engine) as session:
        rows = (
            session.query(StockPrice)
            .filter_by(ticker=ticker)
            .order_by(StockPrice.date.desc())
            .limit(limit)
            .all()
        )
        return [r.to_dict() for r in rows]


def get_all_latest_prices(tickers: list[str]) -> list[dict]:
    """Retourne le dernier cours pour chaque ticker de la liste."""
    return [p for t in tickers if (p := get_latest_price(t)) is not None]


# ---------------------------------------------------------------------------
# Operations sur alerts
# ---------------------------------------------------------------------------

def alert_already_triggered_today(ticker: str) -> bool:
    """Verifie si une alerte a deja ete declenchee aujourd'hui pour ce ticker."""
    today = date.today()
    with Session(engine) as session:
        row = (
            session.query(Alert)
            .filter(Alert.ticker == ticker)
            .filter(Alert.triggered_at >= datetime(today.year, today.month, today.day))
            .first()
        )
        return row is not None


def save_alert(alert_data: dict) -> int:
    """Insere une nouvelle alerte. Retourne l'id de l'alerte."""
    with Session(engine) as session:
        row = Alert(
            ticker=alert_data["ticker"],
            triggered_at=datetime.utcnow(),
            current_price=alert_data["current_price"],
            target_price=alert_data["target_price"],
            alert_type=alert_data["alert_type"],
            notification_sent=alert_data.get("notification_sent", False),
            channel=alert_data.get("channel", "none"),
        )
        session.add(row)
        session.commit()
        session.refresh(row)
        alert_id = row.id
    logger.info("Alerte enregistree pour %s (id=%d)", alert_data["ticker"], alert_id)
    return alert_id


def get_all_alerts(limit: int = 200) -> list[dict]:
    """Retourne toutes les alertes, de la plus recente a la plus ancienne."""
    with Session(engine) as session:
        rows = (
            session.query(Alert)
            .order_by(Alert.triggered_at.desc())
            .limit(limit)
            .all()
        )
        return [r.to_dict() for r in rows]
