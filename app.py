from datetime import datetime
from zoneinfo import ZoneInfo
import pandas as pd
import sqlalchemy as sa
import streamlit as st
import streamlit.components.v1 as components
import yfinance as yf
from sqlalchemy import text

# --- CONFIGURATION DE LA PAGE ---
st.set_page_config(
    page_title="Portefeuille Boursier — Monde & Finance",
    page_icon="📈",
    layout="wide",
)

# --- CONNEXION BASE DE DONNÉES ---
conn = st.connection("sqlite", type="sql", url="sqlite:///portfolio.db")


# --- INITIALISATION DE LA BASE DE DONNÉES ---
def init_db():
    with conn.session as session:
        session.execute(
            text(
                """
            CREATE TABLE IF NOT EXISTS users (
                username TEXT PRIMARY KEY,
                group_name TEXT,
                cash REAL DEFAULT 10000.0
            );
        """
            )
        )
        session.execute(
            text(
                """
            CREATE TABLE IF NOT EXISTS portfolio (
                username TEXT,
                ticker TEXT,
                shares INTEGER,
                avg_price REAL,
                PRIMARY KEY (username, ticker)
            );
        """
            )
        )
        session.execute(
            text(
                """
            CREATE TABLE IF NOT EXISTS transactions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT,
                ticker TEXT,
                type TEXT,
                shares INTEGER,
                price REAL,
                total REAL,
                timestamp TEXT
            );
        """
            )
        )
        # Utilisateur démo par défaut
        session.execute(
            text(
                """
            INSERT OR IGNORE INTO users (username, group_name, cash)
            VALUES ('Élève Démo', 'Groupe 101', 10000.0)
        """
            )
        )
        session.commit()


init_db()


# --- FONCTION DE RÉCUPÉRATION DU PRIX ---
@st.cache_data(ttl=5)
def obtenir_prix_actuel(ticker: str) -> float:
    try:
        data = yf.Ticker(ticker).fast_info
        prix = data.last_price
        if prix is None or pd.isna(prix):
            hist = yf.Ticker(ticker).history(period="1d")
            if not hist.empty:
                prix = hist["Close"].iloc[-1]
        return float(prix) if prix else 0.0
    except Exception:
        return 0.0


# --- SESSION UTILISATEUR ---
if "user" not in st.session_state:
    st.session_state["user"] = "Élève Démo"

user = st.session_state["user"]

# Récupération des infos utilisateur
user_df = conn.query(
    "SELECT group_name, cash FROM users WHERE username=:u",
    params={"u": user},
    ttl=0,
)
if not user_df.empty:
    groupe_actuel = user_df.iloc[0]["group_name"]
    cash_actuel = float(user_df.iloc[0]["cash"])
else:
    groupe_actuel = "Groupe 101"
    cash_actuel = 10000.0

# --- EN-TÊTE PRINCIPAL ---
st.title("📈 Portefeuille Boursier — Monde & Finance")
st.caption(f"👤 Connecté en tant que **{user}** ({groupe_actuel})")

# --- NAVIGATION ONGLETS ---
tab_buy, tab_port, tab_hist, tab_lead = st.tabs(
    [
        "🛒 Acheter des Actions",
        "💼 Mes Positions",
        "📜 Historique",
        "🏆 Classement",
    ]
)

# ==============================================================================
# ONGLET 1 : ACHETER DES ACTIONS
# ==============================================================================
with tab_buy:
    st.markdown("### 🔍 Rechercher & Acheter une Action")

    col_s1, col_s2 = st.columns([2, 1])
    with col_s1:
        ticker_input = (
            st.text_input("Symbole du Ticker (ex: AAPL, MSFT, GOOG, TSLA) :", "AAPL")
            .strip()
            .upper()
        )

    if ticker_input:
        prix_actuel_buy = obtenir_prix_actuel(ticker_input)

        if prix_actuel_buy > 0:
            st.success(
                f"Prix actuel de **{ticker_input}** : **${prix_actuel_buy:,.2f} USD**"
            )

            col_b1, col_b2, col_b3 = st.columns([1, 1, 1])
            with col_b1:
                st.metric("Solde Disponible (Cash)", f"${cash_actuel:,.2f}")
            with col_b2:
                qte_achat = st.number_input(
                    "Quantité à acheter :", min_value=1, value=1, step=1
                )
            with col_b3:
                cout_total = qte_achat * prix_actuel_buy
                st.metric("Coût Total", f"${cout_total:,.2f}")

            if st.button("🛒 Confirmer l'Achat", use_container_width=True):
                if cash_actuel >= cout_total:
                    now_str = datetime.now(
                        ZoneInfo("America/Toronto")
                    ).strftime("%Y-%m-%d %H:%M:%S")
                    with conn.session as session:
                        # Mettre à jour le cash
                        session.execute(
                            text(
                                "UPDATE users SET cash = cash - :cost WHERE username = :u"
                            ),
                            {"cost": cout_total, "u": user},
                        )

                        # Mettre à jour le portefeuille
                        existing = session.execute(
                            text(
                                "SELECT shares, avg_price FROM portfolio WHERE username=:u AND ticker=:t"
                            ),
                            {"u": user, "t": ticker_input},
                        ).fetchone()

                        if existing:
                            old_sh, old_pm = existing[0], existing[1]
                            new_sh = old_sh + qte_achat
                            new_pm = (
                                (old_sh * old_pm) + (qte_achat * prix_actuel_buy)
                            ) / new_sh
                            session.execute(
                                text(
                                    "UPDATE portfolio SET shares=:s, avg_price=:p WHERE username=:u AND ticker=:t"
                                ),
                                {
                                    "s": new_sh,
                                    "p": new_pm,
                                    "u": user,
                                    "t": ticker_input,
                                },
                            )
                        else:
                            session.execute(
                                text(
                                    "INSERT INTO portfolio (username, ticker, shares, avg_price) VALUES (:u, :t, :s, :p)"
                                ),
                                {
                                    "u": user,
                                    "t": ticker_input,
                                    "s": qte_achat,
                                    "p": prix_actuel_buy,
                                },
                            )

                        # Historique transaction
                        session.execute(
                            text(
                                "INSERT INTO transactions (username, ticker, type, shares, price, total, timestamp) VALUES (:u, :t, 'ACHAT', :s, :p, :tot, :time)"
                            ),
                            {
                                "u": user,
                                "t": ticker_input,
                                "s": qte_achat,
                                "p": prix_actuel_buy,
                                "tot": cout_total,
                                "time": now_str,
                            },
                        )
                        session.commit()

                    st.success(
                        f"Achat effectué avec succès ! {qte_achat} action(s) {ticker_input} acquise(s)."
                    )
                    st.rerun()
                else:
                    st.error(
                        "Fonds insuffisants pour réaliser cette transaction."
                    )
        else:
            st.error(
                f"Impossible de récupérer le prix pour le ticker '{ticker_input}'. Vérifiez le symbole."
            )

# ==============================================================================
# ONGLET 2 : POSITIONS ET IMPRESSION PRO (RAFRAÎCHISSEMENT AUTO TOUTES LES 5S)
# ==============================================================================
with tab_port:
    st.markdown(
        """
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
    """,
        unsafe_allow_html=True,
    )

    # COMPOSANT DES POSITIONS MIS À JOUR EN TEMPS RÉEL (TOUTES LES 5 SECONDES)
    @st.fragment(run_every="5s")
    def afficher_positions_live():
        pos_df_live = conn.query(
            "SELECT ticker, shares FROM portfolio WHERE username=:u",
            params={"u": user},
            ttl=0,
        )
        val_actions_live = sum(
            (obtenir_prix_actuel(row["ticker"]) or 0) * row["shares"]
            for _, row in pos_df_live.iterrows()
        )
        val_totale_live = cash_actuel + val_actions_live
        prof_total_live = val_totale_live - 10000.00
        rend_pct_live = (prof_total_live / 10000.00) * 100

        # Heure exacte du rafraîchissement
        heure_actualisation = datetime.now(
            ZoneInfo("America/Toronto")
        ).strftime("%H:%M:%S")
        date_impression = datetime.now(ZoneInfo("America/Toronto")).strftime(
            "%d/%m/%Y à %H:%M"
        )
        pnl_color_print = "#10B981" if prof_total_live >= 0 else "#EF4444"

        # EN-TÊTE DÉDIÉ IMPRESSION
        st.markdown(
            f"""
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
        """,
            unsafe_allow_html=True,
        )

        col_p1, col_p2 = st.columns([3, 1])
        with col_p1:
            st.markdown(
                f"""
                ### Mes Positions Actuelles 
                <span style='font-size:0.8rem; color:#10B981; font-weight:600; background:#E6F4EA; padding:4px 12px; border-radius:20px; border:1px solid #A7F3D0; vertical-align:middle; margin-left:8px;'>
                    🟢 Prix & Valeurs en direct ({heure_actualisation})
                </span>
            """,
                unsafe_allow_html=True,
            )
        with col_p2:
            components.html(
                """
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
            """,
                height=45,
            )

        p_all = conn.query(
            "SELECT ticker, shares, avg_price FROM portfolio WHERE username=:u",
            params={"u": user},
            ttl=0,
        )
        if not p_all.empty:
            options_vente = {}
            html_rows = ""

            for _, r in p_all.iterrows():
                tk, sh, pm = (
                    str(r["ticker"]),
                    int(r["shares"]),
                    float(r["avg_price"] or 0.0),
                )

                # Prix actuel recalculé toutes les 5 secondes
                pa = obtenir_prix_actuel(tk) or 0.0
                pm = pm or pa
                val = sh * pa
                pnl = (pa - pm) * sh
                pnl_pct = ((pa - pm) / pm * 100) if pm > 0 else 0

                pnl_color = "#10B981" if pnl >= 0 else "#EF4444"
                options_vente[f"{tk} ({sh} action(s) disponible(s))"] = (
                    tk,
                    sh,
                    pa,
                )

                html_rows += f"<tr><td><b>{tk}</b></td><td>{sh}</td><td>${pm:,.2f}</td><td><b>${pa:,.2f}</b></td><td>${val:,.2f}</td><td style='color:{pnl_color}; font-weight:700;'>${pnl:+,.2f}</td><td style='color:{pnl_color}; font-weight:700;'>{pnl_pct:+.2f}%</td></tr>"

            table_html = f"<table class='custom-table'><thead><tr><th>Action</th><th>Quantité</th><th>Prix Moyen</th><th>Prix Actuel</th><th>Valeur</th><th>Gain / Perte</th><th>Rendement</th></tr></thead><tbody>{html_rows}</tbody></table>"
            st.markdown(table_html, unsafe_allow_html=True)

            st.markdown("<hr>", unsafe_allow_html=True)
            st.markdown("### 💸 Vendre rapidement mes positions")

            col_v1, col_v2, col_v3 = st.columns([2, 1, 1])
            with col_v1:
                choix_v = st.selectbox(
                    "Sélectionnez l'action à vendre :",
                    list(options_vente.keys()),
                )
                tk_v, max_sh, pa_v = options_vente[choix_v]
            with col_v2:
                qty_v = st.number_input(
                    "Quantité à vendre :",
                    min_value=1,
                    max_value=max_sh,
                    value=min(1, max_sh),
                    step=1,
                )
            with col_v3:
                st.markdown("<br>", unsafe_allow_html=True)
                total_vente = qty_v * pa_v
                if st.button(
                    f"Vendre pour ${total_vente:,.2f}", use_container_width=True
                ):
                    now_str = datetime.now(
                        ZoneInfo("America/Toronto")
                    ).strftime("%Y-%m-%d %H:%M:%S")
                    with conn.session as session:
                        session.execute(
                            text(
                                "UPDATE users SET cash = cash + :cost WHERE username = :u"
                            ),
                            {"cost": total_vente, "u": user},
                        )
                        rem = max_sh - qty_v
                        if rem > 0:
                            session.execute(
                                text(
                                    "UPDATE portfolio SET shares=:s WHERE username=:u AND ticker=:t"
                                ),
                                {"s": rem, "u": user, "t": tk_v},
                            )
                        else:
                            session.execute(
                                text(
                                    "DELETE FROM portfolio WHERE username=:u AND ticker=:t"
                                ),
                                {"u": user, "t": tk_v},
                            )
                        session.execute(
                            text(
                                "INSERT INTO transactions (username, ticker, type, shares, price, total, timestamp) VALUES (:u, :t, 'VENTE', :s, :p, :tot, :time)"
                            ),
                            {
                                "u": user,
                                "t": tk_v,
                                "s": qty_v,
                                "p": pa_v,
                                "tot": total_vente,
                                "time": now_str,
                            },
                        )
                        session.commit()
                    st.success(
                        f"Vente de {qty_v} action(s) {tk_v} confirmée !"
                    )
                    st.rerun()
        else:
            st.info("Vous n'avez aucune position ouverte actuellement.")

    afficher_positions_live()

# ==============================================================================
# ONGLET 3 : HISTORIQUE DES TRANSACTIONS
# ==============================================================================
with tab_hist:
    st.markdown("### 📜 Historique des Ordres")
    tx_df = conn.query(
        "SELECT timestamp as 'Date/Heure', type as 'Type', ticker as 'Ticker', shares as 'Quantité', price as 'Prix Unitaire ($)', total as 'Total ($)' FROM transactions WHERE username=:u ORDER BY id DESC",
        params={"u": user},
        ttl=0,
    )
    if not tx_df.empty:
        st.dataframe(tx_df, use_container_width=True)
    else:
        st.info("Aucune transaction enregistrée.")

# ==============================================================================
# ONGLET 4 : CLASSEMENT DU GROUPE
# ==============================================================================
with tab_lead:
    st.markdown(f"### 🏆 Classement Général — {groupe_actuel}")
    users_in_group = conn.query(
        "SELECT username, cash FROM users WHERE group_name=:g",
        params={"g": groupe_actuel},
        ttl=0,
    )

    leaderboard_data = []
    for _, u_row in users_in_group.iterrows():
        u_name = u_row["username"]
        u_cash = float(u_row["cash"])
        u_pos = conn.query(
            "SELECT ticker, shares FROM portfolio WHERE username=:u",
            params={"u": u_name},
            ttl=0,
        )

        u_val_actions = sum(
            (obtenir_prix_actuel(r["ticker"]) or 0) * r["shares"]
            for _, r in u_pos.iterrows()
        )
        u_val_totale = u_cash + u_val_actions
        u_profit = u_val_totale - 10000.0
        u_rendement = (u_profit / 10000.0) * 100

        leaderboard_data.append(
            {
                "Élève": u_name,
                "Cash ($)": f"${u_cash:,.2f}",
                "Valeur Actions ($)": f"${u_val_actions:,.2f}",
                "Valeur Totale ($)": f"${u_val_totale:,.2f}",
                "Profit/Perte ($)": f"${u_profit:+,.2f}",
                "Rendement (%)": f"{u_rendement:+.2f}%",
                "val_num": u_val_totale,
            }
        )

    if leaderboard_data:
        df_lead = pd.DataFrame(leaderboard_data).sort_values(
            by="val_num", ascending=False
        )
        df_lead = df_lead.drop(columns=["val_num"]).reset_index(drop=True)
        df_lead.index += 1  # Rang 1, 2, 3...
        st.dataframe(df_lead, use_container_width=True)
