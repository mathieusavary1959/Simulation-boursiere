import streamlit as st
import yfinance as yf
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import xml.etree.ElementTree as ET
import requests
import uuid
import html
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from sqlalchemy import text
import streamlit.components.v1 as components

# --- LOGO DE LA SIMULATION (chandeliers rouges, choix de Mathieu, 31 oct. 2026) ---
try:
    import base64 as _b64_logo, io as _io_logo
    from PIL import Image as _ImageLogo
    from fond_data import LOGO_BOURSE_PNG_B64 as _LOGO_B64
    _ICONE_PAGE = _ImageLogo.open(_io_logo.BytesIO(_b64_logo.b64decode(_LOGO_B64)))
except Exception:
    _ICONE_PAGE = None

# --- PAGE DU JOURNAL DU KRACH (module genere depuis journal-krach-v7.html) ---
try:
    from krach_data import PAGE_KRACH_HTML
except Exception:
    PAGE_KRACH_HTML = ""

# --- CONFIGURATION DE LA PAGE ---
st.set_page_config(page_title="Monde & Finance — Simulation Boursière", layout="wide", page_icon=_ICONE_PAGE)

# --- MODE MAINTENANCE (activé le 21 oct. 2026 : problèmes techniques en classe) ---
# Pour rouvrir le site : passer à False et redéployer.
MODE_MAINTENANCE = False
if MODE_MAINTENANCE:
    st.markdown("""
    <style>
        @import url('https://fonts.googleapis.com/css2?family=Bebas+Neue&family=Work+Sans:wght@400;600;800&display=swap');
        .maint-wrap { max-width: 720px; margin: 9vh auto 0 auto; text-align: center; padding: 48px 32px; background: #141414; border: 1px solid #2b2b2b; border-top: 4px solid #E50914; border-radius: 14px; }
        .maint-marque { font-family: 'Bebas Neue', 'Arial Narrow', sans-serif; font-size: 64px; letter-spacing: 0.04em; color: #FFFFFF; line-height: 1; }
        .maint-marque span { color: #E50914; }
        .maint-titre { font-family: 'Work Sans', sans-serif; font-weight: 800; font-size: 26px; color: #FFFFFF; margin-top: 26px; }
        .maint-texte { font-family: 'Work Sans', sans-serif; font-size: 17px; color: #E8E8E8; line-height: 1.55; margin-top: 12px; }
    </style>
    <div class="maint-wrap">
        <div class="maint-marque">MONDE <span>&amp;</span> FINANCE</div>
        <div class="maint-titre">Site en maintenance</div>
        <div class="maint-texte">On corrige des problèmes techniques pour que le site fonctionne mieux.<br>Revenez un peu plus tard.</div>
        <div class="maint-texte">Vos comptes, vos positions et votre argent virtuel sont en sécurité : rien n'est perdu.</div>
    </div>
    """, unsafe_allow_html=True)
    st.stop()

# Liste des 10 groupes + Groupe Enseignants
LISTE_GROUPES = [f"Groupe {i}" for i in range(501, 511)] + ["Enseignants"]

# --- CONNEXION BASE DE DONNÉES CLOUD (SUPABASE) ---
conn = st.connection("postgres", type="sql")

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
                    shares INT,
                    price DOUBLE PRECISION,
                    total DOUBLE PRECISION,
                    timestamp TEXT
                );
            '''))
            session.execute(text('''
                CREATE TABLE IF NOT EXISTS sessions (
                    token TEXT PRIMARY KEY,
                    username TEXT,
                    created_at TEXT
                );
            '''))
            session.execute(text('''
                CREATE TABLE IF NOT EXISTS favoris (
                    username TEXT,
                    ticker TEXT,
                    PRIMARY KEY (username, ticker)
                );
            '''))
            session.execute(text('''
                CREATE TABLE IF NOT EXISTS groupes_fermes (
                    groupe TEXT PRIMARY KEY
                );
            '''))
            session.execute(text('''
                CREATE TABLE IF NOT EXISTS regles_vues (
                    username TEXT PRIMARY KEY,
                    version INT,
                    vue_le TEXT
                );
            '''))
            session.execute(text('''
                CREATE TABLE IF NOT EXISTS avis_correction (
                    username TEXT PRIMARY KEY,
                    sens TEXT,
                    vu_le TEXT
                );
            '''))
            session.execute(text('''
                CREATE TABLE IF NOT EXISTS frais (
                    id SERIAL PRIMARY KEY,
                    username TEXT,
                    type TEXT,
                    montant DOUBLE PRECISION,
                    details TEXT,
                    timestamp TEXT
                );
            '''))
            session.execute(text('''
                CREATE TABLE IF NOT EXISTS prix_geles (
                    ticker TEXT NOT NULL,
                    session TEXT NOT NULL,
                    prix_cad DOUBLE PRECISION NOT NULL,
                    capture_le TEXT,
                    PRIMARY KEY (ticker, session)
                );
            '''))
            session.execute(text('''
                CREATE TABLE IF NOT EXISTS titres_suspendus (
                    ticker TEXT PRIMARY KEY,
                    motif TEXT,
                    depuis TEXT
                );
            '''))
            session.execute(text('''
                CREATE TABLE IF NOT EXISTS joueurs_suspendus (
                    username TEXT PRIMARY KEY,
                    depuis TEXT,
                    motif TEXT
                );
            '''))
            session.execute(text('''
                CREATE TABLE IF NOT EXISTS ordres_en_attente (
                    id SERIAL PRIMARY KEY,
                    username TEXT,
                    ticker TEXT,
                    montant_cad DOUBLE PRECISION,
                    devise TEXT,
                    place_le TEXT,
                    session_execution TEXT,
                    statut TEXT,
                    prix_execution DOUBLE PRECISION,
                    shares INT,
                    execute_le TEXT,
                    note TEXT,
                    sens TEXT DEFAULT 'ACHAT',
                    parts INT,
                    avg_reserve DOUBLE PRECISION
                );
            '''))
            # Étape 2 (6 nov. 2026) : les ordres portent aussi les VENTES
            # en attente (sens, parts réservées, prix moyen à restaurer
            # si l'ordre est annulé). Colonnes ajoutées à la table
            # existante ; les ordres d'achat déjà là gardent sens NULL,
            # lu comme ACHAT partout.
            session.execute(text("ALTER TABLE ordres_en_attente ADD COLUMN IF NOT EXISTS sens TEXT DEFAULT 'ACHAT'"))
            session.execute(text("ALTER TABLE ordres_en_attente ADD COLUMN IF NOT EXISTS parts INT"))
            session.execute(text("ALTER TABLE ordres_en_attente ADD COLUMN IF NOT EXISTS avg_reserve DOUBLE PRECISION"))
            session.execute(text('''
                CREATE TABLE IF NOT EXISTS photos (
                    username TEXT PRIMARY KEY,
                    image TEXT,
                    maj TEXT
                );
            '''))
            session.execute(text('''
                CREATE TABLE IF NOT EXISTS prix_relais (
                    ticker TEXT PRIMARY KEY,
                    prix_natif DOUBLE PRECISION,
                    prev_natif DOUBLE PRECISION,
                    ouverture DOUBLE PRECISION,
                    haut DOUBLE PRECISION,
                    bas DOUBLE PRECISION,
                    haut52 DOUBLE PRECISION,
                    bas52 DOUBLE PRECISION,
                    devise TEXT,
                    maj TEXT
                );
            '''))
            session.execute(text('''
                CREATE TABLE IF NOT EXISTS historique_relais (
                    ticker TEXT,
                    jour TEXT,
                    o DOUBLE PRECISION,
                    h DOUBLE PRECISION,
                    l DOUBLE PRECISION,
                    c DOUBLE PRECISION,
                    v DOUBLE PRECISION,
                    PRIMARY KEY (ticker, jour)
                );
            '''))
            session.execute(text('''
                CREATE TABLE IF NOT EXISTS journal_connexions (
                    id SERIAL PRIMARY KEY,
                    username TEXT,
                    evenement TEXT,
                    ip TEXT,
                    agent TEXT,
                    cree_le TEXT
                );
            '''))
            session.execute(text('''
                CREATE TABLE IF NOT EXISTS krach_etat (
                    id INT PRIMARY KEY,
                    actif BOOLEAN,
                    declenche_le TEXT,
                    expire_le TEXT
                );
            '''))
            session.execute(text("INSERT INTO krach_etat (id, actif, declenche_le, expire_le) VALUES (1, FALSE, NULL, NULL) ON CONFLICT (id) DO NOTHING"))
            session.execute(text('''
                CREATE TABLE IF NOT EXISTS sauvegarde_krach (
                    lot TEXT,
                    table_nom TEXT,
                    username TEXT,
                    donnees TEXT
                );
            '''))
            session.execute(text('''
                CREATE TABLE IF NOT EXISTS depart_etape2 (
                    username TEXT PRIMARY KEY,
                    montant NUMERIC NOT NULL
                );
            '''))
            session.commit()
        except Exception:
            session.rollback()

init_db()

# --- TRACEUR DE SECURITE (faux comptes) : journal des inscriptions et connexions ---
def _entetes_connexion():
    """Adresse relaiee et navigateur de la requete courante. Ne leve jamais
    d'exception. CONCLUSION MESUREE le 2 nov. 2026 : Streamlit Cloud ne transmet
    a l'application que des adresses INTERNES (chaine xff du type
    10.12.129.5, 10.20.70.2 ; aucun en-tete cf/tci/fwd/real). La vraie adresse
    du visiteur n'est donc PAS accessible ici ; la valeur stockee dans la
    colonne ip est l'adresse interne de la plateforme, conservee au cas ou
    l'hebergeur changerait son comportement. Ce qui identifie utilement une
    connexion : l'heure exacte et le navigateur (Chrome OS = chariot de
    Chromebooks, Windows = tour de laboratoire)."""
    try:
        h = st.context.headers
        ip = ""
        for cle in ("X-Forwarded-For", "x-forwarded-for", "X-Real-Ip", "x-real-ip"):
            val = h.get(cle)
            if val:
                ip = str(val).split(",")[0].strip()
                break
        ua = h.get("User-Agent") or h.get("user-agent") or ""
        return ip, str(ua)
    except Exception:
        return "", ""

def journaliser_connexion(nom_utilisateur, evenement):
    """Inscrit une inscription ou une connexion dans journal_connexions (IP + appareil).
    Silencieux : un echec de journalisation ne bloque jamais l'acces."""
    try:
        ip, ua = _entetes_connexion()
        heure = datetime.now(ZoneInfo("America/Toronto")).strftime("%Y-%m-%d %H:%M:%S")
        with conn.session as s:
            s.execute(text("INSERT INTO journal_connexions (username, evenement, ip, agent, cree_le) VALUES (:u, :e, :ip, :a, :t)"),
                      {"u": nom_utilisateur, "e": evenement, "ip": ip, "a": ua[:500], "t": heure})
            s.commit()
    except Exception:
        pass

# --- KRACH BOURSIER (16 novembre 2026) : reset complet + page du journal ---
KRACH_EXEMPT_UTILISATEUR = "MathieuSavary"
KRACH_EXEMPT_GROUPE = "Enseignants"

def krach_fin_fenetre(declenche):
    """La page du journal reste en place jusqu'au minuit (Toronto) suivant le declenchement."""
    lendemain = declenche.date() + timedelta(days=1)
    return datetime(lendemain.year, lendemain.month, lendemain.day, tzinfo=ZoneInfo("America/Toronto"))

@st.cache_data(ttl=20)
def _krach_etat_lu():
    try:
        df = conn.query("SELECT actif, declenche_le, expire_le FROM krach_etat WHERE id=1", ttl=0)
        if df.empty:
            return None
        r = df.iloc[0]
        return {"actif": bool(r["actif"]), "declenche_le": r["declenche_le"], "expire_le": r["expire_le"]}
    except Exception:
        return None

def krach_est_actif():
    etat = _krach_etat_lu()
    if not etat or not etat["actif"]:
        return False
    try:
        expire = datetime.strptime(etat["expire_le"], "%Y-%m-%d %H:%M:%S").replace(tzinfo=ZoneInfo("America/Toronto"))
    except Exception:
        return False
    if datetime.now(ZoneInfo("America/Toronto")) >= expire:
        try:
            with conn.session as s:
                s.execute(text("UPDATE krach_etat SET actif=FALSE WHERE id=1"))
                s.commit()
            _krach_etat_lu.clear()
        except Exception:
            pass
        return False
    return True

def apercu_krach():
    """Volumes touches par le reset (comptes non exemptes seulement)."""
    p = {"prof": KRACH_EXEMPT_UTILISATEUR, "grp": KRACH_EXEMPT_GROUPE}
    cond = "u.username <> :prof AND u.groupe <> :grp"
    def _n(q):
        df = conn.query(q, params=p, ttl=0)
        return int(df.iloc[0]["n"]) if not df.empty else 0
    return {
        "comptes": _n(f"SELECT COUNT(*) AS n FROM users u WHERE {cond}"),
        "positions": _n(f"SELECT COUNT(*) AS n FROM portfolio x JOIN users u ON u.username = x.username WHERE {cond}"),
        "transactions": _n(f"SELECT COUNT(*) AS n FROM transactions x JOIN users u ON u.username = x.username WHERE {cond}"),
        "ordres": _n(f"SELECT COUNT(*) AS n FROM ordres_en_attente x JOIN users u ON u.username = x.username WHERE {cond} AND x.statut = 'en_attente'"),
    }

def executer_krach():
    """Sauvegarde complete des comptes touches (table sauvegarde_krach), puis reset a
    10 000 $ et activation de la page du journal jusqu'a minuit. Exemptes : le compte
    de Mathieu et le groupe Enseignants (donc le compte du robot de surveillance)."""
    import json as _json
    tz = ZoneInfo("America/Toronto")
    maintenant = datetime.now(tz)
    lot = maintenant.strftime("krach-%Y%m%d-%H%M%S")
    expire = krach_fin_fenetre(maintenant).strftime("%Y-%m-%d %H:%M:%S")
    p = {"prof": KRACH_EXEMPT_UTILISATEUR, "grp": KRACH_EXEMPT_GROUPE}
    cond = "u.username <> :prof AND u.groupe <> :grp"
    try:
        df_dep = conn.query("SELECT username, montant FROM depart_etape2", ttl=0)
        departs_speciaux = [(str(r["username"]), float(r["montant"])) for _, r in df_dep.iterrows()]
    except Exception:
        departs_speciaux = []
    with conn.session as s:
        requetes = {
            "users": f"SELECT u.* FROM users u WHERE {cond}",
            "portfolio": f"SELECT x.* FROM portfolio x JOIN users u ON u.username = x.username WHERE {cond}",
            "transactions": f"SELECT x.* FROM transactions x JOIN users u ON u.username = x.username WHERE {cond}",
            "frais": f"SELECT x.* FROM frais x JOIN users u ON u.username = x.username WHERE {cond}",
            "ordres_en_attente": f"SELECT x.* FROM ordres_en_attente x JOIN users u ON u.username = x.username WHERE {cond}",
            "avis_correction": f"SELECT x.* FROM avis_correction x JOIN users u ON u.username = x.username WHERE {cond}",
        }
        total_lignes = 0
        for table_nom, q in requetes.items():
            for lig in s.execute(text(q), p).mappings().all():
                d = dict(lig)
                s.execute(text("INSERT INTO sauvegarde_krach (lot, table_nom, username, donnees) VALUES (:lot, :t, :u, :d)"),
                          {"lot": lot, "t": table_nom, "u": d.get("username"), "d": _json.dumps(d, default=str)})
                total_lignes += 1
        for table_nom in ("portfolio", "transactions", "frais", "ordres_en_attente", "avis_correction", "sessions"):
            s.execute(text(f"DELETE FROM {table_nom} WHERE username IN (SELECT username FROM users WHERE username <> :prof AND groupe <> :grp)"), p)
        s.execute(text("UPDATE users SET cash = 10000.0 WHERE username <> :prof AND groupe <> :grp"), p)
        for nom_dep, montant_dep in departs_speciaux:
            s.execute(text("UPDATE users SET cash = :m WHERE username = :u AND username <> :prof AND groupe <> :grp"),
                      {"m": montant_dep, "u": nom_dep, "prof": p["prof"], "grp": p["grp"]})
        s.execute(text("UPDATE krach_etat SET actif=TRUE, declenche_le=:d, expire_le=:e WHERE id=1"),
                  {"d": maintenant.strftime("%Y-%m-%d %H:%M:%S"), "e": expire})
        s.commit()
    _krach_etat_lu.clear()
    return lot, total_lignes, expire

def terminer_krach():
    with conn.session as s:
        s.execute(text("UPDATE krach_etat SET actif=FALSE WHERE id=1"))
        s.commit()
    _krach_etat_lu.clear()

def afficher_page_krach():
    st.markdown("""
    <style>
      #MainMenu, header, footer, section[data-testid="stSidebar"] { display: none !important; }
      .block-container { padding-top: 0 !important; }
    </style>
    """, unsafe_allow_html=True)
    if PAGE_KRACH_HTML:
        st.markdown(PAGE_KRACH_HTML, unsafe_allow_html=True)
    else:
        st.markdown("## Krash boursier\nLa Bourse est fermée pour la journée. Tout recommence mardi 17 novembre à 0 h 00 : chaque compte repart à 10 000 $.")

# --- FENETRE OBLIGATOIRE DES REGLES DU JEU (1 seule fois par version) ---
VERSION_REGLES = 5

@st.dialog("Étape 2 : les règles du jeu")
def afficher_popup_regles(username):
    st.markdown(
        "**Lis ça une fois. Après, tu ne pourras plus dire que tu ne savais pas.**\n\n"
        "**ÉTAPE 2 : ON REPART À ZÉRO**\n\n"
        "Tous les comptes repartent à 10 000 $. Voici les règles complètes de l'étape 2. "
        "Elles sont annoncées dès le départ et elles ne changeront pas en cours de route : "
        "pas de surprise, pas de nouvelle règle en plein milieu de l'étape.\n\n"
        "**LES BALISES DU MARCHÉ**\n"
        "1. Le marché ouvre à 9 h 30 et ferme à 16 h ; en dehors, on prépare des ordres, on ne transige pas.\n"
        "2. Un ordre préparé à l'avance s'exécute à l'ouverture, au prix d'ouverture, le même pour tout le monde.\n"
        "3. Chaque achat vaut entre 2 % et 25 % de ton compte.\n"
        "4. Maximum 5 achats par jour. Le marché sera encore là demain.\n"
        "5. Un titre acheté se garde au moins 30 minutes, 1 h pour un fonds (ETF).\n"
        "6. Si un titre bouge de plus de 30 % dans une journée, ses achats s'arrêtent jusqu'au lendemain.\n"
        "7. Vrais frais : 10 $, conversion sur les titres américains, 0,5 % de gestion le 1er du mois.\n"
        "8. Ce qui est inscrit est final. Un bogue n'est pas un gain.\n\n"
        "Et voici le détail, point par point :\n\n"
        "**1. La bourse a des heures : 9 h 30 à 16 h.**\n"
        "Les transactions se font pendant la séance seulement. En dehors des heures, tu peux placer un ordre, pour un achat comme pour une vente : il s'exécute à l'ouverture de la prochaine séance, au prix d'ouverture. Tu peux annuler un ordre tant qu'il est en attente. "
        "*En vrai, personne n'achète une action à 21 h au prix de la fermeture de 16 h.*\n\n"
        "**2. Détention minimale : 30 minutes pour une action, 1 h pour un ETF.**\n"
        "*Acheter et revendre deux minutes plus tard sans réfléchir, ce n'est pas investir.*\n\n"
        "**3. Chaque achat vaut entre 2 % et 25 % de la valeur de ton compte.**\n"
        "*Fini les positions décorations achetées avec de la petite monnaie pour cocher une case, et aucun vrai conseiller ne te laisserait miser plus du quart de ton argent sur une seule entreprise.*\n\n"
        "**4. Maximum 5 achats par jour. Les ventes restent toujours libres.**\n"
        "*Le marché sera encore là demain, il ne part pas sans toi.*\n\n"
        "**5. Les frais : 10 $ par achat et par vente, 1,5 % de conversion sur les titres américains, 0,5 % de frais de gestion le 1er de chaque mois.**\n"
        "*Investir coûte quelque chose. Ton argent doit travailler plus fort que les frais.*\n\n"
        "**6. Coupe-circuit : si un titre monte ou descend de plus de 30 % dans une journée, ses achats sont suspendus jusqu'au prochain jour de bourse. Tu peux toujours vendre.**\n"
        "*Les vrais marchés font exactement ça pour calmer le jeu.*\n\n"
        "**7. Ta position sur un titre ne peut pas dépasser 5 % de ce qui s'échange chaque jour sur ce titre. Et seulement 3 bourses : Toronto, New York et Nasdaq.**\n\n"
        "**8. Toujours en vigueur : 4 titres différents minimum, 5 achats par mois. Les points perdus aux vérifications ne reviennent pas.**\n"
        "*C'est une évaluation, pas juste un jeu.*"
    )
    lu = st.checkbox("J'ai lu et je comprends ces règles.")
    if st.button("Fermer", disabled=not lu, use_container_width=True):
        now_str = datetime.now(ZoneInfo("America/Toronto")).strftime("%Y-%m-%d %H:%M:%S")
        with conn.session as session:
            session.execute(
                text("INSERT INTO regles_vues (username, version, vue_le) VALUES (:u, :v, :d) "
                     "ON CONFLICT (username) DO UPDATE SET version=:v, vue_le=:d"),
                {"u": username, "v": VERSION_REGLES, "d": now_str})
            session.commit()
        st.rerun()


def verifier_popup_regles(username):
    """Affiche la fenêtre des règles tant que l'élève n'a pas vu la version en cours.

    GARDE-FOU (6 nov. 2026) : la fenêtre de l'étape 2 annonce le retour
    à 10 000 $. Avant le jour du krach (16 novembre 2026), seuls les
    comptes enseignants peuvent la voir : la surprise reste entière
    même si le paquet étape 2 est déployé plus tôt, pour un essai ou
    par erreur."""
    if not est_compte_enseignant(username):
        from datetime import date as _date_garde
        if datetime.now(ZoneInfo("America/Toronto")).date() < _date_garde(2026, 11, 16):
            return
    try:
        r = conn.query("SELECT version FROM regles_vues WHERE username=:u", params={"u": username}, ttl=0)
        if r.empty or int(r.iloc[0]['version']) < VERSION_REGLES:
            afficher_popup_regles(username)
    except Exception:
        pass

# --- FENETRE D'AVIS DE CORRECTION (bogue de conversion, octobre 2026) ---
# Avis rattaché au compte : seuls les élèves dont le nom est dans la table
# avis_correction voient la fenêtre, une seule fois, à leur prochaine connexion.

@st.dialog("Correction de ton compte")
def afficher_popup_correction(username, sens):
    if sens == "remboursement":
        st.markdown(
            "Un bogue de conversion (5 au 16 octobre) t'avait fait perdre de l'argent "
            "sur des titres américains : ton compte a été recalculé aux bons prix "
            "et le montant perdu t'a été remboursé."
        )
    elif sens == "veea":
        st.markdown(
            "Le 12 octobre, une vente de 250 actions du titre VEEA a été créditée "
            "à ton compte alors que tu ne possédais pas ce titre : c'est une erreur "
            "du système, pas un gain. Le montant de 1 425,00 $ a été retiré de ton "
            "comptant. Tout le reste de ton compte est inchangé."
        )
    elif sens == "nan_axg":
        st.markdown(
            "Deux corrections sur ton compte ce soir. La première : une vente de "
            "4 actions GOOGL est passée à un prix vide à cause d'un bogue de prix "
            "après la fermeture des marchés. Elle est annulée et tes 4 actions "
            "sont de retour. La deuxième : ton achat de 125 944 actions AXG à "
            "0,0397 $ et ta vente de ces actions à 7,9426 $ sont annulés. Les prix "
            "de ce titre chez notre fournisseur de données étaient incohérents "
            "(deux séries de prix différentes pour le même titre dans la même "
            "journée) : le gain de 995 322,81 $ était un gain de bogue, pas un "
            "gain de marché. Ton comptant est maintenant de 6 125,51 $. Tout le "
            "reste de ton compte est inchangé."
        )
    elif sens == "nan":
        st.markdown(
            "Ce soir, trois de tes ventes (1 action KO, 5 actions TPL et 6 actions "
            "AAPL) sont passées à un prix vide à cause d'un bogue de prix après la "
            "fermeture des marchés. Elles sont annulées : tes actions sont de "
            "retour dans ton portefeuille et ton comptant est recalculé à "
            "6 810,25 $. Tout le reste de ton compte est inchangé."
        )
    elif sens == "axg_achats":
        st.markdown(
            "Tes deux achats du titre AXG (100 000 actions le 27 octobre et "
            "146 341 actions le 28 octobre) sont annulés et l'argent des deux "
            "achats t'a été remboursé : 11 609,98 $. Les prix de ce titre chez "
            "notre fournisseur de données étaient incohérents : le même titre "
            "valait quelques sous à un endroit et plusieurs dollars à un autre, "
            "donc ces achats n'auraient jamais dû passer à ce prix. Ton "
            "comptant est maintenant de 12 263,29 $. Tout le reste de ton "
            "compte est inchangé."
        )
    elif sens == "nan_lina":
        st.markdown(
            "Ce soir, une de tes ventes (4 actions AAPL) est passée à un prix "
            "vide à cause d'un bogue de prix après la fermeture des marchés. "
            "Elle est annulée : tes 4 actions sont de retour dans ton "
            "portefeuille et ton comptant est recalculé à 6 461,24 $. Tout le "
            "reste de ton compte est inchangé."
        )
    elif sens == "crypto":
        st.markdown(
            "Avant le 17 octobre, l'application laissait passer des paires de "
            "cryptomonnaies (par exemple SOL-GBP ou ETH-BTC). Ce ne sont pas des "
            "actions en bourse : elles n'auraient jamais dû être permises, et la "
            "porte est fermée depuis le 17 octobre. Les gains faits avec ces "
            "paires, 533,62 $, ont été retirés de ton comptant. Tout le reste de "
            "ton compte est inchangé."
        )
    elif sens == "xp_prix":
        st.markdown(
            "Le 27 octobre, ton achat de 75 actions du titre XP est passé à "
            "42,70 $ l'action à cause d'un bogue de prix chez notre "
            "fournisseur de données : le vrai prix était de 22,44 $. Ton "
            "achat a été recalculé au vrai prix et la différence, "
            "1 519,36 $, t'a été remboursée. Ton comptant est maintenant "
            "de 5 437,33 $. Tout le reste de ton compte est inchangé."
        )
    else:
        st.markdown(
            "Un bogue de conversion (5 au 16 octobre) a faussé les prix des titres "
            "américains : ton compte a été recalculé aux bons prix, comme si le "
            "bogue n'était jamais arrivé."
        )
    lu = st.checkbox("J'ai compris.")
    if st.button("Fermer", disabled=not lu, use_container_width=True):
        now_str = datetime.now(ZoneInfo("America/Toronto")).strftime("%Y-%m-%d %H:%M:%S")
        with conn.session as session:
            session.execute(
                text("UPDATE avis_correction SET vu_le=:d WHERE username=:u"),
                {"u": username, "d": now_str})
            session.commit()
        st.rerun()


def verifier_popup_correction(username):
    """Affiche l'avis de correction si l'élève en a un qu'il n'a pas encore vu."""
    try:
        r = conn.query("SELECT sens, vu_le FROM avis_correction WHERE username=:u", params={"u": username}, ttl=0)
        if not r.empty and (r.iloc[0]['vu_le'] is None or str(r.iloc[0]['vu_le']).strip() == ""):
            afficher_popup_correction(username, str(r.iloc[0]['sens']))
    except Exception:
        pass

# --- MODE « VRAIE BOURSE » : FRAIS, PLAFOND DE CONCENTRATION, COUPE-CIRCUIT ---
# Décision de Mathieu (28 oct. 2026) : rapprocher la simulation de la réalité.
# - Frais de transaction : 10 $ par achat et par vente (jamais rétroactifs).
# - Frais de conversion : 1,5 % sur les titres américains (achat et vente).
# - Frais de gestion : 0,5 % de la valeur totale du compte, prélevés le 1er
#   de chaque mois à compter du 1er novembre 2026.
# - Plafond : maximum 25 % de la valeur du compte sur un seul titre à l'achat.
# - Coupe-circuit : achats suspendus si le titre bouge de plus de 30 % dans
#   la journée (contre la clôture de la veille) ; les ventes restent permises.
# Le compte de l'enseignant et ceux du groupe Enseignants sont exemptés.
FRAIS_TRANSACTION = 10.00
FRAIS_CONVERSION_PCT = 0.015
FRAIS_GESTION_PCT = 0.005
FRAIS_GESTION_DEBUT = (2026, 11)  # (année, mois) du premier prélèvement
PLAFOND_TITRE_PCT = 25.0
# Plancher d'achat de l'étape 2 (décision de Mathieu, 6 nov. 2026) :
# chaque achat vaut au moins 2 % de la valeur du compte, le symétrique
# du plafond de 25 %. Il tue les positions décorations (une action
# pour cocher « 4 titres ») sans empêcher les achats en tranches.
# Vérifié à la création de l'achat ou de l'ordre seulement, jamais à
# l'exécution : une position qui rapetisse ensuite n'est pas punie.
PLANCHER_TITRE_PCT = 2.0
COUPE_CIRCUIT_PCT = 30.0


def compte_exempte_frais(username):
    """Vrai pour le compte de Mathieu et le groupe Enseignants."""
    if username == "MathieuSavary":
        return True
    try:
        r = conn.query("SELECT groupe FROM users WHERE username=:u",
                       params={"u": username}, ttl=300)
        if not r.empty:
            return str(r.iloc[0]['groupe'] or "").strip().lower().startswith("enseignant")
    except Exception:
        pass
    return False


def est_compte_enseignant(username):
    """Vrai pour les comptes du groupe Enseignants (et MathieuSavary).
    La Supervision n'existe que pour ces comptes : les autres ne voient
    même pas l'onglet (demande de Mathieu, 6 nov. 2026)."""
    if username == "MathieuSavary":
        return True
    try:
        r = conn.query("SELECT groupe FROM users WHERE username=:u",
                       params={"u": username}, ttl=300)
        if not r.empty:
            return "enseignant" in str(r.iloc[0]['groupe'] or "").strip().lower()
    except Exception:
        pass
    return False


# Plafond d'achats par jour (décision de Mathieu, 29 oct. 2026 ; porté
# à 5 et annoncé dans les règles à l'étape 2, décision du 6 nov. 2026) : après
# LIMITE_ACHATS_JOUR achats dans la même journée civile (heure de
# Toronto, de minuit à minuit), les achats sont en pause jusqu'au
# lendemain ; les ventes restent toujours libres. Rien n'est annoncé
# d'avance : le message n'apparaît qu'au moment où l'élève atteint la
# limite, l'effet de surprise fait partie du dispositif.
LIMITE_ACHATS_JOUR = 5


def achats_du_jour(username):
    """Nombre d'achats déjà faits aujourd'hui par le compte (jour
    civil à Toronto). En cas d'erreur de lecture, on renvoie 0 : ce
    garde-fou ne doit pas bloquer tout le monde pour un pépin."""
    jour = datetime.now(ZoneInfo("America/Toronto")).strftime("%Y-%m-%d")
    try:
        r = conn.query(
            "SELECT shares FROM transactions WHERE username=:u "
            "AND timestamp LIKE :p",
            params={"u": username, "p": jour + "%"}, ttl=0)
    except Exception:
        return 0
    if r.empty:
        return 0
    return int(sum(1 for s in r['shares'] if float(s) > 0))


def plafond_achats_atteint(username):
    """Vrai si le compte a épuisé ses achats du jour. Les comptes
    exemptés (enseignant) n'ont pas de plafond."""
    if compte_exempte_frais(username):
        return False
    return achats_du_jour(username) >= LIMITE_ACHATS_JOUR


# Plafond caché de 500 $ par achat hors heures (30 oct. 2026) RETIRÉ
# à l'étape 2 (décision de Mathieu, 6 nov. 2026) : hors heures, il
# n'y a plus aucune transaction immédiate, seulement des ordres en
# attente exécutés à l'ouverture, et le plancher d'achat de 2 % de la
# valeur du compte remplace le plafond comme garde-fou anti-excès.


@st.dialog("Prends une pause de la bourse !")
def dialogue_pause_bourse():
    st.write("5 achats dans la même journée, c'est suffisant ;) "
             "Rassure-toi : le marché sera encore là demain, il ne "
             "part pas sans toi.")
    st.write("Les bons investisseurs choisissent leurs moments au "
             "lieu de courir après chaque mouvement. Tes achats sont "
             "en pause jusqu'à demain ; tes ventes restent toujours "
             "possibles.")
    if st.button("J'ai compris"):
        st.rerun()


def frais_pour_ordre(devise, montant_cad):
    """(frais fixes, frais de conversion) d'un ordre au mode vraie bourse."""
    conv = round(FRAIS_CONVERSION_PCT * montant_cad, 2) if devise == "USD" else 0.0
    return FRAIS_TRANSACTION, conv


def _verrou_transaction(session, username):
    """Verrou consultatif Postgres par utilisateur, tenu jusqu'à la fin de
    la transaction SQL en cours. Il sérialise les opérations d'argent d'un
    même compte entre sessions simultanées : sans lui, six sessions
    ouvertes en même temps lisent le même solde ou la même position avant
    qu'aucune écrive, et la même position peut être vendue plusieurs fois
    (faille dévoilée par un élève le 4 novembre 2026). À prendre EN
    PREMIER dans la session d'écriture, puis relire l'état (comptant,
    positions) DANS la même session avant de valider."""
    session.execute(text("SELECT pg_advisory_xact_lock(hashtext(:u))"), {"u": username})


def enregistrer_frais(session, username, type_frais, montant, details=""):
    """Consigne un frais dans la table frais (dans la session d'écriture ouverte)."""
    if montant and float(montant) > 0:
        now_str = datetime.now(ZoneInfo("America/Toronto")).strftime("%Y-%m-%d %H:%M:%S")
        session.execute(
            text("INSERT INTO frais (username, type, montant, details, timestamp) "
                 "VALUES (:u, :ty, :m, :d, :ts)"),
            {"u": username, "ty": type_frais, "m": round(float(montant), 2),
             "d": details, "ts": now_str})


def valeur_totale_compte(username):
    """(comptant, valeur des positions, valeur totale) aux prix actuels.
    Repli sur le prix moyen quand un prix est indisponible."""
    c = conn.query("SELECT cash FROM users WHERE username=:u", params={"u": username}, ttl=0)
    cash = float(c.iloc[0]['cash']) if not c.empty else 0.0
    pos = conn.query("SELECT ticker, shares, avg_price FROM portfolio WHERE username=:u",
                     params={"u": username}, ttl=0)
    val = 0.0
    if not pos.empty:
        prix = obtenir_prix_groupes(pos['ticker'].unique().tolist())
        for _, row in pos.iterrows():
            tk = str(row['ticker']).strip().upper()
            info = prix.get(tk)
            px = info["cad"] if info else None
            val += (px if px is not None else float(row['avg_price'] or 0.0)) * int(row['shares'] or 0)
    return cash, val, cash + val


def part_titre_apres_achat(username, ticker_symbol, prix_unitaire_cad, quantite):
    """Part (%) qu'occuperait le titre dans le compte après un achat."""
    _, _, total = valeur_totale_compte(username)
    if total <= 0:
        return 100.0
    p = conn.query("SELECT shares FROM portfolio WHERE username=:u AND LOWER(ticker)=LOWER(:t)",
                   params={"u": username, "t": ticker_symbol}, ttl=0)
    sh = int(p.iloc[0]['shares']) if not p.empty else 0
    return (sh + quantite) * prix_unitaire_cad / total * 100.0


def plancher_achat_minimum(username):
    """Montant minimum d'un achat : PLANCHER_TITRE_PCT % de la valeur
    totale du compte. None si la valeur est illisible (dans ce cas,
    on ne bloque pas sur une donnée qu'on ne peut pas vérifier)."""
    try:
        _, _, total = valeur_totale_compte(username)
    except Exception:
        return None
    if not total or float(total) <= 0:
        return None
    return round(float(total) * PLANCHER_TITRE_PCT / 100.0, 2)


def coupe_circuit_actif(ticker_symbol):
    """(bloqué, variation %) : vrai si le titre a bougé de plus de 30 %
    aujourd'hui contre la clôture de la veille. (False, None) si la
    variation ne peut pas être mesurée."""
    try:
        cv = cloture_veille(ticker_symbol)
        pa = obtenir_prix_actuel(ticker_symbol)
        if not cv or not pa or float(cv) <= 0:
            return False, None
        var = (float(pa) - float(cv)) / float(cv) * 100.0
        return abs(var) > COUPE_CIRCUIT_PCT, var
    except Exception:
        return False, None


def appliquer_frais_gestion(username):
    """Prélève les frais de gestion dus (0,5 % le 1er de chaque mois dès
    le 1er novembre 2026). Vérification légère : au plus une fois par
    session et par jour ; chaque prélèvement est consigné une seule fois
    grâce à sa référence (la date du 1er) dans la table frais."""
    try:
        maintenant = datetime.now(ZoneInfo("America/Toronto"))
        auj = maintenant.date()
        if (auj.year, auj.month) < FRAIS_GESTION_DEBUT:
            return
        cle = f"fg_verifie_{auj.isoformat()}"
        if st.session_state.get(cle):
            return
        st.session_state[cle] = True
        if compte_exempte_frais(username):
            return
        dues = []
        a, m = FRAIS_GESTION_DEBUT
        while (a, m) <= (auj.year, auj.month):
            dues.append(f"{a:04d}-{m:02d}-01")
            m += 1
            if m > 12:
                a, m = a + 1, 1
        faites = conn.query("SELECT details FROM frais WHERE username=:u AND type='gestion'",
                            params={"u": username}, ttl=0)
        deja = set(faites['details'].astype(str).tolist()) if not faites.empty else set()
        for ref in dues:
            if ref in deja:
                continue
            _, _, total = valeur_totale_compte(username)
            frais_m = round(FRAIS_GESTION_PCT * total, 2) if total > 0 else 0.0
            now_str = maintenant.strftime("%Y-%m-%d %H:%M:%S")
            with conn.session as session:
                if frais_m > 0:
                    session.execute(text("UPDATE users SET cash = cash - :f WHERE username = :u"),
                                    {"f": frais_m, "u": username})
                session.execute(
                    text("INSERT INTO frais (username, type, montant, details, timestamp) "
                         "VALUES (:u, 'gestion', :m, :d, :ts)"),
                    {"u": username, "m": frais_m, "d": ref, "ts": now_str})
                session.commit()
    except Exception:
        pass

# --- ORDRES EN ATTENTE EXÉCUTÉS AU PRIX D'OUVERTURE ---
# Mécanique testée le 2 nov. 2026 au soir sur le seul compte de Mathieu,
# puis MISE EN LIGNE POUR TOUS LE MÊME SOIR, sur sa décision expresse,
# SANS annonce et SANS monter VERSION_REGLES : les élèves qui se
# plaignent que « ce n'est plus de la vraie bourse » ont tort dans l'autre
# sens, car c'est l'exécution au prix gelé qui n'existe pas sur un vrai
# marché ; un ordre passé marché fermé s'y exécute à l'ouverture. La
# direction de Mathieu : rapprocher tranquillement la simulation de la
# bourse réelle, surtout après le krach du 16 novembre. La mécanique
# ferme la porte exploitée par les achats hors heures au prix gelé
# (audit de timofeybussiere du 2 nov. : ULBI, INO, SLGB achetés marché
# fermé à la clôture de la veille, revendus après le saut de l'ouverture).
# Interrupteur d'urgence : ORDRES_OUVERTURE_ACTIFS = False redonne
# l'exécution immédiate au prix gelé pour les NOUVEAUX achats ; les
# ordres déjà en attente continuent d'être réglés normalement.
# Mécanique : hors heures, l'achat du compte test devient un ordre en
# attente. Le montant total (prix gelé estimé + frais) est réservé dans
# le comptant au moment de l'ordre. À la première connexion après
# l'ouverture de la séance visée, l'ordre s'exécute au prix d'ouverture
# officiel de cette séance (barre quotidienne Yahoo, qui ne change plus
# une fois la séance commencée) : le montant se convertit en actions à
# ce prix, les frais du mode vraie bourse s'appliquent, le reste est
# remboursé. Si le titre a bougé de plus de 30 % à l'ouverture contre
# la clôture de la veille (coupe-circuit), si la limite de volume ou le
# plafond de 25 % bloque, ou si le prix d'ouverture dépasse le montant,
# l'ordre est annulé et le montant est remboursé au complet.
# L'ordre peut être annulé par l'élève tant qu'il est en attente.
ORDRES_OUVERTURE_ACTIFS = True
LIMITE_ORDRES_EN_ATTENTE = 4


def ordres_ouverture_actif(username):
    """Vrai si les nouveaux achats hors heures deviennent des ordres en
    attente. Le nom d'utilisateur est accepté pour garder la porte
    ouverte à un périmètre par compte si un jour il le faut."""
    return ORDRES_OUVERTURE_ACTIFS


def _prochaine_seance_execution(moment):
    """Date (ISO) de la séance où un ordre placé à ce moment s'exécute :
    aujourd'hui si c'est un jour de semaine avant 9 h 30, sinon le
    prochain jour de semaine. Fonction pure, testable."""
    d = moment.date()
    minutes = moment.hour * 60 + moment.minute
    if moment.weekday() < 5 and minutes < 9 * 60 + 30:
        return d.isoformat()
    d = d + timedelta(days=1)
    while d.weekday() >= 5:
        d = d + timedelta(days=1)
    return d.isoformat()


def _prix_ouverture_session(ticker_symbol, date_iso):
    """Prix d'ouverture officiel (en CAD) du titre pour la séance
    date_iso, lu dans la barre quotidienne Yahoo de ce jour-là.
    Retourne None si la barre n'existe pas encore (séance pas commencée,
    jour férié ou données pas consolidées)."""
    try:
        debut = datetime.strptime(date_iso, "%Y-%m-%d").date()
        fin = debut + timedelta(days=1)
        t = yf.Ticker(ticker_symbol)
        hist = t.history(start=debut.isoformat(), end=fin.isoformat())
        if hist is None or hist.empty or 'Open' not in hist.columns:
            return None
        try:
            devise = str(t.fast_info.get('currency') or 'CAD').upper()
        except Exception:
            devise = devise_naturelle(ticker_symbol)
        for idx, row in hist.iterrows():
            if idx.date() != debut:
                continue
            o = float(row['Open'])
            if pd.isna(o) or o <= 0:
                return None
            return convertir_vers_cad(o, devise)
        return None
    except Exception:
        return None


def _actions_abordables(montant_cad, prix_cad, devise, exempte):
    """(actions, coût, frais fixe, frais de conversion) achetables avec
    montant_cad au prix prix_cad, frais du mode vraie bourse déduits du
    montant. Fonction pure, testable."""
    frais_fixe = 0.0 if exempte else FRAIS_TRANSACTION
    budget = float(montant_cad) - frais_fixe
    if budget <= 0 or not prix_cad or float(prix_cad) <= 0:
        return 0, 0.0, frais_fixe, 0.0
    if devise == "USD" and not exempte:
        unitaire = float(prix_cad) * (1.0 + FRAIS_CONVERSION_PCT)
    else:
        unitaire = float(prix_cad)
    shares = int(budget // unitaire)
    if shares < 1:
        return 0, 0.0, frais_fixe, 0.0
    cout = round(shares * float(prix_cad), 2)
    frais_conv = round(FRAIS_CONVERSION_PCT * cout, 2) if (devise == "USD" and not exempte) else 0.0
    return shares, cout, frais_fixe, frais_conv


def ordres_en_attente_pour(username):
    """Ordres en attente du compte, du plus récent au plus ancien."""
    try:
        return conn.query(
            "SELECT id, ticker, montant_cad, devise, place_le, session_execution, sens, parts "
            "FROM ordres_en_attente WHERE username=:u AND statut='en_attente' "
            "ORDER BY id DESC",
            params={"u": username}, ttl=0)
    except Exception:
        return pd.DataFrame()


def _ordre_compte_pour_le_jour(statut, place_le, session_execution, auj_iso, nouvelle_session):
    """Vrai si un ordre existant compte comme « l'achat du jour » pour
    son titre : encore en attente (peu importe sa date), exécuté à la
    séance d'aujourd'hui, visant la même séance que le nouvel ordre,
    ou placé aujourd'hui. Fonction pure, testable."""
    if statut == "en_attente":
        return True
    if str(session_execution) == auj_iso:
        return True
    if str(session_execution) == nouvelle_session:
        return True
    if str(place_le)[:10] == auj_iso:
        return True
    return False


def achat_hors_heures_deja_fait(username, ticker_symbol, nouvelle_session):
    """Vrai si le compte a déjà fait son achat hors heures de ce titre
    aujourd'hui (règle « un achat par entreprise par jour » hors heures,
    décision de Mathieu, 2 nov. 2026 au soir, après les 4 achats
    identiques de MERC à 499,88 $ d'Éloi Lévesque : un achat hors
    heures ne doit pas se fractionner en répétant le même titre).
    Un ordre annulé par l'élève avant l'ouverture ne compte pas : il
    n'a jamais été un achat. Les comptes exemptés ne sont pas touchés.
    Le refus paraît en une ligne dans le panneau d'ordre."""
    if compte_exempte_frais(username):
        return False
    auj = datetime.now(ZoneInfo("America/Toronto")).strftime("%Y-%m-%d")
    try:
        r = conn.query(
            "SELECT statut, place_le, session_execution FROM ordres_en_attente "
            "WHERE username=:u AND LOWER(ticker)=LOWER(:t) AND statut <> 'annule_eleve'",
            params={"u": username, "t": ticker_symbol}, ttl=0)
    except Exception:
        return False
    if r.empty:
        return False
    for _, row in r.iterrows():
        if _ordre_compte_pour_le_jour(row['statut'], row['place_le'],
                                       row['session_execution'], auj, nouvelle_session):
            return True
    return False


def creer_ordre_en_attente(username, ticker_symbol, montant_cad, devise, session_exec=None):
    """Réserve le montant dans le comptant et inscrit l'ordre en
    attente. À appeler seulement après les vérifications d'usage.
    Le solde et le nombre d'ordres en attente sont REVÉRIFIÉS sous le
    verrou par utilisateur, dans la transaction d'écriture : des
    sessions simultanées du même compte ne peuvent pas réserver deux
    fois le même argent. Retourne None si la réservation est refusée
    à cette relecture."""
    moment = datetime.now(ZoneInfo("America/Toronto"))
    now_str = moment.strftime("%Y-%m-%d %H:%M:%S")
    if session_exec is None:
        session_exec = _prochaine_seance_execution(moment)
    montant_r = round(float(montant_cad), 2)
    with conn.session as session:
        _verrou_transaction(session, username)
        cash_rel = session.execute(text("SELECT cash FROM users WHERE username=:u"),
                                   {"u": username}).scalar()
        nb_att = session.execute(
            text("SELECT COUNT(*) FROM ordres_en_attente WHERE username=:u AND statut='en_attente'"),
            {"u": username}).scalar()
        if cash_rel is None or float(cash_rel) < montant_r or int(nb_att or 0) >= LIMITE_ORDRES_EN_ATTENTE:
            session.rollback()
            return None
        session.execute(text("UPDATE users SET cash = cash - :m WHERE username = :u"),
                        {"m": montant_r, "u": username})
        session.execute(
            text("INSERT INTO ordres_en_attente (username, ticker, montant_cad, devise, "
                 "place_le, session_execution, statut) VALUES (:u, :t, :m, :d, :p, :s, 'en_attente')"),
            {"u": username, "t": ticker_symbol.upper(), "m": montant_r,
             "d": devise, "p": now_str, "s": session_exec})
        session.commit()
    return session_exec


def _regler_ordre_annule(session, ordre, statut, note):
    """Rembourse le montant réservé et marque l'ordre annulé.
    execute_le reçoit le moment du règlement (comme pour un ordre
    exécuté) : c'est lui qui fait partir le délai d'affichage de
    2 minutes de la carte de résultat."""
    regle_le = datetime.now(ZoneInfo("America/Toronto")).strftime("%Y-%m-%d %H:%M:%S")
    session.execute(text("UPDATE users SET cash = cash + :m WHERE username = :u"),
                    {"m": float(ordre['montant_cad']), "u": ordre['username']})
    session.execute(
        text("UPDATE ordres_en_attente SET statut=:st, note=:n, execute_le=:e WHERE id=:i"),
        {"st": statut, "n": note, "e": regle_le, "i": int(ordre['id'])})


def _regler_ordre_vente_annule(session, ordre, statut, note):
    """Remet les parts réservées d'un ordre de vente dans le
    portefeuille et marque l'ordre réglé. Le prix moyen est refondu
    au prorata si la position existe encore (des achats ont pu
    s'ajouter entre-temps) ; sinon, la ligne est recréée avec le
    prix moyen gardé dans l'ordre. execute_le reçoit le moment du
    règlement : c'est lui qui fait partir le délai d'affichage de
    2 minutes de la carte de résultat."""
    regle_le = datetime.now(ZoneInfo("America/Toronto")).strftime("%Y-%m-%d %H:%M:%S")
    username_o = ordre['username']
    ticker_o = str(ordre['ticker']).upper()
    try:
        parts_o = int(ordre['parts'] or 0)
    except (TypeError, ValueError):
        parts_o = 0
    avg_o = ordre['avg_reserve']
    try:
        avg_o = float(avg_o) if avg_o is not None and not pd.isna(avg_o) else None
    except (TypeError, ValueError):
        avg_o = None
    if parts_o > 0:
        p_row = session.execute(text("SELECT shares, avg_price FROM portfolio WHERE username=:u AND LOWER(ticker)=LOWER(:t)"),
                                {"u": username_o, "t": ticker_o}).fetchone()
        if p_row is not None:
            anc_s, anc_p = int(p_row[0]), float(p_row[1] or 0.0)
            base_p = avg_o if avg_o is not None else anc_p
            n_s = anc_s + parts_o
            n_p = ((anc_s * anc_p) + (parts_o * base_p)) / n_s
            session.execute(text("UPDATE portfolio SET shares=:s, avg_price=:p WHERE username=:u AND LOWER(ticker)=LOWER(:t)"),
                            {"s": n_s, "p": n_p, "u": username_o, "t": ticker_o})
        else:
            session.execute(text("INSERT INTO portfolio VALUES (:u, :t, :s, :p)"),
                            {"u": username_o, "t": ticker_o, "s": parts_o,
                             "p": avg_o if avg_o is not None else 0.0})
    session.execute(
        text("UPDATE ordres_en_attente SET statut=:st, note=:n, execute_le=:e WHERE id=:i"),
        {"st": statut, "n": note, "e": regle_le, "i": int(ordre['id'])})


def annuler_ordre_en_attente(username, ordre_id):
    """Annulation par l'élève avant l'ouverture. Achat : remboursement
    intégral du montant réservé. Vente : les parts réservées
    retournent dans le portefeuille."""
    r = conn.query("SELECT id, username, montant_cad, ticker, sens, parts, avg_reserve "
                   "FROM ordres_en_attente "
                   "WHERE id=:i AND username=:u AND statut='en_attente'",
                   params={"i": int(ordre_id), "u": username}, ttl=0)
    if r.empty:
        return False
    with conn.session as session:
        _verrou_transaction(session, username)
        # Relecture du statut sous le verrou : si une exécution à
        # l'ouverture vient de régler cet ordre dans une autre session,
        # il ne faut surtout pas rembourser une deuxième fois.
        statut_rel = session.execute(
            text("SELECT statut FROM ordres_en_attente WHERE id=:i"),
            {"i": int(ordre_id)}).scalar()
        if statut_rel != 'en_attente':
            session.rollback()
            return False
        if str(r.iloc[0]['sens'] or 'ACHAT').upper() == 'VENTE':
            _regler_ordre_vente_annule(session, r.iloc[0], "annule_eleve",
                                       "Annulé par l'élève avant l'ouverture. Les actions sont de retour dans ton portefeuille.")
        else:
            _regler_ordre_annule(session, r.iloc[0], "annule_eleve", "Annulé par l'élève avant l'ouverture.")
        session.commit()
    return True


def ordre_vente_en_attente_sur(username, ticker_symbol):
    """Vrai si un ordre de VENTE est déjà en attente sur ce titre :
    un seul ordre de vente par entreprise à la fois (les parts sont
    réservées, un deuxième ordre n'aurait rien de propre à réserver)."""
    try:
        r = conn.query(
            "SELECT COUNT(*) AS n FROM ordres_en_attente WHERE username=:u "
            "AND LOWER(ticker)=LOWER(:t) AND statut='en_attente' AND sens='VENTE'",
            params={"u": username, "t": ticker_symbol}, ttl=0)
        return not r.empty and int(r.iloc[0]['n'] or 0) > 0
    except Exception:
        return False


def creer_ordre_vente_en_attente(username, ticker_symbol, parts, devise, session_exec=None):
    """Réserve les parts dans le portefeuille et inscrit l'ordre de
    vente en attente. Les parts sortent du portefeuille dès la
    création (même patron que l'argent réservé des achats) : elles
    ne peuvent plus être vendues une deuxième fois ailleurs. Le
    prix moyen d'achat est gardé dans l'ordre, pour restaurer la
    position à l'identique si l'ordre est annulé ou échoue.
    Parts disponibles, limite d'ordres et doublon sont REVÉRIFIÉS
    sous le verrou, dans la transaction d'écriture. Retourne la
    séance d'exécution, ou None si la réservation est refusée."""
    try:
        parts = int(parts)
    except (TypeError, ValueError):
        return None
    if parts < 1:
        return None
    moment = datetime.now(ZoneInfo("America/Toronto"))
    now_str = moment.strftime("%Y-%m-%d %H:%M:%S")
    if session_exec is None:
        session_exec = _prochaine_seance_execution(moment)
    tk = str(ticker_symbol).upper()
    with conn.session as session:
        _verrou_transaction(session, username)
        nb_att = session.execute(
            text("SELECT COUNT(*) FROM ordres_en_attente WHERE username=:u AND statut='en_attente'"),
            {"u": username}).scalar()
        if int(nb_att or 0) >= LIMITE_ORDRES_EN_ATTENTE:
            session.rollback()
            return None
        doublon = session.execute(
            text("SELECT COUNT(*) FROM ordres_en_attente WHERE username=:u AND LOWER(ticker)=LOWER(:t) AND statut='en_attente' AND sens='VENTE'"),
            {"u": username, "t": tk}).scalar()
        if int(doublon or 0) > 0:
            session.rollback()
            return None
        p_row = session.execute(text("SELECT shares, avg_price FROM portfolio WHERE username=:u AND LOWER(ticker)=LOWER(:t)"),
                                {"u": username, "t": tk}).fetchone()
        if p_row is None or int(p_row[0]) < parts:
            session.rollback()
            return None
        anc_s, anc_p = int(p_row[0]), float(p_row[1] or 0.0)
        rem = anc_s - parts
        if rem > 0:
            session.execute(text("UPDATE portfolio SET shares=:s WHERE username=:u AND LOWER(ticker)=LOWER(:t)"),
                            {"s": rem, "u": username, "t": tk})
        else:
            session.execute(text("DELETE FROM portfolio WHERE username=:u AND LOWER(ticker)=LOWER(:t)"),
                            {"u": username, "t": tk})
        session.execute(
            text("INSERT INTO ordres_en_attente (username, ticker, montant_cad, devise, "
                 "place_le, session_execution, statut, sens, parts, avg_reserve) "
                 "VALUES (:u, :t, 0, :d, :p, :s, 'en_attente', 'VENTE', :n, :a)"),
            {"u": username, "t": tk, "d": devise, "p": now_str, "s": session_exec,
             "n": parts, "a": anc_p})
        session.commit()
    return session_exec


def _regler_ordre_vente(username, ordre, maintenant, auj, minutes, exempte):
    """Règle un ordre de VENTE en attente à l'ouverture de sa séance.
    Symétrique des achats, avec les différences de la vraie bourse :
    aucun coupe-circuit sur une vente (vendre reste toujours
    permis), aucune limite de volume (vendre ne crée pas de
    position) et aucun délai de détention à revérifier (entre la
    création le soir et l'ouverture du lendemain, le délai de
    30 minutes ou de 1 h est toujours écoulé). Si le prix
    d'ouverture est introuvable après 4 jours, les parts sont
    remises et l'ordre est fermé en échec."""
    date_exec = str(ordre['session_execution'])
    if date_exec == auj and minutes < 9 * 60 + 30:
        return  # l'ouverture de cette séance n'a pas encore eu lieu
    ticker_o = str(ordre['ticker']).upper()
    try:
        parts_o = int(ordre['parts'] or 0)
    except (TypeError, ValueError):
        parts_o = 0
    devise_o = str(ordre['devise'] or devise_naturelle(ticker_o)).upper()
    prix_ouv = _prix_ouverture_session(ticker_o, date_exec)
    if prix_ouv is None:
        try:
            retard = (maintenant.date() - datetime.strptime(date_exec, "%Y-%m-%d").date()).days
        except Exception:
            retard = 0
        if retard > 4:
            with conn.session as session:
                _regler_ordre_vente_annule(session, ordre, "echec",
                                           "Aucun prix d'ouverture trouvé pour la séance visée. Tes actions sont de retour dans ton portefeuille.")
                session.commit()
        return
    # Bouclier prix incohérent, le même que sur les transactions
    # directes : si l'ouverture s'écarte d'un facteur 3 de la
    # clôture de la veille, ce sont les données qui sont fausses
    # (ou un fractionnement) ; on ne vend pas à un prix faux, les
    # parts retournent dans le portefeuille.
    clot_prec_v = cloture_avant_date(ticker_o, date_exec)
    if clot_prec_v and float(clot_prec_v) > 0 and (
            prix_ouv > 3.0 * float(clot_prec_v) or prix_ouv < float(clot_prec_v) / 3.0):
        with conn.session as session:
            _regler_ordre_vente_annule(session, ordre, "echec",
                                       "Le prix d'ouverture ne concordait pas avec la clôture de la veille. Tes actions sont de retour dans ton portefeuille.")
            session.commit()
        return
    if parts_o < 1:
        with conn.session as session:
            _regler_ordre_vente_annule(session, ordre, "echec",
                                       "Ordre de vente sans quantité lisible. Tes actions sont de retour dans ton portefeuille.")
            session.commit()
        return
    now_str = maintenant.strftime("%Y-%m-%d %H:%M:%S")
    brut = round(parts_o * prix_ouv, 2)
    frais_fixe_o, frais_conv_o = (0.0, 0.0) if exempte else frais_pour_ordre(devise_o, brut)
    credit_net = round(brut - frais_fixe_o - frais_conv_o, 2)
    with conn.session as session:
        session.execute(text("UPDATE users SET cash = cash + :m WHERE username = :u"),
                        {"m": credit_net, "u": username})
        session.execute(text("INSERT INTO transactions (username, ticker, shares, price, total, timestamp) "
                             "VALUES (:u, :t, :s, :p, :tot, :time)"),
                        {"u": username, "t": ticker_o, "s": -parts_o, "p": prix_ouv,
                         "tot": brut, "time": now_str})
        enregistrer_frais(session, username, "transaction", frais_fixe_o, ticker_o)
        enregistrer_frais(session, username, "conversion", frais_conv_o, ticker_o)
        session.execute(
            text("UPDATE ordres_en_attente SET statut='execute', prix_execution=:p, "
                 "shares=:s, execute_le=:e, note=:n WHERE id=:i"),
            {"p": prix_ouv, "s": parts_o, "e": now_str,
             "n": f"Vendu à l'ouverture du {date_exec}.", "i": int(ordre['id'])})
        session.commit()


def executer_ordres_en_attente(username):
    """Exécute les ordres en attente arrivés à échéance, au prix
    d'ouverture officiel de leur séance. Appelée à la connexion, comme
    les frais de gestion : le prix d'ouverture ne change plus une fois
    la séance commencée, donc l'exécution reste exacte même si elle a
    lieu plus tard dans la journée. Chaque ordre est réglé dans sa
    propre transaction ; un ordre qui échoue reste en attente et sera
    réessayé, sauf annulation franche (remboursement immédiat).
    Volontairement SANS garde sur ORDRES_OUVERTURE_ACTIFS : même si
    l'interrupteur est fermé, les ordres déjà placés doivent être réglés.
    Verrou par utilisateur tenu pendant tout le règlement : deux
    sessions simultanées du même compte ne peuvent pas exécuter
    (ni rembourser) deux fois le même ordre.
    """
    try:
        with conn.session as verrou:
            _verrou_transaction(verrou, username)
            _executer_ordres_en_attente_sous_verrou(username)
            verrou.commit()
    except Exception:
        pass


def _executer_ordres_en_attente_sous_verrou(username):
    maintenant = datetime.now(ZoneInfo("America/Toronto"))
    auj = maintenant.date().isoformat()
    minutes = maintenant.hour * 60 + maintenant.minute
    dus = conn.query(
        "SELECT id, username, ticker, montant_cad, devise, session_execution, sens, parts, avg_reserve "
        "FROM ordres_en_attente WHERE username=:u AND statut='en_attente' "
        "AND session_execution <= :a ORDER BY id",
        params={"u": username, "a": auj}, ttl=0)
    if dus.empty:
        return
    exempte = compte_exempte_frais(username)
    for _, ordre in dus.iterrows():
        if str(ordre['sens'] or 'ACHAT').upper() == 'VENTE':
            _regler_ordre_vente(username, ordre, maintenant, auj, minutes, exempte)
            continue
        date_exec = str(ordre['session_execution'])
        if date_exec == auj and minutes < 9 * 60 + 30:
            continue  # l'ouverture de cette séance n'a pas encore eu lieu
        ticker_o = str(ordre['ticker']).upper()
        montant = float(ordre['montant_cad'])
        devise_o = str(ordre['devise'] or devise_naturelle(ticker_o)).upper()
        prix_ouv = _prix_ouverture_session(ticker_o, date_exec)
        if prix_ouv is None:
            # Pas de barre pour la séance visée : jour férié ou
            # données pas encore consolidées. On réessaie à la
            # prochaine connexion ; après 4 jours, on rembourse.
            try:
                retard = (maintenant.date() - datetime.strptime(date_exec, "%Y-%m-%d").date()).days
            except Exception:
                retard = 0
            if retard > 4:
                with conn.session as session:
                    _regler_ordre_annule(session, ordre, "echec",
                                         "Aucun prix d'ouverture trouvé pour la séance visée. Montant remboursé.")
                    session.commit()
            continue
        now_str = maintenant.strftime("%Y-%m-%d %H:%M:%S")
        # Coupe-circuit mesuré à l'ouverture : variation du prix
        # d'ouverture contre la clôture de la séance précédente.
        clot_prec = cloture_avant_date(ticker_o, date_exec)
        var_ouv = None
        if clot_prec and float(clot_prec) > 0:
            var_ouv = (prix_ouv - float(clot_prec)) / float(clot_prec) * 100.0
        if var_ouv is not None and abs(var_ouv) > COUPE_CIRCUIT_PCT:
            with conn.session as session:
                _regler_ordre_annule(session, ordre, "annule_circuit",
                                     f"Coupe-circuit : le titre a ouvert à {var_ouv:+.1f} % contre la clôture de la veille. Montant remboursé.")
                session.commit()
            continue
        shares, cout, frais_fixe_o, frais_conv_o = _actions_abordables(montant, prix_ouv, devise_o, exempte)
        if shares < 1:
            with conn.session as session:
                _regler_ordre_annule(session, ordre, "echec",
                                     "Le prix d'ouverture dépassait le montant de l'ordre. Montant remboursé.")
                session.commit()
            continue
        msg_vol = verifier_limite_volume(username, ticker_o, prix_ouv, cout)
        if msg_vol:
            with conn.session as session:
                _regler_ordre_annule(session, ordre, "annule_volume",
                                     "Limite de volume quotidien atteinte à l'exécution. Montant remboursé.")
                session.commit()
            continue
        if not exempte and part_titre_apres_achat(username, ticker_o, prix_ouv, shares) > PLAFOND_TITRE_PCT:
            with conn.session as session:
                _regler_ordre_annule(session, ordre, "annule_concentration",
                                     "Maximum 25 % sur un seul titre à l'exécution. Montant remboursé.")
                session.commit()
            continue
        total_o = cout + frais_fixe_o + frais_conv_o
        reste = round(montant - total_o, 2)
        with conn.session as session:
            if reste > 0:
                session.execute(text("UPDATE users SET cash = cash + :m WHERE username = :u"),
                                {"m": reste, "u": username})
            p_row = session.execute(text("SELECT shares, avg_price FROM portfolio WHERE username=:u AND LOWER(ticker)=LOWER(:t)"),
                                    {"u": username, "t": ticker_o}).fetchone()
            if p_row is not None:
                anc_s, anc_p = int(p_row[0]), float(p_row[1] or prix_ouv)
                n_s = anc_s + shares
                n_p = ((anc_s * anc_p) + (shares * prix_ouv)) / n_s
                session.execute(text("UPDATE portfolio SET shares=:s, avg_price=:p WHERE username=:u AND LOWER(ticker)=LOWER(:t)"),
                                {"s": n_s, "p": n_p, "u": username, "t": ticker_o})
            else:
                session.execute(text("INSERT INTO portfolio VALUES (:u, :t, :s, :p)"),
                                {"u": username, "t": ticker_o, "s": shares, "p": prix_ouv})
            session.execute(text("INSERT INTO transactions (username, ticker, shares, price, total, timestamp) "
                                 "VALUES (:u, :t, :s, :p, :tot, :time)"),
                            {"u": username, "t": ticker_o, "s": shares, "p": prix_ouv,
                             "tot": cout, "time": now_str})
            enregistrer_frais(session, username, "transaction", frais_fixe_o, ticker_o)
            enregistrer_frais(session, username, "conversion", frais_conv_o, ticker_o)
            session.execute(
                text("UPDATE ordres_en_attente SET statut='execute', prix_execution=:p, "
                     "shares=:s, execute_le=:e, note=:n WHERE id=:i"),
                {"p": prix_ouv, "s": shares, "e": now_str,
                 "n": f"Exécuté à l'ouverture du {date_exec}.", "i": int(ordre['id'])})
            session.commit()

_JOURS_FR = ["lun.", "mar.", "mer.", "jeu.", "ven.", "sam.", "dim."]
_MOIS_FR = ["janv.", "févr.", "mars", "avr.", "mai", "juin", "juil.",
            "août", "sept.", "oct.", "nov.", "déc."]


def _date_fr_courte(date_iso):
    """« 2026-11-03 » devient « mar. 3 nov. ». Chaîne inchangée si le
    format est inattendu."""
    try:
        d = datetime.strptime(str(date_iso), "%Y-%m-%d").date()
        return f"{_JOURS_FR[d.weekday()]} {d.day} {_MOIS_FR[d.month - 1]}"
    except Exception:
        return str(date_iso)


DELAI_AFFICHAGE_ORDRE_REGLE_S = 120


def _ordre_regle_visible(execute_le, maintenant):
    """Vrai si la carte de résultat d'un ordre réglé (exécuté ou
    annulé) doit encore paraître : seulement pendant les 2 minutes
    qui suivent son règlement (règle de Mathieu, 3 nov. 2026).
    Sans heure de règlement lisible, la carte ne paraît pas.
    Fonction pure, testable."""
    try:
        regle_le = datetime.strptime(str(execute_le)[:19], "%Y-%m-%d %H:%M:%S")
    except Exception:
        return False
    ecart = (maintenant.replace(tzinfo=None) - regle_le).total_seconds()
    return 0 <= ecart <= DELAI_AFFICHAGE_ORDRE_REGLE_S


def _html_recu(d):
    """Reçu de transaction en HTML : la confirmation d'un achat ou
    d'une vente, d'un ordre en attente, d'une annulation ou d'un refus,
    dans la famille visuelle des cartes du site plutôt que les messages
    par défaut de Streamlit (demande de Mathieu, 6 nov. 2026).
    d : genre, titre, sous, lignes [(libellé, montant)], total
    (libellé, montant) ou None, pied. Fonction pure, testable."""
    import html as _h
    genre = str(d.get("genre") or "")
    classe = "recu"
    if genre in ("ordre", "refus", "annulation"):
        classe += " " + genre
    morceaux = [f"<div class='{classe}'>"]
    morceaux.append(f"<div class='recu-titre'>{_h.escape(str(d.get('titre') or ''))}</div>")
    if d.get("sous"):
        morceaux.append(f"<div class='recu-sous'>{_h.escape(str(d['sous']))}</div>")
    lignes = d.get("lignes") or []
    total = d.get("total")
    if lignes or total:
        morceaux.append("<table class='recu-lignes'>")
        for lib, mont in lignes:
            morceaux.append(f"<tr><td>{_h.escape(str(lib))}</td><td class='m'>{_h.escape(str(mont))}</td></tr>")
        if total:
            morceaux.append(f"<tr class='total'><td>{_h.escape(str(total[0]))}</td><td class='m'>{_h.escape(str(total[1]))}</td></tr>")
        morceaux.append("</table>")
    if d.get("pied"):
        morceaux.append(f"<div class='recu-pied'>{_h.escape(str(d['pied']))}</div>")
    morceaux.append("</div>")
    return "".join(morceaux)


def afficher_refus(raison):
    """Un refus d'ordre, dans la même forme éteinte que le reçu,
    plutôt que le bloc bourgogne par défaut. La raison reste en une
    phrase, dans le panneau, comme Mathieu l'a demandé le 30 oct."""
    st.markdown(_html_recu({"genre": "refus", "titre": "ORDRE REFUSÉ",
                            "sous": str(raison), "lignes": [],
                            "total": None, "pied": ""}),
                unsafe_allow_html=True)


def enrichir_historique_fifo(lignes):
    """Pour chaque vente, calcule le coût d'achat moyen des actions
    vendues (méthode FIFO : les premières achetées sont réputées les
    premières revendues) et le gain réalisé. Entrée : transactions en
    ordre chronologique avec shares signées ; sortie : la même liste,
    chaque vente enrichie de cout_achat_moyen et gain_realise (None si
    les achats retracés ne couvrent pas la vente : on n'invente pas un
    coût). Fonction pure, testée unitairement."""
    from collections import deque
    lots = {}
    out = []
    for lig in lignes:
        tk = str(lig['ticker']).upper()
        q = float(lig['shares'])
        px = float(lig['price'])
        copie = dict(lig)
        copie['cout_achat_moyen'] = None
        copie['gain_realise'] = None
        if q > 0:
            lots.setdefault(tk, deque()).append([q, px])
        elif q < 0:
            reste = -q
            cout = 0.0
            pris = 0.0
            file = lots.setdefault(tk, deque())
            while reste > 1e-9 and file:
                lot = file[0]
                prendre = min(lot[0], reste)
                cout += prendre * lot[1]
                pris += prendre
                lot[0] -= prendre
                reste -= prendre
                if lot[0] <= 1e-9:
                    file.popleft()
            if reste <= 1e-9 and pris > 0:
                moyen = cout / pris
                copie['cout_achat_moyen'] = moyen
                copie['gain_realise'] = (px - moyen) * pris
        out.append(copie)
    return out


# --- CONSOLE SUPERVISION : les outils de l'onglet, un par fonction
# (vague 2, 6 nov. 2026). L'onglet ne fait que choisir la section
# et appeler la fonction ; plus aucun menu déroulant empilé.

def sup_apercu(user):
    st.subheader("Aperçu enseignant de l'étape 2")
    st.caption("Simule la séance pour l'affichage seulement, sur ton écran : la bande de cotation défile comme en pleine séance et l'écran « le marché dort » disparaît. Les transactions, les prix et ce que les élèves voient ne changent pas.")
    st.toggle("Simuler la séance (affichage seulement)", key="demo_jour")



def sup_groupes(user):
    st.markdown("<div style=\'font-family:'Bebas Neue','Work Sans',sans-serif;font-size:1.25rem;letter-spacing:0.06em;color:#FFFFFF;margin:14px 0 6px;\'>GROUPES : INSCRIPTIONS ET CHANGEMENTS DE GROUPE</div>", unsafe_allow_html=True)
    st.info(
        "Fermez un groupe quand tous ses élèves sont inscrits : plus personne "
        "ne pourra s'y inscrire. Les élèves déjà inscrits ne sont pas affectés. "
        "Rouvrir un groupe réactive les inscriptions."
    )
    try:
        _fermes = set(conn.query("SELECT groupe FROM groupes_fermes", ttl=0)['groupe'].tolist())
    except Exception:
        _fermes = set()
    _comptes = conn.query("SELECT groupe, COUNT(*) as n FROM users GROUP BY groupe", ttl=0)
    _nb_par_groupe = {str(r['groupe']): int(r['n']) for _, r in _comptes.iterrows()} if not _comptes.empty else {}
    for g in LISTE_GROUPES:
        _nb = _nb_par_groupe.get(g, 0)
        _est_ferme = g in _fermes
        cg1, cg2, cg3 = st.columns([3, 2, 2])
        cg1.markdown(f"**{g}** — {_nb} inscrit(s)")
        cg2.markdown("Fermé" if _est_ferme else "Ouvert")
        if _est_ferme:
            if cg3.button("Rouvrir", key=f"rouvrir_{g}", use_container_width=True):
                with conn.session as session:
                    session.execute(text("DELETE FROM groupes_fermes WHERE groupe = :g"), {"g": g})
                    session.commit()
                st.rerun()
        else:
            if cg3.button("Fermer", key=f"fermer_{g}", use_container_width=True):
                with conn.session as session:
                    session.execute(text("INSERT INTO groupes_fermes (groupe) VALUES (:g)"), {"g": g})
                    session.commit()
                st.rerun()



def sup_fiche(user):
    grp_p = st.selectbox("Groupe :", ["Tous les groupes"] + LISTE_GROUPES, key="prof_grp")

    if grp_p == "Tous les groupes":
        e_list = conn.query("SELECT username FROM users ORDER BY username", ttl=0)['username'].tolist()
    else:
        e_list = conn.query("SELECT username FROM users WHERE groupe=:g ORDER BY username", params={"g": grp_p}, ttl=0)['username'].tolist()

    if e_list:
        e_sel = st.selectbox("Élève à inspecter :", e_list)
        e_data_df = conn.query("SELECT cash, groupe FROM users WHERE username=:u", params={"u": e_sel}, ttl=0)

        if not e_data_df.empty:
            e_data = e_data_df.iloc[0]
            e_cash, e_grp = float(e_data['cash']), e_data['groupe']
            e_pos = conn.query("SELECT ticker, shares, avg_price FROM portfolio WHERE username=:u", params={"u": e_sel}, ttl=0)

            pos_rows = []
            e_val_act = 0.0
            if not e_pos.empty:
                e_tks = e_pos['ticker'].unique().tolist()
                prix_dict_prof = obtenir_prix_groupes(e_tks)

                for _, row in e_pos.iterrows():
                    tk = str(row['ticker'])
                    sh = int(row['shares'])
                    pm = float(row['avg_price'] or 0.0)
                    _info_prof = prix_dict_prof.get(tk.upper())
                    pa_live = _info_prof["cad"] if _info_prof else None
                    pa = pa_live if pa_live is not None else pm
                    val = sh * pa
                    pnl = (pa - pm) * sh
                    pnl_pct = ((pa - pm) / pm * 100) if pm > 0 else 0.0
                    e_val_act += val

                    dv_prof = _info_prof["devise"] if _info_prof else devise_naturelle(tk)
                    pa_aff_p = _info_prof["natif"] if (_info_prof and _info_prof["natif"] is not None) else vers_natif(pa, dv_prof)
                    fmt_pa = fmt_prix(pa_aff_p, dv_prof)
                    fmt_pm = fmt_prix(vers_natif(pm, dv_prof), dv_prof)

                    pos_rows.append({
                        "Action": tk,
                        "Quantité": sh,
                        "Prix Moyen": fmt_pm,
                        "Prix Actuel": fmt_pa,
                        "Valeur Totale": f"${val:,.2f}",
                        "Gain / Perte": f"${pnl:+,.2f}",
                        "Rendement": f"{pnl_pct:+.2f}%"
                    })

            e_tot = e_cash + e_val_act
            e_pnl = e_tot - 10000.00
            e_perf = (e_pnl / 10000.00) * 100

            col_top_prof1, col_top_prof2, col_top_prof3 = st.columns([2.5, 1, 1])
            with col_top_prof1:
                st.markdown(f"#### Fiche d'investisseur : **{e_sel}** ({e_grp})")

            with col_top_prof2:
                if st.button(f"Réinitialiser {e_sel}", use_container_width=True):
                    with conn.session as session:
                        session.execute(text("UPDATE users SET cash = 10000.00 WHERE username = :u"), {"u": e_sel})
                        session.execute(text("DELETE FROM portfolio WHERE username = :u"), {"u": e_sel})
                        session.execute(text("DELETE FROM transactions WHERE username = :u"), {"u": e_sel})
                        session.commit()
                    st.session_state['flash_msg'] = ("success", f"Le compte de {e_sel} a été réinitialisé à 10 000 $ !")
                    st.rerun()

            with col_top_prof3:
                if st.button("Supprimer le compte", use_container_width=True):
                    with conn.session as session:
                        session.execute(text("DELETE FROM portfolio WHERE username = :u"), {"u": e_sel})
                        session.execute(text("DELETE FROM transactions WHERE username = :u"), {"u": e_sel})
                        session.execute(text("DELETE FROM users WHERE username = :u"), {"u": e_sel})
                        session.commit()
                    st.session_state['flash_msg'] = ("success", f"Le profil de {e_sel} a été définitivement supprimé !")
                    st.rerun()

            col_g1, col_g2 = st.columns([3, 1])
            with col_g1:
                _idx_grp = LISTE_GROUPES.index(e_grp) if e_grp in LISTE_GROUPES else 0
                _nv_grp = st.selectbox("Changer le groupe de l'élève :", LISTE_GROUPES, index=_idx_grp, key=f"nvgrp_{e_sel}")
            with col_g2:
                st.markdown("<br>", unsafe_allow_html=True)
                if st.button("Changer de groupe", use_container_width=True, key=f"btngrp_{e_sel}"):
                    if _nv_grp != e_grp:
                        with conn.session as session:
                            session.execute(text("UPDATE users SET groupe = :g WHERE username = :u"), {"g": _nv_grp, "u": e_sel})
                            session.commit()
                        st.session_state['flash_msg'] = ("success", f"{e_sel} est maintenant dans le groupe {_nv_grp}.")
                    else:
                        st.session_state['flash_msg'] = ("success", f"{e_sel} est déjà dans le groupe {_nv_grp}.")
                    st.rerun()

            col_t1, col_t2, col_t3, col_t4 = st.columns(4)
            col_t1.markdown(f"<div class='kpi-card'><div class='kpi-label'>Disponible (Cash)</div><div class='kpi-value'>${e_cash:,.2f}</div></div>", unsafe_allow_html=True)
            col_t2.markdown(f"<div class='kpi-card'><div class='kpi-label'>Actions Possédées</div><div class='kpi-value'>${e_val_act:,.2f}</div></div>", unsafe_allow_html=True)
            col_t3.markdown(f"<div class='kpi-card'><div class='kpi-label'>Valeur Totale</div><div class='kpi-value'>${e_tot:,.2f}</div></div>", unsafe_allow_html=True)
            classe_delta_p = "kpi-delta up" if e_pnl >= 0 else "kpi-delta down"
            fleche_delta_p = "▲" if e_pnl >= 0 else "▼"
            classe_carte_p = "kpi-card kpi-up" if e_pnl >= 0 else "kpi-card kpi-down"
            col_t4.markdown(f"<div class='{classe_carte_p}'><div class='kpi-label'>Gains / Pertes</div><div class='kpi-value'>${e_pnl:+,.2f}</div><div class='{classe_delta_p}'>{fleche_delta_p} {e_perf:+.2f}%</div></div>", unsafe_allow_html=True)

            st.markdown("##### Portefeuille Détaillé")
            if pos_rows:
                st.dataframe(pd.DataFrame(pos_rows), use_container_width=True, hide_index=True)
            else:
                st.info("Cet élève n'a aucune position ouverte actuellement.")

            st.markdown("##### Historique des Transactions")
            tx_e = conn.query("SELECT timestamp, CASE WHEN shares > 0 THEN 'ACHAT' ELSE 'VENTE' END as type, ticker, ABS(shares) as shares, price, total FROM transactions WHERE username=:u ORDER BY id DESC", params={"u": e_sel}, ttl=0)
            if not tx_e.empty:
                tx_e.columns = ["Date & Heure", "Type", "Action", "Quantité", "Prix ($ CAD)", "Total ($ CAD)"]
                st.dataframe(tx_e, use_container_width=True, hide_index=True)
            else:
                st.info("Aucune transaction enregistrée.")
    else:
        st.info("Aucun élève trouvé dans ce groupe.")




def sup_mdp(user):
    st.markdown("<div style=\'font-family:'Bebas Neue','Work Sans',sans-serif;font-size:1.25rem;letter-spacing:0.06em;color:#FFFFFF;margin:14px 0 6px;\'>GESTION DES MOTS DE PASSE (SUPABASE)</div>", unsafe_allow_html=True)
    st.warning("Ce lien ouvre la console Supabase, où les mots de passe des élèves peuvent être modifiés directement. À utiliser avec prudence.")
    code_supabase = st.text_input("Code d'accès :", type="password", key="code_supabase", autocomplete="off")
    try:
        _code_attendu = st.secrets.get("CODE_SUPABASE")
    except Exception:
        _code_attendu = None
    if _code_attendu and code_supabase == _code_attendu:
        st.link_button("Ouvrir la console Supabase", "https://supabase.com/dashboard/project/pixbjedmpvvjqswltzkq/editor/17585?schema=public")
    elif code_supabase:
        st.error("Code incorrect.")



def sup_suspension(user):
    st.subheader("Suspension d'un joueur")
    st.caption("Un joueur suspendu peut se connecter et voir son portefeuille, mais aucun bouton ne fonctionne sur sa page, sauf Déconnexion. La suspension dure jusqu'à ce que tu la lèves ici.")
    try:
        susp_df = conn.query("SELECT username, depuis FROM joueurs_suspendus ORDER BY depuis", ttl=0)
    except Exception:
        susp_df = pd.DataFrame(columns=["username", "depuis"])
    susp_noms = set(susp_df['username'].tolist()) if not susp_df.empty else set()
    if susp_noms:
        st.markdown("**Suspendus en ce moment :** " + " · ".join(
            f"{r['username']} (depuis le {r['depuis']})" for _, r in susp_df.iterrows()))
    else:
        st.caption("Aucun joueur suspendu en ce moment.")
    users_susp = conn.query("SELECT username, groupe FROM users ORDER BY groupe, username", ttl=0)
    choix_susp = [r['username'] for _, r in users_susp.iterrows()
                  if r['username'] != "MathieuSavary"
                  and not str(r['groupe'] or "").strip().lower().startswith("enseignant")]
    sel_susp = st.selectbox("Joueur :", choix_susp, key="sel_suspension")
    if sel_susp in susp_noms:
        st.warning(f"{sel_susp} est suspendu en ce moment.")
        if st.button("Lever la suspension", key="btn_lever_suspension", use_container_width=True):
            lever_suspension_joueur(sel_susp)
            st.success(f"Suspension levée pour {sel_susp}.")
            st.rerun()
    elif st.button("Suspendre ce joueur", key="btn_suspendre", use_container_width=True):
        suspendre_joueur(sel_susp)
        st.success(f"{sel_susp} est suspendu. Il peut se connecter et voir son portefeuille, mais ne peut plus rien faire sauf se déconnecter.")
        st.rerun()



def sup_correction(user):
    st.markdown("<div style=\'font-family:'Bebas Neue','Work Sans',sans-serif;font-size:1.25rem;letter-spacing:0.06em;color:#FFFFFF;margin:14px 0 6px;\'>CORRECTION RÈGLE 9H30 (ACHATS PRÉ-MARCHÉ)</div>", unsafe_allow_html=True)
    st.info(
        "Détecte automatiquement les achats avant 9h30 sur une période donnée, "
        "pour des actions dont la clôture du jour de bourse précédent était sous 5 $, "
        "puis annule d'un coup toutes les transactions du jour fautif pour ces actions "
        "(achats et ventes), comme si elles n'avaient jamais existé : cash remboursé, "
        "portefeuille recalculé."
    )
    from datetime import date as _date, timedelta as _td
    _auj = _date.today()
    col_d1, col_d2 = st.columns(2)
    with col_d1:
        date_debut = st.date_input("Du", value=_auj - _td(days=7), key="d9_debut")
    with col_d2:
        date_fin = st.date_input("Au", value=_auj, key="d9_fin")
    if st.button("Analyser la période", key="btn_analyse_9h30"):
        ds0, ds1 = date_debut.isoformat(), date_fin.isoformat()
        with st.spinner(f"Analyse du {ds0} au {ds1} en cours..."):
            viol = analyser_violations_9h30(ds0, ds1)
            if not viol.empty:
                viol = calculer_gains_9h30(viol)
        if viol.empty:
            st.success(f"Aucun achat fautif détecté entre le {ds0} et le {ds1} avant 9h30.")
            st.session_state.pop('violations_9h30', None)
        else:
            st.session_state['violations_9h30'] = viol
            st.rerun()
    viol = st.session_state.get('violations_9h30')
    if viol is not None and not viol.empty:
        resume = viol.groupby(['date', 'username', 'ticker']).agg(
            total_achats=('total', 'sum'),
            prix_achat=('prix_achat', 'first'),
            cloture_veille=('cloture_veille', 'first'),
            gain_estime=('gain_estime', 'first'),
            heures_achat=('heures_achat', 'first'),
            heures_vente=('heures_vente', 'first')
        ).reset_index()
        resume.columns = ["Date", "Élève", "Action", "Total achats ($)", "Prix achat ($)", "Clôture veille ($)", "Gain estimé ($)", "Achat à", "Revente à"]
        resume["Sélectionner"] = True
        st.markdown(f"**{len(resume)} cas élève/action/jour concernés, {len(viol)} achats fautifs au total.** Coche les cas à annuler.")
        edited = st.data_editor(
            resume,
            column_config={"Sélectionner": st.column_config.CheckboxColumn("Sélectionner")},
            disabled=[c for c in resume.columns if c != "Sélectionner"],
            hide_index=True, use_container_width=True, key="editor_9h30"
        )
        sel = edited[edited["Sélectionner"]]
        st.markdown(f"**{len(sel)} cas sélectionnés.**")
        if st.button("Annuler la sélection", key="btn_exec_9h30", disabled=sel.empty):
            cles = set(zip(sel["Date"], sel["Élève"], sel["Action"]))
            viol_sel = viol[viol.apply(lambda r: (r['date'], r['username'], r['ticker']) in cles, axis=1)]
            with st.spinner("Annulation en cours..."):
                nb_c, nb_tx, tot_cash = executer_annulation_9h30(viol_sel)
            st.session_state.pop('violations_9h30', None)
            st.success(f"Terminé : {nb_tx} transactions annulées pour {nb_c} cas. Cash total réajusté : ${tot_cash:+,.2f}.")
            st.rerun()



def sup_frais(user):
    st.markdown("<div style=\'font-family:'Bebas Neue','Work Sans',sans-serif;font-size:1.25rem;letter-spacing:0.06em;color:#FFFFFF;margin:14px 0 6px;\'>FRAIS DU MODE VRAIE BOURSE (PAR ÉLÈVE)</div>", unsafe_allow_html=True)
    st.info("Frais prélevés depuis le passage au mode vraie bourse : 10 $ par transaction, 1,5 % de conversion sur les titres américains, 0,5 % de frais de gestion le 1er de chaque mois (dès le 1er novembre).")
    frais_sup = conn.query(
        "SELECT f.username AS username, u.groupe AS groupe, f.type AS type, SUM(f.montant) AS tot "
        "FROM frais f JOIN users u ON u.username = f.username GROUP BY f.username, u.groupe, f.type",
        ttl=0)
    if frais_sup.empty:
        st.write("Aucun frais prélevé pour le moment.")
    else:
        piv = frais_sup.pivot_table(index=["username", "groupe"], columns="type", values="tot", aggfunc="sum", fill_value=0.0).reset_index()
        for col_f in ["transaction", "conversion", "gestion"]:
            if col_f not in piv.columns:
                piv[col_f] = 0.0
        piv["total"] = piv["transaction"] + piv["conversion"] + piv["gestion"]
        piv = piv.sort_values("total", ascending=False)
        tot_tx = float(piv["transaction"].sum())
        tot_cv = float(piv["conversion"].sum())
        tot_ge = float(piv["gestion"].sum())
        st.markdown(f"**Total de la classe : {tot_tx + tot_cv + tot_ge:,.2f} $** (transactions {tot_tx:,.2f} $ • conversion {tot_cv:,.2f} $ • gestion {tot_ge:,.2f} $)")
        aff = piv.rename(columns={"username": "Élève", "groupe": "Groupe", "transaction": "Transactions ($)", "conversion": "Conversion ($)", "gestion": "Gestion ($)", "total": "Total ($)"})
        st.dataframe(aff[["Élève", "Groupe", "Transactions ($)", "Conversion ($)", "Gestion ($)", "Total ($)"]], use_container_width=True, hide_index=True)



def sup_photos(user):
    st.markdown("<div style=\'font-family:'Bebas Neue','Work Sans',sans-serif;font-size:1.25rem;letter-spacing:0.06em;color:#FFFFFF;margin:14px 0 6px;\'>PHOTOS DES MENEURS (PODIUM DU CLASSEMENT)</div>", unsafe_allow_html=True)
    st.info("Choisis un élève, dépose sa photo officielle : elle apparaîtra dans sa carte du podium s'il est dans les 3 premiers. Sans photo, la carte affiche ses initiales.")
    _df_users_ph = conn.query("SELECT username FROM users ORDER BY username", ttl=0)
    _liste_eleves_ph = _df_users_ph['username'].tolist() if not _df_users_ph.empty else []
    if _liste_eleves_ph:
        eleve_photo = st.selectbox("Élève :", _liste_eleves_ph, key="eleve_photo_podium")
        photo_existante = obtenir_photo(eleve_photo)
        if photo_existante:
            st.image(f"data:image/jpeg;base64,{photo_existante}", width=90)
            st.caption("Photo actuelle de cet élève.")
        fichier_meneur = st.file_uploader("Photo de l'élève (jpg ou png)", type=["jpg", "jpeg", "png"], key="uploader_photo_meneur")
        col_ph1, col_ph2 = st.columns(2)
        if fichier_meneur and col_ph1.button("Enregistrer la photo", use_container_width=True):
            try:
                b64_meneur = traiter_photo(fichier_meneur.getvalue())
                with conn.session as session:
                    session.execute(text("INSERT INTO photos (username, image, maj) VALUES (:u, :i, :d) ON CONFLICT (username) DO UPDATE SET image=:i, maj=:d"),
                                    {"u": eleve_photo, "i": b64_meneur, "d": datetime.now(ZoneInfo("America/Toronto")).strftime("%Y-%m-%d %H:%M:%S")})
                    session.commit()
                obtenir_photo.clear()
                st.success(f"Photo enregistrée pour {eleve_photo}.")
                st.rerun()
            except Exception:
                st.error("Cette image n'a pas pu être traitée. Essaie un autre fichier.")
        if photo_existante and col_ph2.button("Retirer la photo", use_container_width=True):
            with conn.session as session:
                session.execute(text("DELETE FROM photos WHERE username=:u"), {"u": eleve_photo})
                session.commit()
            obtenir_photo.clear()
            st.rerun()



def afficher_missions(user):
    """La carte des missions de l'étape 2 (affichage seulement). Depuis
    la vague 2 du 6 nov. 2026, elle ne paraît que dans l'onglet Marché
    & Analyse, plus dans le bloc global du haut de page. Lectures
    propres à la fonction, mêmes règles qu'avant."""
    pos_df = conn.query("SELECT ticker, shares, avg_price FROM portfolio WHERE username=:u",
                        params={"u": user}, ttl=0)
    mois_court = datetime.now(ZoneInfo("America/Toronto")).strftime("%Y-%m")
    nb_titres = int(pos_df['ticker'].nunique()) if not pos_df.empty else 0
    ach_mois_q = conn.query(
        "SELECT COUNT(*) AS n FROM transactions WHERE username=:u AND shares > 0 AND timestamp LIKE :m",
        params={"u": user, "m": mois_court + "%"}, ttl=0)
    nb_achats_mois = int(ach_mois_q.iloc[0]['n']) if not ach_mois_q.empty else 0
    regle_titres_ok = nb_titres >= 4
    regle_achats_ok = nb_achats_mois >= 5
    prix_dict = {}
    valeur_positions = 0.0
    if not pos_df.empty:
        prix_dict = obtenir_prix_groupes(pos_df['ticker'].unique().tolist())
        for _, r_v in pos_df.iterrows():
            _i_v = prix_dict.get(str(r_v['ticker']).strip().upper())
            _px_v = _i_v["cad"] if _i_v and _i_v.get("cad") is not None else float(r_v['avg_price'] or 0.0)
            valeur_positions += _px_v * float(r_v['shares'])
    cash_q = conn.query("SELECT cash FROM users WHERE username=:u", params={"u": user}, ttl=0)
    cash_val = float(cash_q.iloc[0]['cash']) if not cash_q.empty else 0.0
    valeur_totale = cash_val + valeur_positions
    nb_pos_conformes = 0
    nb_pos_trop_petites = 0
    nb_pos_trop_grosses = 0
    if not pos_df.empty and valeur_totale > 0:
        for _, row_m in pos_df.iterrows():
            tk_m = str(row_m['ticker']).strip().upper()
            _info_m = prix_dict.get(tk_m)
            px_m = _info_m["cad"] if _info_m else None
            px_m = px_m if px_m is not None else float(row_m['avg_price'] or 0.0)
            part_m = px_m * float(row_m['shares']) / valeur_totale * 100
            if part_m < 2.0:
                nb_pos_trop_petites += 1
            elif part_m > 25.0:
                nb_pos_trop_grosses += 1
            else:
                nb_pos_conformes += 1
    mission_positions_ok = (nb_titres > 0 and nb_pos_trop_petites == 0)

    def ligne_mission(titre, sous, valeur, cible, ok):
        if ok:
            coche = "<div style='width:26px;height:26px;border-radius:50%;border:2.5px solid #34D399;background:rgba(52,211,153,0.14);color:#34D399;flex:none;display:flex;align-items:center;justify-content:center;font-weight:800;font-size:15px;'>✓</div>"
            droite = f"<div style='font-weight:800;font-size:15px;min-width:42px;text-align:right;'>{valeur} / {cible}</div>"
        else:
            coche = "<div style='width:26px;height:26px;border-radius:50%;border:2.5px solid #3D3D3D;flex:none;'></div>"
            pct = min(100, int(valeur / cible * 100)) if cible else 0
            droite = (f"<div style='background:#2B2B2B;border-radius:20px;height:11px;width:110px;flex:none;overflow:hidden;'>"
                      f"<div style='height:100%;background:#E50914;width:{pct}%;'></div></div>"
                      f"<div style='font-weight:800;font-size:15px;min-width:42px;text-align:right;'>{valeur} / {cible}</div>")
        return (f"<div style='display:flex;align-items:center;gap:14px;padding:9px 0;border-bottom:1px solid #262626;'>"
                f"{coche}<div style='flex:1;font-size:16px;font-weight:600;color:#FFFFFF;'>{titre}"
                f"<small style='display:block;color:#9CA3AF;font-weight:400;font-size:13.5px;'>{sous}</small></div>{droite}</div>")

    manques = []
    if not regle_titres_ok:
        manques.append(f"ajoute {4 - nb_titres} titre(s) différent(s)")
    if not regle_achats_ok:
        manques.append(f"fais {5 - nb_achats_mois} achat(s) de plus ce mois-ci")
    if nb_pos_trop_petites:
        manques.append("une de tes positions vaut moins de 2 % de ton compte : elle ne compte presque pas")
    if manques:
        pied_missions = "Pour tes missions : " + " et ".join(manques) + "."
    elif nb_titres:
        pied_missions = "Missions accomplies. Beau travail !"
    else:
        pied_missions = ""
    if nb_pos_trop_grosses:
        pied_missions += " Une de tes positions dépasse 25 % de ton compte. Quand un seul titre pèse aussi lourd, tout ton compte bouge avec lui : pense à répartir ton risque."
    pos_valeur = nb_pos_conformes + nb_pos_trop_grosses
    pos_cible = max(nb_titres, 1)
    pos_ok = mission_positions_ok and nb_pos_trop_grosses == 0
    carte_missions = (
        "<div style='background:linear-gradient(180deg,#262626 0%,#1A1A1A 100%);border:1px solid rgba(255,255,255,0.12);"
        "border-top:3px solid #E50914;border-radius:14px;padding:18px 22px 10px;margin:6px 0 14px;"
        "box-shadow:0 16px 32px -14px rgba(0,0,0,0.9);'>"
        "<div style=\"font-family:'Bebas Neue','Work Sans',sans-serif;font-size:1.8rem;letter-spacing:0.06em;color:#FFFFFF;line-height:1;\">TES MISSIONS <span style='color:#E50914;'>ÉTAPE 2</span></div>"
        "<div style='color:#9CA3AF;font-size:0.92rem;margin:3px 0 4px;'>Les missions montrent où tu en es. Elles ne donnent ni argent ni pouvoir.</div>"
        + ligne_mission("Posséder 4 titres différents", "La diversification minimale, toujours en vigueur.", nb_titres, 4, regle_titres_ok)
        + ligne_mission("Faire 5 achats ce mois-ci", "Le minimum mensuel, toujours en vigueur.", nb_achats_mois, 5, regle_achats_ok)
        + ligne_mission("Garder chaque position entre 2 % et 25 % de ton compte", "Assez grosse pour compter, jamais assez pour tout risquer sur un seul titre.", pos_valeur, pos_cible, pos_ok)
        + (f"<div style='color:#9CA3AF;font-size:0.88rem;padding:8px 0 4px;'>{pied_missions}</div>" if pied_missions else "")
        + "</div>")
    st.markdown(carte_missions, unsafe_allow_html=True)


def afficher_ordres_en_attente(username):
    """Bloc « Mes ordres en attente », en haut de page : une carte par
    ordre, dans la famille des cartes KPI avec un accent cyan réservé
    aux ordres en attente. Bouton d'annulation sous chaque carte en
    cours ; cartes de résultat pendant 2 minutes après le règlement
    de l'ordre, puis elles disparaissent.
    Le bloc ne paraît que s'il y a quelque chose à montrer."""
    en_attente = ordres_en_attente_pour(username)
    maintenant = datetime.now(ZoneInfo("America/Toronto"))
    try:
        tous_regles = conn.query(
            "SELECT ticker, montant_cad, statut, prix_execution, shares, note, session_execution, execute_le, sens, parts "
            "FROM ordres_en_attente WHERE username=:u AND statut <> 'en_attente' "
            "ORDER BY id DESC",
            params={"u": username}, ttl=0)
    except Exception:
        tous_regles = pd.DataFrame()
    if not tous_regles.empty:
        regles = tous_regles[tous_regles['execute_le'].apply(
            lambda e: _ordre_regle_visible(e, maintenant))]
    else:
        regles = tous_regles
    if en_attente.empty and regles.empty:
        return
    st.markdown(
        "<div style='color:#E5E7EB;font-size:0.8rem;font-weight:800;letter-spacing:0.1em;"
        "text-transform:uppercase;margin:6px 0 8px;'>Mes ordres en attente · exécution au prix d'ouverture</div>",
        unsafe_allow_html=True)
    if not en_attente.empty:
        boutons_css = "<style>"
        cols = st.columns(len(en_attente))
        for i, (_, o) in enumerate(en_attente.iterrows()):
            oid = int(o['id'])
            tk = str(o['ticker']).upper()
            with cols[i]:
                _est_vente = str(o.get('sens') or 'ACHAT').upper() == 'VENTE'
                if _est_vente:
                    _montant_carte = f"VENTE · {int(o['parts'] or 0)} actions réservées"
                    _detail_carte = (f"Ordre de vente. S'exécute à l'ouverture, au prix d'ouverture<br>"
                                     f"({_date_fr_courte(o['session_execution'])} · 9 h 30)")
                else:
                    _montant_carte = f"ACHAT · ${float(o['montant_cad']):,.2f} réservés"
                    _detail_carte = (f"S'exécute à l'ouverture, au prix d'ouverture<br>"
                                     f"({_date_fr_courte(o['session_execution'])} · 9 h 30)")
                _classe_carte = "ordre-card vente" if _est_vente else "ordre-card"
                _classe_badge = "ordre-badge vente" if _est_vente else "ordre-badge"
                _lib_badge = "Vente en attente" if _est_vente else "Achat en attente"
                _coul_btn = "245, 158, 11" if _est_vente else "34, 211, 238"
                _coul_btn_txt = "#FBBF24" if _est_vente else "#22D3EE"
                st.markdown(
                    f"<div class='{_classe_carte}'>"
                    f"<div class='ordre-ticker'>{tk}</div>"
                    f"<div class='ordre-montant'>{_montant_carte}</div>"
                    f"<div class='ordre-detail'>{_detail_carte}</div>"
                    f"<span class='{_classe_badge}'><span class='ordre-point'></span>{_lib_badge}</span>"
                    f"</div>",
                    unsafe_allow_html=True)
                boutons_css += (
                    f'div[class~="st-key-annuler_ordre_{oid}"] button {{'
                    "background: #101418 !important;"
                    f"border: 1px solid rgba({_coul_btn}, 0.6) !important;"
                    "}"
                    f'div[class~="st-key-annuler_ordre_{oid}"] button p {{'
                    f"color: {_coul_btn_txt} !important; font-weight: 700 !important;"
                    "}")
                if st.button("Annuler l'ordre", key=f"annuler_ordre_{oid}", use_container_width=True):
                    if annuler_ordre_en_attente(username, oid):
                        st.session_state['flash_msg'] = ("recu", {"genre": "annulation", "titre": "ORDRE ANNULÉ", "sous": "", "lignes": [], "total": None, "pied": "La réservation est libérée : le montant ou les actions sont de retour dans ton compte."})
                        st.rerun()
        boutons_css += "</style>"
        st.markdown(boutons_css, unsafe_allow_html=True)
    for _, o in regles.iterrows():
        tk = str(o['ticker']).upper()
        vente_o = str(o.get('sens') or 'ACHAT').upper() == 'VENTE'
        if o['statut'] == 'execute':
            if vente_o:
                _montant_regle = f"{int(o['shares'])} actions vendues à ${float(o['prix_execution']):,.2f}"
                _detail_regle = f"Vendu au prix d'ouverture du {_date_fr_courte(o['session_execution'])}"
            else:
                _montant_regle = f"{int(o['shares'])} actions à ${float(o['prix_execution']):,.2f}"
                _detail_regle = (f"Acheté au prix d'ouverture du {_date_fr_courte(o['session_execution'])} "
                                 f"(ordre de ${float(o['montant_cad']):,.2f})")
            st.markdown(
                f"<div class='ordre-card exec'>"
                f"<div class='ordre-ticker'>{tk}</div>"
                f"<div class='ordre-montant'>{_montant_regle}</div>"
                f"<div class='ordre-detail'>{_detail_regle}</div>"
                f"<span class='ordre-badge exec'>Exécuté</span>"
                f"</div>",
                unsafe_allow_html=True)
        else:
            libelle = "Annulé par toi" if o['statut'] == 'annule_eleve' else "Annulé"
            if vente_o:
                try:
                    _n_parts = int(o['parts'] or 0)
                except (TypeError, ValueError):
                    _n_parts = 0
                note = str(o['note'] or "Tes actions sont de retour dans ton portefeuille.")
                _montant_regle = f"{_n_parts} actions remises dans ton portefeuille"
            else:
                note = str(o['note'] or "Montant remboursé au complet.")
                _montant_regle = f"${float(o['montant_cad']):,.2f} remboursés"
            st.markdown(
                f"<div class='ordre-card annule'>"
                f"<div class='ordre-ticker'>{tk}</div>"
                f"<div class='ordre-montant'>{_montant_regle}</div>"
                f"<div class='ordre-detail'>{note}</div>"
                f"<span class='ordre-badge annule'>{libelle}</span>"
                f"</div>",
                unsafe_allow_html=True)


# --- VALIDATION STRICTE DES INSTRUMENTS AUTORISÉS ---
# Règle de Mathieu (17 oct. 2026) : actions et FNB seulement, cotés uniquement
# sur TSX (Toronto), NYSE ou Nasdaq. Aucune crypto, devise, future ni indice ;
# aucun marché OTC, TSX-V, NEO, CSE ni bourse étrangère.
# Codes d'échange Yahoo : TOR=TSX, NYQ=NYSE, NMS/NGM/NCM=Nasdaq,
# PCX=NYSE Arca, ASE=NYSE American, BTS=Cboe BZX (lieux de cotation des FNB).
EXCHANGES_AUTORISES = {'TOR', 'NYQ', 'NMS', 'NGM', 'NCM', 'PCX', 'ASE', 'BTS'}
TYPES_AUTORISES = {'EQUITY', 'ETF'}

def _symbole_syntaxe_ok(symbol):
    """Pré-filtre sans appel réseau : rejette devises (=X), futures (=F),
    indices (^...), cryptos (-USD) et symboles vides."""
    s = (symbol or '').upper().strip()
    if not s:
        return False
    return not ('^' in s or '=' in s or s.endswith('-USD'))

def instrument_autorise(symbol, exch_code="", exch_disp="", quote_type=""):
    """Vrai si l'instrument peut être acheté dans le jeu."""
    s = (symbol or '').upper().strip()
    if not _symbole_syntaxe_ok(s):
        return False
    # Seul le suffixe .TO (TSX Toronto) est accepté ; toute autre bourse
    # à suffixe (TSX-V, NEO, CSE, Paris, Tokyo...) est rejetée.
    if '.' in s and not s.endswith('.TO'):
        return False
    # Si l'info d'échange est fournie, elle doit être TSX/NYSE/Nasdaq.
    codes = set(f"{exch_code} {exch_disp}".upper().split())
    if codes and not (codes & EXCHANGES_AUTORISES):
        return False
    # Si le type d'instrument est fourni, actions et FNB seulement.
    qt = (quote_type or '').upper().strip()
    if qt and qt not in TYPES_AUTORISES:
        return False
    return True

# --- CONVERSION AUTOMATIQUE USD -> CAD ---
# L'élève ne fait aucun calcul : tous les prix sont affichés et comptabilisés
# en dollars canadiens. Un seul appel Yahoo par heure, partagé par les 200+
# élèves via le cache (aucun ralentissement).
@st.cache_resource
def _memo_dernier_taux():
    """Dernier taux USD/CAD valide, gardé tant que l'app roule. Filet de
    sécurité : une coupure des sources ne doit jamais faire retomber les
    conversions à « aucune conversion » (prix US alors traités comme des
    CAD : valeur totale amputée d'environ 2 600 $ à l'écran sur un seul
    compte, vu le 21 oct. 2026)."""
    return {"taux": None, "echec": 0.0}


@st.cache_data(ttl=1800, show_spinner=False)
def _taux_usdcad_sources():
    """Taux USD/CAD depuis les sources, dans l'ordre. Lève une exception
    si aucune source ne répond : Streamlit ne met pas les exceptions en
    cache, donc un échec ne fige pas le taux pour 30 minutes."""
    # 1) Yahoo (temps réel)
    try:
        r = yf.Ticker('USDCAD=X').fast_info.get('lastPrice')
        if r is not None and not pd.isna(r) and float(r) > 0:
            return float(r)
    except Exception:
        pass
    # 2) Frankfurter (taux de référence quotidien, indépendant de Yahoo)
    try:
        d = requests.get('https://api.frankfurter.dev/v1/latest?base=USD&symbols=CAD',
                         timeout=5).json()
        v = float(d['rates']['CAD'])
        if v > 0:
            return v
    except Exception:
        pass
    raise RuntimeError("Taux USD/CAD indisponible (toutes sources)")


def obtenir_taux_usdcad():
    memo = _memo_dernier_taux()
    t = None
    # Pendant une panne totale, on ne retente les sources qu'une fois par
    # minute ; entre-temps, le dernier taux connu sert les conversions.
    if datetime.now().timestamp() - memo.get("echec", 0.0) > 60:
        try:
            t = _taux_usdcad_sources()
        except Exception:
            memo["echec"] = datetime.now().timestamp()
    if t:
        memo["taux"] = t
        return t
    return memo["taux"]

def convertir_vers_cad(prix, devise):
    """Convertit un prix vers le dollar canadien (comptabilité du compte)."""
    if prix is None:
        return None
    try:
        p = float(prix)
    except (TypeError, ValueError):
        return None
    if pd.isna(p):
        return None
    if str(devise or '').upper() == 'USD':
        taux = obtenir_taux_usdcad()
        if taux:
            return round(p * taux, 4)
    return round(p, 4)


# --- AFFICHAGE EN DEVISE NATURELLE (depuis le 20 oct. 2026) ---
# Les prix s'affichent dans la devise du titre (ex. $ US pour Apple), comme
# sur les vrais sites. Le compte de l'élève reste en CAD : la conversion
# s'applique au moment de l'achat/vente, avec l'ajustement de change
# indiqué. La comptabilité (transactions, prix moyens, totaux) ne change
# pas : toujours en CAD.
def devise_naturelle(ticker_symbol):
    """Devise naturelle d'après le symbole : suffixe canadien (.TO, .V,
    .NE, .CN) = CAD, sinon USD (NYSE/Nasdaq). Affichage seulement."""
    t = str(ticker_symbol or '').upper().strip()
    return 'CAD' if '.' in t else 'USD'


def vers_natif(prix_cad, devise):
    """Convertit un montant CAD vers la devise naturelle, au taux du jour.
    AFFICHAGE seulement : la comptabilité reste en CAD."""
    if prix_cad is None:
        return None
    try:
        p = float(prix_cad)
    except (TypeError, ValueError):
        return None
    if pd.isna(p):
        return None
    if str(devise or '').upper() == 'USD':
        taux = obtenir_taux_usdcad()
        if taux:
            return round(p / taux, 4)
    return round(p, 4)


def fmt_prix(valeur, devise=None):
    """Formate un prix affiché : $X,XX, suffixe ' US' si devise USD."""
    if valeur is None:
        return "n/d"
    v = float(valeur)
    s = f"${v:,.4f}" if v < 1 else f"${v:,.2f}"
    if str(devise or '').upper() == 'USD':
        s += " US"
    return s

# --- FONCTION DE PROTECTION ANTI-SPAM (COOLDOWN DE 3 SECONDES) ---
def verifier_cooldown(username, delai_secondes=3):
    res = conn.query("SELECT timestamp FROM transactions WHERE username=:u ORDER BY id DESC LIMIT 1", params={"u": username}, ttl=0)
    if not res.empty:
        try:
            dernier_temps = datetime.strptime(str(res.iloc[0]['timestamp']), "%Y-%m-%d %H:%M:%S")
            maintenant = datetime.now(ZoneInfo("America/Toronto")).replace(tzinfo=None)
            if (maintenant - dernier_temps).total_seconds() < delai_secondes:
                return False
        except Exception:
            pass
    return True

# --- DESIGN STYLE NETFLIX PREMIUM PLUS (COUCHE VISUELLE SEULEMENT) ---
st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Bebas+Neue&family=Work+Sans:wght@400;500;600;700;800&display=swap');

    html, body, [class*="css"] {
        font-family: 'Work Sans', -apple-system, BlinkMacSystemFont, sans-serif;
    }

    .stApp {
        background: radial-gradient(1200px 520px at 50% -8%, rgba(229, 9, 20, 0.16), rgba(20, 20, 20, 0) 62%), #141414 !important;
        background-color: #141414 !important;
        color: #FFFFFF !important;
    }

    #MainMenu, footer, header { visibility: hidden; }

    ::selection { background: #E50914; color: #FFFFFF; }

    ::-webkit-scrollbar { width: 10px; height: 10px; }
    ::-webkit-scrollbar-track { background: #141414; }
    ::-webkit-scrollbar-thumb { background: #3A3A3A; border-radius: 8px; }
    ::-webkit-scrollbar-thumb:hover { background: #E50914; }

    .stApp h1 { font-size: 2.7rem !important; }
    .stApp h2 { font-size: 2.3rem !important; }
    .stApp h3 { font-size: 2rem !important; }
    .stApp h1, .stApp h2, .stApp h3, .stApp h4, .stApp h5, .stApp h6 {
        font-family: 'Bebas Neue', 'Work Sans', sans-serif !important;
        font-weight: 400 !important;
        letter-spacing: 0.05em !important;
        color: #FFFFFF !important;
    }
    .stApp h3, .stApp h4, .stApp h5 {
        border-left: 4px solid #E50914;
        padding-left: 14px;
    }

    .stApp .stMarkdown p, .stApp .stMarkdown li {
        color: #FFFFFF;
    }
    div[data-testid="stWidgetLabel"] p, .stApp label {
        color: #FFFFFF !important;
        font-weight: 600 !important;
    }
    div[data-testid="stRadio"] label, div[data-testid="stRadio"] label p {
        color: #FFFFFF !important;
    }

    .brand-banner {
        background: linear-gradient(120deg, #000000 0%, #161616 55%, #2B0A0C 100%);
        border-radius: 16px;
        padding: 28px 36px;
        color: #FFFFFF;
        margin-bottom: 24px;
        box-shadow: 0 22px 44px -18px rgba(0, 0, 0, 0.95), 0 0 44px -8px rgba(229, 9, 20, 0.65);
        display: flex;
        justify-content: space-between;
        align-items: center;
        border: 1px solid rgba(229, 9, 20, 0.5);
        border-bottom: 3px solid #E50914;
        animation: fadeDown 0.55s ease both;
        position: relative;
        overflow: hidden;
    }
    .brand-banner::after {
        content: "";
        position: absolute;
        top: 0;
        left: -80%;
        width: 55%;
        height: 100%;
        background: linear-gradient(105deg, rgba(255,255,255,0) 0%, rgba(255,255,255,0.10) 50%, rgba(255,255,255,0) 100%);
        transform: skewX(-18deg);
        animation: sheen 4.5s ease-in-out infinite;
        pointer-events: none;
    }
    .brand-title {
        font-family: 'Bebas Neue', 'Work Sans', sans-serif;
        font-size: 3.1rem;
        letter-spacing: 0.06em;
        line-height: 1;
        color: #FFFFFF;
        margin: 0;
        text-shadow: 0 0 28px rgba(229, 9, 20, 0.6);
    }
    .brand-subtitle {
        color: #FFFFFF;
        font-size: 0.92rem;
        font-weight: 500;
        margin-top: 6px;
    }
    .brand-badge {
        background: #E50914;
        border: none;
        padding: 7px 18px;
        border-radius: 6px;
        font-size: 0.8rem;
        font-weight: 800;
        color: #FFFFFF;
        letter-spacing: 0.08em;
        text-transform: uppercase;
        white-space: nowrap;
        box-shadow: 0 8px 20px -8px rgba(229, 9, 20, 0.9);
    }

    @keyframes fadeDown {
        from { opacity: 0; transform: translateY(-8px); }
        to { opacity: 1; transform: translateY(0); }
    }
    @keyframes sheen {
        0%, 55% { left: -80%; }
        85%, 100% { left: 130%; }
    }
    @keyframes fadeUp {
        from { opacity: 0; transform: translateY(10px); }
        to { opacity: 1; transform: translateY(0); }
    }
    @media (prefers-reduced-motion: reduce) {
        .brand-banner, .brand-banner::after, .kpi-card, .podium-card,
        .custom-table, .mon-rang, .kpi-up, .kpi-down, .ordre-card, .ordre-point { animation: none !important; }
        .kpi-card { transition: none !important; }
    }

    /* --- CARTES KPI SUR MESURE --- */
    .kpi-card {
        background: linear-gradient(180deg, #262626 0%, #1A1A1A 100%);
        border: 1px solid rgba(255, 255, 255, 0.12);
        border-top: 3px solid #E50914;
        border-radius: 14px;
        padding: 18px 22px 16px 22px;
        box-shadow: 0 16px 32px -14px rgba(0, 0, 0, 0.9);
        transition: transform 0.3s ease, box-shadow 0.3s ease, border-color 0.3s ease;
        animation: fadeUp 0.5s ease both;
        margin-bottom: 8px;
    }
    div[data-testid="stHorizontalBlock"] > div:nth-child(1) .kpi-card { animation-delay: 0.00s; }
    div[data-testid="stHorizontalBlock"] > div:nth-child(2) .kpi-card { animation-delay: 0.08s; }
    div[data-testid="stHorizontalBlock"] > div:nth-child(3) .kpi-card { animation-delay: 0.16s; }
    div[data-testid="stHorizontalBlock"] > div:nth-child(4) .kpi-card { animation-delay: 0.24s; }
    .kpi-card:hover {
        transform: translateY(-4px) scale(1.03);
        border-color: rgba(229, 9, 20, 0.65);
        border-top-color: #E50914;
        box-shadow: 0 26px 44px -14px rgba(0, 0, 0, 0.95), 0 0 32px -6px rgba(229, 9, 20, 0.7);
    }

    /* --- CARTES ORDRES EN ATTENTE (prix d'ouverture) ---
       Même famille que les cartes KPI, accent cyan : une couleur
       réservée aux ordres en attente sur la plateforme. */
    section[data-testid="stSidebar"] { background: #0A0A0A; border-right: 1px solid #262626; min-width: 206px !important; max-width: 206px !important; width: 206px !important; }
    button[data-testid="stSidebarCollapseButton"], div[data-testid="stSidebarCollapseButton"] { display: none !important; }
    div[data-testid="stSidebarCollapsedControl"], div[data-testid="collapsedControl"] { visibility: visible !important; display: flex !important; position: fixed !important; top: 58px !important; left: 0 !important; z-index: 1000001 !important; background: #E50914 !important; color: #FFFFFF !important; border-radius: 0 10px 10px 0 !important; padding: 10px 12px !important; box-shadow: 0 10px 22px -6px rgba(229, 9, 20, 0.65) !important; opacity: 1 !important; }
    .ordre-card {
        background: linear-gradient(180deg, #262626 0%, #1A1A1A 100%);
        border: 1px solid rgba(34, 211, 238, 0.35);
        border-top: 3px solid #22D3EE;
        border-radius: 14px;
        padding: 14px 18px 12px 18px;
        box-shadow: 0 16px 32px -14px rgba(0, 0, 0, 0.9), 0 0 24px -8px rgba(34, 211, 238, 0.45);
        animation: fadeUp 0.5s ease both;
        margin-bottom: 8px;
    }
    .ordre-card.exec { border-color: rgba(52, 211, 153, 0.4); border-top-color: #34D399; box-shadow: 0 16px 32px -14px rgba(0, 0, 0, 0.9), 0 0 24px -8px rgba(52, 211, 153, 0.4); }
    .ordre-card.vente { border-color: rgba(245, 158, 11, 0.4); border-top-color: #F59E0B; box-shadow: 0 16px 32px -14px rgba(0, 0, 0, 0.9), 0 0 24px -8px rgba(245, 158, 11, 0.45); }
    .ordre-card.vente .ordre-point { background: #F59E0B; animation-name: ordrePulseAmbre; }
    @keyframes ordrePulseAmbre { 0%, 100% { opacity: 1; box-shadow: 0 0 0 0 rgba(245, 158, 11, 0.5); } 50% { opacity: 0.55; box-shadow: 0 0 0 5px rgba(245, 158, 11, 0); } }
    .ordre-card.annule { border-color: rgba(255, 255, 255, 0.14); border-top-color: #6B7280; box-shadow: 0 16px 32px -14px rgba(0, 0, 0, 0.9); opacity: 0.8; }
    .ordre-ticker {
        font-family: 'Bebas Neue', 'Work Sans', sans-serif;
        font-size: 1.9rem; line-height: 1; color: #FFFFFF; letter-spacing: 0.04em;
    }
    .ordre-montant { font-size: 1.05rem; font-weight: 800; color: #FFFFFF; font-variant-numeric: tabular-nums; margin-top: 4px; }
    .ordre-detail { color: #9CA3AF; font-size: 0.85rem; margin-top: 3px; line-height: 1.45; }
    .ordre-badge {
        display: inline-flex; align-items: center; gap: 7px;
        margin-top: 9px; padding: 3px 12px; border-radius: 999px;
        font-size: 0.78rem; font-weight: 800; letter-spacing: 0.05em; text-transform: uppercase;
        background: rgba(34, 211, 238, 0.14); color: #22D3EE; border: 1px solid rgba(34, 211, 238, 0.55);
    }
    .ordre-badge.exec { background: rgba(16, 185, 129, 0.16); color: #34D399; border-color: rgba(16, 185, 129, 0.55); }
    .ordre-badge.vente { background: rgba(245, 158, 11, 0.15); color: #FBBF24; border-color: rgba(245, 158, 11, 0.55); }
    .ordre-badge.annule { background: rgba(107, 114, 128, 0.16); color: #9CA3AF; border-color: rgba(107, 114, 128, 0.55); }
    .ordre-point { width: 8px; height: 8px; border-radius: 50%; background: #22D3EE; animation: ordrePulse 1.6s ease-in-out infinite; }
    @keyframes ordrePulse { 0%, 100% { opacity: 1; box-shadow: 0 0 0 0 rgba(34, 211, 238, 0.5); } 50% { opacity: 0.55; box-shadow: 0 0 0 5px rgba(34, 211, 238, 0); } }

    /* Reçus de transaction : remplacent les messages par défaut
       (vert kaki, bourgogne) à l'achat et à la vente. */
    .recu {
        background: linear-gradient(180deg, #262626 0%, #1A1A1A 100%);
        border: 1px solid rgba(255, 255, 255, 0.12);
        border-top: 6px solid #E50914;
        border-radius: 14px;
        padding: 20px 22px 16px 22px;
        box-shadow: 0 16px 32px -14px rgba(0, 0, 0, 0.9);
        animation: fadeUp 0.5s ease both;
        margin: 10px 0 14px 0;
    }
    .recu.ordre { border-top-color: #22D3EE; }
    .recu.refus, .recu.annulation { border-top-color: #6B7280; }
    .recu-titre {
        font-family: 'Bebas Neue', 'Work Sans', sans-serif;
        font-size: 2.2rem; line-height: 1; color: #FFFFFF; letter-spacing: 0.05em;
    }
    .recu.refus .recu-titre, .recu.annulation .recu-titre { color: #D1D5DB; }
    .recu-sous { color: #D1D5DB; font-size: 0.98rem; font-weight: 700; margin-top: 3px; }
    .recu-lignes { width: 100%; border-collapse: collapse; margin-top: 8px; }
    .recu-lignes td { padding: 3px 0; color: #E5E7EB; font-size: 0.97rem; }
    .recu-lignes td.m { text-align: right; font-weight: 700; color: #FFFFFF; font-variant-numeric: tabular-nums; white-space: nowrap; padding-left: 16px; }
    .recu-lignes tr.total td { border-top: 1px solid rgba(255, 255, 255, 0.28); padding-top: 7px; font-weight: 800; color: #FFFFFF; }
    .recu-pied { color: #9CA3AF; font-size: 0.88rem; margin-top: 8px; line-height: 1.45; }

    /* Cartes de vente rapide */
    div[data-testid="stVerticalBlockBorderWrapper"] {
        background: linear-gradient(180deg, #1E1E1E 0%, #161616 100%) !important;
        border: 1px solid #2E2E2E !important;
        border-radius: 14px !important;
    }
    div[data-testid="stVerticalBlockBorderWrapper"]:hover {
        border-color: rgba(229, 9, 20, 0.45) !important;
    }
    .kpi-label {
        color: #FFFFFF;
        font-size: 0.78rem;
        text-transform: uppercase;
        font-weight: 800;
        letter-spacing: 0.08em;
        margin-bottom: 6px;
    }
    .kpi-value {
        font-family: 'Bebas Neue', 'Work Sans', sans-serif;
        font-size: 2.45rem;
        line-height: 1;
        color: #FFFFFF;
        letter-spacing: 0.03em;
        font-variant-numeric: tabular-nums;
        white-space: nowrap;
    }
    .kpi-delta {
        display: inline-block;
        margin-top: 8px;
        padding: 3px 12px;
        border-radius: 999px;
        font-size: 0.85rem;
        font-weight: 800;
        font-variant-numeric: tabular-nums;
    }
    .kpi-delta.up {
        background: rgba(16, 185, 129, 0.18);
        color: #34D399;
        border: 1px solid rgba(16, 185, 129, 0.55);
    }
    .kpi-delta.down {
        background: rgba(239, 68, 68, 0.16);
        color: #F87171;
        border: 1px solid rgba(239, 68, 68, 0.55);
    }
    .kpi-up {
        border-color: rgba(16, 185, 129, 0.55);
        border-top-color: #34D399;
        background: linear-gradient(180deg, rgba(16, 185, 129, 0.18) 0%, #1A1A1A 62%);
        box-shadow: 0 16px 32px -14px rgba(0, 0, 0, 0.9), 0 0 46px -4px rgba(16, 185, 129, 0.8);
        animation: fadeUp 0.5s ease both, pulseUp 2.8s ease-in-out 0.6s infinite;
    }
    .kpi-down {
        border-color: rgba(239, 68, 68, 0.55);
        border-top-color: #F87171;
        background: linear-gradient(180deg, rgba(239, 68, 68, 0.18) 0%, #1A1A1A 62%);
        box-shadow: 0 16px 32px -14px rgba(0, 0, 0, 0.9), 0 0 46px -4px rgba(239, 68, 68, 0.8);
        animation: fadeUp 0.5s ease both, pulseDown 2.8s ease-in-out 0.6s infinite;
    }
    @keyframes pulseUp {
        0%, 100% { box-shadow: 0 16px 32px -14px rgba(0, 0, 0, 0.9), 0 0 34px -6px rgba(16, 185, 129, 0.55); }
        50% { box-shadow: 0 16px 32px -14px rgba(0, 0, 0, 0.9), 0 0 56px -2px rgba(16, 185, 129, 0.95); }
    }
    @keyframes pulseDown {
        0%, 100% { box-shadow: 0 16px 32px -14px rgba(0, 0, 0, 0.9), 0 0 34px -6px rgba(239, 68, 68, 0.55); }
        50% { box-shadow: 0 16px 32px -14px rgba(0, 0, 0, 0.9), 0 0 56px -2px rgba(239, 68, 68, 0.95); }
    }
    .kpi-up .kpi-value { color: #34D399; }
    .kpi-down .kpi-value { color: #F87171; }
    .kpi-up:hover {
        border-color: rgba(16, 185, 129, 0.8);
        box-shadow: 0 26px 44px -14px rgba(0, 0, 0, 0.95), 0 0 54px -4px rgba(16, 185, 129, 0.9);
    }
    .kpi-down:hover {
        border-color: rgba(239, 68, 68, 0.8);
        box-shadow: 0 26px 44px -14px rgba(0, 0, 0, 0.95), 0 0 54px -4px rgba(239, 68, 68, 0.9);
    }

    /* --- CARTE-CITATION (MARCHÉ) --- */
    .quote-card {
        display: flex;
        align-items: center;
        gap: 22px;
        flex-wrap: wrap;
        background: linear-gradient(120deg, #1E1E1E 0%, #161616 100%);
        border: 1px solid #2E2E2E;
        border-left: 4px solid #E50914;
        border-radius: 14px;
        padding: 16px 24px;
        margin-bottom: 10px;
        box-shadow: 0 16px 32px -16px rgba(0, 0, 0, 0.9);
        animation: fadeUp 0.5s ease both;
        position: relative;
        overflow: hidden;
    }
    .quote-card::after {
        content: attr(data-tk);
        position: absolute;
        right: 14px;
        top: 50%;
        transform: translateY(-50%);
        font-family: 'Bebas Neue', 'Work Sans', sans-serif;
        font-size: 5.4rem;
        letter-spacing: 0.04em;
        color: rgba(255, 255, 255, 0.05);
        pointer-events: none;
    }
    .quote-card > div { position: relative; z-index: 1; }
    .quote-ticker {
        font-family: 'Bebas Neue', 'Work Sans', sans-serif;
        font-size: 2.9rem;
        line-height: 1;
        color: #FFFFFF;
        letter-spacing: 0.04em;
    }
    .quote-price {
        font-family: 'Bebas Neue', 'Work Sans', sans-serif;
        font-size: 2.5rem;
        line-height: 1;
        color: #FFFFFF;
        font-variant-numeric: tabular-nums;
    }
    .quote-var {
        padding: 5px 14px;
        border-radius: 999px;
        font-weight: 800;
        font-variant-numeric: tabular-nums;
    }
    .quote-var.up {
        background: rgba(16, 185, 129, 0.18);
        color: #34D399;
        border: 1px solid rgba(16, 185, 129, 0.55);
    }
    .quote-var.down {
        background: rgba(239, 68, 68, 0.16);
        color: #F87171;
        border: 1px solid rgba(239, 68, 68, 0.55);
    }
    .quote-card.up {
        box-shadow: 0 16px 32px -16px rgba(0, 0, 0, 0.9), 0 0 36px -8px rgba(16, 185, 129, 0.55);
    }
    .quote-card.down {
        box-shadow: 0 16px 32px -16px rgba(0, 0, 0, 0.9), 0 0 36px -8px rgba(239, 68, 68, 0.55);
    }

    /* --- PODIUM DU CLASSEMENT --- */
    .pos-carte {
        background: linear-gradient(180deg, #262626 0%, #1A1A1A 100%);
        border: 1px solid rgba(255, 255, 255, 0.12);
        border-top: 3px solid #E50914;
        border-radius: 14px;
        padding: 14px 16px 12px;
        box-shadow: 0 16px 32px -14px rgba(0, 0, 0, 0.9);
        flex: 1 1 280px;
        max-width: 430px;
        animation: fadeUp 0.5s ease both;
    }
    .pos-sym { font-family: 'Bebas Neue', 'Work Sans', sans-serif; font-size: 1.75rem; line-height: 1; color: #FFFFFF; letter-spacing: 0.04em; }
    .pos-val { font-size: 1.08rem; font-weight: 800; color: #FFFFFF; font-variant-numeric: tabular-nums; }
    .pos-detail { color: #9CA3AF; font-size: 0.88rem; margin-top: 5px; line-height: 1.5; }
    .pos-detail b { color: #E5E7EB; }
    .pos-gain { font-size: 1rem; font-weight: 800; margin-top: 6px; font-variant-numeric: tabular-nums; }
    .meneur-card {
        border: 1px solid rgba(255, 215, 0, 0.35);
        border-top: 3px solid #FFD700;
        border-radius: 14px;
        padding: 12px 18px;
        margin: 2px 0 12px 0;
        background: linear-gradient(180deg, #262626 0%, #1A1A1A 100%);
        box-shadow: 0 16px 32px -14px rgba(0, 0, 0, 0.9);
        animation: fadeUp 0.5s ease both;
    }
    .meneur-titre { color: #FFD700; font-size: 0.78rem; font-weight: 800; letter-spacing: 0.1em; text-transform: uppercase; }
    .meneur-nom { font-family: 'Bebas Neue', 'Work Sans', sans-serif; font-size: 1.9rem; line-height: 1.05; color: #FFFFFF; letter-spacing: 0.04em; margin-top: 2px; }
    .meneur-val { color: #34D399; font-size: 1.15rem; font-weight: 800; font-variant-numeric: tabular-nums; }
    .meneur-detail { color: #9CA3AF; font-size: 0.85rem; margin-top: 3px; line-height: 1.45; }
    .podium-card {
        border: 1px solid rgba(255, 255, 255, 0.12);
        border-top: 4px solid #FFFFFF;
        border-radius: 14px;
        padding: 16px 20px;
        margin-bottom: 10px;
        background: linear-gradient(180deg, #262626 0%, #1A1A1A 100%);
        box-shadow: 0 16px 32px -14px rgba(0, 0, 0, 0.9);
        animation: fadeUp 0.5s ease both;
    }
    .podium-or {
        border-top-color: #FFD700;
        background: linear-gradient(180deg, rgba(255, 215, 0, 0.38) 0%, rgba(255, 215, 0, 0.14) 45%, rgba(26, 26, 26, 1) 100%);
        box-shadow: 0 16px 32px -14px rgba(0, 0, 0, 0.9), 0 0 30px -6px rgba(255, 215, 0, 0.55);
    }
    .podium-or .podium-rang { color: #FFD700; }
    .podium-argent {
        border-top-color: #C0C0C0;
        background: linear-gradient(180deg, rgba(192, 192, 192, 0.34) 0%, rgba(192, 192, 192, 0.12) 45%, rgba(26, 26, 26, 1) 100%);
        box-shadow: 0 16px 32px -14px rgba(0, 0, 0, 0.9), 0 0 30px -6px rgba(192, 192, 192, 0.5);
    }
    .podium-argent .podium-rang { color: #E8E8E8; }
    .podium-bronze {
        border-top-color: #CD7F32;
        background: linear-gradient(180deg, rgba(205, 127, 50, 0.38) 0%, rgba(205, 127, 50, 0.14) 45%, rgba(26, 26, 26, 1) 100%);
        box-shadow: 0 16px 32px -14px rgba(0, 0, 0, 0.9), 0 0 30px -6px rgba(205, 127, 50, 0.55);
    }
    .podium-bronze .podium-rang { color: #E09A5A; }
    .podium-rang {
        font-family: 'Bebas Neue', 'Work Sans', sans-serif;
        font-size: 2.1rem;
        line-height: 1;
        color: #FFFFFF;
    }
    .podium-nom {
        font-weight: 800;
        font-size: 1.05rem;
        color: #FFFFFF;
        margin-top: 4px;
    }
    .podium-suspendu {
        display: inline-block;
        margin-top: 6px;
        padding: 2px 12px;
        background: #E50914;
        color: #FFFFFF;
        font-weight: 800;
        font-size: 0.8rem;
        letter-spacing: 0.14em;
        border-radius: 4px;
    }
    .podium-val {
        font-family: 'Bebas Neue', 'Work Sans', sans-serif;
        font-size: 1.55rem;
        line-height: 1.1;
        color: #FFFFFF;
        font-variant-numeric: tabular-nums;
    }
    .podium-perf {
        font-weight: 700;
        font-size: 0.9rem;
        color: #FFFFFF;
        font-variant-numeric: tabular-nums;
    }
    .podium-jour {
        margin-top: 10px;
        padding: 7px 10px;
        border: 1px solid rgba(255, 255, 255, 0.22);
        border-radius: 9px;
        background: rgba(0, 0, 0, 0.35);
        font-size: 0.82rem;
        font-weight: 700;
        color: #FFFFFF;
        font-variant-numeric: tabular-nums;
    }
    .podium-jour .hausse { color: #4ADE80; }
    .podium-jour .baisse { color: #FF6B6B; }
    .podium-photo-wrap {
        position: relative;
        width: 80px;
        margin: 2px auto 10px;
    }
    .podium-photo {
        width: 80px; height: 80px;
        border-radius: 50%;
        object-fit: cover;
        display: block;
        border: 3px solid #FFFFFF;
        box-shadow: 0 10px 22px rgba(0, 0, 0, 0.55);
    }
    .podium-initiales {
        width: 80px; height: 80px;
        border-radius: 50%;
        display: flex; align-items: center; justify-content: center;
        font-family: 'Bebas Neue', 'Work Sans', sans-serif;
        font-size: 1.7rem; color: #FFFFFF;
        background: radial-gradient(circle at 32% 30%, #3d3d3d, #171717 72%);
        border: 3px solid #FFFFFF;
        box-shadow: 0 10px 22px rgba(0, 0, 0, 0.55);
    }
    .podium-or .podium-photo, .podium-or .podium-initiales { border-color: #FFD700; }
    .podium-argent .podium-photo, .podium-argent .podium-initiales { border-color: #E8E8E8; }
    .podium-bronze .podium-photo, .podium-bronze .podium-initiales { border-color: #E09A5A; }
    .podium-badge {
        position: absolute; right: -5px; bottom: -5px;
        width: 29px; height: 29px;
        border-radius: 50%;
        background: #FFFFFF; color: #111111;
        font-weight: 800; font-size: 0.95rem;
        display: flex; align-items: center; justify-content: center;
        border: 2px solid rgba(0, 0, 0, 0.25);
        box-shadow: 0 4px 10px rgba(0, 0, 0, 0.5);
    }
    .podium-or .podium-badge { background: #FFD700; }
    .podium-argent .podium-badge { background: #E8E8E8; }
    .podium-bronze .podium-badge { background: #E09A5A; }
    .podium-nom, .podium-val, .podium-perf, .podium-jour { text-align: center; }
    .podium-1 { animation-delay: 0.00s; }
    .podium-2 { animation-delay: 0.15s; }
    .podium-3 { animation-delay: 0.30s; }
    .podium-card {
        position: relative;
        overflow: hidden;
        transition: box-shadow 0.3s ease, transform 0.3s ease;
    }
    .podium-card > div { position: relative; z-index: 1; }
    .podium-or:hover {
        transform: translateY(-3px);
        box-shadow: 0 20px 38px -14px rgba(0, 0, 0, 0.95), 0 0 46px -4px rgba(255, 215, 0, 0.8);
    }
    .podium-argent:hover {
        transform: translateY(-3px);
        box-shadow: 0 20px 38px -14px rgba(0, 0, 0, 0.95), 0 0 46px -4px rgba(192, 192, 192, 0.75);
    }
    .podium-bronze:hover {
        transform: translateY(-3px);
        box-shadow: 0 20px 38px -14px rgba(0, 0, 0, 0.95), 0 0 46px -4px rgba(205, 127, 50, 0.8);
    }

    .mon-rang {
        display: flex;
        align-items: center;
        gap: 18px;
        flex-wrap: wrap;
        background: #1E1E1E;
        border: 1px solid #2E2E2E;
        border-left: 4px solid #E50914;
        border-radius: 12px;
        padding: 12px 20px;
        margin: 4px 0 14px 0;
    }
    .mon-rang-label {
        text-transform: uppercase;
        font-weight: 800;
        letter-spacing: 0.08em;
        font-size: 0.78rem;
        color: #FFFFFF;
    }
    .mon-rang-val {
        font-family: 'Bebas Neue', 'Work Sans', sans-serif;
        font-size: 1.9rem;
        line-height: 1;
        color: #FFFFFF;
    }
    .mon-rang-detail {
        font-weight: 700;
        color: #FFFFFF;
        font-variant-numeric: tabular-nums;
    }

    /* --- ENTRÉES ANIMÉES DES BLOCS SUR MESURE --- */
    .custom-table, .mon-rang {
        animation: fadeUp 0.5s ease both;
    }

    /* --- NAVIGATION EN BOUTONS --- */
    div[data-testid="stRadio"]:has(input[name="main_nav_radio"]) > label {
        display: none !important;
    }
    div[data-testid="stRadio"]:has(input[name="main_nav_radio"]) > div {
        flex-direction: row !important;
        gap: 12px !important;
        background-color: transparent !important;
        border: none !important;
        padding: 4px 0px 16px 0px !important;
        margin-bottom: 10px !important;
        flex-wrap: wrap !important;
    }
    div[data-testid="stRadio"]:has(input[name="main_nav_radio"]) label {
        background: #1F1F1F !important;
        border-radius: 999px !important;
        color: #FFFFFF !important;
        padding: 11px 22px !important;
        font-weight: 700 !important;
        font-size: 0.92rem !important;
        border: 1px solid #3A3A3A !important;
        box-shadow: 0 6px 16px -8px rgba(0, 0, 0, 0.85) !important;
        transition: all 0.15s ease !important;
        cursor: pointer !important;
        margin: 0 !important;
    }
    div[data-testid="stRadio"]:has(input[name="main_nav_radio"]) label:hover {
        color: #FFFFFF !important;
        border-color: rgba(229, 9, 20, 0.75) !important;
        transform: translateY(-2px) scale(1.03);
    }
    div[data-testid="stRadio"]:has(input[name="main_nav_radio"]) label:has(input:checked) {
        background: linear-gradient(180deg, #E50914 0%, #B00610 100%) !important;
        color: #FFFFFF !important;
        box-shadow: 0 10px 24px -8px rgba(229, 9, 20, 0.9) !important;
        border: 1px solid rgba(255, 130, 130, 0.45) !important;
        transform: translateY(0px) !important;
    }
    div[data-testid="stRadio"]:has(input[name="main_nav_radio"]) div[data-testid="stMarkdownContainer"] p {
        color: inherit !important;
        font-weight: 700 !important;
        font-size: 0.92rem !important;
    }

    /* Navigation qui reste en haut lors du défilement */
    .block-container div[data-testid="stVerticalBlock"] > div:has(input[name="main_nav_radio"]) {
        position: sticky;
        top: 0;
        z-index: 1000;
        background: rgba(20, 20, 20, 0.96);
        padding-top: 6px;
        border-bottom: 1px solid rgba(255, 255, 255, 0.08);
    }

    /* Boutons standards */
    .stButton>button, div[data-testid="stFormSubmitButton"]>button {
        border-radius: 10px !important;
        background: linear-gradient(180deg, #E50914 0%, #B00610 100%) !important;
        color: #FFFFFF !important;
        font-weight: 700 !important;
        border: 1px solid rgba(255, 130, 130, 0.4) !important;
        padding: 12px 24px !important;
        box-shadow: 0 10px 22px -10px rgba(229, 9, 20, 0.85) !important;
        transition: all 0.15s ease !important;
    }
    .stButton>button:hover, div[data-testid="stFormSubmitButton"]>button:hover {
        filter: brightness(1.15);
        transform: translateY(-2px) scale(1.02);
        box-shadow: 0 14px 26px -10px rgba(229, 9, 20, 0.95) !important;
    }
    .stButton>button:active, div[data-testid="stFormSubmitButton"]>button:active {
        transform: translateY(0px);
    }

    /* Bouton favoris : jaune ambre pour le distinguer du rouge/vert */
    div[data-testid="stButton"] button[kind="primary"] {
        background: linear-gradient(180deg, #F7C948 0%, #E0A800 100%) !important;
        border: 1px solid rgba(255, 220, 120, 0.55) !important;
        color: #1A1A1A !important;
        box-shadow: 0 10px 22px -10px rgba(247, 201, 72, 0.8) !important;
    }
    div[data-testid="stButton"] button[kind="primary"]:hover {
        filter: brightness(1.08);
        box-shadow: 0 14px 26px -10px rgba(247, 201, 72, 0.95) !important;
    }
    div[data-testid="stButton"] button[kind="primary"] p {
        color: #1A1A1A !important;
    }

    /* Boutons-liens vers les sites de finance */
    div[data-testid="stLinkButton"] > a {
        display: inline-flex !important;
        justify-content: center !important;
        align-items: center !important;
        width: 100% !important;
        border-radius: 9px !important;
        background: linear-gradient(180deg, #12161C 0%, #0B0E13 100%) !important;
        color: #EAF6FF !important;
        font-weight: 700 !important;
        font-size: 0.9rem !important;
        letter-spacing: 0.03em !important;
        text-decoration: none !important;
        border: 1px solid rgba(0, 191, 255, 0.75) !important;
        padding: 9px 16px !important;
        box-shadow: 0 0 20px -2px rgba(0, 191, 255, 0.55), inset 0 0 14px rgba(0, 191, 255, 0.12) !important;
        transition: all 0.15s ease !important;
    }
    div[data-testid="stLinkButton"] > a:hover {
        border-color: rgba(150, 228, 255, 1) !important;
        color: #FFFFFF !important;
        transform: translateY(-2px);
        box-shadow: 0 0 30px 0px rgba(0, 191, 255, 0.85), inset 0 0 18px rgba(0, 191, 255, 0.22) !important;
    }

    .stTextInput>div>div>input, .stNumberInput>div>div>input, .stSelectbox>div>div {
        background-color: #1F1F1F !important;
        color: #FFFFFF !important;
        border-radius: 10px !important;
        border: 1.5px solid #3A3A3A !important;
        padding: 11px 16px !important;
        font-weight: 600 !important;
    }
    .stTextInput>div>div>input:focus, .stNumberInput>div>div>input:focus {
        border-color: #E50914 !important;
        box-shadow: 0 0 0 1px #E50914 !important;
    }
    .stTextInput input::placeholder, .stNumberInput input::placeholder {
        color: #FFFFFF !important;
        opacity: 0.65;
    }
    .stSelectbox div[data-baseweb="select"] div {
        color: #FFFFFF !important;
    }

    div[data-baseweb="popover"] {
        background-color: #1F1F1F !important;
        border: 1px solid #3A3A3A !important;
        border-radius: 12px !important;
    }
    div[data-baseweb="popover"] li, div[data-baseweb="popover"] div {
        color: #FFFFFF !important;
    }

    div[data-testid="stDataFrame"] {
        border: 1px solid #2E2E2E !important;
        border-radius: 14px !important;
        overflow: hidden !important;
        box-shadow: 0 14px 30px -16px rgba(0, 0, 0, 0.9) !important;
    }

    div[data-testid="stAlert"] {
        border-radius: 12px !important;
        border: 1px solid rgba(255, 255, 255, 0.14) !important;
    }
    div[data-testid="stAlert"] p {
        color: #FFFFFF !important;
    }

    /* Carte de connexion (page d'accueil) */
    div[data-testid="stTabs"] {
        background: linear-gradient(180deg, #1E1E1E 0%, #161616 100%);
        border: 1px solid #2E2E2E;
        border-top: 3px solid #E50914;
        border-radius: 16px;
        padding: 12px 24px 24px 24px;
        box-shadow: 0 24px 48px -18px rgba(0, 0, 0, 0.95), 0 0 34px -12px rgba(229, 9, 20, 0.45);
        animation: fadeUp 0.55s ease both;
    }
    div[data-baseweb="tab-list"] { gap: 10px !important; }
    button[data-baseweb="tab"] {
        color: #FFFFFF !important;
        font-weight: 700 !important;
        font-size: 1rem !important;
    }
    button[data-baseweb="tab"][aria-selected="true"] { color: #FFFFFF !important; }
    div[data-baseweb="tab-highlight"] { background-color: #E50914 !important; }
    div[data-baseweb="tab-border"] { background-color: rgba(255, 255, 255, 0.14) !important; }

    .custom-table {
        width: 100%;
        border-collapse: collapse;
        background-color: #1A1A1A;
        border-radius: 14px;
        overflow: hidden;
        border: 1px solid #2E2E2E;
        margin-bottom: 24px;
        box-shadow: 0 14px 30px -16px rgba(0, 0, 0, 0.9);
    }
    .custom-table th {
        background-color: #262626;
        color: #FFFFFF;
        font-weight: 800;
        padding: 14px 18px;
        text-align: left;
        border-bottom: 2px solid #E50914;
        text-transform: uppercase;
        font-size: 0.78rem;
        letter-spacing: 0.05em;
    }
    .custom-table td {
        padding: 14px 18px;
        border-bottom: 1px solid rgba(255, 255, 255, 0.07);
        color: #FFFFFF;
        font-weight: 600;
        font-size: 0.93rem;
        font-variant-numeric: tabular-nums;
    }
    .custom-table tbody tr { transition: background-color 0.15s ease; }
    .custom-table tbody tr:hover { background-color: rgba(229, 9, 20, 0.10); }

    @media print {
        .custom-table { background-color: #FFFFFF !important; }
        .custom-table th, .custom-table td { color: #000000 !important; }
    }

    hr { border-color: rgba(255, 255, 255, 0.14) !important; margin: 28px 0 !important; }
    </style>
""", unsafe_allow_html=True)

# --- CACHE DES DONNÉES FINANCIÈRES EN TEMPS RÉEL SÉCURISÉ (TTL = 10s) ---
@st.cache_data(ttl=3600)
def _recherche_cached(query):
    """Recherche de symboles chez Yahoo, deux serveurs en relais.
    Lève une exception si les deux échouent : Streamlit ne met pas les
    exceptions en cache. Avant, un échec retournait une liste vide que
    le cache figeait pendant une heure, donc la recherche restait morte
    pour ce mot-là même après le retour de Yahoo (21 oct. 2026)."""
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'}
    derniere_erreur = None
    for hote in ("query2", "query1"):
        url = f"https://{hote}.finance.yahoo.com/v1/finance/search?q={query}&quotesCount=10&newsCount=0"
        try:
            r = requests.get(url, headers=headers, timeout=3)
            if r.status_code != 200:
                derniere_erreur = Exception(f"HTTP {r.status_code}")
                continue
            data = r.json()
            results = []
            for quote in data.get('quotes', []):
                symbol = quote.get('symbol')
                shortname = quote.get('shortname') or quote.get('longname') or symbol
                exch = quote.get('exchDisp') or quote.get('exchange') or ''
                type_disp = quote.get('typeDisp') or ''
                exch_code = (quote.get('exchange') or '').upper()

                if symbol and _symbole_syntaxe_ok(symbol):
                    if (type_disp in ['Equity', 'ETF', 'Action', 'Stock'] or not type_disp):
                        if not exch_code or exch_code in EXCHANGES_AUTORISES:
                            results.append({'symbol': symbol, 'label': f"{shortname} ({symbol}) — {exch}"})
            return results
        except Exception as e:
            derniere_erreur = e
            continue
    raise derniere_erreur or Exception("Recherche Yahoo indisponible")


def rechercher_symbole_universel(query):
    if not query or len(query.strip()) < 1: return []
    try:
        return _recherche_cached(query)
    except Exception:
        return []

@st.cache_data(ttl=120, show_spinner=False)
def obtenir_donnees_favoris(tickers_tuple):
    """Prix NATIF + variation du jour pour les favoris, en un seul appel groupé. {ticker: (prix_natif, var_pct, devise)}"""
    tickers_list = list(tickers_tuple)
    if not tickers_list:
        return {}
    try:
        clean = list(set([str(t).strip().upper() for t in tickers_list if t and str(t).strip()]))
        if not clean:
            return {}
        data = yf.Tickers(" ".join(clean))
        out = {}
        for tk in clean:
            try:
                fi = data.tickers[tk].fast_info
                devise = str(fi.get('currency') or 'CAD').upper()
                px = fi.get('lastPrice') or fi.get('regularMarketPrice') or fi.get('last_price')
                op = fi.get('open') or fi.get('openPrice')
                if px is not None and not pd.isna(px) and float(px) > 0:
                    px = float(px)
                    if op is not None and not pd.isna(op) and float(op) > 0:
                        vp = (px - float(op)) / float(op) * 100
                    else:
                        vp = 0.0
                    out[tk] = (round(px, 4), round(vp, 2), devise)
                else:
                    out[tk] = (None, None, devise)
            except Exception:
                out[tk] = (None, None, devise_naturelle(tk))
        return out
    except Exception:
        return {}

# --- GEL DES PRIX HORS HEURES ---
# Règle de Mathieu : les achats et les ventes restent permis en tout
# temps, mais entre la fermeture (16 h) et l'ouverture suivante
# (9 h 30), le prix ne bouge plus : c'est la clôture officielle de la
# dernière séance complétée. Sans ce gel, le « prix courant » de Yahoo
# continuait de dériver en séance prolongée (jusqu'à 20 h) et un
# aller-retour de soirée pouvait générer un profit à partir de rien
# (vu le 27 oct. 2026 : DAVI acheté 4,2149 $ à 19 h 24 et revendu
# 4,2177 $ à 23 h 36, alors que la clôture officielle était 3,00 $).

def _marche_ouvert():
    """Vrai pendant la séance régulière (lun-ven, 9 h 30 à 16 h,
    heure de Toronto)."""
    maintenant = datetime.now(ZoneInfo("America/Toronto"))
    if maintenant.weekday() >= 5:
        return False
    minutes = maintenant.hour * 60 + maintenant.minute
    return 9 * 60 + 30 <= minutes < 16 * 60


def _prochaine_ouverture(moment):
    """Prochaine ouverture de séance (lun-ven, 9 h 30, heure de
    Toronto) strictement après le moment donné. Fonction pure,
    testable. Les jours fériés ne sont pas déduits, comme partout
    ailleurs dans l'application."""
    candidat = moment.replace(hour=9, minute=30, second=0, microsecond=0)
    if moment.weekday() < 5 and moment < candidat:
        return candidat
    candidat += timedelta(days=1)
    while candidat.weekday() >= 5:
        candidat += timedelta(days=1)
    return candidat


def _duree_avant_ouverture(maintenant):
    """(heures, minutes) avant la prochaine ouverture. Pure, testable."""
    ouv = _prochaine_ouverture(maintenant)
    secondes = int((ouv - maintenant).total_seconds())
    return secondes // 3600, (secondes % 3600) // 60


@st.cache_data(ttl=300, show_spinner=False)
def _indices_bande():
    """Les trois indices de la bande de cotation (S&P/TSX, S&P 500,
    NASDAQ) : un seul appel groupé, caché 5 minutes pour tout le
    monde, aucun coût par élève. Retourne [] si indisponible."""
    try:
        noms = {"^GSPTSE": "S&P/TSX", "^GSPC": "S&P 500", "^IXIC": "NASDAQ"}
        data = yf.download(list(noms), period="5d", progress=False,
                           auto_adjust=False, threads=False)
        if data is None or data.empty or "Close" not in data:
            return []
        closes = data["Close"]
        sortie = []
        for sym, nom in noms.items():
            try:
                serie = closes[sym].dropna()
                if len(serie) >= 2:
                    dernier, avant = float(serie.iloc[-1]), float(serie.iloc[-2])
                    if avant > 0:
                        sortie.append((nom, dernier, (dernier / avant - 1) * 100))
            except Exception:
                continue
        return sortie
    except Exception:
        return []


def _elements_bande():
    """Éléments de la bande de cotation : les indices, puis les titres
    les plus détenus par les élèves, aux prix du relais. Chaque élément :
    (nom, prix affiché, variation du jour en % ou None)."""
    elements = []
    for nom, valeur, var in _indices_bande():
        elements.append((nom, f"{valeur:,.0f}", var))
    try:
        top = conn.query(
            "SELECT ticker FROM portfolio GROUP BY ticker "
            "ORDER BY COUNT(*) DESC LIMIT 8", ttl=120)
        tickers = [str(t).strip().upper() for t in top['ticker'].tolist()] if not top.empty else []
    except Exception:
        tickers = []
    if tickers:
        prix = obtenir_prix_groupes(tickers)
        for tk in tickers:
            info = prix.get(tk)
            if not info or info.get("natif") is None:
                continue
            var = None
            if info.get("prev_cad") and info.get("cad"):
                try:
                    var = (float(info["cad"]) / float(info["prev_cad"]) - 1) * 100
                except Exception:
                    var = None
            elements.append((tk, fmt_prix(info["natif"], info.get("devise") or devise_naturelle(tk)), var))
    return elements


def _variation_html(var):
    if var is None:
        return ""
    couleur = "#34D399" if var >= 0 else "#F87171"
    fleche = "▲" if var >= 0 else "▼"
    return f"<span style='color:{couleur};'>{fleche} {var:+.1f} %</span>"


def afficher_bande_cotation(en_seance):
    """Bande de cotation en haut de l'accueil (étape 2, affichage
    seulement) : pendant la séance, un ruban qui défile lentement ;
    marché fermé, une bande fixe avec les clôtures et la prochaine
    ouverture. Aucun appel réseau par élève : indices cachés, titres
    au prix du relais."""
    elements = _elements_bande()
    if not elements:
        return
    if en_seance:
        items = "".join(
            f"<span class='item'><b>{n}</b>&nbsp;{p}&nbsp;{_variation_html(v)}</span>"
            for n, p, v in elements)
        duree = max(24, 4 * len(elements))
        css = ("<style>body{margin:0;background:#111111;font-family:'Work Sans',sans-serif;overflow:hidden;"
               "border:1px solid #2E2E2E;border-radius:10px;box-sizing:border-box;height:44px}"
               ".track{display:flex;width:max-content;padding:11px 0;animation:bandeScroll " + str(duree) + "s linear infinite}"
               ".track:hover{animation-play-state:paused}"
               ".item{padding:0 22px;border-right:1px solid rgba(255,255,255,0.12);color:#FFFFFF;font-weight:600;white-space:nowrap;font-variant-numeric:tabular-nums}"
               ".item b{font-family:'Bebas Neue','Work Sans',sans-serif;font-weight:400;letter-spacing:0.05em;font-size:17px}"
               "@keyframes bandeScroll{from{transform:translateX(0)}to{transform:translateX(-50%)}}</style>")
        components.html(f"<!DOCTYPE html><html><head>{css}</head><body><div class='track'>{items}{items}</div></body></html>", height=46)
    else:
        # Marché fermé : le ruban défile en continu, comme en séance,
        # avec les clôtures du jour et la prochaine ouverture (vague 2,
        # 6 nov. 2026 : pas de bandeau statique).
        maintenant = datetime.now(ZoneInfo("America/Toronto"))
        ouv = _prochaine_ouverture(maintenant)
        ecart_jours = (ouv.date() - maintenant.date()).days
        if ecart_jours == 0:
            jour_ouv = "aujourd'hui"
        elif ecart_jours == 1:
            jour_ouv = "demain"
        else:
            jour_ouv = "lundi" if ouv.weekday() == 0 else ouv.strftime("le %d-%m")
        items = ("<span class='item'><b style='color:#E50914;'>MARCHÉ FERMÉ</b></span>"
                 + "".join(
                     f"<span class='item'><b>{n}</b>&nbsp;{p}&nbsp;{_variation_html(v)}</span>"
                     for n, p, v in elements)
                 + f"<span class='item'>Prochaine ouverture : <b>{jour_ouv} 9 h 30</b></span>")
        duree = max(24, 4 * (len(elements) + 2))
        css = ("<style>body{margin:0;background:#111111;font-family:'Work Sans',sans-serif;overflow:hidden;"
               "border:1px solid #2E2E2E;border-radius:10px;box-sizing:border-box;height:44px}"
               ".track{display:flex;width:max-content;padding:11px 0;animation:bandeScroll " + str(duree) + "s linear infinite}"
               ".track:hover{animation-play-state:paused}"
               ".item{padding:0 22px;border-right:1px solid rgba(255,255,255,0.12);color:#FFFFFF;font-weight:600;white-space:nowrap;font-variant-numeric:tabular-nums}"
               ".item b{font-family:'Bebas Neue','Work Sans',sans-serif;font-weight:400;letter-spacing:0.05em;font-size:17px}"
               "@keyframes bandeScroll{from{transform:translateX(0)}to{transform:translateX(-50%)}}</style>")
        components.html(f"<!DOCTYPE html><html><head>{css}</head><body><div class='track'>{items}{items}</div></body></html>", height=46)


@st.cache_data(ttl=300, show_spinner=False)
def _cloture_officielle_figee(ticker_symbol):
    """Clôture officielle (en CAD) de la dernière séance complétée,
    lue dans les barres quotidiennes : avant l'ouverture, celle de la
    veille ; après la fermeture, celle du jour ; le week-end, celle
    de vendredi. Retourne None si les barres sont indisponibles."""
    try:
        t = yf.Ticker(ticker_symbol)
        hist = t.history(period="5d")
        if hist is None or hist.empty or 'Close' not in hist.columns:
            return None
        try:
            devise = str(t.fast_info.get('currency') or 'CAD').upper()
        except Exception:
            devise = devise_naturelle(ticker_symbol)
        maintenant = datetime.now(ZoneInfo("America/Toronto"))
        aujourdhui = maintenant.date()
        minutes = maintenant.hour * 60 + maintenant.minute
        cloture = None
        for idx, row in hist.iterrows():
            try:
                c = float(row['Close'])
            except Exception:
                continue
            # Yahoo renvoie parfois la barre du jour avec une clôture
            # NaN le soir, avant de la consolider (vu le 28 oct. 2026
            # sur tous les titres américains) : un NaN n'est pas un
            # prix, on l'ignore comme une barre muette.
            if pd.isna(c) or c <= 0:
                continue
            d = idx.date()
            if d < aujourdhui or (d == aujourdhui and minutes >= 16 * 60):
                cloture = c
        if cloture is None:
            return None
        return convertir_vers_cad(cloture, devise)
    except Exception:
        return None


# --- VRAI GEL : PRIX FIGÉ ÉCRIT UNE FOIS PAR SÉANCE (28 oct. 2026 au soir) ---
# Le premier gel ne tenait pas sa promesse : le prix « figé » était
# recalculé à chaque transaction depuis les barres Yahoo, qui bougent
# encore en après-séance avant d'être consolidées, et quand Yahoo se
# taisait, le code retombait en silence sur le prix en direct. Deux
# transactions la même soirée pouvaient donc passer à deux prix
# différents (ventes AAPL du 28 oct. à 19 h 41, au prix d'après-séance).
# Maintenant : la clôture est capturée UNE fois par titre et par
# séance, écrite dans la table prix_geles, puis relue telle quelle
# jusqu'à l'ouverture suivante. Sans prix figé, la transaction hors
# heures est refusée (fail closed), jamais exécutée au prix en direct.

def _session_reference():
    """Date de la dernière séance complétée : celle dont la clôture
    sert de prix gelé. Après la fermeture d'un jour de semaine, la
    séance du jour ; sinon, le dernier jour de semaine écoulé."""
    maintenant = datetime.now(ZoneInfo("America/Toronto"))
    minutes = maintenant.hour * 60 + maintenant.minute
    if maintenant.weekday() < 5 and minutes >= 16 * 60:
        candidat = maintenant.date()
    else:
        candidat = maintenant.date() - timedelta(days=1)
    while candidat.weekday() >= 5:
        candidat -= timedelta(days=1)
    return candidat


def _lire_un_prix_gele(ticker_symbol, session_iso):
    """Prix figé déjà écrit pour ce titre et cette séance, ou None."""
    try:
        r = conn.query(
            "SELECT prix_cad FROM prix_geles WHERE ticker=:t AND session=:s",
            params={"t": str(ticker_symbol).strip().upper(), "s": session_iso}, ttl=0)
        if r.empty:
            return None
        v = float(r.iloc[0]['prix_cad'])
        if pd.isna(v) or v <= 0:
            return None
        return v
    except Exception:
        return None


@st.cache_data(ttl=60, show_spinner=False)
def _prix_geles_lire(session_iso, tickers_tuple):
    """Lecture en lot des prix figés (affichage) : une seule requête
    pour tous les titres demandés."""
    if not tickers_tuple:
        return {}
    try:
        params = {"s": session_iso}
        marques = []
        for i, tk in enumerate(tickers_tuple):
            cle = f"t{i}"
            marques.append(f":{cle}")
            params[cle] = tk
        sql = ("SELECT ticker, prix_cad FROM prix_geles WHERE session=:s "
               f"AND ticker IN ({', '.join(marques)})")
        r = conn.query(sql, params=params, ttl=0)
        sortie = {}
        for _, ligne in r.iterrows():
            try:
                v = float(ligne['prix_cad'])
            except Exception:
                continue
            if not pd.isna(v) and v > 0:
                sortie[str(ligne['ticker']).strip().upper()] = v
        return sortie
    except Exception:
        return {}


def _ecrire_prix_gele(ticker_symbol, session_iso, prix_cad):
    """Écrit le prix figé. Le premier écrit gagne : des captures
    simultanées ne s'écrasent pas (ON CONFLICT DO NOTHING)."""
    try:
        now_str = datetime.now(ZoneInfo("America/Toronto")).strftime("%Y-%m-%d %H:%M:%S")
        with conn.session as session:
            session.execute(
                text("INSERT INTO prix_geles (ticker, session, prix_cad, capture_le) "
                     "VALUES (:t, :s, :p, :c) ON CONFLICT (ticker, session) DO NOTHING"),
                {"t": str(ticker_symbol).strip().upper(), "s": session_iso,
                 "p": float(prix_cad), "c": now_str})
            session.commit()
        return True
    except Exception:
        return False


@st.cache_data(ttl=300, show_spinner=False)
def _cloture_pour_session(ticker_symbol, session_iso):
    """Clôture officielle (en CAD) de la séance demandée, lue dans les
    barres quotidiennes : la dernière barre valide dont la date est au
    plus celle de la séance (si la barre de la séance est encore NaN
    ou absente, c'est la séance précédente qui sert). None si rien."""
    try:
        cible = datetime.strptime(session_iso, "%Y-%m-%d").date()
        t = yf.Ticker(ticker_symbol)
        hist = t.history(period="10d")
        if hist is None or hist.empty or 'Close' not in hist.columns:
            return None
        try:
            devise = str(t.fast_info.get('currency') or 'CAD').upper()
        except Exception:
            devise = devise_naturelle(ticker_symbol)
        retenue = None
        for idx, row in hist.iterrows():
            try:
                c = float(row['Close'])
            except Exception:
                continue
            if pd.isna(c) or c <= 0:
                continue
            if idx.date() <= cible:
                retenue = c
        if retenue is None:
            return None
        return convertir_vers_cad(retenue, devise)
    except Exception:
        return None


def _capturer_prix_gele(ticker_symbol, session_iso):
    """Capture la clôture de la séance et l'écrit une fois pour toutes.
    Retourne le prix figé en vigueur après la capture (celui qui est
    écrit, même si une autre session a écrit le sien en premier)."""
    cad = _cloture_pour_session(ticker_symbol, session_iso)
    if cad is None:
        cad = cloture_veille(ticker_symbol)
    if cad is None or pd.isna(cad) or float(cad) <= 0:
        return None
    _ecrire_prix_gele(ticker_symbol, session_iso, float(cad))
    # Le prix ne vaut que s'il est vraiment écrit et relu : sans prix
    # figé établi dans la table, on refuse plutôt que d'exécuter à un
    # prix calculé localement qu'une autre session ne reverrait pas.
    return _lire_un_prix_gele(ticker_symbol, session_iso)


def _prix_gele_ou_none(ticker_symbol):
    """Prix gelé de la séance (en CAD) : celui écrit dans prix_geles,
    capturé au besoin. None si aucun prix ne peut être figé : hors
    heures, l'appelant doit alors refuser la transaction, jamais
    retomber sur le prix en direct."""
    try:
        session_iso = _session_reference().isoformat()
        lu = _lire_un_prix_gele(ticker_symbol, session_iso)
        if lu is not None:
            return lu
        return _capturer_prix_gele(ticker_symbol, session_iso)
    except Exception:
        return None


# --- BOUCLIERS (28 oct. 2026 au soir) ---
# Directive de Mathieu après les bogues NaN et AXG : bloquer les
# failles AVANT les dégâts plutôt que corriger après coup. Trois
# garde-fous s'ajoutent aux portes d'exécution (panneau d'ordre et
# vente rapide), en plus du vrai gel :
# 1. Cohérence des prix : un prix d'exécution qui contredit la
#    dernière clôture quotidienne (facteur > 3) signale des données
#    incohérentes (cas AXG : exécution à 0,05 $ contre une clôture
#    quotidienne de 8,00 $ chez le même fournisseur) ; refus net.
# 2. Compte en vérification : un comptant devenu illisible (NaN)
#    bloque les transactions de ce compte, sans toucher aux chiffres.
# 3. Titres suspendus : un titre aux données incohérentes peut être
#    suspendu par l'enseignant (table titres_suspendus) ; ni achat
#    ni vente tant qu'il est suspendu.

SEUIL_COHERENCE_PRIX = 3.0


@st.cache_data(ttl=60, show_spinner=False)
def _titres_suspendus():
    try:
        r = conn.query("SELECT ticker FROM titres_suspendus", ttl=0)
        return {str(t).strip().upper() for t in r['ticker'].tolist()}
    except Exception:
        return set()


def titre_suspendu(ticker_symbol):
    try:
        return str(ticker_symbol).strip().upper() in _titres_suspendus()
    except Exception:
        return False


@st.cache_data(ttl=30, show_spinner=False)
def _joueurs_suspendus():
    try:
        r = conn.query("SELECT username FROM joueurs_suspendus", ttl=0)
        return {str(u) for u in r['username'].tolist()}
    except Exception:
        return set()


def joueur_suspendu(username):
    """Vrai si le joueur est suspendu par l'enseignant : il peut se
    connecter et voir son portefeuille, mais aucun bouton ne fonctionne
    sur sa page sauf Déconnexion. Les comptes exemptés (enseignant) ne
    sont jamais suspendus."""
    try:
        if compte_exempte_frais(username):
            return False
        return username in _joueurs_suspendus()
    except Exception:
        return False


def suspendre_joueur(username):
    if compte_exempte_frais(username):
        return
    with conn.session as session:
        session.execute(text(
            "INSERT INTO joueurs_suspendus (username, depuis) VALUES (:u, :d) "
            "ON CONFLICT (username) DO NOTHING"),
            {"u": username,
             "d": datetime.now(ZoneInfo("America/Toronto")).strftime("%Y-%m-%d %H:%M:%S")})
        session.commit()
    _joueurs_suspendus.clear()


def lever_suspension_joueur(username):
    with conn.session as session:
        session.execute(text("DELETE FROM joueurs_suspendus WHERE username = :u"),
                        {"u": username})
        session.commit()
    _joueurs_suspendus.clear()


@st.cache_data(ttl=3600, show_spinner=False)
def jumeau_to(symbole):
    """Garde-fou anti-piège des symboles jumeaux. Si le symbole nu a un
    jumeau coté à Toronto (même symbole + .TO), retourne les noms
    complets des deux titres ; sinon None. Exemple vécu : DOL est un
    FNB américain de WisdomTree, alors que DOL.TO est Dollarama.
    Le panneau d'ordre s'en sert pour faire confirmer le bon titre
    avant l'achat, sans jamais bloquer l'élève."""
    s = str(symbole).strip().upper()
    if not s or '.' in s:
        return None
    try:
        t_to = yf.Ticker(s + ".TO")
        prix_to = t_to.fast_info["last_price"]
        if prix_to is None or float(prix_to) <= 0:
            return None
        info_to = t_to.info or {}
        nom_to = info_to.get("longName") or info_to.get("shortName") or (s + ".TO")
        court_to = str(info_to.get("shortName") or "")
        info_base = yf.Ticker(s).info or {}
        nom_base = info_base.get("longName") or info_base.get("shortName") or s
        # CDR : le nom court du jumeau le trahit (« APPLE CDR (CAD
        # HEDGED) »). Un CDR n'est pas l'action : c'est un certificat
        # qui en suit le cours, par fraction, en dollars couverts.
        return {"nom_base": str(nom_base), "nom_to": str(nom_to),
                "cdr_to": "CDR" in court_to.upper(), "court_to": court_to}
    except Exception:
        return None


def compte_en_verification(username):
    """Vrai si le comptant du compte est illisible (NaN). Les comptes
    exemptés (enseignant) ne sont jamais bloqués par ce garde-fou."""
    try:
        if compte_exempte_frais(username):
            return False
        r = conn.query("SELECT cash FROM users WHERE username=:u",
                       params={"u": username}, ttl=0)
        if r.empty:
            return False
        return bool(pd.isna(float(r.iloc[0]['cash'])))
    except Exception:
        return False


@st.cache_data(ttl=300, show_spinner=False)
def _reference_coherence_cad(ticker_symbol):
    """Référence de cohérence (en CAD) : dernière clôture quotidienne
    valide STRICTEMENT avant aujourd'hui, NaN ignorés. C'est le prix
    « normal » contre lequel un prix d'exécution aberrant se repère."""
    try:
        auj = datetime.now(ZoneInfo("America/Toronto")).date()
        t = yf.Ticker(ticker_symbol)
        hist = t.history(period="10d")
        if hist is None or hist.empty or 'Close' not in hist.columns:
            return None
        try:
            devise = str(t.fast_info.get('currency') or 'CAD').upper()
        except Exception:
            devise = devise_naturelle(ticker_symbol)
        ref = None
        for idx, row in hist.iterrows():
            if idx.date() >= auj:
                continue
            try:
                c = float(row['Close'])
            except Exception:
                continue
            if pd.isna(c) or c <= 0:
                continue
            ref = c
        if ref is None:
            return None
        return convertir_vers_cad(ref, devise)
    except Exception:
        return None


def prix_incoherent(ticker_symbol, prix_execution_cad):
    """(bloqué, référence) : bloqué si le prix d'exécution est
    illisible (NaN, nul ou négatif) ou s'il diverge de la référence
    par un facteur supérieur au seuil, dans un sens ou l'autre.
    Sans prix ou sans référence mesurable, on laisse passer (fail
    open, comme le coupe-circuit) : ce garde-fou vise les données
    incohérentes, pas les vrais mouvements de marché."""
    try:
        if prix_execution_cad is None:
            return False, None
        p = float(prix_execution_cad)
        if pd.isna(p) or p <= 0:
            return True, None
        ref = _reference_coherence_cad(ticker_symbol)
        if ref is None or ref <= 0:
            return False, None
        ratio = p / ref
        return (ratio > SEUIL_COHERENCE_PRIX or ratio < 1.0 / SEUIL_COHERENCE_PRIX), ref
    except Exception:
        return False, None


@st.cache_data(ttl=10, show_spinner=False)
def obtenir_prix_actuel(ticker_symbol):
    """Prix d'exécution d'un ordre. Le relais d'abord quand sa ligne
    est fraîche ; Yahoo ensuite ; le relais en dernier repli.
    Avant le 6 nov. 2026, Yahoo passait en premier et le relais ne
    servait que si Yahoo se taisait : or Yahoo, depuis les serveurs
    partagés de Streamlit, ressert parfois la même valeur périmée
    pendant des dizaines de minutes, et les ordres s'exécutaient à
    ce prix-là (vu sur KRMN pendant que le relais était à jour)."""
    if not _marche_ouvert():
        # Fail closed : hors heures, seul le prix figé écrit peut
        # exécuter un ordre. Sans prix figé, None (la transaction est
        # refusée par l'appelant), jamais le prix en direct qui
        # continue de bouger en après-séance.
        return _prix_gele_ou_none(ticker_symbol)
    lignes_fraiches = _relais_lire_prix([ticker_symbol])
    ligne_f = lignes_fraiches.get(str(ticker_symbol).strip().upper())
    if _ligne_relais_fraiche(ligne_f):
        entree_f = _entree_depuis_ligne_relais(ligne_f, ticker_symbol)
        if entree_f is not None and entree_f.get("cad") is not None:
            return entree_f["cad"]
    try:
        t = yf.Ticker(ticker_symbol)
        data = t.fast_info
        devise = str(data.get('currency') or 'CAD').upper()
        prix = data.get('lastPrice') or data.get('regularMarketPrice') or data.get('last_price')
        if prix is not None and not pd.isna(prix) and float(prix) > 0:
            return convertir_vers_cad(float(prix), devise)
        hist = t.history(period="1d")
        if not hist.empty:
            return convertir_vers_cad(float(hist['Close'].iloc[-1]), devise)
    except Exception:
        pass
    entree = _entree_depuis_relais(ticker_symbol)
    return entree["cad"] if entree else None

# --- LIMITE DE POSITION : 5 % DU VOLUME QUOTIDIEN MOYEN ---
# Un élève ne peut pas détenir plus que 5 % de ce qui s'échange vraiment
# chaque jour sur un titre (en $). En vrai, un ordre plus gros ferait bouger
# le prix. Donnée lente (moyenne 10 jours) : cache 24 h partagé, zéro ralentissement.
LIMITE_VOLUME_PCT = 0.05

@st.cache_data(ttl=86400, show_spinner=False)
def _volume_quotidien_moyen_cached(ticker_symbol):
    """Volume quotidien moyen en $ CAD (moyenne des 10 derniers jours
    d'échanges x dernier prix de clôture).
    Source principale : l'historique des prix, fiable partout.
    L'ancien champ « info » de Yahoo est capricieux depuis les serveurs
    infonuagiques : c'est lui qui a bloqué ATD.TO et Tesla le 21 oct. 2026.
    On le garde seulement en dernier recours.
    Lève une exception si aucune donnée : Streamlit ne met pas les
    exceptions en cache, donc un échec temporaire ne fige plus le titre
    pour 24 h comme le faisait l'ancien None mis en cache."""
    t = yf.Ticker(ticker_symbol)
    hist = t.history(period="1mo")
    if hist is not None and not hist.empty and 'Volume' in hist.columns and 'Close' in hist.columns:
        vols = [float(v) for v in hist['Volume'].tail(10) if v is not None and float(v) > 0]
        px = float(hist['Close'].iloc[-1])
        if vols and px > 0:
            try:
                devise = str(t.fast_info.get('currency') or '').upper() or devise_naturelle(ticker_symbol)
            except Exception:
                devise = devise_naturelle(ticker_symbol)
            return convertir_vers_cad((sum(vols) / len(vols)) * px, devise)
    info = t.info or {}
    vol = info.get('averageDailyVolume10Day') or info.get('averageVolume')
    if vol and float(vol) > 0:
        devise = str(info.get('currency') or '').upper() or devise_naturelle(ticker_symbol)
        fi = t.fast_info
        px = fi.get('lastPrice') or fi.get('regularMarketPrice')
        if px:
            return convertir_vers_cad(float(vol) * float(px), devise)
    raise ValueError(f"Aucune donnée de volume pour {ticker_symbol}")


def obtenir_volume_quotidien_moyen(ticker_symbol):
    """Volume quotidien moyen en $ CAD (moyenne 10 jours x prix).
    Retourne None si indisponible : dans ce cas l'achat est BLOQUE
    (fail closed, comme un vrai courtier qui refuse les titres obscurs
    sans données de volume vérifiables)."""
    try:
        return _volume_quotidien_moyen_cached(ticker_symbol)
    except Exception:
        return None


def verifier_limite_volume(username, ticker_symbol, prix_unitaire_cad, cout_ordre_cad):
    """Retourne un message d'erreur si (position actuelle + nouvel ordre)
    dépasserait 5 % du volume quotidien moyen, sinon None.
    Si le volume est invérifiable : achat BLOQUE (fail closed)."""
    try:
        vol_moyen = obtenir_volume_quotidien_moyen(ticker_symbol)
        if not vol_moyen or vol_moyen <= 0:
            return (f"Ordre refusé : impossible de vérifier ce qui s'échange chaque jour "
                    f"sur {ticker_symbol.upper()}. Sans ces données, l'achat est bloqué. "
                    f"En vrai, ton courtier refuserait aussi de te laisser acheter un titre obscur.")
        limite = LIMITE_VOLUME_PCT * vol_moyen
        p_res = conn.query("SELECT shares FROM portfolio WHERE username=:u AND LOWER(ticker)=LOWER(:t)",
                           params={"u": username, "t": ticker_symbol}, ttl=0)
        val_existante = int(p_res.iloc[0]['shares']) * float(prix_unitaire_cad) if not p_res.empty else 0.0
        if val_existante + float(cout_ordre_cad) > limite:
            return (f"Ordre refusé : ta position sur {ticker_symbol.upper()} ne peut pas dépasser "
                    f"5 % de ce qui s'échange chaque jour ({limite:,.0f} $). "
                    f"En vrai, un ordre plus gros ferait bouger le prix.")
        return None
    except Exception:
        return None


# --- DELAI DE DETENTION MINIMUM AVANT REVENTE ---
# Actions ordinaires : 1 h minimum (anti-flip de quelques secondes).
# Étape 2 (décision de Mathieu, 6 nov. 2026) : détention abaissée à
# 30 minutes pour une action ordinaire et à 1 h pour un ETF (avant :
# 1 h et 24 h).
DELAI_DETENTION_UNIVERSEL_H = 0.5
DELAI_DETENTION_ETF_H = 1

_MOTS_NOM_FONDS = ('ETF', 'FUND', 'TRUST', 'INDEX', 'FONDS', 'SHARES')


@st.cache_data(ttl=86400, show_spinner=False)
def est_etf(ticker_symbol):
    """Vrai si le titre est un FNB. Yahoo donne quoteType « ETF »,
    mais il classe aussi dans les ETF les certificats de dépôt (CDR)
    d'entreprises américaines cotés au Canada (VISA.TO, NKE.TO,
    PEP.TO, UPS.TO, WMT.TO, LMT.TO), qui sont des actions ordinaires :
    la détention de 24 h ne doit pas s'y appliquer (balayage des
    618 titres détenus, 3 nov. 2026 : 6 CDR pris à tort). Un vrai FNB
    se confirme par sa catégorie, sa famille de fonds ou son nom
    (ETF, Fund, Trust, Index...). En cas de doute ou d'échec de
    lecture, ce n'est pas un FNB : le délai léger de 1 h s'applique.
    Type quasi fixe : cache 24 h."""
    try:
        t = yf.Ticker(ticker_symbol)
        if str(t.fast_info.get('quoteType') or '').upper() != 'ETF':
            return False
        info = t.info
        nom = str(info.get('longName') or '').upper()
        return bool(info.get('category') or info.get('fundFamily')
                    or any(m in nom for m in _MOTS_NOM_FONDS))
    except Exception:
        return False


def delai_detention_requis(ticker_symbol):
    """Delai de detention en heures : 1 h pour les ETF, 0,5 h sinon."""
    return DELAI_DETENTION_ETF_H if est_etf(ticker_symbol) else DELAI_DETENTION_UNIVERSEL_H


def vente_avant_delai_bloquee(username, ticker_symbol):
    """Vrai si le dernier achat du titre date de moins que le delai requis."""
    try:
        delai_h = delai_detention_requis(ticker_symbol)
        r = conn.query(
            "SELECT MAX(timestamp) AS dernier FROM transactions WHERE username=:u AND LOWER(ticker)=LOWER(:t) AND shares > 0",
            params={"u": username, "t": ticker_symbol}, ttl=0)
        if r.empty or not r.iloc[0]['dernier']:
            return False
        dernier_achat = datetime.strptime(str(r.iloc[0]['dernier'])[:19], '%Y-%m-%d %H:%M:%S')
        dernier_achat = dernier_achat.replace(tzinfo=ZoneInfo("America/Toronto"))
        maintenant = datetime.now(ZoneInfo("America/Toronto"))
        return (maintenant - dernier_achat).total_seconds() < delai_h * 3600
    except Exception:
        return False


def message_delai_detention(ticker_symbol):
    """Message d'avertissement adapte au delai du titre."""
    if est_etf(ticker_symbol):
        return "Tu dois garder ce titre au moins 1 h avant de le revendre (ETF)."
    return "Tu dois garder ce titre au moins 30 minutes avant de le revendre."


@st.cache_data(ttl=900, show_spinner=False)
def obtenir_nouvelles(ticker_symbol):
    """Actualités du titre via Google News RSS (5 max). 1 appel par titre aux 15 min, partagé entre élèves."""
    try:
        import urllib.parse, urllib.request
        q = urllib.parse.quote_plus(f"{ticker_symbol} stock")
        url = f"https://news.google.com/rss/search?q={q}&hl=en-US&gl=US&ceid=US:en"
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=15) as r:
            data = r.read()
        root = ET.fromstring(data)
        out = []
        for it in root.findall('.//item')[:5]:
            titre = it.findtext('title') or ''
            lien = it.findtext('link') or ''
            src_el = it.find('source')
            pub = (src_el.text or '') if src_el is not None else ''
            if ' - ' in titre:
                titre = titre.rsplit(' - ', 1)[0]
            date_courte = ''
            try:
                from datetime import datetime as _dt_news
                _d_news = _dt_news.strptime((it.findtext('pubDate') or '')[:25], "%a, %d %b %Y %H:%M:%S")
                _mois_fr = ['janv.', 'févr.', 'mars', 'avr.', 'mai', 'juin', 'juill.', 'août', 'sept.', 'oct.', 'nov.', 'déc.']
                date_courte = f"{_d_news.day} {_mois_fr[_d_news.month - 1]}"
            except Exception:
                date_courte = ''
            if titre and lien:
                out.append({'title': titre, 'link': lien, 'publisher': pub, 'date': date_courte})
        return out
    except Exception:
        return []

@st.cache_data(ttl=300, show_spinner=False)
def cloture_veille(ticker_symbol):
    """Prix de clôture de la veille (ou None si indisponible).
    Fonctionne avant, pendant et après les heures de marché."""
    try:
        t = yf.Ticker(ticker_symbol)
        # previousClose de fast_info = clôture officielle précédente, fiable
        # même en premarket
        data = t.fast_info
        devise = str(data.get('currency') or 'CAD').upper()
        pc = data.get('previousClose')
        if pc is not None and not pd.isna(pc) and float(pc) > 0:
            return convertir_vers_cad(float(pc), devise)
        # Repli : historique 5 jours, prendre l'avant-dernière clôture
        # (la dernière peut être la séance du jour en cours)
        hist = t.history(period="5d")
        if hist is None or hist.empty or len(hist) < 2:
            return None
        return convertir_vers_cad(float(hist['Close'].iloc[-2]), devise)
    except Exception:
        return None


def cloture_avant_date(ticker_symbol, date_limite):
    """Clôture du dernier jour de bourse strictement avant date_limite.
    Ex : date_limite='2026-10-12' -> clôture du vendredi 2026-10-09."""
    try:
        t = yf.Ticker(ticker_symbol)
        hist = t.history(start="2026-10-01", end=date_limite)
        if hist is None or hist.empty:
            return None
        try:
            devise = str(t.fast_info.get('currency') or 'CAD').upper()
        except Exception:
            devise = 'CAD'
        return convertir_vers_cad(float(hist['Close'].iloc[-1]), devise)
    except Exception:
        return None


def analyser_violations_9h30(date_debut, date_fin):
    """Détecte les achats avant 9h30 (heure Toronto) entre date_debut et date_fin
    (incluses, format 'AAAA-MM-JJ') sur des actions dont la clôture du dernier
    jour de bourse précédent était sous 5 $. Retourne un DataFrame des
    transactions fautives, avec une colonne 'date' (jour de la transaction)."""
    from datetime import date as _date, timedelta as _td
    d0 = _date.fromisoformat(date_debut)
    d1 = _date.fromisoformat(date_fin)
    morceaux = []
    j = d0
    while j <= d1:
        ds = j.isoformat()
        tx = conn.query(
            "SELECT id, username, ticker, shares, price, total, timestamp FROM transactions "
            f"WHERE timestamp >= '{ds} 00:00:00' AND timestamp < '{ds} 09:30:00' "
            "AND shares > 0 ORDER BY id",
            ttl=0
        )
        if not tx.empty:
            clotures = {}
            for tk in tx['ticker'].unique().tolist():
                clotures[str(tk)] = cloture_avant_date(str(tk), ds)
            tx['cloture_veille'] = tx['ticker'].map(clotures)
            tx['date'] = ds
            viol = tx[(tx['cloture_veille'].notna()) & (tx['cloture_veille'] < 5.0)].copy()
            if not viol.empty:
                morceaux.append(viol)
        j += _td(days=1)
    if not morceaux:
        return pd.DataFrame()
    return pd.concat(morceaux, ignore_index=True)


def calculer_gains_9h30(violations_df):
    """Ajoute à chaque transaction fautive : 'gain_estime' (ventes du jour +
    valeur actuelle du reliquat - coût des achats fautifs), 'heures_achat'
    (heures des achats fautifs) et 'heures_vente' (heures des reventes le jour
    même, ou '-'). Permet de juger si l'infraction a vraiment profité."""
    if violations_df.empty:
        return violations_df
    tickers = violations_df['ticker'].unique().tolist()
    prix_actuels = obtenir_prix_groupes(tickers)
    gains, h_achats, h_ventes, p_achats = {}, {}, {}, {}
    for (ds, u, tk), grp in violations_df.groupby(['date', 'username', 'ticker']):
        cout = float(grp['total'].sum())
        q_achats = int(grp['shares'].sum())
        heures_a = sorted(set(str(t).split(' ')[1] for t in grp['timestamp']))
        prix_a = sorted(set(f"{float(p):.2f}" for p in grp['price']))
        ventes = conn.query(
            "SELECT shares, total, timestamp FROM transactions WHERE username=:u AND ticker=:t "
            f"AND timestamp >= '{ds} 00:00:00' AND timestamp < '{ds} 23:59:59' AND shares < 0",
            params={"u": str(u), "t": str(tk)}, ttl=0
        )
        q_vendues = int((-ventes['shares']).sum()) if not ventes.empty else 0
        tot_vendus = float(ventes['total'].sum()) if not ventes.empty else 0.0
        heures_v = sorted(set(str(t).split(' ')[1] for t in ventes['timestamp'])) if not ventes.empty else []
        reliquat = max(q_achats - q_vendues, 0)
        _info_px = prix_actuels.get(str(tk).upper())
        px = _info_px["cad"] if _info_px else None
        val_reliquat = reliquat * px if px else 0.0
        cle = (ds, str(u), str(tk))
        gains[cle] = (tot_vendus + val_reliquat) - cout
        h_achats[cle] = ", ".join(heures_a)
        h_ventes[cle] = ", ".join(heures_v) if heures_v else "-"
        p_achats[cle] = ", ".join(prix_a)
    violations_df['gain_estime'] = violations_df.apply(
        lambda r: gains.get((r['date'], str(r['username']), str(r['ticker'])), 0.0), axis=1
    )
    violations_df['heures_achat'] = violations_df.apply(
        lambda r: h_achats.get((r['date'], str(r['username']), str(r['ticker'])), ""), axis=1
    )
    violations_df['heures_vente'] = violations_df.apply(
        lambda r: h_ventes.get((r['date'], str(r['username']), str(r['ticker'])), "-"), axis=1
    )
    violations_df['prix_achat'] = violations_df.apply(
        lambda r: p_achats.get((r['date'], str(r['username']), str(r['ticker'])), ""), axis=1
    )
    return violations_df


def executer_annulation_9h30(violations_df):
    """Annule toutes les transactions du jour fautif pour chaque triplet
    (élève, action, date), comme si elles n'avaient jamais existé : cash
    ajusté, transactions supprimées, portefeuille recalculé depuis les
    transactions restantes. Retourne (nb_cas, nb_transactions, total_cash)."""
    triplets = violations_df[['username', 'ticker', 'date']].drop_duplicates()
    plans = []
    for _, row in triplets.iterrows():
        u, tk, ds = str(row['username']), str(row['ticker']), str(row['date'])
        toutes = conn.query(
            "SELECT id, shares, price, total, timestamp FROM transactions "
            "WHERE username=:u AND ticker=:t ORDER BY id",
            params={"u": u, "t": tk}, ttl=0
        )
        if toutes.empty:
            continue
        a_annuler = toutes[
            (toutes['timestamp'] >= f'{ds} 00:00:00') &
            (toutes['timestamp'] < f'{ds} 23:59:59')
        ]
        if a_annuler.empty:
            continue
        restantes = toutes.drop(a_annuler.index)
        ids_annuler = [int(i) for i in a_annuler['id'].tolist()]
        cash_delta = 0.0
        for _, t in a_annuler.iterrows():
            cash_delta += float(t['total']) if int(t['shares']) > 0 else -float(t['total'])
        achats = restantes[restantes['shares'] > 0]
        q_achats = int(achats['shares'].sum()) if not achats.empty else 0
        q_ventes = int((-restantes[restantes['shares'] < 0]['shares']).sum()) if not restantes.empty else 0
        new_shares = q_achats - q_ventes
        new_avg = 0.0
        if q_achats > 0 and new_shares > 0:
            new_avg = float((achats['shares'] * achats['price']).sum() / q_achats)
        plans.append({
            'username': u, 'ticker': tk, 'date': ds, 'ids': ids_annuler,
            'cash_delta': cash_delta, 'new_shares': max(new_shares, 0),
            'new_avg': new_avg, 'nb_tx': len(ids_annuler),
            'anomalie': new_shares < 0
        })
    nb_tx_total = 0
    with conn.session as session:
        for p in plans:
            session.execute(
                text("UPDATE users SET cash = cash + :d WHERE username = :u"),
                {"d": p['cash_delta'], "u": p['username']}
            )
            for tx_id in p['ids']:
                session.execute(text("DELETE FROM transactions WHERE id = :i"), {"i": tx_id})
            session.execute(
                text("DELETE FROM portfolio WHERE username = :u AND ticker = :t"),
                {"u": p['username'], "t": p['ticker']}
            )
            if p['new_shares'] > 0:
                session.execute(
                    text("INSERT INTO portfolio (username, ticker, shares, avg_price) "
                         "VALUES (:u, :t, :s, :p)"),
                    {"u": p['username'], "t": p['ticker'], "s": p['new_shares'], "p": p['new_avg']}
                )
            nb_tx_total += p['nb_tx']
        session.commit()
    total_cash = sum(p['cash_delta'] for p in plans)
    return len(plans), nb_tx_total, total_cash


# Barre des titres sous 5 $ avant 9 h 30 RETIRÉE à l'étape 2
# (décision de Mathieu, 6 nov. 2026) : avant l'ouverture, les achats
# sont de toute façon des ordres en attente exécutés au prix
# d'ouverture, la barre ne protégeait plus rien.

@st.cache_resource
def _memo_derniers_prix():
    """Derniers prix valides obtenus par titre, gardés tant que l'app roule.
    Filet de sécurité : quand Yahoo se tait complètement (direct ET
    historique en même temps), l'affichage retombait sur le prix d'achat
    et tous les gains tombaient à 0,00 $ (vu le 22 oct. 2026). Avec ce
    filet, on affiche le dernier prix réel connu plutôt qu'un faux zéro."""
    return {}


# --- RELAIS DE PRIX (sources multiples, indépendant du nuage) ---
# Une sonde sur la machine de Muse interroge Yahoo ET l'API Nasdaq
# toutes les minutes et écrit les prix dans la base (tables prix_relais
# et historique_relais). Quand Yahoo ne répond pas depuis les serveurs
# de Streamlit (adresse partagée limitée en pleine classe), l'app lit
# le relais au lieu de rester muette : positions, achats, détails et
# graphiques continuent de fonctionner.

def _relais_lire_prix(tickers):
    """Lignes du relais pour une liste de titres : {TICKER: ligne}."""
    propres = [str(t).strip().upper() for t in tickers if t and str(t).strip()]
    if not propres:
        return {}
    try:
        marques = ", ".join(f":t{i}" for i in range(len(propres)))
        params = {f"t{i}": t for i, t in enumerate(propres)}
        df = conn.query(
            "SELECT ticker, prix_natif, prev_natif, ouverture, haut, bas, "
            f"haut52, bas52, devise, maj FROM prix_relais WHERE ticker IN ({marques})",
            params=params, ttl=0)
        return {str(r['ticker']).upper(): r for _, r in df.iterrows()}
    except Exception:
        return {}


def _entree_depuis_ligne_relais(ligne, ticker_symbol):
    """Convertit une ligne prix_relais au format des prix groupés."""
    if ligne is None:
        return None
    try:
        px = float(ligne['prix_natif'])
        if pd.isna(px) or px <= 0:
            return None
    except Exception:
        return None
    devise = str(ligne['devise'] or '').upper() or devise_naturelle(ticker_symbol)
    prev_cad = None
    prev = ligne['prev_natif']
    if prev is not None and not pd.isna(prev) and float(prev) > 0:
        prev_cad = convertir_vers_cad(float(prev), devise)
    return {"cad": convertir_vers_cad(px, devise), "natif": round(px, 4),
            "devise": devise, "prev_cad": prev_cad}


def _entree_depuis_relais(ticker_symbol):
    lignes = _relais_lire_prix([ticker_symbol])
    return _entree_depuis_ligne_relais(
        lignes.get(str(ticker_symbol).strip().upper()), ticker_symbol)


def _ligne_relais_fraiche(ligne, max_age_s=900):
    """Vrai si la ligne du relais a été écrite il y a moins de
    max_age_s secondes. Le champ maj arrive en ISO (avec ou sans T,
    avec fuseau) en heure de Toronto ; on compare en heure locale
    naïve. Le cycle rapide de la sonde écrit aux 3 minutes environ :
    900 s couvre plusieurs cycles manqués avant de déclarer la
    ligne périmée."""
    if ligne is None:
        return False
    try:
        brut = str(ligne['maj']).replace('T', ' ')[:19]
        maj = datetime.strptime(brut, "%Y-%m-%d %H:%M:%S")
    except Exception:
        return False
    maintenant = datetime.now(ZoneInfo("America/Toronto")).replace(tzinfo=None)
    return 0 <= (maintenant - maj).total_seconds() <= max_age_s


def _prix_depuis_historique(ticker_symbol):
    """Repli prix : dernière clôture connue (5 derniers jours).
    Sert quand le prix en direct de Yahoo ne répond pas : sans ce repli,
    l'affichage remplaçait le prix actuel par le prix d'achat et le
    gain/perte de la position tombait à exactement 0,00 $ (vu le
    21 oct. 2026, ex. Rob Thibeault). Un gain presque juste, basé sur
    la dernière clôture, vaut mieux qu'un faux zéro."""
    vide = {"cad": None, "natif": None, "devise": devise_naturelle(ticker_symbol), "prev_cad": None}
    try:
        hist = yf.Ticker(ticker_symbol).history(period="5d")
        if hist is None or hist.empty or 'Close' not in hist.columns:
            return vide
        devise = devise_naturelle(ticker_symbol)
        # Dernière clôture VALIDE : la barre la plus récente peut être
        # NaN chez Yahoo (barre du jour pas encore consolidée).
        valides = []
        for v in hist['Close']:
            try:
                fv = float(v)
            except Exception:
                continue
            if not pd.isna(fv) and fv > 0:
                valides.append(fv)
        if not valides:
            return vide
        px = valides[-1]
        prev_cad = None
        if len(valides) >= 2:
            prev_cad = convertir_vers_cad(valides[-2], devise)
        return {"cad": convertir_vers_cad(px, devise), "natif": round(px, 4),
                "devise": devise, "prev_cad": prev_cad}
    except Exception:
        return vide


@st.cache_data(ttl=30, show_spinner=False)
def obtenir_prix_groupes(tickers_list):
    if not tickers_list:
        return {}
    clean_tickers = list(set([str(t).strip().upper() for t in tickers_list if t and str(t).strip()]))
    if not clean_tickers:
        return {}
    # Le relais d'abord (correctif du 6 nov. 2026) : la sonde écrit
    # les prix aux 3 minutes environ depuis une adresse non limitée,
    # alors que Yahoo, interrogé directement depuis les serveurs
    # partagés de Streamlit, ressert parfois la même valeur périmée
    # pendant des dizaines de minutes (vu sur KRMN : 42,06 $ affichés
    # refresh après refresh pendant que le vrai prix était 43,24 $
    # et le relais à 42,90 $). Un titre dont la ligne du relais est
    # fraîche (15 minutes ou moins en séance) est servi par le
    # relais ; les autres suivent la voie habituelle. Hors séance,
    # la ligne du relais vaut le dernier prix connu et le gel
    # ci-dessous corrige l'affichage.
    prix_dict = {}
    restants = list(clean_tickers)
    try:
        lignes_relais = _relais_lire_prix(clean_tickers)
        ouvert_r = _marche_ouvert()
        for tk in clean_tickers:
            ligne = lignes_relais.get(tk)
            if ligne is None:
                continue
            if ouvert_r and not _ligne_relais_fraiche(ligne):
                continue
            entree_r = _entree_depuis_ligne_relais(ligne, tk)
            if entree_r is not None and entree_r.get("cad") is not None:
                prix_dict[tk] = entree_r
                _memo_derniers_prix()[tk] = dict(entree_r)
        restants = [tk for tk in clean_tickers if tk not in prix_dict]
    except Exception:
        restants = list(clean_tickers)
    try:
        data = yf.Tickers(" ".join(restants)) if restants else None
    except Exception:
        data = None
    for tk in restants:
        entree = None
        if data is not None:
            try:
                info = data.tickers[tk].fast_info
                devise = str(info.get('currency') or 'CAD').upper()
                px = info.get('lastPrice') or info.get('regularMarketPrice') or info.get('last_price')
                if px is not None and not pd.isna(px) and float(px) > 0:
                    natif = float(px)
                    prev = info.get('previousClose')
                    prev_cad = None
                    if prev is not None and not pd.isna(prev):
                        prev_cad = convertir_vers_cad(float(prev), devise)
                    entree = {"cad": convertir_vers_cad(natif, devise),
                              "natif": round(natif, 4), "devise": devise,
                              "prev_cad": prev_cad}
            except Exception:
                entree = None
        if entree is None:
            entree = _prix_depuis_historique(tk)
        # Filet « dernier prix connu » : si les deux voies Yahoo sont
        # muettes (cad = None), on réutilise le dernier prix réel obtenu
        # pour ce titre plutôt que de laisser l'affichage retomber sur le
        # prix d'achat, ce qui affichait un faux gain de 0,00 $ partout
        # (vu le 22 oct. 2026). Si un prix valide arrive, il alimente le
        # filet pour les prochains hoquets.
        memo_prix = _memo_derniers_prix()
        if entree is not None and entree.get("cad") is not None:
            memo_prix[tk] = dict(entree)
        elif memo_prix.get(tk):
            entree = dict(memo_prix[tk])
        prix_dict[tk] = entree
    # Repli relais : les titres restés sans prix (Yahoo muet des deux
    # voies ET filet vide) sont remplis depuis la table du relais.
    manquants = [tk for tk, e in prix_dict.items()
                 if e is None or e.get("cad") is None]
    if manquants:
        lignes = _relais_lire_prix(manquants)
        for tk in manquants:
            entree_r = _entree_depuis_ligne_relais(lignes.get(tk), tk)
            if entree_r is not None and entree_r.get("cad") is not None:
                prix_dict[tk] = entree_r
                _memo_derniers_prix()[tk] = dict(entree_r)
    # Vrai gel hors heures : les prix figés écrits dans prix_geles,
    # capturés au besoin (au plus 25 par appel, pour ne pas ralentir
    # l'affichage ; les autres suivront aux prochains affichages).
    # Un titre sans prix figé garde son prix d'affichage habituel,
    # mais aucun ordre ne peut l'utiliser : l'exécution exige le prix
    # figé (voir obtenir_prix_actuel et les portes des panneaux).
    if not _marche_ouvert():
        try:
            session_iso = _session_reference().isoformat()
            cles = tuple(sorted(prix_dict.keys()))
            lus = _prix_geles_lire(session_iso, cles)
            captures = 0
            for tk in cles:
                if captures >= 25:
                    break
                entree0 = prix_dict.get(tk)
                if tk in lus or entree0 is None or entree0.get("cad") is None:
                    continue
                cap = _capturer_prix_gele(tk, session_iso)
                captures += 1
                if cap is not None:
                    lus[tk] = cap
            for tk, entree in prix_dict.items():
                if entree is None or entree.get("cad") is None or tk not in lus:
                    continue
                entree["cad"] = lus[tk]
                natif = vers_natif(
                    lus[tk], entree.get("devise") or devise_naturelle(tk))
                if natif is not None:
                    entree["natif"] = natif
        except Exception:
            pass
    return prix_dict

def _details_voie_rapide(t, ticker_symbol):
    """Voie rapide (fast_info). Retourne le dict de détails, la chaîne
    'non_na' si le titre est refusé (mauvaise bourse ou mauvais type),
    ou None si Yahoo n'a pas répondu (échec technique, pas un refus)."""
    info = t.fast_info

    # Validation stricte : actions/FNB du TSX, NYSE ou Nasdaq seulement.
    exch = str(info.get('exchange') or '')
    qtype = str(info.get('quoteType') or '')
    if not instrument_autorise(ticker_symbol, exch_code=exch, quote_type=qtype):
        return "non_na"

    devise = str(info.get('currency') or 'CAD').upper()

    last = info.get('lastPrice') or info.get('regularMarketPrice') or info.get('last_price')
    if last is None or pd.isna(last) or float(last) <= 0:
        hist = t.history(period="2d")
        if hist is not None and not hist.empty:
            last = float(hist['Close'].iloc[-1])
        else:
            return None
    else:
        last = float(last)

    # Gel hors heures : le prix affiché est la clôture officielle de
    # la dernière séance complétée, comme pour les ordres.
    if not _marche_ouvert():
        gele = _prix_gele_ou_none(ticker_symbol)
        if gele is not None:
            natif_gele = vers_natif(gele, devise)
            if natif_gele is not None:
                last = float(natif_gele)

    open_p = info.get('open') or info.get('openPrice')
    if open_p is None or pd.isna(open_p):
        hist = t.history(period="2d")
        if hist is not None and len(hist) >= 2:
            open_p = float(hist['Close'].iloc[-2])
        elif hist is not None and not hist.empty:
            open_p = float(hist['Open'].iloc[-1])
        else:
            open_p = last
    else:
        open_p = float(open_p)

    # Prix en devise NATURELLE du titre (affichage, comme les vrais
    # sites). "PrixCAD" sert aux calculs du panneau d'ordre : le compte
    # de l'élève est en dollars canadiens.
    change = last - open_p
    change_pct = (change / open_p) * 100 if open_p > 0 else 0.0
    fmt = ".4f" if last < 1 else ".2f"

    high_n = float(info.get('dayHigh') or last)
    low_n = float(info.get('dayLow') or last)
    y_high_n = float(info.get('yearHigh') or last)
    y_low_n = float(info.get('yearLow') or last)

    return {
        "Prix": last,
        "PrixCAD": convertir_vers_cad(last, devise),
        "Variation": change,
        "VariationPct": change_pct,
        "Ouverture": f"${open_p:{fmt}}",
        "Plus Haut": f"${high_n:{fmt}}",
        "Plus Bas": f"${low_n:{fmt}}",
        "52 sem. Haut": f"${y_high_n:{fmt}}",
        "52 sem. Bas": f"${y_low_n:{fmt}}",
        "Devise": devise
    }


def _details_voie_historique(t, ticker_symbol):
    """Voie de repli : métadonnées et historique Yahoo (l'API graphique,
    celle qui répond de façon fiable depuis les serveurs du site).
    Même validation stricte des bourses et des types d'instruments.
    Sans ce repli, un simple hoquet de Yahoo disait à l'élève que le
    titre n'existait pas et bloquait son achat (ex. SVRN, NASDAQ,
    21 oct. 2026). Retourne le dict, 'non_na' ou None comme la voie
    rapide."""
    md = t.history_metadata or {}
    exch = str(md.get('exchangeName') or '')
    qtype = str(md.get('instrumentType') or '')
    if not instrument_autorise(ticker_symbol, exch_code=exch, quote_type=qtype):
        return "non_na"

    hist = t.history(period="1y")
    if hist is None or hist.empty or 'Close' not in hist.columns:
        return None
    devise = str(md.get('currency') or '').upper() or devise_naturelle(ticker_symbol)
    last = float(hist['Close'].iloc[-1])
    if last <= 0:
        return None
    open_p = hist['Open'].iloc[-1]
    open_p = float(open_p) if open_p is not None and not pd.isna(open_p) and float(open_p) > 0 else (
        float(hist['Close'].iloc[-2]) if len(hist) >= 2 else last)
    change = last - open_p
    change_pct = (change / open_p) * 100 if open_p > 0 else 0.0
    fmt = ".4f" if last < 1 else ".2f"
    return {
        "Prix": last,
        "PrixCAD": convertir_vers_cad(last, devise),
        "Variation": change,
        "VariationPct": change_pct,
        "Ouverture": f"${open_p:{fmt}}",
        "Plus Haut": f"${float(hist['High'].iloc[-1]):{fmt}}",
        "Plus Bas": f"${float(hist['Low'].iloc[-1]):{fmt}}",
        "52 sem. Haut": f"${float(hist['High'].max()):{fmt}}",
        "52 sem. Bas": f"${float(hist['Low'].min()):{fmt}}",
        "Devise": devise
    }


def _details_depuis_relais(ticker_symbol):
    """Détails de repli depuis le relais : même format que la voie
    historique. Sans ce repli, un silence de Yahoo fermait toute la
    page du titre, graphique et achat compris (vu le 22 oct. 2026)."""
    lignes = _relais_lire_prix([ticker_symbol])
    ligne = lignes.get(str(ticker_symbol).strip().upper())
    if ligne is None:
        return None
    try:
        px = float(ligne['prix_natif'])
        if pd.isna(px) or px <= 0:
            return None
    except Exception:
        return None
    devise = str(ligne['devise'] or '').upper() or devise_naturelle(ticker_symbol)

    def _val(col, repli):
        v = ligne[col]
        if v is None or pd.isna(v) or float(v) <= 0:
            return float(repli)
        return float(v)

    ouv = _val('ouverture', px)
    change = px - ouv
    change_pct = (change / ouv) * 100 if ouv > 0 else 0.0
    fmt = ".4f" if px < 1 else ".2f"
    return {
        "Prix": px,
        "PrixCAD": convertir_vers_cad(px, devise),
        "Variation": change,
        "VariationPct": change_pct,
        "Ouverture": f"${ouv:{fmt}}",
        "Plus Haut": f"${_val('haut', px):{fmt}}",
        "Plus Bas": f"${_val('bas', px):{fmt}}",
        "52 sem. Haut": f"${_val('haut52', px):{fmt}}",
        "52 sem. Bas": f"${_val('bas52', px):{fmt}}",
        "Devise": devise
    }


@st.cache_data(ttl=60, show_spinner=False)
def obtenir_details_financiers(ticker_symbol):
    if not _symbole_syntaxe_ok(ticker_symbol):
        return {"erreur": "non_na"}

    t = yf.Ticker(ticker_symbol)
    try:
        r = _details_voie_rapide(t, ticker_symbol)
    except Exception:
        r = None
    if r == "non_na":
        return {"erreur": "non_na"}
    if r is not None:
        return r
    try:
        r = _details_voie_historique(t, ticker_symbol)
    except Exception:
        r = None
    if r == "non_na":
        return {"erreur": "non_na"}
    if r is not None:
        return r
    try:
        return _details_depuis_relais(ticker_symbol)
    except Exception:
        return None


def _historique_depuis_relais(ticker_symbol, periode):
    """Graphique de repli : bougies QUOTIDIENNES stockées par la sonde
    dans historique_relais. Moins fin que l'intrajournalier Yahoo,
    mais le graphique (et l'achat, qui vit sur la même page) reste
    disponible quand Yahoo ne répond pas depuis le nuage."""
    try:
        df = conn.query(
            "SELECT jour, o, h, l, c, v FROM historique_relais "
            "WHERE ticker=:t ORDER BY jour",
            params={"t": str(ticker_symbol).strip().upper()}, ttl=0)
        if df is None or df.empty:
            return None
        fenetres = {"1d": 5, "5d": 5, "1mo": 22, "3mo": 66,
                    "6mo": 132, "1y": 252, "2y": 504, "5y": 1260}
        df = df.tail(fenetres.get(periode, 252))
        out = pd.DataFrame({
            "Open": df['o'].astype(float).values,
            "High": df['h'].astype(float).values,
            "Low": df['l'].astype(float).values,
            "Close": df['c'].astype(float).values,
            "Volume": df['v'].fillna(0).astype(float).values,
        }, index=pd.to_datetime(df['jour']))
        out.index.name = "Date"
        return out
    except Exception:
        return None


@st.cache_data(ttl=300, show_spinner=False)
def obtenir_historique(ticker_symbol, periode, devise="CAD"):
    """Historique en devise NATURELLE du titre (aucune conversion :
    le graphique montre les mêmes chiffres que les vrais sites).
    Repli : bougies quotidiennes du relais quand Yahoo ne répond pas,
    pour que le graphique (et l'achat, sur la même page) reste ouvert."""
    try:
        interval = "5m" if periode == "1d" else ("15m" if periode == "5d" else "1d")
        df = yf.Ticker(ticker_symbol).history(period=periode, interval=interval)
        if df is not None and not df.empty:
            return df
    except Exception:
        pass
    return _historique_depuis_relais(ticker_symbol, periode)

# --- PHOTOS DES MENEURS (déposées par le prof dans Supervision) ---
def traiter_photo(octets):
    """Recadre la photo au carré sur le visage, la réduit à 256 px
    et la compresse en JPEG (base64) pour la base de données."""
    import base64
    import io as _io
    from PIL import Image
    img = Image.open(_io.BytesIO(octets)).convert("RGB")
    cote = min(img.size)
    gauche = (img.width - cote) // 2
    haut = max(0, int((img.height - cote) * 0.18))
    img = img.crop((gauche, haut, gauche + cote, haut + cote)).resize((256, 256))
    tampon = _io.BytesIO()
    img.save(tampon, format="JPEG", quality=82)
    return base64.b64encode(tampon.getvalue()).decode()


@st.cache_data(ttl=60, show_spinner=False)
def obtenir_photo(username):
    try:
        df = conn.query("SELECT image FROM photos WHERE username=:u",
                        params={"u": username}, ttl=0)
        if not df.empty and df.iloc[0]['image']:
            return str(df.iloc[0]['image'])
    except Exception:
        pass
    return None


def initiales_de(nom):
    morceaux = [m for m in str(nom).replace("_", " ").replace(".", " ").split() if m]
    if len(morceaux) >= 2:
        return (morceaux[0][0] + morceaux[1][0]).upper()
    nom = str(nom)
    for c in nom[1:]:
        if c.isupper():
            return (nom[0] + c).upper()
    return nom[:2].upper()


# --- CACHE DES CALCULS DU CLASSEMENT (TTL = 30s) ---
@st.cache_data(ttl=120, show_spinner=False)
def obtenir_donnees_classement(grp_filter):
    if grp_filter == "Tous les groupes":
        users_df = conn.query("SELECT username, cash, groupe FROM users", ttl=0)
    else:
        users_df = conn.query("SELECT username, cash, groupe FROM users WHERE groupe=:g", params={"g": grp_filter}, ttl=0)

    if users_df.empty:
        return pd.DataFrame()

    susp_classement = _joueurs_suspendus()
    all_positions_df = conn.query("SELECT username, ticker, shares, avg_price FROM portfolio", ttl=0)
    unique_tickers = list(all_positions_df['ticker'].unique()) if not all_positions_df.empty else []
    prix_dict = obtenir_prix_groupes(unique_tickers)

    lb = []
    for _, r in users_df.iterrows():
        u_name, u_cash, u_grp = r['username'], float(r['cash']), r['groupe']
        u_p = all_positions_df[all_positions_df['username'] == u_name] if not all_positions_df.empty else pd.DataFrame()

        u_val_act = 0.0
        u_gain_jour = 0.0
        u_base_jour = 0.0
        if not u_p.empty:
            for _, row in u_p.iterrows():
                tk_sym = str(row['ticker']).upper()
                _info_px = prix_dict.get(tk_sym)
                px = _info_px["cad"] if _info_px else None
                px_f = px if px is not None else float(row['avg_price'] or 0.0)
                u_val_act += px_f * row['shares']
                # Gain du jour : positions actuelles comparées à la clôture
                # de la veille (même appel de prix, aucun coût réseau ajouté).
                _prev = _info_px.get("prev_cad") if _info_px else None
                if _prev is not None and px is not None:
                    u_gain_jour += (px - _prev) * row['shares']
                    u_base_jour += _prev * row['shares']

        tot = u_cash + u_val_act
        perf = ((tot - 10000.00) / 10000.00) * 100
        gain_jour_pct = (u_gain_jour / u_base_jour * 100) if u_base_jour > 0 else 0.0
        lb.append({"Élève": u_name, "Groupe": u_grp, "Portefeuille": tot, "Performance": perf,
                   "GainJour": u_gain_jour, "GainJourPct": gain_jour_pct,
                   "Statut": "SUSPENDU" if u_name in susp_classement else ""})

    if lb:
        df_lb = pd.DataFrame(lb).sort_values(by="Portefeuille", ascending=False).reset_index(drop=True)
        df_lb.index += 1
        df_lb['Rang'] = df_lb.index
        df_lb["Portefeuille"] = df_lb["Portefeuille"].map("${:,.2f}".format)
        df_lb["Performance"] = df_lb["Performance"].map("{:+.2f}%".format)
        return df_lb[['Rang', 'Élève', 'Groupe', 'Portefeuille', 'Performance', 'Statut', 'GainJour', 'GainJourPct']]
    return pd.DataFrame()

# --- SÉCURITÉ ET PERSISTENCE PAR JETON DE SESSION ---
if 'user' not in st.session_state:
    st.session_state['user'] = None

if st.session_state['user'] is None:
    session_token = st.query_params.get("session", None)
    if session_token:
        res_token = conn.query("SELECT username FROM sessions WHERE token=:t", params={"t": session_token}, ttl=0)
        if not res_token.empty:
            st.session_state['user'] = res_token.iloc[0]['username']

if "user" in st.query_params:
    del st.query_params["user"]

# MESSAGES FLASH : le reçu de transaction se rend après la bannière,
# dans le flux de la page ; les autres messages restent en toast.
_flash_en_attente = st.session_state.pop('flash_msg', None)

# BANNIÈRE D'EN-TÊTE
st.markdown("""
    <div class="brand-banner">
        <div>
            <div class="brand-title">MONDE & FINANCE</div>
            <div class="brand-subtitle">Plateforme d'apprentissage & simulation boursière</div>
        </div>
        <div class="brand-badge">Édition 2026-2027</div>
    </div>
""", unsafe_allow_html=True)

if _flash_en_attente is not None:
    if _flash_en_attente[0] == "recu":
        st.markdown(_html_recu(_flash_en_attente[1]), unsafe_allow_html=True)
    else:
        st.toast(_flash_en_attente[1])

# --- PORTAIL CONNEXION / INSCRIPTION ---
if st.session_state['user'] is None:
    # Barre latérale masquée tant qu'on n'est pas connecté (vague 2).
    st.markdown("<style>section[data-testid='stSidebar'], div[data-testid='stSidebarCollapsedControl'], div[data-testid='collapsedControl'] { display: none !important; }</style>", unsafe_allow_html=True)
    col_centered = st.columns([1, 1.2, 1])[1]
    with col_centered:
        tab1, tab2 = st.tabs(["Connexion", "Créer un compte"])
        with tab1:
            with st.form("form_connexion"):
                u_login = st.text_input("Identifiant", key="login_user", autocomplete="off")
                p_login = st.text_input("Mot de passe", type="password", key="login_pass", autocomplete="off")
                if st.form_submit_button("Se connecter", use_container_width=True):
                    res = conn.query("SELECT * FROM users WHERE username=:u AND password=:p", params={"u": u_login.strip(), "p": p_login}, ttl=0)
                    if not res.empty:
                        new_token = str(uuid.uuid4())
                        now_str = datetime.now(ZoneInfo("America/Toronto")).strftime("%Y-%m-%d %H:%M:%S")
                        with conn.session as session:
                            session.execute(text("INSERT INTO sessions (token, username, created_at) VALUES (:t, :u, :time)"),
                                            {"t": new_token, "u": u_login.strip(), "time": now_str})
                            session.commit()

                        journaliser_connexion(u_login.strip(), "connexion")
                        st.session_state['user'] = u_login.strip()
                        st.query_params["session"] = new_token
                        st.session_state['flash_msg'] = ("success", f"Bienvenue {u_login.strip()} !")
                        st.rerun()
                    else: st.error("Identifiants incorrects.")

        with tab2:
            try:
                _fermes_inscr = set(conn.query("SELECT groupe FROM groupes_fermes", ttl=0)['groupe'].tolist())
            except Exception:
                _fermes_inscr = set()
            _groupes_ouverts = [g for g in LISTE_GROUPES if g not in _fermes_inscr]
            with st.form("form_inscription"):
                u_new = st.text_input("Identifiant (ex: PrenomNom)", key="new_user", autocomplete="off")
                if _groupes_ouverts:
                    g_new = st.selectbox("Groupe", _groupes_ouverts, key="new_group")
                else:
                    st.warning("Les inscriptions sont fermées pour tous les groupes.")
                    g_new = None
                p_new = st.text_input("Mot de passe", type="password", key="new_pass", autocomplete="off")
                if st.form_submit_button("S'inscrire", use_container_width=True):
                    if u_new and p_new and g_new:
                        # Sécurité : revérifier que le groupe n'a pas été fermé entre-temps
                        _rev = conn.query("SELECT 1 FROM groupes_fermes WHERE groupe=:g", params={"g": g_new}, ttl=0)
                        if not _rev.empty:
                            st.error("Ce groupe vient d'être fermé. Choisissez un autre groupe.")
                        else:
                            res_check = conn.query("SELECT username FROM users WHERE username=:u", params={"u": u_new.strip()}, ttl=0)
                            if res_check.empty:
                                with conn.session as session:
                                    session.execute(text("INSERT INTO users VALUES (:u, :p, 10000.00, :g)"), {"u": u_new.strip(), "p": p_new, "g": g_new})
                                    session.commit()
                                journaliser_connexion(u_new.strip(), "inscription")
                                st.success("Compte créé ! Connectez-vous.")
                            else: st.error("Ce nom d'utilisateur existe déjà.")
                    else: st.error("Veuillez remplir tous les champs.")

else:
    user = st.session_state['user']
    if user != KRACH_EXEMPT_UTILISATEUR and krach_est_actif():
        afficher_page_krach()
        st.stop()
    appliquer_frais_gestion(user)
    executer_ordres_en_attente(user)
    res_u = conn.query("SELECT cash, groupe FROM users WHERE username=:u", params={"u": user}, ttl=0)

    if res_u.empty:
        st.session_state['user'] = None
        st.query_params.clear()
        st.rerun()

    if not joueur_suspendu(user):
        verifier_popup_regles(user)
        verifier_popup_correction(user)

    cash_actuel = float(res_u.iloc[0]['cash'])
    groupe_actuel = res_u.iloc[0]['groupe']

    col_h1, col_h2 = st.columns([4, 1])
    col_h1.markdown(f"<p style='color: #FFFFFF; font-size: 1rem; margin-top:5px;'>Investisseur : <b style='color: #FFFFFF;'>{user}</b> &nbsp;•&nbsp; <span style='background:rgba(229, 9, 20, 0.22); color:#FFFFFF; border:1px solid #E50914; padding:4px 14px; border-radius:12px; font-weight:700; font-size:0.85rem;'>{groupe_actuel}</span></p>", unsafe_allow_html=True)

    if col_h2.button("Déconnexion", use_container_width=True):
        current_token = st.query_params.get("session")
        if current_token:
            with conn.session as session:
                session.execute(text("DELETE FROM sessions WHERE token=:t"), {"t": current_token})
                session.commit()
        st.session_state['user'] = None
        st.query_params.clear()
        st.rerun()

    # --- COMPTE SUSPENDU : LECTURE SEULE ---
    # Un joueur suspendu par l'enseignant (table joueurs_suspendus) voit
    # son portefeuille, mais l'interface s'arrête ici : le seul bouton
    # fonctionnel de sa page est Déconnexion, rendu juste au-dessus.
    if joueur_suspendu(user):
        st.markdown("""
        <div style="background:#1A0505;border:2px solid #E50914;border-radius:12px;padding:18px 20px;margin:10px 0 16px;text-align:center;">
          <div style="font-family:'Bebas Neue','Arial Narrow',sans-serif;font-size:34px;letter-spacing:0.12em;color:#E50914;line-height:1;">COMPTE SUSPENDU</div>
          <div style="color:#EDEDED;font-size:15px;margin-top:8px;line-height:1.5;">Ton enseignant a suspendu ton compte temporairement. Tu peux regarder ton portefeuille, mais tu ne peux rien acheter, rien vendre et rien modifier. Si tu as des questions, parles-en à ton enseignant.</div>
        </div>
        """, unsafe_allow_html=True)
        pos_s = conn.query("SELECT ticker, shares, avg_price FROM portfolio WHERE username=:u", params={"u": user}, ttl=0)
        valeur_actions_s = 0.0
        lignes_s = []
        if not pos_s.empty:
            prix_s = obtenir_prix_groupes(pos_s['ticker'].unique().tolist())
            for _, row_s in pos_s.iterrows():
                tk_s = str(row_s['ticker']).strip().upper()
                info_s = prix_s.get(tk_s)
                px_s = info_s["cad"] if info_s else None
                px_fin_s = px_s if px_s is not None else float(row_s['avg_price'] or 0.0)
                val_s = px_fin_s * float(row_s['shares'])
                valeur_actions_s += val_s
                lignes_s.append({"Titre": tk_s, "Actions": float(row_s['shares']),
                                 "Prix moyen ($)": round(float(row_s['avg_price'] or 0.0), 4),
                                 "Prix actuel ($)": round(px_fin_s, 4),
                                 "Valeur ($)": round(val_s, 2)})
        valeur_totale_s = cash_actuel + valeur_actions_s
        col_s1, col_s2, col_s3 = st.columns(3)
        col_s1.markdown(f"<div class='kpi-card'><div class='kpi-label'>Disponible</div><div class='kpi-value'>${cash_actuel:,.2f}</div></div>", unsafe_allow_html=True)
        col_s2.markdown(f"<div class='kpi-card'><div class='kpi-label'>Actions</div><div class='kpi-value'>${valeur_actions_s:,.2f}</div></div>", unsafe_allow_html=True)
        col_s3.markdown(f"<div class='kpi-card'><div class='kpi-label'>Valeur Totale</div><div class='kpi-value'>${valeur_totale_s:,.2f}</div></div>", unsafe_allow_html=True)
        if lignes_s:
            st.dataframe(pd.DataFrame(lignes_s), use_container_width=True, hide_index=True)
        else:
            st.caption("Aucune position pour le moment.")
        ordres_s = conn.query("SELECT ticker, montant_cad, sens, parts FROM ordres_en_attente WHERE username=:u AND statut='en attente' ORDER BY id", params={"u": user}, ttl=0)
        if not ordres_s.empty:
            st.caption("Ordres en attente (lecture seule) : " + " · ".join(
                (f"{str(o['ticker']).upper()} VENTE de {int(o['parts'] or 0)} actions"
                 if str(o.get('sens') or 'ACHAT').upper() == 'VENTE'
                 else f"{str(o['ticker']).upper()} {float(o['montant_cad']):,.2f} $")
                for _, o in ordres_s.iterrows()))
        st.stop()

    # --- NAVIGATION VERTICALE (barre latérale, vague 2 du 6 nov.
    # 2026) : les onglets vivent à gauche, en boutons pleine largeur.
    # L'onglet actif est rouge plein, les autres sont des cartes
    # sombres. Persistance inchangée : session_state["main_nav_radio"]
    # et le paramètre d'adresse "tab" (F5 garde l'onglet). ---
    TABS_LIST = ["Marché & Analyse", "Mes Positions", "Mon Historique", "Classement"]
    if est_compte_enseignant(user):
        TABS_LIST.append("Supervision Prof")
    if st.session_state.get("main_nav_radio") not in TABS_LIST:
        st.session_state.pop("main_nav_radio", None)
    default_tab = st.query_params.get("tab", "Marché & Analyse")
    if default_tab not in TABS_LIST:
        default_tab = "Marché & Analyse"
    if "main_nav_radio" not in st.session_state:
        st.session_state["main_nav_radio"] = default_tab
    tab_choisi = st.session_state["main_nav_radio"]

    _css_nav = "<style>"
    for _i_nav, _t_nav in enumerate(TABS_LIST):
        if _t_nav == tab_choisi:
            _css_nav += (
                f'div[class~="st-key-navbtn_{_i_nav}"] button {{'
                'background: linear-gradient(180deg, #F6121D 0%, #C40812 100%) !important;'
                'border: 1px solid #FF3B47 !important; border-radius: 10px !important;'
                'box-shadow: 0 10px 22px -8px rgba(229, 9, 20, 0.55) !important;'
                'padding: 10px 14px !important; justify-content: flex-start !important;'
                '}'
                f'div[class~="st-key-navbtn_{_i_nav}"] button p {{'
                'color: #FFFFFF !important; font-weight: 800 !important; font-size: 15px !important;'
                '}')
        else:
            _css_nav += (
                f'div[class~="st-key-navbtn_{_i_nav}"] button {{'
                'background: linear-gradient(180deg, #1E1E1E 0%, #141414 100%) !important;'
                'border: 1px solid #2A2A2A !important; border-radius: 10px !important;'
                'padding: 10px 14px !important; justify-content: flex-start !important;'
                '}'
                f'div[class~="st-key-navbtn_{_i_nav}"] button p {{'
                'color: #D4D4D4 !important; font-weight: 600 !important; font-size: 15px !important;'
                '}'
                f'div[class~="st-key-navbtn_{_i_nav}"] button:hover {{'
                'border-color: #4A4A4A !important;'
                '}')
    _css_nav += "</style>"

    with st.sidebar:
        st.markdown(
            "<div style='font-family:\'Bebas Neue\',\'Work Sans\',sans-serif;font-size:1.45rem;letter-spacing:0.06em;color:#FFFFFF;line-height:1.05;'>MONDE <span style='color:#E50914;'>&</span> FINANCE</div>"
            "<div style='color:#9CA3AF;font-size:0.8rem;margin:2px 0 14px;'>Simulation boursière</div>",
            unsafe_allow_html=True)
        st.markdown(_css_nav, unsafe_allow_html=True)
        for _i_nav, _t_nav in enumerate(TABS_LIST):
            if st.button(_t_nav, key=f"navbtn_{_i_nav}", use_container_width=True):
                st.session_state["main_nav_radio"] = _t_nav
                st.query_params["tab"] = _t_nav
                st.rerun()

    st.query_params["tab"] = tab_choisi

    # Bandeaux des ordres : fragment rafraîchi aux 30 s, pour que les
    # cartes de résultat disparaissent d'elles-mêmes 2 minutes après
    # le règlement de l'ordre, même si personne ne touche à la page.
    try:
        fragment_ordres = st.fragment(run_every=30)
    except TypeError:
        fragment_ordres = st.fragment

    @fragment_ordres
    def _bloc_ordres():
        afficher_ordres_en_attente(user)

    if tab_choisi == "Marché & Analyse":
        _bloc_ordres()

    # --- BANDE DE COTATION (étape 2) : affichage seulement. Le mode
    # démo enseignant (Supervision) peut forcer l'affichage « séance »
    # le soir, pour les yeux des enseignants seulement. ---
    _demo_jour = bool(st.session_state.get("demo_jour")) and est_compte_enseignant(user)

    # --- MODE « LE MARCHÉ DORT » (étape 2, refait en une seule carte
    # à la vague 2 du 6 nov. 2026) : hors séance, une seule grande carte
    # qui porte le titre, la réouverture, le compte à rebours géant et
    # le bouton vers l'onglet Marché. Le bloc entier vit dans un
    # fragment rafraîchi chaque minute : aucun appel réseau, un calcul
    # de dates seulement. Affichage seulement ; les cartes d'ordres en
    # attente sont juste au-dessus. En mode démo enseignant, rien. ---
    if not _marche_ouvert() and not _demo_jour and tab_choisi == "Marché & Analyse":
        try:
            fragment_dort = st.fragment(run_every=60)
        except TypeError:
            fragment_dort = st.fragment

        @fragment_dort
        def _bloc_marche_dort():
            _m_d = datetime.now(ZoneInfo("America/Toronto"))
            _o_d = _prochaine_ouverture(_m_d)
            _j_d = (_o_d.date() - _m_d.date()).days
            _jour_d = "aujourd'hui" if _j_d == 0 else ("demain" if _j_d == 1 else ("lundi" if _o_d.weekday() == 0 else _o_d.strftime("le %d-%m")))
            _h_d, _min_d = _duree_avant_ouverture(_m_d)
            _txt_d = f"{_h_d} h {_min_d:02d} min" if _h_d > 0 else (f"{_min_d} min" if _min_d > 0 else "moins d'une minute")
            st.markdown(
                "<div style='background:radial-gradient(1100px 420px at 50% -60px,#16283B 0%,#0D0D0D 62%);border:1px solid #22384F;border-radius:14px;padding:22px 26px 16px;margin:6px 0 4px;text-align:center;'>"
                "<div style='font-family:\'Bebas Neue\',\'Work Sans\',sans-serif;font-size:2.5rem;line-height:1;color:#FFFFFF;letter-spacing:0.06em;'>LE MARCHÉ <span style='color:#7DB8E8;'>DORT</span></div>"
                f"<div style='color:#9CA3AF;font-size:1.02rem;margin-top:8px;'>Il rouvre {_jour_d} à 9 h 30. Tes ordres l'attendront, et ils s'exécuteront à l'ouverture, au prix d'ouverture.</div>"
                f"<div style='margin-top:14px;'><span style=\"font-family:'Bebas Neue','Work Sans',sans-serif;font-size:3.1rem;color:#FFFFFF;letter-spacing:0.05em;line-height:1;\">{_txt_d}</span></div>"
                "<div style='color:#9CA3AF;font-size:0.78rem;letter-spacing:0.24em;font-weight:700;'>AVANT L'OUVERTURE</div>"
                "</div>", unsafe_allow_html=True)
        _bloc_marche_dort()

    if tab_choisi == "Marché & Analyse":
        afficher_bande_cotation(_marche_ouvert() or _demo_jour)

    # --- MÉTRIQUES DE HAUT DE PAGE ---
    # Rafraîchissement automatique des 4 carrés toutes les 30 s (fragment seul, sans refresh de page).
    # Si la version de Streamlit ne supporte pas run_every, les carrés restent statiques comme avant.
    try:
        fragment_auto = st.fragment(run_every=60)
    except TypeError:
        fragment_auto = st.fragment

    @fragment_auto
    def afficher_metrics_live():
        pos_df = conn.query("SELECT ticker, shares, avg_price FROM portfolio WHERE username=:u", params={"u": user}, ttl=0)
        valeur_actions = 0.0

        if not pos_df.empty:
            unique_tks = pos_df['ticker'].unique().tolist()
            prix_dict = obtenir_prix_groupes(unique_tks)
            for _, row in pos_df.iterrows():
                tk_sym = str(row['ticker']).strip().upper()
                _info_px = prix_dict.get(tk_sym)
                px_actuel = _info_px["cad"] if _info_px else None
                px_final = px_actuel if px_actuel is not None else float(row['avg_price'] or 0.0)
                valeur_actions += px_final * row['shares']

        valeur_totale = cash_actuel + valeur_actions
        profit_total = valeur_totale - 10000.00
        rendement_pct = (profit_total / 10000.00) * 100

        col_m1, col_m2, col_m3, col_m4 = st.columns(4)
        col_m1.markdown(f"<div class='kpi-card'><div class='kpi-label'>Disponible</div><div class='kpi-value'>${cash_actuel:,.2f}</div></div>", unsafe_allow_html=True)
        col_m2.markdown(f"<div class='kpi-card'><div class='kpi-label'>Actions</div><div class='kpi-value'>${valeur_actions:,.2f}</div></div>", unsafe_allow_html=True)
        col_m3.markdown(f"<div class='kpi-card'><div class='kpi-label'>Valeur Totale</div><div class='kpi-value'>${valeur_totale:,.2f}</div></div>", unsafe_allow_html=True)
        classe_delta = "kpi-delta up" if profit_total >= 0 else "kpi-delta down"
        fleche_delta = "▲" if profit_total >= 0 else "▼"
        classe_carte = "kpi-card kpi-up" if profit_total >= 0 else "kpi-card kpi-down"
        col_m4.markdown(f"<div class='{classe_carte}'><div class='kpi-label'>Gains / Pertes</div><div class='kpi-value'>${profit_total:,.2f}</div><div class='{classe_delta}'>{fleche_delta} {rendement_pct:+.2f}%</div></div>", unsafe_allow_html=True)

        if not pos_df.empty:
            items_tape = ""
            for _, row in pos_df.iterrows():
                tk_tape = str(row['ticker']).strip().upper()
                _info_tape = prix_dict.get(tk_tape)
                pm_tape = float(row['avg_price'] or 0.0)
                dv_tape = _info_tape["devise"] if _info_tape else devise_naturelle(tk_tape)
                px_cad_tape = _info_tape["cad"] if _info_tape else None
                px_natif_tape = _info_tape["natif"] if _info_tape else None
                # Flèche : comparaison en CAD (prix actuel CAD vs coût moyen CAD).
                base_cmp = px_cad_tape if px_cad_tape is not None else pm_tape
                # Prix affiché : devise naturelle du titre.
                px_aff = px_natif_tape if px_natif_tape is not None else vers_natif(pm_tape, dv_tape)
                fmt_tape = fmt_prix(px_aff, dv_tape)
                couleur_tape = "#34D399" if base_cmp >= pm_tape else "#F87171"
                fleche_tape = "▲" if base_cmp >= pm_tape else "▼"
                items_tape += f"<span class='item'><b>{tk_tape}</b>&nbsp;<span style='color:{couleur_tape};'>{fleche_tape} {fmt_tape}</span></span>"
            if items_tape:
                duree_tape = max(20, 5 * len(pos_df))
                css_tape = "<style>body{margin:0;background:#161616;font-family:'Work Sans',sans-serif;overflow:hidden;border:1px solid #2E2E2E;border-radius:10px;box-sizing:border-box;height:44px}.track{display:flex;width:max-content;padding:11px 0;animation:tapeScroll " + str(duree_tape) + "s linear infinite}.track:hover{animation-play-state:paused}.item{padding:0 22px;border-right:1px solid rgba(255,255,255,0.12);color:#FFFFFF;font-weight:600;white-space:nowrap;font-variant-numeric:tabular-nums}.item b{font-family:'Bebas Neue','Work Sans',sans-serif;font-weight:400;letter-spacing:0.05em;font-size:17px}@keyframes tapeScroll{from{transform:translateX(0)}to{transform:translateX(-50%)}}</style>"
                components.html(f"<!DOCTYPE html><html><head>{css_tape}</head><body><div class='track'>{items_tape}{items_tape}</div></body></html>", height=46)

        # --- FRAIS PAYÉS (mode vraie bourse) : cumulatif visible par l'élève ---
        try:
            if not compte_exempte_frais(user):
                fq = conn.query("SELECT type, SUM(montant) AS tot FROM frais WHERE username=:u GROUP BY type",
                                params={"u": user}, ttl=30)
                tf = {str(r['type']): float(r['tot'] or 0) for _, r in fq.iterrows()} if not fq.empty else {}
                st.markdown(
                    f"<div style='color:#9CA3AF;font-size:12.5px;margin-top:10px;'>"
                    f"Frais payés depuis le mode vraie bourse : transactions <b style='color:#FFFFFF;'>{tf.get('transaction', 0.0):,.2f} $</b>"
                    f" &nbsp;•&nbsp; conversion <b style='color:#FFFFFF;'>{tf.get('conversion', 0.0):,.2f} $</b>"
                    f" &nbsp;•&nbsp; gestion <b style='color:#FFFFFF;'>{tf.get('gestion', 0.0):,.2f} $</b></div>",
                    unsafe_allow_html=True)
        except Exception:
            pass

    if tab_choisi == "Marché & Analyse":
        afficher_metrics_live()


    # --- ONGLET 1 : MARCHÉ & ANALYSE ---
    if tab_choisi == "Marché & Analyse":
        col_l1, col_l2, col_l3 = st.columns(3)
        col_l1.link_button("Les Affaires", "https://www.lesaffaires.com/?view=register&product_id=1898&plan_id=62962&utm_campaign=ABNT_PROMO30_ADSGOOGLE&utm_medium=ADS&utm_source=ADSGOOGLE&utm_term=landing&gad_source=1&gad_campaignid=24159803993&gbraid=0AAAAADel4hnhaUpWgv3yFaDiNmCZAJv32&gclid=CjwKCAjwrP3VBhBbEiwAnaqpQyOPax6Hc_HEcl3kWXH3NxC0aQVSEw-GAa87RTweJxM5yyasiT0W4RoCAVQQAvD_BwE", use_container_width=True)
        col_l2.link_button("Barchart", "https://www.barchart.com/", use_container_width=True)
        col_l3.link_button("Yahoo Finance", "https://ca.finance.yahoo.com/", use_container_width=True)

        col_s1, col_s2 = st.columns([4, 1])
        with col_s1:
            search_query = st.text_input(
                "Rechercher une action (TSX, NYSE, Nasdaq seulement)",
                value="",
                placeholder="Tapez le nom d'une entreprise ou un symbole (ex: Apple, SHOP.TO)...",
                key="recherche_ticker"
            )
        with col_s2:
            st.markdown("<br>", unsafe_allow_html=True)
            if st.button("Rafraîchir le cours", use_container_width=True):
                st.rerun()

        selected_ticker = "AAPL"

        if search_query and len(search_query.strip()) > 0:
            query_clean = search_query.strip()
            resultats = rechercher_symbole_universel(query_clean)
            if resultats:
                options_dict = {res['label']: res['symbol'] for res in resultats}
                choix_label = st.selectbox("Sélectionnez l'action :", list(options_dict.keys()))
                selected_ticker = options_dict[choix_label]
            else:
                selected_ticker = query_clean.upper()

        # Redirection du garde-fou jumeau .TO : dans le panneau d'ordre,
        # l'élève a choisi la version de Toronto d'un symbole nu.
        _redir_jumeau = st.session_state.get('jumeau_redirige')
        if _redir_jumeau and _redir_jumeau.endswith('.TO') and _redir_jumeau[:-3] == selected_ticker:
            selected_ticker = _redir_jumeau
            st.session_state['jumeau_redirige'] = None

        details = obtenir_details_financiers(selected_ticker)

        if details == {"erreur": "non_na"}:
            st.error(f"**Instrument non autorisé :** Seules les actions et FNB cotés au TSX (Toronto), au NYSE ou au Nasdaq sont permis. Aucune crypto, devise, future ni indice.")
        elif details:
            prix, var, var_pct = details["Prix"], details["Variation"], details["VariationPct"]
            prix_cad = details.get("PrixCAD") or prix
            devise_titre = str(details.get("Devise") or "CAD").upper()
            chart_color = "#10B981" if var >= 0 else "#EF4444"
            fill_color = "rgba(16, 185, 129, 0.20)" if var >= 0 else "rgba(239, 68, 68, 0.20)"
            signe = "+" if var >= 0 else ""
            fmt_prix_carte = fmt_prix(prix, devise_titre)

            col_chart, col_order = st.columns([2.2, 1])

            with col_chart:
                st.markdown(f"<div class='quote-card {'up' if var >= 0 else 'down'}' data-tk='{selected_ticker}'><div class='quote-ticker'>{selected_ticker}</div><div class='quote-price'>{fmt_prix_carte}</div><div class='quote-var {'up' if var >= 0 else 'down'}'>{signe}{var_pct:.2f}% ({signe}{var:,.2f})</div></div>", unsafe_allow_html=True)
                if devise_titre == "USD":
                    st.caption("Prix en dollars américains (devise du titre), comme sur les vrais sites. Ton compte est en dollars canadiens : la conversion se fait à l'achat, au taux du jour.")
                else:
                    st.caption("Prix en dollars canadiens (devise du titre).")

                @st.fragment
                def afficher_graphique_interactif(ticker):
                    period_map = {
                        "1d": "1 Jour",
                        "5d": "5 Jours",
                        "1mo": "1 Mois",
                        "3mo": "3 Mois",
                        "6mo": "6 Mois",
                        "1y": "1 An"
                    }

                    selected_period = st.radio(
                        "Horizon d'analyse",
                        options=list(period_map.keys()),
                        format_func=lambda x: period_map[x],
                        horizontal=True,
                        key=f"horizon_{ticker}"
                    )

                    type_graph = st.radio(
                        "Type de graphique",
                        options=["Ligne", "Chandeliers"],
                        horizontal=True,
                        key=f"typegraph_{ticker}"
                    )

                    df_hist = obtenir_historique(ticker, selected_period, details.get("Devise", "CAD"))
                    if df_hist is not None and not df_hist.empty:
                        min_p = float(df_hist['Close'].min())
                        max_p = float(df_hist['Close'].max())
                        delta = max_p - min_p

                        padding = delta * 0.08 if delta > 0 else min_p * 0.02
                        y_min = max(0, min_p - padding) if min_p > 0 else min_p - padding
                        y_max = max_p + padding

                        tick_fmt = "$.4f" if max_p < 1 else "$.2f"

                        if type_graph == "Chandeliers" and all(c in df_hist.columns for c in ['Open', 'High', 'Low', 'Close']):
                            fig = make_subplots(rows=2, cols=1, shared_xaxes=True,
                                                row_heights=[0.72, 0.28], vertical_spacing=0.06)
                            fig.add_trace(go.Candlestick(
                                x=df_hist.index,
                                open=df_hist['Open'], high=df_hist['High'],
                                low=df_hist['Low'], close=df_hist['Close'],
                                increasing_line_color='#10B981', increasing_fillcolor='#10B981',
                                decreasing_line_color='#EF4444', decreasing_fillcolor='#EF4444',
                                name='Cours'
                            ), row=1, col=1)
                            if len(df_hist) >= 20:
                                fig.add_trace(go.Scatter(
                                    x=df_hist.index, y=df_hist['Close'].rolling(window=20).mean(),
                                    mode='lines', line=dict(color='#F59E0B', width=1.5), name='MM 20'
                                ), row=1, col=1)
                            if len(df_hist) >= 50:
                                fig.add_trace(go.Scatter(
                                    x=df_hist.index, y=df_hist['Close'].rolling(window=50).mean(),
                                    mode='lines', line=dict(color='#8B5CF6', width=1.5), name='MM 50'
                                ), row=1, col=1)
                            vol = df_hist['Volume'].fillna(0) if 'Volume' in df_hist.columns else pd.Series(0, index=df_hist.index)
                            coul_vol = ['#10B981' if c >= o else '#EF4444' for c, o in zip(df_hist['Close'], df_hist['Open'])]
                            fig.add_trace(go.Bar(
                                x=df_hist.index, y=vol, marker_color=coul_vol, opacity=0.55, name='Volume'
                            ), row=2, col=1)
                            fig.update_layout(
                                paper_bgcolor='rgba(0,0,0,0)',
                                plot_bgcolor='rgba(0,0,0,0)',
                                height=460,
                                margin=dict(l=10, r=10, t=30, b=10),
                                xaxis_rangeslider_visible=False,
                                showlegend=True,
                                legend=dict(orientation='h', yanchor='bottom', y=1.02, xanchor='left', x=0,
                                            font=dict(color='#FFFFFF', size=11)),
                                font=dict(color='#FFFFFF', family='Work Sans'),
                                xaxis=dict(showgrid=True, gridcolor='rgba(255,255,255,0.07)', gridwidth=0.8, zeroline=False),
                                xaxis2=dict(showgrid=False, zeroline=False),
                                yaxis=dict(range=[y_min, y_max], showgrid=True, gridcolor='rgba(255,255,255,0.07)',
                                           gridwidth=0.8, zeroline=False, side='right', tickformat=tick_fmt),
                                yaxis2=dict(showgrid=False, zeroline=False, side='right'),
                            )
                            st.plotly_chart(fig, use_container_width=True)
                            return

                        fig = go.Figure()

                        fig.add_trace(go.Scatter(
                            x=df_hist.index,
                            y=df_hist['Close'],
                            mode='lines',
                            line=dict(color=chart_color, width=3),
                            fill='tozeroy',
                            fillcolor=fill_color,
                            hovertemplate='%{x|%d %b %H:%M}<br><b>%{y:' + tick_fmt + '}</b><extra></extra>'
                        ))

                        fig.add_trace(go.Scatter(
                            x=[df_hist.index[-1]],
                            y=[df_hist['Close'].iloc[-1]],
                            mode='markers',
                            marker=dict(size=18, color=chart_color, opacity=0.30),
                            hoverinfo='skip',
                            showlegend=False
                        ))
                        fig.add_trace(go.Scatter(
                            x=[df_hist.index[-1]],
                            y=[df_hist['Close'].iloc[-1]],
                            mode='markers',
                            marker=dict(size=8, color=chart_color, line=dict(color='#FFFFFF', width=1.5)),
                            hoverinfo='skip',
                            showlegend=False
                        ))

                        fig.update_layout(
                            paper_bgcolor='rgba(0,0,0,0)',
                            plot_bgcolor='rgba(0,0,0,0)',
                            height=340,
                            margin=dict(l=10, r=10, t=10, b=10),
                            xaxis=dict(showgrid=True, gridcolor='rgba(255,255,255,0.07)', gridwidth=0.8, zeroline=False),
                            yaxis=dict(
                                range=[y_min, y_max],
                                showgrid=True,
                                gridcolor='rgba(255,255,255,0.07)',
                                gridwidth=0.8,
                                zeroline=False,
                                side="right",
                                tickformat=tick_fmt
                            ),
                            font=dict(color="#FFFFFF", family="Work Sans")
                        )
                        st.plotly_chart(fig, use_container_width=True)

                afficher_graphique_interactif(selected_ticker)

                nouvelles = obtenir_nouvelles(selected_ticker)
                if nouvelles:
                    st.markdown("<div style='font-family:\'Bebas Neue\',\'Work Sans\',sans-serif;font-size:1.55rem;letter-spacing:0.06em;color:#FFFFFF;margin:14px 0 8px;'>ACTUALITÉS <span style='color:#E50914;'>" + html.escape(selected_ticker.upper()) + "</span></div>", unsafe_allow_html=True)
                    for n in nouvelles:
                        nt, nl, npub, ndate = n.get('title'), n.get('link'), n.get('publisher', ''), n.get('date', '')
                        if nt and nl:
                            _meta_actu = " · ".join([x for x in [html.escape(str(npub)), ndate] if x])
                            st.markdown(
                                "<div style='background:linear-gradient(180deg,#232323 0%,#171717 100%);border:1px solid rgba(255,255,255,0.10);border-left:3px solid #E50914;border-radius:10px;padding:11px 14px;margin-bottom:8px;'>"
                                f"<a href='{html.escape(str(nl), quote=True)}' target='_blank' style='color:#FFFFFF;font-weight:600;font-size:15px;text-decoration:none;line-height:1.35;'>{html.escape(str(nt))}</a>"
                                + (f"<div style='color:#9CA3AF;font-size:12px;margin-top:3px;'>{_meta_actu}</div>" if _meta_actu else "")
                                + "</div>",
                                unsafe_allow_html=True)

            with col_order:
                st.markdown("### Passer un ordre")
                mode_ordre = st.radio("Mode d'achat", ["Par quantité", "Par montant ($)"], horizontal=True, key=f"mode_{selected_ticker}")

                if mode_ordre == "Par quantité":
                    qty_achat = st.number_input("Quantité", min_value=1, step=1, value=1, key=f"qty_{selected_ticker}")
                    _cout_a = prix_cad * qty_achat
                    _lignes_a = [(f"{qty_achat} action(s) à {fmt_prix(prix, devise_titre)}", f"${_cout_a:,.2f}")]
                    _tot_a = _cout_a
                    if not compte_exempte_frais(user):
                        _fc_a = round(FRAIS_CONVERSION_PCT * _cout_a, 2) if devise_titre == "USD" else 0.0
                        _lignes_a.append(("Frais de transaction", f"${FRAIS_TRANSACTION:,.2f}"))
                        if _fc_a > 0:
                            _lignes_a.append(("Conversion (1,5 %, titre américain)", f"${_fc_a:,.2f}"))
                        _tot_a = _cout_a + FRAIS_TRANSACTION + _fc_a
                    st.markdown(_html_recu({"genre": "apercu", "titre": "TON ORDRE", "sous": f"{selected_ticker.upper()} · estimation au prix actuel", "lignes": _lignes_a, "total": ("Total débité", f"${_tot_a:,.2f}"), "pied": "Estimation : le prix d'exécution est celui du moment où tu confirmes."}), unsafe_allow_html=True)
                    qty_vente = qty_achat
                else:
                    montant = st.number_input("Montant à investir ($ CAD)", min_value=1.0, step=10.0, value=100.0, key=f"montant_{selected_ticker}")
                    qty_achat = int(montant // prix_cad) if prix_cad and prix_cad > 0 else 0
                    if qty_achat >= 1:
                        _cout_b = qty_achat * prix_cad
                        _lignes_b = [(f"{qty_achat} action(s) à {fmt_prix(prix, devise_titre)}", f"${_cout_b:,.2f}")]
                        _tot_b = _cout_b
                        if not compte_exempte_frais(user):
                            _fc_b = round(FRAIS_CONVERSION_PCT * _cout_b, 2) if devise_titre == "USD" else 0.0
                            _lignes_b.append(("Frais de transaction", f"${FRAIS_TRANSACTION:,.2f}"))
                            if _fc_b > 0:
                                _lignes_b.append(("Conversion (1,5 %, titre américain)", f"${_fc_b:,.2f}"))
                            _tot_b = _cout_b + FRAIS_TRANSACTION + _fc_b
                        st.markdown(_html_recu({"genre": "apercu", "titre": "TON ORDRE", "sous": f"{selected_ticker.upper()} · ce que ton montant peut acheter, au prix actuel", "lignes": _lignes_b, "total": ("Total débité", f"${_tot_b:,.2f}"), "pied": "Estimation : le prix d'exécution est celui du moment où tu confirmes."}), unsafe_allow_html=True)
                    else:
                        st.warning("Ce montant ne permet pas d'acheter une seule action à ce prix.")
                    qty_vente = st.number_input("Quantité à vendre", min_value=1, step=1, value=1, key=f"qtyv_{selected_ticker}")

                if devise_titre == "USD":
                    _taux_jour = obtenir_taux_usdcad()
                    if _taux_jour:
                        st.caption(f"Ajustement de change : 1 $ US = {_taux_jour:.4f} $ CAD aujourd'hui. Le montant débité ou crédité est toujours en dollars canadiens.")

                st.caption("Règle : ta position sur un titre ne peut pas dépasser 5 % de son volume d'échange quotidien.")
                if not compte_exempte_frais(user):
                    st.caption("Frais réels : 10 $ par transaction et 1,5 % de conversion sur les titres américains. Chaque achat vaut entre 2 % et 25 % de ton compte, maximum 5 achats par jour. Le détail complet est dans les règles du jeu, en haut de la page.")
                vol_jour_cap = obtenir_volume_quotidien_moyen(selected_ticker)
                if vol_jour_cap and LIMITE_VOLUME_PCT * vol_jour_cap < 1000000:
                    st.caption(f"Position maximale sur {selected_ticker.upper()} : {LIMITE_VOLUME_PCT * vol_jour_cap:,.0f} $")
                if est_etf(selected_ticker):
                    st.caption("Revente possible 1 h après l'achat (ETF).")
                else:
                    st.caption("Revente possible 30 minutes après l'achat.")

                # --- GARDE-FOU JUMEAU .TO ---
                # Si le symbole nu a un jumeau à Toronto (DOL le FNB
                # américain contre DOL.TO Dollarama), l'élève confirme
                # lequel des deux il veut avant de pouvoir acheter.
                # Aucun blocage définitif : un choix, puis l'achat continue.
                jumeau = jumeau_to(selected_ticker) if '.' not in selected_ticker else None
                jumeau_ok = bool(st.session_state.get(f"jumeau_ok_{selected_ticker}"))
                achat_bloque_jumeau = bool(jumeau and not jumeau_ok)
                if achat_bloque_jumeau:
                    jb1, jb2 = st.columns(2)
                    if jumeau.get('cdr_to'):
                        _titre_j = "ATTENTION : CE N'EST PAS LA MÊME ACTION"
                        _desc_j = (f"{selected_ticker.upper()}.TO n'est pas l'action {jumeau['nom_base']}. C'est un CDR, un certificat qui suit son cours : "
                                   "une part vaut beaucoup moins cher parce qu'elle ne représente qu'un morceau d'une action. Elle se paie en dollars canadiens, "
                                   "sans conversion, et son prix est protégé contre les hauts et les bas du taux de change. Son rendement suit l'action, "
                                   "mais pas exactement, et de petits frais sont prélevés à l'intérieur du certificat.")
                        _nom_affiche_to = jumeau.get('court_to') or jumeau['nom_to']
                        _detail_to = "Certificat (CDR) · Toronto · en dollars canadiens · suit l'action, sans en être une"
                        lib_jb1 = f"New York : {selected_ticker}, la vraie action, en dollars US"
                        lib_jb2 = f"Toronto : {selected_ticker}.TO, le certificat (CDR), en dollars canadiens"
                    elif jumeau['nom_base'] == jumeau['nom_to']:
                        _titre_j = "TON ACTION VIENT D'OÙ ?"
                        _desc_j = "La même entreprise se vend à New York et à Toronto. Choisis sa provenance : la devise change, et la conversion de 1,5 % s'applique sur le titre américain, à l'achat et à la vente."
                        lib_jb1 = f"New York : {selected_ticker}, en dollars US"
                        lib_jb2 = f"Toronto : {selected_ticker}.TO, en dollars canadiens"
                        _nom_affiche_to = jumeau['nom_to']
                        _detail_to = "Bourse de Toronto · en dollars canadiens · aucune conversion"
                    else:
                        _titre_j = "DEUX TITRES SE RESSEMBLENT"
                        _desc_j = "Deux entreprises différentes portent presque le même symbole. Choisis le bon avant d'acheter."
                        lib_jb1 = f"New York : {selected_ticker}, le titre américain"
                        lib_jb2 = f"Toronto : {selected_ticker}.TO, le titre canadien"
                        _nom_affiche_to = jumeau['nom_to']
                        _detail_to = "Bourse de Toronto · en dollars canadiens · aucune conversion"
                    _carte_j = (
                        "<div style='background:linear-gradient(180deg,#262626 0%,#1A1A1A 100%);border:1px solid rgba(255,255,255,0.12);border-top:6px solid #E50914;border-radius:14px;padding:18px 20px 14px;margin:10px 0 6px;box-shadow:0 16px 32px -14px rgba(0,0,0,0.9);'>"
                        f"<div style=\"font-family:'Bebas Neue','Work Sans',sans-serif;font-size:1.7rem;letter-spacing:0.05em;color:#FFFFFF;line-height:1;\">{_titre_j}</div>"
                        f"<div style='color:#D1D5DB;font-size:0.95rem;margin:6px 0 12px;'>{_desc_j}</div>"
                        "<div style='display:flex;gap:12px;flex-wrap:wrap;'>"
                        f"<div style='flex:1;min-width:190px;background:#0D0D0D;border:1.5px solid #3A3A3A;border-radius:10px;padding:12px 14px;'><div style=\"font-family:'Bebas Neue','Work Sans',sans-serif;font-size:1.5rem;color:#FFFFFF;letter-spacing:0.04em;\">{html.escape(selected_ticker.upper())}</div><div style='color:#FFFFFF;font-weight:700;font-size:0.95rem;'>{html.escape(str(jumeau['nom_base']))}</div><div style='color:#9CA3AF;font-size:0.88rem;margin-top:2px;'>Bourse des États-Unis · en dollars US · conversion de 1,5 %</div></div>"
                        f"<div style='flex:1;min-width:190px;background:#0D0D0D;border:1.5px solid #3A3A3A;border-radius:10px;padding:12px 14px;'><div style=\"font-family:'Bebas Neue','Work Sans',sans-serif;font-size:1.5rem;color:#FFFFFF;letter-spacing:0.04em;\">{html.escape(selected_ticker.upper())}.TO</div><div style='color:#FFFFFF;font-weight:700;font-size:0.95rem;'>{html.escape(str(_nom_affiche_to))}</div><div style='color:#9CA3AF;font-size:0.88rem;margin-top:2px;'>{_detail_to}</div></div>"
                        "</div>"
                        "<div style='color:#9CA3AF;font-size:0.88rem;margin-top:10px;'>Choisis la provenance ci-dessous : l'achat se débloque aussitôt.</div></div>")
                    st.markdown(_carte_j, unsafe_allow_html=True)
                    if jb1.button(lib_jb1, key=f"jb_us_{selected_ticker}", use_container_width=True):
                        st.session_state[f"jumeau_ok_{selected_ticker}"] = True
                        st.rerun()
                    if jb2.button(lib_jb2, key=f"jb_to_{selected_ticker}", use_container_width=True):
                        st.session_state['jumeau_redirige'] = selected_ticker + ".TO"
                        st.rerun()

                col_b, col_s = st.columns(2)

                # ACHAT
                if col_b.button("Acheter", use_container_width=True, disabled=achat_bloque_jumeau):
                    if plafond_achats_atteint(user):
                        dialogue_pause_bourse()
                    elif not _marche_ouvert() and _prix_gele_ou_none(selected_ticker) is None:
                        afficher_refus(f"Marché fermé : le prix de clôture de {selected_ticker.upper()} n'a pas pu être figé pour cette séance. La transaction est refusée plutôt que faite à un prix qui bouge. Réessaie plus tard ou attends l'ouverture (9 h 30).")
                    elif titre_suspendu(selected_ticker):
                        afficher_refus(f"{selected_ticker.upper()} est suspendu pour le moment : ses prix ne concordent pas entre les sources de données. Aucun achat ni vente tant que la suspension n'est pas levée.")
                    elif compte_en_verification(user):
                        afficher_refus("Ton compte est en vérification : une erreur de prix a faussé ton solde. Les transactions sont bloquées jusqu'à ce que ton enseignant ait corrigé ton compte.")
                    elif prix_incoherent(selected_ticker, obtenir_prix_actuel(selected_ticker))[0]:
                        afficher_refus(f"Transaction refusée : le prix de {selected_ticker.upper()} ne concorde pas avec sa dernière clôture (écart anormal entre les sources de prix). C'est le signe de données incohérentes, pas d'un vrai mouvement de marché.")
                    elif qty_achat < 1:
                        afficher_refus("Augmentez le montant pour acheter au moins une action.")
                    elif not verifier_cooldown(user, delai_secondes=3):
                        afficher_refus("Veuillez attendre 3 secondes entre chaque transaction.")
                    else:
                        prix_instantane = obtenir_prix_actuel(selected_ticker) or prix_cad
                        cost_real = prix_instantane * qty_achat

                        c_res = conn.query("SELECT cash FROM users WHERE username=:u", params={"u": user}, ttl=0)
                        cash_actuel_db = float(c_res.iloc[0]['cash']) if not c_res.empty else 0.0

                        msg_limite = verifier_limite_volume(user, selected_ticker, prix_instantane, cost_real)
                        exempte = compte_exempte_frais(user)
                        frais_fixe, frais_conv = (0.0, 0.0) if exempte else frais_pour_ordre(devise_titre, cost_real)
                        total_debit = cost_real + frais_fixe + frais_conv
                        bloque_cc, var_cc = (False, None) if exempte else coupe_circuit_actif(selected_ticker)
                        part_apres = 0.0 if exempte else part_titre_apres_achat(user, selected_ticker, prix_instantane, qty_achat)
                        plancher_min = None if exempte else plancher_achat_minimum(user)
                        if msg_limite:
                            afficher_refus(msg_limite)
                        elif bloque_cc:
                            afficher_refus(f"Coupe-circuit : {selected_ticker.upper()} a bougé de {var_cc:+.1f} % aujourd'hui. Quand un titre bouge de plus de 30 % dans une journée, les achats sont suspendus jusqu'au prochain jour de bourse, comme sur les vrais marchés. Tu peux toujours vendre.")
                        elif part_apres > PLAFOND_TITRE_PCT:
                            afficher_refus(f"Maximum 25 % sur un seul titre : après cet achat, {selected_ticker.upper()} représenterait {part_apres:.1f} % de ton compte. Réduis la quantité ou choisis un autre titre.")
                        elif plancher_min is not None and cost_real < plancher_min:
                            afficher_refus(f"Minimum 2 % sur un achat : une position doit compter pour vrai, pas être une décoration. Pour ton compte, un achat vaut au moins {plancher_min:,.2f} $ en ce moment. Augmente le montant ou choisis un titre moins cher.")
                        elif ordres_ouverture_actif(user) and not _marche_ouvert() and mode_ordre == "Par quantité":
                            # Décision de Mathieu (3 nov. 2026) : le soir, un ordre en
                            # attente se place par montant seulement. En quantité, le
                            # nombre d'actions choisi au prix gelé ne peut pas être
                            # garanti à l'ouverture ; le montant, lui, l'est toujours.
                            afficher_refus("Marché fermé : le soir, un ordre en attente se place par montant seulement. Passe en mode « Par montant ($) » ci-dessus : le montant que tu choisis est réservé, et le nombre d'actions sera fixé à l'ouverture, au prix d'ouverture.")
                        elif ordres_ouverture_actif(user) and not _marche_ouvert():
                            # Hors heures, l'achat devient un ordre en
                            # attente exécuté au prix d'ouverture de la
                            # prochaine séance, pas au prix gelé.
                            if prix_instantane is None or prix_instantane <= 0:
                                afficher_refus("Prix indisponible pour le moment : impossible de placer l'ordre. Réessaie plus tard.")
                            elif cash_actuel_db < total_debit:
                                afficher_refus("Fonds insuffisants.")
                            elif len(ordres_en_attente_pour(user)) >= LIMITE_ORDRES_EN_ATTENTE:
                                afficher_refus(f"Tu as déjà {LIMITE_ORDRES_EN_ATTENTE} ordres en attente. Attends leur exécution à l'ouverture, ou annules-en un.")
                            elif achat_hors_heures_deja_fait(user, selected_ticker, _prochaine_seance_execution(datetime.now(ZoneInfo("America/Toronto")))):
                                afficher_refus(f"Marché fermé : hors des heures de marché, c'est un achat par entreprise par jour. Tu as déjà un achat de {selected_ticker.upper()} aujourd'hui ou en attente. Choisis une autre entreprise, ou reviens demain.")
                            else:
                                session_exec = creer_ordre_en_attente(user, selected_ticker, total_debit, devise_titre)
                                if session_exec is None:
                                    afficher_refus("Fonds insuffisants.")
                                else:
                                    st.session_state['flash_msg'] = ("recu", {"genre": "ordre", "titre": "ORDRE EN ATTENTE", "sous": f"{selected_ticker.upper()}", "lignes": [("Montant réservé", f"${total_debit:,.2f}")], "total": None, "pied": f"S'exécute à l'ouverture du {session_exec}, au prix d'ouverture, jamais au prix de fermeture d'hier. Le nombre d'actions sera fixé à ce moment-là. Annulable dans « Mes ordres en attente »."})
                                    st.rerun()
                        elif cash_actuel_db >= total_debit:
                            now_str = datetime.now(ZoneInfo("America/Toronto")).strftime("%Y-%m-%d %H:%M:%S")
                            # Verrou par utilisateur + solde relu DANS la transaction :
                            # des sessions simultanées du même compte ne peuvent pas
                            # dépenser deux fois le même argent.
                            achat_ok = False
                            with conn.session as session:
                                _verrou_transaction(session, user)
                                cash_rel = session.execute(text("SELECT cash FROM users WHERE username=:u"), {"u": user}).scalar()
                                if cash_rel is not None and float(cash_rel) >= total_debit:
                                    session.execute(text("UPDATE users SET cash = cash - :cost WHERE username = :u"), {"cost": total_debit, "u": user})
                                    p_row = session.execute(text("SELECT shares, avg_price FROM portfolio WHERE username=:u AND LOWER(ticker)=LOWER(:t)"), {"u": user, "t": selected_ticker}).fetchone()
                                    if p_row is not None:
                                        anc_s, anc_p = int(p_row[0]), float(p_row[1] or prix_instantane)
                                        n_s = anc_s + qty_achat
                                        n_p = ((anc_s * anc_p) + (qty_achat * prix_instantane)) / n_s
                                        session.execute(text("UPDATE portfolio SET shares=:s, avg_price=:p WHERE username=:u AND LOWER(ticker)=LOWER(:t)"), {"s": n_s, "p": n_p, "u": user, "t": selected_ticker})
                                    else:
                                        session.execute(text("INSERT INTO portfolio VALUES (:u, :t, :s, :p)"), {"u": user, "t": selected_ticker.upper(), "s": qty_achat, "p": prix_instantane})
                                    session.execute(text("INSERT INTO transactions (username, ticker, shares, price, total, timestamp) VALUES (:u, :t, :s, :p, :tot, :time)"),
                                                    {"u": user, "t": selected_ticker.upper(), "s": qty_achat, "p": prix_instantane, "tot": cost_real, "time": now_str})
                                    enregistrer_frais(session, user, "transaction", frais_fixe, selected_ticker.upper())
                                    enregistrer_frais(session, user, "conversion", frais_conv, selected_ticker.upper())
                                    session.commit()
                                    achat_ok = True
                                else:
                                    session.rollback()
                            if not achat_ok:
                                afficher_refus("Fonds insuffisants.")
                            else:
                                _prix_affiche_a = fmt_prix(vers_natif(prix_instantane, 'USD'), 'USD') if devise_titre == "USD" else f"${prix_instantane:,.2f}"
                                _lignes_a = [(f"{qty_achat} actions à {_prix_affiche_a}", f"${cost_real:,.2f}"), ("Frais de transaction", f"${frais_fixe:,.2f}")]
                                if frais_conv > 0:
                                    _lignes_a.append(("Conversion (1,5 %, titre américain)", f"${frais_conv:,.2f}"))
                                _pied_a = f"Il te reste ${cash_actuel_db - total_debit:,.2f} en argent comptant."
                                if devise_titre == "USD":
                                    _taux_fx = obtenir_taux_usdcad()
                                    if _taux_fx:
                                        _pied_a += f" Montants en dollars canadiens, au taux {_taux_fx:.4f}."
                                st.session_state['flash_msg'] = ("recu", {"genre": "achat", "titre": "ACHAT CONFIRMÉ", "sous": f"{selected_ticker.upper()} - {qty_achat} actions", "lignes": _lignes_a, "total": ("Total débité", f"${total_debit:,.2f}"), "pied": _pied_a})
                                st.rerun()
                        else: afficher_refus("Fonds insuffisants.")

                # VENTE
                if col_s.button("Vendre", use_container_width=True):
                    if not _marche_ouvert() and _prix_gele_ou_none(selected_ticker) is None:
                        afficher_refus(f"Marché fermé : le prix de clôture de {selected_ticker.upper()} n'a pas pu être figé pour cette séance. La transaction est refusée plutôt que faite à un prix qui bouge. Réessaie plus tard ou attends l'ouverture (9 h 30).")
                    elif titre_suspendu(selected_ticker):
                        afficher_refus(f"{selected_ticker.upper()} est suspendu pour le moment : ses prix ne concordent pas entre les sources de données. Aucun achat ni vente tant que la suspension n'est pas levée.")
                    elif compte_en_verification(user):
                        afficher_refus("Ton compte est en vérification : une erreur de prix a faussé ton solde. Les transactions sont bloquées jusqu'à ce que ton enseignant ait corrigé ton compte.")
                    elif prix_incoherent(selected_ticker, obtenir_prix_actuel(selected_ticker))[0]:
                        afficher_refus(f"Transaction refusée : le prix de {selected_ticker.upper()} ne concorde pas avec sa dernière clôture (écart anormal entre les sources de prix). C'est le signe de données incohérentes, pas d'un vrai mouvement de marché.")
                    elif vente_avant_delai_bloquee(user, selected_ticker):
                        afficher_refus(message_delai_detention(selected_ticker))
                    elif not verifier_cooldown(user, delai_secondes=3):
                        afficher_refus("Veuillez attendre 3 secondes entre chaque transaction.")
                    else:
                        prix_instantane = obtenir_prix_actuel(selected_ticker) or prix_cad
                        cost_real = prix_instantane * qty_vente

                        p_res = conn.query("SELECT shares FROM portfolio WHERE username=:u AND LOWER(ticker)=LOWER(:t)", params={"u": user, "t": selected_ticker}, ttl=0)
                        shares_dispo = int(p_res.iloc[0]['shares']) if not p_res.empty else 0

                        if not _marche_ouvert() and ordres_ouverture_actif(user):
                            # Étape 2 (6 nov. 2026) : marché fermé, la vente
                            # devient un ordre en attente exécuté à
                            # l'ouverture, au prix d'ouverture, exactement
                            # comme les achats. Fini les ventes au prix gelé.
                            if shares_dispo < qty_vente:
                                afficher_refus("Vous ne possédez pas cette quantité d'actions.")
                            elif len(ordres_en_attente_pour(user)) >= LIMITE_ORDRES_EN_ATTENTE:
                                afficher_refus(f"Tu as déjà {LIMITE_ORDRES_EN_ATTENTE} ordres en attente. Attends leur exécution à l'ouverture, ou annules-en un.")
                            elif ordre_vente_en_attente_sur(user, selected_ticker):
                                afficher_refus(f"Tu as déjà un ordre de vente en attente sur {selected_ticker.upper()}. Annule-le si tu veux changer la quantité.")
                            else:
                                session_exec_v = creer_ordre_vente_en_attente(user, selected_ticker, qty_vente, devise_titre)
                                if session_exec_v is None:
                                    afficher_refus("Vous ne possédez plus cette quantité d'actions.")
                                else:
                                    st.session_state['flash_msg'] = ("recu", {"genre": "ordre", "titre": "ORDRE DE VENTE EN ATTENTE", "sous": f"{selected_ticker.upper()}", "lignes": [("Actions réservées", f"{qty_vente} actions")], "total": None, "pied": f"Elles seront vendues à l'ouverture du {session_exec_v}, au prix d'ouverture. Annulable dans « Mes ordres en attente »."})
                                    st.rerun()
                        elif shares_dispo >= qty_vente:
                            exempte_s = compte_exempte_frais(user)
                            frais_fixe_s, frais_conv_s = (0.0, 0.0) if exempte_s else frais_pour_ordre(devise_titre, cost_real)
                            credit_net = cost_real - frais_fixe_s - frais_conv_s
                            now_str = datetime.now(ZoneInfo("America/Toronto")).strftime("%Y-%m-%d %H:%M:%S")
                            # Verrou par utilisateur + position relue DANS la
                            # transaction : la faille des sessions simultanées
                            # (vendre 6 fois la même position) est fermée ici.
                            vente_ok = False
                            with conn.session as session:
                                _verrou_transaction(session, user)
                                sh_row = session.execute(text("SELECT shares FROM portfolio WHERE username=:u AND LOWER(ticker)=LOWER(:t)"), {"u": user, "t": selected_ticker}).fetchone()
                                sh_rel = int(sh_row[0]) if sh_row is not None else 0
                                if sh_rel >= qty_vente:
                                    session.execute(text("UPDATE users SET cash = cash + :cost WHERE username = :u"), {"cost": credit_net, "u": user})
                                    rem = sh_rel - qty_vente
                                    if rem > 0:
                                        session.execute(text("UPDATE portfolio SET shares=:s WHERE username=:u AND LOWER(ticker)=LOWER(:t)"), {"s": rem, "u": user, "t": selected_ticker})
                                    else:
                                        session.execute(text("DELETE FROM portfolio WHERE username=:u AND LOWER(ticker)=LOWER(:t)"), {"u": user, "t": selected_ticker})
                                    session.execute(text("INSERT INTO transactions (username, ticker, shares, price, total, timestamp) VALUES (:u, :t, :s, :p, :tot, :time)"),
                                                    {"u": user, "t": selected_ticker.upper(), "s": -qty_vente, "p": prix_instantane, "tot": cost_real, "time": now_str})
                                    enregistrer_frais(session, user, "transaction", frais_fixe_s, selected_ticker.upper())
                                    enregistrer_frais(session, user, "conversion", frais_conv_s, selected_ticker.upper())
                                    session.commit()
                                    vente_ok = True
                                else:
                                    session.rollback()
                            if not vente_ok:
                                afficher_refus("Vous ne possédez pas cette quantité d'actions.")
                            else:
                                _prix_affiche_v = fmt_prix(vers_natif(prix_instantane, 'USD'), 'USD') if devise_titre == "USD" else f"${prix_instantane:,.2f}"
                                _lignes_v = [(f"{qty_vente} actions à {_prix_affiche_v}", f"${cost_real:,.2f}"), ("Frais de transaction", f"${frais_fixe_s:,.2f}")]
                                if frais_conv_s > 0:
                                    _lignes_v.append(("Conversion (1,5 %, titre américain)", f"${frais_conv_s:,.2f}"))
                                _pied_v = f"Il te reste ${cash_actuel + credit_net:,.2f} en argent comptant."
                                if devise_titre == "USD":
                                    _taux_fx = obtenir_taux_usdcad()
                                    if _taux_fx:
                                        _pied_v += f" Montants en dollars canadiens, au taux {_taux_fx:.4f}."
                                st.session_state['flash_msg'] = ("recu", {"genre": "vente", "titre": "VENTE CONFIRMÉE", "sous": f"{selected_ticker.upper()} - {qty_vente} actions", "lignes": _lignes_v, "total": ("Net crédité", f"${credit_net:,.2f}"), "pied": _pied_v})
                                st.rerun()
                        else: afficher_refus("Vous ne possédez pas cette quantité d'actions.")

                # FAVORIS (bouton jaune via type="primary")
                def _retirer_favori(tk):
                    with conn.session as session:
                        session.execute(text("DELETE FROM favoris WHERE username=:u AND ticker=:t"), {"u": user, "t": tk})
                        session.commit()

                def _choisir_favori(tk):
                    st.session_state["recherche_ticker"] = tk

                fav_check = conn.query("SELECT 1 FROM favoris WHERE username=:u AND ticker=:t", params={"u": user, "t": selected_ticker.upper()}, ttl=0)
                if not fav_check.empty:
                    st.button("★ Dans mes favoris (retirer)", use_container_width=True, key=f"favrm_{selected_ticker}",
                              type="primary", on_click=_retirer_favori, args=(selected_ticker.upper(),))
                else:
                    if st.button("☆ Ajouter à mes favoris", use_container_width=True, key=f"favadd_{selected_ticker}", type="primary"):
                        with conn.session as session:
                            session.execute(text("INSERT INTO favoris (username, ticker) VALUES (:u, :t) ON CONFLICT DO NOTHING"), {"u": user, "t": selected_ticker.upper()})
                            session.commit()
                        st.rerun()

                # Liste des favoris sous le bouton jaune
                fav_q = conn.query("SELECT ticker FROM favoris WHERE username=:u ORDER BY ticker", params={"u": user}, ttl=0)
                if not fav_q.empty:
                    st.markdown("<div style='color:#9CA3AF;font-size:12px;font-weight:700;text-transform:uppercase;letter-spacing:0.08em;margin:12px 0 7px;'><span style='color:#FFD700;'>★</span> Mes favoris</div>", unsafe_allow_html=True)
                    fav_tickers = fav_q['ticker'].tolist()
                    fav_data = obtenir_donnees_favoris(tuple(fav_tickers))
                    chip_css = "<style>"
                    for i, tk in enumerate(fav_tickers):
                        px, vp, dv_fav = fav_data.get(tk.upper(), (None, None, devise_naturelle(tk)))
                        cle = f"favchip_{i}"
                        chip_css += (
                            f'div[class~="st-key-{cle}"] button {{'
                            'background: linear-gradient(180deg, #262626 0%, #1A1A1A 100%) !important;'
                            'border: 1px solid rgba(255, 215, 0, 0.45) !important;'
                            'border-top: 2px solid #FFD700 !important;'
                            'border-radius: 10px !important;'
                            'padding: 7px 8px !important;'
                            'box-shadow: 0 10px 20px -10px rgba(0, 0, 0, 0.85) !important;'
                            '}'
                            f'div[class~="st-key-{cle}"] button p {{'
                            'color: #FFFFFF !important; font-weight: 700 !important; font-size: 13.5px !important;'
                            '}'
                            f'div[class~="st-key-{cle}"] button:hover {{'
                            'border-color: #FFD700 !important;'
                            '}'
                        )
                    chip_css += "</style>"
                    st.markdown(chip_css, unsafe_allow_html=True)
                    fav_cols = st.columns(2)
                    for i, tk in enumerate(fav_tickers):
                        px, vp, dv_fav = fav_data.get(tk.upper(), (None, None, devise_naturelle(tk)))
                        if px is None:
                            chip_label = f"**{tk}**"
                        else:
                            fmt_px = fmt_prix(px, dv_fav)
                            signe = "+" if (vp or 0) >= 0 else ""
                            fleche = "▲" if (vp or 0) >= 0 else "▼"
                            chip_label = f"**{tk}** · {fmt_px} · {fleche} {signe}{vp:.2f} %"
                        with fav_cols[i % 2]:
                            st.button(chip_label, key=f"favchip_{i}", use_container_width=True, on_click=_choisir_favori, args=(tk,))
        else:
            st.error(f"Impossible de trouver des données financières pour '{selected_ticker}'. Vérifiez le nom ou le symbole boursier.")

    # --- ONGLET 2 : POSITIONS ET IMPRESSION PRO ---
    elif tab_choisi == "Mes Positions":
        afficher_missions(user)
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
                div[data-testid="stRadio"], .stButton, button,
                iframe, hr, .stSelectbox, .stNumberInput, .brand-banner,
                div[data-testid="stMetric"], .kpi-card, .podium-card, .mon-rang {
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

        @st.fragment
        def afficher_positions_live():
            pos_df_live = conn.query("SELECT ticker, shares, avg_price FROM portfolio WHERE username=:u", params={"u": user}, ttl=0)
            val_actions_live = 0.0

            if not pos_df_live.empty:
                unique_tks = pos_df_live['ticker'].unique().tolist()
                prix_dict = obtenir_prix_groupes(unique_tks)
                for _, r in pos_df_live.iterrows():
                    tk_sym = str(r['ticker']).strip().upper()
                    _info_px = prix_dict.get(tk_sym)
                    px_a = _info_px["cad"] if _info_px else None
                    px_f = px_a if px_a is not None else float(r['avg_price'] or 0.0)
                    val_actions_live += px_f * r['shares']

            val_totale_live = cash_actuel + val_actions_live
            prof_total_live = val_totale_live - 10000.00
            rend_pct_live = (prof_total_live / 10000.00) * 100

            date_impression = datetime.now(ZoneInfo("America/Toronto")).strftime("%d/%m/%Y à %H:%M")
            pnl_color_print = "#10B981" if prof_total_live >= 0 else "#EF4444"

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
                st.markdown("### Mes Positions Actuelles")
            with col_p2:
                components.html("""
                    <button onclick="window.parent.print()" style="
                        background: linear-gradient(180deg, #E50914 0%, #B00610 100%);
                        color: #FFFFFF;
                        border: 1px solid rgba(255, 130, 130, 0.4);
                        padding: 10px 18px;
                        border-radius: 10px;
                        font-weight: 700;
                        cursor: pointer;
                        width: 100%;
                        font-family: 'Work Sans', sans-serif;
                        box-shadow: 0 10px 22px -10px rgba(229, 9, 20, 0.85);
                        transition: all 0.12s ease;
                    " onmousedown="this.style.transform='translateY(2px)'" onmouseup="this.style.transform='translateY(0px)'">
                        Imprimer / PDF
                    </button>
                """, height=45)

            p_all = conn.query("SELECT ticker, shares, avg_price FROM portfolio WHERE username=:u", params={"u": user}, ttl=0)
            if not p_all.empty:
                html_rows = ""

                tks_all = p_all['ticker'].unique().tolist()
                prix_dict_pos = obtenir_prix_groupes(tks_all)

                pie_labels, pie_vals = [], []

                for _, r in p_all.iterrows():
                    tk, sh, pm = str(r['ticker']), int(r['shares']), float(r['avg_price'] or 0.0)
                    _info_pos = prix_dict_pos.get(tk.upper())
                    pa_live = _info_pos["cad"] if _info_pos else None
                    pa = pa_live if pa_live is not None else pm
                    val = sh * pa
                    pnl = (pa - pm) * sh
                    pnl_pct = ((pa - pm) / pm * 100) if pm > 0 else 0
                    pie_labels.append(tk)
                    pie_vals.append(val)

                    # Affichage des prix unitaires en devise naturelle (le prix
                    # moyen CAD est converti au taux du jour, affichage seulement).
                    # Valeur, gain et rendement restent en CAD exacts.
                    dv_pos = _info_pos["devise"] if _info_pos else devise_naturelle(tk)
                    pa_aff = _info_pos["natif"] if (_info_pos and _info_pos["natif"] is not None) else vers_natif(pa, dv_pos)
                    pm_aff = vers_natif(pm, dv_pos)

                    pnl_color = "#10B981" if pnl >= 0 else "#EF4444"
                    fmt_pa = fmt_prix(pa_aff, dv_pos)
                    fmt_pm = fmt_prix(pm_aff, dv_pos)

                    html_rows += (f"<div class='pos-carte'><div style='display:flex;justify-content:space-between;align-items:baseline;'>"
                                  f"<span class='pos-sym'>{tk}</span><span class='pos-val'>${val:,.2f}</span></div>"
                                  f"<div class='pos-detail'><b>{sh}</b> actions · prix moyen <b>{fmt_pm}</b> · actuel <b>{fmt_pa}</b></div>"
                                  f"<div class='pos-gain' style='color:{pnl_color};'>${pnl:+,.2f} ({pnl_pct:+.2f} %)</div></div>")

                st.markdown(f"<div style='display:flex;flex-wrap:wrap;gap:12px;'>{html_rows}</div>", unsafe_allow_html=True)
                st.caption("Prix moyen et prix actuel : devise naturelle du titre (prix moyen converti au taux du jour). Valeur, gain/perte et rendement : dollars canadiens.")

                # --- CAMEMBERT : RÉPARTITION DU PORTEFEUILLE ---
                cash_q = conn.query("SELECT cash FROM users WHERE username=:u", params={"u": user}, ttl=0)
                cash_val = float(cash_q.iloc[0]['cash']) if not cash_q.empty else 0.0

                rep_labels = list(pie_labels) + (["Liquidités"] if cash_val > 0.005 else [])
                rep_values = list(pie_vals) + ([cash_val] if cash_val > 0.005 else [])
                total_pf = sum(rep_values)

                if total_pf > 0:
                    paires = sorted(zip(rep_labels, rep_values), key=lambda x: x[1], reverse=True)
                    rep_labels, rep_values = [p[0] for p in paires], [p[1] for p in paires]

                    palette = ["#E50914", "#10B981", "#3B82F6", "#F59E0B", "#8B5CF6", "#EC4899", "#06B6D4", "#84CC16", "#F97316", "#6366F1", "#14B8A6", "#EAB308"]
                    couleurs = [("#6B7280" if lab == "Liquidités" else palette[i % len(palette)]) for i, lab in enumerate(rep_labels)]

                    fig_pie = go.Figure(data=[go.Pie(
                        labels=rep_labels,
                        values=rep_values,
                        hole=0.45,
                        marker=dict(colors=couleurs, line=dict(color="#141414", width=3)),
                        textinfo="label+percent",
                        textfont=dict(color="#FFFFFF", family="Work Sans", size=14),
                        hovertemplate="<b>%{label}</b><br>%{value:,.2f} $ (%{percent})<extra></extra>",
                        sort=False,
                    )])
                    fig_pie.update_layout(
                        title=dict(text="Répartition du portefeuille", font=dict(color="#FFFFFF", family="Bebas Neue", size=30), x=0.5, xanchor="center"),
                        paper_bgcolor="rgba(0,0,0,0)",
                        plot_bgcolor="rgba(0,0,0,0)",
                        font=dict(color="#FFFFFF", family="Work Sans"),
                        showlegend=False,
                        height=480,
                        margin=dict(l=20, r=20, t=70, b=20),
                        annotations=[dict(
                            text=f"${total_pf:,.2f}",
                            x=0.5, y=0.5,
                            font=dict(size=24, color="#FFFFFF", family="Work Sans"),
                            showarrow=False
                        )],
                    )
                    cp1, cp2, cp3 = st.columns([1, 2, 1])
                    with cp2:
                        st.plotly_chart(fig_pie, use_container_width=True)

                st.markdown("<hr>", unsafe_allow_html=True)
                st.markdown("### Vendre rapidement mes positions")

                exempte_vente_rapide = compte_exempte_frais(user)
                cartes_vente = []
                for _, r in p_all.iterrows():
                    tk2, sh2 = str(r['ticker']), int(r['shares'] or 0)
                    if sh2 <= 0:
                        continue  # ligne résiduelle sans action : rien à vendre, on l'ignore
                    pm2 = float(r['avg_price'] or 0.0)
                    _info_v = prix_dict_pos.get(tk2.upper())
                    pa2_live = _info_v["cad"] if _info_v else None
                    pa2 = pa2_live if pa2_live is not None else pm2
                    cartes_vente.append((tk2, sh2, pm2, pa2))

                grille_vente = st.columns(3)
                for i, (tk, sh, pm, pa) in enumerate(cartes_vente):
                    with grille_vente[i % 3]:
                        with st.container(border=True):
                            sh_s = max(int(sh), 1)
                            cle_slider = f"slqv_{tk}_{sh_s}"
                            qty_init = max(1, min(int(st.session_state.get(cle_slider, sh_s)), sh_s))
                            pnl_badge = (pa - pm) * qty_init
                            coul_b = "#10B981" if pnl_badge >= 0 else "#EF4444"
                            fond_b = "rgba(16,185,129,0.12)" if pnl_badge >= 0 else "rgba(239,68,68,0.12)"
                            st.markdown(
                                f"<div style='display:flex;justify-content:space-between;align-items:flex-start;gap:8px;'>"
                                f"<div><div style='font-family:\"Bebas Neue\",\"Work Sans\",sans-serif;font-size:24px;letter-spacing:0.04em;color:#FFFFFF;'>{tk}</div>"
                                f"<div style='color:#9CA3AF;font-size:13px;margin-bottom:8px;'>J'en possède : {sh}</div></div>"
                                f"<div style='background:{fond_b};border:1px solid {coul_b};border-radius:8px;padding:4px 10px;color:{coul_b};font-weight:800;font-size:14px;white-space:nowrap;'>${pnl_badge:+,.2f}</div>"
                                f"</div>",
                                unsafe_allow_html=True)
                            if sh_s <= 1:
                                # Streamlit refuse un curseur avec min == max : avec une seule action, pas de curseur
                                qty_c = 1
                                st.markdown("<div style='color:#9CA3AF;font-size:14px;margin:4px 0 8px 0;'>J'en vends : <b style='color:#FFFFFF;'>1</b></div>", unsafe_allow_html=True)
                            else:
                                qty_c = st.slider("J'en vends :", min_value=1, max_value=sh_s, value=qty_init, key=cle_slider)
                            tot_c = qty_c * pa
                            if exempte_vente_rapide:
                                tot_affiche, frais_carte = tot_c, 0.0
                            else:
                                _info_c = prix_dict_pos.get(tk.upper())
                                _dv_carte = (_info_c["devise"] if _info_c and _info_c.get("devise") else devise_naturelle(tk))
                                _ff_carte, _fc_carte = frais_pour_ordre(_dv_carte, tot_c)
                                frais_carte = _ff_carte + _fc_carte
                                tot_affiche = tot_c - frais_carte
                            if not _marche_ouvert():
                                libelle_recois = f"Ordre de vente à l'ouverture : environ <b>${tot_affiche:,.2f}</b> au prix de fermeture"
                            else:
                                libelle_recois = f"Je reçois : <b>${tot_affiche:,.2f}</b>" + (f" <span style='color:#9CA3AF;font-size:12px;'>(après {frais_carte:,.2f} $ de frais)</span>" if frais_carte > 0 else "")
                            st.markdown(
                                f"<div style='color:#FFFFFF;font-size:15px;margin:4px 0 10px;'>{libelle_recois}</div>",
                                unsafe_allow_html=True)
                            if st.button(f"Vendre {qty_c} {tk}", use_container_width=True, key=f"vndcarte_{tk}"):
                                if not _marche_ouvert() and _prix_gele_ou_none(tk) is None:
                                    afficher_refus(f"Marché fermé : le prix de clôture de {tk} n'a pas pu être figé pour cette séance. Vente refusée plutôt que faite à un prix qui bouge. Réessaie plus tard ou attends l'ouverture (9 h 30).")
                                elif titre_suspendu(tk):
                                    afficher_refus(f"{tk} est suspendu pour le moment : ses prix ne concordent pas entre les sources de données. Aucun achat ni vente tant que la suspension n'est pas levée.")
                                elif compte_en_verification(user):
                                    afficher_refus("Ton compte est en vérification : une erreur de prix a faussé ton solde. Les transactions sont bloquées jusqu'à ce que ton enseignant ait corrigé ton compte.")
                                elif prix_incoherent(tk, obtenir_prix_actuel(tk))[0]:
                                    afficher_refus(f"Transaction refusée : le prix de {tk} ne concorde pas avec sa dernière clôture (écart anormal entre les sources de prix). C'est le signe de données incohérentes, pas d'un vrai mouvement de marché.")
                                elif vente_avant_delai_bloquee(user, tk):
                                    afficher_refus(message_delai_detention(tk))
                                elif not verifier_cooldown(user, delai_secondes=3):
                                    afficher_refus("Veuillez attendre 3 secondes entre chaque transaction.")
                                else:
                                    check_p = conn.query("SELECT shares FROM portfolio WHERE username=:u AND ticker=:t", params={"u": user, "t": tk}, ttl=0)
                                    sh_real = int(check_p.iloc[0]['shares']) if not check_p.empty else 0
                                    if not _marche_ouvert() and ordres_ouverture_actif(user):
                                        # Étape 2 : marché fermé, la vente rapide
                                        # devient elle aussi un ordre en attente
                                        # à l'ouverture, jamais une vente au
                                        # prix gelé.
                                        if sh_real < qty_c:
                                            afficher_refus("Vous ne possédez plus ces actions.")
                                        elif len(ordres_en_attente_pour(user)) >= LIMITE_ORDRES_EN_ATTENTE:
                                            afficher_refus(f"Tu as déjà {LIMITE_ORDRES_EN_ATTENTE} ordres en attente. Attends leur exécution à l'ouverture, ou annules-en un.")
                                        elif ordre_vente_en_attente_sur(user, tk):
                                            afficher_refus(f"Tu as déjà un ordre de vente en attente sur {tk}. Annule-le si tu veux changer la quantité.")
                                        else:
                                            session_exec_v = creer_ordre_vente_en_attente(user, tk, qty_c, devise_naturelle(tk))
                                            if session_exec_v is None:
                                                afficher_refus("Vous ne possédez plus ces actions.")
                                            else:
                                                st.session_state['flash_msg'] = ("recu", {"genre": "ordre", "titre": "ORDRE DE VENTE EN ATTENTE", "sous": f"{str(tk).upper()}", "lignes": [("Actions réservées", f"{qty_c} actions")], "total": None, "pied": f"Elles seront vendues à l'ouverture du {session_exec_v}, au prix d'ouverture. Annulable dans « Mes ordres en attente »."})
                                                st.rerun()
                                    elif sh_real >= qty_c:
                                        prix_v_instantane = obtenir_prix_actuel(tk) or pa
                                        total_v_instantane = qty_c * prix_v_instantane
                                        if exempte_vente_rapide:
                                            frais_fixe_c, frais_conv_c = 0.0, 0.0
                                        else:
                                            frais_fixe_c, frais_conv_c = frais_pour_ordre(devise_naturelle(tk), total_v_instantane)
                                        credit_net_c = total_v_instantane - frais_fixe_c - frais_conv_c
                                        now_str = datetime.now(ZoneInfo("America/Toronto")).strftime("%Y-%m-%d %H:%M:%S")
                                        # Verrou par utilisateur + position relue DANS
                                        # la transaction (même faille multi-sessions
                                        # que la vente principale).
                                        vente_c_ok = False
                                        with conn.session as session:
                                            _verrou_transaction(session, user)
                                            sh_row_c = session.execute(text("SELECT shares FROM portfolio WHERE username=:u AND ticker=:t"), {"u": user, "t": tk}).fetchone()
                                            sh_rel_c = int(sh_row_c[0]) if sh_row_c is not None else 0
                                            if sh_rel_c >= qty_c:
                                                session.execute(text("UPDATE users SET cash = cash + :cost WHERE username = :u"), {"cost": credit_net_c, "u": user})
                                                rem = sh_rel_c - qty_c
                                                if rem > 0:
                                                    session.execute(text("UPDATE portfolio SET shares=:s WHERE username=:u AND ticker=:t"), {"s": rem, "u": user, "t": tk})
                                                else:
                                                    session.execute(text("DELETE FROM portfolio WHERE username=:u AND ticker=:t"), {"u": user, "t": tk})
                                                session.execute(text("INSERT INTO transactions (username, ticker, shares, price, total, timestamp) VALUES (:u, :t, :s, :p, :tot, :time)"),
                                                                {"u": user, "t": tk, "s": -qty_c, "p": prix_v_instantane, "tot": total_v_instantane, "time": now_str})
                                                enregistrer_frais(session, user, "transaction", frais_fixe_c, tk)
                                                enregistrer_frais(session, user, "conversion", frais_conv_c, tk)
                                                session.commit()
                                                vente_c_ok = True
                                            else:
                                                session.rollback()
                                        if not vente_c_ok:
                                            afficher_refus("Vous ne possédez plus ces actions.")
                                        else:
                                            _devise_c = devise_naturelle(tk)
                                            _prix_affiche_c = fmt_prix(vers_natif(prix_v_instantane, 'USD'), 'USD') if _devise_c == "USD" else f"${prix_v_instantane:,.2f}"
                                            _lignes_c = [(f"{qty_c} actions à {_prix_affiche_c}", f"${total_v_instantane:,.2f}"), ("Frais de transaction", f"${frais_fixe_c:,.2f}")]
                                            if frais_conv_c > 0:
                                                _lignes_c.append(("Conversion (1,5 %, titre américain)", f"${frais_conv_c:,.2f}"))
                                            st.session_state['flash_msg'] = ("recu", {"genre": "vente", "titre": "VENTE CONFIRMÉE", "sous": f"{str(tk).upper()} - {qty_c} actions", "lignes": _lignes_c, "total": ("Net crédité", f"${credit_net_c:,.2f}"), "pied": f"Il te reste ${cash_actuel + credit_net_c:,.2f} en argent comptant."})
                                            st.rerun()
                                    else:
                                        afficher_refus("Vous ne possédez plus ces actions.")
            else: st.info("Vous n'avez aucune position ouverte actuellement.")

        afficher_positions_live()

    # --- ONGLET 3 : HISTORIQUE ---
    elif tab_choisi == "Mon Historique":
        # Relevé refait (vague 2, 6 nov. 2026) : sur chaque vente, le
        # coût d'achat des actions vendues (FIFO) et le gain réalisé,
        # pour que l'élève voie les deux prix, celui payé au départ et
        # celui obtenu à la vente. Le calcul se fait sur l'historique
        # complet en ordre chronologique, l'affichage reste aux 120
        # plus récentes.
        tx_all = conn.query("SELECT timestamp, ticker, shares, price, total FROM transactions WHERE username=:u ORDER BY id ASC", params={"u": user}, ttl=0)
        if not tx_all.empty:
            _nb_tx = len(tx_all)
            _enrichies = enrichir_historique_fifo(tx_all.to_dict('records'))
            _lignes_hist = ""
            for _rtx in list(reversed(_enrichies))[:120]:
                _est_achat = float(_rtx['shares']) > 0
                _qte_h = abs(int(float(_rtx['shares'])))
                _pastille = ("<span style='background:#E50914;color:#FFFFFF;font-weight:800;font-size:0.72rem;"
                             "letter-spacing:0.06em;padding:3px 9px;border-radius:999px;'>ACHAT</span>") if _est_achat else (
                             "<span style='border:1.5px solid #E5E7EB;color:#FFFFFF;font-weight:800;font-size:0.72rem;"
                             "letter-spacing:0.06em;padding:3px 9px;border-radius:999px;'>VENTE</span>")
                if _est_achat:
                    _milieu = f"{_qte_h} actions à ${float(_rtx['price']):,.2f} l'action"
                    _gain_html = ""
                else:
                    _milieu = f"{_qte_h} actions vendues à ${float(_rtx['price']):,.2f} l'action"
                    if _rtx.get('cout_achat_moyen') is not None:
                        _milieu += f" · achetées à ${_rtx['cout_achat_moyen']:,.2f} l'action"
                        _g = float(_rtx['gain_realise'])
                        _coul_g = "#34D399" if _g >= 0 else "#F87171"
                        _gain_html = f"<div style='color:{_coul_g};font-weight:700;font-size:0.85rem;font-variant-numeric:tabular-nums;'>{'+' if _g >= 0 else '−'}${abs(_g):,.2f}</div>"
                    else:
                        _gain_html = ""
                _lignes_hist += (
                    "<div style='display:flex;align-items:center;gap:14px;background:linear-gradient(180deg,#262626 0%,#1A1A1A 100%);"
                    "border:1px solid rgba(255,255,255,0.10);border-radius:12px;padding:10px 16px;margin-bottom:8px;'>"
                    f"<div style='color:#9CA3AF;font-size:0.82rem;min-width:118px;'>{str(_rtx['timestamp'])[:16]}</div>"
                    f"<div style=\"font-family:'Bebas Neue','Work Sans',sans-serif;font-size:1.45rem;color:#FFFFFF;letter-spacing:0.04em;min-width:86px;\">{html.escape(str(_rtx['ticker']))}</div>"
                    f"{_pastille}"
                    f"<div style='flex:1;color:#D1D5DB;font-size:0.94rem;'>{_milieu}</div>"
                    f"<div style='text-align:right;'><div style='color:#FFFFFF;font-weight:800;font-size:1rem;font-variant-numeric:tabular-nums;'>${abs(float(_rtx['total'])):,.2f}</div>{_gain_html}</div></div>")
            st.markdown(_lignes_hist, unsafe_allow_html=True)
            if _nb_tx > 120:
                st.caption(f"Tes 120 transactions les plus récentes, sur {_nb_tx} au total.")
        else: st.info("Aucune transaction.")

    # --- ONGLET 4 : CLASSEMENT (AVEC RECHERCHE & SURGLIGNAGE JAUNE) ---
    elif tab_choisi == "Classement":
        col_r1, col_r2, col_r3 = st.columns([2, 2, 1])
        with col_r1:
            grp_filter = st.selectbox("Filtrer par groupe :", ["Tous les groupes"] + LISTE_GROUPES)
        with col_r2:
            search_user_rank = st.text_input("Rechercher un élève :", value="", placeholder="Tapez un nom d'élève...", autocomplete="off")
        with col_r3:
            st.markdown("<br>", unsafe_allow_html=True)
            if st.button("Actualiser", use_container_width=True):
                obtenir_donnees_classement.clear()
                st.rerun()

        df_classement = obtenir_donnees_classement(grp_filter)
        if not df_classement.empty:
            top3 = df_classement.head(3)
            classes_podium = ["podium-or", "podium-argent", "podium-bronze"]
            cols_podium = st.columns(len(top3))
            for i, (_, r_pod) in enumerate(top3.iterrows()):
                _gj = float(r_pod['GainJour'])
                _gjp = float(r_pod['GainJourPct'])
                _classe_jour = 'hausse' if _gj >= 0 else 'baisse'
                _signe_jour = '+' if _gj >= 0 else '-'
                _jour_html = (f"<div class='podium-jour'>Aujourd'hui : "
                              f"<span class='{_classe_jour}'>{_signe_jour}${abs(_gj):,.2f} "
                              f"({_gjp:+.2f}%)</span></div>")
                _nom_pod = str(r_pod['Élève'])
                _photo_pod = obtenir_photo(_nom_pod)
                if _photo_pod:
                    _avatar = (f"<div class='podium-photo-wrap'>"
                               f"<img class='podium-photo' src='data:image/jpeg;base64,{_photo_pod}' alt=''>"
                               f"<span class='podium-badge'>{int(r_pod['Rang'])}</span></div>")
                else:
                    _avatar = (f"<div class='podium-photo-wrap'>"
                               f"<div class='podium-initiales'>{initiales_de(_nom_pod)}</div>"
                               f"<span class='podium-badge'>{int(r_pod['Rang'])}</span></div>")
                _susp_html = "<div><span class='podium-suspendu'>SUSPENDU</span></div>" if str(r_pod.get('Statut', '')) == 'SUSPENDU' else ""
                cols_podium[i].markdown(f"<div class='podium-card {classes_podium[i]} podium-{i + 1}'>{_avatar}<div class='podium-nom'>{r_pod['Élève']}</div>{_susp_html}<div class='podium-val'>{r_pod['Portefeuille']}</div><div class='podium-perf'>{r_pod['Performance']}</div>{_jour_html}</div>", unsafe_allow_html=True)

            # MENEUR DU JOUR (étape 2, affichage seulement) : la plus
            # forte hausse du jour, sur les positions comparées à la
            # clôture de la veille, avec les données du classement.
            # Calcul direct sur le tableau (aucune requête ajoutée) :
            # les comptes enseignants et les suspendus sont exclus.
            _cand = df_classement[
                (df_classement['GainJourPct'] > 0)
                & (df_classement['Statut'] != 'SUSPENDU')
                & (~df_classement['Groupe'].astype(str).str.contains('enseignant', case=False, na=False))
                & (df_classement['Élève'] != 'MathieuSavary')]
            if not _cand.empty:
                _meneur = _cand.loc[_cand['GainJourPct'].idxmax()]
                st.markdown(
                    f"<div class='meneur-card'><div class='meneur-titre'>Meneur du jour</div>"
                    f"<div class='meneur-nom' style='font-size:2.15rem;'>{_meneur['Élève']}</div>"
                    f"<div class='meneur-val'>+{float(_meneur['GainJourPct']):.1f} % aujourd'hui</div>"
                    f"<div class='meneur-detail'>Calculé sur ses positions, comparées à la clôture d'hier. "
                    f"Un titre d'affichage seulement : il ne donne rien, sauf le droit de s'en vanter jusqu'à demain.</div></div>",
                    unsafe_allow_html=True)

            moi = df_classement[df_classement['Élève'] == user]
            if not moi.empty:
                r_moi = moi.iloc[0]
                st.markdown(f"<div class='mon-rang'><span class='mon-rang-label'>Ton rang</span><span class='mon-rang-val'>#{int(r_moi['Rang'])}</span><span class='mon-rang-detail'>{r_moi['Portefeuille']} · {r_moi['Performance']}</span></div>", unsafe_allow_html=True)

            def highlight_row(row):
                styles = [''] * len(row)
                if str(row['Élève']) == user:
                    styles = ['background-color: rgba(229, 9, 20, 0.30); color: #FFFFFF; font-weight: 700;'] * len(row)
                if search_user_rank and search_user_rank.strip() and search_user_rank.strip().lower() in str(row['Élève']).lower():
                    styles = ['background-color: rgba(229, 9, 20, 0.95); color: #FFFFFF; font-weight: 700;'] * len(row)
                if str(row.get('Statut', '')) == 'SUSPENDU':
                    styles[list(row.index).index('Statut')] = 'color: #FF5147; font-weight: 800; letter-spacing: 0.08em;'
                return styles

            styled_df = df_classement[['Rang', 'Élève', 'Groupe', 'Portefeuille', 'Performance', 'Statut']].style.apply(highlight_row, axis=1)
            st.dataframe(styled_df, use_container_width=True, hide_index=True)
        else:
            st.info("Aucun élève trouvé pour ce classement.")

    # --- ONGLET 5 : SUPERVISION PROFESSEUR ---
    elif tab_choisi == "Supervision Prof":
        if not est_compte_enseignant(user):
            st.stop()
        try:
            _pin_attendu = st.secrets.get("PIN_PROF")
        except Exception:
            _pin_attendu = None
        if not _pin_attendu:
            st.warning("Supervision non configurée : le PIN enseignant n'est pas défini dans les secrets de l'application.")
            pin = ""
        else:
            pin = st.text_input("PIN Enseignant :", type="password", autocomplete="off")
        if _pin_attendu and pin == _pin_attendu:
            st.markdown("<div style=\'font-family:'Bebas Neue','Work Sans',sans-serif;font-size:2.2rem;letter-spacing:0.06em;color:#FFFFFF;line-height:1;margin:4px 0 2px;\'>SUPERVISION</div><div style='color:#9CA3AF;font-size:0.92rem;margin-bottom:12px;'>La console des enseignants, organisée par tâche : comptes, règles, argent et affichage.</div>", unsafe_allow_html=True)
            # --- KRACH BOURSIER : panneau en haut de la Supervision (refonte du 3 nov. :
            # enseigne néon jaune pulsante, visible dès l'ouverture de l'onglet) ---
            st.markdown("""
            <style>
              @keyframes krachNeon {
                0%, 100% { box-shadow: 0 0 12px rgba(255, 230, 0, 0.35), inset 0 0 10px rgba(255, 230, 0, 0.05); }
                50% { box-shadow: 0 0 34px rgba(255, 230, 0, 0.65), inset 0 0 22px rgba(255, 230, 0, 0.13); }
              }
              @keyframes krachBtn {
                0%, 100% { box-shadow: 0 0 8px rgba(255, 230, 0, 0.5), inset 0 0 6px rgba(255, 230, 0, 0.25); }
                50% { box-shadow: 0 0 22px rgba(255, 230, 0, 0.95), inset 0 0 12px rgba(255, 230, 0, 0.45); }
              }
              .krach-panel {
                background: #070707;
                border: 2px solid #FFE600;
                border-radius: 12px;
                padding: 20px 22px 14px;
                text-align: center;
                margin: 4px 0 14px;
                animation: krachNeon 2.2s ease-in-out infinite;
              }
              .krach-titre {
                font-family: 'Bebas Neue', 'Arial Narrow', sans-serif;
                font-size: 52px;
                letter-spacing: 0.16em;
                line-height: 1;
                color: #FFE600;
                text-shadow: 0 0 6px rgba(255, 230, 0, 0.9), 0 0 20px rgba(255, 230, 0, 0.6), 0 0 46px rgba(255, 230, 0, 0.35);
              }
              .krach-sous {
                font-family: 'Work Sans', sans-serif;
                color: #EDEDED;
                font-size: 15px;
                margin-top: 9px;
                line-height: 1.5;
              }
              div[class~="st-key-btn_krach_prep"] button, div[class~="st-key-btn_krach_go"] button {
                background: #0A0A0A !important;
                border: 2px solid #FFE600 !important;
                border-radius: 10px !important;
                animation: krachBtn 1.1s ease-in-out infinite !important;
              }
              div[class~="st-key-btn_krach_prep"] button p, div[class~="st-key-btn_krach_go"] button p {
                color: #FFE600 !important;
                font-weight: 800 !important;
                letter-spacing: 0.08em !important;
                text-shadow: 0 0 8px rgba(255, 230, 0, 0.8) !important;
              }
              div[class~="st-key-btn_krach_go"] button {
                border-width: 3px !important;
              }
            </style>
            <div class="krach-panel">
              <div class="krach-titre">KRACH BOURSIER</div>
              <div class="krach-sous">Zone du lundi 16 novembre, au matin. Au déclenchement : sauvegarde complète de tous les comptes, retour de chaque élève à 10 000 $ (sauf les départs spéciaux inscrits, à 9 000 $), et la page du journal remplace l'interface jusqu'à minuit. Ton compte et le groupe Enseignants ne sont pas touchés.</div>
            </div>
            """, unsafe_allow_html=True)
            if krach_est_actif():
                st.warning("Le krach est EN COURS : les élèves voient la page du journal jusqu'à minuit.")
                if st.button("Éteindre la page du krach maintenant", key="btn_krach_off"):
                    terminer_krach()
                    st.success("Page du krach éteinte. L'interface normale est de retour pour les élèves.")
                    st.rerun()
            else:
                ap_k = apercu_krach()
                st.caption(f"Portée du reset : {ap_k['comptes']} comptes · {ap_k['positions']} positions · {ap_k['transactions']} transactions · {ap_k['ordres']} ordres en attente. La sauvegarde complète part AVANT le premier effacement, dans la même opération.")
                if not st.session_state.get("krach_confirme"):
                    if st.button("PRÉPARER LE KRACH", key="btn_krach_prep", use_container_width=True):
                        st.session_state["krach_confirme"] = True
                        st.rerun()
                else:
                    st.warning("Dernière chance de reculer : l'étape suivante est le déclenchement réel.")
                    col_k1, col_k2 = st.columns(2)
                    if col_k1.button("DÉCLENCHER LE KRACH", key="btn_krach_go", use_container_width=True):
                        lot_k, lignes_k, expire_k = executer_krach()
                        st.session_state["krach_confirme"] = False
                        st.success(f"Krach déclenché. Sauvegarde « {lot_k} » : {lignes_k} lignes archivées. Page du journal active jusqu'au {expire_k}.")
                        st.rerun()
                    if col_k2.button("Annuler", key="btn_krach_non", use_container_width=True):
                        st.session_state["krach_confirme"] = False
                        st.rerun()

            # --- SUSPENSION D'UN JOUEUR ---
            # --- CONSOLE À SECTIONS (vague 2, 6 nov. 2026) : quatre
            # sections choisies par boutons, une seule visible à la
            # fois ; le panneau du krach reste toujours au-dessus. ---
            _SECTIONS_SUP = ["Comptes", "Groupes et accès", "Règles et sanctions", "Argent et affichage"]
            if st.session_state.get("sup_section") not in _SECTIONS_SUP:
                st.session_state["sup_section"] = "Comptes"
            _sup_actuelle = st.session_state["sup_section"]
            _cols_sup = st.columns(len(_SECTIONS_SUP))
            for _i_sup, _nom_sup in enumerate(_SECTIONS_SUP):
                with _cols_sup[_i_sup]:
                    if st.button(_nom_sup, key=f"supsec_{_i_sup}", use_container_width=True, type="primary" if _nom_sup == _sup_actuelle else "secondary"):
                        st.session_state["sup_section"] = _nom_sup
                        st.rerun()
            if _sup_actuelle == "Comptes":
                sup_fiche(user)
            elif _sup_actuelle == "Groupes et accès":
                sup_groupes(user)
                sup_mdp(user)
            elif _sup_actuelle == "Règles et sanctions":
                sup_suspension(user)
                sup_correction(user)
            else:
                sup_frais(user)
                sup_photos(user)
                sup_apercu(user)