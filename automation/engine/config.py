"""Settings for the Meridian content engine. Everything secret comes from environment variables."""
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]          # repo root (the website)
AUTO = ROOT / "automation"
PROMPTS = AUTO / "prompts"
DATA = AUTO / "data"
RUNS = DATA / "runs"
GSC_DIR = DATA / "gsc"

SITE = "https://meridiancapital.in"
HOST = "meridiancapital.in"
GSC_SITE = os.environ.get("GSC_SITE", "sc-domain:meridiancapital.in")
STYLE_REFERENCE = "insights/us-estate-tax-for-indians.html"   # voice reference + blind-test benchmark

IST = timezone(timedelta(hours=5, minutes=30))


def now_ist():
    return datetime.now(IST)


# Models per agent. Opus where judgement and writing quality matter, Sonnet elsewhere.
OPUS = os.environ.get("MODEL_OPUS", "claude-opus-5-5")
SONNET = os.environ.get("MODEL_SONNET", "claude-sonnet-5-5")
HAIKU = os.environ.get("MODEL_HAIKU", "claude-haiku-5-5")
MODELS = {
    "perspective_bank": OPUS,
    "director": SONNET,
    "scout": SONNET,
    "strategist": SONNET,
    "serp": SONNET,
    "researcher": SONNET,
    "writer": OPUS,
    "editor": OPUS,
    "reader_panel": SONNET,
    "gate": OPUS,
    "builder": SONNET,
    "analyst": SONNET,
    "retitle": SONNET,
    "reporter": HAIKU,
}

# USD per million tokens (input, output). Update if pricing changes.
PRICES = {
    OPUS: (4.0, 20.0),
    SONNET: (2.0, 10.0),
    HAIKU: (0.10, 0.50),
}
WEB_SEARCH_USD = 0.01                       # per search
MAX_RUN_USD = float(os.environ.get("MAX_RUN_USD", "12"))   # hard stop for one weekly run

# Behaviour
MAX_GATE_ROUNDS = 3
STRICT_WEEKS = 4                             # gate treats MINOR issues as blocking for the first N posts
MAX_TOPIC_FALLBACKS = 2
CHECKPOINTS = (7, 21, 28, 56, 84)

PILLARS = ["P1", "P2", "P3", "P4", "P5", "P6"]
CORNERSTONES = {
    "P1": "/insights/lrs-tcs-schedule-fa",
    "P2": "/insights/how-us-investments-are-taxed-in-india",
    "P3": "/insights/us-estate-tax-for-indians",
    "P4": "/insights/rupee-is-a-return",
    "P5": "/insights/us-etfs-vs-irish-ucits-etfs",
    "P6": "/insights/how-much-should-be-global",
}

SEED_TERMS = [
    "LRS limit", "TCS on foreign remittance", "send money abroad from India for investment",
    "invest in US stocks from India", "Schedule FA", "foreign tax credit Form 67",
    "tax on US stocks in India", "US dividend withholding tax India", "DTAA India US",
    "US estate tax for Indians", "is Interactive Brokers safe in India", "SIPC protection",
    "rupee depreciation", "USD INR long term", "Fed rate decision impact India",
    "Irish ETF vs US ETF", "UCITS ETF India", "international mutual funds India limit",
    "GIFT City US stocks", "fractional shares US India", "US treasury bonds from India",
    "how much international diversification", "S&P 500 vs Nifty", "home bias investing",
    "Interactive Brokers account India", "overseas portfolio investment FEMA",
    "capital gains on foreign shares India", "remittance charges forex markup",
    "US stocks nomination India", "global portfolio for Indians",
]

NEWS_FEEDS = [
    "https://www.rbi.org.in/pressreleases_rss.xml",
    "https://www.rbi.org.in/notifications_rss.xml",
    "https://www.sebi.gov.in/sebirss.xml",
    "https://www.federalreserve.gov/feeds/press_all.xml",
    "https://www.livemint.com/rss/markets",
    "https://www.business-standard.com/rss/markets-106.rss",
    "https://economictimes.indiatimes.com/markets/rssfeeds/1977021501.cms",
]
NEWS_KEYWORDS = [
    "lrs", "liberalised remittance", "tcs", "remittance", "overseas", "foreign", "fema",
    "rupee", "dollar", "usd", "fed ", "federal reserve", "fomc", "interest rate", "gift city",
    "international fund", "us stock", "nasdaq", "s&p", "estate tax", "dtaa", "income tax",
    "cbdt", "schedule fa", "black money",
]

# Secrets / integrations
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
DATAFORSEO_LOGIN = os.environ.get("DATAFORSEO_LOGIN", "")
DATAFORSEO_PASSWORD = os.environ.get("DATAFORSEO_PASSWORD", "")
GSC_SA_JSON = os.environ.get("GSC_SA_JSON", "")
RESEND_API_KEY = os.environ.get("RESEND_API_KEY", "")
REPORT_EMAIL = os.environ.get("REPORT_EMAIL", "")
MAIL_FROM = os.environ.get("MAIL_FROM", "Meridian SEO Engine <seo@meridiancapital.in>")
DRY_RUN = os.environ.get("DRY_RUN", "").lower() in ("1", "true", "yes")
CALC_SANDBOX = os.environ.get("CALC_SANDBOX", "auto")      # "strict" in CI: no network, unprivileged user
