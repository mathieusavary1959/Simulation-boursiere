import streamlit as st
import yfinance as yf
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import xml.etree.ElementTree as ET
import requests
import uuid
from datetime import datetime
from zoneinfo import ZoneInfo
from sqlalchemy import text
import streamlit.components.v1 as components

# --- CONFIGURATION DE LA PAGE ---
st.set_page_config(page_title="Monde & Finance — Simulation Boursière", layout="wide")

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
            session.execute(text('''
                CREATE TABLE IF NOT EXISTS favoris (
                    username TEXT,
                    ticker TEXT,
                    PRIMARY KEY (username, ticker)
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

# --- DESIGN STYLE NETFLIX PREMIUM PLUS (COUCHE VISUELLE SEULEMENT) ---
st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Bebas+Neue&family=Work+Sans:wght@400;500;600;700;800&display=swap');

    html, body, [class*="css"] {
        font-family: 'Work Sans', -apple-system, BlinkMacSystemFont, sans-serif;
    }

    .stApp {
        background: radial-gradient(1200px 520px at 50% -8%, rgba(229, 9, 20, 0.16), rgba(20, 20, 20, 0) 62%), #141414 !important;
        background-color: #141414 !important;
        color: #FFFFFF !important;
    }

    #MainMenu, footer, header { visibility: hidden; }

    ::selection { background: #E50914; color: #FFFFFF; }

    ::-webkit-scrollbar { width: 10px; height: 10px; }
    ::-webkit-scrollbar-track { background: #141414; }
    ::-webkit-scrollbar-thumb { background: #3A3A3A; border-radius: 8px; }
    ::-webkit-scrollbar-thumb:hover { background: #E50914; }

    .stApp h1 { font-size: 2.7rem !important; }
    .stApp h2 { font-size: 2.3rem !important; }
    .stApp h3 { font-size: 2rem !important; }
    .stApp h1, .stApp h2, .stApp h3, .stApp h4, .stApp h5, .stApp h6 {
        font-family: 'Bebas Neue', 'Work Sans', sans-serif !important;
        font-weight: 400 !important;
        letter-spacing: 0.05em !important;
        color: #FFFFFF !important;
    }
    .stApp h3, .stApp h4, .stApp h5 {
        border-left: 4px solid #E50914;
        padding-left: 14px;
    }

    .stApp .stMarkdown p, .stApp .stMarkdown li {
        color: #FFFFFF;
    }
    div[data-testid="stWidgetLabel"] p, .stApp label {
        color: #FFFFFF !important;
        font-weight: 600 !important;
    }
    div[data-testid="stRadio"] label, div[data-testid="stRadio"] label p {
        color: #FFFFFF !important;
    }

    .brand-banner {
        background: linear-gradient(120deg, #000000 0%, #161616 55%, #2B0A0C 100%);
        border-radius: 16px;
        padding: 28px 36px;
        color: #FFFFFF;
        margin-bottom: 24px;
        box-shadow: 0 22px 44px -18px rgba(0, 0, 0, 0.95), 0 0 44px -8px rgba(229, 9, 20, 0.65);
        display: flex;
        justify-content: space-between;
        align-items: center;
        border: 1px solid rgba(229, 9, 20, 0.5);
        border-bottom: 3px solid #E50914;
        animation: fadeDown 0.55s ease both;
        position: relative;
        overflow: hidden;
    }
    .brand-banner::after {
        content: "";
        position: absolute;
        top: 0;
        left: -80%;
        width: 55%;
        height: 100%;
        background: linear-gradient(105deg, rgba(255,255,255,0) 0%, rgba(255,255,255,0.10) 50%, rgba(255,255,255,0) 100%);
        transform: skewX(-18deg);
        animation: sheen 4.5s ease-in-out infinite;
        pointer-events: none;
    }
    .brand-title {
        font-family: 'Bebas Neue', 'Work Sans', sans-serif;
        font-size: 3.1rem;
        letter-spacing: 0.06em;
        line-height: 1;
        color: #FFFFFF;
        margin: 0;
        text-shadow: 0 0 28px rgba(229, 9, 20, 0.6);
    }
    .brand-subtitle {
        color: #FFFFFF;
        font-size: 0.92rem;
        font-weight: 500;
        margin-top: 6px;
    }
    .brand-badge {
        background: #E50914;
        border: none;
        padding: 7px 18px;
        border-radius: 6px;
        font-size: 0.8rem;
        font-weight: 800;
        color: #FFFFFF;
        letter-spacing: 0.08em;
        text-transform: uppercase;
        white-space: nowrap;
        box-shadow: 0 8px 20px -8px rgba(229, 9, 20, 0.9);
    }

    @keyframes fadeDown {
        from { opacity: 0; transform: translateY(-8px); }
        to { opacity: 1; transform: translateY(0); }
    }
    @keyframes sheen {
        0%, 55% { left: -80%; }
        85%, 100% { left: 130%; }
    }
    @keyframes fadeUp {
        from { opacity: 0; transform: translateY(10px); }
        to { opacity: 1; transform: translateY(0); }
    }
    @media (prefers-reduced-motion: reduce) {
        .brand-banner, .brand-banner::after, .kpi-card, .podium-card,
        .custom-table, .mon-rang, .kpi-up, .kpi-down { animation: none !important; }
        .kpi-card { transition: none !important; }
    }

    /* --- CARTES KPI SUR MESURE --- */
    .kpi-card {
        background: linear-gradient(180deg, #262626 0%, #1A1A1A 100%);
        border: 1px solid rgba(255, 255, 255, 0.12);
        border-top: 3px solid #E50914;
        border-radius: 14px;
        padding: 18px 22px 16px 22px;
        box-shadow: 0 16px 32px -14px rgba(0, 0, 0, 0.9);
        transition: transform 0.3s ease, box-shadow 0.3s ease, border-color 0.3s ease;
        animation: fadeUp 0.5s ease both;
        margin-bottom: 8px;
    }
    div[data-testid="stHorizontalBlock"] > div:nth-child(1) .kpi-card { animation-delay: 0.00s; }
    div[data-testid="stHorizontalBlock"] > div:nth-child(2) .kpi-card { animation-delay: 0.08s; }
    div[data-testid="stHorizontalBlock"] > div:nth-child(3) .kpi-card { animation-delay: 0.16s; }
    div[data-testid="stHorizontalBlock"] > div:nth-child(4) .kpi-card { animation-delay: 0.24s; }
    .kpi-card:hover {
        transform: translateY(-4px) scale(1.03);
        border-color: rgba(229, 9, 20, 0.65);
        border-top-color: #E50914;
        box-shadow: 0 26px 44px -14px rgba(0, 0, 0, 0.95), 0 0 32px -6px rgba(229, 9, 20, 0.7);
    }
    .kpi-label {
        color: #FFFFFF;
        font-size: 0.78rem;
        text-transform: uppercase;
        font-weight: 800;
        letter-spacing: 0.08em;
        margin-bottom: 6px;
    }
    .kpi-value {
        font-family: 'Bebas Neue', 'Work Sans', sans-serif;
        font-size: 2.45rem;
        line-height: 1;
        color: #FFFFFF;
        letter-spacing: 0.03em;
        font-variant-numeric: tabular-nums;
        white-space: nowrap;
    }
    .kpi-delta {
        display: inline-block;
        margin-top: 8px;
        padding: 3px 12px;
        border-radius: 999px;
        font-size: 0.85rem;
        font-weight: 800;
        font-variant-numeric: tabular-nums;
    }
    .kpi-delta.up {
        background: rgba(16, 185, 129, 0.18);
        color: #34D399;
        border: 1px solid rgba(16, 185, 129, 0.55);
    }
    .kpi-delta.down {
        background: rgba(239, 68, 68, 0.16);
        color: #F87171;
        border: 1px solid rgba(239, 68, 68, 0.55);
    }
    .kpi-up {
        border-color: rgba(16, 185, 129, 0.55);
        border-top-color: #34D399;
        background: linear-gradient(180deg, rgba(16, 185, 129, 0.18) 0%, #1A1A1A 62%);
        box-shadow: 0 16px 32px -14px rgba(0, 0, 0, 0.9), 0 0 46px -4px rgba(16, 185, 129, 0.8);
        animation: fadeUp 0.5s ease both, pulseUp 2.8s ease-in-out 0.6s infinite;
    }
    .kpi-down {
        border-color: rgba(239, 68, 68, 0.55);
        border-top-color: #F87171;
        background: linear-gradient(180deg, rgba(239, 68, 68, 0.18) 0%, #1A1A1A 62%);
        box-shadow: 0 16px 32px -14px rgba(0, 0, 0, 0.9), 0 0 46px -4px rgba(239, 68, 68, 0.8);
        animation: fadeUp 0.5s ease both, pulseDown 2.8s ease-in-out 0.6s infinite;
    }
    @keyframes pulseUp {
        0%, 100% { box-shadow: 0 16px 32px -14px rgba(0, 0, 0, 0.9), 0 0 34px -6px rgba(16, 185, 129, 0.55); }
        50% { box-shadow: 0 16px 32px -14px rgba(0, 0, 0, 0.9), 0 0 56px -2px rgba(16, 185, 129, 0.95); }
    }
    @keyframes pulseDown {
        0%, 100% { box-shadow: 0 16px 32px -14px rgba(0, 0, 0, 0.9), 0 0 34px -6px rgba(239, 68, 68, 0.55); }
        50% { box-shadow: 0 16px 32px -14px rgba(0, 0, 0, 0.9), 0 0 56px -2px rgba(239, 68, 68, 0.95); }
    }
    .kpi-up .kpi-value { color: #34D399; }
    .kpi-down .kpi-value { color: #F87171; }
    .kpi-up:hover {
        border-color: rgba(16, 185, 129, 0.8);
        box-shadow: 0 26px 44px -14px rgba(0, 0, 0, 0.95), 0 0 54px -4px rgba(16, 185, 129, 0.9);
    }
    .kpi-down:hover {
        border-color: rgba(239, 68, 68, 0.8);
        box-shadow: 0 26px 44px -14px rgba(0, 0, 0, 0.95), 0 0 54px -4px rgba(239, 68, 68, 0.9);
    }

    /* --- CARTE-CITATION (MARCHÉ) --- */
    .quote-card {
        display: flex;
        align-items: center;
        gap: 22px;
        flex-wrap: wrap;
        background: linear-gradient(120deg, #1E1E1E 0%, #161616 100%);
        border: 1px solid #2E2E2E;
        border-left: 4px solid #E50914;
        border-radius: 14px;
        padding: 16px 24px;
        margin-bottom: 10px;
        box-shadow: 0 16px 32px -16px rgba(0, 0, 0, 0.9);
        animation: fadeUp 0.5s ease both;
        position: relative;
        overflow: hidden;
    }
    .quote-card::after {
        content: attr(data-tk);
        position: absolute;
        right: 14px;
        top: 50%;
        transform: translateY(-50%);
        font-family: 'Bebas Neue', 'Work Sans', sans-serif;
        font-size: 5.4rem;
        letter-spacing: 0.04em;
        color: rgba(255, 255, 255, 0.05);
        pointer-events: none;
    }
    .quote-card > div { position: relative; z-index: 1; }
    .quote-ticker {
        font-family: 'Bebas Neue', 'Work Sans', sans-serif;
        font-size: 2.9rem;
        line-height: 1;
        color: #FFFFFF;
        letter-spacing: 0.04em;
    }
    .quote-price {
        font-family: 'Bebas Neue', 'Work Sans', sans-serif;
        font-size: 2.5rem;
        line-height: 1;
        color: #FFFFFF;
        font-variant-numeric: tabular-nums;
    }
    .quote-var {
        padding: 5px 14px;
        border-radius: 999px;
        font-weight: 800;
        font-variant-numeric: tabular-nums;
    }
    .quote-var.up {
        background: rgba(16, 185, 129, 0.18);
        color: #34D399;
        border: 1px solid rgba(16, 185, 129, 0.55);
    }
    .quote-var.down {
        background: rgba(239, 68, 68, 0.16);
        color: #F87171;
        border: 1px solid rgba(239, 68, 68, 0.55);
    }
    .quote-card.up {
        box-shadow: 0 16px 32px -16px rgba(0, 0, 0, 0.9), 0 0 36px -8px rgba(16, 185, 129, 0.55);
    }
    .quote-card.down {
        box-shadow: 0 16px 32px -16px rgba(0, 0, 0, 0.9), 0 0 36px -8px rgba(239, 68, 68, 0.55);
    }

    /* --- PODIUM DU CLASSEMENT --- */
    .podium-card {
        border: 1px solid rgba(255, 255, 255, 0.12);
        border-top: 4px solid #FFFFFF;
        border-radius: 14px;
        padding: 16px 20px;
        margin-bottom: 10px;
        background: linear-gradient(180deg, #262626 0%, #1A1A1A 100%);
        box-shadow: 0 16px 32px -14px rgba(0, 0, 0, 0.9);
        animation: fadeUp 0.5s ease both;
    }
    .podium-or {
        border-top-color: #FFD700;
        background: linear-gradient(180deg, rgba(255, 215, 0, 0.38) 0%, rgba(255, 215, 0, 0.14) 45%, rgba(26, 26, 26, 1) 100%);
        box-shadow: 0 16px 32px -14px rgba(0, 0, 0, 0.9), 0 0 30px -6px rgba(255, 215, 0, 0.55);
    }
    .podium-or .podium-rang { color: #FFD700; }
    .podium-argent {
        border-top-color: #C0C0C0;
        background: linear-gradient(180deg, rgba(192, 192, 192, 0.34) 0%, rgba(192, 192, 192, 0.12) 45%, rgba(26, 26, 26, 1) 100%);
        box-shadow: 0 16px 32px -14px rgba(0, 0, 0, 0.9), 0 0 30px -6px rgba(192, 192, 192, 0.5);
    }
    .podium-argent .podium-rang { color: #E8E8E8; }
    .podium-bronze {
        border-top-color: #CD7F32;
        background: linear-gradient(180deg, rgba(205, 127, 50, 0.38) 0%, rgba(205, 127, 50, 0.14) 45%, rgba(26, 26, 26, 1) 100%);
        box-shadow: 0 16px 32px -14px rgba(0, 0, 0, 0.9), 0 0 30px -6px rgba(205, 127, 50, 0.55);
    }
    .podium-bronze .podium-rang { color: #E09A5A; }
    .podium-rang {
        font-family: 'Bebas Neue', 'Work Sans', sans-serif;
        font-size: 2.1rem;
        line-height: 1;
        color: #FFFFFF;
    }
    .podium-nom {
        font-weight: 800;
        font-size: 1.05rem;
        color: #FFFFFF;
        margin-top: 4px;
    }
    .podium-val {
        font-family: 'Bebas Neue', 'Work Sans', sans-serif;
        font-size: 1.55rem;
        line-height: 1.1;
        color: #FFFFFF;
        font-variant-numeric: tabular-nums;
    }
    .podium-perf {
        font-weight: 700;
        font-size: 0.9rem;
        color: #FFFFFF;
        font-variant-numeric: tabular-nums;
    }
    .podium-1 { animation-delay: 0.00s; }
    .podium-2 { animation-delay: 0.15s; }
    .podium-3 { animation-delay: 0.30s; }
    .podium-card {
        position: relative;
        overflow: hidden;
        transition: box-shadow 0.3s ease, transform 0.3s ease;
    }
    .podium-card > div { position: relative; z-index: 1; }
    .podium-or:hover {
        transform: translateY(-3px);
        box-shadow: 0 20px 38px -14px rgba(0, 0, 0, 0.95), 0 0 46px -4px rgba(255, 215, 0, 0.8);
    }
    .podium-argent:hover {
        transform: translateY(-3px);
        box-shadow: 0 20px 38px -14px rgba(0, 0, 0, 0.95), 0 0 46px -4px rgba(192, 192, 192, 0.75);
    }
    .podium-bronze:hover {
        transform: translateY(-3px);
        box-shadow: 0 20px 38px -14px rgba(0, 0, 0, 0.95), 0 0 46px -4px rgba(205, 127, 50, 0.8);
    }

    .mon-rang {
        display: flex;
        align-items: center;
        gap: 18px;
        flex-wrap: wrap;
        background: #1E1E1E;
        border: 1px solid #2E2E2E;
        border-left: 4px solid #E50914;
        border-radius: 12px;
        padding: 12px 20px;
        margin: 4px 0 14px 0;
    }
    .mon-rang-label {
        text-transform: uppercase;
        font-weight: 800;
        letter-spacing: 0.08em;
        font-size: 0.78rem;
        color: #FFFFFF;
    }
    .mon-rang-val {
        font-family: 'Bebas Neue', 'Work Sans', sans-serif;
        font-size: 1.9rem;
        line-height: 1;
        color: #FFFFFF;
    }
    .mon-rang-detail {
        font-weight: 700;
        color: #FFFFFF;
        font-variant-numeric: tabular-nums;
    }

    /* --- ENTRÉES ANIMÉES DES BLOCS SUR MESURE --- */
    .custom-table, .mon-rang {
        animation: fadeUp 0.5s ease both;
    }

    /* --- NAVIGATION EN BOUTONS --- */
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
        background: #1F1F1F !important;
        border-radius: 999px !important;
        color: #FFFFFF !important;
        padding: 11px 22px !important;
        font-weight: 700 !important;
        font-size: 0.92rem !important;
        border: 1px solid #3A3A3A !important;
        box-shadow: 0 6px 16px -8px rgba(0, 0, 0, 0.85) !important;
        transition: all 0.15s ease !important;
        cursor: pointer !important;
        margin: 0 !important;
    }
    div[data-testid="stRadio"]:has(input[name="main_nav_radio"]) label:hover {
        color: #FFFFFF !important;
        border-color: rgba(229, 9, 20, 0.75) !important;
        transform: translateY(-2px) scale(1.03);
    }
    div[data-testid="stRadio"]:has(input[name="main_nav_radio"]) label:has(input:checked) {
        background: linear-gradient(180deg, #E50914 0%, #B00610 100%) !important;
        color: #FFFFFF !important;
        box-shadow: 0 10px 24px -8px rgba(229, 9, 20, 0.9) !important;
        border: 1px solid rgba(255, 130, 130, 0.45) !important;
        transform: translateY(0px) !important;
    }
    div[data-testid="stRadio"]:has(input[name="main_nav_radio"]) div[data-testid="stMarkdownContainer"] p {
        color: inherit !important;
        font-weight: 700 !important;
        font-size: 0.92rem !important;
    }

    /* Navigation qui reste en haut lors du défilement */
    .block-container div[data-testid="stVerticalBlock"] > div:has(input[name="main_nav_radio"]) {
        position: sticky;
        top: 0;
        z-index: 1000;
        background: rgba(20, 20, 20, 0.96);
        padding-top: 6px;
        border-bottom: 1px solid rgba(255, 255, 255, 0.08);
    }

    /* Boutons standards */
    .stButton>button, div[data-testid="stFormSubmitButton"]>button {
        border-radius: 10px !important;
        background: linear-gradient(180deg, #E50914 0%, #B00610 100%) !important;
        color: #FFFFFF !important;
        font-weight: 700 !important;
        border: 1px solid rgba(255, 130, 130, 0.4) !important;
        padding: 12px 24px !important;
        box-shadow: 0 10px 22px -10px rgba(229, 9, 20, 0.85) !important;
        transition: all 0.15s ease !important;
    }
    .stButton>button:hover, div[data-testid="stFormSubmitButton"]>button:hover {
        filter: brightness(1.15);
        transform: translateY(-2px) scale(1.02);
        box-shadow: 0 14px 26px -10px rgba(229, 9, 20, 0.95) !important;
    }
    .stButton>button:active, div[data-testid="stFormSubmitButton"]>button:active {
        transform: translateY(0px);
    }

    /* Bouton favoris : jaune ambre pour le distinguer du rouge/vert */
    div[data-testid="stButton"] button[kind="primary"] {
        background: linear-gradient(180deg, #F7C948 0%, #E0A800 100%) !important;
        border: 1px solid rgba(255, 220, 120, 0.55) !important;
        color: #1A1A1A !important;
        box-shadow: 0 10px 22px -10px rgba(247, 201, 72, 0.8) !important;
    }
    div[data-testid="stButton"] button[kind="primary"]:hover {
        filter: brightness(1.08);
        box-shadow: 0 14px 26px -10px rgba(247, 201, 72, 0.95) !important;
    }
    div[data-testid="stButton"] button[kind="primary"] p {
        color: #1A1A1A !important;
    }

    /* Boutons-liens vers les sites de finance */
    div[data-testid="stLinkButton"] > a {
        display: inline-flex !important;
        justify-content: center !important;
        align-items: center !important;
        width: 100% !important;
        border-radius: 9px !important;
        background: linear-gradient(180deg, #12161C 0%, #0B0E13 100%) !important;
        color: #EAF6FF !important;
        font-weight: 700 !important;
        font-size: 0.9rem !important;
        letter-spacing: 0.03em !important;
        text-decoration: none !important;
        border: 1px solid rgba(0, 191, 255, 0.75) !important;
        padding: 9px 16px !important;
        box-shadow: 0 0 20px -2px rgba(0, 191, 255, 0.55), inset 0 0 14px rgba(0, 191, 255, 0.12) !important;
        transition: all 0.15s ease !important;
    }
    div[data-testid="stLinkButton"] > a:hover {
        border-color: rgba(150, 228, 255, 1) !important;
        color: #FFFFFF !important;
        transform: translateY(-2px);
        box-shadow: 0 0 30px 0px rgba(0, 191, 255, 0.85), inset 0 0 18px rgba(0, 191, 255, 0.22) !important;
    }

    .stTextInput>div>div>input, .stNumberInput>div>div>input, .stSelectbox>div>div {
        background-color: #1F1F1F !important;
        color: #FFFFFF !important;
        border-radius: 10px !important;
        border: 1.5px solid #3A3A3A !important;
        padding: 11px 16px !important;
        font-weight: 600 !important;
    }
    .stTextInput>div>div>input:focus, .stNumberInput>div>div>input:focus {
        border-color: #E50914 !important;
        box-shadow: 0 0 0 1px #E50914 !important;
    }
    .stTextInput input::placeholder, .stNumberInput input::placeholder {
        color: #FFFFFF !important;
        opacity: 0.65;
    }
    .stSelectbox div[data-baseweb="select"] div {
        color: #FFFFFF !important;
    }

    div[data-baseweb="popover"] {
        background-color: #1F1F1F !important;
        border: 1px solid #3A3A3A !important;
        border-radius: 12px !important;
    }
    div[data-baseweb="popover"] li, div[data-baseweb="popover"] div {
        color: #FFFFFF !important;
    }

    div[data-testid="stDataFrame"] {
        border: 1px solid #2E2E2E !important;
        border-radius: 14px !important;
        overflow: hidden !important;
        box-shadow: 0 14px 30px -16px rgba(0, 0, 0, 0.9) !important;
    }

    div[data-testid="stAlert"] {
        border-radius: 12px !important;
        border: 1px solid rgba(255, 255, 255, 0.14) !important;
    }
    div[data-testid="stAlert"] p {
        color: #FFFFFF !important;
    }

    /* Carte de connexion (page d'accueil) */
    div[data-testid="stTabs"] {
        background: linear-gradient(180deg, #1E1E1E 0%, #161616 100%);
        border: 1px solid #2E2E2E;
        border-top: 3px solid #E50914;
        border-radius: 16px;
        padding: 12px 24px 24px 24px;
        box-shadow: 0 24px 48px -18px rgba(0, 0, 0, 0.95), 0 0 34px -12px rgba(229, 9, 20, 0.45);
        animation: fadeUp 0.55s ease both;
    }
    div[data-baseweb="tab-list"] { gap: 10px !important; }
    button[data-baseweb="tab"] {
        color: #FFFFFF !important;
        font-weight: 700 !important;
        font-size: 1rem !important;
    }
    button[data-baseweb="tab"][aria-selected="true"] { color: #FFFFFF !important; }
    div[data-baseweb="tab-highlight"] { background-color: #E50914 !important; }
    div[data-baseweb="tab-border"] { background-color: rgba(255, 255, 255, 0.14) !important; }

    .custom-table {
        width: 100%;
        border-collapse: collapse;
        background-color: #1A1A1A;
        border-radius: 14px;
        overflow: hidden;
        border: 1px solid #2E2E2E;
        margin-bottom: 24px;
        box-shadow: 0 14px 30px -16px rgba(0, 0, 0, 0.9);
    }
    .custom-table th {
        background-color: #262626;
        color: #FFFFFF;
        font-weight: 800;
        padding: 14px 18px;
        text-align: left;
        border-bottom: 2px solid #E50914;
        text-transform: uppercase;
        font-size: 0.78rem;
        letter-spacing: 0.05em;
    }
    .custom-table td {
        padding: 14px 18px;
        border-bottom: 1px solid rgba(255, 255, 255, 0.07);
        color: #FFFFFF;
        font-weight: 600;
        font-size: 0.93rem;
        font-variant-numeric: tabular-nums;
    }
    .custom-table tbody tr { transition: background-color 0.15s ease; }
    .custom-table tbody tr:hover { background-color: rgba(229, 9, 20, 0.10); }

    @media print {
        .custom-table { background-color: #FFFFFF !important; }
        .custom-table th, .custom-table td { color: #000000 !important; }
    }

    hr { border-color: rgba(255, 255, 255, 0.14) !important; margin: 28px 0 !important; }
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

@st.cache_data(ttl=60, show_spinner=False)
def obtenir_donnees_favoris(tickers_tuple):
    """Prix + variation du jour pour les favoris, en un seul appel groupé. {ticker: (prix, var_pct)}"""
    tickers_list = list(tickers_tuple)
    if not tickers_list:
        return {}
    try:
        clean = list(set([str(t).strip().upper() for t in tickers_list if t and str(t).strip()]))
        if not clean:
            return {}
        data = yf.Tickers(" ".join(clean))
        out = {}
        for tk in clean:
            try:
                fi = data.tickers[tk].fast_info
                px = fi.get('lastPrice') or fi.get('regularMarketPrice') or fi.get('last_price')
                op = fi.get('open') or fi.get('openPrice')
                if px is not None and not pd.isna(px) and float(px) > 0:
                    px = float(px)
                    if op is not None and not pd.isna(op) and float(op) > 0:
                        vp = (px - float(op)) / float(op) * 100
                    else:
                        vp = 0.0
                    out[tk] = (round(px, 4), round(vp, 2))
                else:
                    out[tk] = (None, None)
            except Exception:
                out[tk] = (None, None)
        return out
    except Exception:
        return {}

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

@st.cache_data(ttl=900, show_spinner=False)
def obtenir_nouvelles(ticker_symbol):
    """Actualités du titre via Google News RSS (5 max). 1 appel par titre aux 15 min, partagé entre élèves."""
    try:
        import urllib.parse, urllib.request
        q = urllib.parse.quote_plus(f"{ticker_symbol} stock")
        url = f"https://news.google.com/rss/search?q={q}&hl=en-US&gl=US&ceid=US:en"
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=15) as r:
            data = r.read()
        root = ET.fromstring(data)
        out = []
        for it in root.findall('.//item')[:5]:
            titre = it.findtext('title') or ''
            lien = it.findtext('link') or ''
            src_el = it.find('source')
            pub = (src_el.text or '') if src_el is not None else ''
            if ' - ' in titre:
                titre = titre.rsplit(' - ', 1)[0]
            if titre and lien:
                out.append({'title': titre, 'link': lien, 'publisher': pub})
        return out
    except Exception:
        return []

@st.cache_data(ttl=300, show_spinner=False)
def cloture_veille(ticker_symbol):
    """Prix de clôture de la veille (ou None si indisponible).
    Fonctionne avant, pendant et après les heures de marché."""
    try:
        t = yf.Ticker(ticker_symbol)
        # previousClose de fast_info = clôture officielle précédente, fiable
        # même en premarket
        data = t.fast_info
        pc = data.get('previousClose')
        if pc is not None and not pd.isna(pc) and float(pc) > 0:
            return round(float(pc), 4)
        # Repli : historique 5 jours, prendre l'avant-dernière clôture
        # (la dernière peut être la séance du jour en cours)
        hist = t.history(period="5d")
        if hist is None or hist.empty or len(hist) < 2:
            return None
        return round(float(hist['Close'].iloc[-2]), 4)
    except Exception:
        return None


def cloture_avant_date(ticker_symbol, date_limite):
    """Clôture du dernier jour de bourse strictement avant date_limite.
    Ex : date_limite='2026-10-12' -> clôture du vendredi 2026-10-09."""
    try:
        t = yf.Ticker(ticker_symbol)
        hist = t.history(start="2026-10-01", end=date_limite)
        if hist is None or hist.empty:
            return None
        return round(float(hist['Close'].iloc[-1]), 4)
    except Exception:
        return None


def analyser_violations_9h30(date_debut, date_fin):
    """Détecte les achats avant 9h30 (heure Toronto) entre date_debut et date_fin
    (incluses, format 'AAAA-MM-JJ') sur des actions dont la clôture du dernier
    jour de bourse précédent était sous 5 $. Retourne un DataFrame des
    transactions fautives, avec une colonne 'date' (jour de la transaction)."""
    from datetime import date as _date, timedelta as _td
    d0 = _date.fromisoformat(date_debut)
    d1 = _date.fromisoformat(date_fin)
    morceaux = []
    j = d0
    while j <= d1:
        ds = j.isoformat()
        tx = conn.query(
            "SELECT id, username, ticker, shares, price, total, timestamp FROM transactions "
            f"WHERE timestamp >= '{ds} 00:00:00' AND timestamp < '{ds} 09:30:00' "
            "AND shares > 0 ORDER BY id",
            ttl=0
        )
        if not tx.empty:
            clotures = {}
            for tk in tx['ticker'].unique().tolist():
                clotures[str(tk)] = cloture_avant_date(str(tk), ds)
            tx['cloture_veille'] = tx['ticker'].map(clotures)
            tx['date'] = ds
            viol = tx[(tx['cloture_veille'].notna()) & (tx['cloture_veille'] < 5.0)].copy()
            if not viol.empty:
                morceaux.append(viol)
        j += _td(days=1)
    if not morceaux:
        return pd.DataFrame()
    return pd.concat(morceaux, ignore_index=True)


def calculer_gains_9h30(violations_df):
    """Ajoute à chaque transaction fautive : 'gain_estime' (ventes du jour +
    valeur actuelle du reliquat - coût des achats fautifs), 'heures_achat'
    (heures des achats fautifs) et 'heures_vente' (heures des reventes le jour
    même, ou '-'). Permet de juger si l'infraction a vraiment profité."""
    if violations_df.empty:
        return violations_df
    tickers = violations_df['ticker'].unique().tolist()
    prix_actuels = obtenir_prix_groupes(tickers)
    gains, h_achats, h_ventes, p_achats = {}, {}, {}, {}
    for (ds, u, tk), grp in violations_df.groupby(['date', 'username', 'ticker']):
        cout = float(grp['total'].sum())
        q_achats = int(grp['shares'].sum())
        heures_a = sorted(set(str(t).split(' ')[1] for t in grp['timestamp']))
        prix_a = sorted(set(f"{float(p):.2f}" for p in grp['price']))
        ventes = conn.query(
            "SELECT shares, total, timestamp FROM transactions WHERE username=:u AND ticker=:t "
            f"AND timestamp >= '{ds} 00:00:00' AND timestamp < '{ds} 23:59:59' AND shares < 0",
            params={"u": str(u), "t": str(tk)}, ttl=0
        )
        q_vendues = int((-ventes['shares']).sum()) if not ventes.empty else 0
        tot_vendus = float(ventes['total'].sum()) if not ventes.empty else 0.0
        heures_v = sorted(set(str(t).split(' ')[1] for t in ventes['timestamp'])) if not ventes.empty else []
        reliquat = max(q_achats - q_vendues, 0)
        px = prix_actuels.get(str(tk).upper())
        val_reliquat = reliquat * px if px else 0.0
        cle = (ds, str(u), str(tk))
        gains[cle] = (tot_vendus + val_reliquat) - cout
        h_achats[cle] = ", ".join(heures_a)
        h_ventes[cle] = ", ".join(heures_v) if heures_v else "-"
        p_achats[cle] = ", ".join(prix_a)
    violations_df['gain_estime'] = violations_df.apply(
        lambda r: gains.get((r['date'], str(r['username']), str(r['ticker'])), 0.0), axis=1
    )
    violations_df['heures_achat'] = violations_df.apply(
        lambda r: h_achats.get((r['date'], str(r['username']), str(r['ticker'])), ""), axis=1
    )
    violations_df['heures_vente'] = violations_df.apply(
        lambda r: h_ventes.get((r['date'], str(r['username']), str(r['ticker'])), "-"), axis=1
    )
    violations_df['prix_achat'] = violations_df.apply(
        lambda r: p_achats.get((r['date'], str(r['username']), str(r['ticker'])), ""), axis=1
    )
    return violations_df


def executer_annulation_9h30(violations_df):
    """Annule toutes les transactions du jour fautif pour chaque triplet
    (élève, action, date), comme si elles n'avaient jamais existé : cash
    ajusté, transactions supprimées, portefeuille recalculé depuis les
    transactions restantes. Retourne (nb_cas, nb_transactions, total_cash)."""
    triplets = violations_df[['username', 'ticker', 'date']].drop_duplicates()
    plans = []
    for _, row in triplets.iterrows():
        u, tk, ds = str(row['username']), str(row['ticker']), str(row['date'])
        toutes = conn.query(
            "SELECT id, shares, price, total, timestamp FROM transactions "
            "WHERE username=:u AND ticker=:t ORDER BY id",
            params={"u": u, "t": tk}, ttl=0
        )
        if toutes.empty:
            continue
        a_annuler = toutes[
            (toutes['timestamp'] >= f'{ds} 00:00:00') &
            (toutes['timestamp'] < f'{ds} 23:59:59')
        ]
        if a_annuler.empty:
            continue
        restantes = toutes.drop(a_annuler.index)
        ids_annuler = [int(i) for i in a_annuler['id'].tolist()]
        cash_delta = 0.0
        for _, t in a_annuler.iterrows():
            cash_delta += float(t['total']) if int(t['shares']) > 0 else -float(t['total'])
        achats = restantes[restantes['shares'] > 0]
        q_achats = int(achats['shares'].sum()) if not achats.empty else 0
        q_ventes = int((-restantes[restantes['shares'] < 0]['shares']).sum()) if not restantes.empty else 0
        new_shares = q_achats - q_ventes
        new_avg = 0.0
        if q_achats > 0 and new_shares > 0:
            new_avg = float((achats['shares'] * achats['price']).sum() / q_achats)
        plans.append({
            'username': u, 'ticker': tk, 'date': ds, 'ids': ids_annuler,
            'cash_delta': cash_delta, 'new_shares': max(new_shares, 0),
            'new_avg': new_avg, 'nb_tx': len(ids_annuler),
            'anomalie': new_shares < 0
        })
    nb_tx_total = 0
    with conn.session as session:
        for p in plans:
            session.execute(
                text("UPDATE users SET cash = cash + :d WHERE username = :u"),
                {"d": p['cash_delta'], "u": p['username']}
            )
            for tx_id in p['ids']:
                session.execute(text("DELETE FROM transactions WHERE id = :i"), {"i": tx_id})
            session.execute(
                text("DELETE FROM portfolio WHERE username = :u AND ticker = :t"),
                {"u": p['username'], "t": p['ticker']}
            )
            if p['new_shares'] > 0:
                session.execute(
                    text("INSERT INTO portfolio (username, ticker, shares, avg_price) "
                         "VALUES (:u, :t, :s, :p)"),
                    {"u": p['username'], "t": p['ticker'], "s": p['new_shares'], "p": p['new_avg']}
                )
            nb_tx_total += p['nb_tx']
        session.commit()
    total_cash = sum(p['cash_delta'] for p in plans)
    return len(plans), nb_tx_total, total_cash


def achat_penny_stock_bloque(ticker_symbol):
    """Vrai si l'action clôturait sous 5 $ la veille ET qu'on est avant
    l'ouverture à 9h30. Dès 9h30, tout est permis."""
    maintenant = datetime.now(ZoneInfo("America/Toronto"))
    minutes = maintenant.hour * 60 + maintenant.minute
    if minutes >= 9 * 60 + 30:
        return False  # marché ouvert : tout est permis
    veille = cloture_veille(ticker_symbol)
    return veille is not None and veille < 5.0

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
            "Ouverture": f"${open_p:{fmt}}",
            "Plus Haut": f"${high_p:{fmt}}",
            "Plus Bas": f"${low_p:{fmt}}",
            "52 sem. Haut": f"${y_high:{fmt}}",
            "52 sem. Bas": f"${y_low:{fmt}}"
        }
    except Exception:
        return None

@st.cache_data(ttl=300, show_spinner=False)
def obtenir_historique(ticker_symbol, periode):
    try:
        interval = "5m" if periode == "1d" else ("15m" if periode == "5d" else "1d")
        return yf.Ticker(ticker_symbol).history(period=periode, interval=interval)
    except Exception: return None

# --- CACHE DES CALCULS DU CLASSEMENT (TTL = 30s) ---
@st.cache_data(ttl=30, show_spinner=False)
def obtenir_donnees_classement(grp_filter):
    if grp_filter == "Tous les groupes":
        users_df = conn.query("SELECT username, cash, groupe FROM users", ttl=0)
    else:
        users_df = conn.query("SELECT username, cash, groupe FROM users WHERE groupe=:g", params={"g": grp_filter}, ttl=0)

    if users_df.empty:
        return pd.DataFrame()

    all_positions_df = conn.query("SELECT username, ticker, shares, avg_price FROM portfolio", ttl=0)
    unique_tickers = list(all_positions_df['ticker'].unique()) if not all_positions_df.empty else []
    prix_dict = obtenir_prix_groupes(unique_tickers)

    lb = []
    for _, r in users_df.iterrows():
        u_name, u_cash, u_grp = r['username'], float(r['cash']), r['groupe']
        u_p = all_positions_df[all_positions_df['username'] == u_name] if not all_positions_df.empty else pd.DataFrame()

        u_val_act = 0.0
        if not u_p.empty:
            for _, row in u_p.iterrows():
                tk_sym = str(row['ticker']).upper()
                px = prix_dict.get(tk_sym)
                px_f = px if px is not None else float(row['avg_price'] or 0.0)
                u_val_act += px_f * row['shares']

        tot = u_cash + u_val_act
        perf = ((tot - 10000.00) / 10000.00) * 100
        lb.append({"Élève": u_name, "Groupe": u_grp, "Portefeuille": tot, "Performance": perf})

    if lb:
        df_lb = pd.DataFrame(lb).sort_values(by="Portefeuille", ascending=False).reset_index(drop=True)
        df_lb.index += 1
        df_lb['Rang'] = df_lb.index
        df_lb["Portefeuille"] = df_lb["Portefeuille"].map("${:,.2f}".format)
        df_lb["Performance"] = df_lb["Performance"].map("{:+.2f}%".format)
        return df_lb[['Rang', 'Élève', 'Groupe', 'Portefeuille', 'Performance']]
    return pd.DataFrame()

# --- SÉCURITÉ ET PERSISTENCE PAR JETON DE SESSION ---
if 'user' not in st.session_state:
    st.session_state['user'] = None

if st.session_state['user'] is None:
    session_token = st.query_params.get("session", None)
    if session_token:
        res_token = conn.query("SELECT username FROM sessions WHERE token=:t", params={"t": session_token}, ttl=0)
        if not res_token.empty:
            st.session_state['user'] = res_token.iloc[0]['username']

if "user" in st.query_params:
    del st.query_params["user"]

# AFFICHAGE DES MESSAGES FLASH (TOAST)
if 'flash_msg' in st.session_state:
    type_msg, txt = st.session_state.pop('flash_msg')
    if type_msg == "success":
        st.toast(txt)
    elif type_msg == "error":
        st.toast(txt)

# BANNIÈRE D'EN-TÊTE
st.markdown("""
    <div class="brand-banner">
        <div>
            <div class="brand-title">MONDE & FINANCE</div>
            <div class="brand-subtitle">Plateforme d'apprentissage & simulation boursière</div>
        </div>
        <div class="brand-badge">Édition 2026-2027</div>
    </div>
""", unsafe_allow_html=True)

# --- PORTAIL CONNEXION / INSCRIPTION ---
if st.session_state['user'] is None:
    col_centered = st.columns([1, 1.2, 1])[1]
    with col_centered:
        tab1, tab2 = st.tabs(["Connexion", "Créer un compte"])
        with tab1:
            with st.form("form_connexion"):
                u_login = st.text_input("Identifiant", key="login_user")
                p_login = st.text_input("Mot de passe", type="password", key="login_pass")
                if st.form_submit_button("Se connecter", use_container_width=True):
                    res = conn.query("SELECT * FROM users WHERE username=:u AND password=:p", params={"u": u_login.strip(), "p": p_login}, ttl=0)
                    if not res.empty:
                        new_token = str(uuid.uuid4())
                        now_str = datetime.now(ZoneInfo("America/Toronto")).strftime("%Y-%m-%d %H:%M:%S")
                        with conn.session as session:
                            session.execute(text("INSERT INTO sessions (token, username, created_at) VALUES (:t, :u, :time)"),
                                            {"t": new_token, "u": u_login.strip(), "time": now_str})
                            session.commit()

                        st.session_state['user'] = u_login.strip()
                        st.query_params["session"] = new_token
                        st.session_state['flash_msg'] = ("success", f"Bienvenue {u_login.strip()} !")
                        st.rerun()
                    else: st.error("Identifiants incorrects.")

        with tab2:
            with st.form("form_inscription"):
                u_new = st.text_input("Identifiant (ex: PrenomNom)", key="new_user")
                g_new = st.selectbox("Groupe", LISTE_GROUPES, key="new_group")
                p_new = st.text_input("Mot de passe", type="password", key="new_pass")
                if st.form_submit_button("S'inscrire", use_container_width=True):
                    if u_new and p_new:
                        res_check = conn.query("SELECT username FROM users WHERE username=:u", params={"u": u_new.strip()}, ttl=0)
                        if res_check.empty:
                            with conn.session as session:
                                session.execute(text("INSERT INTO users VALUES (:u, :p, 10000.00, :g)"), {"u": u_new.strip(), "p": p_new, "g": g_new})
                                session.commit()
                            st.success("Compte créé ! Connectez-vous.")
                        else: st.error("Ce nom d'utilisateur existe déjà.")
                    else: st.error("Veuillez remplir tous les champs.")

else:
    user = st.session_state['user']
    res_u = conn.query("SELECT cash, groupe FROM users WHERE username=:u", params={"u": user}, ttl=0)

    if res_u.empty:
        st.session_state['user'] = None
        st.query_params.clear()
        st.rerun()

    cash_actuel = float(res_u.iloc[0]['cash'])
    groupe_actuel = res_u.iloc[0]['groupe']

    col_h1, col_h2 = st.columns([4, 1])
    col_h1.markdown(f"<p style='color: #FFFFFF; font-size: 1rem; margin-top:5px;'>Investisseur : <b style='color: #FFFFFF;'>{user}</b> &nbsp;•&nbsp; <span style='background:rgba(229, 9, 20, 0.22); color:#FFFFFF; border:1px solid #E50914; padding:4px 14px; border-radius:12px; font-weight:700; font-size:0.85rem;'>{groupe_actuel}</span></p>", unsafe_allow_html=True)

    if col_h2.button("Déconnexion", use_container_width=True):
        current_token = st.query_params.get("session")
        if current_token:
            with conn.session as session:
                session.execute(text("DELETE FROM sessions WHERE token=:t"), {"t": current_token})
                session.commit()
        st.session_state['user'] = None
        st.query_params.clear()
        st.rerun()

    # --- MÉTRIQUES DE HAUT DE PAGE ---
    # Rafraîchissement automatique des 4 carrés toutes les 30 s (fragment seul, sans refresh de page).
    # Si la version de Streamlit ne supporte pas run_every, les carrés restent statiques comme avant.
    try:
        fragment_auto = st.fragment(run_every=30)
    except TypeError:
        fragment_auto = st.fragment

    @fragment_auto
    def afficher_metrics_live():
        pos_df = conn.query("SELECT ticker, shares, avg_price FROM portfolio WHERE username=:u", params={"u": user}, ttl=0)
        valeur_actions = 0.0

        if not pos_df.empty:
            unique_tks = pos_df['ticker'].unique().tolist()
            prix_dict = obtenir_prix_groupes(unique_tks)
            for _, row in pos_df.iterrows():
                tk_sym = str(row['ticker']).strip().upper()
                px_actuel = prix_dict.get(tk_sym)
                px_final = px_actuel if px_actuel is not None else float(row['avg_price'] or 0.0)
                valeur_actions += px_final * row['shares']

        valeur_totale = cash_actuel + valeur_actions
        profit_total = valeur_totale - 10000.00
        rendement_pct = (profit_total / 10000.00) * 100

        col_m1, col_m2, col_m3, col_m4 = st.columns(4)
        col_m1.markdown(f"<div class='kpi-card'><div class='kpi-label'>Disponible</div><div class='kpi-value'>${cash_actuel:,.2f}</div></div>", unsafe_allow_html=True)
        col_m2.markdown(f"<div class='kpi-card'><div class='kpi-label'>Actions</div><div class='kpi-value'>${valeur_actions:,.2f}</div></div>", unsafe_allow_html=True)
        col_m3.markdown(f"<div class='kpi-card'><div class='kpi-label'>Valeur Totale</div><div class='kpi-value'>${valeur_totale:,.2f}</div></div>", unsafe_allow_html=True)
        classe_delta = "kpi-delta up" if profit_total >= 0 else "kpi-delta down"
        fleche_delta = "▲" if profit_total >= 0 else "▼"
        classe_carte = "kpi-card kpi-up" if profit_total >= 0 else "kpi-card kpi-down"
        col_m4.markdown(f"<div class='{classe_carte}'><div class='kpi-label'>Gains / Pertes</div><div class='kpi-value'>${profit_total:,.2f}</div><div class='{classe_delta}'>{fleche_delta} {rendement_pct:+.2f}%</div></div>", unsafe_allow_html=True)

        if not pos_df.empty:
            items_tape = ""
            for _, row in pos_df.iterrows():
                tk_tape = str(row['ticker']).strip().upper()
                px_tape = prix_dict.get(tk_tape)
                pm_tape = float(row['avg_price'] or 0.0)
                px_aff = px_tape if px_tape is not None else pm_tape
                fmt_tape = f"${px_aff:,.4f}" if px_aff < 1 else f"${px_aff:,.2f}"
                couleur_tape = "#34D399" if px_aff >= pm_tape else "#F87171"
                fleche_tape = "▲" if px_aff >= pm_tape else "▼"
                items_tape += f"<span class='item'><b>{tk_tape}</b>&nbsp;<span style='color:{couleur_tape};'>{fleche_tape} {fmt_tape}</span></span>"
            if items_tape:
                duree_tape = max(20, 5 * len(pos_df))
                css_tape = "<style>body{margin:0;background:#161616;font-family:'Work Sans',sans-serif;overflow:hidden;border:1px solid #2E2E2E;border-radius:10px;box-sizing:border-box;height:44px}.track{display:flex;width:max-content;padding:11px 0;animation:tapeScroll " + str(duree_tape) + "s linear infinite}.track:hover{animation-play-state:paused}.item{padding:0 22px;border-right:1px solid rgba(255,255,255,0.12);color:#FFFFFF;font-weight:600;white-space:nowrap;font-variant-numeric:tabular-nums}.item b{font-family:'Bebas Neue','Work Sans',sans-serif;font-weight:400;letter-spacing:0.05em;font-size:17px}@keyframes tapeScroll{from{transform:translateX(0)}to{transform:translateX(-50%)}}</style>"
                components.html(f"<!DOCTYPE html><html><head>{css_tape}</head><body><div class='track'>{items_tape}{items_tape}</div></body></html>", height=46)

        # --- SUIVI DES RÈGLES DU JEU (compact, effet néon discret) ---
        mois_court = datetime.now(ZoneInfo("America/Toronto")).strftime("%Y-%m")
        nb_titres = int(pos_df['ticker'].nunique()) if not pos_df.empty else 0
        ach_mois_q = conn.query(
            "SELECT COUNT(*) AS n FROM transactions WHERE username=:u AND shares > 0 AND timestamp LIKE :m",
            params={"u": user, "m": mois_court + "%"}, ttl=0)
        nb_achats_mois = int(ach_mois_q.iloc[0]['n']) if not ach_mois_q.empty else 0

        regle_titres_ok = nb_titres >= 4
        regle_achats_ok = nb_achats_mois >= 5

        def puce_regle(titre, valeur, cible, ok):
            affichage = "✓" if ok else f"{valeur}/{cible}"
            couleur = "#10B981" if ok else "#E50914"
            pct = min(100, int(valeur / cible * 100)) if cible else 0
            return (f"<div style=\"background:#161616;border:1px solid #2E2E2E;border-radius:10px;padding:8px 14px;"
                    f"box-shadow:0 0 18px -6px {couleur}66;\">"
                    f"<span style=\"color:#9CA3AF;font-size:11px;font-weight:700;text-transform:uppercase;letter-spacing:0.06em;\">{titre}</span>"
                    f"<span style=\"color:#FFFFFF;font-size:15px;font-weight:800;margin-left:8px;\">{affichage}</span>"
                    f"<div style=\"background:#2E2E2E;border-radius:6px;height:5px;margin-top:6px;\">"
                    f"<div style=\"background:{couleur};border-radius:6px;height:5px;width:{pct}%;box-shadow:0 0 10px {couleur};\"></div></div></div>")

        st.markdown("<div style=\"color:#9CA3AF;font-size:12px;font-weight:700;text-transform:uppercase;letter-spacing:0.08em;margin:2px 0 8px 0;\">Règles du jeu</div>", unsafe_allow_html=True)
        rc1, rc2 = st.columns(2)
        rc1.markdown(puce_regle("Titres différents (min. 4)", nb_titres, 4, regle_titres_ok), unsafe_allow_html=True)
        rc2.markdown(puce_regle("Achats ce mois-ci (min. 5)", nb_achats_mois, 5, regle_achats_ok), unsafe_allow_html=True)

        manques = []
        if not regle_titres_ok:
            manques.append(f"ajoute {4 - nb_titres} titre(s) différent(s)")
        if not regle_achats_ok:
            manques.append(f"fais {5 - nb_achats_mois} achat(s) de plus ce mois-ci")
        if manques:
            st.caption("Pour respecter les règles : " + " et ".join(manques) + ".")
        else:
            st.caption("Règles respectées. Beau travail!")

    afficher_metrics_live()

    st.markdown("<hr>", unsafe_allow_html=True)

    # --- NAVIGATION ET PERSISTENCE D'ONGLET (POUR F5) ---
    TABS_LIST = ["Marché & Analyse", "Mes Positions", "Mon Historique", "Classement", "Supervision Prof"]
    default_tab = st.query_params.get("tab", "Marché & Analyse")
    if default_tab not in TABS_LIST:
        default_tab = "Marché & Analyse"

    tab_choisi = st.radio(
        "Navigation",
        options=TABS_LIST,
        index=TABS_LIST.index(default_tab),
        horizontal=True,
        key="main_nav_radio"
    )

    st.query_params["tab"] = tab_choisi

    # --- ONGLET 1 : MARCHÉ & ANALYSE ---
    if tab_choisi == "Marché & Analyse":
        col_l1, col_l2, col_l3 = st.columns(3)
        col_l1.link_button("Les Affaires", "https://www.lesaffaires.com/?view=register&product_id=1898&plan_id=62962&utm_campaign=ABNT_PROMO30_ADSGOOGLE&utm_medium=ADS&utm_source=ADSGOOGLE&utm_term=landing&gad_source=1&gad_campaignid=24159803993&gbraid=0AAAAADel4hnhaUpWgv3yFaDiNmCZAJv32&gclid=CjwKCAjwrP3VBhBbEiwAnaqpQyOPax6Hc_HEcl3kWXH3NxC0aQVSEw-GAa87RTweJxM5yyasiT0W4RoCAVQQAvD_BwE", use_container_width=True)
        col_l2.link_button("Barchart", "https://www.barchart.com/", use_container_width=True)
        col_l3.link_button("Yahoo Finance", "https://ca.finance.yahoo.com/", use_container_width=True)

        col_s1, col_s2 = st.columns([4, 1])
        with col_s1:
            search_query = st.text_input(
                "Rechercher une action nord-américaine (ex: Apple, Tesla, Royal Bank, NVDA, SHOP.TO...)",
                value="",
                placeholder="Tapez le nom d'une entreprise ou un symbole (NYSE, NASDAQ, TSX)...",
                key="recherche_ticker"
            )
        with col_s2:
            st.markdown("<br>", unsafe_allow_html=True)
            if st.button("Rafraîchir le cours", use_container_width=True):
                st.rerun()

        selected_ticker = "AAPL"

        if search_query and len(search_query.strip()) > 0:
            query_clean = search_query.strip()
            resultats = rechercher_symbole_universel(query_clean)
            if resultats:
                options_dict = {res['label']: res['symbol'] for res in resultats}
                choix_label = st.selectbox("Sélectionnez l'action :", list(options_dict.keys()))
                selected_ticker = options_dict[choix_label]
            else:
                selected_ticker = query_clean.upper()

        details = obtenir_details_financiers(selected_ticker)

        if details == {"erreur": "non_na"}:
            st.error(f"**Marché non autorisé :** L'action `{selected_ticker}` est cotée hors de l'Amérique du Nord (ex: Paris, Tokyo, Londres). Seules les bourses nord-américaines (NYSE, NASDAQ, TSX, TSX-V, OTC) sont permises.")
        elif details:
            prix, var, var_pct = details["Prix"], details["Variation"], details["VariationPct"]
            chart_color = "#10B981" if var >= 0 else "#EF4444"
            fill_color = "rgba(16, 185, 129, 0.20)" if var >= 0 else "rgba(239, 68, 68, 0.20)"
            signe = "+" if var >= 0 else ""
            fmt_prix = f"${prix:,.4f}" if prix < 1 else f"${prix:,.2f}"

            col_chart, col_order = st.columns([2.2, 1])

            with col_chart:
                st.markdown(f"<div class='quote-card {'up' if var >= 0 else 'down'}' data-tk='{selected_ticker}'><div class='quote-ticker'>{selected_ticker}</div><div class='quote-price'>{fmt_prix}</div><div class='quote-var {'up' if var >= 0 else 'down'}'>{signe}{var_pct:.2f}% ({signe}{var:,.2f})</div></div>", unsafe_allow_html=True)

                @st.fragment
                def afficher_graphique_interactif(ticker):
                    period_map = {
                        "1d": "1 Jour",
                        "5d": "5 Jours",
                        "1mo": "1 Mois",
                        "3mo": "3 Mois",
                        "6mo": "6 Mois",
                        "1y": "1 An"
                    }

                    selected_period = st.radio(
                        "Horizon d'analyse",
                        options=list(period_map.keys()),
                        format_func=lambda x: period_map[x],
                        horizontal=True,
                        key=f"horizon_{ticker}"
                    )

                    type_graph = st.radio(
                        "Type de graphique",
                        options=["Ligne", "Chandeliers"],
                        horizontal=True,
                        key=f"typegraph_{ticker}"
                    )

                    df_hist = obtenir_historique(ticker, selected_period)
                    if df_hist is not None and not df_hist.empty:
                        min_p = float(df_hist['Close'].min())
                        max_p = float(df_hist['Close'].max())
                        delta = max_p - min_p

                        padding = delta * 0.08 if delta > 0 else min_p * 0.02
                        y_min = max(0, min_p - padding) if min_p > 0 else min_p - padding
                        y_max = max_p + padding

                        tick_fmt = "$.4f" if max_p < 1 else "$.2f"

                        if type_graph == "Chandeliers" and all(c in df_hist.columns for c in ['Open', 'High', 'Low', 'Close']):
                            fig = make_subplots(rows=2, cols=1, shared_xaxes=True,
                                                row_heights=[0.72, 0.28], vertical_spacing=0.06)
                            fig.add_trace(go.Candlestick(
                                x=df_hist.index,
                                open=df_hist['Open'], high=df_hist['High'],
                                low=df_hist['Low'], close=df_hist['Close'],
                                increasing_line_color='#10B981', increasing_fillcolor='#10B981',
                                decreasing_line_color='#EF4444', decreasing_fillcolor='#EF4444',
                                name='Cours'
                            ), row=1, col=1)
                            if len(df_hist) >= 20:
                                fig.add_trace(go.Scatter(
                                    x=df_hist.index, y=df_hist['Close'].rolling(window=20).mean(),
                                    mode='lines', line=dict(color='#F59E0B', width=1.5), name='MM 20'
                                ), row=1, col=1)
                            if len(df_hist) >= 50:
                                fig.add_trace(go.Scatter(
                                    x=df_hist.index, y=df_hist['Close'].rolling(window=50).mean(),
                                    mode='lines', line=dict(color='#8B5CF6', width=1.5), name='MM 50'
                                ), row=1, col=1)
                            vol = df_hist['Volume'].fillna(0) if 'Volume' in df_hist.columns else pd.Series(0, index=df_hist.index)
                            coul_vol = ['#10B981' if c >= o else '#EF4444' for c, o in zip(df_hist['Close'], df_hist['Open'])]
                            fig.add_trace(go.Bar(
                                x=df_hist.index, y=vol, marker_color=coul_vol, opacity=0.55, name='Volume'
                            ), row=2, col=1)
                            fig.update_layout(
                                paper_bgcolor='rgba(0,0,0,0)',
                                plot_bgcolor='rgba(0,0,0,0)',
                                height=460,
                                margin=dict(l=10, r=10, t=30, b=10),
                                xaxis_rangeslider_visible=False,
                                showlegend=True,
                                legend=dict(orientation='h', yanchor='bottom', y=1.02, xanchor='left', x=0,
                                            font=dict(color='#FFFFFF', size=11)),
                                font=dict(color='#FFFFFF', family='Work Sans'),
                                xaxis=dict(showgrid=True, gridcolor='rgba(255,255,255,0.07)', gridwidth=0.8, zeroline=False),
                                xaxis2=dict(showgrid=False, zeroline=False),
                                yaxis=dict(range=[y_min, y_max], showgrid=True, gridcolor='rgba(255,255,255,0.07)',
                                           gridwidth=0.8, zeroline=False, side='right', tickformat=tick_fmt),
                                yaxis2=dict(showgrid=False, zeroline=False, side='right'),
                            )
                            st.plotly_chart(fig, use_container_width=True)
                            return

                        fig = go.Figure()

                        fig.add_trace(go.Scatter(
                            x=df_hist.index,
                            y=df_hist['Close'],
                            mode='lines',
                            line=dict(color=chart_color, width=3),
                            fill='tozeroy',
                            fillcolor=fill_color,
                            hovertemplate='%{x|%d %b %H:%M}<br><b>%{y:' + tick_fmt + '}</b><extra></extra>'
                        ))

                        fig.add_trace(go.Scatter(
                            x=[df_hist.index[-1]],
                            y=[df_hist['Close'].iloc[-1]],
                            mode='markers',
                            marker=dict(size=18, color=chart_color, opacity=0.30),
                            hoverinfo='skip',
                            showlegend=False
                        ))
                        fig.add_trace(go.Scatter(
                            x=[df_hist.index[-1]],
                            y=[df_hist['Close'].iloc[-1]],
                            mode='markers',
                            marker=dict(size=8, color=chart_color, line=dict(color='#FFFFFF', width=1.5)),
                            hoverinfo='skip',
                            showlegend=False
                        ))

                        fig.update_layout(
                            paper_bgcolor='rgba(0,0,0,0)',
                            plot_bgcolor='rgba(0,0,0,0)',
                            height=340,
                            margin=dict(l=10, r=10, t=10, b=10),
                            xaxis=dict(showgrid=True, gridcolor='rgba(255,255,255,0.07)', gridwidth=0.8, zeroline=False),
                            yaxis=dict(
                                range=[y_min, y_max],
                                showgrid=True,
                                gridcolor='rgba(255,255,255,0.07)',
                                gridwidth=0.8,
                                zeroline=False,
                                side="right",
                                tickformat=tick_fmt
                            ),
                            font=dict(color="#FFFFFF", family="Work Sans")
                        )
                        st.plotly_chart(fig, use_container_width=True)

                afficher_graphique_interactif(selected_ticker)

                nouvelles = obtenir_nouvelles(selected_ticker)
                if nouvelles:
                    st.markdown("### Actualités")
                    for n in nouvelles:
                        nt, nl, npub = n.get('title'), n.get('link'), n.get('publisher', '')
                        if nt and nl:
                            st.markdown(
                                "<div style='margin-bottom:10px;'>"
                                f"<a href='{nl}' target='_blank' style='color:#FFFFFF;font-weight:600;text-decoration:none;'>{nt}</a>"
                                f"<div style='color:#9CA3AF;font-size:12px;'>{npub}</div>"
                                "</div>",
                                unsafe_allow_html=True)

            with col_order:
                st.markdown("### Passer un ordre")
                mode_ordre = st.radio("Mode d'achat", ["Par quantité", "Par montant ($)"], horizontal=True, key=f"mode_{selected_ticker}")

                if mode_ordre == "Par quantité":
                    qty_achat = st.number_input("Quantité", min_value=1, step=1, value=1, key=f"qty_{selected_ticker}")
                    st.write(f"Total estimé : **${prix*qty_achat:,.2f}**")
                    qty_vente = qty_achat
                else:
                    montant = st.number_input("Montant à investir ($)", min_value=1.0, step=10.0, value=100.0, key=f"montant_{selected_ticker}")
                    qty_achat = int(montant // prix) if prix and prix > 0 else 0
                    if qty_achat >= 1:
                        st.write(f"Vous pouvez acheter **{qty_achat}** actions pour **${qty_achat*prix:,.2f}**")
                    else:
                        st.warning("Ce montant ne permet pas d'acheter une seule action à ce prix.")
                    qty_vente = st.number_input("Quantité à vendre", min_value=1, step=1, value=1, key=f"qtyv_{selected_ticker}")

                if achat_penny_stock_bloque(selected_ticker):
                    st.warning("BIEN ESSAYÉ! MAIS ATTENDS À 9H30!")

                col_b, col_s = st.columns(2)

                # ACHAT
                if col_b.button("Acheter", use_container_width=True):
                    if achat_penny_stock_bloque(selected_ticker):
                        st.warning("BIEN ESSAYÉ! MAIS ATTENDS À 9H30!")
                    elif qty_achat < 1:
                        st.warning("Augmentez le montant pour acheter au moins une action.")
                    elif not verifier_cooldown(user, delai_secondes=3):
                        st.warning("Veuillez attendre 3 secondes entre chaque transaction.")
                    else:
                        prix_instantane = obtenir_prix_actuel(selected_ticker) or prix
                        cost_real = prix_instantane * qty_achat

                        c_res = conn.query("SELECT cash FROM users WHERE username=:u", params={"u": user}, ttl=0)
                        cash_actuel_db = float(c_res.iloc[0]['cash']) if not c_res.empty else 0.0

                        if cash_actuel_db >= cost_real:
                            now_str = datetime.now(ZoneInfo("America/Toronto")).strftime("%Y-%m-%d %H:%M:%S")
                            with conn.session as session:
                                session.execute(text("UPDATE users SET cash = cash - :cost WHERE username = :u"), {"cost": cost_real, "u": user})
                                p_res = conn.query("SELECT shares, avg_price FROM portfolio WHERE username=:u AND LOWER(ticker)=LOWER(:t)", params={"u": user, "t": selected_ticker}, ttl=0)
                                if not p_res.empty:
                                    anc_s, anc_p = int(p_res.iloc[0]['shares']), float(p_res.iloc[0]['avg_price'] or prix_instantane)
                                    n_s = anc_s + qty_achat
                                    n_p = ((anc_s * anc_p) + (qty_achat * prix_instantane)) / n_s
                                    session.execute(text("UPDATE portfolio SET shares=:s, avg_price=:p WHERE username=:u AND LOWER(ticker)=LOWER(:t)"), {"s": n_s, "p": n_p, "u": user, "t": selected_ticker})
                                else:
                                    session.execute(text("INSERT INTO portfolio VALUES (:u, :t, :s, :p)"), {"u": user, "t": selected_ticker.upper(), "s": qty_achat, "p": prix_instantane})
                                session.execute(text("INSERT INTO transactions (username, ticker, shares, price, total, timestamp) VALUES (:u, :t, :s, :p, :tot, :time)"),
                                                {"u": user, "t": selected_ticker.upper(), "s": qty_achat, "p": prix_instantane, "tot": cost_real, "time": now_str})
                                session.commit()

                            st.session_state['flash_msg'] = ("success", f"Achat de {qty_achat} {selected_ticker.upper()} à ${prix_instantane:,.2f} effectué !")
                            st.rerun()
                        else: st.error("Fonds insuffisants.")

                # VENTE
                if col_s.button("Vendre", use_container_width=True):
                    if not verifier_cooldown(user, delai_secondes=3):
                        st.warning("Veuillez attendre 3 secondes entre chaque transaction.")
                    else:
                        prix_instantane = obtenir_prix_actuel(selected_ticker) or prix
                        cost_real = prix_instantane * qty_vente

                        p_res = conn.query("SELECT shares FROM portfolio WHERE username=:u AND LOWER(ticker)=LOWER(:t)", params={"u": user, "t": selected_ticker}, ttl=0)
                        shares_dispo = int(p_res.iloc[0]['shares']) if not p_res.empty else 0

                        if shares_dispo >= qty_vente:
                            now_str = datetime.now(ZoneInfo("America/Toronto")).strftime("%Y-%m-%d %H:%M:%S")
                            with conn.session as session:
                                session.execute(text("UPDATE users SET cash = cash + :cost WHERE username = :u"), {"cost": cost_real, "u": user})
                                rem = shares_dispo - qty_vente
                                if rem > 0:
                                    session.execute(text("UPDATE portfolio SET shares=:s WHERE username=:u AND LOWER(ticker)=LOWER(:t)"), {"s": rem, "u": user, "t": selected_ticker})
                                else:
                                    session.execute(text("DELETE FROM portfolio WHERE username=:u AND LOWER(ticker)=LOWER(:t)"), {"u": user, "t": selected_ticker})
                                session.execute(text("INSERT INTO transactions (username, ticker, shares, price, total, timestamp) VALUES (:u, :t, :s, :p, :tot, :time)"),
                                                {"u": user, "t": selected_ticker.upper(), "s": -qty_vente, "p": prix_instantane, "tot": cost_real, "time": now_str})
                                session.commit()

                            st.session_state['flash_msg'] = ("success", f"Vente de {qty_vente} {selected_ticker.upper()} à ${prix_instantane:,.2f} effectuée !")
                            st.rerun()
                        else: st.error("Vous ne possédez pas cette quantité d'actions.")

                # FAVORIS (bouton jaune via type="primary")
                def _retirer_favori(tk):
                    with conn.session as session:
                        session.execute(text("DELETE FROM favoris WHERE username=:u AND ticker=:t"), {"u": user, "t": tk})
                        session.commit()

                def _choisir_favori(tk):
                    st.session_state["recherche_ticker"] = tk

                fav_check = conn.query("SELECT 1 FROM favoris WHERE username=:u AND ticker=:t", params={"u": user, "t": selected_ticker.upper()}, ttl=0)
                if not fav_check.empty:
                    st.button("★ Dans mes favoris (retirer)", use_container_width=True, key=f"favrm_{selected_ticker}",
                              type="primary", on_click=_retirer_favori, args=(selected_ticker.upper(),))
                else:
                    if st.button("☆ Ajouter à mes favoris", use_container_width=True, key=f"favadd_{selected_ticker}", type="primary"):
                        with conn.session as session:
                            session.execute(text("INSERT INTO favoris (username, ticker) VALUES (:u, :t) ON CONFLICT DO NOTHING"), {"u": user, "t": selected_ticker.upper()})
                            session.commit()
                        st.rerun()

                # Liste des favoris sous le bouton jaune
                fav_q = conn.query("SELECT ticker FROM favoris WHERE username=:u ORDER BY ticker", params={"u": user}, ttl=0)
                if not fav_q.empty:
                    st.markdown("<div style='color:#9CA3AF;font-size:11px;font-weight:700;text-transform:uppercase;letter-spacing:0.06em;margin:10px 0 6px;'>Mes favoris</div>", unsafe_allow_html=True)
                    fav_tickers = fav_q['ticker'].tolist()
                    fav_data = obtenir_donnees_favoris(tuple(fav_tickers))
                    chip_css = (
                        "<style>"
                        "@keyframes neonPulseJaune {"
                        "0%,100% {box-shadow: 0 0 6px 1px rgba(255,215,0,0.55), 0 0 18px 4px rgba(255,215,0,0.22);}"
                        "50% {box-shadow: 0 0 16px 3px rgba(255,215,0,1), 0 0 40px 10px rgba(255,215,0,0.45);}"
                        "}"
                    )
                    for tk in fav_tickers:
                        px, vp = fav_data.get(tk.upper(), (None, None))
                        couleur_txt = "#10B981" if (vp or 0) >= 0 else "#EF4444"
                        cle = f"favchip_{tk}"
                        chip_css += (
                            f'div[class*="st-key-{cle}"] button {{'
                            f'background: #161616 !important;'
                            f'border: 1px solid #FFD700 !important;'
                            f'padding: 5px 6px !important;'
                            f'animation: neonPulseJaune 2.4s ease-in-out infinite;'
                            f'}}'
                            f'div[class*="st-key-{cle}"] button p {{'
                            f'color: {couleur_txt} !important; font-weight: 700 !important; font-size: 13px !important;'
                            f'}}'
                        )
                    chip_css += "</style>"
                    st.markdown(chip_css, unsafe_allow_html=True)
                    fav_cols = st.columns(2)
                    for i, tk in enumerate(fav_tickers):
                        px, vp = fav_data.get(tk.upper(), (None, None))
                        if px is None:
                            chip_label = f"{tk}"
                        else:
                            fmt_px = f"${px:,.4f}" if px < 1 else f"${px:,.2f}"
                            signe = "+" if (vp or 0) >= 0 else ""
                            fleche = "▲" if (vp or 0) >= 0 else "▼"
                            chip_label = f"{tk} {fmt_px} {fleche} {signe}{vp:.2f}%"
                        with fav_cols[i % 2]:
                            st.button(chip_label, key=f"favchip_{tk}", use_container_width=True, on_click=_choisir_favori, args=(tk,))
        else:
            st.error(f"Impossible de trouver des données financières pour '{selected_ticker}'. Vérifiez le nom ou le symbole boursier.")

    # --- ONGLET 2 : POSITIONS ET IMPRESSION PRO ---
    elif tab_choisi == "Mes Positions":
        st.markdown("""
            <style>
            @media print {
                html, body, .stApp, [data-testid="stAppViewContainer"], section.main, .block-container {
                    height: auto !important;
                    min-height: auto !important;
                    overflow: visible !important;
                    position: static !important;
                    background-color: #FFFFFF !important;
                    color: #000000 !important;
                    padding: 0 !important;
                    margin: 0 !important;
                }
                header, footer, [data-testid="stHeader"], [data-testid="stSidebar"],
                div[data-testid="stRadio"], .stButton, button,
                iframe, hr, .stSelectbox, .stNumberInput, .brand-banner,
                div[data-testid="stMetric"], .kpi-card, .podium-card, .mon-rang {
                    display: none !important;
                }
                .print-header {
                    display: block !important;
                    margin-bottom: 20px;
                    color: #0F172A !important;
                }
                .print-summary-table {
                    width: 100% !important;
                    border-collapse: collapse !important;
                    margin-bottom: 20px !important;
                    text-align: center !important;
                    border: 1px solid #CBD5E1 !important;
                }
                .print-summary-table th, .print-summary-table td {
                    border: 1px solid #CBD5E1 !important;
                    padding: 8px 12px !important;
                    font-size: 11pt !important;
                    color: #000000 !important;
                }
                .print-summary-table th {
                    background-color: #F1F5F9 !important;
                    font-weight: 700 !important;
                    text-transform: uppercase !important;
                    font-size: 9pt !important;
                    -webkit-print-color-adjust: exact !important;
                    print-color-adjust: exact !important;
                }
                .custom-table {
                    width: 100% !important;
                    border: 1px solid #CBD5E1 !important;
                    page-break-inside: auto;
                }
                .custom-table th, .custom-table td {
                    border: 1px solid #CBD5E1 !important;
                    padding: 8px 10px !important;
                    font-size: 10pt !important;
                    color: #000000 !important;
                }
                .custom-table th {
                    background-color: #F1F5F9 !important;
                    -webkit-print-color-adjust: exact !important;
                    print-color-adjust: exact !important;
                }
            }
            .print-header { display: none; }
            </style>
        """, unsafe_allow_html=True)

        @st.fragment
        def afficher_positions_live():
            pos_df_live = conn.query("SELECT ticker, shares, avg_price FROM portfolio WHERE username=:u", params={"u": user}, ttl=0)
            val_actions_live = 0.0

            if not pos_df_live.empty:
                unique_tks = pos_df_live['ticker'].unique().tolist()
                prix_dict = obtenir_prix_groupes(unique_tks)
                for _, r in pos_df_live.iterrows():
                    tk_sym = str(r['ticker']).strip().upper()
                    px_a = prix_dict.get(tk_sym)
                    px_f = px_a if px_a is not None else float(r['avg_price'] or 0.0)
                    val_actions_live += px_f * r['shares']

            val_totale_live = cash_actuel + val_actions_live
            prof_total_live = val_totale_live - 10000.00
            rend_pct_live = (prof_total_live / 10000.00) * 100

            date_impression = datetime.now(ZoneInfo("America/Toronto")).strftime("%d/%m/%Y à %H:%M")
            pnl_color_print = "#10B981" if prof_total_live >= 0 else "#EF4444"

            st.markdown(f"""
                <div class="print-header">
                    <div style="border-bottom: 2px solid #0F172A; padding-bottom: 10px; margin-bottom: 14px;">
                        <h2 style="margin:0; color:#0F172A; font-size: 1.5rem; font-weight:800;">Rapport de Portefeuille Boursier — Monde & Finance</h2>
                        <p style="margin:6px 0 0 0; font-size:1rem; color:#334155;">
                            <b>Élève :</b> {user} &nbsp;|&nbsp; <b>Groupe :</b> {groupe_actuel} &nbsp;|&nbsp; <b>Date d'impression :</b> {date_impression}
                        </p>
                    </div>
                    <table class="print-summary-table">
                        <thead>
                            <tr>
                                <th>Disponible (Cash)</th>
                                <th>Actions Possédées</th>
                                <th>Valeur Totale</th>
                                <th>Gains / Pertes</th>
                            </tr>
                        </thead>
                        <tbody>
                            <tr>
                                <td><b>${cash_actuel:,.2f}</b></td>
                                <td><b>${val_actions_live:,.2f}</b></td>
                                <td><b>${val_totale_live:,.2f}</b></td>
                                <td style="color:{pnl_color_print};"><b>${prof_total_live:+,.2f} ({rend_pct_live:+.2f}%)</b></td>
                            </tr>
                        </tbody>
                    </table>
                </div>
            """, unsafe_allow_html=True)

            col_p1, col_p2 = st.columns([3, 1])
            with col_p1:
                st.markdown("### Mes Positions Actuelles")
            with col_p2:
                components.html("""
                    <button onclick="window.parent.print()" style="
                        background: linear-gradient(180deg, #E50914 0%, #B00610 100%);
                        color: #FFFFFF;
                        border: 1px solid rgba(255, 130, 130, 0.4);
                        padding: 10px 18px;
                        border-radius: 10px;
                        font-weight: 700;
                        cursor: pointer;
                        width: 100%;
                        font-family: 'Work Sans', sans-serif;
                        box-shadow: 0 10px 22px -10px rgba(229, 9, 20, 0.85);
                        transition: all 0.12s ease;
                    " onmousedown="this.style.transform='translateY(2px)'" onmouseup="this.style.transform='translateY(0px)'">
                        Imprimer / PDF
                    </button>
                """, height=45)

            p_all = conn.query("SELECT ticker, shares, avg_price FROM portfolio WHERE username=:u", params={"u": user}, ttl=0)
            if not p_all.empty:
                options_vente = {}
                html_rows = ""

                tks_all = p_all['ticker'].unique().tolist()
                prix_dict_pos = obtenir_prix_groupes(tks_all)

                pie_labels, pie_vals = [], []

                for _, r in p_all.iterrows():
                    tk, sh, pm = str(r['ticker']), int(r['shares']), float(r['avg_price'] or 0.0)
                    pa_live = prix_dict_pos.get(tk.upper())
                    pa = pa_live if pa_live is not None else pm
                    val = sh * pa
                    pnl = (pa - pm) * sh
                    pnl_pct = ((pa - pm) / pm * 100) if pm > 0 else 0
                    pie_labels.append(tk)
                    pie_vals.append(val)

                    pnl_color = "#10B981" if pnl >= 0 else "#EF4444"
                    fmt_pa = f"${pa:,.4f}" if pa < 1 else f"${pa:,.2f}"
                    fmt_pm = f"${pm:,.4f}" if pm < 1 else f"${pm:,.2f}"

                    options_vente[f"{tk} ({sh} action(s) disponible(s))"] = (tk, sh, pa)

                    html_rows += f"<tr><td><b>{tk}</b></td><td>{sh}</td><td>{fmt_pm}</td><td>{fmt_pa}</td><td>${val:,.2f}</td><td style='color:{pnl_color}; font-weight:700;'>${pnl:+,.2f}</td><td style='color:{pnl_color}; font-weight:700;'>{pnl_pct:+.2f}%</td></tr>"

                table_html = f"<table class='custom-table'><thead><tr><th>Action</th><th>Quantité</th><th>Prix Moyen</th><th>Prix Actuel</th><th>Valeur</th><th>Gain / Perte</th><th>Rendement</th></tr></thead><tbody>{html_rows}</tbody></table>"
                st.markdown(table_html, unsafe_allow_html=True)

                # --- CAMEMBERT : RÉPARTITION DU PORTEFEUILLE ---
                cash_q = conn.query("SELECT cash FROM users WHERE username=:u", params={"u": user}, ttl=0)
                cash_val = float(cash_q.iloc[0]['cash']) if not cash_q.empty else 0.0

                rep_labels = list(pie_labels) + (["Liquidités"] if cash_val > 0.005 else [])
                rep_values = list(pie_vals) + ([cash_val] if cash_val > 0.005 else [])
                total_pf = sum(rep_values)

                if total_pf > 0:
                    paires = sorted(zip(rep_labels, rep_values), key=lambda x: x[1], reverse=True)
                    rep_labels, rep_values = [p[0] for p in paires], [p[1] for p in paires]

                    palette = ["#E50914", "#10B981", "#3B82F6", "#F59E0B", "#8B5CF6", "#EC4899", "#06B6D4", "#84CC16", "#F97316", "#6366F1", "#14B8A6", "#EAB308"]
                    couleurs = [("#6B7280" if lab == "Liquidités" else palette[i % len(palette)]) for i, lab in enumerate(rep_labels)]

                    fig_pie = go.Figure(data=[go.Pie(
                        labels=rep_labels,
                        values=rep_values,
                        hole=0.45,
                        marker=dict(colors=couleurs, line=dict(color="#141414", width=3)),
                        textinfo="label+percent",
                        textfont=dict(color="#FFFFFF", family="Work Sans", size=14),
                        hovertemplate="<b>%{label}</b><br>%{value:,.2f} $ (%{percent})<extra></extra>",
                        sort=False,
                    )])
                    fig_pie.update_layout(
                        title=dict(text="Répartition du portefeuille", font=dict(color="#FFFFFF", family="Bebas Neue", size=30), x=0.5, xanchor="center"),
                        paper_bgcolor="rgba(0,0,0,0)",
                        plot_bgcolor="rgba(0,0,0,0)",
                        font=dict(color="#FFFFFF", family="Work Sans"),
                        showlegend=False,
                        height=480,
                        margin=dict(l=20, r=20, t=70, b=20),
                        annotations=[dict(
                            text=f"${total_pf:,.2f}",
                            x=0.5, y=0.5,
                            font=dict(size=24, color="#FFFFFF", family="Work Sans"),
                            showarrow=False
                        )],
                    )
                    cp1, cp2, cp3 = st.columns([1, 2, 1])
                    with cp2:
                        st.plotly_chart(fig_pie, use_container_width=True)

                st.markdown("<hr>", unsafe_allow_html=True)
                st.markdown("### Vendre rapidement mes positions")

                col_v1, col_v2, col_v3 = st.columns([2, 1, 1])
                with col_v1:
                    choix_v = st.selectbox("Sélectionnez l'action à vendre :", list(options_vente.keys()))
                    tk_v, max_sh, pa_v = options_vente[choix_v]
                with col_v2:
                    qty_v = st.number_input("Quantité à vendre :", min_value=1, max_value=max_sh, value=min(1, max_sh), step=1)
                with col_v3:
                    st.markdown("<br>", unsafe_allow_html=True)
                    total_vente = qty_v * pa_v
                    if st.button(f"Vendre pour ${total_vente:,.2f}", use_container_width=True):
                        if not verifier_cooldown(user, delai_secondes=3):
                            st.warning("Veuillez attendre 3 secondes entre chaque transaction.")
                        else:
                            check_p = conn.query("SELECT shares FROM portfolio WHERE username=:u AND ticker=:t", params={"u": user, "t": tk_v}, ttl=0)
                            sh_real = int(check_p.iloc[0]['shares']) if not check_p.empty else 0

                            if sh_real >= qty_v:
                                prix_v_instantane = obtenir_prix_actuel(tk_v) or pa_v
                                total_v_instantane = qty_v * prix_v_instantane
                                now_str = datetime.now(ZoneInfo("America/Toronto")).strftime("%Y-%m-%d %H:%M:%S")

                                with conn.session as session:
                                    session.execute(text("UPDATE users SET cash = cash + :cost WHERE username = :u"), {"cost": total_v_instantane, "u": user})
                                    rem = sh_real - qty_v
                                    if rem > 0:
                                        session.execute(text("UPDATE portfolio SET shares=:s WHERE username=:u AND ticker=:t"), {"s": rem, "u": user, "t": tk_v})
                                    else:
                                        session.execute(text("DELETE FROM portfolio WHERE username=:u AND ticker=:t"), {"u": user, "t": tk_v})

                                    session.execute(text("INSERT INTO transactions (username, ticker, shares, price, total, timestamp) VALUES (:u, :t, :s, :p, :tot, :time)"),
                                                    {"u": user, "t": tk_v, "s": -qty_v, "p": prix_v_instantane, "tot": total_v_instantane, "time": now_str})
                                    session.commit()

                                st.session_state['flash_msg'] = ("success", f"Vente de {qty_v} {tk_v} à ${prix_v_instantane:,.2f} effectuée !")
                                st.rerun()
                            else: st.error("Vous ne possédez plus ces actions.")
            else: st.info("Vous n'avez aucune position ouverte actuellement.")

        afficher_positions_live()

    # --- ONGLET 3 : HISTORIQUE ---
    elif tab_choisi == "Mon Historique":
        tx_all = conn.query("SELECT timestamp, CASE WHEN shares > 0 THEN 'ACHAT' ELSE 'VENTE' END as type, ticker, ABS(shares) as shares, price, total FROM transactions WHERE username=:u ORDER BY id DESC", params={"u": user}, ttl=0)
        if not tx_all.empty:
            tx_all.columns = ["Date & Heure", "Type", "Action", "Quantité", "Prix ($)", "Total ($)"]
            st.dataframe(tx_all, use_container_width=True, hide_index=True)
        else: st.info("Aucune transaction.")

    # --- ONGLET 4 : CLASSEMENT (AVEC RECHERCHE & SURGLIGNAGE JAUNE) ---
    elif tab_choisi == "Classement":
        col_r1, col_r2, col_r3 = st.columns([2, 2, 1])
        with col_r1:
            grp_filter = st.selectbox("Filtrer par groupe :", ["Tous les groupes"] + LISTE_GROUPES)
        with col_r2:
            search_user_rank = st.text_input("Rechercher un élève :", value="", placeholder="Tapez un nom d'élève...")
        with col_r3:
            st.markdown("<br>", unsafe_allow_html=True)
            if st.button("Actualiser", use_container_width=True):
                obtenir_donnees_classement.clear()
                st.rerun()

        df_classement = obtenir_donnees_classement(grp_filter)
        if not df_classement.empty:
            top3 = df_classement.head(3)
            classes_podium = ["podium-or", "podium-argent", "podium-bronze"]
            cols_podium = st.columns(len(top3))
            for i, (_, r_pod) in enumerate(top3.iterrows()):
                cols_podium[i].markdown(f"<div class='podium-card {classes_podium[i]} podium-{i + 1}'><div class='podium-rang'>{int(r_pod['Rang'])}</div><div class='podium-nom'>{r_pod['Élève']}</div><div class='podium-val'>{r_pod['Portefeuille']}</div><div class='podium-perf'>{r_pod['Performance']}</div></div>", unsafe_allow_html=True)

            moi = df_classement[df_classement['Élève'] == user]
            if not moi.empty:
                r_moi = moi.iloc[0]
                st.markdown(f"<div class='mon-rang'><span class='mon-rang-label'>Ton rang</span><span class='mon-rang-val'>#{int(r_moi['Rang'])}</span><span class='mon-rang-detail'>{r_moi['Portefeuille']} · {r_moi['Performance']}</span></div>", unsafe_allow_html=True)

            def highlight_row(row):
                styles = [''] * len(row)
                if str(row['Élève']) == user:
                    styles = ['background-color: rgba(229, 9, 20, 0.30); color: #FFFFFF; font-weight: 700;'] * len(row)
                if search_user_rank and search_user_rank.strip() and search_user_rank.strip().lower() in str(row['Élève']).lower():
                    styles = ['background-color: rgba(229, 9, 20, 0.95); color: #FFFFFF; font-weight: 700;'] * len(row)
                return styles

            styled_df = df_classement.style.apply(highlight_row, axis=1)
            st.dataframe(styled_df, use_container_width=True, hide_index=True)
        else:
            st.info("Aucun élève trouvé pour ce classement.")

    # --- ONGLET 5 : SUPERVISION PROFESSEUR ---
    elif tab_choisi == "Supervision Prof":
        pin = st.text_input("PIN Enseignant :", type="password") if user.lower() not in ['prof', 'admin'] else "1959"
        if pin == "1959":
            with st.expander("Gestion des mots de passe (Supabase)"):
                st.warning("Ce lien ouvre la console Supabase, où les mots de passe des élèves peuvent être modifiés directement. À utiliser avec prudence.")
                code_supabase = st.text_input("Code d'accès :", type="password", key="code_supabase")
                if code_supabase == "996633":
                    st.link_button("Ouvrir la console Supabase", "https://supabase.com/dashboard/project/pixbjedmpvvjqswltzkq/editor/17585?schema=public")
                elif code_supabase:
                    st.error("Code incorrect.")

            with st.expander("Correction règle 9h30 (achats pré-marché)"):
                st.info(
                    "Détecte automatiquement les achats avant 9h30 sur une période donnée, "
                    "pour des actions dont la clôture du jour de bourse précédent était sous 5 $, "
                    "puis annule d'un coup toutes les transactions du jour fautif pour ces actions "
                    "(achats et ventes), comme si elles n'avaient jamais existé : cash remboursé, "
                    "portefeuille recalculé."
                )
                from datetime import date as _date, timedelta as _td
                _auj = _date.today()
                col_d1, col_d2 = st.columns(2)
                with col_d1:
                    date_debut = st.date_input("Du", value=_auj - _td(days=7), key="d9_debut")
                with col_d2:
                    date_fin = st.date_input("Au", value=_auj, key="d9_fin")
                if st.button("Analyser la période", key="btn_analyse_9h30"):
                    ds0, ds1 = date_debut.isoformat(), date_fin.isoformat()
                    with st.spinner(f"Analyse du {ds0} au {ds1} en cours..."):
                        viol = analyser_violations_9h30(ds0, ds1)
                        if not viol.empty:
                            viol = calculer_gains_9h30(viol)
                    if viol.empty:
                        st.success(f"Aucun achat fautif détecté entre le {ds0} et le {ds1} avant 9h30.")
                        st.session_state.pop('violations_9h30', None)
                    else:
                        st.session_state['violations_9h30'] = viol
                        st.rerun()
                viol = st.session_state.get('violations_9h30')
                if viol is not None and not viol.empty:
                    resume = viol.groupby(['date', 'username', 'ticker']).agg(
                        total_achats=('total', 'sum'),
                        prix_achat=('prix_achat', 'first'),
                        cloture_veille=('cloture_veille', 'first'),
                        gain_estime=('gain_estime', 'first'),
                        heures_achat=('heures_achat', 'first'),
                        heures_vente=('heures_vente', 'first')
                    ).reset_index()
                    resume.columns = ["Date", "Élève", "Action", "Total achats ($)", "Prix achat ($)", "Clôture veille ($)", "Gain estimé ($)", "Achat à", "Revente à"]
                    resume["Sélectionner"] = True
                    st.markdown(f"**{len(resume)} cas élève/action/jour concernés, {len(viol)} achats fautifs au total.** Coche les cas à annuler.")
                    edited = st.data_editor(
                        resume,
                        column_config={"Sélectionner": st.column_config.CheckboxColumn("Sélectionner")},
                        disabled=[c for c in resume.columns if c != "Sélectionner"],
                        hide_index=True, use_container_width=True, key="editor_9h30"
                    )
                    sel = edited[edited["Sélectionner"]]
                    st.markdown(f"**{len(sel)} cas sélectionnés.**")
                    if st.button("Annuler la sélection", key="btn_exec_9h30", disabled=sel.empty):
                        cles = set(zip(sel["Date"], sel["Élève"], sel["Action"]))
                        viol_sel = viol[viol.apply(lambda r: (r['date'], r['username'], r['ticker']) in cles, axis=1)]
                        with st.spinner("Annulation en cours..."):
                            nb_c, nb_tx, tot_cash = executer_annulation_9h30(viol_sel)
                        st.session_state.pop('violations_9h30', None)
                        st.success(f"Terminé : {nb_tx} transactions annulées pour {nb_c} cas. Cash total réajusté : ${tot_cash:+,.2f}.")
                        st.rerun()

            grp_p = st.selectbox("Groupe :", ["Tous les groupes"] + LISTE_GROUPES, key="prof_grp")

            if grp_p == "Tous les groupes":
                e_list = conn.query("SELECT username FROM users ORDER BY username", ttl=0)['username'].tolist()
            else:
                e_list = conn.query("SELECT username FROM users WHERE groupe=:g ORDER BY username", params={"g": grp_p}, ttl=0)['username'].tolist()

            if e_list:
                e_sel = st.selectbox("Élève à inspecter :", e_list)
                e_data_df = conn.query("SELECT cash, groupe FROM users WHERE username=:u", params={"u": e_sel}, ttl=0)

                if not e_data_df.empty:
                    e_data = e_data_df.iloc[0]
                    e_cash, e_grp = float(e_data['cash']), e_data['groupe']
                    e_pos = conn.query("SELECT ticker, shares, avg_price FROM portfolio WHERE username=:u", params={"u": e_sel}, ttl=0)

                    pos_rows = []
                    e_val_act = 0.0
                    if not e_pos.empty:
                        e_tks = e_pos['ticker'].unique().tolist()
                        prix_dict_prof = obtenir_prix_groupes(e_tks)

                        for _, row in e_pos.iterrows():
                            tk = str(row['ticker'])
                            sh = int(row['shares'])
                            pm = float(row['avg_price'] or 0.0)
                            pa_live = prix_dict_prof.get(tk.upper())
                            pa = pa_live if pa_live is not None else pm
                            val = sh * pa
                            pnl = (pa - pm) * sh
                            pnl_pct = ((pa - pm) / pm * 100) if pm > 0 else 0.0
                            e_val_act += val

                            fmt_pa = f"${pa:,.4f}" if pa < 1 else f"${pa:,.2f}"
                            fmt_pm = f"${pm:,.4f}" if pm < 1 else f"${pm:,.2f}"

                            pos_rows.append({
                                "Action": tk,
                                "Quantité": sh,
                                "Prix Moyen": fmt_pm,
                                "Prix Actuel": fmt_pa,
                                "Valeur Totale": f"${val:,.2f}",
                                "Gain / Perte": f"${pnl:+,.2f}",
                                "Rendement": f"{pnl_pct:+.2f}%"
                            })

                    e_tot = e_cash + e_val_act
                    e_pnl = e_tot - 10000.00
                    e_perf = (e_pnl / 10000.00) * 100

                    col_top_prof1, col_top_prof2, col_top_prof3 = st.columns([2.5, 1, 1])
                    with col_top_prof1:
                        st.markdown(f"#### Fiche d'investisseur : **{e_sel}** ({e_grp})")

                    with col_top_prof2:
                        if st.button(f"Réinitialiser {e_sel}", use_container_width=True):
                            with conn.session as session:
                                session.execute(text("UPDATE users SET cash = 10000.00 WHERE username = :u"), {"u": e_sel})
                                session.execute(text("DELETE FROM portfolio WHERE username = :u"), {"u": e_sel})
                                session.execute(text("DELETE FROM transactions WHERE username = :u"), {"u": e_sel})
                                session.commit()
                            st.session_state['flash_msg'] = ("success", f"Le compte de {e_sel} a été réinitialisé à 10 000 $ !")
                            st.rerun()

                    with col_top_prof3:
                        if st.button("Supprimer le compte", use_container_width=True):
                            with conn.session as session:
                                session.execute(text("DELETE FROM portfolio WHERE username = :u"), {"u": e_sel})
                                session.execute(text("DELETE FROM transactions WHERE username = :u"), {"u": e_sel})
                                session.execute(text("DELETE FROM users WHERE username = :u"), {"u": e_sel})
                                session.commit()
                            st.session_state['flash_msg'] = ("success", f"Le profil de {e_sel} a été définitivement supprimé !")
                            st.rerun()

                    col_t1, col_t2, col_t3, col_t4 = st.columns(4)
                    col_t1.markdown(f"<div class='kpi-card'><div class='kpi-label'>Disponible (Cash)</div><div class='kpi-value'>${e_cash:,.2f}</div></div>", unsafe_allow_html=True)
                    col_t2.markdown(f"<div class='kpi-card'><div class='kpi-label'>Actions Possédées</div><div class='kpi-value'>${e_val_act:,.2f}</div></div>", unsafe_allow_html=True)
                    col_t3.markdown(f"<div class='kpi-card'><div class='kpi-label'>Valeur Totale</div><div class='kpi-value'>${e_tot:,.2f}</div></div>", unsafe_allow_html=True)
                    classe_delta_p = "kpi-delta up" if e_pnl >= 0 else "kpi-delta down"
                    fleche_delta_p = "▲" if e_pnl >= 0 else "▼"
                    classe_carte_p = "kpi-card kpi-up" if e_pnl >= 0 else "kpi-card kpi-down"
                    col_t4.markdown(f"<div class='{classe_carte_p}'><div class='kpi-label'>Gains / Pertes</div><div class='kpi-value'>${e_pnl:+,.2f}</div><div class='{classe_delta_p}'>{fleche_delta_p} {e_perf:+.2f}%</div></div>", unsafe_allow_html=True)

                    st.markdown("##### Portefeuille Détaillé")
                    if pos_rows:
                        st.dataframe(pd.DataFrame(pos_rows), use_container_width=True, hide_index=True)
                    else:
                        st.info("Cet élève n'a aucune position ouverte actuellement.")

                    st.markdown("##### Historique des Transactions")
                    tx_e = conn.query("SELECT timestamp, CASE WHEN shares > 0 THEN 'ACHAT' ELSE 'VENTE' END as type, ticker, ABS(shares) as shares, price, total FROM transactions WHERE username=:u ORDER BY id DESC", params={"u": e_sel}, ttl=0)
                    if not tx_e.empty:
                        tx_e.columns = ["Date & Heure", "Type", "Action", "Quantité", "Prix ($)", "Total ($)"]
                        st.dataframe(tx_e, use_container_width=True, hide_index=True)
                    else:
                        st.info("Aucune transaction enregistrée.")
            else:
                st.info("Aucun élève trouvé dans ce groupe.")
