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
            session.execute(text("""
                CREATE TABLE IF NOT EXISTS users (
                    username TEXT PRIMARY KEY,
                    password TEXT,
                    cash DOUBLE PRECISION,
                    groupe TEXT
                );
            """))
            session.execute(text("""
                CREATE TABLE IF NOT EXISTS portfolio (
                    username TEXT,
                    ticker TEXT,
                    shares INT,
                    avg_price DOUBLE PRECISION,
                    PRIMARY KEY(username, ticker)
                );
            """))
            session.execute(text("""
                CREATE TABLE IF NOT EXISTS transactions (
                    id SERIAL PRIMARY KEY,
                    username TEXT,
                    ticker TEXT,
                    shares INT,
                    price DOUBLE PRECISION,
                    total DOUBLE PRECISION,
                    timestamp TEXT
                );
            """))
            session.execute(text("""
                CREATE TABLE IF NOT EXISTS sessions (
                    token TEXT PRIMARY KEY,
                    username TEXT,
                    created_at TEXT
                );
            """))
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
        'VENTURE', 'CBOE', 'AMERICAN', 'PNK', 'NMS', 'NGM', 'NCM', 'TOR', 'VAN'
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
st.markdown(r"""
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

        high_p = float(info.get('dayHigh', last) or last)
        low_p = float(info.get('dayLow', last) or last)
        y_high = float(info.get('yearHigh', last) or last)
        y_low = float(info.get('yearLow', last) or last)

        def fmt_val(v):
            return f"${v:,.4f}" if last < 1 else f"${v:,.2f}"

        return {
            "Prix": last, 
            "Variation": change, 
            "VariationPct": change_pct,
            "Ouverture": fmt_val(open_p),
            "Plus Haut": fmt_val(high_p),
            "Plus Bas": fmt_val(low_p),
            "52 sem. Haut": fmt_val(y_high),
            "52 sem. Bas": fmt_val(y_low)
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
        st.toast(txt, icon="✅")
    elif type_msg == "error":
        st.toast(txt, icon="⚠️")

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
    col_h1.markdown(f"<p style='color: #475569; font-size: 1rem; margin-top:5px;'>Investisseur : <b style='color: #0F172A;'>{user}</b> &nbsp;•&nbsp; <span style='background:#CBD5E1; color:#0F172A; padding:4px 14px; border-radius:12px; font-weight:700; font-size:0.85rem;'>{groupe_actuel}</span></p>", unsafe_allow_html=True)
    
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
    @st.fragment
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
        rendement_pct = (profit_total /
