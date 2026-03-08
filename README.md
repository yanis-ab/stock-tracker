# Stock Monitor

Outil de surveillance automatique de cours boursiers europeens (PEA).
Detecte chaque matin les opportunites sur votre watchlist et envoie des alertes par email et/ou Telegram.

## Fonctionnalites

- **Surveillance quotidienne** automatique via APScheduler
- **Alertes** email (Gmail) et/ou Telegram quand un cours atteint votre prix cible
- **Dashboard web** Streamlit avec graphiques Plotly interactifs
- **Historique** des cours et des alertes en base SQLite locale
- **10 suggestions** d'actions europeennes eligibles PEA avec analyse

## Installation

```bash
git clone <repo> && cd stock-monitor
python -m venv .venv
source .venv/bin/activate   # Mac/Linux
# .venv\Scripts\activate    # Windows
pip install -r requirements.txt
```

## Configuration

Editer `config.yaml` :
- Ajouter vos actions dans `watchlist` avec le ticker Yahoo Finance, le prix cible et le type d'alerte
- Configurer vos credentials email Gmail (mot de passe d'application requis)
- Configurer votre bot Telegram (creer via @BotFather)

### Tickers Yahoo Finance par place boursiere
| Place | Suffixe | Exemple |
|-------|---------|---------|
| Euronext Paris | `.PA` | `AIR.PA` (Airbus) |
| Amsterdam | `.AS` | `ASML.AS` |
| Milan | `.MI` | `STM.MI` |
| Frankfurt | `.DE` | `SAP.DE` |
| Madrid | `.MC` | `IBE.MC` |
| Zurich | `.SW` | `NESN.SW` |

## Lancement

```bash
python main.py
```

Lance le scheduler en arriere-plan et ouvre automatiquement le dashboard sur http://localhost:8501.

### Lancer uniquement le dashboard

```bash
streamlit run dashboard/streamlit_app.py
```

## Structure

```
stock-monitor/
├── main.py                  # Point d'entree
├── config.yaml              # Configuration (watchlist, alertes, schedule)
├── requirements.txt
├── app/
│   ├── fetcher.py           # Recuperation des cours via yfinance
│   ├── database.py          # SQLAlchemy + SQLite
│   ├── analyzer.py          # Detection des alertes
│   ├── notifier.py          # Email + Telegram
│   └── scheduler.py         # APScheduler (tache quotidienne)
├── dashboard/
│   └── streamlit_app.py     # Interface web
├── data/                    # Base SQLite (auto-generee)
└── logs/                    # Logs avec rotation hebdomadaire
```

## Telegram — mise en place

1. Ecrire a `@BotFather` sur Telegram → `/newbot` → noter le token
2. Ecrire un message a votre bot
3. Recuperer votre `chat_id` : `https://api.telegram.org/bot<TOKEN>/getUpdates`
4. Renseigner `bot_token` et `chat_id` dans `config.yaml`

## Gmail — mot de passe d'application

1. Activer la validation en 2 etapes sur votre compte Google
2. Google Account → Securite → Mots de passe des applications
3. Generer un mot de passe pour "Mail" → utiliser ce mot de passe dans `config.yaml`
