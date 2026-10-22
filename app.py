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

# --- MODE MAINTENANCE (activé le 21 oct. 2026 : problèmes techniques en classe) ---
# Pour rouvrir le site : passer à False et redéployer.
MODE_MAINTENANCE = False
if MODE_MAINTENANCE:
    st.markdown("""
    <style>
        @import url('https://fonts.googleapis.com/css2?family=Bebas+Neue&family=Work+Sans:wght@400;600;800&display=swap');
        .maint-wrap { max-width: 720px; margin: 9vh auto 0 auto; text-align: center; padding: 48px 32px; background: #141414; border: 1px solid #2b2b2b; border-top: 4px solid #E50914; border-radius: 14px; }
        .maint-marque { font-family: 'Bebas Neue', 'Arial Narrow', sans-serif; font-size: 64px; letter-spacing: 0.04em; color: #FFFFFF; line-height: 1; }
        .maint-marque span { color: #E50914; }
        .maint-titre { font-family: 'Work Sans', sans-serif; font-weight: 800; font-size: 26px; color: #FFFFFF; margin-top: 26px; }
        .maint-texte { font-family: 'Work Sans', sans-serif; font-size: 17px; color: #E8E8E8; line-height: 1.55; margin-top: 12px; }
    </style>
    <div class="maint-wrap">
        <div class="maint-marque">MONDE <span>&amp;</span> FINANCE</div>
        <div class="maint-titre">Site en maintenance</div>
        <div class="maint-texte">On corrige des problèmes techniques pour que le site fonctionne mieux.<br>Revenez un peu plus tard.</div>
        <div class="maint-texte">Vos comptes, vos positions et votre argent virtuel sont en sécurité : rien n'est perdu.</div>
    </div>
    """, unsafe_allow_html=True)
    st.stop()

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
            session.execute(text('''
                CREATE TABLE IF NOT EXISTS groupes_fermes (
                    groupe TEXT PRIMARY KEY
                );
            '''))
            session.execute(text('''
                CREATE TABLE IF NOT EXISTS regles_vues (
                    username TEXT PRIMARY KEY,
                    version INT,
                    vue_le TEXT
                );
            '''))
            session.execute(text('''
                CREATE TABLE IF NOT EXISTS photos (
                    username TEXT PRIMARY KEY,
                    image TEXT,
                    maj TEXT
                );
            '''))
            session.execute(text('''
                CREATE TABLE IF NOT EXISTS prix_relais (
                    ticker TEXT PRIMARY KEY,
                    prix_natif DOUBLE PRECISION,
                    prev_natif DOUBLE PRECISION,
                    ouverture DOUBLE PRECISION,
                    haut DOUBLE PRECISION,
                    bas DOUBLE PRECISION,
                    haut52 DOUBLE PRECISION,
                    bas52 DOUBLE PRECISION,
                    devise TEXT,
                    maj TEXT
                );
            '''))
            session.execute(text('''
                CREATE TABLE IF NOT EXISTS historique_relais (
                    ticker TEXT,
                    jour TEXT,
                    o DOUBLE PRECISION,
                    h DOUBLE PRECISION,
                    l DOUBLE PRECISION,
                    c DOUBLE PRECISION,
                    v DOUBLE PRECISION,
                    PRIMARY KEY (ticker, jour)
                );
            '''))
            session.commit()
        except Exception:
            session.rollback()

init_db()

# --- FENETRE OBLIGATOIRE DES REGLES DU JEU (1 seule fois par version) ---
VERSION_REGLES = 3

@st.dialog("Nouvelles règles du jeu")
def afficher_popup_regles(username):
    st.markdown(
        "**Lis ça une fois. Après, tu ne pourras plus dire que tu ne savais pas.**\n\n"
        "**1. 3 bourses seulement : Toronto, New York et Nasdaq.**\n"
        "Fini les cryptos, les devises, les paris sur la peur. "
        "*En vrai, on ne trade pas le franc suisse à l'école. On joue à la vraie bourse.*\n\n"
        "**2. Les prix sont affichés dans la devise du titre (ex. $ US pour Apple), comme sur les vrais sites.**\n"
        "*Ton compte reste en dollars canadiens : à l'achat et à la vente, le montant est converti au taux de change du jour, et tu vois l'ajustement avant de confirmer.*\n\n"
        "**3. Ta position ne peut pas dépasser 5 % de ce qui s'échange chaque jour sur un titre.**\n"
        "*En vrai, un ordre géant fait bouger le prix.*\n\n"
        "**4. Détention minimale : 1 h pour les actions, 24 h pour les ETF.**\n"
        "*Acheter et revendre en 60 secondes sans réfléchir, ce n'est pas investir.*\n\n"
        "**5. Rappel : 4 titres différents minimum, 5 achats par mois.**\n"
        "*C'est une évaluation, pas juste un jeu.*\n\n"
        "**6. Les points perdus aux vérifications ne reviennent pas.**\n"
        "*Tu connais les règles : c'est un risque que tu prends.*"
    )
    lu = st.checkbox("J'ai lu et je comprends ces règles.")
    if st.button("Fermer", disabled=not lu, use_container_width=True):
        now_str = datetime.now(ZoneInfo("America/Toronto")).strftime("%Y-%m-%d %H:%M:%S")
        with conn.session as session:
            session.execute(
                text("INSERT INTO regles_vues (username, version, vue_le) VALUES (:u, :v, :d) "
                     "ON CONFLICT (username) DO UPDATE SET version=:v, vue_le=:d"),
                {"u": username, "v": VERSION_REGLES, "d": now_str})
            session.commit()
        st.rerun()


def verifier_popup_regles(username):
    """Affiche la fenêtre des règles tant que l'élève n'a pas vu la version en cours."""
    try:
        r = conn.query("SELECT version FROM regles_vues WHERE username=:u", params={"u": username}, ttl=0)
        if r.empty or int(r.iloc[0]['version']) < VERSION_REGLES:
            afficher_popup_regles(username)
    except Exception:
        pass

# --- VALIDATION STRICTE DES INSTRUMENTS AUTORISÉS ---
# Règle de Mathieu (17 oct. 2026) : actions et FNB seulement, cotés uniquement
# sur TSX (Toronto), NYSE ou Nasdaq. Aucune crypto, devise, future ni indice ;
# aucun marché OTC, TSX-V, NEO, CSE ni bourse étrangère.
# Codes d'échange Yahoo : TOR=TSX, NYQ=NYSE, NMS/NGM/NCM=Nasdaq,
# PCX=NYSE Arca, ASE=NYSE American, BTS=Cboe BZX (lieux de cotation des FNB).
EXCHANGES_AUTORISES = {'TOR', 'NYQ', 'NMS', 'NGM', 'NCM', 'PCX', 'ASE', 'BTS'}
TYPES_AUTORISES = {'EQUITY', 'ETF'}

def _symbole_syntaxe_ok(symbol):
    """Pré-filtre sans appel réseau : rejette devises (=X), futures (=F),
    indices (^...), cryptos (-USD) et symboles vides."""
    s = (symbol or '').upper().strip()
    if not s:
        return False
    return not ('^' in s or '=' in s or s.endswith('-USD'))

def instrument_autorise(symbol, exch_code="", exch_disp="", quote_type=""):
    """Vrai si l'instrument peut être acheté dans le jeu."""
    s = (symbol or '').upper().strip()
    if not _symbole_syntaxe_ok(s):
        return False
    # Seul le suffixe .TO (TSX Toronto) est accepté ; toute autre bourse
    # à suffixe (TSX-V, NEO, CSE, Paris, Tokyo...) est rejetée.
    if '.' in s and not s.endswith('.TO'):
        return False
    # Si l'info d'échange est fournie, elle doit être TSX/NYSE/Nasdaq.
    codes = set(f"{exch_code} {exch_disp}".upper().split())
    if codes and not (codes & EXCHANGES_AUTORISES):
        return False
    # Si le type d'instrument est fourni, actions et FNB seulement.
    qt = (quote_type or '').upper().strip()
    if qt and qt not in TYPES_AUTORISES:
        return False
    return True

# --- CONVERSION AUTOMATIQUE USD -> CAD ---
# L'élève ne fait aucun calcul : tous les prix sont affichés et comptabilisés
# en dollars canadiens. Un seul appel Yahoo par heure, partagé par les 200+
# élèves via le cache (aucun ralentissement).
@st.cache_resource
def _memo_dernier_taux():
    """Dernier taux USD/CAD valide, gardé tant que l'app roule. Filet de
    sécurité : une coupure des sources ne doit jamais faire retomber les
    conversions à « aucune conversion » (prix US alors traités comme des
    CAD : valeur totale amputée d'environ 2 600 $ à l'écran sur un seul
    compte, vu le 21 oct. 2026)."""
    return {"taux": None, "echec": 0.0}


@st.cache_data(ttl=1800, show_spinner=False)
def _taux_usdcad_sources():
    """Taux USD/CAD depuis les sources, dans l'ordre. Lève une exception
    si aucune source ne répond : Streamlit ne met pas les exceptions en
    cache, donc un échec ne fige pas le taux pour 30 minutes."""
    # 1) Yahoo (temps réel)
    try:
        r = yf.Ticker('USDCAD=X').fast_info.get('lastPrice')
        if r is not None and not pd.isna(r) and float(r) > 0:
            return float(r)
    except Exception:
        pass
    # 2) Frankfurter (taux de référence quotidien, indépendant de Yahoo)
    try:
        d = requests.get('https://api.frankfurter.dev/v1/latest?base=USD&symbols=CAD',
                         timeout=5).json()
        v = float(d['rates']['CAD'])
        if v > 0:
            return v
    except Exception:
        pass
    raise RuntimeError("Taux USD/CAD indisponible (toutes sources)")


def obtenir_taux_usdcad():
    memo = _memo_dernier_taux()
    t = None
    # Pendant une panne totale, on ne retente les sources qu'une fois par
    # minute ; entre-temps, le dernier taux connu sert les conversions.
    if datetime.now().timestamp() - memo.get("echec", 0.0) > 60:
        try:
            t = _taux_usdcad_sources()
        except Exception:
            memo["echec"] = datetime.now().timestamp()
    if t:
        memo["taux"] = t
        return t
    return memo["taux"]

def convertir_vers_cad(prix, devise):
    """Convertit un prix vers le dollar canadien (comptabilité du compte)."""
    if prix is None:
        return None
    try:
        p = float(prix)
    except (TypeError, ValueError):
        return None
    if str(devise or '').upper() == 'USD':
        taux = obtenir_taux_usdcad()
        if taux:
            return round(p * taux, 4)
    return round(p, 4)


# --- AFFICHAGE EN DEVISE NATURELLE (depuis le 20 oct. 2026) ---
# Les prix s'affichent dans la devise du titre (ex. $ US pour Apple), comme
# sur les vrais sites. Le compte de l'élève reste en CAD : la conversion
# s'applique au moment de l'achat/vente, avec l'ajustement de change
# indiqué. La comptabilité (transactions, prix moyens, totaux) ne change
# pas : toujours en CAD.
def devise_naturelle(ticker_symbol):
    """Devise naturelle d'après le symbole : suffixe canadien (.TO, .V,
    .NE, .CN) = CAD, sinon USD (NYSE/Nasdaq). Affichage seulement."""
    t = str(ticker_symbol or '').upper().strip()
    return 'CAD' if '.' in t else 'USD'


def vers_natif(prix_cad, devise):
    """Convertit un montant CAD vers la devise naturelle, au taux du jour.
    AFFICHAGE seulement : la comptabilité reste en CAD."""
    if prix_cad is None:
        return None
    try:
        p = float(prix_cad)
    except (TypeError, ValueError):
        return None
    if str(devise or '').upper() == 'USD':
        taux = obtenir_taux_usdcad()
        if taux:
            return round(p / taux, 4)
    return round(p, 4)


def fmt_prix(valeur, devise=None):
    """Formate un prix affiché : $X,XX, suffixe ' US' si devise USD."""
    if valeur is None:
        return "n/d"
    v = float(valeur)
    s = f"${v:,.4f}" if v < 1 else f"${v:,.2f}"
    if str(devise or '').upper() == 'USD':
        s += " US"
    return s

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

    /* Cartes de vente rapide */
    div[data-testid="stVerticalBlockBorderWrapper"] {
        background: linear-gradient(180deg, #1E1E1E 0%, #161616 100%) !important;
        border: 1px solid #2E2E2E !important;
        border-radius: 14px !important;
    }
    div[data-testid="stVerticalBlockBorderWrapper"]:hover {
        border-color: rgba(229, 9, 20, 0.45) !important;
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
    .podium-jour {
        margin-top: 10px;
        padding: 7px 10px;
        border: 1px solid rgba(255, 255, 255, 0.22);
        border-radius: 9px;
        background: rgba(0, 0, 0, 0.35);
        font-size: 0.82rem;
        font-weight: 700;
        color: #FFFFFF;
        font-variant-numeric: tabular-nums;
    }
    .podium-jour .hausse { color: #4ADE80; }
    .podium-jour .baisse { color: #FF6B6B; }
    .podium-photo-wrap {
        position: relative;
        width: 80px;
        margin: 2px auto 10px;
    }
    .podium-photo {
        width: 80px; height: 80px;
        border-radius: 50%;
        object-fit: cover;
        display: block;
        border: 3px solid #FFFFFF;
        box-shadow: 0 10px 22px rgba(0, 0, 0, 0.55);
    }
    .podium-initiales {
        width: 80px; height: 80px;
        border-radius: 50%;
        display: flex; align-items: center; justify-content: center;
        font-family: 'Bebas Neue', 'Work Sans', sans-serif;
        font-size: 1.7rem; color: #FFFFFF;
        background: radial-gradient(circle at 32% 30%, #3d3d3d, #171717 72%);
        border: 3px solid #FFFFFF;
        box-shadow: 0 10px 22px rgba(0, 0, 0, 0.55);
    }
    .podium-or .podium-photo, .podium-or .podium-initiales { border-color: #FFD700; }
    .podium-argent .podium-photo, .podium-argent .podium-initiales { border-color: #E8E8E8; }
    .podium-bronze .podium-photo, .podium-bronze .podium-initiales { border-color: #E09A5A; }
    .podium-badge {
        position: absolute; right: -5px; bottom: -5px;
        width: 29px; height: 29px;
        border-radius: 50%;
        background: #FFFFFF; color: #111111;
        font-weight: 800; font-size: 0.95rem;
        display: flex; align-items: center; justify-content: center;
        border: 2px solid rgba(0, 0, 0, 0.25);
        box-shadow: 0 4px 10px rgba(0, 0, 0, 0.5);
    }
    .podium-or .podium-badge { background: #FFD700; }
    .podium-argent .podium-badge { background: #E8E8E8; }
    .podium-bronze .podium-badge { background: #E09A5A; }
    .podium-nom, .podium-val, .podium-perf, .podium-jour { text-align: center; }
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
def _recherche_cached(query):
    """Recherche de symboles chez Yahoo, deux serveurs en relais.
    Lève une exception si les deux échouent : Streamlit ne met pas les
    exceptions en cache. Avant, un échec retournait une liste vide que
    le cache figeait pendant une heure, donc la recherche restait morte
    pour ce mot-là même après le retour de Yahoo (21 oct. 2026)."""
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'}
    derniere_erreur = None
    for hote in ("query2", "query1"):
        url = f"https://{hote}.finance.yahoo.com/v1/finance/search?q={query}&quotesCount=10&newsCount=0"
        try:
            r = requests.get(url, headers=headers, timeout=3)
            if r.status_code != 200:
                derniere_erreur = Exception(f"HTTP {r.status_code}")
                continue
            data = r.json()
            results = []
            for quote in data.get('quotes', []):
                symbol = quote.get('symbol')
                shortname = quote.get('shortname') or quote.get('longname') or symbol
                exch = quote.get('exchDisp') or quote.get('exchange') or ''
                type_disp = quote.get('typeDisp') or ''
                exch_code = (quote.get('exchange') or '').upper()

                if symbol and _symbole_syntaxe_ok(symbol):
                    if (type_disp in ['Equity', 'ETF', 'Action', 'Stock'] or not type_disp):
                        if not exch_code or exch_code in EXCHANGES_AUTORISES:
                            results.append({'symbol': symbol, 'label': f"{shortname} ({symbol}) — {exch}"})
            return results
        except Exception as e:
            derniere_erreur = e
            continue
    raise derniere_erreur or Exception("Recherche Yahoo indisponible")


def rechercher_symbole_universel(query):
    if not query or len(query.strip()) < 1: return []
    try:
        return _recherche_cached(query)
    except Exception:
        return []

@st.cache_data(ttl=120, show_spinner=False)
def obtenir_donnees_favoris(tickers_tuple):
    """Prix NATIF + variation du jour pour les favoris, en un seul appel groupé. {ticker: (prix_natif, var_pct, devise)}"""
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
                devise = str(fi.get('currency') or 'CAD').upper()
                px = fi.get('lastPrice') or fi.get('regularMarketPrice') or fi.get('last_price')
                op = fi.get('open') or fi.get('openPrice')
                if px is not None and not pd.isna(px) and float(px) > 0:
                    px = float(px)
                    if op is not None and not pd.isna(op) and float(op) > 0:
                        vp = (px - float(op)) / float(op) * 100
                    else:
                        vp = 0.0
                    out[tk] = (round(px, 4), round(vp, 2), devise)
                else:
                    out[tk] = (None, None, devise)
            except Exception:
                out[tk] = (None, None, devise_naturelle(tk))
        return out
    except Exception:
        return {}

@st.cache_data(ttl=10, show_spinner=False)
def obtenir_prix_actuel(ticker_symbol):
    """Prix d'exécution d'un ordre. Yahoo d'abord ; si Yahoo ne répond
    pas depuis le nuage, repli sur le relais de prix (sonde multi-sources),
    pour qu'un hoquet de Yahoo ne bloque plus les achats et les ventes."""
    try:
        t = yf.Ticker(ticker_symbol)
        data = t.fast_info
        devise = str(data.get('currency') or 'CAD').upper()
        prix = data.get('lastPrice') or data.get('regularMarketPrice') or data.get('last_price')
        if prix is not None and not pd.isna(prix) and float(prix) > 0:
            return convertir_vers_cad(float(prix), devise)
        hist = t.history(period="1d")
        if not hist.empty:
            return convertir_vers_cad(float(hist['Close'].iloc[-1]), devise)
    except Exception:
        pass
    entree = _entree_depuis_relais(ticker_symbol)
    return entree["cad"] if entree else None

# --- LIMITE DE POSITION : 5 % DU VOLUME QUOTIDIEN MOYEN ---
# Un élève ne peut pas détenir plus que 5 % de ce qui s'échange vraiment
# chaque jour sur un titre (en $). En vrai, un ordre plus gros ferait bouger
# le prix. Donnée lente (moyenne 10 jours) : cache 24 h partagé, zéro ralentissement.
LIMITE_VOLUME_PCT = 0.05

@st.cache_data(ttl=86400, show_spinner=False)
def _volume_quotidien_moyen_cached(ticker_symbol):
    """Volume quotidien moyen en $ CAD (moyenne des 10 derniers jours
    d'échanges x dernier prix de clôture).
    Source principale : l'historique des prix, fiable partout.
    L'ancien champ « info » de Yahoo est capricieux depuis les serveurs
    infonuagiques : c'est lui qui a bloqué ATD.TO et Tesla le 21 oct. 2026.
    On le garde seulement en dernier recours.
    Lève une exception si aucune donnée : Streamlit ne met pas les
    exceptions en cache, donc un échec temporaire ne fige plus le titre
    pour 24 h comme le faisait l'ancien None mis en cache."""
    t = yf.Ticker(ticker_symbol)
    hist = t.history(period="1mo")
    if hist is not None and not hist.empty and 'Volume' in hist.columns and 'Close' in hist.columns:
        vols = [float(v) for v in hist['Volume'].tail(10) if v is not None and float(v) > 0]
        px = float(hist['Close'].iloc[-1])
        if vols and px > 0:
            try:
                devise = str(t.fast_info.get('currency') or '').upper() or devise_naturelle(ticker_symbol)
            except Exception:
                devise = devise_naturelle(ticker_symbol)
            return convertir_vers_cad((sum(vols) / len(vols)) * px, devise)
    info = t.info or {}
    vol = info.get('averageDailyVolume10Day') or info.get('averageVolume')
    if vol and float(vol) > 0:
        devise = str(info.get('currency') or '').upper() or devise_naturelle(ticker_symbol)
        fi = t.fast_info
        px = fi.get('lastPrice') or fi.get('regularMarketPrice')
        if px:
            return convertir_vers_cad(float(vol) * float(px), devise)
    raise ValueError(f"Aucune donnée de volume pour {ticker_symbol}")


def obtenir_volume_quotidien_moyen(ticker_symbol):
    """Volume quotidien moyen en $ CAD (moyenne 10 jours x prix).
    Retourne None si indisponible : dans ce cas l'achat est BLOQUE
    (fail closed, comme un vrai courtier qui refuse les titres obscurs
    sans données de volume vérifiables)."""
    try:
        return _volume_quotidien_moyen_cached(ticker_symbol)
    except Exception:
        return None


def verifier_limite_volume(username, ticker_symbol, prix_unitaire_cad, cout_ordre_cad):
    """Retourne un message d'erreur si (position actuelle + nouvel ordre)
    dépasserait 5 % du volume quotidien moyen, sinon None.
    Si le volume est invérifiable : achat BLOQUE (fail closed)."""
    try:
        vol_moyen = obtenir_volume_quotidien_moyen(ticker_symbol)
        if not vol_moyen or vol_moyen <= 0:
            return (f"Ordre refusé : impossible de vérifier ce qui s'échange chaque jour "
                    f"sur {ticker_symbol.upper()}. Sans ces données, l'achat est bloqué. "
                    f"En vrai, ton courtier refuserait aussi de te laisser acheter un titre obscur.")
        limite = LIMITE_VOLUME_PCT * vol_moyen
        p_res = conn.query("SELECT shares FROM portfolio WHERE username=:u AND LOWER(ticker)=LOWER(:t)",
                           params={"u": username, "t": ticker_symbol}, ttl=0)
        val_existante = int(p_res.iloc[0]['shares']) * float(prix_unitaire_cad) if not p_res.empty else 0.0
        if val_existante + float(cout_ordre_cad) > limite:
            return (f"Ordre refusé : ta position sur {ticker_symbol.upper()} ne peut pas dépasser "
                    f"5 % de ce qui s'échange chaque jour ({limite:,.0f} $). "
                    f"En vrai, un ordre plus gros ferait bouger le prix.")
        return None
    except Exception:
        return None


# --- DELAI DE DETENTION MINIMUM AVANT REVENTE ---
# Actions ordinaires : 1 h minimum (anti-flip de quelques secondes).
# ETF : 24 h minimum (oblige a prendre le risque overnight, anti-faux-prophetes).
DELAI_DETENTION_UNIVERSEL_H = 1
DELAI_DETENTION_ETF_H = 24

@st.cache_data(ttl=86400, show_spinner=False)
def est_etf(ticker_symbol):
    """Vrai si le titre est un ETF (quoteType). Type quasi fixe : cache 24 h."""
    try:
        t = yf.Ticker(ticker_symbol)
        return str(t.fast_info.get('quoteType') or '').upper() == 'ETF'
    except Exception:
        return False


def delai_detention_requis(ticker_symbol):
    """Delai de detention en heures : 24 h pour les ETF, 1 h sinon."""
    return DELAI_DETENTION_ETF_H if est_etf(ticker_symbol) else DELAI_DETENTION_UNIVERSEL_H


def vente_avant_delai_bloquee(username, ticker_symbol):
    """Vrai si le dernier achat du titre date de moins que le delai requis."""
    try:
        delai_h = delai_detention_requis(ticker_symbol)
        r = conn.query(
            "SELECT MAX(timestamp) AS dernier FROM transactions WHERE username=:u AND LOWER(ticker)=LOWER(:t) AND shares > 0",
            params={"u": username, "t": ticker_symbol}, ttl=0)
        if r.empty or not r.iloc[0]['dernier']:
            return False
        dernier_achat = datetime.strptime(str(r.iloc[0]['dernier'])[:19], '%Y-%m-%d %H:%M:%S')
        dernier_achat = dernier_achat.replace(tzinfo=ZoneInfo("America/Toronto"))
        maintenant = datetime.now(ZoneInfo("America/Toronto"))
        return (maintenant - dernier_achat).total_seconds() < delai_h * 3600
    except Exception:
        return False


def message_delai_detention(ticker_symbol):
    """Message d'avertissement adapte au delai du titre."""
    if est_etf(ticker_symbol):
        return "Tu dois garder ce titre au moins 24 h avant de le revendre (ETF)."
    return "Tu dois garder ce titre au moins 1 h avant de le revendre."


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
        devise = str(data.get('currency') or 'CAD').upper()
        pc = data.get('previousClose')
        if pc is not None and not pd.isna(pc) and float(pc) > 0:
            return convertir_vers_cad(float(pc), devise)
        # Repli : historique 5 jours, prendre l'avant-dernière clôture
        # (la dernière peut être la séance du jour en cours)
        hist = t.history(period="5d")
        if hist is None or hist.empty or len(hist) < 2:
            return None
        return convertir_vers_cad(float(hist['Close'].iloc[-2]), devise)
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
        try:
            devise = str(t.fast_info.get('currency') or 'CAD').upper()
        except Exception:
            devise = 'CAD'
        return convertir_vers_cad(float(hist['Close'].iloc[-1]), devise)
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
        _info_px = prix_actuels.get(str(tk).upper())
        px = _info_px["cad"] if _info_px else None
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

@st.cache_resource
def _memo_derniers_prix():
    """Derniers prix valides obtenus par titre, gardés tant que l'app roule.
    Filet de sécurité : quand Yahoo se tait complètement (direct ET
    historique en même temps), l'affichage retombait sur le prix d'achat
    et tous les gains tombaient à 0,00 $ (vu le 22 oct. 2026). Avec ce
    filet, on affiche le dernier prix réel connu plutôt qu'un faux zéro."""
    return {}


# --- RELAIS DE PRIX (sources multiples, indépendant du nuage) ---
# Une sonde sur la machine de Muse interroge Yahoo ET l'API Nasdaq
# toutes les minutes et écrit les prix dans la base (tables prix_relais
# et historique_relais). Quand Yahoo ne répond pas depuis les serveurs
# de Streamlit (adresse partagée limitée en pleine classe), l'app lit
# le relais au lieu de rester muette : positions, achats, détails et
# graphiques continuent de fonctionner.

def _relais_lire_prix(tickers):
    """Lignes du relais pour une liste de titres : {TICKER: ligne}."""
    propres = [str(t).strip().upper() for t in tickers if t and str(t).strip()]
    if not propres:
        return {}
    try:
        marques = ", ".join(f":t{i}" for i in range(len(propres)))
        params = {f"t{i}": t for i, t in enumerate(propres)}
        df = conn.query(
            "SELECT ticker, prix_natif, prev_natif, ouverture, haut, bas, "
            f"haut52, bas52, devise FROM prix_relais WHERE ticker IN ({marques})",
            params=params, ttl=0)
        return {str(r['ticker']).upper(): r for _, r in df.iterrows()}
    except Exception:
        return {}


def _entree_depuis_ligne_relais(ligne, ticker_symbol):
    """Convertit une ligne prix_relais au format des prix groupés."""
    if ligne is None:
        return None
    try:
        px = float(ligne['prix_natif'])
        if px <= 0:
            return None
    except Exception:
        return None
    devise = str(ligne['devise'] or '').upper() or devise_naturelle(ticker_symbol)
    prev_cad = None
    prev = ligne['prev_natif']
    if prev is not None and not pd.isna(prev) and float(prev) > 0:
        prev_cad = convertir_vers_cad(float(prev), devise)
    return {"cad": convertir_vers_cad(px, devise), "natif": round(px, 4),
            "devise": devise, "prev_cad": prev_cad}


def _entree_depuis_relais(ticker_symbol):
    lignes = _relais_lire_prix([ticker_symbol])
    return _entree_depuis_ligne_relais(
        lignes.get(str(ticker_symbol).strip().upper()), ticker_symbol)


def _prix_depuis_historique(ticker_symbol):
    """Repli prix : dernière clôture connue (5 derniers jours).
    Sert quand le prix en direct de Yahoo ne répond pas : sans ce repli,
    l'affichage remplaçait le prix actuel par le prix d'achat et le
    gain/perte de la position tombait à exactement 0,00 $ (vu le
    21 oct. 2026, ex. Rob Thibeault). Un gain presque juste, basé sur
    la dernière clôture, vaut mieux qu'un faux zéro."""
    vide = {"cad": None, "natif": None, "devise": devise_naturelle(ticker_symbol), "prev_cad": None}
    try:
        hist = yf.Ticker(ticker_symbol).history(period="5d")
        if hist is None or hist.empty or 'Close' not in hist.columns:
            return vide
        devise = devise_naturelle(ticker_symbol)
        px = float(hist['Close'].iloc[-1])
        if px <= 0:
            return vide
        prev_cad = None
        if len(hist) >= 2:
            prev_cad = convertir_vers_cad(float(hist['Close'].iloc[-2]), devise)
        return {"cad": convertir_vers_cad(px, devise), "natif": round(px, 4),
                "devise": devise, "prev_cad": prev_cad}
    except Exception:
        return vide


@st.cache_data(ttl=30, show_spinner=False)
def obtenir_prix_groupes(tickers_list):
    if not tickers_list:
        return {}
    clean_tickers = list(set([str(t).strip().upper() for t in tickers_list if t and str(t).strip()]))
    if not clean_tickers:
        return {}
    try:
        data = yf.Tickers(" ".join(clean_tickers))
    except Exception:
        data = None
    prix_dict = {}
    for tk in clean_tickers:
        entree = None
        if data is not None:
            try:
                info = data.tickers[tk].fast_info
                devise = str(info.get('currency') or 'CAD').upper()
                px = info.get('lastPrice') or info.get('regularMarketPrice') or info.get('last_price')
                if px is not None and not pd.isna(px) and float(px) > 0:
                    natif = float(px)
                    prev = info.get('previousClose')
                    prev_cad = None
                    if prev is not None and not pd.isna(prev):
                        prev_cad = convertir_vers_cad(float(prev), devise)
                    entree = {"cad": convertir_vers_cad(natif, devise),
                              "natif": round(natif, 4), "devise": devise,
                              "prev_cad": prev_cad}
            except Exception:
                entree = None
        if entree is None:
            entree = _prix_depuis_historique(tk)
        # Filet « dernier prix connu » : si les deux voies Yahoo sont
        # muettes (cad = None), on réutilise le dernier prix réel obtenu
        # pour ce titre plutôt que de laisser l'affichage retomber sur le
        # prix d'achat, ce qui affichait un faux gain de 0,00 $ partout
        # (vu le 22 oct. 2026). Si un prix valide arrive, il alimente le
        # filet pour les prochains hoquets.
        memo_prix = _memo_derniers_prix()
        if entree is not None and entree.get("cad") is not None:
            memo_prix[tk] = dict(entree)
        elif memo_prix.get(tk):
            entree = dict(memo_prix[tk])
        prix_dict[tk] = entree
    # Repli relais : les titres restés sans prix (Yahoo muet des deux
    # voies ET filet vide) sont remplis depuis la table du relais.
    manquants = [tk for tk, e in prix_dict.items()
                 if e is None or e.get("cad") is None]
    if manquants:
        lignes = _relais_lire_prix(manquants)
        for tk in manquants:
            entree_r = _entree_depuis_ligne_relais(lignes.get(tk), tk)
            if entree_r is not None and entree_r.get("cad") is not None:
                prix_dict[tk] = entree_r
                _memo_derniers_prix()[tk] = dict(entree_r)
    return prix_dict

def _details_voie_rapide(t, ticker_symbol):
    """Voie rapide (fast_info). Retourne le dict de détails, la chaîne
    'non_na' si le titre est refusé (mauvaise bourse ou mauvais type),
    ou None si Yahoo n'a pas répondu (échec technique, pas un refus)."""
    info = t.fast_info

    # Validation stricte : actions/FNB du TSX, NYSE ou Nasdaq seulement.
    exch = str(info.get('exchange') or '')
    qtype = str(info.get('quoteType') or '')
    if not instrument_autorise(ticker_symbol, exch_code=exch, quote_type=qtype):
        return "non_na"

    devise = str(info.get('currency') or 'CAD').upper()

    last = info.get('lastPrice') or info.get('regularMarketPrice') or info.get('last_price')
    if last is None or pd.isna(last) or float(last) <= 0:
        hist = t.history(period="2d")
        if hist is not None and not hist.empty:
            last = float(hist['Close'].iloc[-1])
        else:
            return None
    else:
        last = float(last)

    open_p = info.get('open') or info.get('openPrice')
    if open_p is None or pd.isna(open_p):
        hist = t.history(period="2d")
        if hist is not None and len(hist) >= 2:
            open_p = float(hist['Close'].iloc[-2])
        elif hist is not None and not hist.empty:
            open_p = float(hist['Open'].iloc[-1])
        else:
            open_p = last
    else:
        open_p = float(open_p)

    # Prix en devise NATURELLE du titre (affichage, comme les vrais
    # sites). "PrixCAD" sert aux calculs du panneau d'ordre : le compte
    # de l'élève est en dollars canadiens.
    change = last - open_p
    change_pct = (change / open_p) * 100 if open_p > 0 else 0.0
    fmt = ".4f" if last < 1 else ".2f"

    high_n = float(info.get('dayHigh') or last)
    low_n = float(info.get('dayLow') or last)
    y_high_n = float(info.get('yearHigh') or last)
    y_low_n = float(info.get('yearLow') or last)

    return {
        "Prix": last,
        "PrixCAD": convertir_vers_cad(last, devise),
        "Variation": change,
        "VariationPct": change_pct,
        "Ouverture": f"${open_p:{fmt}}",
        "Plus Haut": f"${high_n:{fmt}}",
        "Plus Bas": f"${low_n:{fmt}}",
        "52 sem. Haut": f"${y_high_n:{fmt}}",
        "52 sem. Bas": f"${y_low_n:{fmt}}",
        "Devise": devise
    }


def _details_voie_historique(t, ticker_symbol):
    """Voie de repli : métadonnées et historique Yahoo (l'API graphique,
    celle qui répond de façon fiable depuis les serveurs du site).
    Même validation stricte des bourses et des types d'instruments.
    Sans ce repli, un simple hoquet de Yahoo disait à l'élève que le
    titre n'existait pas et bloquait son achat (ex. SVRN, NASDAQ,
    21 oct. 2026). Retourne le dict, 'non_na' ou None comme la voie
    rapide."""
    md = t.history_metadata or {}
    exch = str(md.get('exchangeName') or '')
    qtype = str(md.get('instrumentType') or '')
    if not instrument_autorise(ticker_symbol, exch_code=exch, quote_type=qtype):
        return "non_na"

    hist = t.history(period="1y")
    if hist is None or hist.empty or 'Close' not in hist.columns:
        return None
    devise = str(md.get('currency') or '').upper() or devise_naturelle(ticker_symbol)
    last = float(hist['Close'].iloc[-1])
    if last <= 0:
        return None
    open_p = hist['Open'].iloc[-1]
    open_p = float(open_p) if open_p is not None and not pd.isna(open_p) and float(open_p) > 0 else (
        float(hist['Close'].iloc[-2]) if len(hist) >= 2 else last)
    change = last - open_p
    change_pct = (change / open_p) * 100 if open_p > 0 else 0.0
    fmt = ".4f" if last < 1 else ".2f"
    return {
        "Prix": last,
        "PrixCAD": convertir_vers_cad(last, devise),
        "Variation": change,
        "VariationPct": change_pct,
        "Ouverture": f"${open_p:{fmt}}",
        "Plus Haut": f"${float(hist['High'].iloc[-1]):{fmt}}",
        "Plus Bas": f"${float(hist['Low'].iloc[-1]):{fmt}}",
        "52 sem. Haut": f"${float(hist['High'].max()):{fmt}}",
        "52 sem. Bas": f"${float(hist['Low'].min()):{fmt}}",
        "Devise": devise
    }


def _details_depuis_relais(ticker_symbol):
    """Détails de repli depuis le relais : même format que la voie
    historique. Sans ce repli, un silence de Yahoo fermait toute la
    page du titre, graphique et achat compris (vu le 22 oct. 2026)."""
    lignes = _relais_lire_prix([ticker_symbol])
    ligne = lignes.get(str(ticker_symbol).strip().upper())
    if ligne is None:
        return None
    try:
        px = float(ligne['prix_natif'])
        if px <= 0:
            return None
    except Exception:
        return None
    devise = str(ligne['devise'] or '').upper() or devise_naturelle(ticker_symbol)

    def _val(col, repli):
        v = ligne[col]
        if v is None or pd.isna(v) or float(v) <= 0:
            return float(repli)
        return float(v)

    ouv = _val('ouverture', px)
    change = px - ouv
    change_pct = (change / ouv) * 100 if ouv > 0 else 0.0
    fmt = ".4f" if px < 1 else ".2f"
    return {
        "Prix": px,
        "PrixCAD": convertir_vers_cad(px, devise),
        "Variation": change,
        "VariationPct": change_pct,
        "Ouverture": f"${ouv:{fmt}}",
        "Plus Haut": f"${_val('haut', px):{fmt}}",
        "Plus Bas": f"${_val('bas', px):{fmt}}",
        "52 sem. Haut": f"${_val('haut52', px):{fmt}}",
        "52 sem. Bas": f"${_val('bas52', px):{fmt}}",
        "Devise": devise
    }


@st.cache_data(ttl=60, show_spinner=False)
def obtenir_details_financiers(ticker_symbol):
    if not _symbole_syntaxe_ok(ticker_symbol):
        return {"erreur": "non_na"}

    t = yf.Ticker(ticker_symbol)
    try:
        r = _details_voie_rapide(t, ticker_symbol)
    except Exception:
        r = None
    if r == "non_na":
        return {"erreur": "non_na"}
    if r is not None:
        return r
    try:
        r = _details_voie_historique(t, ticker_symbol)
    except Exception:
        r = None
    if r == "non_na":
        return {"erreur": "non_na"}
    if r is not None:
        return r
    try:
        return _details_depuis_relais(ticker_symbol)
    except Exception:
        return None


def _historique_depuis_relais(ticker_symbol, periode):
    """Graphique de repli : bougies QUOTIDIENNES stockées par la sonde
    dans historique_relais. Moins fin que l'intrajournalier Yahoo,
    mais le graphique (et l'achat, qui vit sur la même page) reste
    disponible quand Yahoo ne répond pas depuis le nuage."""
    try:
        df = conn.query(
            "SELECT jour, o, h, l, c, v FROM historique_relais "
            "WHERE ticker=:t ORDER BY jour",
            params={"t": str(ticker_symbol).strip().upper()}, ttl=0)
        if df is None or df.empty:
            return None
        fenetres = {"1d": 5, "5d": 5, "1mo": 22, "3mo": 66,
                    "6mo": 132, "1y": 252, "2y": 504, "5y": 1260}
        df = df.tail(fenetres.get(periode, 252))
        out = pd.DataFrame({
            "Open": df['o'].astype(float).values,
            "High": df['h'].astype(float).values,
            "Low": df['l'].astype(float).values,
            "Close": df['c'].astype(float).values,
            "Volume": df['v'].fillna(0).astype(float).values,
        }, index=pd.to_datetime(df['jour']))
        out.index.name = "Date"
        return out
    except Exception:
        return None


@st.cache_data(ttl=300, show_spinner=False)
def obtenir_historique(ticker_symbol, periode, devise="CAD"):
    """Historique en devise NATURELLE du titre (aucune conversion :
    le graphique montre les mêmes chiffres que les vrais sites).
    Repli : bougies quotidiennes du relais quand Yahoo ne répond pas,
    pour que le graphique (et l'achat, sur la même page) reste ouvert."""
    try:
        interval = "5m" if periode == "1d" else ("15m" if periode == "5d" else "1d")
        df = yf.Ticker(ticker_symbol).history(period=periode, interval=interval)
        if df is not None and not df.empty:
            return df
    except Exception:
        pass
    return _historique_depuis_relais(ticker_symbol, periode)

# --- PHOTOS DES MENEURS (déposées par le prof dans Supervision) ---
def traiter_photo(octets):
    """Recadre la photo au carré sur le visage, la réduit à 256 px
    et la compresse en JPEG (base64) pour la base de données."""
    import base64
    import io as _io
    from PIL import Image
    img = Image.open(_io.BytesIO(octets)).convert("RGB")
    cote = min(img.size)
    gauche = (img.width - cote) // 2
    haut = max(0, int((img.height - cote) * 0.18))
    img = img.crop((gauche, haut, gauche + cote, haut + cote)).resize((256, 256))
    tampon = _io.BytesIO()
    img.save(tampon, format="JPEG", quality=82)
    return base64.b64encode(tampon.getvalue()).decode()


@st.cache_data(ttl=60, show_spinner=False)
def obtenir_photo(username):
    try:
        df = conn.query("SELECT image FROM photos WHERE username=:u",
                        params={"u": username}, ttl=0)
        if not df.empty and df.iloc[0]['image']:
            return str(df.iloc[0]['image'])
    except Exception:
        pass
    return None


def initiales_de(nom):
    morceaux = [m for m in str(nom).replace("_", " ").replace(".", " ").split() if m]
    if len(morceaux) >= 2:
        return (morceaux[0][0] + morceaux[1][0]).upper()
    nom = str(nom)
    for c in nom[1:]:
        if c.isupper():
            return (nom[0] + c).upper()
    return nom[:2].upper()


# --- CACHE DES CALCULS DU CLASSEMENT (TTL = 30s) ---
@st.cache_data(ttl=120, show_spinner=False)
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
        u_gain_jour = 0.0
        u_base_jour = 0.0
        if not u_p.empty:
            for _, row in u_p.iterrows():
                tk_sym = str(row['ticker']).upper()
                _info_px = prix_dict.get(tk_sym)
                px = _info_px["cad"] if _info_px else None
                px_f = px if px is not None else float(row['avg_price'] or 0.0)
                u_val_act += px_f * row['shares']
                # Gain du jour : positions actuelles comparées à la clôture
                # de la veille (même appel de prix, aucun coût réseau ajouté).
                _prev = _info_px.get("prev_cad") if _info_px else None
                if _prev is not None and px is not None:
                    u_gain_jour += (px - _prev) * row['shares']
                    u_base_jour += _prev * row['shares']

        tot = u_cash + u_val_act
        perf = ((tot - 10000.00) / 10000.00) * 100
        gain_jour_pct = (u_gain_jour / u_base_jour * 100) if u_base_jour > 0 else 0.0
        lb.append({"Élève": u_name, "Groupe": u_grp, "Portefeuille": tot, "Performance": perf,
                   "GainJour": u_gain_jour, "GainJourPct": gain_jour_pct})

    if lb:
        df_lb = pd.DataFrame(lb).sort_values(by="Portefeuille", ascending=False).reset_index(drop=True)
        df_lb.index += 1
        df_lb['Rang'] = df_lb.index
        df_lb["Portefeuille"] = df_lb["Portefeuille"].map("${:,.2f}".format)
        df_lb["Performance"] = df_lb["Performance"].map("{:+.2f}%".format)
        return df_lb[['Rang', 'Élève', 'Groupe', 'Portefeuille', 'Performance', 'GainJour', 'GainJourPct']]
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
                u_login = st.text_input("Identifiant", key="login_user", autocomplete="off")
                p_login = st.text_input("Mot de passe", type="password", key="login_pass", autocomplete="off")
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
            try:
                _fermes_inscr = set(conn.query("SELECT groupe FROM groupes_fermes", ttl=0)['groupe'].tolist())
            except Exception:
                _fermes_inscr = set()
            _groupes_ouverts = [g for g in LISTE_GROUPES if g not in _fermes_inscr]
            with st.form("form_inscription"):
                u_new = st.text_input("Identifiant (ex: PrenomNom)", key="new_user", autocomplete="off")
                if _groupes_ouverts:
                    g_new = st.selectbox("Groupe", _groupes_ouverts, key="new_group")
                else:
                    st.warning("Les inscriptions sont fermées pour tous les groupes.")
                    g_new = None
                p_new = st.text_input("Mot de passe", type="password", key="new_pass", autocomplete="off")
                if st.form_submit_button("S'inscrire", use_container_width=True):
                    if u_new and p_new and g_new:
                        # Sécurité : revérifier que le groupe n'a pas été fermé entre-temps
                        _rev = conn.query("SELECT 1 FROM groupes_fermes WHERE groupe=:g", params={"g": g_new}, ttl=0)
                        if not _rev.empty:
                            st.error("Ce groupe vient d'être fermé. Choisissez un autre groupe.")
                        else:
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

    verifier_popup_regles(user)

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
        fragment_auto = st.fragment(run_every=60)
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
                _info_px = prix_dict.get(tk_sym)
                px_actuel = _info_px["cad"] if _info_px else None
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
                _info_tape = prix_dict.get(tk_tape)
                pm_tape = float(row['avg_price'] or 0.0)
                dv_tape = _info_tape["devise"] if _info_tape else devise_naturelle(tk_tape)
                px_cad_tape = _info_tape["cad"] if _info_tape else None
                px_natif_tape = _info_tape["natif"] if _info_tape else None
                # Flèche : comparaison en CAD (prix actuel CAD vs coût moyen CAD).
                base_cmp = px_cad_tape if px_cad_tape is not None else pm_tape
                # Prix affiché : devise naturelle du titre.
                px_aff = px_natif_tape if px_natif_tape is not None else vers_natif(pm_tape, dv_tape)
                fmt_tape = fmt_prix(px_aff, dv_tape)
                couleur_tape = "#34D399" if base_cmp >= pm_tape else "#F87171"
                fleche_tape = "▲" if base_cmp >= pm_tape else "▼"
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
                "Rechercher une action (TSX, NYSE, Nasdaq seulement)",
                value="",
                placeholder="Tapez le nom d'une entreprise ou un symbole (ex: Apple, SHOP.TO)...",
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
            st.error(f"**Instrument non autorisé :** Seules les actions et FNB cotés au TSX (Toronto), au NYSE ou au Nasdaq sont permis. Aucune crypto, devise, future ni indice.")
        elif details:
            prix, var, var_pct = details["Prix"], details["Variation"], details["VariationPct"]
            prix_cad = details.get("PrixCAD") or prix
            devise_titre = str(details.get("Devise") or "CAD").upper()
            chart_color = "#10B981" if var >= 0 else "#EF4444"
            fill_color = "rgba(16, 185, 129, 0.20)" if var >= 0 else "rgba(239, 68, 68, 0.20)"
            signe = "+" if var >= 0 else ""
            fmt_prix_carte = fmt_prix(prix, devise_titre)

            col_chart, col_order = st.columns([2.2, 1])

            with col_chart:
                st.markdown(f"<div class='quote-card {'up' if var >= 0 else 'down'}' data-tk='{selected_ticker}'><div class='quote-ticker'>{selected_ticker}</div><div class='quote-price'>{fmt_prix_carte}</div><div class='quote-var {'up' if var >= 0 else 'down'}'>{signe}{var_pct:.2f}% ({signe}{var:,.2f})</div></div>", unsafe_allow_html=True)
                if devise_titre == "USD":
                    st.caption("Prix en dollars américains (devise du titre), comme sur les vrais sites. Ton compte est en dollars canadiens : la conversion se fait à l'achat, au taux du jour.")
                else:
                    st.caption("Prix en dollars canadiens (devise du titre).")

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

                    df_hist = obtenir_historique(ticker, selected_period, details.get("Devise", "CAD"))
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
                    if devise_titre == "USD":
                        st.write(f"Total estimé : **{fmt_prix(prix*qty_achat, 'USD')}** (≈ **${prix_cad*qty_achat:,.2f} CAD** débités)")
                    else:
                        st.write(f"Total estimé : **${prix*qty_achat:,.2f}**")
                    qty_vente = qty_achat
                else:
                    montant = st.number_input("Montant à investir ($ CAD)", min_value=1.0, step=10.0, value=100.0, key=f"montant_{selected_ticker}")
                    qty_achat = int(montant // prix_cad) if prix_cad and prix_cad > 0 else 0
                    if qty_achat >= 1:
                        if devise_titre == "USD":
                            st.write(f"Vous pouvez acheter **{qty_achat}** actions à **{fmt_prix(prix, 'USD')}** pour **${qty_achat*prix_cad:,.2f} CAD**")
                        else:
                            st.write(f"Vous pouvez acheter **{qty_achat}** actions pour **${qty_achat*prix_cad:,.2f}**")
                    else:
                        st.warning("Ce montant ne permet pas d'acheter une seule action à ce prix.")
                    qty_vente = st.number_input("Quantité à vendre", min_value=1, step=1, value=1, key=f"qtyv_{selected_ticker}")

                if devise_titre == "USD":
                    _taux_jour = obtenir_taux_usdcad()
                    if _taux_jour:
                        st.caption(f"Ajustement de change : 1 $ US = {_taux_jour:.4f} $ CAD aujourd'hui. Le montant débité ou crédité est toujours en dollars canadiens.")

                st.caption("Règle : ta position sur un titre ne peut pas dépasser 5 % de son volume d'échange quotidien.")
                vol_jour_cap = obtenir_volume_quotidien_moyen(selected_ticker)
                if vol_jour_cap and LIMITE_VOLUME_PCT * vol_jour_cap < 1000000:
                    st.caption(f"Position maximale sur {selected_ticker.upper()} : {LIMITE_VOLUME_PCT * vol_jour_cap:,.0f} $")
                if est_etf(selected_ticker):
                    st.caption("Revente possible 24 h après l'achat (ETF).")
                else:
                    st.caption("Revente possible 1 h après l'achat.")

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
                        prix_instantane = obtenir_prix_actuel(selected_ticker) or prix_cad
                        cost_real = prix_instantane * qty_achat

                        c_res = conn.query("SELECT cash FROM users WHERE username=:u", params={"u": user}, ttl=0)
                        cash_actuel_db = float(c_res.iloc[0]['cash']) if not c_res.empty else 0.0

                        msg_limite = verifier_limite_volume(user, selected_ticker, prix_instantane, cost_real)
                        if msg_limite:
                            st.error(msg_limite)
                        elif cash_actuel_db >= cost_real:
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

                            if devise_titre == "USD":
                                _taux_fx = obtenir_taux_usdcad()
                                _msg_fx = f" (débité : ${cost_real:,.2f} CAD au taux {_taux_fx:.4f})" if _taux_fx else f" (débité : ${cost_real:,.2f} CAD)"
                                st.session_state['flash_msg'] = ("success", f"Achat de {qty_achat} {selected_ticker.upper()} à {fmt_prix(vers_natif(prix_instantane, 'USD'), 'USD')} effectué !{_msg_fx}")
                            else:
                                st.session_state['flash_msg'] = ("success", f"Achat de {qty_achat} {selected_ticker.upper()} à ${prix_instantane:,.2f} effectué !")
                            st.rerun()
                        else: st.error("Fonds insuffisants.")

                # VENTE
                if col_s.button("Vendre", use_container_width=True):
                    if vente_avant_delai_bloquee(user, selected_ticker):
                        st.warning(message_delai_detention(selected_ticker))
                    elif not verifier_cooldown(user, delai_secondes=3):
                        st.warning("Veuillez attendre 3 secondes entre chaque transaction.")
                    else:
                        prix_instantane = obtenir_prix_actuel(selected_ticker) or prix_cad
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

                            if devise_titre == "USD":
                                _taux_fx = obtenir_taux_usdcad()
                                _msg_fx = f" (crédité : ${cost_real:,.2f} CAD au taux {_taux_fx:.4f})" if _taux_fx else f" (crédité : ${cost_real:,.2f} CAD)"
                                st.session_state['flash_msg'] = ("success", f"Vente de {qty_vente} {selected_ticker.upper()} à {fmt_prix(vers_natif(prix_instantane, 'USD'), 'USD')} effectuée !{_msg_fx}")
                            else:
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
                    for i, tk in enumerate(fav_tickers):
                        px, vp, dv_fav = fav_data.get(tk.upper(), (None, None, devise_naturelle(tk)))
                        couleur_txt = "#10B981" if (vp or 0) >= 0 else "#EF4444"
                        cle = f"favchip_{i}"
                        chip_css += (
                            f'div[class~="st-key-{cle}"] button {{'
                            f'background: #161616 !important;'
                            f'border: 1px solid #FFD700 !important;'
                            f'padding: 5px 6px !important;'
                            f'animation: neonPulseJaune 2.4s ease-in-out infinite;'
                            f'}}'
                            f'div[class~="st-key-{cle}"] button p {{'
                            f'color: {couleur_txt} !important; font-weight: 700 !important; font-size: 13px !important;'
                            f'}}'
                        )
                    chip_css += "</style>"
                    st.markdown(chip_css, unsafe_allow_html=True)
                    fav_cols = st.columns(2)
                    for i, tk in enumerate(fav_tickers):
                        px, vp, dv_fav = fav_data.get(tk.upper(), (None, None, devise_naturelle(tk)))
                        if px is None:
                            chip_label = f"{tk}"
                        else:
                            fmt_px = fmt_prix(px, dv_fav)
                            signe = "+" if (vp or 0) >= 0 else ""
                            fleche = "▲" if (vp or 0) >= 0 else "▼"
                            chip_label = f"{tk} {fmt_px} {fleche} {signe}{vp:.2f}%"
                        with fav_cols[i % 2]:
                            st.button(chip_label, key=f"favchip_{i}", use_container_width=True, on_click=_choisir_favori, args=(tk,))
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
                    _info_px = prix_dict.get(tk_sym)
                    px_a = _info_px["cad"] if _info_px else None
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
                html_rows = ""

                tks_all = p_all['ticker'].unique().tolist()
                prix_dict_pos = obtenir_prix_groupes(tks_all)

                pie_labels, pie_vals = [], []

                for _, r in p_all.iterrows():
                    tk, sh, pm = str(r['ticker']), int(r['shares']), float(r['avg_price'] or 0.0)
                    _info_pos = prix_dict_pos.get(tk.upper())
                    pa_live = _info_pos["cad"] if _info_pos else None
                    pa = pa_live if pa_live is not None else pm
                    val = sh * pa
                    pnl = (pa - pm) * sh
                    pnl_pct = ((pa - pm) / pm * 100) if pm > 0 else 0
                    pie_labels.append(tk)
                    pie_vals.append(val)

                    # Affichage des prix unitaires en devise naturelle (le prix
                    # moyen CAD est converti au taux du jour, affichage seulement).
                    # Valeur, gain et rendement restent en CAD exacts.
                    dv_pos = _info_pos["devise"] if _info_pos else devise_naturelle(tk)
                    pa_aff = _info_pos["natif"] if (_info_pos and _info_pos["natif"] is not None) else vers_natif(pa, dv_pos)
                    pm_aff = vers_natif(pm, dv_pos)

                    pnl_color = "#10B981" if pnl >= 0 else "#EF4444"
                    fmt_pa = fmt_prix(pa_aff, dv_pos)
                    fmt_pm = fmt_prix(pm_aff, dv_pos)

                    html_rows += f"<tr><td><b>{tk}</b></td><td>{sh}</td><td>{fmt_pm}</td><td>{fmt_pa}</td><td>${val:,.2f}</td><td style='color:{pnl_color}; font-weight:700;'>${pnl:+,.2f}</td><td style='color:{pnl_color}; font-weight:700;'>{pnl_pct:+.2f}%</td></tr>"

                table_html = f"<table class='custom-table'><thead><tr><th>Action</th><th>Quantité</th><th>Prix Moyen</th><th>Prix Actuel</th><th>Valeur</th><th>Gain / Perte</th><th>Rendement</th></tr></thead><tbody>{html_rows}</tbody></table>"
                st.markdown(table_html, unsafe_allow_html=True)
                st.caption("Prix moyen et prix actuel : devise naturelle du titre (prix moyen converti au taux du jour). Valeur, gain/perte et rendement : dollars canadiens.")

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

                cartes_vente = []
                for _, r in p_all.iterrows():
                    tk2, sh2 = str(r['ticker']), int(r['shares'] or 0)
                    if sh2 <= 0:
                        continue  # ligne résiduelle sans action : rien à vendre, on l'ignore
                    pm2 = float(r['avg_price'] or 0.0)
                    _info_v = prix_dict_pos.get(tk2.upper())
                    pa2_live = _info_v["cad"] if _info_v else None
                    pa2 = pa2_live if pa2_live is not None else pm2
                    cartes_vente.append((tk2, sh2, pm2, pa2))

                grille_vente = st.columns(3)
                for i, (tk, sh, pm, pa) in enumerate(cartes_vente):
                    with grille_vente[i % 3]:
                        with st.container(border=True):
                            sh_s = max(int(sh), 1)
                            cle_slider = f"slqv_{tk}_{sh_s}"
                            qty_init = max(1, min(int(st.session_state.get(cle_slider, sh_s)), sh_s))
                            pnl_badge = (pa - pm) * qty_init
                            coul_b = "#10B981" if pnl_badge >= 0 else "#EF4444"
                            fond_b = "rgba(16,185,129,0.12)" if pnl_badge >= 0 else "rgba(239,68,68,0.12)"
                            st.markdown(
                                f"<div style='display:flex;justify-content:space-between;align-items:flex-start;gap:8px;'>"
                                f"<div><div style='font-family:\"Bebas Neue\",\"Work Sans\",sans-serif;font-size:24px;letter-spacing:0.04em;color:#FFFFFF;'>{tk}</div>"
                                f"<div style='color:#9CA3AF;font-size:13px;margin-bottom:8px;'>J'en possède : {sh}</div></div>"
                                f"<div style='background:{fond_b};border:1px solid {coul_b};border-radius:8px;padding:4px 10px;color:{coul_b};font-weight:800;font-size:14px;white-space:nowrap;'>${pnl_badge:+,.2f}</div>"
                                f"</div>",
                                unsafe_allow_html=True)
                            if sh_s <= 1:
                                # Streamlit refuse un curseur avec min == max : avec une seule action, pas de curseur
                                qty_c = 1
                                st.markdown("<div style='color:#9CA3AF;font-size:14px;margin:4px 0 8px 0;'>J'en vends : <b style='color:#FFFFFF;'>1</b></div>", unsafe_allow_html=True)
                            else:
                                qty_c = st.slider("J'en vends :", min_value=1, max_value=sh_s, value=qty_init, key=cle_slider)
                            tot_c = qty_c * pa
                            st.markdown(
                                f"<div style='color:#FFFFFF;font-size:15px;margin:4px 0 10px;'>Je reçois : <b>${tot_c:,.2f}</b></div>",
                                unsafe_allow_html=True)
                            if st.button(f"Vendre {qty_c} {tk}", use_container_width=True, key=f"vndcarte_{tk}"):
                                if vente_avant_delai_bloquee(user, tk):
                                    st.warning(message_delai_detention(tk))
                                elif not verifier_cooldown(user, delai_secondes=3):
                                    st.warning("Veuillez attendre 3 secondes entre chaque transaction.")
                                else:
                                    check_p = conn.query("SELECT shares FROM portfolio WHERE username=:u AND ticker=:t", params={"u": user, "t": tk}, ttl=0)
                                    sh_real = int(check_p.iloc[0]['shares']) if not check_p.empty else 0
                                    if sh_real >= qty_c:
                                        prix_v_instantane = obtenir_prix_actuel(tk) or pa
                                        total_v_instantane = qty_c * prix_v_instantane
                                        now_str = datetime.now(ZoneInfo("America/Toronto")).strftime("%Y-%m-%d %H:%M:%S")
                                        with conn.session as session:
                                            session.execute(text("UPDATE users SET cash = cash + :cost WHERE username = :u"), {"cost": total_v_instantane, "u": user})
                                            rem = sh_real - qty_c
                                            if rem > 0:
                                                session.execute(text("UPDATE portfolio SET shares=:s WHERE username=:u AND ticker=:t"), {"s": rem, "u": user, "t": tk})
                                            else:
                                                session.execute(text("DELETE FROM portfolio WHERE username=:u AND ticker=:t"), {"u": user, "t": tk})
                                            session.execute(text("INSERT INTO transactions (username, ticker, shares, price, total, timestamp) VALUES (:u, :t, :s, :p, :tot, :time)"),
                                                            {"u": user, "t": tk, "s": -qty_c, "p": prix_v_instantane, "tot": total_v_instantane, "time": now_str})
                                            session.commit()
                                        if devise_naturelle(tk) == "USD":
                                            st.session_state['flash_msg'] = ("success", f"Vente de {qty_c} {tk} à {fmt_prix(vers_natif(prix_v_instantane, 'USD'), 'USD')} effectuée ! (crédité : ${total_v_instantane:,.2f} CAD)")
                                        else:
                                            st.session_state['flash_msg'] = ("success", f"Vente de {qty_c} {tk} à ${prix_v_instantane:,.2f} effectuée !")
                                        st.rerun()
                                    else:
                                        st.error("Vous ne possédez plus ces actions.")
            else: st.info("Vous n'avez aucune position ouverte actuellement.")

        afficher_positions_live()

    # --- ONGLET 3 : HISTORIQUE ---
    elif tab_choisi == "Mon Historique":
        tx_all = conn.query("SELECT timestamp, CASE WHEN shares > 0 THEN 'ACHAT' ELSE 'VENTE' END as type, ticker, ABS(shares) as shares, price, total FROM transactions WHERE username=:u ORDER BY id DESC", params={"u": user}, ttl=0)
        if not tx_all.empty:
            tx_all.columns = ["Date & Heure", "Type", "Action", "Quantité", "Prix ($ CAD)", "Total ($ CAD)"]
            st.dataframe(tx_all, use_container_width=True, hide_index=True)
        else: st.info("Aucune transaction.")

    # --- ONGLET 4 : CLASSEMENT (AVEC RECHERCHE & SURGLIGNAGE JAUNE) ---
    elif tab_choisi == "Classement":
        col_r1, col_r2, col_r3 = st.columns([2, 2, 1])
        with col_r1:
            grp_filter = st.selectbox("Filtrer par groupe :", ["Tous les groupes"] + LISTE_GROUPES)
        with col_r2:
            search_user_rank = st.text_input("Rechercher un élève :", value="", placeholder="Tapez un nom d'élève...", autocomplete="off")
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
                _gj = float(r_pod['GainJour'])
                _gjp = float(r_pod['GainJourPct'])
                _classe_jour = 'hausse' if _gj >= 0 else 'baisse'
                _signe_jour = '+' if _gj >= 0 else '-'
                _jour_html = (f"<div class='podium-jour'>Aujourd'hui : "
                              f"<span class='{_classe_jour}'>{_signe_jour}${abs(_gj):,.2f} "
                              f"({_gjp:+.2f}%)</span></div>")
                _nom_pod = str(r_pod['Élève'])
                _photo_pod = obtenir_photo(_nom_pod)
                if _photo_pod:
                    _avatar = (f"<div class='podium-photo-wrap'>"
                               f"<img class='podium-photo' src='data:image/jpeg;base64,{_photo_pod}' alt=''>"
                               f"<span class='podium-badge'>{int(r_pod['Rang'])}</span></div>")
                else:
                    _avatar = (f"<div class='podium-photo-wrap'>"
                               f"<div class='podium-initiales'>{initiales_de(_nom_pod)}</div>"
                               f"<span class='podium-badge'>{int(r_pod['Rang'])}</span></div>")
                cols_podium[i].markdown(f"<div class='podium-card {classes_podium[i]} podium-{i + 1}'>{_avatar}<div class='podium-nom'>{r_pod['Élève']}</div><div class='podium-val'>{r_pod['Portefeuille']}</div><div class='podium-perf'>{r_pod['Performance']}</div>{_jour_html}</div>", unsafe_allow_html=True)

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

            styled_df = df_classement[['Rang', 'Élève', 'Groupe', 'Portefeuille', 'Performance']].style.apply(highlight_row, axis=1)
            st.dataframe(styled_df, use_container_width=True, hide_index=True)
        else:
            st.info("Aucun élève trouvé pour ce classement.")

    # --- ONGLET 5 : SUPERVISION PROFESSEUR ---
    elif tab_choisi == "Supervision Prof":
        pin = st.text_input("PIN Enseignant :", type="password", autocomplete="off") if user.lower() not in ['prof', 'admin'] else "1959"
        if pin == "1959":
            with st.expander("Gestion des mots de passe (Supabase)"):
                st.warning("Ce lien ouvre la console Supabase, où les mots de passe des élèves peuvent être modifiés directement. À utiliser avec prudence.")
                code_supabase = st.text_input("Code d'accès :", type="password", key="code_supabase", autocomplete="off")
                if code_supabase == "996633":
                    st.link_button("Ouvrir la console Supabase", "https://supabase.com/dashboard/project/pixbjedmpvvjqswltzkq/editor/17585?schema=public")
                elif code_supabase:
                    st.error("Code incorrect.")

            with st.expander("Photos des meneurs (podium du classement)"):
                st.info("Choisis un élève, dépose sa photo officielle : elle apparaîtra dans sa carte du podium s'il est dans les 3 premiers. Sans photo, la carte affiche ses initiales.")
                _df_users_ph = conn.query("SELECT username FROM users ORDER BY username", ttl=0)
                _liste_eleves_ph = _df_users_ph['username'].tolist() if not _df_users_ph.empty else []
                if _liste_eleves_ph:
                    eleve_photo = st.selectbox("Élève :", _liste_eleves_ph, key="eleve_photo_podium")
                    photo_existante = obtenir_photo(eleve_photo)
                    if photo_existante:
                        st.image(f"data:image/jpeg;base64,{photo_existante}", width=90)
                        st.caption("Photo actuelle de cet élève.")
                    fichier_meneur = st.file_uploader("Photo de l'élève (jpg ou png)", type=["jpg", "jpeg", "png"], key="uploader_photo_meneur")
                    col_ph1, col_ph2 = st.columns(2)
                    if fichier_meneur and col_ph1.button("Enregistrer la photo", use_container_width=True):
                        try:
                            b64_meneur = traiter_photo(fichier_meneur.getvalue())
                            with conn.session as session:
                                session.execute(text("INSERT INTO photos (username, image, maj) VALUES (:u, :i, :d) ON CONFLICT (username) DO UPDATE SET image=:i, maj=:d"),
                                                {"u": eleve_photo, "i": b64_meneur, "d": datetime.now(ZoneInfo("America/Toronto")).strftime("%Y-%m-%d %H:%M:%S")})
                                session.commit()
                            obtenir_photo.clear()
                            st.success(f"Photo enregistrée pour {eleve_photo}.")
                            st.rerun()
                        except Exception:
                            st.error("Cette image n'a pas pu être traitée. Essaie un autre fichier.")
                    if photo_existante and col_ph2.button("Retirer la photo", use_container_width=True):
                        with conn.session as session:
                            session.execute(text("DELETE FROM photos WHERE username=:u"), {"u": eleve_photo})
                            session.commit()
                        obtenir_photo.clear()
                        st.rerun()

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

            with st.expander("Groupes : inscriptions et changements de groupe"):
                st.info(
                    "Fermez un groupe quand tous ses élèves sont inscrits : plus personne "
                    "ne pourra s'y inscrire. Les élèves déjà inscrits ne sont pas affectés. "
                    "Rouvrir un groupe réactive les inscriptions."
                )
                try:
                    _fermes = set(conn.query("SELECT groupe FROM groupes_fermes", ttl=0)['groupe'].tolist())
                except Exception:
                    _fermes = set()
                _comptes = conn.query("SELECT groupe, COUNT(*) as n FROM users GROUP BY groupe", ttl=0)
                _nb_par_groupe = {str(r['groupe']): int(r['n']) for _, r in _comptes.iterrows()} if not _comptes.empty else {}
                for g in LISTE_GROUPES:
                    _nb = _nb_par_groupe.get(g, 0)
                    _est_ferme = g in _fermes
                    cg1, cg2, cg3 = st.columns([3, 2, 2])
                    cg1.markdown(f"**{g}** — {_nb} inscrit(s)")
                    cg2.markdown("Fermé" if _est_ferme else "Ouvert")
                    if _est_ferme:
                        if cg3.button("Rouvrir", key=f"rouvrir_{g}", use_container_width=True):
                            with conn.session as session:
                                session.execute(text("DELETE FROM groupes_fermes WHERE groupe = :g"), {"g": g})
                                session.commit()
                            st.rerun()
                    else:
                        if cg3.button("Fermer", key=f"fermer_{g}", use_container_width=True):
                            with conn.session as session:
                                session.execute(text("INSERT INTO groupes_fermes (groupe) VALUES (:g)"), {"g": g})
                                session.commit()
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
                            _info_prof = prix_dict_prof.get(tk.upper())
                            pa_live = _info_prof["cad"] if _info_prof else None
                            pa = pa_live if pa_live is not None else pm
                            val = sh * pa
                            pnl = (pa - pm) * sh
                            pnl_pct = ((pa - pm) / pm * 100) if pm > 0 else 0.0
                            e_val_act += val

                            dv_prof = _info_prof["devise"] if _info_prof else devise_naturelle(tk)
                            pa_aff_p = _info_prof["natif"] if (_info_prof and _info_prof["natif"] is not None) else vers_natif(pa, dv_prof)
                            fmt_pa = fmt_prix(pa_aff_p, dv_prof)
                            fmt_pm = fmt_prix(vers_natif(pm, dv_prof), dv_prof)

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

                    col_g1, col_g2 = st.columns([3, 1])
                    with col_g1:
                        _idx_grp = LISTE_GROUPES.index(e_grp) if e_grp in LISTE_GROUPES else 0
                        _nv_grp = st.selectbox("Changer le groupe de l'élève :", LISTE_GROUPES, index=_idx_grp, key=f"nvgrp_{e_sel}")
                    with col_g2:
                        st.markdown("<br>", unsafe_allow_html=True)
                        if st.button("Changer de groupe", use_container_width=True, key=f"btngrp_{e_sel}"):
                            if _nv_grp != e_grp:
                                with conn.session as session:
                                    session.execute(text("UPDATE users SET groupe = :g WHERE username = :u"), {"g": _nv_grp, "u": e_sel})
                                    session.commit()
                                st.session_state['flash_msg'] = ("success", f"{e_sel} est maintenant dans le groupe {_nv_grp}.")
                            else:
                                st.session_state['flash_msg'] = ("success", f"{e_sel} est déjà dans le groupe {_nv_grp}.")
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
                        tx_e.columns = ["Date & Heure", "Type", "Action", "Quantité", "Prix ($ CAD)", "Total ($ CAD)"]
                        st.dataframe(tx_e, use_container_width=True, hide_index=True)
                    else:
                        st.info("Aucune transaction enregistrée.")
            else:
                st.info("Aucun élève trouvé dans ce groupe.")
