# Stock Monitor

Outil de surveillance automatique de cours boursiers europeens (PEA).
Strategie GARP long terme : actions de qualite achetees en zone de sous-evaluation.

## Fonctionnalites

- **Score de conviction 0/5** par action (5 criteres combines)
- **Indicateurs techniques** : RSI 14j, MA50, MA200, range 52 semaines
- **Donnees analystes** : objectif de cours, upside, consensus, fundamentaux
- **Alertes quotidiennes** email (Gmail) et/ou Telegram
- **Dashboard Streamlit** avec graphiques Plotly interactifs (cours + MA + RSI)
- **Historique** des cours et des alertes en base SQLite/PostgreSQL locale

## Score de conviction (strategie GARP)

| Critere | Condition | Point |
|---------|-----------|-------|
| Prix cible personnel | Cours atteint votre seuil | +1 |
| RSI survendu | RSI 14j < 40 | +1 |
| Decote long terme | Cours sous la MA200 | +1 |
| Valeur reconnue | Upside analystes > 15% | +1 |
| Consensus positif | Recommandation buy/strong_buy | +1 |

**4-5/5 = Zone d'achat forte · 3/5 = Zone interessante · 2/5 = A surveiller · 0-1/5 = Attendre**

## Installation

```bash
git clone <repo> && cd stock-monitor
python3 -m venv .venv
source .venv/bin/activate      # Mac/Linux
# .venv\Scripts\activate       # Windows
pip install -r requirements.txt
```

## Configuration

Editer `config.yaml` :
- `watchlist` : vos actions avec ticker Yahoo Finance, prix cible, type d'alerte, notes/these
- `email` : credentials Gmail (mot de passe d'application requis)
- `telegram` : token bot + chat_id
- `schedule` : heure du check quotidien

### Tickers Yahoo Finance
| Place | Suffixe | Exemple |
|-------|---------|---------|
| Euronext Paris | `.PA` | `AIR.PA` (Airbus) |
| Amsterdam | `.AS` | `ASML.AS` |
| Milan | `.MI` | `STM.MI` |
| Frankfurt | `.DE` | `SAP.DE` |
| Madrid | `.MC` | `IBE.MC` |
| Zurich | `.SW` | `NESN.SW` |

## Lancement local

```bash
source .venv/bin/activate
streamlit run dashboard/streamlit_app.py   # Dashboard seul
# ou
python main.py                              # Dashboard + scheduler complet
```

## Deploiement cloud (gratuit)

| Service | Role | Gratuit |
|---------|------|---------|
| **Supabase** | Base PostgreSQL | 500MB permanent |
| **GitHub Actions** | Check quotidien lun-ven | 2000 min/mois |
| **Streamlit Community Cloud** | Dashboard en ligne | Illimite |

### Variables d'environnement requises

```
DATABASE_URL          # URL PostgreSQL Supabase
EMAIL_SENDER          # Adresse Gmail expediteur
EMAIL_PASSWORD        # Mot de passe d'application Gmail
EMAIL_RECIPIENT       # Adresse destinataire
TELEGRAM_BOT_TOKEN    # Token bot Telegram
TELEGRAM_CHAT_ID      # Votre Chat ID Telegram
```

A configurer dans :
- **GitHub** : Settings → Secrets → Actions
- **Streamlit Cloud** : Settings → Secrets (format TOML)

## Structure

```
stock-monitor/
├── main.py                     # Lance scheduler + dashboard
├── run_check.py                # Point d'entree GitHub Actions (one-shot)
├── config.yaml                 # Watchlist + configuration
├── requirements.txt
├── app/
│   ├── fetcher.py              # yfinance : cours, RSI, MA, analystes
│   ├── database.py             # SQLAlchemy (SQLite local / PostgreSQL cloud)
│   ├── analyzer.py             # Detection alertes + score de conviction
│   ├── notifier.py             # Email + Telegram
│   └── scheduler.py            # APScheduler + tache quotidienne
├── dashboard/
│   └── streamlit_app.py        # Interface web (5 pages)
├── .github/workflows/
│   └── daily_check.yml         # Cron GitHub Actions lun-ven 9h Paris
└── .streamlit/
    └── secrets.toml.example    # Template secrets Streamlit Cloud
```

## Telegram — mise en place

1. Ecrire a `@BotFather` → `/newbot` → noter le token
2. Ecrire un message a votre bot
3. Recuperer votre chat_id : `https://api.telegram.org/bot<TOKEN>/getUpdates`

## Gmail — mot de passe d'application

1. Activer la validation en 2 etapes sur votre compte Google
2. Google Account → Securite → Mots de passe des applications → generer pour "Mail"
