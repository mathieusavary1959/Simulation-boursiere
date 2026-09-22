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

# --- DESIGN MODERNE EN FOND CLAIR AVEC EFFET 3D ---
st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700;800&display=swap');

    html, body, [class*="css"] {
        font-family: 'Plus Jakarta Sans', -apple-system, BlinkMacSystemFont, sans-serif;
    }

    /* Fond Clair & Épuré */
    .stApp {
        background-color: #F8FAFC !important;
        color: #0F172A !important;
    }

    #MainMenu, footer, header { visibility: hidden; }

    /* Bannière d'en-tête Institutionnelle & Moderne */
    .brand-banner {
        background: linear-gradient(135deg, #0F172A 0%, #1E293B 100%);
        border-radius: 20px;
        padding: 24px 32px;
        color: #FFFFFF;
        margin-bottom: 28px;
        box-shadow: 0 10px 25px -5px rgba(15, 23, 42, 0.12), 0 8px 10px -6px rgba(15, 23, 42, 0.08);
        display: flex;
        justify-content: space-between;
        align-items: center;
        border: 1px solid rgba(255, 255, 255, 0.1);
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

    /* Cartes Métriques Blanches à Relief */
    div[data-testid="stMetric"] {
        background-color: #FFFFFF !important;
        border: 1px solid #E2E8F0 !important;
        border-radius: 18px !important;
        padding: 18px 20px !important;
        box-shadow: 0 4px 12px -2px rgba(15, 23, 42, 0.04) !important;
        transition: all 0.25s ease !important;
    }
    div[data-testid="stMetric"]:hover {
        transform: translateY(-2px);
        box-shadow: 0 10px 20px -4px rgba(15, 23, 42, 0.08) !important;
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
        color: #64748B !important;
        font-size: 0.75rem;
        text-transform: uppercase;
        font-weight: 700;
        letter-spacing: 0.06em;
    }

    /* --- STYLE MODERNE DES ONGLETS --- */
    .stTabs [data-baseweb="tab-list"] {
        gap: 8px !important;
        background-color: #F1F5F9 !important;
        padding: 6px !important;
        border-radius: 16px !important;
        border: 1px solid #E2E8F0 !important;
        margin-bottom: 28px !important;
    }
    .stTabs [data-baseweb="tab"] {
        height: auto !important;
        background-color: transparent !important;
        border-radius: 12px !important;
        color: #64748B !important;
        padding: 10px 22px !important;
        font-weight: 700 !important;
        font-size: 0.9rem !important;
        border: none !important;
        transition: all 0.2s ease-in-out !important;
    }
    .stTabs [data-baseweb="tab"]:hover {
        color: #0F172A !important;
        background-color: rgba(255, 255, 255, 0.6) !important;
    }
    .stTabs [aria-selected="true"] {
        background-color: #FFFFFF !important;
        color: #2563EB !important;
        box-shadow: 0 4px 12px -2px rgba(37, 99, 235, 0.15) !important;
    }
    .stTabs [data-baseweb="tab-border"], .stTabs [data-baseweb="tab-highlight"] {
        display: none !important;
    }

    /* Boutons avec Effet 3D */
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
    .stButton>button:active, div[data-testid="stFormSubmitButton"]>button:active {
        transform: translateY(3px) !important;
        box-shadow: 0 1px 0 #1E40AF, 0 3px 6px rgba(37, 99, 235, 0.2) !important;
    }

    /* Champs de Saisie */
    .stTextInput>div>div>input, .stNumberInput>div>div>input, .stSelectbox>div>div {
        background-color: #FFFFFF !important;
        color: #0F172A !important;
        border-radius: 12px !important;
        border: 1px solid #CBD5E1 !important;
        padding: 11px 16px !important;
        font-weight: 500 !important;
    }

    /* Tableau Personnalisé */
    .custom-table {
        width: 100%;
        border-collapse: collapse;
        background-color: #FFFFFF;
        border-radius: 14px;
        overflow: hidden;
        border: 1px solid #E2E8F0;
        margin-bottom: 24px;
        box-shadow: 0 4px 12px rgba(0,0,0,0.03);
    }
    .custom-table th {
        background-color: #F1F5F9;
        color: #475569;
        font-weight: 700;
        padding: 14px 18px;
        text-align: left;
        border-bottom: 1px solid #E2E8F0;
        text-transform: uppercase;
        font-size: 0.75rem;
        letter-spacing: 0.05em;
    }
    .custom-table td {
        padding: 14px 18px;
        border-bottom: 1px solid #F1F5F9;
        color: #0F172A;
        font-weight: 500;
        font-size: 0.92rem;
    }

    hr { border-color: #E2E8F0 !important; margin: 30px 0 !important; }
    </style>
""", unsafe_allow_html=True)

# --- RECHERCHE UNIVERSELLE & DONNÉES FINANCIÈRES (TTL RÉDUIT À 5 SECONDES) ---
@st.cache_data(ttl=3600)
def rechercher_symbole_universel(query):
    if not query or len(query.strip()) < 1: return []
    url = f"https://query2.finance.yahoo.com/v1/finance/search?q={query}&quotesCount=8&newsCount=0"
    headers = {'User-Agent': 'Mozilla/5.0'}
    try:
        r = requests.get(url, headers=headers, timeout=3)
        data = r.json()
        results = []
        for quote in data.get('quotes', []):
            symbol = quote.get('symbol')
            shortname = quote.get('shortname') or quote.get('longname') or symbol
            exch = quote.get('exchDisp') or quote.get('exchange') or ''
            type_disp = quote.get('typeDisp') or ''
            if symbol and type_disp in ['Equity', 'ETF', 'Action']:
                results.append({'symbol': symbol, 'label': f"{shortname} ({symbol}) — {exch}"})
        return results
    except Exception:
        return []

@st.cache_data(ttl=5)  # Mis à jour à 5 secondes pour rafraîchissement temps réel
def obtenir_prix_actuel(ticker_symbol):
    try: return round(float(yf.Ticker(ticker_symbol).fast_info['lastPrice']), 2)
    except Exception: return None

@st.cache_data(ttl=5)  # Mis à jour à 5 secondes
def obtenir_details_financiers(ticker_symbol):
    try:
        info = yf.Ticker(ticker_symbol).fast_info
        last = info['lastPrice']
        open_price = info.get('open', last)
        change = last - open_price
        change_pct = (change / open_price) * 100 if open_price else 0
        return {
            "Prix": last, "Variation": change, "VariationPct": change_pct,
            "Ouverture": f"${info['open']:.2f}" if info.get('open') else "N/A",
            "Plus Haut": f"${info['dayHigh']:.2f}" if info.get('dayHigh') else "N/A",
            "Plus Bas": f"${info['dayLow']:.2f}" if info.get('dayLow') else "N/A",
            "52 sem. Haut": f"${info['yearHigh']:.2f}" if info.get('yearHigh') else "N/A",
            "52 sem. Bas": f"${info['yearLow']:.2f}" if info.get('yearLow') else "N/A",
        }
    except Exception: return None

@st.cache_data(ttl=180)
def obtenir_historique(ticker_symbol, periode):
    try: return yf.Ticker(ticker_symbol).history(period=periode)
    except Exception: return None

# --- GESTION DE SESSION AVEC PERSISTENCE PAR URL (CONSERVE LA CONNEXION APRÈS F5) ---
if 'user' not in st.session_state or st.session_state['user'] is None:
    if "user" in st.query_params:
        st.session_state['user'] = st.query_params["user"]
    else:
        st.session_state['user'] = None

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
                        st.query_params["user"] = u_login.strip()  # Enregistre dans l'URL pour garder la session
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
    cash_actuel = float(res_u.iloc[0]['cash']) if not res_u.empty else 10000.00
    groupe_actuel = res_u.iloc[0]['groupe'] if not res_u.empty else "Non assigné"

    col_h1, col_h2 = st.columns([4, 1])
    col_h1.markdown(f"<p style='color: #64748B; font-size: 1rem; margin-top:5px;'>Investisseur : <b style='color: #0F172A;'>{user}</b> &nbsp;•&nbsp; <span style='background:#E2E8F0; color:#0F172A; padding:3px 12px; border-radius:12px; font-weight:700; font-size:0.85rem;'>{groupe_actuel}</span></p>", unsafe_allow_html=True)
    if col_h2.button("Déconnexion", use_container_width=True):
        st.session_state['user'] = None
        st.query_params.clear()  # Efface l'URL lors de la déconnexion
        st.rerun()

    # --- COMPOSANT DES CARTES MÉTRIQUES (RAFRAÎCHISSEMENT AUTO TOUTES LES 5S) ---
    @st.fragment(run_every="5s")
    def afficher_metrics_live():
        pos_df = conn.query("SELECT ticker, shares FROM portfolio WHERE username=:u", params={"u": user}, ttl=0)
        valeur_actions = sum((obtenir_prix_actuel(row['ticker']) or 0) * row['shares'] for _, row in pos_df.iterrows())
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
        search_query = st.text_input("Rechercher une action ou entreprise", "Apple")
        selected_ticker = None
        if search_query:
            resultats = rechercher_symbole_universel(search_query)
            if resultats:
                options_dict = {res['label']: res['symbol'] for res in resultats}
                choix_label = st.selectbox("Sélectionnez l'action :", list(options_dict.keys()))
                selected_ticker = options_dict[choix_label]
            else: selected_ticker = search_query.strip().upper()

        if selected_ticker:
            details = obtenir_details_financiers(selected_ticker)
            if details:
                prix, var, var_pct = details["Prix"], details["Variation"], details["VariationPct"]
                chart_color = "#10B981" if var >= 0 else "#EF4444"
                signe = "+" if var >= 0 else ""

                col_chart, col_order = st.columns([2.2, 1])
                with col_chart:
                    st.markdown(f"### {selected_ticker} — ${prix:,.2f} ({signe}{var_pct:.2f}%)")
                    period_map = {"1mo": "1 Mois", "3mo": "3 Mois", "6mo": "6 Mois", "1y": "1 An"}
                    selected_period = st.selectbox("Horizon d'analyse", list(period_map.keys()), format_func=lambda x: period_map[x])
                    df_hist = obtenir_historique(selected_ticker, selected_period)
                    if df_hist is not None and not df_hist.empty:
                        fig = go.Figure(go.Scatter(x=df_hist.index, y=df_hist['Close'], mode='lines', line=dict(color=chart_color, width=3)))
                        fig.update_layout(paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)', height=320, margin=dict(l=0, r=0, t=10, b=0), font=dict(color="#64748B"))
                        st.plotly_chart(fig, use_container_width=True)

                with col_order:
                    st.markdown("### Passer un ordre")
                    qty = st.number_input("Quantité", min_value=1, step=1, value=1)
                    cost_total = prix * qty
                    st.write(f"Total estimé : **${cost_total:,.2f}**")
                    now_str = datetime.now(ZoneInfo("America/Toronto")).strftime("%Y-%m-%d %H:%M:%S")

                    col_b, col_s = st.columns(2)
                    if col_b.button("Acheter", use_container_width=True):
                        if cash_actuel >= cost_total:
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
                            st.success(f"Achat de {qty} {selected_ticker.upper()} effectué !")
                            st.rerun()
                        else: st.error("Fonds insuffisants.")

                    if col_s.button("Vendre", use_container_width=True):
                        p_res = conn.query("SELECT shares FROM portfolio WHERE username=:u AND LOWER(ticker)=LOWER(:t)", params={"u": user, "t": selected_ticker}, ttl=0)
                        if not p_res.empty and int(p_res.iloc[0]['shares']) >= qty:
                            with conn.session as session:
                                session.execute(text("UPDATE users SET cash = cash + :cost WHERE username = :u"), {"cost": cost_total, "u": user})
                                rem = int(p_res.iloc[0]['shares']) - qty
                                if rem > 0:
                                    session.execute(text("UPDATE portfolio SET shares=:s WHERE username=:u AND LOWER(ticker)=LOWER(:t)"), {"s": rem, "u": user, "t": selected_ticker})
                                else:
                                    session.execute(text("DELETE FROM portfolio WHERE username=:u AND LOWER(ticker)=LOWER(:t)"), {"u": user, "t": selected_ticker})
                                session.execute(text("INSERT INTO transactions (username, ticker, type, shares, price, total, timestamp) VALUES (:u, :t, 'VENTE', :s, :p, :tot, :time)"),
                                                {"u": user, "t": selected_ticker.upper(), "s": qty, "p": prix, "tot": cost_total, "time": now_str})
                                session.commit()
                            st.success(f"Vente de {qty} {selected_ticker.upper()} effectuée !")
                            st.rerun()
                        else: st.error("Vous ne possédez pas cette quantité d'actions.")

    # --- ONGLET 2 : POSITIONS ET IMPRESSION PRO (RAFRAÎCHISSEMENT AUTO TOUTES LES 5S) ---
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

        # COMPOSANT DES POSITIONS MIS À JOUR EN TEMPS RÉEL (TOUTES LES 5 SECONDES)
        @st.fragment(run_every="5s")
        def afficher_positions_live():
            pos_df_live = conn.query("SELECT ticker, shares FROM portfolio WHERE username=:u", params={"u": user}, ttl=0)
            val_actions_live = sum((obtenir_prix_actuel(row['ticker']) or 0) * row['shares'] for _, row in pos_df_live.iterrows())
            val_totale_live = cash_actuel + val_actions_live
            prof_total_live = val_totale_live - 10000.00
            rend_pct_live = (prof_total_live / 10000.00) * 100

            date_impression = datetime.now(ZoneInfo("America/Toronto")).strftime("%d/%m/%Y à %H:%M")
            pnl_color_print = "#10B981" if prof_total_live >= 0 else "#EF4444"

            # EN-TÊTE DÉDIÉ IMPRESSION
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
                    pa = obtenir_prix_actuel(tk) or 0.0
                    pm = pm or pa
                    val = sh * pa
                    pnl = (pa - pm) * sh
                    pnl_pct = ((pa - pm) / pm * 100) if pm > 0 else 0

                    pnl_color = "#10B981" if pnl >= 0 else "#EF4444"
                    options_vente[f"{tk} ({sh} action(s) disponible(s))"] = (tk, sh, pa)

                    html_rows += f"<tr><td><b>{tk}</b></td><td>{sh}</td><td>${pm:,.2f}</td><td>${pa:,.2f}</td><td>${val:,.2f}</td><td style='color:{pnl_color}; font-weight:700;'>${pnl:+,.2f}</td><td style='color:{pnl_color}; font-weight:700;'>{pnl_pct:+.2f}%</td></tr>"

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
                        now_str = datetime.now(ZoneInfo("America/Toronto")).strftime("%Y-%m-%d %H:%M:%S")
                        with conn.session as session:
                            session.execute(text("UPDATE users SET cash = cash + :cost WHERE username = :u"), {"cost": total_vente, "u": user})
                            rem = max_sh - qty_v
                            if rem > 0:
                                session.execute(text("UPDATE portfolio SET shares=:s WHERE username=:u AND ticker=:t"), {"s": rem, "u": user, "t": tk_v})
                            else:
                                session.execute(text("DELETE FROM portfolio WHERE username=:u AND ticker=:t"), {"u": user, "t": tk_v})
                            session.execute(text("INSERT INTO transactions (username, ticker, type, shares, price, total, timestamp) VALUES (:u, :t, 'VENTE', :s, :p, :tot, :time)"),
                                            {"u": user, "t": tk_v, "s": qty_v, "p": pa_v, "tot": total_vente, "time": now_str})
                            session.commit()
                        st.success(f"Vente de {qty_v} action(s) {tk_v} confirmée !")
                        st.rerun()
            else: st.info("Vous n'avez aucune position ouverte actuellement.")

        afficher_positions_live()

    # --- ONGLET 3 : HISTORIQUE ---
    with tab_hist:
        tx_all = conn.query("SELECT timestamp, type, ticker, shares, price, total FROM transactions WHERE username=:u ORDER BY id DESC", params={"u": user}, ttl=0)
        if not tx_all.empty:
            tx_all.columns = ["Date & Heure", "Type", "Action", "Quantité", "Prix ($)", "Total ($)"]
            st.dataframe(tx_all, use_container_width=True, hide_index=True)
        else: st.info("Aucune transaction.")

    # --- ONGLET 4 : CLASSEMENT ---
    with tab_rank:
        grp_filter = st.selectbox("Filtrer par groupe :", ["Tous les groupes"] + LISTE_GROUPES)
        query_u = "SELECT username, cash, groupe FROM users" if grp_filter == "Tous les groupes" else f"SELECT username, cash, groupe FROM users WHERE groupe='{grp_filter}'"
        users_df = conn.query(query_u, ttl=0)
        
        lb = []
        for _, r in users_df.iterrows():
            u_name, u_cash, u_grp = r['username'], float(r['cash']), r['groupe']
            u_p = conn.query("SELECT ticker, shares FROM portfolio WHERE username=:u", params={"u": u_name}, ttl=0)
            u_val_act = sum((obtenir_prix_actuel(row['ticker']) or 0) * row['shares'] for _, row in u_p.iterrows())
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
            q_e = "SELECT username FROM users ORDER BY username" if grp_p == "Tous les groupes" else f"SELECT username FROM users WHERE groupe='{grp_p}' ORDER BY username"
            e_list = conn.query(q_e, ttl=0)['username'].tolist()
            if e_list:
                e_sel = st.selectbox("Élève à inspecter :", e_list)
                e_data = conn.query("SELECT cash, groupe FROM users WHERE username=:u", params={"u": e_sel}, ttl=0).iloc[0]
                e_cash, e_grp = float(e_data['cash']), e_data['groupe']
                e_pos = conn.query("SELECT ticker, shares, avg_price FROM portfolio WHERE username=:u", params={"u": e_sel}, ttl=0)
                e_val_act = sum((obtenir_prix_actuel(row['ticker']) or 0) * row['shares'] for _, row in e_pos.iterrows())
                st.markdown(f"#### Fiche de {e_sel} ({e_grp})")
                st.metric("Total", f"${e_cash + e_val_act:,.2f}", f"{((e_cash + e_val_act - 10000)/10000)*100:+.2f}%")
                st.dataframe(e_pos, use_container_width=True, hide_index=True)
                st.dataframe(conn.query("SELECT timestamp, type, ticker, shares, price, total FROM transactions WHERE username=:u ORDER BY id DESC", params={"u": e_sel}, ttl=0), use_container_width=True, hide_index=True)
