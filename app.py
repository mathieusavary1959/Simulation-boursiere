import streamlit as st
import yfinance as yf
import sqlite3
import pandas as pd
import plotly.graph_objects as go

# --- CONFIGURATION DE LA PAGE ---
st.set_page_config(page_title="MarketWatch Simulator - École", layout="wide")

# --- DESIGN MARKETWATCH GAMES (STYLE SLATE FINANCIAL) ---
st.markdown("""
    <style>
    .stApp {
        background-color: #0B0E14;
        color: #E2E8F0;
        font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
    }
    
    #MainMenu, footer, header {visibility: hidden;}

    /* Top Banner Game Dashboard */
    .game-card {
        background: #151C28;
        border: 1px solid #2A364F;
        border-radius: 12px;
        padding: 16px 20px;
        box-shadow: 0 4px 12px rgba(0,0,0,0.3);
    }

    div[data-testid="stMetric"] {
        background: #151C28;
        border: 1px solid #2A364F;
        border-radius: 12px;
        padding: 16px 20px;
    }
    
    div[data-testid="stMetricValue"] {
        font-size: 1.9rem !important;
        font-weight: 700;
        color: #FFFFFF !important;
    }

    div[data-testid="stMetricLabel"] {
        color: #94A3B8 !important;
        font-size: 0.8rem;
        text-transform: uppercase;
        font-weight: 600;
        letter-spacing: 0.5px;
    }

    /* Tabs Style MarketWatch */
    .stTabs [data-baseweb="tab-list"] {
        gap: 8px;
        background-color: #151C28;
        padding: 6px;
        border-radius: 10px;
        border: 1px solid #2A364F;
        margin-bottom: 20px;
    }

    .stTabs [data-baseweb="tab"] {
        background-color: transparent;
        border-radius: 8px;
        color: #94A3B8 !important;
        padding: 8px 20px;
        border: none !important;
        font-weight: 600;
    }

    .stTabs [aria-selected="true"] {
        background-color: #2563EB !important;
        color: #FFFFFF !important;
    }
    
    .stTabs [aria-selected="true"] span {
        color: #FFFFFF !important;
    }

    /* Inputs */
    .stTextInput>div>div>input, .stNumberInput>div>div>input, .stSelectbox>div>div {
        background-color: #151C28 !important;
        color: #FFFFFF !important;
        border-radius: 8px !important;
        border: 1px solid #2A364F !important;
    }

    /* Order Trade Buttons */
    .stButton>button {
        border-radius: 8px !important;
        background-color: #2563EB !important;
        color: #FFFFFF !important;
        font-weight: 700 !important;
        border: none !important;
        padding: 10px 20px !important;
        transition: all 0.2s ease;
    }
    
    .stButton>button:hover {
        background-color: #1D4ED8 !important;
        transform: translateY(-1px);
    }

    /* Tables */
    div[data-testid="stDataFrame"] {
        background-color: #151C28;
        border-radius: 12px;
        border: 1px solid #2A364F;
    }
    
    hr {
        border-color: #2A364F !important;
    }
    </style>
""", unsafe_allow_html=True)

# --- BASE DE DONNÉES ---
conn = sqlite3.connect('bourse_ecole.db', check_same_thread=False)
c = conn.cursor()

c.execute('''CREATE TABLE IF NOT EXISTS users 
             (username TEXT PRIMARY KEY, password TEXT, cash REAL)''')
c.execute('''CREATE TABLE IF NOT EXISTS portfolio 
             (username TEXT, ticker TEXT, shares INTEGER, avg_price REAL, PRIMARY KEY(username, ticker))''')
conn.commit()

# --- CACHE DES DONNÉES BOURSIÈRES ---
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
            "Plus haut": f"${info['dayHigh']:.2f}" if info.get('dayHigh') else "N/A",
            "Plus bas": f"${info['dayLow']:.2f}" if info.get('dayLow') else "N/A",
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

# --- GESTION SESSION ---
if 'user' not in st.session_state:
    st.session_state['user'] = None
if 'selected_ticker' not in st.session_state:
    st.session_state['selected_ticker'] = "AAPL"

st.markdown("<h1 style='font-size: 2.2rem; font-weight: 800; color: #FFFFFF; margin-bottom: 20px;'>MARKETWATCH SIMULATOR</h1>", unsafe_allow_html=True)

# --- CONNEXION / INSCRIPTION ---
if st.session_state['user'] is None:
    col_centered = st.columns([1, 1.3, 1])[1]
    with col_centered:
        tab1, tab2 = st.tabs(["Connexion au Jeu", "Créer un Compte Élève"])
        
        with tab1:
            u_login = st.text_input("Nom d'utilisateur")
            p_login = st.text_input("Mot de passe", type="password")
            if st.button("Rejoindre la Partie", use_container_width=True):
                c.execute("SELECT * FROM users WHERE username=? AND password=?", (u_login, p_login))
                if c.fetchone():
                    st.session_state['user'] = u_login
                    st.rerun()
                else:
                    st.error("Identifiants introuvables.")

        with tab2:
            u_new = st.text_input("Identifiant désiré")
            p_new = st.text_input("Mot de passe désiré", type="password")
            if st.button("S'inscrire", use_container_width=True):
                try:
                    c.execute("INSERT INTO users VALUES (?, ?, 10000.00)", (u_new, p_new))
                    conn.commit()
                    st.success("Compte joueur créé !")
                except sqlite3.IntegrityError:
                    st.error("Identifiant déjà pris.")

else:
    user = st.session_state['user']

    # --- CALCUL DES VALEURS ET DU RANG DU JOUEUR ---
    c.execute("SELECT username, cash FROM users")
    all_users = c.fetchall()
    
    leaderboard = []
    for u, c_val in all_users:
        c.execute("SELECT ticker, shares FROM portfolio WHERE username=?", (u,))
        u_pos = c.fetchall()
        u_actions_val = sum((obtenir_prix_actuel(tk) or 0) * sh for tk, sh in u_pos)
        tot = c_val + u_actions_val
        leaderboard.append({"user": u, "total": tot, "cash": c_val, "actions_val": u_actions_val})

    df_lb_calc = pd.DataFrame(leaderboard).sort_values(by="total", ascending=False).reset_index(drop=True)
    
    # Trouver le rang du joueur actuel
    user_rank = df_lb_calc[df_lb_calc['user'] == user].index[0] + 1
    total_players = len(df_lb_calc)
    
    user_data = df_lb_calc[df_lb_calc['user'] == user].iloc[0]
    cash_actuel = user_data['cash']
    valeur_actions = user_data['actions_val']
    valeur_totale = user_data['total']
    profit_total = valeur_totale - 10000.00
    rendement_pct = (profit_total / 10000.00) * 100

    # BANNIÈRE TABLEAU DE BORD JOUEUR (MarketWatch Game Header)
    col_h1, col_h2 = st.columns([4, 1])
    col_h1.markdown(f"<p style='color: #94A3B8;'>Joueur connecté : <b style='color: #FFFFFF;'>{user}</b></p>", unsafe_allow_html=True)
    if col_h2.button("Déconnexion", use_container_width=True):
        st.session_state['user'] = None
        st.rerun()

    col_m1, col_m2, col_m3, col_m4 = st.columns(4)
    col_m1.metric("Rang au classement", f"#{user_rank} / {total_players}")
    col_m2.metric("Valeur du Portefeuille", f"${valeur_totale:,.2f}")
    col_m3.metric("Pouvoir d'achat (Cash)", f"${cash_actuel:,.2f}")
    col_m4.metric("Gain / Perte Global", f"${profit_total:,.2f}", f"{rendement_pct:+.2f}%")

    st.markdown("<hr>", unsafe_allow_html=True)

    # ONGLETS DE NAVIGATION DU JEU
    tab_trade, tab_port, tab_rank = st.tabs(["Trouver & Transiger", "Mon Portefeuille", "Classement du Jeu"])

    # --- ONGLET 1 : TROUVER ET TRANSIGER ---
    with tab_trade:
        st.markdown("<h4 style='font-weight:700;'>Raccourcis populaires</h4>", unsafe_allow_html=True)
        
        # Boutons de raccourcis rapides
        cols_quick = st.columns(7)
        quick_tickers = ["AAPL", "NVDA", "TSLA", "MSFT", "SHOP.TO", "TD.TO", "RY.TO"]
        for idx, qt in enumerate(quick_tickers):
            if cols_quick[idx].button(qt, use_container_width=True):
                st.session_state['selected_ticker'] = qt

        col_search1, col_search2 = st.columns([3, 1])
        symbol_input = col_search1.text_input("Rechercher un symbole (ex: AAPL, AMZN, GOOGL, TD.TO)", st.session_state['selected_ticker']).strip().upper()
        
        if symbol_input:
            st.session_state['selected_ticker'] = symbol_input

        symbol = st.session_state['selected_ticker']
        details = obtenir_details_financiers(symbol)

        if details:
            prix = details["Prix"]
            var = details["Variation"]
            var_pct = details["VariationPct"]
            color_code = "#10B981" if var >= 0 else "#EF4444"
            signe = "+" if var >= 0 else ""

            st.markdown("<br>", unsafe_allow_html=True)

            # DISPOSITION MARKETWATCH TRADING (GRAPHIQUE GAUCHE / BILLET D'ORDRE DROITE)
            col_chart_side, col_order_side = st.columns([2.2, 1])

            # GAUCHE : EN-TÊTE + GRAPHIQUE + INFOS
            with col_chart_side:
                st.markdown(f"""
                    <div style="display:flex; justify-shadow:space-between; align-items:baseline;">
                        <h2 style="margin:0; font-size:2rem; font-weight:800;">{symbol}</h2>
                        <h2 style="margin:0; color:{color_code}; font-size:2rem; font-weight:800; margin-left:15px;">
                            ${prix:,.2f} <span style="font-size:1.1rem;">({signe}${var:,.2f} / {signe}{var_pct:.2f}%)</span>
                        </h2>
                    </div>
                """, unsafe_allow_html=True)

                col_t_space, col_period = st.columns([3, 1])
                period_map = {"1mo": "1 Mois", "3mo": "3 Mois", "6mo": "6 Mois", "1y": "1 An"}
                selected_period = col_period.selectbox("Période", list(period_map.keys()), format_func=lambda x: period_map[x])

                df_hist = obtenir_historique(symbol, selected_period)
                if df_hist is not None and not df_hist.empty:
                    fig = go.Figure()
                    fig.add_trace(go.Scatter(
                        x=df_hist.index, 
                        y=df_hist['Close'], 
                        mode='lines', 
                        name='Prix', 
                        line=dict(color=color_code, width=2.5),
                        fill='tozeroy',
                        fillcolor='rgba(37, 99, 235, 0.05)'
                    ))

                    fig.update_layout(
                        paper_bgcolor='rgba(0,0,0,0)',
                        plot_bgcolor='rgba(0,0,0,0)',
                        margin=dict(l=0, r=0, t=10, b=0),
                        height=340,
                        showlegend=False,
                        hovermode="x unified",
                        font=dict(color='#94A3B8'),
                        xaxis=dict(showgrid=False),
                        yaxis=dict(showgrid=True, gridcolor='#2A364F', side='right')
                    )
                    st.plotly_chart(fig, use_container_width=True)

                st.markdown("### Statistiques clés")
                stats_df = pd.DataFrame([
                    {"Ouverture": details["Ouverture"], "Plus Haut": details["Plus haut"], "Plus Bas": details["Plus bas"]},
                    {"52 sem. Haut": details["52 sem. Haut"], "52 sem. Bas": details["52 sem. Bas"], "Marché": "Actions"}
                ])
                st.dataframe(stats_df, use_container_width=True, hide_index=True)

            # DROITE : BILLET D'ORDRE (TRADE TICKET)
            with col_order_side:
                st.markdown("""
                    <div style="background:#151C28; border:1px solid #2A364F; border-radius:12px; padding:20px;">
                        <h3 style="margin-top:0; font-weight:700;">Billet d'ordre</h3>
                """, unsafe_allow_html=True)

                qty = st.number_input("Nombre d'actions", min_value=1, step=1, value=1)
                cost_total = prix * qty

                st.markdown(f"""
                    <div style="margin:15px 0;">
                        <p style="color:#94A3B8; margin:0;">Prix unitaire : <b>${prix:,.2f}</b></p>
                        <p style="color:#94A3B8; margin:0;">Estimation totale : <b style="color:#FFFFFF; font-size:1.2rem;">${cost_total:,.2f}</b></p>
                        <p style="color:#94A3B8; margin:0;">Cash disponible : <b>${cash_actuel:,.2f}</b></p>
                    </div>
                """, unsafe_allow_html=True)

                col_b_buy, col_b_sell = st.columns(2)
                
                if col_b_buy.button("ACHETER", use_container_width=True):
                    if cash_actuel >= cost_total:
                        c.execute("UPDATE users SET cash=? WHERE username=?", (cash_actuel - cost_total, user))
                        c.execute("SELECT shares, avg_price FROM portfolio WHERE username=? AND ticker=?", (user, symbol))
                        row = c.fetchone()
                        if row:
                            anc_shares, anc_price = row[0], row[1] or prix
                            n_shares = anc_shares + qty
                            n_price = ((anc_shares * anc_price) + (qty * prix)) / n_shares
                            c.execute("UPDATE portfolio SET shares=?, avg_price=? WHERE username=? AND ticker=?", (n_shares, n_price, user, symbol))
                        else:
                            c.execute("INSERT INTO portfolio VALUES (?, ?, ?, ?)", (user, symbol, qty, prix))
                        conn.commit()
                        st.success(f"Acheté {qty} x {symbol}")
                        st.rerun()
                    else:
                        st.error("Cash insuffisant.")

                if col_b_sell.button("VENDRE", use_container_width=True):
                    c.execute("SELECT shares FROM portfolio WHERE username=? AND ticker=?", (user, symbol))
                    row = c.fetchone()
                    if row and row[0] >= qty:
                        c.execute("UPDATE users SET cash=? WHERE username=?", (cash_actuel + cost_total, user))
                        rem = row[0] - qty
                        if rem > 0:
                            c.execute("UPDATE portfolio SET shares=? WHERE username=? AND ticker=?", (rem, user, symbol))
                        else:
                            c.execute("DELETE FROM portfolio WHERE username=? AND ticker=?", (user, symbol))
                        conn.commit()
                        st.success(f"Vendu {qty} x {symbol}")
                        st.rerun()
                    else:
                        st.error("Quantité d'actions insuffisante.")

                st.markdown("</div>", unsafe_allow_html=True)

        else:
            st.warning("Symbole introuvable. Essaie un symbole valide comme AAPL, MSFT, TSLA, SHOP.TO.")

    # --- ONGLET 2 : MON PORTEFEUILLE ---
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
                    "Symbole": t,
                    "Actions": s,
                    "Prix Moyen": f"${p_moyen:,.2f}",
                    "Prix Actuel": f"${p_actuel:,.2f}",
                    "Valeur Totale": f"${val_tot:,.2f}",
                    "Gain / Perte": f"${pnl:+,.2f}",
                    "Rendement (%)": f"{pnl_pct:+.2f}%"
                })
            st.dataframe(pd.DataFrame(data_p), use_container_width=True, hide_index=True)
        else:
            st.info("Aucune position ouverte actuellement.")

    # --- ONGLET 3 : CLASSEMENT DU JEU ---
    with tab_rank:
        st.markdown("<h3 style='font-weight:700;'>Classement Général du Jeu</h3>", unsafe_allow_html=True)
        
        df_lb_show = df_lb_calc.copy()
        df_lb_show.index += 1
        df_lb_show['Rang'] = df_lb_show.index
        df_lb_show['Performance (%)'] = ((df_lb_show['total'] - 10000.00) / 10000.00) * 100
        
        df_lb_show['Valeur Totale'] = df_lb_show['total'].map("${:,.2f}".format)
        df_lb_show['Cash'] = df_lb_show['cash'].map("${:,.2f}".format)
        df_lb_show['Performance (%)'] = df_lb_show['Performance (%)'].map("{:+.2f}%".format)
        df_lb_show.rename(columns={'user': 'Élève Joueur'}, inplace=True)
        
        st.dataframe(df_lb_show[['Rang', 'Élève Joueur', 'Valeur Totale', 'Cash', 'Performance (%)']], use_container_width=True, hide_index=True)
