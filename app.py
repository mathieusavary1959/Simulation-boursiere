import streamlit as st
import yfinance as yf
import pandas as pd
import plotly.graph_objects as go
import requests
from datetime import datetime
from zoneinfo import ZoneInfo
from sqlalchemy import text

# --- CONFIGURATION DE LA PAGE ---
st.set_page_config(page_title="Simulateur Boursier - École", layout="wide")

LISTE_GROUPES = [f"Groupe {i}" for i in range(501, 511)]

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

# Lancement unique de l'initialisation
init_db()

# --- DESIGN MODERN FINTECH ---
st.markdown("""
    <style>
    .stApp { background-color: #F8FAFC; color: #0F172A; font-family: -apple-system, BlinkMacSystemFont, "Inter", sans-serif; }
    #MainMenu, footer, header {visibility: hidden;}
    div[data-testid="stMetric"] { background-color: #FFFFFF; border: 1px solid #E2E8F0; border-radius: 16px; padding: 20px 24px; }
    div[data-testid="stMetricValue"] { font-size: 2rem !important; font-weight: 800 !important; color: #0F172A !important; }
    div[data-testid="stMetricLabel"] { color: #64748B !important; font-size: 0.8rem; text-transform: uppercase; font-weight: 700; }
    .stTabs [data-baseweb="tab-list"] { gap: 6px; background-color: #E2E8F0; padding: 6px; border-radius: 14px; max-width: fit-content; margin-bottom: 25px; }
    .stTabs [data-baseweb="tab"] { background-color: transparent; border-radius: 10px; color: #475569 !important; padding: 10px 22px; font-weight: 700; }
    .stTabs [aria-selected="true"] { background-color: #FFFFFF !important; color: #0F172A !important; box-shadow: 0 2px 8px rgba(15, 23, 42, 0.08); }
    .stTextInput>div>div>input, .stNumberInput>div>div>input, .stSelectbox>div>div { background-color: #FFFFFF !important; color: #0F172A !important; border-radius: 12px !important; border: 1px solid #CBD5E1 !important; padding: 10px 14px !important; }
    .stButton>button, div[data-testid="stFormSubmitButton"]>button { border-radius: 12px !important; background-color: #0F172A !important; color: #FFFFFF !important; font-weight: 700 !important; border: none !important; padding: 12px 24px !important; }
    .stButton>button:hover, div[data-testid="stFormSubmitButton"]>button:hover { background-color: #2563EB !important; color: #FFFFFF !important; }
    div[data-testid="stDataFrame"] { background-color: #FFFFFF; border-radius: 16px; border: 1px solid #E2E8F0; padding: 8px; }
    hr { border-color: #E2E8F0 !important; margin: 25px 0 !important; }
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

st.markdown("<h1 style='font-size: 2.2rem; font-weight: 900; color: #0F172A;'>Bourse & Investissement</h1>", unsafe_allow_html=True)

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
    col_h1.markdown(f"<p style='color: #64748B;'>Portefeuille : <b style='color: #0F172A;'>{user}</b> ({groupe_actuel})</p>", unsafe_allow_html=True)
    if col_h2.button("Déconnexion", use_container_width=True):
        st.session_state['user'] = None
        st.rerun()

    col_m1, col_m2, col_m3, col_m4 = st.columns(4)
    col_m1.metric("Disponible", f"${cash_actuel:,.2f}")
    col_m2.metric("Actions", f"${valeur_actions:,.2f}")
    col_m3.metric("Valeur Totale", f"${valeur_totale:,.2f}")
    col_m4.metric("Gains/Pertes", f"${profit_total:,.2f}", f"{rendement_pct:+.2f}%")

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
                    selected_period = st.selectbox("Horizon", list(period_map.keys()), format_func=lambda x: period_map[x])
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
                                p_res = conn.query("SELECT shares, avg_price FROM portfolio WHERE username=:u AND ticker=:t", params={"u": user, "t": selected_ticker}, ttl=0)
                                if not p_res.empty:
                                    anc_s, anc_p = p_res.iloc[0]['shares'], p_res.iloc[0]['avg_price'] or prix
                                    n_s = anc_s + qty
                                    n_p = ((anc_s * anc_p) + (qty * prix)) / n_s
                                    session.execute(text("UPDATE portfolio SET shares=:s, avg_price=:p WHERE username=:u AND ticker=:t"), {"s": n_s, "p": n_p, "u": user, "t": selected_ticker})
                                else:
                                    session.execute(text("INSERT INTO portfolio VALUES (:u, :t, :s, :p)"), {"u": user, "t": selected_ticker, "s": qty, "p": prix})
                                session.execute(text("INSERT INTO transactions (username, ticker, type, shares, price, total, timestamp) VALUES (:u, :t, 'ACHAT', :s, :p, :tot, :time)"),
                                                {"u": user, "t": selected_ticker, "s": qty, "p": prix, "tot": cost_total, "time": now_str})
                                session.commit()
                            st.success(f"Achat de {qty} {selected_ticker} effectué !")
                            st.rerun()
                        else: st.error("Fonds insuffisants.")

                    if col_s.button("Vendre", use_container_width=True):
                        p_res = conn.query("SELECT shares FROM portfolio WHERE username=:u AND ticker=:t", params={"u": user, "t": selected_ticker}, ttl=0)
                        if not p_res.empty and p_res.iloc[0]['shares'] >= qty:
                            with conn.session as session:
                                session.execute(text("UPDATE users SET cash = cash + :cost WHERE username = :u"), {"cost": cost_total, "u": user})
                                rem = p_res.iloc[0]['shares'] - qty
                                if rem > 0:
                                    session.execute(text("UPDATE portfolio SET shares=:s WHERE username=:u AND ticker=:t"), {"s": rem, "u": user, "t": selected_ticker})
                                else:
                                    session.execute(text("DELETE FROM portfolio WHERE username=:u AND ticker=:t"), {"u": user, "t": selected_ticker})
                                session.execute(text("INSERT INTO transactions (username, ticker, type, shares, price, total, timestamp) VALUES (:u, :t, 'VENTE', :s, :p, :tot, :time)"),
                                                {"u": user, "t": selected_ticker, "s": qty, "p": prix, "tot": cost_total, "time": now_str})
                                session.commit()
                            st.success(f"Vente de {qty} {selected_ticker} effectuée !")
                            st.rerun()
                        else: st.error("Actions insuffisantes.")

    # --- ONGLET 2 : POSITIONS ---
    with tab_port:
        p_all = conn.query("SELECT ticker, shares, avg_price FROM portfolio WHERE username=:u", params={"u": user}, ttl=0)
        if not p_all.empty:
            rows = []
            for _, r in p_all.iterrows():
                tk, sh, pm = r['ticker'], r['shares'], r['avg_price']
                pa = obtenir_prix_actuel(tk) or 0.0
                pm = pm or pa
                val = sh * pa
                pnl = (pa - pm) * sh
                pnl_pct = ((pa - pm) / pm * 100) if pm > 0 else 0
                rows.append({"Action": tk, "Quantité": sh, "Prix Moyen": f"${pm:,.2f}", "Prix Actuel": f"${pa:,.2f}", "Valeur": f"${val:,.2f}", "Gain/Perte": f"${pnl:+,.2f}", "Rendement": f"{pnl_pct:+.2f}%"})
            st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
        else: st.info("Aucune position ouverte.")

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
