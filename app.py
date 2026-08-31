import streamlit as st
import yfinance as yf
import sqlite3
import pandas as pd
import plotly.graph_objects as go

# --- CONFIGURATION DE LA PAGE ---
st.set_page_config(page_title="Simulateur Boursier", layout="wide")

# --- DESIGN HAUTE FIDÉLITÉ (STYLE APPLE / SPOTIFY / NETFLIX) ---
st.markdown("""
    <style>
    /* Fond principal sombre profond */
    .stApp {
        background: #090A0F;
        color: #F5F5F7;
        font-family: -apple-system, BlinkMacSystemFont, "SF Pro Display", "SF Pro Text", "Helvetica Neue", sans-serif;
    }
    
    /* Masquer les éléments natifs Streamlit inutilement visibles */
    #MainMenu, footer, header {visibility: hidden;}

    /* Cartes Glassmorphism */
    div[data-testid="stMetric"] {
        background: rgba(255, 255, 255, 0.03);
        border: 1px solid rgba(255, 255, 255, 0.08);
        border-radius: 16px;
        padding: 20px 24px;
        backdrop-filter: blur(20px);
        box-shadow: 0 8px 32px 0 rgba(0, 0, 0, 0.3);
        transition: all 0.3s ease;
    }
    
    div[data-testid="stMetric"]:hover {
        border-color: rgba(255, 255, 255, 0.18);
        background: rgba(255, 255, 255, 0.05);
    }
    
    div[data-testid="stMetricValue"] {
        font-size: 2.1rem !important;
        font-weight: 700;
        color: #FFFFFF !important;
        letter-spacing: -0.5px;
    }

    div[data-testid="stMetricLabel"] {
        color: #8E8E93 !important;
        font-size: 0.8rem;
        text-transform: uppercase;
        letter-spacing: 1px;
        font-weight: 600;
    }

    /* Navigation par Onglets (Style Pill Buttons Spotify/Apple) */
    .stTabs [data-baseweb="tab-list"] {
        gap: 12px;
        background-color: rgba(255, 255, 255, 0.04);
        padding: 6px;
        border-radius: 50px;
        border: 1px solid rgba(255, 255, 255, 0.06);
        max-width: fit-content;
        margin-bottom: 25px;
    }

    .stTabs [data-baseweb="tab"] {
        background-color: transparent;
        border-radius: 50px;
        color: #8E8E93 !important;
        padding: 10px 24px;
        border: none !important;
        font-weight: 600;
        font-size: 0.9rem;
        transition: all 0.2s ease;
    }

    .stTabs [aria-selected="true"] {
        background-color: #FFFFFF !important;
        color: #000000 !important;
        box-shadow: 0 4px 14px rgba(255, 255, 255, 0.25);
    }
    
    .stTabs [aria-selected="true"] span {
        color: #000000 !important;
    }

    /* Champs de saisie */
    .stTextInput>div>div>input, .stNumberInput>div>div>input, .stSelectbox>div>div {
        background-color: rgba(255, 255, 255, 0.05) !important;
        color: #FFFFFF !important;
        border-radius: 12px !important;
        border: 1px solid rgba(255, 255, 255, 0.1) !important;
        padding: 12px 16px !important;
        font-size: 0.95rem !important;
    }
    
    .stTextInput>div>div>input:focus, .stNumberInput>div>div>input:focus {
        border-color: #0A84FF !important;
        box-shadow: 0 0 0 2px rgba(10, 132, 255, 0.3) !important;
    }

    /* Boutons de transaction (Acheter / Vendre) */
    .stButton>button {
        border-radius: 12px !important;
        background: #FFFFFF !important;
        color: #000000 !important;
        font-weight: 700 !important;
        border: none !important;
        padding: 12px 24px !important;
        font-size: 0.95rem !important;
        transition: all 0.2s ease !important;
        box-shadow: 0 4px 15px rgba(255, 255, 255, 0.15);
    }
    
    .stButton>button:hover {
        transform: translateY(-1px);
        box-shadow: 0 6px 20px rgba(255, 255, 255, 0.25);
        background: #F2F2F7 !important;
        color: #000000 !important;
    }

    /* Tableaux */
    div[data-testid="stDataFrame"] {
        background: rgba(255, 255, 255, 0.02);
        border-radius: 16px;
        border: 1px solid rgba(255, 255, 255, 0.08);
        padding: 8px;
    }
    
    hr {
        border-color: rgba(255, 255, 255, 0.08) !important;
        margin: 30px 0 !important;
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

# --- FONCTIONS REQUÊTES EN DIRECT (AVEC CORRECTION DE LA PÉRIODE) ---
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
        return {
            "Prix Ouverture": f"${info['open']:.2f}" if info.get('open') else "N/A",
            "Plus Haut (Jour)": f"${info['dayHigh']:.2f}" if info.get('dayHigh') else "N/A",
            "Plus Bas (Jour)": f"${info['dayLow']:.2f}" if info.get('dayLow') else "N/A",
            "Plus Haut (52 sem.)": f"${info['yearHigh']:.2f}" if info.get('yearHigh') else "N/A",
            "Plus Bas (52 sem.)": f"${info['yearLow']:.2f}" if info.get('yearLow') else "N/A",
        }
    except Exception:
        return None

@st.cache_data(ttl=180)
def obtenir_historique(ticker_symbol, periode):
    try:
        # Périodes valides yfinance: 1mo, 3mo, 6mo, 1y
        df = yf.Ticker(ticker_symbol).history(period=periode)
        return df
    except Exception:
        return None

# --- GESTION SESSION ---
if 'user' not in st.session_state:
    st.session_state['user'] = None

st.markdown("<h1 style='font-size: 2.4rem; font-weight: 800; letter-spacing: -1px; margin-bottom: 25px;'>PORTFOLIO</h1>", unsafe_allow_html=True)

# --- INTERFACE DE CONNEXION / INSCRIPTION ---
if st.session_state['user'] is None:
    col_centered = st.columns([1, 1.3, 1])[1]
    with col_centered:
        tab1, tab2 = st.tabs(["Connexion", "Créer un compte"])
        
        with tab1:
            u_login = st.text_input("Identifiant")
            p_login = st.text_input("Mot de passe", type="password")
            if st.button("Se connecter", use_container_width=True):
                c.execute("SELECT * FROM users WHERE username=? AND password=?", (u_login, p_login))
                if c.fetchone():
                    st.session_state['user'] = u_login
                    st.rerun()
                else:
                    st.error("Identifiants incorrects.")

        with tab2:
            u_new = st.text_input("Nouvel identifiant")
            p_new = st.text_input("Nouveau mot de passe", type="password")
            if st.button("S'inscrire", use_container_width=True):
                try:
                    c.execute("INSERT INTO users VALUES (?, ?, 10000.00)", (u_new, p_new))
                    conn.commit()
                    st.success("Compte créé. Connexion autorisée.")
                except sqlite3.IntegrityError:
                    st.error("Cet identifiant est déjà utilisé.")

else:
    user = st.session_state['user']
    
    # En-tête utilisateur
    col_h1, col_h2 = st.columns([4, 1])
    col_h1.markdown(f"<p style='color: #8E8E93; font-size: 1rem; margin-top: 5px;'>Membre connecté : <b style='color: #FFFFFF;'>{user}</b></p>", unsafe_allow_html=True)
    if col_h2.button("Déconnexion", use_container_width=True):
        st.session_state['user'] = None
        st.rerun()

    # Calculs du portefeuille
    c.execute("SELECT cash FROM users WHERE username=?", (user,))
    cash_actuel = c.fetchone()[0]
    
    c.execute("SELECT ticker, shares FROM portfolio WHERE username=?", (user,))
    positions = c.fetchall()
    
    valeur_actions = sum((obtenir_prix_actuel(tk) or 0) * sh for tk, sh in positions)
    valeur_totale = cash_actuel + valeur_actions
    profit_total = valeur_totale - 10000.00
    rendement_pct = (profit_total / 10000.00) * 100

    # Cartes d'indicateurs (Apple Style Metrics)
    col_m1, col_m2, col_m3, col_m4 = st.columns(4)
    col_m1.metric("Solde Cash", f"${cash_actuel:,.2f}")
    col_m2.metric("Valeur des Actifs", f"${valeur_actions:,.2f}")
    col_m3.metric("Valeur Totale", f"${valeur_totale:,.2f}")
    col_m4.metric("Rendement Global", f"${profit_total:,.2f}", f"{rendement_pct:+.2f}%")

    st.markdown("<hr>", unsafe_allow_html=True)

    # NAVIGATION PRINCIPALE
    tab_trade, tab_port, tab_rank = st.tabs(["Marché & Graphiques", "Mon Portefeuille", "Classement"])

    # --- ONGLET 1 : MARCHÉ ET ORDRES ---
    with tab_trade:
        col_m, col_s, col_q = st.columns([2, 2, 2])
        marche = col_m.selectbox("Sélectionner le marché", ["États-Unis (NYSE/NASDAQ)", "Canada (TSX)"])
        raw_symbol = col_s.text_input("Symbole d'action", "AAPL").strip().upper()
        qty = col_q.number_input("Quantité à négocier", min_value=1, step=1)

        symbol = f"{raw_symbol}.TO" if "Canada" in marche and not (raw_symbol.endswith(".TO") or raw_symbol.endswith(".V")) else raw_symbol

        if symbol:
            prix = obtenir_prix_actuel(symbol)
            details = obtenir_details_financiers(symbol)

            if prix:
                st.markdown("<br>", unsafe_allow_html=True)
                
                # Header Action
                col_head_left, col_head_right = st.columns([3, 1])
                col_head_left.markdown(f"<h2 style='margin:0; font-size: 2rem; font-weight:700;'>{symbol}</h2>", unsafe_allow_html=True)
                col_head_right.markdown(f"<h2 style='margin:0; text-align:right; color:#30D158; font-size: 2rem; font-weight:700;'>${prix:,.2f}</h2>", unsafe_allow_html=True)

                # Sélecteur de période du graphique
                col_title, col_period = st.columns([4, 1.2])
                period_map = {"1mo": "1 Mois", "3mo": "3 Mois", "6mo": "6 Mois", "1y": "1 An"}
                selected_period = col_period.selectbox("Horizon temporel", list(period_map.keys()), format_func=lambda x: period_map[x])

                # RÉCUPÉRATION ET AFFICHAGE GARANTI DU GRAPHIQUE
                df_hist = obtenir_historique(symbol, selected_period)

                if df_hist is not None and not df_hist.empty:
                    # Graphique fluide style Apple / TradingView
                    fig = go.Figure()
                    
                    # Courbe principale
                    fig.add_trace(go.Scatter(
                        x=df_hist.index, 
                        y=df_hist['Close'], 
                        mode='lines', 
                        name='Prix', 
                        line=dict(color='#30D158', width=2.5),
                        fill='tozeroy',
                        fillcolor='rgba(48, 209, 88, 0.08)'
                    ))

                    fig.update_layout(
                        paper_bgcolor='rgba(0,0,0,0)',
                        plot_bgcolor='rgba(0,0,0,0)',
                        margin=dict(l=0, r=0, t=10, b=0),
                        height=360,
                        showlegend=False,
                        hovermode="x unified",
                        font=dict(color='#8E8E93', family='-apple-system'),
                        xaxis=dict(showgrid=False, zeroline=False),
                        yaxis=dict(showgrid=True, gridcolor='rgba(255,255,255,0.05)', zeroline=False, side='right')
                    )
                    st.plotly_chart(fig, use_container_width=True)
                else:
                    st.info("Chargement des données du graphique en cours ou données indisponibles pour cet horizon.")

                # Grille des données financières sous le graphique
                if details:
                    st.markdown("<h4 style='font-weight:600; margin-top:20px;'>Indicateurs de marché</h4>", unsafe_allow_html=True)
                    cols_det = st.columns(len(details))
                    for idx, (k, v) in enumerate(details.items()):
                        cols_det[idx].metric(k, v)

                st.markdown("<hr>", unsafe_allow_html=True)
                
                # Panneau de transaction
                col_b, col_s = st.columns(2)
                cost_total = prix * qty

                if col_b.button(f"Acheter {qty} x {symbol} (${cost_total:,.2f})", use_container_width=True):
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
                        st.success("Ordre d'achat exécuté.")
                        st.rerun()
                    else:
                        st.error("Solde en cash insuffisant.")

                if col_s.button(f"Vendre {qty} x {symbol} (${cost_total:,.2f})", use_container_width=True):
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
                        st.success("Ordre de vente exécuté.")
                        st.rerun()
                    else:
                        st.error("Nombre d'actions insuffisant dans votre portefeuille.")
            else:
                st.warning("Action non trouvée. Vérifie le symbole (ex: AAPL, NVDA, TSLA, SHOP, TD).")

    # --- ONGLET 2 : MON PORTEFEUILLE ---
    with tab_port:
        if positions:
            data_p = []
            for t, s in positions:
                p_actuel = obtenir_prix_actuel(t) or 0.0
                c.execute("SELECT avg_price FROM portfolio WHERE username=? AND ticker=?", (user, t))
                p_moyen = c.fetchone()[0] or p_actuel
                val_tot = s * p_actuel
                pnl = (p_actuel - p_moyen) * s
                pnl_pct = ((p_actuel - p_moyen) / p_moyen * 100) if p_moyen > 0 else 0
                
                data_p.append({
                    "Titre": t,
                    "Actions": s,
                    "Prix Moyen": f"${p_moyen:,.2f}",
                    "Prix Actuel": f"${p_actuel:,.2f}",
                    "Valeur Totale": f"${val_tot:,.2f}",
                    "Gain / Perte": f"${pnl:+,.2f}",
                    "Rendement": f"{pnl_pct:+.2f}%"
                })
            st.dataframe(pd.DataFrame(data_p), use_container_width=True, hide_index=True)
        else:
            st.info("Aucune position ouverte actuellement.")

    # --- ONGLET 3 : CLASSEMENT ---
    with tab_rank:
        st.markdown("<h3 style='font-weight:700;'>Classement général des élèves</h3>", unsafe_allow_html=True)
        
        c.execute("SELECT username, cash FROM users")
        all_users = c.fetchall()
        
        leaderboard = []
        for u, c_val in all_users:
            c.execute("SELECT ticker, shares FROM portfolio WHERE username=?", (u,))
            u_pos = c.fetchall()
            u_actions_val = sum((obtenir_prix_actuel(tk) or 0) * sh for tk, sh in u_pos)
            tot = c_val + u_actions_val
            perf = ((tot - 10000.00) / 10000.00) * 100
            leaderboard.append({"Rang": 0, "Élève": u, "Valeur du Portefeuille": tot, "Performance": perf})

        df_lb = pd.DataFrame(leaderboard).sort_values(by="Valeur du Portefeuille", ascending=False).reset_index(drop=True)
        df_lb["Rang"] = df_lb.index + 1
        
        df_lb["Valeur du Portefeuille"] = df_lb["Valeur du Portefeuille"].map("${:,.2f}".format)
        df_lb["Performance"] = df_lb["Performance"].map("{:+.2f}%".format)
        
        st.dataframe(df_lb[["Rang", "Élève", "Valeur du Portefeuille", "Performance"]], use_container_width=True, hide_index=True)
