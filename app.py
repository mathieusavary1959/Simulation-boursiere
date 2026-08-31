import streamlit as st
import yfinance as yf
import sqlite3
import pandas as pd

# --- CONFIGURATION PAGE ET BASE DE DONNÉES ---
st.set_page_config(page_title="Simulateur Boursier École", layout="wide")

conn = sqlite3.connect('bourse_ecole.db', check_same_thread=False)
c = conn.cursor()

c.execute('''CREATE TABLE IF NOT EXISTS users 
             (username TEXT PRIMARY KEY, password TEXT, cash REAL)''')
c.execute('''CREATE TABLE IF NOT EXISTS portfolio 
             (username TEXT, ticker TEXT, shares INTEGER, PRIMARY KEY(username, ticker))''')
conn.commit()

# --- SYSTEME DE CACHE POUR ÉVITER LES BLOCAGES ---
@st.cache_data(ttl=60)  # Récupère le prix une fois par minute max pour toute la classe
def obtenir_prix(ticker_symbol):
    try:
        data = yf.Ticker(ticker_symbol)
        prix = data.fast_info['lastPrice']
        return round(prix, 2)
    except Exception:
        return None

# --- GESTION DE LA SESSION ---
if 'user' not in st.session_state:
    st.session_state['user'] = None

st.title("📈 Simulateur Boursier Indépendant")

# --- INTERFACE DE CONNEXION / INSCRIPTION ---
if st.session_state['user'] is None:
    tab1, tab2 = st.tabs(["Connexion", "Créer un compte"])
    
    with tab1:
        u_login = st.text_input("Nom d'utilisateur")
        p_login = st.text_input("Mot de passe", type="password")
        if st.button("Se connecter"):
            c.execute("SELECT * FROM users WHERE username=? AND password=?", (u_login, p_login))
            if c.fetchone():
                st.session_state['user'] = u_login
                st.rerun()
            else:
                st.error("Identifiants incorrects.")

    with tab2:
        u_new = st.text_input("Choisir un nom d'utilisateur")
        p_new = st.text_input("Choisir un mot de passe", type="password")
        if st.button("S'inscrire"):
            try:
                c.execute("INSERT INTO users VALUES (?, ?, 10000.00)", (u_new, p_new))
                conn.commit()
                st.success("Compte créé avec succès ! Connecte-toi maintenant.")
            except sqlite3.IntegrityError:
                st.error("Ce nom d'utilisateur existe déjà.")

else:
    # --- TABLEAU DE BORD DE L'ÉLÈVE ---
    user = st.session_state['user']
    
    # Barre supérieure avec bouton déconnexion
    col_head1, col_head2 = st.columns([4, 1])
    col_head1.write(f"### Bienvenue, **{user}** 👋")
    if col_head2.button("Se déconnecter"):
        st.session_state['user'] = None
        st.rerun()

    # Solde de l'élève
    c.execute("SELECT cash FROM users WHERE username=?", (user,))
    cash = c.fetchone()[0]
    
    st.metric("Solde Cash Disponible", f"{cash:,.2f} $")

    # SECTION 1 : RECHERCHE ET PASSAGE D'ORDRES
    st.write("---")
    st.subheader("Passer un ordre sur le marché")
    
    col_ticker, col_qty, col_action = st.columns([2, 2, 2])
    symbol = col_ticker.text_input("Symbole de l'action (ex: AAPL, TSLA, NVDA, MSFT)", "AAPL").upper()
    qty = col_qty.number_input("Quantité d'actions", min_value=1, step=1)
    
    prix_actuel = obtenir_prix(symbol)
    
    if prix_actuel:
        st.info(f"Cours en direct de **{symbol}** : **{prix_actuel} $** | Coût total : **{prix_actuel * qty:,.2f} $**")
        
        col_buy, col_sell = st.columns(2)
        
        # Action : ACHETER
        if col_buy.button("Acheter", use_container_width=True):
            cout_total = prix_actuel * qty
            if cash >= cout_total:
                # Déduire du cash
                nouveau_cash = cash - cout_total
                c.execute("UPDATE users SET cash=? WHERE username=?", (nouveau_cash, user))
                
                # Mettre à jour le portefeuille
                c.execute("SELECT shares FROM portfolio WHERE username=? AND ticker=?", (user, symbol))
                row = c.fetchone()
                if row:
                    c.execute("UPDATE portfolio SET shares=? WHERE username=? AND ticker=?", (row[0] + qty, user, symbol))
                else:
                    c.execute("INSERT INTO portfolio VALUES (?, ?, ?)", (user, symbol, qty))
                
                conn.commit()
                st.success(f"Achat de {qty} x {symbol} effectué !")
                st.rerun()
            else:
                st.error("Solde en cash insuffisant !")
                
        # Action : VENDRE
        if col_sell.button("Vendre", use_container_width=True):
            c.execute("SELECT shares FROM portfolio WHERE username=? AND ticker=?", (user, symbol))
            row = c.fetchone()
            if row and row[0] >= qty:
                gain_total = prix_actuel * qty
                nouveau_cash = cash + gain_total
                c.execute("UPDATE users SET cash=? WHERE username=?", (nouveau_cash, user))
                
                nouvelles_actions = row[0] - qty
                if nouvelles_actions > 0:
                    c.execute("UPDATE portfolio SET shares=? WHERE username=? AND ticker=?", (nouvelles_actions, user, symbol))
                else:
                    c.execute("DELETE FROM portfolio WHERE username=? AND ticker=?", (user, symbol))
                
                conn.commit()
                st.success(f"Vente de {qty} x {symbol} effectuée !")
                st.rerun()
            else:
                st.error("Tu ne possèdes pas assez d'actions pour cette vente !")
    else:
        st.warning("Symbole introuvable ou erreur de connexion au marché.")

    # SECTION 2 : AFFICHAGE DU PORTEFEUILLE
    st.write("---")
    st.subheader("Ton Portefeuille Actuel")
    
    df_portfolio = pd.read_sql_query("SELECT ticker as Action, shares as Quantité FROM portfolio WHERE username=?", conn, params=(user,))
    
    if not df_portfolio.empty:
        # Calcul de la valeur actuelle
        valeurs_actuelles = []
        for index, row in df_portfolio.iterrows():
            p = obtenir_prix(row['Action']) or 0
            valeurs_actuelles.append(round(p * row['Quantité'], 2))
        
        df_portfolio['Valeur Totale ($)'] = valeurs_actuelles
        st.dataframe(df_portfolio, use_container_width=True)
    else:
        st.write("Tu ne possèdes aucune action pour le moment.")
