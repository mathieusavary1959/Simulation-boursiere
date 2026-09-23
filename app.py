import streamlit as st
import yfinance as yf
import pandas as pd
import plotly.graph_objects as go
import requests
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
                    type TEXT,
                    shares INT,
                    price DOUBLE PRECISION,
                    total DOUBLE PRECISION,
                    timestamp TEXT
                );
            '''))
            session.commit()
        except Exception:
            session.rollback()

init_db()

# --- FILTRE DE VALIDATION DES BOURSES NORD-AMÉRICAINES ---
def est_marche_nord_americain(symbol, exch_code="", exch_disp=""):
    symbol_upper = symbol.upper().strip()
    
    # Suffixes boursiers internationaux à bloquer
    suffixes_interdits = (
        '.PA', '.T', '.L', '.DE', '.MI', '.SS', '.HK', '.AX', 
        '.BR', '.LS', '.MC', '.AS', '.SW', '.SA', '.MX', '.BE', '.F', '.VI'
    )
    if symbol_upper.endswith(suffixes_interdits):
        return False
        
    # Si le symbole contient un point (ex: TD.TO), valider que c'est un marché canadien
    if '.' in symbol_upper:
        suffix = symbol_upper.split('.')[-1]
        if suffix not in ['TO', 'V', 'CN', 'NE']:
            return False

    # Liste des bourses nord-américaines valides
    mots_cles_na = [
        'NYSE', 'NASDAQ', 'TSX', 'TORONTO', 'AMEX', 'OTC', 'NEO', 
        'VENTURE', 'CBOE', 'AMERICAN', 'PNK', 'NMS', 'NYQ', 'NGM', 'NCM', 'TOR', 'VAN'
    ]
    
    comb = f"{exch_code} {exch_disp}".upper()
    if comb.strip():
        return any(kw in comb for kw in mots_cles_na)
        
    return True

# --- FONCTION DE PROTECTION ANTI-SPAM (COOLDOWN) ---
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

# --- DESIGN HAUT CONTRASTE & ONGLET BLEU FONCÉ ARRONDIS ---
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

    /* --- NOUVEAU STYLE UNIFORME DES ONGLETS (BLEU FONCÉ ET ARRONDIS) --- */
    .stTabs [data-baseweb="tab-list"] {
        gap: 8px !important;
        background-color: #0F172A !important; /* Bleu foncé identique à la bannière */
        padding: 8px !important;
        border-radius: 20px !important; /* Arrondis prononcés */
        border: 1px solid #334155 !important;
        margin-bottom: 24px !important;
        box-shadow: 0 8px 20px rgba(15, 23, 42, 0.15) !important;
    }
    .stTabs [data-baseweb="tab"] {
        height: auto !important;
        background-color: transparent !important;
        border-radius: 14px !important;
        color: #94A3B8 !important; /* Texte gris/bleu très lisible */
        padding: 12px 24px !important;
        font-weight: 700 !important;
        font-size: 0.92rem !important;
        border: 1px solid transparent !important;
        transition: all 0.2s ease-in-out !important;
    }
    .stTabs [data-baseweb="tab"]:hover {
        color: #FFFFFF !important;
        background-color: #1E293B !important; /* Survol bleu nuit */
    }
    .stTabs [aria-selected="true"] {
        background: linear-gradient(135deg, #1E3A8A 0%, #2563EB 100%) !important; /* Dégradé bleu foncé / royal */
        color: #FFFFFF !important;
        box-shadow: 0 4px 14px rgba(37, 99, 235, 0.35) !important;
        border: 1px solid #3B82F6 !important;
    }
    .stTabs [data-baseweb="tab-border"], .stTabs [data-baseweb="tab-highlight"] {
        display: none !important;
    }

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

    div[data-testid="stRadio"] > label {
        font-weight: 800 !important;
        color: #334155 !important;
        font-size: 0.85rem !important;
        text-transform: uppercase;
        letter-spacing: 0.04em;
        margin-bottom: 6px;
    }
    div[data-testid="stRadio"] > div {
        flex-direction: row !important;
        gap: 8px !important;
        background-color: #FFFFFF;
        padding: 6px;
        border-radius: 14px;
        border: 1.5px solid #CBD5E1;
    }
    div[data-testid="stRadio"] [data-testid="stMarkdownContainer"] p {
        font-weight: 700 !important;
        font-size: 0.88rem !important;
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
    </style>
""", unsafe_allow_html=True)

# --- CACHE DES DONNÉES FINANCIÈRES PARTAGÉES ---
@st.cache_data(ttl=3600)
def rechercher_symbole_universel(query):
    if not query or len(query.strip()) < 1: return []
    url = f"https://query2.finance.yahoo.com/v1/finance/search?q={query}&quotesCount=12&newsCount=0"
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'}
    try:
        r = requests.get(url, headers=headers, timeout=4)
        data = r.json()
        results = []
        for quote in data.get('quotes', []):
            symbol = quote.get('symbol')
            shortname = quote.get('shortname') or quote.get('longname') or symbol
            exch = quote.get('exchDisp') or quote.get('exchange') or ''
            type_disp = quote.get('typeDisp') or ''
            
            # FILTRAGE : Uniquement actions/ETF nord-américains
            if symbol and (type_disp in ['Equity', 'ETF', 'Action', 'Stock'] or not type_disp):
                if est_marche_nord_americain(symbol, exch_code=quote.get('exchange', ''), exch_disp=exch):
                    results.append({'symbol': symbol, 'label': f"{shortname} ({symbol}) — {exch}"})
        return results
    except Exception:
        return []

@st.cache_data(ttl=30, show_spinner=False)
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

@st.cache_data(ttl=60, show_spinner=False)
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

@st.cache_data(ttl=30)
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

# --- GESTION DE SESSION AVEC PERSISTENCE EN URL ---
if 'user' not in st.session_state:
    st.session_state['user'] = st.query_params.get("user", None)

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
                        st.session_state['user'] = u_login.strip()
                        st.query_params["user"] = u_login.strip()
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
    
    # Sécurité si l'utilisateur en URL a été supprimé
    if res_u.empty:
        st.session_state['user'] = None
        st.query_params.clear()
        st.rerun()

    cash_actuel = float(res_u.iloc[0]['cash'])
    groupe_actuel = res_u.iloc[0]['groupe']

    col_h1, col_h2 = st.columns([4, 1])
    col_h1.markdown(f"<p style='color: #475569; font-size: 1rem; margin-top:5px;'>Investisseur : <b style='color: #0F172A;'>{user}</b> &nbsp;•&nbsp; <span style='background:#CBD5E1; color:#0F172A; padding:4px 14px; border-radius:12px; font-weight:700; font-size:0.85rem;'>{groupe_actuel}</span></p>", unsafe_allow_html=True)
    if col_h2.button("Déconnexion", use_container_width=True):
        st.session_state['user'] = None
        st.query_params.clear()
        st.rerun()

    # --- METRIQUES LIVE ---
    @st.fragment(run_every="30s")
    def afficher_metrics_live():
        pos_df = conn.query("SELECT ticker, shares, avg_price FROM portfolio WHERE username=:u", params={"u": user}, ttl=0)
        valeur_actions = 0.0
        for _, row in pos_df.iterrows():
            px_actuel = obtenir_prix_actuel(row['ticker'])
            px_final = px_actuel if px_actuel is not None else float(row['avg_price'] or 0.0)
            valeur_actions += px_final * row['shares']

        valeur_totale = cash_actuel + valeur_actions
        profit_total = valeur_totale - 10000.00
        rendement_pct = (profit_total / 10000.00) * 100

        col_m1, col_m2, col_m3, col_m4 = st.columns(4)
        col_m1.metric("Disponible", f"${cash_actuel:,.2f}")
        col_m2.metric("Actions", f"${valeur_actions:,.2f}")
        col_m3.metric("Valeur Totale", f"${valeur_totale:,.2f}")
        col_m4.metric("Gains / Pertes", f"${profit_total:,.2f}", f"{rendement_pct:+.2f}%")

    afficher_metrics_live()

    st.markdown("<hr>", unsafe_allow_html=True)

    tab_trade, tab_port, tab_hist, tab_rank, tab_teacher = st.tabs(["Marché & Analyse", "Mes Positions", "Mon Historique", "Classement", "Supervision Prof"])

    # --- ONGLET 1 : MARCHE & ACHAT/VENTE ---
    with tab_trade:
        search_query = st.text_input(
            "🔎 Rechercher une action nord-américaine (ex: Apple, Tesla, Royal Bank, NVDA, SHOP.TO...)",
            value="",
            placeholder="Tapez le nom d'une entreprise ou un symbole (NYSE, NASDAQ, TSX)..."
        )
        
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
            st.error(f"⚠️ **Marché non autorisé :** L'action `{selected_ticker}` est cotée hors de l'Amérique du Nord (ex: Paris, Tokyo, Londres). Seules les bourses nord-américaines (NYSE, NASDAQ, TSX, TSX-V, OTC) sont permises.")
        elif details:
            prix, var, var_pct = details["Prix"], details["Variation"], details["VariationPct"]
            chart_color = "#10B981" if var >= 0 else "#EF4444"
            fill_color = "rgba(16, 185, 129, 0.12)" if var >= 0 else "rgba(239, 68, 68, 0.12)"
            signe = "+" if var >= 0 else ""
            fmt_prix = f"${prix:,.4f}" if prix < 1 else f"${prix:,.2f}"

            col_chart, col_order = st.columns([2.2, 1])
            
            with col_chart:
                st.markdown(f"### {selected_ticker} — {fmt_prix} ({signe}{var_pct:.2f}%)")

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

                    df_hist = obtenir_historique(ticker, selected_period)
                    if df_hist is not None and not df_hist.empty:
                        min_p = float(df_hist['Close'].min())
                        max_p = float(df_hist['Close'].max())
                        delta = max_p - min_p
                        
                        padding = delta * 0.08 if delta > 0 else min_p * 0.02
                        y_min = max(0, min_p - padding) if min_p > 0 else min_p - padding
                        y_max = max_p + padding

                        tick_fmt = "$.4f" if max_p < 1 else "$.2f"

                        fig = go.Figure()
                        
                        fig.add_trace(go.Scatter(
                            x=df_hist.index,
                            y=df_hist['Close'],
                            mode='lines',
                            line=dict(color=chart_color, width=2.5),
                            fill='tozeroy',
                            fillcolor=fill_color,
                            hovertemplate='%{x|%d %b %H:%M}<br><b>%{y:' + tick_fmt + '}</b><extra></extra>'
                        ))
                        
                        fig.update_layout(
                            paper_bgcolor='rgba(0,0,0,0)',
                            plot_bgcolor='rgba(0,0,0,0)',
                            height=340,
                            margin=dict(l=10, r=10, t=10, b=10),
                            xaxis=dict(showgrid=True, gridcolor='#CBD5E1', gridwidth=0.8, zeroline=False),
                            yaxis=dict(
                                range=[y_min, y_max],
                                showgrid=True, 
                                gridcolor='#CBD5E1', 
                                gridwidth=0.8, 
                                zeroline=False, 
                                side="right",
                                tickformat=tick_fmt
                            ),
                            font=dict(color="#334155", family="Plus Jakarta Sans")
                        )
                        st.plotly_chart(fig, use_container_width=True)

                afficher_graphique_interactif(selected_ticker)

            with col_order:
                st.markdown("### Passer un ordre")
                qty = st.number_input("Quantité", min_value=1, step=1, value=1)
                cost_total = prix * qty
                st.write(f"Total estimé : **${cost_total:,.2f}**")

                col_b, col_s = st.columns(2)
                
                if col_b.button("Acheter", use_container_width=True):
                    if not verifier_cooldown(user, delai_secondes=3):
                        st.warning("⏳ Veuillez attendre 3 secondes entre chaque transaction.")
                    else:
                        c_res = conn.query("SELECT cash FROM users WHERE username=:u", params={"u": user}, ttl=0)
                        cash_actuel_db = float(c_res.iloc[0]['cash']) if not c_res.empty else 0.0
                        
                        if cash_actuel_db >= cost_total:
                            now_str = datetime.now(ZoneInfo("America/Toronto")).strftime("%Y-%m-%d %H:%M:%S")
                            with conn.session as session:
                                session.execute(text("UPDATE users SET cash = cash - :cost WHERE username = :u"), {"cost": cost_total, "u": user})
                                p_res = conn.query("SELECT shares, avg_price FROM portfolio WHERE username=:u AND LOWER(ticker)=LOWER(:t)", params={"u": user, "t": selected_ticker}, ttl=0)
                                if not p_res.empty:
                                    anc_s, anc_p = int(p_res.iloc[0]['shares']), float(p_res.iloc[0]['avg_price'] or prix)
                                    n_s = anc_s + qty
                                    n_p = ((anc_s * anc_p) + (qty * prix)) / n_s
                                    session.execute(text("UPDATE portfolio SET shares=:s, avg_price=:p WHERE username=:u AND LOWER(ticker)=LOWER(:t)"), {"s": n_s, "p": n_p, "u": user, "t": selected_ticker})
                                else:
                                    session.execute(text("INSERT INTO portfolio VALUES (:u, :t, :s, :p)"), {"u": user, "t": selected_ticker.upper(), "s": qty, "p": prix})
                                session.execute(text("INSERT INTO transactions (username, ticker, type, shares, price, total, timestamp) VALUES (:u, :t, 'ACHAT', :s, :p, :tot, :time)"),
                                                {"u": user, "t": selected_ticker.upper(), "s": qty, "p": prix, "tot": cost_total, "time": now_str})
                                session.commit()
                            
                            st.session_state['flash_msg'] = ("success", f"Achat de {qty} {selected_ticker.upper()} effectué !")
                            st.rerun()
                        else: st.error("Fonds insuffisants.")

                if col_s.button("Vendre", use_container_width=True):
                    if not verifier_cooldown(user, delai_secondes=3):
                        st.warning("⏳ Veuillez attendre 3 secondes entre chaque transaction.")
                    else:
                        p_res = conn.query("SELECT shares FROM portfolio WHERE username=:u AND LOWER(ticker)=LOWER(:t)", params={"u": user, "t": selected_ticker}, ttl=0)
                        shares_dispo = int(p_res.iloc[0]['shares']) if not p_res.empty else 0

                        if shares_dispo >= qty:
                            now_str = datetime.now(ZoneInfo("America/Toronto")).strftime("%Y-%m-%d %H:%M:%S")
                            with conn.session as session:
                                session.execute(text("UPDATE users SET cash = cash + :cost WHERE username = :u"), {"cost": cost_total, "u": user})
                                rem = shares_dispo - qty
                                if rem > 0:
                                    session.execute(text("UPDATE portfolio SET shares=:s WHERE username=:u AND LOWER(ticker)=LOWER(:t)"), {"s": rem, "u": user, "t": selected_ticker})
                                else:
                                    session.execute(text("DELETE FROM portfolio WHERE username=:u AND LOWER(ticker)=LOWER(:t)"), {"u": user, "t": selected_ticker})
                                session.execute(text("INSERT INTO transactions (username, ticker, type, shares, price, total, timestamp) VALUES (:u, :t, 'VENTE', :s, :p, :tot, :time)"),
                                                {"u": user, "t": selected_ticker.upper(), "s": qty, "p": prix, "tot": cost_total, "time": now_str})
                                session.commit()
                            
                            st.session_state['flash_msg'] = ("success", f"Vente de {qty} {selected_ticker.upper()} effectuée !")
                            st.rerun()
                        else: st.error("Vous ne possédez pas cette quantité d'actions.")
        else:
            st.error(f"⚠️ Impossible de trouver des données financières pour '{selected_ticker}'. Vérifiez le nom ou le symbole boursier.")

    # --- ONGLET 2 : POSITIONS ET IMPRESSION PRO ---
    with tab_port:
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
                .stTabs [data-baseweb="tab-list"], .stButton, button, 
                iframe, hr, .stSelectbox, .stNumberInput, .brand-banner,
                div[data-testid="stMetric"] {
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

        @st.fragment(run_every="30s")
        def afficher_positions_live():
            pos_df_live = conn.query("SELECT ticker, shares, avg_price FROM portfolio WHERE username=:u", params={"u": user}, ttl=0)
            val_actions_live = 0.0
            for _, r in pos_df_live.iterrows():
                px_a = obtenir_prix_actuel(r['ticker'])
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
                        background: linear-gradient(180deg, #1E293B 0%, #0F172A 100%);
                        color: #FFFFFF;
                        border: none;
                        padding: 10px 18px;
                        border-radius: 12px;
                        font-weight: 700;
                        cursor: pointer;
                        width: 100%;
                        font-family: 'Plus Jakarta Sans', sans-serif;
                        box-shadow: 0 4px 0 #020617, 0 6px 12px rgba(15, 23, 42, 0.2);
                        transition: all 0.12s ease;
                    " onmousedown="this.style.transform='translateY(3px)'; this.style.boxShadow='0 1px 0 #020617'" onmouseup="this.style.transform='translateY(0px)'; this.style.boxShadow='0 4px 0 #020617, 0 6px 12px rgba(15, 23, 42, 0.2)'">
                        🖨️ Imprimer / PDF
                    </button>
                """, height=45)

            p_all = conn.query("SELECT ticker, shares, avg_price FROM portfolio WHERE username=:u", params={"u": user}, ttl=0)
            if not p_all.empty:
                options_vente = {}
                html_rows = ""

                for _, r in p_all.iterrows():
                    tk, sh, pm = str(r['ticker']), int(r['shares']), float(r['avg_price'] or 0.0)
                    pa_live = obtenir_prix_actuel(tk)
                    pa = pa_live if pa_live is not None else pm
                    val = sh * pa
                    pnl = (pa - pm) * sh
                    pnl_pct = ((pa - pm) / pm * 100) if pm > 0 else 0

                    pnl_color = "#10B981" if pnl >= 0 else "#EF4444"
                    fmt_pa = f"${pa:,.4f}" if pa < 1 else f"${pa:,.2f}"
                    fmt_pm = f"${pm:,.4f}" if pm < 1 else f"${pm:,.2f}"
                    
                    options_vente[f"{tk} ({sh} action(s) disponible(s))"] = (tk, sh, pa)

                    html_rows += f"<tr><td><b>{tk}</b></td><td>{sh}</td><td>{fmt_pm}</td><td>{fmt_pa}</td><td>${val:,.2f}</td><td style='color:{pnl_color}; font-weight:700;'>${pnl:+,.2f}</td><td style='color:{pnl_color}; font-weight:700;'>{pnl_pct:+.2f}%</td></tr>"

                table_html = f"<table class='custom-table'><thead><tr><th>Action</th><th>Quantité</th><th>Prix Moyen</th><th>Prix Actuel</th><th>Valeur</th><th>Gain / Perte</th><th>Rendement</th></tr></thead><tbody>{html_rows}</tbody></table>"
                st.markdown(table_html, unsafe_allow_html=True)

                st.markdown("<hr>", unsafe_allow_html=True)
                st.markdown("### 💸 Vendre rapidement mes positions")

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
                            st.warning("⏳ Veuillez attendre 3 secondes entre chaque transaction.")
                        else:
                            check_p = conn.query("SELECT shares FROM portfolio WHERE username=:u AND ticker=:t", params={"u": user, "t": tk_v}, ttl=0)
                            sh_real = int(check_p.iloc[0]['shares']) if not check_p.empty else 0

                            if sh_real >= qty_v:
                                now_str = datetime.now(ZoneInfo("America/Toronto")).strftime("%Y-%m-%d %H:%M:%S")
                                with conn.session as session:
                                    session.execute(text("UPDATE users SET cash = cash + :cost WHERE username = :u"), {"cost": total_vente, "u": user})
                                    rem = sh_real - qty_v
                                    if rem > 0:
                                        session.execute(text("UPDATE portfolio SET shares=:s WHERE username=:u AND ticker=:t"), {"s": rem, "u": tk_v})
                                    else:
                                        session.execute(text("DELETE FROM portfolio WHERE username=:u AND ticker=:t"), {"u": user, "t": tk_v})
                                    session.execute(text("INSERT INTO transactions (username, ticker, type, shares, price, total, timestamp) VALUES (:u, :t, 'VENTE', :s, :p, :tot, :time)"),
                                                    {"u": user, "t": tk_v, "s": qty_v, "p": pa_v, "tot": total_vente, "time": now_str})
                                    session.commit()
                                
                                st.session_state['flash_msg'] = ("success", f"Vente de {qty_v} {tk_v} effectuée !")
                                st.rerun()
                            else: st.error("Vous ne possédez plus ces actions.")
            else: st.info("Vous n'avez aucune position ouverte actuellement.")

        afficher_positions_live()

    # --- ONGLET 3 : HISTORIQUE ---
    with tab_hist:
        tx_all = conn.query("SELECT timestamp, type, ticker, shares, price, total FROM transactions WHERE username=:u ORDER BY id DESC", params={"u": user}, ttl=0)
        if not tx_all.empty:
            tx_all.columns = ["Date & Heure", "Type", "Action", "Quantité", "Prix ($)", "Total ($)"]
            st.dataframe(tx_all, use_container_width=True, hide_index=True)
        else: st.info("Aucune transaction.")

    # --- ONGLET 4 : CLASSEMENT OPTIMISÉ ---
    with tab_rank:
        grp_filter = st.selectbox("Filtrer par groupe :", ["Tous les groupes"] + LISTE_GROUPES)
        
        if grp_filter == "Tous les groupes":
            users_df = conn.query("SELECT username, cash, groupe FROM users", ttl=10)
        else:
            users_df = conn.query("SELECT username, cash, groupe FROM users WHERE groupe=:g", params={"g": grp_filter}, ttl=10)
        
        all_positions_df = conn.query("SELECT username, ticker, shares, avg_price FROM portfolio", ttl=10)
        
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
            st.dataframe(df_lb[['Rang', 'Élève', 'Groupe', 'Portefeuille', 'Performance']], use_container_width=True, hide_index=True)

    # --- ONGLET 5 : SUPERVISION PROFESSEUR ---
    with tab_teacher:
        pin = st.text_input("PIN Enseignant :", type="password") if user.lower() not in ['prof', 'admin'] else "1959"
        if pin == "1959":
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
                        for _, row in e_pos.iterrows():
                            tk = str(row['ticker'])
                            sh = int(row['shares'])
                            pm = float(row['avg_price'] or 0.0)
                            pa_live = obtenir_prix_actuel(tk)
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
                        if st.button(f"⚠️ Réinitialiser {e_sel}", use_container_width=True):
                            with conn.session as session:
                                session.execute(text("UPDATE users SET cash = 10000.00 WHERE username = :u"), {"u": e_sel})
                                session.execute(text("DELETE FROM portfolio WHERE username = :u"), {"u": e_sel})
                                session.execute(text("DELETE FROM transactions WHERE username = :u"), {"u": e_sel})
                                session.commit()
                            st.session_state['flash_msg'] = ("success", f"Le compte de {e_sel} a été réinitialisé à 10 000 $ !")
                            st.rerun()

                    with col_top_prof3:
                        if st.button(f"❌ Supprimer le compte", use_container_width=True):
                            with conn.session as session:
                                session.execute(text("DELETE FROM portfolio WHERE username = :u"), {"u": e_sel})
                                session.execute(text("DELETE FROM transactions WHERE username = :u"), {"u": e_sel})
                                session.execute(text("DELETE FROM users WHERE username = :u"), {"u": e_sel})
                                session.commit()
                            st.session_state['flash_msg'] = ("success", f"Le profil de {e_sel} a été définitivement supprimé !")
                            st.rerun()

                    col_t1, col_t2, col_t3, col_t4 = st.columns(4)
                    col_t1.metric("Disponible (Cash)", f"${e_cash:,.2f}")
                    col_t2.metric("Actions Possédées", f"${e_val_act:,.2f}")
                    col_t3.metric("Valeur Totale", f"${e_tot:,.2f}")
                    col_t4.metric("Gains / Pertes", f"${e_pnl:+,.2f}", f"{e_perf:+.2f}%")

                    st.markdown("##### Portefeuille Détaillé")
                    if pos_rows:
                        st.dataframe(pd.DataFrame(pos_rows), use_container_width=True, hide_index=True)
                    else:
                        st.info("Cet élève n'a aucune position ouverte actuellement.")

                    st.markdown("##### Historique des Transactions")
                    tx_e = conn.query("SELECT timestamp, type, ticker, shares, price, total FROM transactions WHERE username=:u ORDER BY id DESC", params={"u": e_sel}, ttl=0)
                    if not tx_e.empty:
                        tx_e.columns = ["Date & Heure", "Type", "Action", "Quantité", "Prix ($)", "Total ($)"]
                        st.dataframe(tx_e, use_container_width=True, hide_index=True)
                    else:
                        st.info("Aucune transaction enregistrée.")
            else:
                st.info("Aucun élève trouvé dans ce groupe.")
