import streamlit as st
import yfinance as yf
import sqlite3
import pandas as pd
import plotly.graph_objects as go
import requests
from datetime import datetime
from zoneinfo import ZoneInfo

# --- CONFIGURATION DE LA PAGE ---
st.set_page_config(page_title="Simulateur Boursier - École", layout="wide")

# --- DESIGN MODERN FINTECH (LIGHT MODE PRO) ---
st.markdown("""
    <style>
    .stApp {
        background-color: #F8FAFC;
        color: #0F172A;
        font-family: -apple-system, BlinkMacSystemFont, "Inter", "Segoe UI", Roboto, sans-serif;
    }
    
    #MainMenu, footer, header {visibility: hidden;}

    /* Cartes d'indicateurs */
    div[data-testid="stMetric"] {
        background-color: #FFFFFF;
        border: 1px solid #E2E8F0;
        border-radius: 16px;
        padding: 20px 24px;
        box-shadow: 0 4px 6px -1px rgba(15, 23, 42, 0.03);
        transition: all 0.2s ease;
    }
    
    div[data-testid="stMetric"]:hover {
        border-color: #CBD5E1;
        box-shadow: 0 10px 15px -3px rgba(15, 23, 42, 0.06);
    }
    
    div[data-testid="stMetricValue"] {
        font-size: 2rem !important;
        font-weight: 800 !important;
        color: #0F172A !important;
        letter-spacing: -0.5px;
    }

    div[data-testid="stMetricLabel"] {
        color: #64748B !important;
        font-size: 0.8rem;
        text-transform: uppercase;
        font-weight: 700;
        letter-spacing: 0.8px;
    }

    /* Navigation par Onglets */
    .stTabs [data-baseweb="tab-list"] {
        gap: 6px;
        background-color: #E2E8F0;
        padding: 6px;
        border-radius: 14px;
        border: none;
        max-width: fit-content;
        margin-bottom: 25px;
    }

    .stTabs [data-baseweb="tab"] {
        background-color: transparent;
        border-radius: 10px;
        color: #475569 !important;
        padding: 10px 22px;
        border: none !important;
        font-weight: 700;
        font-size: 0.95rem;
    }

    .stTabs [aria-selected="true"] {
        background-color: #FFFFFF !important;
        color: #0F172A !important;
        box-shadow: 0 2px 8px rgba(15, 23, 42, 0.08);
    }
    
    .stTabs [aria-selected="true"] span {
        color: #0F172A !important;
    }

    /* Champs de saisie */
    .stTextInput>div>div>input, .stNumberInput>div>div>input, .stSelectbox>div>div {
        background-color: #FFFFFF !important;
        color: #0F172A !important;
        border-radius: 12px !important;
        border: 1px solid #CBD5E1 !important;
        padding: 10px 14px !important;
        box-shadow: 0 1px 2px rgba(0, 0, 0, 0.05) !important;
        font-weight: 500;
    }

    /* Boutons */
    .stButton>button, div[data-testid="stFormSubmitButton"]>button {
        border-radius: 12px !important;
        background-color: #0F172A !important;
        color: #FFFFFF !important;
        font-weight: 700 !important;
        border: none !important;
        padding: 12px 24px !important;
        font-size: 0.95rem !important;
        transition: all 0.2s ease !important;
        box-shadow: 0 4px 12px rgba(15, 23, 42, 0.15);
    }
    
    .stButton>button:hover, div[data-testid="stFormSubmitButton"]>button:hover {
        background-color: #2563EB !important;
        color: #FFFFFF !important;
        transform: translateY(-1px);
        box-shadow: 0 6px 20px rgba(37, 99, 235, 0.25);
    }

    /* Tableaux */
    div[data-testid="stDataFrame"] {
        background-color: #FFFFFF;
        border-radius: 16px;
        border: 1px solid #E2E8F0;
        box-shadow: 0 4px 6px -1px rgba(15, 23, 42, 0.03);
        padding: 8px;
    }
    
    hr {
        border-color: #E2E8F0 !important;
        margin: 25px 0 !important;
    }
    </style>
""", unsafe_allow_html=True)

# --- BASE DE DONNÉES SQLITE ET STRUCTURE ---
conn = sqlite3.connect('bourse_ecole.db', check_same_thread=False)
c = conn.cursor()

c.execute('''CREATE TABLE IF NOT EXISTS users 
             (username TEXT PRIMARY KEY, password TEXT, cash REAL)''')

c.execute('''CREATE TABLE IF NOT EXISTS portfolio 
             (username TEXT, ticker TEXT, shares INTEGER, avg_price REAL, PRIMARY KEY(username, ticker))''')

c.execute('''CREATE TABLE IF NOT EXISTS transactions 
             (id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT, ticker TEXT, type TEXT, shares INTEGER, price REAL, total REAL, timestamp TEXT)''')

try:
    c.execute("ALTER TABLE portfolio ADD COLUMN avg_price REAL DEFAULT 0.0")
    conn.commit()
except sqlite3.OperationalError:
    pass

# --- RECHERCHE UNIVERSELLE ---
@st.cache_data(ttl=3600)
def rechercher_symbole_universel(query):
    if not query or len(query.strip()) < 1:
        return []
    url = f"https://query2.finance.yahoo.com/v1/finance/search?q={query}&quotesCount=8&newsCount=0"
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
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
                results.append({
                    'symbol': symbol,
                    'label': f"{shortname} ({symbol}) — {exch}"
                })
        return results
    except Exception:
        return []

# --- CACHE DONNÉES FINANCIÈRES ---
@st.cache_data(ttl=60)
def obtenir_prix_actuel(ticker_symbol):
    try:
        data = yf.Ticker(ticker_symbol)
        prix = data.fast_info['lastPrice']
        return round(float(prix), 2)
    except Exception:
        return None

@st.cache_data(ttl=60)
def obtenir_details_financiers(ticker_symbol):
    try:
        t = yf.Ticker(ticker_symbol)
        info = t.fast_info
        last = info['lastPrice']
        open_price = info.get('open', last)
        change = last - open_price
        change_pct = (change / open_price) * 100 if open_price else 0
        
        return {
            "Prix": last,
            "Variation": change,
            "VariationPct": change_pct,
            "Ouverture": f"${info['open']:.2f}" if info.get('open') else "N/A",
            "Plus Haut": f"${info['dayHigh']:.2f}" if info.get('dayHigh') else "N/A",
            "Plus Bas": f"${info['dayLow']:.2f}" if info.get('dayLow') else "N/A",
            "52 sem. Haut": f"${info['yearHigh']:.2f}" if info.get('yearHigh') else "N/A",
            "52 sem. Bas": f"${info['yearLow']:.2f}" if info.get('yearLow') else "N/A",
        }
    except Exception:
        return None

@st.cache_data(ttl=180)
def obtenir_historique(ticker_symbol, periode):
    try:
        df = yf.Ticker(ticker_symbol).history(period=periode)
        return df
    except Exception:
        return None

# --- GESTION DE SESSION ---
if 'user' not in st.session_state:
    st.session_state['user'] = None

st.markdown("<h1 style='font-size: 2.2rem; font-weight: 900; color: #0F172A; letter-spacing: -1px; margin-bottom: 20px;'>Bourse & Investissement</h1>", unsafe_allow_html=True)

# --- PORTAIL DE CONNEXION / INSCRIPTION ---
if st.session_state['user'] is None:
    col_centered = st.columns([1, 1.2, 1])[1]
    with col_centered:
        tab1, tab2 = st.tabs(["Connexion", "Créer un compte"])
        
        with tab1:
            with st.form("form_connexion"):
                u_login = st.text_input("Identifiant", key="login_user")
                p_login = st.text_input("Mot de passe", type="password", key="login_pass")
                btn_login = st.form_submit_button("Se connecter", use_container_width=True)
                
                if btn_login:
                    if not u_login or not p_login:
                        st.error("Veuillez remplir tous les champs.")
                    else:
                        c.execute("SELECT * FROM users WHERE username=? AND password=?", (u_login.strip(), p_login))
                        if c.fetchone():
                            st.session_state['user'] = u_login.strip()
                            st.rerun()
                        else:
                            st.error("Identifiants incorrects.")

        with tab2:
            with st.form("form_inscription"):
                u_new = st.text_input("Choisissez un identifiant (ex: PrenomNom)", key="new_user")
                p_new = st.text_input("Choisissez un mot de passe", type="password", key="new_pass")
                btn_signup = st.form_submit_button("S'inscrire", use_container_width=True)
                
                if btn_signup:
                    if not u_new or not p_new:
                        st.error("Veuillez remplir tous les champs.")
                    else:
                        try:
                            c.execute("INSERT INTO users VALUES (?, ?, 10000.00)", (u_new.strip(), p_new))
                            conn.commit()
                            st.success("Compte créé avec succès ! Connectez-vous dans l'onglet 'Connexion'.")
                        except sqlite3.IntegrityError:
                            st.error("Nom d'utilisateur déjà utilisé.")

else:
    user = st.session_state['user']

    # BANNIÈRE DE PERFORMANCE DE L'UTILISATEUR
    c.execute("SELECT cash FROM users WHERE username=?", (user,))
    res_cash = c.fetchone()
    cash_actuel = res_cash[0] if res_cash else 10000.00
    
    c.execute("SELECT ticker, shares FROM portfolio WHERE username=?", (user,))
    positions = c.fetchall()
    
    valeur_actions = sum((obtenir_prix_actuel(tk) or 0) * sh for tk, sh in positions)
    valeur_totale = cash_actuel + valeur_actions
    profit_total = valeur_totale - 10000.00
    rendement_pct = (profit_total / 10000.00) * 100

    col_h1, col_h2 = st.columns([4, 1])
    col_h1.markdown(f"<p style='color: #64748B; font-weight: 600;'>Portefeuille actif : <b style='color: #0F172A;'>{user}</b></p>", unsafe_allow_html=True)
    if col_h2.button("Déconnexion", use_container_width=True):
        st.session_state['user'] = None
        st.rerun()

    col_m1, col_m2, col_m3, col_m4 = st.columns(4)
    col_m1.metric("Argent disponible", f"${cash_actuel:,.2f}")
    col_m2.metric("Valeur Actions", f"${valeur_actions:,.2f}")
    col_m3.metric("Valeur Totale", f"${valeur_totale:,.2f}")
    col_m4.metric("Gains ou Pertes", f"${profit_total:,.2f}", f"{rendement_pct:+.2f}%")

    st.markdown("<hr>", unsafe_allow_html=True)

    # NAVIGATION PRINCIPALE
    tab_trade, tab_port, tab_hist, tab_rank, tab_teacher = st.tabs([
        "Marché & Analyse", 
        "Mes Positions", 
        "Mon Historique", 
        "Classement", 
        "Supervision Prof"
    ])

    # --- ONGLET 1 : ANALYSE & TRANSACTION ---
    with tab_trade:
        st.markdown("<h4 style='font-weight:700; color:#0F172A; margin-bottom:5px;'>Rechercher une entreprise ou une action</h4>", unsafe_allow_html=True)
        
        search_query = st.text_input("Tapez un nom d'entreprise ou un symbole (ex: Apple, Tesla, Shopify, TD, Microsoft...)", "Apple")
        selected_ticker = None
        
        if search_query:
            resultats = rechercher_symbole_universel(search_query)
            if resultats:
                options_dict = {res['label']: res['symbol'] for res in resultats}
                choix_label = st.selectbox("Sélectionnez l'action exacte dans la liste :", list(options_dict.keys()))
                selected_ticker = options_dict[choix_label]
            else:
                selected_ticker = search_query.strip().upper()

        if selected_ticker:
            details = obtenir_details_financiers(selected_ticker)

            if details:
                prix = details["Prix"]
                var = details["Variation"]
                var_pct = details["VariationPct"]
                is_positive = var >= 0
                chart_color = "#10B981" if is_positive else "#EF4444"
                fill_color = "rgba(16, 185, 129, 0.08)" if is_positive else "rgba(239, 68, 68, 0.08)"
                signe = "+" if is_positive else ""

                st.markdown("<br>", unsafe_allow_html=True)

                col_chart_side, col_order_side = st.columns([2.2, 1])

                with col_chart_side:
                    st.markdown(f"""
                        <div style="display:flex; justify-content:space-between; align-items:flex-end; margin-bottom:10px;">
                            <div>
                                <h2 style="margin:0; font-size:2.2rem; font-weight:800; color:#0F172A;">{selected_ticker}</h2>
                            </div>
                            <div style="text-align:right;">
                                <h2 style="margin:0; font-size:2.2rem; font-weight:800; color:#0F172A;">${prix:,.2f}</h2>
                                <span style="font-size:1rem; font-weight:700; color:{chart_color};">
                                    {signe}${var:,.2f} ({signe}{var_pct:.2f}%)
                                </span>
                            </div>
                        </div>
                    """, unsafe_allow_html=True)

                    col_t_space, col_period = st.columns([3, 1.2])
                    period_map = {"1mo": "1 Mois", "3mo": "3 Mois", "6mo": "6 Mois", "1y": "1 An"}
                    selected_period = col_period.selectbox("Horizon", list(period_map.keys()), format_func=lambda x: period_map[x])

                    df_hist = obtenir_historique(selected_ticker, selected_period)
                    if df_hist is not None and not df_hist.empty:
                        fig = go.Figure()
                        fig.add_trace(go.Scatter(
                            x=df_hist.index, 
                            y=df_hist['Close'], 
                            mode='lines', 
                            name='Prix', 
                            line=dict(color=chart_color, width=3),
                            fill='tozeroy',
                            fillcolor=fill_color
                        ))

                        fig.update_layout(
                            paper_bgcolor='rgba(0,0,0,0)',
                            plot_bgcolor='rgba(0,0,0,0)',
                            margin=dict(l=0, r=0, t=10, b=0),
                            height=340,
                            showlegend=False,
                            hovermode="x unified",
                            font=dict(color='#64748B', family='-apple-system'),
                            xaxis=dict(showgrid=False),
                            yaxis=dict(showgrid=True, gridcolor='#E2E8F0', side='right')
                        )
                        st.plotly_chart(fig, use_container_width=True)

                    st.markdown("### Statistiques clés")
                    stats_df = pd.DataFrame([
                        {"Ouverture": details["Ouverture"], "Plus Haut": details["Plus Haut"], "Plus Bas": details["Plus Bas"]},
                        {"52 sem. Haut": details["52 sem. Haut"], "52 sem. Bas": details["52 sem. Bas"], "Ticker": selected_ticker}
                    ])
                    st.dataframe(stats_df, use_container_width=True, hide_index=True)

                with col_order_side:
                    st.markdown("""
                        <div style="background:#FFFFFF; border:1px solid #E2E8F0; border-radius:18px; padding:22px; box-shadow:0 10px 25px rgba(0,0,0,0.03);">
                            <h3 style="margin-top:0; font-weight:800; color:#0F172A; font-size:1.2rem;">Passer un ordre</h3>
                    """, unsafe_allow_html=True)

                    qty = st.number_input("Nombre d'actions", min_value=1, step=1, value=1)
                    cost_total = prix * qty

                    st.markdown(f"""
                        <div style="background:#F8FAFC; padding:15px; border-radius:12px; margin:15px 0; border:1px solid #E2E8F0;">
                            <div style="display:flex; justify-content:space-between; margin-bottom:6px;">
                                <span style="color:#64748B; font-size:0.9rem;">Prix unitaire</span>
                                <span style="font-weight:700; color:#0F172A;">${prix:,.2f}</span>
                            </div>
                            <div style="display:flex; justify-content:space-between; margin-bottom:6px;">
                                <span style="color:#64748B; font-size:0.9rem;">Argent disponible</span>
                                <span style="font-weight:700; color:#0F172A;">${cash_actuel:,.2f}</span>
                            </div>
                            <hr style="margin:10px 0 !important;">
                            <div style="display:flex; justify-content:space-between;">
                                <span style="font-weight:700; color:#0F172A;">Total estimé</span>
                                <span style="font-weight:800; color:#2563EB; font-size:1.1rem;">${cost_total:,.2f}</span>
                            </div>
                        </div>
                    """, unsafe_allow_html=True)

                    col_b_buy, col_b_sell = st.columns(2)
                    
                    # HORODATAGE EN HEURE DU QUÉBEC
                    now_str = datetime.now(ZoneInfo("America/Toronto")).strftime("%Y-%m-%d %H:%M:%S")

                    if col_b_buy.button("Acheter", use_container_width=True):
                        if cash_actuel >= cost_total:
                            c.execute("UPDATE users SET cash=? WHERE username=?", (cash_actuel - cost_total, user))
                            c.execute("SELECT shares, avg_price FROM portfolio WHERE username=? AND ticker=?", (user, selected_ticker))
                            row = c.fetchone()
                            if row:
                                anc_shares, anc_price = row[0], row[1] or prix
                                n_shares = anc_shares + qty
                                n_price = ((anc_shares * anc_price) + (qty * prix)) / n_shares
                                c.execute("UPDATE portfolio SET shares=?, avg_price=? WHERE username=? AND ticker=?", (n_shares, n_price, user, selected_ticker))
                            else:
                                c.execute("INSERT INTO portfolio VALUES (?, ?, ?, ?)", (user, selected_ticker, qty, prix))
                            
                            c.execute("INSERT INTO transactions VALUES (NULL, ?, ?, 'ACHAT', ?, ?, ?, ?)",
                                      (user, selected_ticker, qty, prix, cost_total, now_str))
                            
                            conn.commit()
                            st.success(f"Achat de {qty} action(s) confirmé.")
                            st.rerun()
                        else:
                            st.error("Solde d'argent disponible insuffisant.")

                    if col_b_sell.button("Vendre", use_container_width=True):
                        c.execute("SELECT shares FROM portfolio WHERE username=? AND ticker=?", (user, selected_ticker))
                        row = c.fetchone()
                        if row and row[0] >= qty:
                            c.execute("UPDATE users SET cash=? WHERE username=?", (cash_actuel + cost_total, user))
                            rem = row[0] - qty
                            if rem > 0:
                                c.execute("UPDATE portfolio SET shares=? WHERE username=? AND ticker=?", (rem, user, selected_ticker))
                            else:
                                c.execute("DELETE FROM portfolio WHERE username=? AND ticker=?", (user, selected_ticker))
                            
                            c.execute("INSERT INTO transactions VALUES (NULL, ?, ?, 'VENTE', ?, ?, ?, ?)",
                                      (user, selected_ticker, qty, prix, cost_total, now_str))
                            
                            conn.commit()
                            st.success(f"Vente de {qty} action(s) confirmée.")
                            st.rerun()
                        else:
                            st.error("Nombre d'actions insuffisant en portefeuille.")

                    st.markdown("</div>", unsafe_allow_html=True)
            else:
                st.warning("Aucune donnée financière trouvée pour cette recherche.")

    # --- ONGLET 2 : MES POSITIONS ---
    with tab_port:
        c.execute("SELECT ticker, shares, avg_price FROM portfolio WHERE username=?", (user,))
        pos_user = c.fetchall()

        if pos_user:
            data_p = []
            for t, s, p_moyen in pos_user:
                p_actuel = obtenir_prix_actuel(t) or 0.0
                p_moyen = p_moyen or p_actuel
                val_tot = s * p_actuel
                pnl = (p_actuel - p_moyen) * s
                pnl_pct = ((p_actuel - p_moyen) / p_moyen * 100) if p_moyen > 0 else 0
                
                data_p.append({
                    "Action": t,
                    "Quantité": s,
                    "Prix Moyen": f"${p_moyen:,.2f}",
                    "Prix Actuel": f"${p_actuel:,.2f}",
                    "Valeur Totale": f"${val_tot:,.2f}",
                    "Gain / Perte": f"${pnl:+,.2f}",
                    "Rendement (%)": f"{pnl_pct:+.2f}%"
                })
            st.dataframe(pd.DataFrame(data_p), use_container_width=True, hide_index=True)
        else:
            st.info("Vous n'avez aucune position ouverte actuellement.")

    # --- ONGLET 3 : MON HISTORIQUE DE TRANSACTIONS ---
    with tab_hist:
        st.markdown("<h3 style='font-weight:800; color:#0F172A;'>Journal de vos transactions</h3>", unsafe_allow_html=True)
        c.execute("SELECT timestamp, type, ticker, shares, price, total FROM transactions WHERE username=? ORDER BY id DESC", (user,))
        txs = c.fetchall()
        
        if txs:
            df_tx = pd.DataFrame(txs, columns=["Date & Heure", "Type", "Action", "Quantité", "Prix Unitaire ($)", "Montant Total ($)"])
            df_tx["Prix Unitaire ($)"] = df_tx["Prix Unitaire ($)"].map("${:,.2f}".format)
            df_tx["Montant Total ($)"] = df_tx["Montant Total ($)"].map("${:,.2f}".format)
            st.dataframe(df_tx, use_container_width=True, hide_index=True)
        else:
            st.info("Aucune transaction enregistrée.")

    # --- ONGLET 4 : CLASSEMENT ---
    with tab_rank:
        st.markdown("<h3 style='font-weight:800; color:#0F172A;'>Classement général</h3>", unsafe_allow_html=True)
        c.execute("SELECT username, cash FROM users")
        all_users = c.fetchall()
        
        leaderboard = []
        for u, c_val in all_users:
            c.execute("SELECT ticker, shares FROM portfolio WHERE username=?", (u,))
            u_pos = c.fetchall()
            u_actions_val = sum((obtenir_prix_actuel(tk) or 0) * sh for tk, sh in u_pos)
            tot = c_val + u_actions_val
            perf = ((tot - 10000.00) / 10000.00) * 100
            leaderboard.append({"Élève": u, "Portefeuille ($)": tot, "Performance (%)": perf})

        if leaderboard:
            df_lb = pd.DataFrame(leaderboard).sort_values(by="Portefeuille ($)", ascending=False).reset_index(drop=True)
            df_lb.index += 1
            df_lb['Rang'] = df_lb.index
            df_lb["Portefeuille ($)"] = df_lb["Portefeuille ($)"].map("${:,.2f}".format)
            df_lb["Performance (%)"] = df_lb["Performance (%)"].map("{:+.2f}%".format)
            st.dataframe(df_lb[['Rang', 'Élève', 'Portefeuille ($)', 'Performance (%)']], use_container_width=True, hide_index=True)

    # --- ONGLET 5 : SUPERVISION PROFESSEUR ---
    with tab_teacher:
        st.markdown("<h3 style='font-weight:800; color:#0F172A;'>Tableau de bord Enseignant</h3>", unsafe_allow_html=True)
        
        is_prof_user = user.lower() in ['prof', 'enseignant', 'admin']
        pin_input = ""
        
        if not is_prof_user:
            pin_input = st.text_input("Accès restreint. Entrez le PIN Enseignant :", type="password")
        
        if is_prof_user or pin_input == "1959":
            c.execute("SELECT username FROM users ORDER BY username ASC")
            liste_eleves = [r[0] for r in c.fetchall()]
            
            if liste_eleves:
                eleve_choisi = st.selectbox("Inspecter le compte de l'élève :", liste_eleves)
                
                if eleve_choisi:
                    c.execute("SELECT cash FROM users WHERE username=?", (eleve_choisi,))
                    e_cash = c.fetchone()[0]
                    
                    c.execute("SELECT ticker, shares, avg_price FROM portfolio WHERE username=?", (eleve_choisi,))
                    e_positions = c.fetchall()
                    
                    e_val_actions = sum((obtenir_prix_actuel(tk) or 0) * sh for tk, sh, _ in e_positions)
                    e_tot = e_cash + e_val_actions
                    e_perf = ((e_tot - 10000.00) / 10000.00) * 100
                    
                    col_e1, col_e2, col_e3, col_e4 = st.columns(4)
                    col_e1.metric("Argent disponible", f"${e_cash:,.2f}")
                    col_e2.metric("Actions", f"${e_val_actions:,.2f}")
                    col_e3.metric("Valeur Totale", f"${e_tot:,.2f}")
                    col_e4.metric("Gains ou Pertes", f"${e_tot-10000.00:,.2f}", f"{e_perf:+.2f}%")
                    
                    st.markdown("#### Positions en cours")
                    if e_positions:
                        d_ep = []
                        for t, s, pm in e_positions:
                            pa = obtenir_prix_actuel(t) or 0.0
                            pm = pm or pa
                            val_t = s * pa
                            pnl = (pa - pm) * s
                            d_ep.append({
                                "Action": t, "Quantité": s, "Prix Moyen": f"${pm:,.2f}", 
                                "Prix Actuel": f"${pa:,.2f}", "Valeur Totale": f"${val_t:,.2f}", "P&L": f"${pnl:+,.2f}"
                            })
                        st.dataframe(pd.DataFrame(d_ep), use_container_width=True, hide_index=True)
                    else:
                        st.write("Aucune position active.")
                    
                    st.markdown("#### Journal d'achat et de vente")
                    c.execute("SELECT timestamp, type, ticker, shares, price, total FROM transactions WHERE username=? ORDER BY id DESC", (eleve_choisi,))
                    e_txs = c.fetchall()
                    if e_txs:
                        df_etx = pd.DataFrame(e_txs, columns=["Date & Heure", "Type", "Action", "Quantité", "Prix Unitaire ($)", "Total ($)"])
                        df_etx["Prix Unitaire ($)"] = df_etx["Prix Unitaire ($)"].map("${:,.2f}".format)
                        df_etx["Total ($)"] = df_etx["Total ($)"].map("${:,.2f}".format)
                        st.dataframe(df_etx, use_container_width=True, hide_index=True)
                    else:
                        st.write("Aucune transaction effectuée.")
            else:
                st.info("Aucun élève inscrit pour le moment.")
        elif pin_input:
            st.error("PIN incorrect.")
