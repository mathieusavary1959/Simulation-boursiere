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

# Création automatique des tables (exécutée UNE SEULE FOIS au démarrage)
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

# --- DESIGN PREMIUM STYLE MONDE & FINANCE ---
st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700;800&display=swap');

    html, body, [class*="css"] {
        font-family: 'Plus Jakarta Sans', -apple-system, BlinkMacSystemFont, sans-serif;
    }

    .stApp {
        background-color: #F8FAFC;
        color: #0F172A;
    }

    #MainMenu, footer, header { visibility: hidden; }

    /* En-tête Institutionnel Monde & Finance */
    .brand-banner {
        background: linear-gradient(135deg, #0F172A 0%, #1E293B 100%);
        padding: 24px 32px;
        border-radius: 20px;
        color: #FFFFFF;
        margin-bottom: 28px;
        box-shadow: 0 10px 25px -5px rgba(15, 23, 42, 0.12);
        display: flex;
        justify-content: space-between;
        align-items: center;
    }
    .brand-title {
        font-size: 1.8rem;
        font-weight: 800;
        letter-spacing: -0.02em;
        margin: 0;
        color: #FFFFFF;
    }
    .brand-subtitle {
        color: #94A3B8;
        font-size: 0.88rem;
        font-weight: 500;
        margin-top: 4px;
    }
    .brand-badge {
        background-color: rgba(255, 255, 255, 0.1);
        border: 1px solid rgba(255, 255, 255, 0.15);
        padding: 6px 14px;
        border-radius: 30px;
        font-size: 0.8rem;
        font-weight: 700;
        color: #38BDF8;
        letter-spacing: 0.05em;
        text-transform: uppercase;
    }

    /* Cartes de métriques Financières */
    div[data-testid="stMetric"] {
        background-color: #FFFFFF;
        border: 1px solid #E2E8F0;
        border-radius: 18px;
        padding: 22px 26px;
        box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.02), 0 2px 4px -2px rgba(0, 0, 0, 0.02);
        transition: all 0.25s ease;
    }
    div[data-testid="stMetric"]:hover {
        transform: translateY(-2px);
        box-shadow: 0 12px 20px -3px rgba(0, 0, 0, 0.05);
        border-color: #CBD5E1;
    }
    div[data-testid="stMetricValue"] {
        font-size: 2.1rem !important;
        font-weight: 800 !important;
        color: #0F172A !important;
        letter-spacing: -0.03em;
    }
    div[data-testid="stMetricLabel"] {
        color: #64748B !important;
        font-size: 0.78rem;
        text-transform: uppercase;
        font-weight: 700;
        letter-spacing: 0.06em;
    }

    /* Navigation par Onglets (Barre Flottante Style Dashboard) */
    .stTabs [data-baseweb="tab-list"] {
        gap: 8px;
        background-color: #F1F5F9;
        padding: 6px;
        border-radius: 16px;
        max-width: fit-content;
        margin-bottom: 28px;
        border: 1px solid #E2E8F0;
    }
    .stTabs [data-baseweb="tab"] {
        background-color: transparent;
        border-radius: 12px;
        color: #64748B !important;
        padding: 10px 24px;
        font-weight: 700;
        font-size: 0.88rem;
        transition: all 0.2s;
    }
    .stTabs [aria-selected="true"] {
        background-color: #FFFFFF !important;
        color: #0F172A !important;
        box-shadow: 0 4px 12px rgba(15, 23, 42, 0.08) !important;
    }

    /* Champs de Saisie et Boutons Premium */
    .stTextInput>div>div>input, .stNumberInput>div>div>input, .stSelectbox>div>div {
        background-color: #FFFFFF !important;
        color: #0F172A !important;
        border-radius: 12px !important;
        border: 1px solid #CBD5E1 !important;
        padding: 11px 16px !important;
        font-weight: 500 !important;
    }
    .stTextInput>div>div>input:focus, .stSelectbox>div>div:focus {
        border-color: #2563EB !important;
        box-shadow: 0 0 0 3px rgba(37, 99, 235, 0.12) !important;
    }
    .stButton>button, div[data-testid="stFormSubmitButton"]>button {
        border-radius: 12px !important;
        background: linear-gradient(135deg, #0F172A 0%, #1E293B 100%) !important;
        color: #FFFFFF !important;
        font-weight: 700 !important;
        border: none !important;
        padding: 12px 24px !important;
        box-shadow: 0 4px 12px rgba(15, 23, 42, 0.12) !important;
        transition: all 0.2s ease !important;
    }
    .stButton>button:hover, div[data-testid="stFormSubmitButton"]>button:hover {
        background: linear-gradient(135deg, #2563EB 0%, #1D4ED8 100%) !important;
        transform: translateY(-1px) !important;
        box-shadow: 0 6px 16px rgba(37, 99, 235, 0.22) !important;
    }

    /* Tableaux de données */
    div[data-testid="stDataFrame"] {
        background-color: #FFFFFF;
        border-radius: 18px;
        border: 1px solid #E2E8F0;
        padding: 10px;
        box-shadow: 0 2px 4px rgba(0,0,0,0.02);
    }

    hr { border-color: #E2E8F0 !important; margin: 30px 0 !important; }
    </style>
""", unsafe_allow_html=True)

# --- RECHERCHE UNIVERSELLE & DONNÉES FINANCIÈRES ---
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

@st.cache_data(ttl=60)
def obtenir_prix_actuel(ticker_symbol):
    try: return round(float(yf.Ticker(ticker_symbol).fast_info['lastPrice']), 2)
    except Exception: return None

@st.cache_data(ttl=60)
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

# --- GESTION DE SESSION ---
if 'user' not in st.session_state:
    st.session_state['user'] = None

# BANNIÈRE D'EN-TÊTE
st.markdown("""
    <div class="brand-banner">
        <div>
            <div class="brand-title">MONDE & FINANCE</div>
            <div class="brand-subtitle">Plateforme d'Apprentissage & Simulation Boursière</div>
        </div>
        <div class="brand-badge">Édition Scolaire</div>
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

    pos_df = conn.query("SELECT ticker, shares FROM portfolio WHERE username=:u", params={"u": user}, ttl=0)
    valeur_actions = sum((obtenir_prix_actuel(row['ticker']) or 0) * row['shares'] for _, row in pos_df.iterrows())
    valeur_totale = cash_actuel + valeur_actions
    profit_total = valeur_totale - 10000.00
    rendement_pct = (profit_total / 10000.00) * 100

    col_h1, col_h2 = st.columns([4, 1])
    col_h1.markdown(f"<p style='color: #64748B; font-size: 1rem; margin-top:5px;'>Investisseur : <b style='color: #0F172A;'>{user}</b> &nbsp;•&nbsp; <span style='background:#E2E8F0; padding:3px 10px; border-radius:12px; font-weight:700; font-size:0.85rem;'>{groupe_actuel}</span></p>", unsafe_allow_html=True)
    if col_h2.button("Déconnexion", use_container_width=True):
        st.session_state['user'] = None
        st.rerun()

    col_m1, col_m2, col_m3, col_m4 = st.columns(4)
    col_m1.metric("Disponible", f"${cash_actuel:,.2f}")
    col_m2.metric("Actions", f"${valeur_actions:,.2f}")
    col_m3.metric("Valeur Totale", f"${valeur_totale:,.2f}")
    col_m4.metric("Gains / Pertes", f"${profit_total:,.2f}", f"{rendement_pct:+.2f}%")

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
                        fig.update_layout(paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)', height=320, margin=dict(l=0, r=0, t=10, b=0))
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

    # --- ONGLET 2 : POSITIONS ET VENTE RAPIDE (AVEC IMPRESSION PRO) ---
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
                }
                header, footer, [data-testid="stHeader"], [data-testid="stSidebar"],
                .stTabs [data-baseweb="tab-list"], .stButton, button, 
                iframe, hr, .stSelectbox, .stNumberInput, .brand-banner {
                    display: none !important;
                }
                .print-header {
                    display: block !important;
                    margin-bottom: 25px;
                    border-bottom: 2px solid #0F172A;
                    padding-bottom: 12px;
                }
            }
            .print-header { display: none; }
            </style>
        """, unsafe_allow_html=True)

        date_impression = datetime.now(ZoneInfo("America/Toronto")).strftime("%d/%m/%Y à %H:%M")
        st.markdown(f"""
            <div class="print-header">
                <h2 style="margin:0; color:#0F172A;">Rapport de Portefeuille Boursier — Monde & Finance</h2>
                <p style="margin:6px 0; font-size:1.05rem;"><b>Élève :</b> {user} &nbsp;|&nbsp; <b>Groupe :</b> {groupe_actuel} &nbsp;|&nbsp; <b>Date :</b> {date_impression}</p>
                <p style="margin:6px 0; font-size:1.05rem;"><b>Valeur totale :</b> ${valeur_totale:,.2f} &nbsp;|&nbsp; <b>Disponible :</b> ${cash_actuel:,.2f} &nbsp;|&nbsp; <b>Gains/Pertes :</b> ${profit_total:,.2f} ({rendement_pct:+.2f}%)</p>
            </div>
        """, unsafe_allow_html=True)

        col_p1, col_p2 = st.columns([3, 1])
        with col_p1:
            st.markdown(f"### Mes Positions Actuelles")
        with col_p2:
            components.html("""
                <button onclick="window.parent.print()" style="
                    background-color: #0F172A;
                    color: white;
                    border: none;
                    padding: 10px 18px;
                    border-radius: 12px;
                    font-weight: bold;
                    cursor: pointer;
                    width: 100%;
                    font-family: sans-serif;
                    box-shadow: 0 4px 10px rgba(0,0,0,0.1);
                ">
                    🖨️ Imprimer / PDF
                </button>
            """, height=45)

        p_all = conn.query("SELECT ticker, shares, avg_price FROM portfolio WHERE username=:u", params={"u": user}, ttl=0)
        if not p_all.empty:
            rows = []
            options_vente = {}
            for _, r in p_all.iterrows():
                tk, sh, pm = str(r['ticker']), int(r['shares']), float(r['avg_price'] or 0.0)
                pa = obtenir_prix_actuel(tk) or 0.0
                pm = pm or pa
                val = sh * pa
                pnl = (pa - pm) * sh
                pnl_pct = ((pa - pm) / pm * 100) if pm > 0 else 0
                rows.append({"Action": tk, "Quantité": sh, "Prix Moyen": f"${pm:,.2f}", "Prix Actuel": f"${pa:,.2f}", "Valeur": f"${val:,.2f}", "Gain/Perte": f"${pnl:+,.2f}", "Rendement": f"{pnl_pct:+.2f}%"})
                options_vente[f"{tk} ({sh} action(s) disponible(s))"] = (tk, sh, pa)

            st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

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
