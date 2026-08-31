import streamlit as st
import yfinance as yf
import sqlite3
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

# --- CONFIGURATION DE LA PAGE ---
st.set_page_config(page_title="Terminal Boursier", layout="wide")

# --- STYLE CSS PERSONNALISÉ HAUTE FIDÉLITÉ ---
st.markdown("""
    <style>
    /* Fond global */
    .stApp {
        background-color: #0A0C10;
        color: #E6EDF3;
        font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
    }
    
    /* Conteneurs et cartes */
    div[data-testid="stMetric"] {
        background-color: #12161F;
        border: 1px solid #212635;
        border-radius: 12px;
        padding: 16px 20px;
        box-shadow: 0 4px 20px rgba(0, 0, 0, 0.4);
    }
    
    div[data-testid="stMetricValue"] {
        font-size: 1.9rem !important;
        font-weight: 700;
        color: #FFFFFF !important;
        letter-spacing: -0.5px;
    }

    div[data-testid="stMetricLabel"] {
        color: #8B949E !important;
        font-size: 0.85rem;
        text-transform: uppercase;
        letter-spacing: 0.8px;
        font-weight: 600;
    }

    /* Onglets de navigation */
    .stTabs [data-baseweb="tab-list"] {
        gap: 8px;
        background-color: #12161F;
        padding: 6px;
        border-radius: 10px;
        border: 1px solid #212635;
    }

    .stTabs [data-baseweb="tab"] {
        background-color: transparent;
        border-radius: 8px;
        color: #8B949E !important;
        padding: 10px 24px;
        border: none !important;
        font-weight: 600;
        font-size: 0.9rem;
    }

    .stTabs [aria-selected="true"] {
        background-color: #212635 !important;
        color: #FFFFFF !important;
    }
    
    .stTabs [aria-selected="true"] span {
        color: #FFFFFF !important;
    }

    /* Inputs et formulaires */
    .stTextInput>div>div>input, .stNumberInput>div>div>input, .stSelectbox>div>div {
        background-color: #12161F !important;
        color: #FFFFFF !important;
        border-radius: 8px !important;
        border: 1px solid #212635 !important;
        padding: 10px !important;
    }
    
    .stTextInput>div>div>input:focus, .stNumberInput>div>div>input:focus {
        border-color: #58A6FF !important;
        box-shadow: 0 0 0 1px #58A6FF !important;
    }

    /* Boutons */
    .stButton>button {
        border-radius: 8px !important;
        background-color: #238636 !important;
        color: #FFFFFF !important;
        font-weight: 600 !important;
        border: 1px solid rgba(240, 246, 252, 0.1) !important;
        padding: 10px 20px !important;
        transition: all 0.2s ease;
    }
    
    .stButton>button:hover {
        background-color: #2EA043 !important;
        border-color: #8B949E !important;
    }

    /* Tableaux */
    div[data-testid="stDataFrame"] {
        background-color: #12161F;
        border-radius: 12px;
        border: 1px solid #212635;
        padding: 8px;
    }
    
    /* Ligne de séparation */
    hr {
        border-color: #212635 !important;
    }
    </style>
""", unsafe_allow_html=True)

# --- INITIALISATION BASE DE DONNÉES ---
conn = sqlite3.connect('bourse_ecole.db', check_same_thread=False)
c = conn.cursor()

c.execute('''CREATE TABLE IF NOT EXISTS users 
             (username TEXT PRIMARY KEY, password TEXT, cash REAL)''')
c.execute('''CREATE TABLE IF NOT EXISTS portfolio 
             (username TEXT, ticker TEXT, shares INTEGER, avg_price REAL, PRIMARY KEY(username, ticker))''')
conn.commit()

# --- FONCTIONS DE CACHE OPTIMISÉES ---
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

@st.cache_data(ttl=120)
def obtenir_historique(ticker_symbol, periode):
    try:
        df = yf.Ticker(ticker_symbol).history(period=periode)
        return df
    except Exception:
        return None

# --- GESTION DE LA SESSION ---
if 'user' not in st.session_state:
    st.session_state['user'] = None

st.markdown("<h1 style='font-size: 2.2rem; font-weight: 800; margin-bottom: 20px;'>TERMINAL BOURSIER</h1>", unsafe_allow_html=True)

# --- ECRAN DE CONNEXION / INSCRIPTION ---
if st.session_state['user'] is None:
    col_centered = st.columns([1, 1.5, 1])[1]
    with col_centered:
        st.markdown("<br>", unsafe_allow_html=True)
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
            if st.button("Créer un compte", use_container_width=True):
                try:
                    c.execute("INSERT INTO users VALUES (?, ?, 10000.00)", (u_new, p_new))
                    conn.commit()
                    st.success("Compte créé avec succès. Connexion autorisée.")
                except sqlite3.IntegrityError:
                    st.error("Ce nom d'utilisateur est déjà pris.")

else:
    user = st.session_state['user']
    
    # Barre supérieure utilisateur
    col_h1, col_h2 = st.columns([4, 1])
    col_h1.markdown(f"<p style='color: #8B949E; font-size: 1.1rem;'>Compte actif : <b style='color: #FFFFFF;'>{user}</b></p>", unsafe_allow_html=True)
    if col_h2.button("Déconnexion", use_container_width=True):
        st.session_state['user'] = None
        st.rerun()

    # Calcul de la valeur globale du portefeuille
    c.execute("SELECT cash FROM users WHERE username=?", (user,))
    cash_actuel = c.fetchone()[0]
    
    c.execute("SELECT ticker, shares FROM portfolio WHERE username=?", (user,))
    positions = c.fetchall()
    
    valeur_actions = sum((obtenir_prix_actuel(tk) or 0) * sh for tk, sh in positions)
    valeur_totale = cash_actuel + valeur_actions
    profit_total = valeur_totale - 10000.00
    rendement_pct = (profit_total / 10000.00) * 100

    # Cartes de performance globales
    col_m1, col_m2, col_m3, col_m4 = st.columns(4)
    col_m1.metric("Cash Disponible", f"${cash_actuel:,.2f}")
    col_m2.metric("Valeur des Actifs", f"${valeur_actions:,.2f}")
    col_m3.metric("Portefeuille Total", f"${valeur_totale:,.2f}")
    col_m4.metric("Gain / Perte", f"${profit_total:,.2f}", f"{rendement_pct:+.2f}%")

    st.markdown("<hr>", unsafe_allow_html=True)

    # STRUCTURE PAR ONGLETS
    tab_trade, tab_port, tab_rank = st.tabs(["Analyse & Ordres", "Mon Portefeuille", "Classement général"])

    # --- ONGLET 1 : ANALYSE & ORDRES ---
    with tab_trade:
        col_m, col_s, col_q = st.columns([2, 2, 2])
        marche = col_m.selectbox("Marché financier", ["États-Unis (NYSE/NASDAQ)", "Canada (TSX)"])
        raw_symbol = col_s.text_input("Symbole de l'action", "AAPL").strip().upper()
        qty = col_q.number_input("Nombre d'actions", min_value=1, step=1)

        symbol = f"{raw_symbol}.TO" if "Canada" in marche and not (raw_symbol.endswith(".TO") or raw_symbol.endswith(".V")) else raw_symbol

        if symbol:
            prix = obtenir_prix_actuel(symbol)
            details = obtenir_details_financiers(symbol)

            if prix and details:
                st.markdown("<br>", unsafe_allow_html=True)
                
                # Barre d'en-tête de l'action
                col_t1, col_t2 = st.columns([3, 1])
                col_t1.markdown(f"<h2 style='margin:0;'>{symbol}</h2>", unsafe_allow_html=True)
                col_t2.markdown(f"<h2 style='margin:0; text-align:right; color:#58A6FF;'>${prix:,.2f}</h2>", unsafe_allow_html=True)

                # Sélecteur de période du graphique
                col_p1, col_p2 = st.columns([4, 1])
                periode_choisie = col_p2.selectbox("Horizon temporel", ["1m", "3m", "6m", "1y"], format_func=lambda x: {"1m": "1 Mois", "3m": "3 Mois", "6m": "6 Mois", "1y": "1 An"}[x])

                # Graphique interactif Plotly
                df_hist = obtenir_historique(symbol, periode_choisie)
                if df_hist is not None and not df_hist.empty:
                    fig = make_subplots(rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.03, row_heights=[0.75, 0.25])

                    # Courbe principale de prix
                    fig.add_trace(go.Scatter(
                        x=df_hist.index, 
                        y=df_hist['Close'], 
                        mode='lines', 
                        name='Prix', 
                        line=dict(color='#00E676', width=2),
                        fill='tonexty',
                        fillcolor='rgba(0, 230, 118, 0.05)'
                    ), row=1, col=1)

                    # Histogramme des volumes
                    colors_vol = ['#00E676' if row['Open'] <= row['Close'] else '#FF5252' for _, row in df_hist.iterrows()]
                    fig.add_trace(go.Bar(
                        x=df_hist.index, 
                        y=df_hist['Volume'], 
                        name='Volume',
                        marker_color=colors_vol,
                        opacity=0.5
                    ), row=2, col=1)

                    fig.update_layout(
                        paper_bgcolor='rgba(0,0,0,0)',
                        plot_bgcolor='rgba(0,0,0,0)',
                        margin=dict(l=10, r=10, t=10, b=10),
                        height=380,
                        showlegend=False,
                        font=dict(color='#8B949E'),
                        xaxis_rangeslider_visible=False
                    )
                    fig.update_xaxes(showgrid=True, gridcolor='#212635')
                    fig.update_yaxes(showgrid=True, gridcolor='#212635')

                    st.plotly_chart(fig, use_container_width=True)

                # Tableau des indicateurs financiers
                st.markdown("### Données de marché")
                df_details = pd.DataFrame(list(details.items()), columns=["Métrique", "Valeur"])
                st.dataframe(df_details, use_container_width=True, hide_index=True)

                st.markdown("<hr>", unsafe_allow_html=True)
                
                # Panneau d'exécution des ordres
                col_b, col_s = st.columns(2)
                cost_total = prix * qty

                if col_b.button(f"Acheter {qty} action(s) pour ${cost_total:,.2f}", use_container_width=True):
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

                if col_s.button(f"Vendre {qty} action(s) pour ${cost_total:,.2f}", use_container_width=True):
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
                st.warning("Symbole introuvable sur le marché sélectionné.")

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
                    "Action": t,
                    "Quantité": s,
                    "Prix d'Achat Moyen": f"${p_moyen:,.2f}",
                    "Prix du Marché": f"${p_actuel:,.2f}",
                    "Valeur Totale": f"${val_tot:,.2f}",
                    "Plus/Moins-Value": f"${pnl:+,.2f}",
                    "Rendement": f"{pnl_pct:+.2f}%"
                })
            st.dataframe(pd.DataFrame(data_p), use_container_width=True, hide_index=True)
        else:
            st.info("Aucun actif détenu actuellement.")

    # --- ONGLET 3 : CLASSEMENT ---
    with tab_rank:
        st.markdown("### Classement de la classe")
        
        c.execute("SELECT username, cash FROM users")
        all_users = c.fetchall()
        
        leaderboard = []
        for u, c_val in all_users:
            c.execute("SELECT ticker, shares FROM portfolio WHERE username=?", (u,))
            u_pos = c.fetchall()
            u_actions_val = sum((obtenir_prix_actuel(tk) or 0) * sh for tk, sh in u_pos)
            tot = c_val + u_actions_val
            perf = ((tot - 10000.00) / 10000.00) * 100
            leaderboard.append({"Rang": 0, "Élève": u, "Portefeuille ($)": tot, "Performance (%)": perf})

        df_lb = pd.DataFrame(leaderboard).sort_values(by="Portefeuille ($)", ascending=False).reset_index(drop=True)
        df_lb["Rang"] = df_lb.index + 1
        
        df_lb["Portefeuille ($)"] = df_lb["Portefeuille ($)"].map("${:,.2f}".format)
        df_lb["Performance (%)"] = df_lb["Performance (%)"].map("{:+.2f}%".format)
        
        st.dataframe(df_lb[["Rang", "Élève", "Portefeuille ($)", "Performance (%)"]], use_container_width=True, hide_index=True)
