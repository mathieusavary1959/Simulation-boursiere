# --- ONGLET 2 : POSITIONS ET IMPRESSION PRO (RAFRAÎCHISSEMENT AUTO TOUTES LES 5S) ---
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
        """, unsafe_allow_html=True)

        # COMPOSANT DES POSITIONS MIS À JOUR EN TEMPS RÉEL (TOUTES LES 5 SECONDES)
        @st.fragment(run_every="5s")
        def afficher_positions_live():
            pos_df_live = conn.query("SELECT ticker, shares FROM portfolio WHERE username=:u", params={"u": user}, ttl=0)
            val_actions_live = sum((obtenir_prix_actuel(row['ticker']) or 0) * row['shares'] for _, row in pos_df_live.iterrows())
            val_totale_live = cash_actuel + val_actions_live
            prof_total_live = val_totale_live - 10000.00
            rend_pct_live = (prof_total_live / 10000.00) * 100

            # Heure exacte du rafraîchissement
            heure_actualisation = datetime.now(ZoneInfo("America/Toronto")).strftime("%H:%M:%S")
            date_impression = datetime.now(ZoneInfo("America/Toronto")).strftime("%d/%m/%Y à %H:%M")
            pnl_color_print = "#10B981" if prof_total_live >= 0 else "#EF4444"

            # EN-TÊTE DÉDIÉ IMPRESSION
            st.markdown(f"""
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
            """, unsafe_allow_html=True)

            col_p1, col_p2 = st.columns([3, 1])
            with col_p1:
                # Ajout de l'indicateur visuel d'actualisation des prix
                st.markdown(f"""
                    ### Mes Positions Actuelles 
                    <span style='font-size:0.8rem; color:#10B981; font-weight:600; background:#E6F4EA; padding:4px 12px; border-radius:20px; border:1px solid #A7F3D0; vertical-align:middle; margin-left:8px;'>
                        🟢 Prix & Valeurs en direct ({heure_actualisation})
                    </span>
                """, unsafe_allow_html=True)
            with col_p2:
                components.html("""
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
                """, height=45)

            p_all = conn.query("SELECT ticker, shares, avg_price FROM portfolio WHERE username=:u", params={"u": user}, ttl=0)
            if not p_all.empty:
                options_vente = {}
                html_rows = ""

                for _, r in p_all.iterrows():
                    tk, sh, pm = str(r['ticker']), int(r['shares']), float(r['avg_price'] or 0.0)
                    
                    # Prix actuel recalculé toutes les 5 secondes
                    pa = obtenir_prix_actuel(tk) or 0.0
                    pm = pm or pa
                    val = sh * pa
                    pnl = (pa - pm) * sh
                    pnl_pct = ((pa - pm) / pm * 100) if pm > 0 else 0

                    pnl_color = "#10B981" if pnl >= 0 else "#EF4444"
                    options_vente[f"{tk} ({sh} action(s) disponible(s))"] = (tk, sh, pa)

                    html_rows += f"<tr><td><b>{tk}</b></td><td>{sh}</td><td>${pm:,.2f}</td><td><b>${pa:,.2f}</b></td><td>${val:,.2f}</td><td style='color:{pnl_color}; font-weight:700;'>${pnl:+,.2f}</td><td style='color:{pnl_color}; font-weight:700;'>{pnl_pct:+.2f}%</td></tr>"

                table_html = f"<table class='custom-table'><thead><tr><th>Action</th><th>Quantité</th><th>Prix Moyen</th><th>Prix Actuel</th><th>Valeur</th><th>Gain / Perte</th><th>Rendement</th></tr></thead><tbody>{html_rows}</tbody></table>"
                st.markdown(table_html, unsafe_allow_html=True)

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
                                session.execute(text("DELETE FROM portfolio WHERE username=:u AND ticker=:t"), {"s": rem, "u": user, "t": tk_v})
                            session.execute(text("INSERT INTO transactions (username, ticker, type, shares, price, total, timestamp) VALUES (:u, :t, 'VENTE', :s, :p, :tot, :time)"),
                                            {"u": user, "t": tk_v, "s": qty_v, "p": pa_v, "tot": total_vente, "time": now_str})
                            session.commit()
                        st.success(f"Vente de {qty_v} action(s) {tk_v} confirmée !")
                        st.rerun()
            else: st.info("Vous n'avez aucune position ouverte actuellement.")

        afficher_positions_live()
