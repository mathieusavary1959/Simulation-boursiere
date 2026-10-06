import streamlit as st
import yfinance as yf
import pandas as pd
import plotly.graph_objects as go
import requests
import uuid
from datetime import datetime
from zoneinfo import ZoneInfo
from sqlalchemy import text
import streamlit.components.v1 as components

# --- CONFIGURATION DE LA PAGE ---
st.set_page_config(page_title="Monde & Finance — Simulation Boursière", page_icon="📈", layout="wide")

# Liste des 10 groupes + Groupe Enseignants
LISTE_GROUPES = [f"Groupe {i}" for i in range(501, 511)] + ["Enseignants"]

# --- CONNEXION BASE DE DONNÉES CLOUD (SUPABASE) ---
conn = st.connection("postgres", type="sql")

@st.cache_resource
def init_db():
    with conn.session as session:
        try:
            session.execute(text('''
                CREATE TABLE IF NOT EXISTS users (
                    username TEXT PRIMARY KEY,
                    password TEXT,
                    cash DOUBLE PRECISION,
                    groupe TEXT
                );
            '''))
            session.execute(text('''
                CREATE TABLE IF NOT EXISTS portfolio (
                    username TEXT,
                    ticker TEXT,
                    shares INT,
                    avg_price DOUBLE PRECISION,
                    PRIMARY KEY(username, ticker)
                );
            '''))
            session.execute(text('''
                CREATE TABLE IF NOT EXISTS transactions (
                    id SERIAL PRIMARY KEY,
                    username TEXT,
                    ticker TEXT,
                    shares INT,
                    price DOUBLE PRECISION,
                    total DOUBLE PRECISION,
                    timestamp TEXT
                );
            '''))
            session.execute(text('''
                CREATE TABLE IF NOT EXISTS sessions (
                    token TEXT PRIMARY KEY,
                    username TEXT,
                    created_at TEXT
                );
            '''))
            session.commit()
        except Exception:
            session.rollback()

init_db()

# --- FILTRE DE VALIDATION DES BOURSES NORD-AMÉRICAINES ---
def est_marche_nord_americain(symbol, exch_code="", exch_disp=""):
    symbol_upper = symbol.upper().strip()
    
    suffixes_interdits = (
        '.PA', '.T', '.L', '.DE', '.MI', '.SS', '.HK', '.AX', 
        '.BR', '.LS', '.MC', '.AS', '.SW', '.SA', '.MX', '.BE', '.F', '.VI'
    )
    if symbol_upper.endswith(suffixes_interdits):
        return False
        
    if '.' in symbol_upper:
        suffix = symbol_upper.split('.')[-1]
        if suffix not in ['TO', 'V', 'CN', 'NE']:
            return False

    mots_cles_na = [
        'NYSE', 'NASDAQ', 'TSX', 'TORONTO', 'AMEX', 'OTC', 'NEO', 
        'VENTURE', 'CBOE', 'AMERICAN', 'PNK', 'NMS', 'NYQ', 'NGM', 'NCM', 'TOR', 'VAN'
    ]
    
    comb = f"{exch_code} {exch_disp}".upper()
    if comb.strip():
        return any(kw in comb for kw in mots_cles_na)
        
    return True

# --- FONCTION DE PROTECTION ANTI-SPAM (COOLDOWN DE 3 SECONDES) ---
def verifier_cooldown(username, delai_secondes=3):
    res = conn.query("SELECT timestamp FROM transactions WHERE username=:u ORDER BY id DESC LIMIT 1", params={"u": username}, ttl=0)
    if not res.empty:
        try:
            dernier_temps = datetime.strptime(str(res.iloc[0]['timestamp']), "%Y-%m-%d %H:%M:%S")
            maintenant = datetime.now(ZoneInfo("America/Toronto")).replace(tzinfo=None)
            if (maintenant - dernier_temps).total_seconds() < delai_secondes:
                return False
        except Exception:
            pass
    return True

# --- DESIGN HAUT CONTRASTE, STYLE BOUTONS 3D & ADAPTATION MOBILE ---
st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700;800&display=swap');

    html, body, [class*="css"] {
        font-family: 'Plus Jakarta Sans', -apple-system, BlinkMacSystemFont, sans-serif;
    }

    .stApp {
        background-color: #E2E8F0 !important;
        color: #0F172A !important;
    }

    #MainMenu, footer, header { visibility: hidden; }

    .brand-banner {
        background: linear-gradient(135deg, #0F172A 0%, #1E293B 100%);
        border-radius: 20px;
        padding: 24px 32px;
        color: #FFFFFF;
        margin-bottom: 24px;
        box-shadow: 0 10px 25px -5px rgba(15, 23, 42, 0.2);
        display: flex;
        justify-content: space-between;
        align-items: center;
        border: 1px solid #334155;
    }
    .brand-title {
        font-size: 1.9rem;
        font-weight: 800;
        letter-spacing: -0.02em;
        color: #FFFFFF;
        margin: 0;
    }
    .brand-subtitle {
        color: #94A3B8;
        font-size: 0.88rem;
        font-weight: 500;
        margin-top: 4px;
    }
    .brand-badge {
        background: rgba(56, 189, 248, 0.15);
        border: 1px solid #38BDF8;
        padding: 6px 16px;
        border-radius: 30px;
        font-size: 0.8rem;
        font-weight: 700;
        color: #38BDF8;
        letter-spacing: 0.05em;
        text-transform: uppercase;
    }

    div[data-testid="stMetric"] {
        background-color: #FFFFFF !important;
        border: 1.5px solid #CBD5E1 !important;
        border-radius: 18px !important;
        padding: 18px 20px !important;
        box-shadow: 0 4px 14px rgba(15, 23, 42, 0.08) !important;
        transition: all 0.25s ease !important;
    }
    div[data-testid="stMetric"]:hover {
        transform: translateY(-2px);
        box-shadow: 0 8px 20px rgba(15, 23, 42, 0.12) !important;
        border-color: #94A3B8 !important;
    }
    div[data-testid="stMetricValue"] {
        font-size: 1.6rem !important;
        font-weight: 800 !important;
        color: #0F172A !important;
        letter-spacing: -0.02em;
        white-space: nowrap !important;
        overflow: visible !important;
    }
    div[data-testid="stMetricLabel"] {
        color: #475569 !important;
        font-size: 0.78rem;
        text-transform: uppercase;
        font-weight: 800;
        letter-spacing: 0.06em;
    }

    /* --- NAVIGATION EN BOUTONS 3D --- */
    div[data-testid="stRadio"]:has(input[name="main_nav_radio"]) > label {
        display: none !important;
    }
    div[data-testid="stRadio"]:has(input[name="main_nav_radio"]) > div {
        flex-direction: row !important;
        gap: 12px !important;
        background-color: transparent !important;
        border: none !important;
        padding: 4px 0px 16px 0px !important;
        margin-bottom: 10px !important;
        flex-wrap: wrap !important;
    }
    div[data-testid="stRadio"]:has(input[name="main_nav_radio"]) label {
        background: linear-gradient(180deg, #1E293B 0%, #0F172A 100%) !important;
        border-radius: 12px !important;
        color: #CBD5E1 !important;
        padding: 12px 24px !important;
        font-weight: 700 !important;
        font-size: 0.92rem !important;
        border: none !important;
        box-shadow: 0 4px 0 #020617, 0 6px 14px rgba(15, 23, 42, 0.2) !important;
        transition: all 0.12s ease !important;
        cursor: pointer !important;
        margin: 0 !important;
    }
    div[data-testid="stRadio"]:has(input[name="main_nav_radio"]) label:hover {
        color: #FFFFFF !important;
        background: linear-gradient(180deg, #334155 0%, #1E293B 100%) !important;
        transform: translateY(-2px);
        box-shadow: 0 6px 0 #020617, 0 8px 18px rgba(15, 23, 42, 0.25) !important;
    }
    div[data-testid="stRadio"]:has(input[name="main_nav_radio"]) label:has(input:checked) {
        background: linear-gradient(180deg, #2563EB 0%, #1D4ED8 100%) !important;
        color: #FFFFFF !important;
        box-shadow: 0 4px 0 #1E40AF, 0 8px 20px rgba(37, 99, 235, 0.35) !important;
        border: none !important;
        transform: translateY(0px) !important;
    }
    div[data-testid="stRadio"]:has(input[name="main_nav_radio"]) div[data-testid="stMarkdownContainer"] p {
        color: inherit !important;
        font-weight: 700 !important;
        font-size: 0.92rem !important;
    }

    /* Boutons standards */
    .stButton>button, div[data-testid="stFormSubmitButton"]>button {
        border-radius: 12px !important;
        background: linear-gradient(180deg, #1E293B 0%, #0F172A 100%) !important;
        color: #FFFFFF !important;
        font-weight: 700 !important;
        border: none !important;
        padding: 12px 24px !important;
        box-shadow: 0 4px 0 #020617, 0 6px 14px rgba(15, 23, 42, 0.2) !important;
        transition: all 0.12s ease !important;
    }
    .stButton>button:hover, div[data-testid="stFormSubmitButton"]>button:hover {
        background: linear-gradient(180deg, #2563EB 0%, #1D4ED8 100%) !important;
        box-shadow: 0 6px 0 #1E40AF, 0 10px 20px rgba(37, 99, 235, 0.3) !important;
        transform: translateY(-2px);
    }

    .stTextInput>div>div>input, .stNumberInput>div>div>input, .stSelectbox>div>div {
        background-color: #FFFFFF !important;
        color: #0F172A !important;
        border-radius: 12px !important;
        border: 1.5px solid #94A3B8 !important;
        padding: 11px 16px !important;
        font-weight: 600 !important;
    }

    .custom-table {
        width: 100%;
        border-collapse: collapse;
        background-color: #FFFFFF;
        border-radius: 14px;
        overflow: hidden;
        border: 1.5px solid #CBD5E1;
        margin-bottom: 24px;
        box-shadow: 0 4px 14px rgba(0,0,0,0.05);
    }
    .custom-table th {
        background-color: #F1F5F9;
        color: #1E293B;
        font-weight: 800;
        padding: 14px 18px;
        text-align: left;
        border-bottom: 1.5px solid #CBD5E1;
        text-transform: uppercase;
        font-size: 0.78rem;
        letter-spacing: 0.05em;
    }
    .custom-table td {
        padding: 14px 18px;
        border-bottom: 1px solid #E2E8F0;
        color: #0F172A;
        font-weight: 600;
        font-size: 0.93rem;
    }

    hr { border-color: #CBD5E1 !important; margin: 28px 0 !important; }

    /* --- OPTIMISATION ET RESPONSIVITÉ MOBILE --- */
    @media (max-width: 768px) {
        .block-container {
            padding-top: 1rem !important;
            padding-bottom: 1rem !important;
            padding-left: 0.75rem !important;
            padding-right: 0.75rem !important;
        }
        .brand-banner {
            padding: 16px 20px !important;
            flex-direction: column !important;
            align-items: flex-start !important;
            gap: 12px !important;
            border-radius: 16px !important;
        }
        .brand-title {
            font-size: 1.45rem !important;
        }
        .brand-subtitle {
            font-size: 0.8rem !important;
        }
        div[data-testid="stRadio"]:has(input[name="main_nav_radio"]) > div {
            gap: 8px !important;
        }
        div[data-testid="stRadio"]:has(input[name="main_nav_radio"]) label {
            padding: 10px 14px !important;
            font-size: 0.82rem !important;
            flex: 1 1 calc(50% - 8px) !important;
            text-align: center !important;
            justify-content: center !important;
        }
        div[data-testid="stMetric"] {
            padding: 12px 14px !important;
            margin-bottom: 8px !important;
        }
        div[data-testid="stMetricValue"] {
            font-size: 1.25rem !important;
        }
        div[data-testid="stMetricLabel"] {
            font-size: 0.7rem !important;
        }
        .custom-table {
            display: block !important;
            overflow-x: auto !important;
            white-space: nowrap !important;
        }
    }
    </style>
""", unsafe_allow_html=True)

# --- CACHE DES DONNÉES FINANCIÈRES EN TEMPS RÉEL SÉCURISÉ (TTL = 10s) ---
@st.cache_data(ttl=3600)
def rechercher_symbole_universel(query):
    if not query or len(query.strip()) < 1: return []
    url = f"https://query2.finance.yahoo.com/v1/finance/search?q={query}&quotesCount=10&newsCount=0"
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'}
    try:
        r = requests.get(url, headers=headers, timeout=3)
        data = r.json()
        results = []
        for quote in data.get('quotes', []):
            symbol = quote.get('symbol')
            shortname = quote.get('shortname') or quote.get('longname') or symbol
            exch = quote.get('exchDisp') or quote.get('exchange') or ''
            type_disp = quote.get('typeDisp') or ''
            
            if symbol and (type_disp in ['Equity', 'ETF', 'Action', 'Stock'] or not type_disp):
                if est_marche_nord_americain(symbol, exch_code=quote.get('exchange', ''), exch_disp=exch):
                    results.append({'symbol': symbol, 'label': f"{shortname} ({symbol}) — {exch}"})
        return results
    except Exception:
        return []

@st.cache_data(ttl=10, show_spinner=False)
def obtenir_prix_actuel(ticker_symbol):
    try:
        t = yf.Ticker(ticker_symbol)
        data = t.fast_info
        prix = data.get('lastPrice') or data.get('regularMarketPrice') or data.get('last_price')
        if prix is not None and not pd.isna(prix) and float(prix) > 0:
            return round(float(prix), 4)
        hist = t.history(period="1d")
        if not hist.empty:
            return round(float(hist['Close'].iloc[-1]), 4)
        return None
    except Exception:
        return None

@st.cache_data(ttl=10, show_spinner=False)
def obtenir_prix_groupes(tickers_list):
    if not tickers_list:
        return {}
    try:
        clean_tickers = list(set([str(t).strip().upper() for t in tickers_list if t and str(t).strip()]))
        if not clean_tickers:
            return {}
        
        data = yf.Tickers(" ".join(clean_tickers))
        prix_dict = {}
        for tk in clean_tickers:
            try:
                info = data.tickers[tk].fast_info
                px = info.get('lastPrice') or info.get('regularMarketPrice') or info.get('last_price')
                if px is not None and not pd.isna(px):
                    prix_dict[tk] = round(float(px), 4)
                else:
                    prix_dict[tk] = None
            except Exception:
                prix_dict[tk] = None
        return prix_dict
    except Exception:
        return {}

@st.cache_data(ttl=10, show_spinner=False)
def obtenir_details_financiers(ticker_symbol):
    if not est_marche_nord_americain(ticker_symbol):
        return {"erreur": "non_na"}

    try:
        t = yf.Ticker(ticker_symbol)
        info = t.fast_info
        
        last = info.get('lastPrice') or info.get('regularMarketPrice') or info.get('last_price')
        if last is None or pd.isna(last) or float(last) <= 0:
            hist = t.history(period="2d")
            if not hist.empty:
                last = float(hist['Close'].iloc[-1])
            else:
                return None
        else:
            last = float(last)

        open_p = info.get('open') or info.get('openPrice')
        if open_p is None or pd.isna(open_p):
            hist = t.history(period="2d")
            if len(hist) >= 2:
                open_p = float(hist['Close'].iloc[-2])
            elif not hist.empty:
                open_p = float(hist['Open'].iloc[-1])
            else:
                open_p = last
        else:
            open_p = float(open_p)

        change = last - open_p
        change_pct = (change / open_p) * 100 if open_p > 0 else 0.0
        fmt = ".4f" if last < 1 else ".2f"

        high_p = info.get('dayHigh', last)
        low_p = info.get('dayLow', last)
        y_high = info.get('yearHigh', last)
        y_low = info.get('yearLow', last)

        return {
            "Prix": last, 
            "Variation": change, 
            "VariationPct": change_pct,
            "Ouverture":
