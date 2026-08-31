import streamlit as st
import yfinance as yf
import sqlite3
import pandas as pd
import plotly.graph_objects as go

# --- CONFIGURATION PAGE ---
st.set_page_config(page_title="Simulateur Boursier", layout="wide")

# --- STYLISATION INTERFACE (STYLE SPOTIFY) ---
st.markdown("""
    <style>
    /* Fond principal */
    .stApp {
        background-color: #121212;
        color: #FFFFFF;
    }
    
    /* Titres et textes */
    h1, h2, h3, h4, h5, h6, p, label {
        color: #FFFFFF !important;
        font-family: 'Circular', -apple-system, BlinkMacSystemFont, Roboto, sans-serif;
    }

    /* Cartes de métriques */
    div[data-testid="stMetric"] {
        background-color: #181818;
        border: 1px solid #282828;
        border-radius: 8px;
        padding: 16px;
    }
    
    div[data-testid="stMetricValue"] {
        font-size: 1.8rem !important;
        font-weight: 700;
        color: #FFFFFF !important;
    }

    div[data-testid="stMetricLabel"] {
        color: #B3B3B3 !important;
        font-size: 0.9rem;
    }

    /* Style des Onglets (Type pilules Spotify) */
    .stTabs [data-baseweb="tab-list"] {
        gap: 10px;
        background-color: transparent;
    }

    .stTabs [data-baseweb="tab"] {
        background-color: #282828;
        border-radius: 50px;
        color: #FFFFFF !important;
        padding: 8px 20px;
        border: none !important;
        font-weight: 600;
    }

    .stTabs [aria-selected="true"] {
        background-color: #FFFFFF !important;
        color: #000000 !important;
    }
    
    .stTabs [aria-selected="true"] span {
        color: #000000 !important;
    }

    /* Champs de saisie */
    .stTextInput>div>div>input, .stNumberInput>div>div>input, .stSelectbox>div>div {
        background-color: #282828 !important;
        color: #FFFFFF !important;
        border-radius: 6px !important;
        border: 1px solid #3E3E3E !important;
    }

    /* Boutons */
    .stButton>button {
        border-radius: 50px !important;
        background-color: #FFFFFF !important;
        color: #000000 !important;
        font-weight: 700 !important;
        border: none !important;
        padding: 10px 24px !important;
        transition: transform 0.1s ease-in-out;
    }
    
    .stButton>button:hover {
        transform: scale(1.02);
        background-color: #F0F0F0 !important;
        color: #000000 !important;
    }

    /* Tableaux */
    div[data-testid="stDataFrame"] {
        background-color: #181818;
        border-radius: 8px;
        border: 1px solid #282828;
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
        return {
            "Dernier prix": f"${info['lastPrice']:.2f}",
            "Ouverture": f"${info['open']:.2f}" if info.get('open') else "N/A",
            "Plus haut (jour)": f"${info['dayHigh']:.2f}" if info.get('dayHigh') else "N/A",
            "Plus bas (jour)": f"${info['dayLow']:.2f}" if info.get('dayLow') else "N/A",
            "Plus haut (52 sem.)": f"${info['yearHigh']:.2f}" if info.get('yearHigh') else "N/A",
            "Plus bas (52 sem.)": f"${info['yearLow']:.2f}" if info.get('yearLow') else "N/A",
        }
    except Exception:
        return None

@st.cache_data(ttl=300)
def obtenir_historique(ticker_symbol):
    try:
        df = yf.Ticker(ticker_symbol).history(period="1m")
        return df
    except Exception:
        return None

# --- SESSION UTILISATEUR ---
if 'user' not in st.session_state:
    st.session_state['user'] = None

st.title("SIMULATEUR BOURSIER")

# --- INTERFACE DE CONNEXION / INSCRIPTION ---
if st.session_state['user'] is None:
    col_centered = st.columns([1, 2, 1])[1]
    with col_centered:
        tab1, tab2 = st.tabs(["Connexion", "Inscription"])
        
        with tab1:
            u_login = st.text_input("Nom d'utilisateur")
            p_login = st.text_input("Mot de passe", type="password")
            if st.button("Se connecter", use_container_width=True):
                c.execute("SELECT * FROM users WHERE username=? AND password=?", (u_login, p_login))
                if c.fetchone():
                    st.session_state['user'] = u_login
                    st.rerun()
                else:
                    st.error("Identifiants incorrects.")

        with tab2:
            u_new = st.text_input("Choisir un nom d'utilisateur")
            p_new = st.text_input("Choisir un mot de passe", type="password")
            if st.button("Créer mon compte", use_container_width=True):
                try:
                    c.execute("INSERT INTO users VALUES (?, ?, 10000.00)", (u_new, p_new))
                    conn.commit()
                    st.success("Compte créé. Connexion autorisée.")
                except sqlite3.IntegrityError:
                    st.error("Nom d'utilisateur indisponible.")

else:
    user = st.session_state['user']
    
    col_h1, col_h2 = st.columns([4, 1])
    col_h1.markdown(f"### Session : **{user}**")
    if col_h2.button("Déconnexion", use_container_width=True):
        st.session_state['user'] = None
        st.rerun()

    # Calcul des métriques du portefeuille
    c.execute("SELECT cash FROM users WHERE username=?", (user,))
    cash_actuel = c.fetchone()[0]
    
    c.execute("SELECT ticker, shares FROM portfolio WHERE username=?", (user,))
    positions = c.fetchall()
    
    valeur_actions = sum((obtenir_prix_actuel(tk) or 0) * sh for tk, sh in positions)
    valeur_totale = cash_actuel + valeur_actions
    profit_total = valeur_totale - 10000.00
    rendement_pct = (profit_total / 10000.00) * 100

    # Affichage des cartes de performances
    col_m1, col_m2, col_m3, col_m4 = st.columns(4)
    col_m1.metric("Cash disponible", f"${cash_actuel:,.2f}")
    col_m2.metric("Valeur du portefeuille", f"${valeur_actions:,.2f}")
    col_m3.metric("Valeur totale", f"${valeur_totale:,.2f}")
    col_m4.metric("Performance globale", f"${profit_total:,.2f}", f"{rendement_pct:+.2f}%")

    st.write("---")

    # ONGLETS PRINCIPAUX
    tab_trade, tab_port, tab_rank = st.tabs(["Marché et Ordres", "Mon Portefeuille", "Classement général"])

    # --- ONGLET 1 : MARCHÉ ET ORDRES ---
    with tab_trade:
        c_m, c_s, c_q = st.columns([2, 2, 2])
        marche = c_m.selectbox("Marché", ["Etats-Unis (NYSE/NASDAQ)", "Canada (TSX)"])
        raw_symbol = c_s.text_input("Symbole de l'action", "AAPL").strip().upper()
        qty = c_q.number_input("Quantité d'actions", min_value=1, step=1)

        symbol = f"{raw_symbol}.TO" if "Canada" in marche and not (raw_symbol.endswith(".TO") or raw_symbol.endswith(".V")) else raw_symbol

        if symbol:
            prix = obtenir_prix_actuel(symbol)
            details = obtenir_details_financiers(symbol)

            if prix and details:
                st.write("---")
                col_graph, col_table = st.columns([3, 2])

                # Graphique interactif (Style Sombre)
                with col_graph:
                    st.subheader(f"Évolution de {symbol}")
                    df_hist = obtenir_historique(symbol)
                    if df_hist is not None and not df_hist.empty:
                        fig = go.Figure()
                        fig.add_trace(go.Scatter(
                            x=df_hist.index, 
                            y=df_hist['Close'], 
                            mode='lines', 
                            name=symbol, 
                            line=dict(color='#FFFFFF', width=2)
                        ))
                        fig.update_layout(
                            paper_bgcolor='rgba(0,0,0,0)',
                            plot_bgcolor='rgba(0,0,0,0)',
                            margin=dict(l=10, r=10, t=20, b=10),
                            height=320,
                            font=dict(color='#B3B3B3'),
                            xaxis=dict(showgrid=False),
                            yaxis=dict(showgrid=True, gridcolor='#282828')
                        )
                        st.plotly_chart(fig, use_container_width=True)

                # Tableau des données financières
                with col_table:
                    st.subheader("Données financières")
                    df_details = pd.DataFrame(list(details.items()), columns=["Métrique", "Valeur"])
                    st.dataframe(df_details, use_container_width=True, hide_index=True)

                st.write("---")
                col_b, col_s = st.columns(2)
                
                # ACHAT
                if col_b.button(f"Acheter {qty} x {symbol} (${(prix * qty):,.2f})", use_container_width=True):
                    cout = prix * qty
                    if cash_actuel >= cout:
                        c.execute("UPDATE users SET cash=? WHERE username=?", (cash_actuel - cout, user))
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
                        st.success("Transaction d'achat validée.")
                        st.rerun()
                    else:
                        st.error("Solde insuffisant.")

                # VENTE
                if col_s.button(f"Vendre {qty} x {symbol} (${(prix * qty):,.2f})", use_container_width=True):
                    c.execute("SELECT shares FROM portfolio WHERE username=? AND ticker=?", (user, symbol))
                    row = c.fetchone()
                    if row and row[0] >= qty:
                        c.execute("UPDATE users SET cash=? WHERE username=?", (cash_actuel + (prix * qty), user))
                        rem = row[0] - qty
                        if rem > 0:
                            c.execute("UPDATE portfolio SET shares=? WHERE username=? AND ticker=?", (rem, user, symbol))
                        else:
                            c.execute("DELETE FROM portfolio WHERE username=? AND ticker=?", (user, symbol))
                        conn.commit()
                        st.success("Transaction de vente validée.")
                        st.rerun()
                    else:
                        st.error("Nombre d'actions insuffisant.")
            else:
                st.warning("Symbole introuvable sur ce marché.")

    # --- ONGLET 2 : PORTEFEUILLE ---
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
                    "Action": t,
                    "Quantité": s,
                    "Prix Moyen Achat ($)": f"${p_moyen:,.2f}",
                    "Prix Actuel ($)": f"${p_actuel:,.2f}",
                    "Valeur Totale ($)": f"${val_tot:,.2f}",
                    "Gain/Perte ($)": f"${pnl:+,.2f}",
                    "Rendement (%)": f"{pnl_pct:+.2f}%"
                })
            st.dataframe(pd.DataFrame(data_p), use_container_width=True, hide_index=True)
        else:
            st.info("Aucune position ouverte.")

    # --- ONGLET 3 : CLASSEMENT ---
    with tab_rank:
        st.subheader("Classement général")
        
        c.execute("SELECT username, cash FROM users")
        all_users = c.fetchall()
        
        leaderboard = []
        for u, c_val in all_users:
            c.execute("SELECT ticker, shares FROM portfolio WHERE username=?", (u,))
            u_pos = c.fetchall()
            u_actions_val = sum((obtenir_prix_actuel(tk) or 0) * sh for tk, sh in u_pos)
            tot = c_val + u_actions_val
            perf = ((tot - 10000.00) / 10000.00) * 100
            leaderboard.append({"Élève": u, "Valeur du Portefeuille ($)": tot, "Performance (%)": perf})

        df_lb = pd.DataFrame(leaderboard).sort_values(by="Valeur du Portefeuille ($)", ascending=False).reset_index(drop=True)
        df_lb.index += 1
        
        df_lb["Valeur du Portefeuille ($)"] = df_lb["Valeur du Portefeuille ($)"].map("{:,.2f} $".format)
        df_lb["Performance (%)"] = df_lb["Performance (%)"].map("{:+.2f} %".format)
        
        st.dataframe(df_lb, use_container_width=True)
