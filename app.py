import streamlit as st
import yfinance as yf
import sqlite3
import pandas as pd
import plotly.graph_objects as go

# --- CONFIGURATION PAGE ---
st.set_page_config(page_title="Simulateur Boursier - Élèves", page_icon="📈", layout="wide")

# --- BASE DE DONNÉES ---
conn = sqlite3.connect('bourse_ecole.db', check_same_thread=False)
c = conn.cursor()

c.execute('''CREATE TABLE IF NOT EXISTS users 
             (username TEXT PRIMARY KEY, password TEXT, cash REAL)''')
c.execute('''CREATE TABLE IF NOT EXISTS portfolio 
             (username TEXT, ticker TEXT, shares INTEGER, avg_price REAL, PRIMARY KEY(username, ticker))''')
conn.commit()

# --- CACHE DES DONNÉES FINANCIÈRES ---
@st.cache_data(ttl=60)
def obtenir_prix_actuel(ticker_symbol):
    try:
        data = yf.Ticker(ticker_symbol)
        prix = data.fast_info['lastPrice']
        return round(float(prix), 2)
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

# --- HEADER PRINCIPAL ---
st.title("📈 Simulateur Boursier Éducatif")

# --- SYSTEME DE CONNEXION / INSCRIPTION ---
if st.session_state['user'] is None:
    col_centered = st.columns([1, 2, 1])[1]
    with col_centered:
        tab1, tab2 = st.tabs(["🔒 Connexion", "📝 Inscription"])
        
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
                    st.success("Compte créé ! Tu peux maintenant te connecter.")
                except sqlite3.IntegrityError:
                    st.error("Ce nom d'utilisateur est déjà pris.")

else:
    user = st.session_state['user']
    
    # Barre supérieure
    col_h1, col_h2 = st.columns([4, 1])
    col_h1.markdown(f"### Bienvenue, **{user}** 👋")
    if col_h2.button("Déconnexion", use_container_width=True):
        st.session_state['user'] = None
        st.rerun()

    # Métriques clés du joueur
    c.execute("SELECT cash FROM users WHERE username=?", (user,))
    cash_actuel = c.fetchone()[0]
    
    c.execute("SELECT ticker, shares FROM portfolio WHERE username=?", (user,))
    positions = c.fetchall()
    
    valeur_actions = 0.0
    for ticker, shares in positions:
        p = obtenir_prix_actuel(ticker) or 0
        valeur_actions += p * shares

    valeur_totale = cash_actuel + valeur_actions
    profit_total = valeur_totale - 10000.00
    rendement_pct = (profit_total / 10000.00) * 100

    col_m1, col_m2, col_m3, col_m4 = st.columns(4)
    col_m1.metric("Cash disponible", f"${cash_actuel:,.2f}")
    col_m2.metric("Valeur des actions", f"${valeur_actions:,.2f}")
    col_m3.metric("Valeur totale du portefeuille", f"${valeur_totale:,.2f}")
    col_m4.metric("Plus-value / Moins-value", f"${profit_total:,.2f}", f"{rendement_pct:+.2f}%")

    st.write("---")

    # NAVIGATION PAR ONGLETS
    tab_trade, tab_port, tab_rank = st.tabs(["💰 Passer un ordre", "💼 Mon Portefeuille", "🏆 Classement de la classe"])

    # ------------------ ONGLET 1 : TRADING ------------------
    with tab_trade:
        c_m, c_s, c_q = st.columns([2, 2, 2])
        marche = c_m.selectbox("Marché", ["🇺🇸 États-Unis (NYSE/NASDAQ)", "🇨🇦 Canada (TSX)"])
        raw_symbol = c_s.text_input("Symbole (ex: AAPL, NVDA, TD, SHOP)", "AAPL").strip().upper()
        qty = c_q.number_input("Quantité", min_value=1, step=1)

        symbol = f"{raw_symbol}.TO" if "Canada" in marche and not (raw_symbol.endswith(".TO") or raw_symbol.endswith(".V")) else raw_symbol

        if symbol:
            prix = obtenir_prix_actuel(symbol)
            if prix:
                st.subheader(f"Cours de {symbol} : **${prix:,.2f} USD/CAD**")
                
                # Graphique interactif des 30 derniers jours
                df_hist = obtenir_historique(symbol)
                if df_hist is not None and not df_hist.empty:
                    fig = go.Figure()
                    fig.add_trace(go.Scatter(x=df_hist.index, y=df_hist['Close'], mode='lines', name=symbol, line=dict(color='#00CC96', width=2)))
                    fig.update_layout(title=f"Évolution sur 30 jours ({symbol})", margin=dict(l=20, r=20, t=40, b=20), height=300)
                    st.plotly_chart(fig, use_container_width=True)

                col_b, col_s = st.columns(2)
                
                # ACHAT
                if col_b.button(f"🛒 Acheter {qty} action(s) pour ${(prix * qty):,.2f}", use_container_width=True):
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
                        st.success("Ordre d'achat exécuté !")
                        st.rerun()
                    else:
                        st.error("Cash insuffisant !")

                # VENTE
                if col_s.button(f"🏷️ Vendre {qty} action(s) pour ${(prix * qty):,.2f}", use_container_width=True):
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
                        st.success("Ordre de vente exécuté !")
                        st.rerun()
                    else:
                        st.error("Tu ne possèdes pas assez d'actions.")
            else:
                st.warning("Symbole non trouvé.")

    # ------------------ ONGLET 2 : PORTEFEUILLE ------------------
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
            st.dataframe(pd.DataFrame(data_p), use_container_width=True)
        else:
            st.info("Aucune position ouverte pour le moment.")

    # ------------------ ONGLET 3 : CLASSEMENT ------------------
    with tab_rank:
        st.subheader("🏆 Classement Général de la Classe")
        
        c.execute("SELECT username, cash FROM users")
        all_users = c.fetchall()
        
        leaderboard = []
        for u, c_val in all_users:
            c.execute("SELECT ticker, shares FROM portfolio WHERE username=?", (u,))
            u_pos = c.fetchall()
            u_actions_val = sum((obtenir_prix_actuel(tk) or 0) * sh for tk, sh in u_pos)
            tot = c_val + u_actions_val
            perf = ((tot - 10000.00) / 10000.00) * 100
            leaderboard.append({"Élève": u, "Valeur du Portefeuille ($)": tot, "Performance": perf})

        df_lb = pd.DataFrame(leaderboard).sort_values(by="Valeur du Portefeuille ($)", ascending=False).reset_index(drop=True)
        df_lb.index += 1  # Rang commence à 1
        
        df_lb["Valeur du Portefeuille ($)"] = df_lb["Valeur du Portefeuille ($)"].map("{:,.2f} $".format)
        df_lb["Performance"] = df_lb["Performance"].map("{:+.2f} %".format)
        
        st.table(df_lb)
