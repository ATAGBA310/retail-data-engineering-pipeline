from pathlib import Path
import sqlite3
import xml.etree.ElementTree as ET

import numpy as np
import pandas as pd


# ============================================================
# CHEMINS DU PROJET
# ============================================================

PROJECT_DIR = Path(__file__).resolve().parent

RAW_DIR = PROJECT_DIR / "data" / "raw"
PROCESSED_DIR = PROJECT_DIR / "data" / "processed"
REPORTS_DIR = PROJECT_DIR / "reports"

DATABASE_DIR = PROJECT_DIR / "database"
DATABASE_PATH = DATABASE_DIR / "lerouge_moulin.db"

# ============================================================
# LECTURE ET CHARGEMENT
# ============================================================

def lire_xml(chemin_fichier, balise_element):
    """
    Lit les enregistrements d'un fichier XML
    et les transforme en DataFrame pandas.
    """

    arbre = ET.parse(chemin_fichier)
    racine = arbre.getroot()

    donnees = []

    for element in racine.findall(balise_element):
        ligne = {
            champ.tag: champ.text
            for champ in element
        }

        donnees.append(ligne)

    return pd.DataFrame(donnees)


def charger_donnees(raw_dir):
    """
    Charge les quatre fichiers sources du projet.

    Retourne
    --------
    clients : DataFrame
    products_csv : DataFrame
    products_xml : DataFrame
    transactions : DataFrame
    """

    fichiers = {
        "client_xml": raw_dir / "client.xml",
        "product_csv": raw_dir / "product.csv",
        "product_xml": raw_dir / "product.xml",
        "transactions_csv": raw_dir / "transactions_2026.csv"
    }

    fichiers_absents = [
        str(chemin)
        for chemin in fichiers.values()
        if not chemin.exists()
    ]

    if fichiers_absents:
        raise FileNotFoundError(
            "Fichiers sources absents :\n"
            + "\n".join(fichiers_absents)
        )

    clients = lire_xml(
        fichiers["client_xml"],
        "Client"
    )

    products_csv = pd.read_csv(
        fichiers["product_csv"]
    )

    products_xml = lire_xml(
        fichiers["product_xml"],
        "Product"
    )

    transactions = pd.read_csv(
        fichiers["transactions_csv"]
    )

    print("Chargement des données terminé.")

    print(f"CLIENT XML : {len(clients)} lignes")
    print(f"PRODUIT CSV : {len(products_csv)} lignes")
    print(f"PRODUIT XML : {len(products_xml)} lignes")
    print(f"TRANSACTIONS : {len(transactions)} lignes")

    return (
        clients,
        products_csv,
        products_xml,
        transactions
    )


# ============================================================
# CONVERSION ET TRANSFORMATION
# ============================================================

def convertir_types(
    clients,
    products_csv,
    products_xml,
    transactions
):
    """
    Convertit et harmonise les types des données sources.
    Concatène également les deux sources PRODUIT.
    """

    clients = clients.copy()
    products_csv = products_csv.copy()
    products_xml = products_xml.copy()
    transactions = transactions.copy()

    # CLIENT
    clients["client_id"] = clients["client_id"].astype("string")
    clients["name"] = clients["name"].astype("string")
    clients["sexe"] = clients["sexe"].astype("string")
    clients["status"] = clients["status"].astype("string")

    clients["age"] = pd.to_numeric(
        clients["age"],
        errors="coerce"
    ).astype("Int64")

    clients["opening_date"] = pd.to_datetime(
        clients["opening_date"],
        errors="coerce"
    )

    # PRODUIT CSV et XML
        # PRODUIT CSV et XML
    for dataframe in [products_csv, products_xml]:

        dataframe["product_id"] = (
            dataframe["product_id"].astype("string")
        )

        dataframe["product_name"] = (
            dataframe["product_name"].astype("string")
        )

        dataframe["product_price"] = pd.to_numeric(
            dataframe["product_price"],
            errors="coerce"
        )

        dataframe["price_date"] = pd.to_datetime(
            dataframe["price_date"],
            errors="coerce"
        )

    # --------------------------------------------------------
    # HOMOGÉNÉISATION STRUCTURELLE DES SOURCES PRODUIT
    # --------------------------------------------------------

    # product.csv : produits internes en euros
    products_csv["product_price_original"] = (
        products_csv["product_price"]
    )

    products_csv["currency_original"] = "EUR"
    products_csv["product_source"] = "INTERNE"

    # product.xml : produits externes en dollars
    products_xml["product_price_original"] = (
        products_xml["product_price"]
    )

    products_xml["currency_original"] = "USD"
    products_xml["product_source"] = "EXTERNE"

    # Colonnes communes aux deux sources
    colonnes_produit = [
        "product_id",
        "product_name",
        "product_price_original",
        "currency_original",
        "price_date",
        "product_source"
    ]

    # Sélection de la même structure pour les deux sources
    products_csv = products_csv[colonnes_produit]
    products_xml = products_xml[colonnes_produit]

    # Concaténation après ajout de la devise et de la source
    products_all = pd.concat(
        [products_csv, products_xml],
        ignore_index=True
    )

    # TRANSACTIONS
    colonnes_texte = [
        "trsx_id",
        "client_id",
        "cart_id",
        "product_id"
    ]

    for colonne in colonnes_texte:
        transactions[colonne] = (
            transactions[colonne].astype("string")
        )

    transactions["date"] = pd.to_datetime(
        transactions["date"],
        errors="coerce"
    )

    transactions["amount"] = pd.to_numeric(
        transactions["amount"],
        errors="coerce"
    ).astype("Int64")

    colonnes_numeriques = [
        "price",
        "products_price",
        "cart_price"
    ]

    for colonne in colonnes_numeriques:
        transactions[colonne] = pd.to_numeric(
            transactions[colonne],
            errors="coerce"
        )

    print("Conversion des types terminée.")

    return clients, products_all, transactions


def transformer_donnees(
    clients,
    products_all,
    transactions
):
    """
    Construit les tables relationnelles finales :
    CLIENT, PRODUIT, PANIER et LIGNE_PANIER.
    """

    table_client = clients[
        [
            "client_id",
            "name",
            "age",
            "sexe",
            "opening_date",
            "status"
        ]
    ].copy()

    table_produit = products_all[
    [
        "product_id",
        "product_name",
        "product_price_original",
        "currency_original",
        "price_date",
        "product_source"
    ]
].copy()

    table_panier = (
        transactions[
            [
                "cart_id",
                "date",
                "cart_price",
                "client_id"
            ]
        ]
        .drop_duplicates(subset=["cart_id"])
        .reset_index(drop=True)
    )

    table_ligne_panier = transactions[
        [
            "trsx_id",
            "amount",
            "price",
            "products_price",
            "cart_id",
            "product_id"
        ]
    ].copy()

    print("Transformation des données terminée.")

    return {
        "CLIENT": table_client,
        "PRODUIT": table_produit,
        "PANIER": table_panier,
        "LIGNE_PANIER": table_ligne_panier
    }

# ============================================================
# CONTRÔLES QUALITÉ
# ============================================================

def creer_ligne_rapport(
    controle,
    categorie,
    nombre_anomalies,
    criticite,
    commentaire
):
    """
    Crée une ligne standardisée pour le rapport qualité.
    """

    nombre_anomalies = int(nombre_anomalies)

    if nombre_anomalies == 0:
        statut = "CONFORME"
    elif criticite == "Bloquante":
        statut = "ANOMALIE"
    elif criticite == "Avertissement":
        statut = "AVERTISSEMENT"
    else:
        statut = "INFORMATION"

    return {
        "controle": controle,
        "categorie": categorie,
        "nombre_anomalies": nombre_anomalies,
        "statut": statut,
        "criticite": criticite,
        "commentaire": commentaire
    }


def compter_valeurs_manquantes(dataframe):
    """
    Retourne le nombre total de valeurs manquantes.
    """
    return int(dataframe.isna().sum().sum())


def compter_doublons_complets(dataframe):
    """
    Retourne le nombre de lignes entièrement dupliquées.
    """
    return int(dataframe.duplicated().sum())

def compter_anomalies_cle_primaire(dataframe, colonne_cle):
    """
    Compte les clés primaires dupliquées ou manquantes.
    """
    doublons = dataframe[colonne_cle].duplicated().sum()
    valeurs_manquantes = dataframe[colonne_cle].isna().sum()

    return int(doublons + valeurs_manquantes)

def compter_cles_etrangeres_inconnues(
    dataframe_enfant,
    colonne_etrangere,
    dataframe_parent,
    colonne_parent
):
    """
    Compte les clés étrangères qui ne correspondent
    à aucune clé de la table parente.
    """

    masque_inconnu = ~dataframe_enfant[colonne_etrangere].isin(
        dataframe_parent[colonne_parent]
    )

    return int(masque_inconnu.sum())

def compter_paniers_plusieurs_clients(transactions):
    """
    Compte les paniers associés à plusieurs clients.
    """

    nombre_clients_par_panier = (
        transactions
        .groupby("cart_id")["client_id"]
        .nunique()
    )

    return int((nombre_clients_par_panier > 1).sum())

def compter_paniers_plusieurs_dates(transactions):
    """
    Compte les paniers associés à plusieurs dates.
    """

    nombre_dates_par_panier = (
        transactions
        .groupby("cart_id")["date"]
        .nunique()
    )

    return int((nombre_dates_par_panier > 1).sum())

def compter_quantites_invalides(transactions):
    """
    Compte les quantités nulles, négatives ou manquantes.
    """

    masque_invalide = (
        transactions["amount"].isna()
        | (transactions["amount"] <= 0)
    )

    return int(masque_invalide.sum())

def compter_prix_invalides(transactions):
    """
    Compte les prix unitaires négatifs ou manquants.
    """

    masque_invalide = (
        transactions["price"].isna()
        | (transactions["price"] < 0)
    )

    return int(masque_invalide.sum())

def compter_products_price_incoherents(transactions):
    """
    Vérifie que products_price = amount × price.
    """

    montant_calcule = (
        transactions["amount"].astype("float64")
        * transactions["price"]
    )

    masque_incoherent = ~np.isclose(
        transactions["products_price"],
        montant_calcule,
        equal_nan=False
    )

    return int(masque_incoherent.sum())

def compter_paniers_plusieurs_totaux(transactions):
    """
    Compte les paniers ayant plusieurs valeurs de cart_price.
    """

    nombre_totaux_par_panier = (
        transactions
        .groupby("cart_id")["cart_price"]
        .nunique()
    )

    return int((nombre_totaux_par_panier > 1).sum())

def compter_totaux_panier_incoherents(transactions):
    """
    Vérifie que cart_price correspond à la somme
    des products_price du panier.
    """

    totaux_calcules = (
        transactions
        .groupby("cart_id", as_index=False)["products_price"]
        .sum()
        .rename(columns={
            "products_price": "cart_price_calcule"
        })
    )

    totaux_declares = (
        transactions[
            ["cart_id", "cart_price"]
        ]
        .drop_duplicates(subset=["cart_id"])
    )

    comparaison = totaux_declares.merge(
        totaux_calcules,
        on="cart_id",
        how="left"
    )

    masque_incoherent = ~np.isclose(
        comparaison["cart_price"],
        comparaison["cart_price_calcule"],
        equal_nan=False
    )

    return int(masque_incoherent.sum())

def compter_ecarts_prix_catalogue(
    transactions,
    products_all
):
    """
    Compare le prix transactionnel au prix catalogue
    uniquement pour les produits internes en EUR.

    Les produits externes en USD sont exclus du contrôle,
    car aucun taux de conversion n'est fourni.
    """

    produits_internes_eur = products_all[
        (
            products_all["product_source"] == "INTERNE"
        )
        & (
            products_all["currency_original"] == "EUR"
        )
    ][
        [
            "product_id",
            "product_price_original"
        ]
    ]

    comparaison = transactions.merge(
        produits_internes_eur,
        on="product_id",
        how="inner"
    )

    masque_ecart = ~np.isclose(
        comparaison["price"],
        comparaison["product_price_original"],
        equal_nan=False
    )

    return int(masque_ecart.sum())

def compter_transactions_avant_date_prix(
    transactions,
    products_all
):
    """
    Compte les transactions antérieures à price_date.
    """

    comparaison = transactions.merge(
        products_all[
            [
                "product_id",
                "price_date"
            ]
        ],
        on="product_id",
        how="left"
    )

    masque = (
        comparaison["date"].notna()
        & comparaison["price_date"].notna()
        & (comparaison["date"] < comparaison["price_date"])
    )

    return int(masque.sum())

def analyser_repetitions_cart_produit(transactions):
    """
    Retourne le nombre de couples cart_id-product_id répétés
    et le nombre de lignes concernées.
    """

    masque_repetition = transactions.duplicated(
        subset=["cart_id", "product_id"],
        keep=False
    )

    lignes_repetees = transactions.loc[
        masque_repetition,
        ["cart_id", "product_id"]
    ]

    nombre_lignes = len(lignes_repetees)

    nombre_couples = (
        lignes_repetees
        .drop_duplicates()
        .shape[0]
    )

    return int(nombre_couples), int(nombre_lignes)

def compter_devises_invalides(products_all):
    """
    Compte les produits dont la devise n'est ni EUR ni USD.
    """

    devises_autorisees = {"EUR", "USD"}

    masque_invalide = (
        products_all["currency_original"].isna()
        | ~products_all["currency_original"].isin(
            devises_autorisees
        )
    )

    return int(masque_invalide.sum())

def compter_sources_produit_invalides(products_all):
    """
    Compte les produits dont la source
    n'est ni INTERNE ni EXTERNE.
    """

    sources_autorisees = {"INTERNE", "EXTERNE"}

    masque_invalide = (
        products_all["product_source"].isna()
        | ~products_all["product_source"].isin(
            sources_autorisees
        )
    )

    return int(masque_invalide.sum())

def compter_incoherences_source_devise(products_all):
    """
    Vérifie la cohérence entre la source du produit
    et sa devise d'origine.

    INTERNE doit correspondre à EUR.
    EXTERNE doit correspondre à USD.
    """

    masque_incoherent = (
        (
            (products_all["product_source"] == "INTERNE")
            & (products_all["currency_original"] != "EUR")
        )
        |
        (
            (products_all["product_source"] == "EXTERNE")
            & (products_all["currency_original"] != "USD")
        )
    )

    return int(masque_incoherent.sum())

def compter_prix_produit_invalides(products_all):
    """
    Compte les prix catalogue manquants,
    nuls ou négatifs.
    """

    masque_invalide = (
        products_all["product_price_original"].isna()
        | (products_all["product_price_original"] <= 0)
    )

    return int(masque_invalide.sum())


def verifier_qualite(
    clients,
    products_all,
    transactions,
    tables
):
    """
    Exécute l'ensemble des contrôles qualité
    et retourne le rapport ainsi que le statut global.
    """

    table_client = tables["CLIENT"]
    table_produit = tables["PRODUIT"]
    table_panier = tables["PANIER"]
    table_ligne_panier = tables["LIGNE_PANIER"]

    rapport = []

    # Complétude
    for nom_table, dataframe in tables.items():

        rapport.append(
            creer_ligne_rapport(
                controle=f"Valeurs manquantes dans {nom_table}",
                categorie="Complétude",
                nombre_anomalies=compter_valeurs_manquantes(
                    dataframe
                ),
                criticite="Bloquante",
                commentaire=(
                    "Les colonnes obligatoires doivent être renseignées."
                )
            )
        )

    # Doublons complets
    for nom_table, dataframe in tables.items():

        rapport.append(
            creer_ligne_rapport(
                controle=f"Doublons complets dans {nom_table}",
                categorie="Unicité",
                nombre_anomalies=compter_doublons_complets(
                    dataframe
                ),
                criticite="Bloquante",
                commentaire=(
                    "Une ligne complète ne doit pas être répétée."
                )
            )
        )

    # Clés primaires
    cles_primaires = {
        "CLIENT": "client_id",
        "PRODUIT": "product_id",
        "PANIER": "cart_id",
        "LIGNE_PANIER": "trsx_id"
    }

    for nom_table, colonne_cle in cles_primaires.items():

        rapport.append(
            creer_ligne_rapport(
                controle=f"Unicité de {colonne_cle}",
                categorie="Clé primaire",
                nombre_anomalies=compter_anomalies_cle_primaire(
                    tables[nom_table],
                    colonne_cle
                ),
                criticite="Bloquante",
                commentaire=(
                    f"{colonne_cle} doit être unique et renseigné."
                )
            )
        )

    # Intégrité référentielle
    rapport.append(
        creer_ligne_rapport(
            controle="PANIER vers CLIENT",
            categorie="Intégrité référentielle",
            nombre_anomalies=compter_cles_etrangeres_inconnues(
                table_panier,
                "client_id",
                table_client,
                "client_id"
            ),
            criticite="Bloquante",
            commentaire=(
                "Chaque panier doit référencer un client existant."
            )
        )
    )

    rapport.append(
        creer_ligne_rapport(
            controle="LIGNE_PANIER vers PANIER",
            categorie="Intégrité référentielle",
            nombre_anomalies=compter_cles_etrangeres_inconnues(
                table_ligne_panier,
                "cart_id",
                table_panier,
                "cart_id"
            ),
            criticite="Bloquante",
            commentaire=(
                "Chaque ligne doit référencer un panier existant."
            )
        )
    )

    rapport.append(
        creer_ligne_rapport(
            controle="LIGNE_PANIER vers PRODUIT",
            categorie="Intégrité référentielle",
            nombre_anomalies=compter_cles_etrangeres_inconnues(
                table_ligne_panier,
                "product_id",
                table_produit,
                "product_id"
            ),
            criticite="Bloquante",
            commentaire=(
                "Chaque ligne doit référencer un produit existant."
            )
        )
    )

    # Règles métier
    controles_metier = [
        (
            "Un seul client par panier",
            "Cohérence métier",
            compter_paniers_plusieurs_clients(transactions),
            "Un panier ne peut appartenir qu'à un seul client."
        ),
        (
            "Une seule date par panier",
            "Cohérence métier",
            compter_paniers_plusieurs_dates(transactions),
            "Un panier ne peut avoir qu'une seule date."
        ),
        (
            "Quantités strictement positives",
            "Validité métier",
            compter_quantites_invalides(transactions),
            "La quantité doit être strictement positive."
        ),
        (
            "Prix unitaires valides",
            "Validité métier",
            compter_prix_invalides(transactions),
            "Le prix doit être positif ou nul."
        ),
        (
            "Calcul de products_price",
            "Exactitude",
            compter_products_price_incoherents(transactions),
            "products_price doit être égal à amount multiplié par price."
        ),
        (
            "Un seul cart_price par panier",
            "Cohérence métier",
            compter_paniers_plusieurs_totaux(transactions),
            "Un panier ne doit posséder qu'un seul total déclaré."
        ),
        (
            "Calcul du total du panier",
            "Exactitude",
            compter_totaux_panier_incoherents(transactions),
            "cart_price doit correspondre à la somme des products_price."
        )
    ]

    for (
        controle,
        categorie,
        nombre_anomalies,
        commentaire
    ) in controles_metier:

        rapport.append(
            creer_ligne_rapport(
                controle=controle,
                categorie=categorie,
                nombre_anomalies=nombre_anomalies,
                criticite="Bloquante",
                commentaire=commentaire
            )
        )

        # Contrôles d'homogénéisation du catalogue produit
    controles_produit = [
        (
            "Validité des devises produit",
            "Homogénéisation",
            compter_devises_invalides(products_all),
            "Les devises autorisées sont EUR et USD."
        ),
        (
            "Validité des sources produit",
            "Homogénéisation",
            compter_sources_produit_invalides(products_all),
            "Les sources autorisées sont INTERNE et EXTERNE."
        ),
        (
            "Cohérence source-devise",
            "Homogénéisation",
            compter_incoherences_source_devise(products_all),
            (
                "Les produits internes doivent être en EUR "
                "et les produits externes en USD."
            )
        ),
        (
            "Validité des prix catalogue",
            "Validité métier",
            compter_prix_produit_invalides(products_all),
            (
                "Le prix d'origine d'un produit doit être "
                "renseigné et strictement positif."
            )
        )
    ]

    for (
        controle,
        categorie,
        nombre_anomalies,
        commentaire
    ) in controles_produit:

        rapport.append(
            creer_ligne_rapport(
                controle=controle,
                categorie=categorie,
                nombre_anomalies=nombre_anomalies,
                criticite="Bloquante",
                commentaire=commentaire
            )
        )

    # Avertissements
    rapport.append(
        creer_ligne_rapport(
            controle=(
                "Écart entre prix transactionnel "
                "et catalogue interne EUR"
            ),
            categorie="Cohérence tarifaire",
            nombre_anomalies=compter_ecarts_prix_catalogue(
                transactions,
                products_all
            ),
            criticite="Avertissement",
            commentaire=(
                "Le contrôle porte uniquement sur les produits "
                "internes dont le prix catalogue est en EUR. "
                "Les produits externes en USD sont exclus, "
                "car aucun taux de conversion n'est fourni. "
                "Un écart peut correspondre à une remise "
                "ou à un prix historique."
            )
        )
    )

    rapport.append(
        creer_ligne_rapport(
            controle="Transaction antérieure à price_date",
            categorie="Cohérence temporelle",
            nombre_anomalies=compter_transactions_avant_date_prix(
                transactions,
                products_all
            ),
            criticite="Avertissement",
            commentaire=(
                "Le catalogue ne contenant pas d'historique tarifaire, "
                "le prix transactionnel est conservé."
            )
        )
    )

    # Information sur les répétitions
    nombre_couples, nombre_lignes = (
        analyser_repetitions_cart_produit(transactions)
    )

    rapport.append(
        creer_ligne_rapport(
            controle="Répétition du couple cart_id-product_id",
            categorie="Information",
            nombre_anomalies=0,
            criticite="Information",
            commentaire=(
                f"{nombre_couples} couples répétés et "
                f"{nombre_lignes} lignes concernées. "
                "Les trsx_id sont distincts : "
                "ces lignes ne sont pas considérées comme des doublons."
            )
        )
    )
    rapport_qualite_df = pd.DataFrame(rapport)

    rapport_qualite_df.insert(
        0,
        "date_execution",
        pd.Timestamp.now().strftime("%Y-%m-%d %H:%M:%S")
    )

    anomalies_bloquantes = rapport_qualite_df[
        (rapport_qualite_df["criticite"] == "Bloquante")
        & (rapport_qualite_df["nombre_anomalies"] > 0)
    ]

    statut_pipeline = (
        "SUCCÈS"
        if anomalies_bloquantes.empty
        else "ÉCHEC"
    )

    return (
        rapport_qualite_df,
        statut_pipeline,
        anomalies_bloquantes
    )


# ============================================================
# EXPORT
# ============================================================

def exporter_tables(tables, processed_dir):
    """
    Exporte les tables finales au format CSV.

    Paramètres
    ----------
    tables : dict
        Dictionnaire contenant les DataFrames CLIENT,
        PRODUIT, PANIER et LIGNE_PANIER.
    processed_dir : Path
        Dossier de destination des fichiers transformés.

    Retour
    ------
    dict
        Chemins des fichiers exportés.
    """

    processed_dir.mkdir(parents=True, exist_ok=True)

    noms_fichiers = {
        "CLIENT": "client.csv",
        "PRODUIT": "produit.csv",
        "PANIER": "panier.csv",
        "LIGNE_PANIER": "ligne_panier.csv"
    }

    fichiers_exportes = {}

    for nom_table, dataframe in tables.items():

        chemin_sortie = (
            processed_dir / noms_fichiers[nom_table]
        )

        dataframe.to_csv(
            chemin_sortie,
            index=False,
            encoding="utf-8-sig"
        )

        fichiers_exportes[nom_table] = chemin_sortie

        print(
            f"{nom_table} exportée : "
            f"{chemin_sortie.name}"
        )

    return fichiers_exportes


def generer_rapport(
    rapport_qualite_df,
    reports_dir
):
    """
    Exporte le rapport qualité au format CSV.

    Paramètres
    ----------
    rapport_qualite_df : DataFrame
        Rapport produit par verifier_qualite().
    reports_dir : Path
        Dossier de destination du rapport.

    Retour
    ------
    Path
        Chemin du rapport exporté.
    """

    reports_dir.mkdir(parents=True, exist_ok=True)

    chemin_rapport = (
        reports_dir / "rapport_qualite.csv"
    )

    rapport_qualite_df.to_csv(
        chemin_rapport,
        index=False,
        encoding="utf-8-sig"
    )

    print(
        "Rapport qualité exporté :",
        chemin_rapport.name
    )

    return chemin_rapport


# ============================================================
# BASE DE DONNÉES RELATIONNELLE
# ============================================================

def alimenter_base_sqlite(tables, database_path):
    """
    Alimente une base de données SQLite avec les tables
    CLIENT, PRODUIT, PANIER et LIGNE_PANIER.

    Paramètres
    ----------
    tables : dict
        Dictionnaire contenant les tables finales.
    database_path : Path
        Chemin de la base SQLite.

    Retour
    ------
    Path
        Chemin de la base de données créée.
    """

    database_path.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    with sqlite3.connect(database_path) as connexion:

        # Activation des contraintes de clés étrangères
        connexion.execute("PRAGMA foreign_keys = ON;")

        # Suppression des anciennes tables
        connexion.execute(
            "DROP TABLE IF EXISTS LIGNE_PANIER;"
        )
        connexion.execute(
            "DROP TABLE IF EXISTS PANIER;"
        )
        connexion.execute(
            "DROP TABLE IF EXISTS PRODUIT;"
        )
        connexion.execute(
            "DROP TABLE IF EXISTS CLIENT;"
        )

        # Création de la table CLIENT
        connexion.execute(
            """
            CREATE TABLE CLIENT (
                client_id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                age INTEGER NOT NULL,
                sexe TEXT NOT NULL,
                opening_date TEXT NOT NULL,
                status TEXT NOT NULL
            );
            """
        )

                # Création de la table PRODUIT
        connexion.execute(
            """
            CREATE TABLE PRODUIT (
                product_id TEXT PRIMARY KEY,
                product_name TEXT NOT NULL,
                product_price_original REAL NOT NULL,
                currency_original TEXT NOT NULL,
                price_date TEXT NOT NULL,
                product_source TEXT NOT NULL,

                CHECK (
                    product_price_original > 0
                ),

                CHECK (
                    currency_original IN ('EUR', 'USD')
                ),

                CHECK (
                    product_source IN (
                        'INTERNE',
                        'EXTERNE'
                    )
                ),

                CHECK (
                    (
                        product_source = 'INTERNE'
                        AND currency_original = 'EUR'
                    )
                    OR
                    (
                        product_source = 'EXTERNE'
                        AND currency_original = 'USD'
                    )
                )
            );
            """
        )

        # Création de la table PANIER
        connexion.execute(
            """
            CREATE TABLE PANIER (
                cart_id TEXT PRIMARY KEY,
                date TEXT NOT NULL,
                cart_price REAL NOT NULL,
                client_id TEXT NOT NULL,

                FOREIGN KEY (client_id)
                REFERENCES CLIENT(client_id)
            );
            """
        )

        # Création de la table LIGNE_PANIER
        connexion.execute(
            """
            CREATE TABLE LIGNE_PANIER (
                trsx_id TEXT PRIMARY KEY,
                amount INTEGER NOT NULL,
                price REAL NOT NULL,
                products_price REAL NOT NULL,
                cart_id TEXT NOT NULL,
                product_id TEXT NOT NULL,

                FOREIGN KEY (cart_id)
                REFERENCES PANIER(cart_id),

                FOREIGN KEY (product_id)
                REFERENCES PRODUIT(product_id)
            );
            """
        )

        # Préparation des dates pour SQLite
        tables_sql = {
            nom: dataframe.copy()
            for nom, dataframe in tables.items()
        }

        tables_sql["CLIENT"]["opening_date"] = (
            tables_sql["CLIENT"]["opening_date"]
            .dt.strftime("%Y-%m-%d")
        )

        tables_sql["PRODUIT"]["price_date"] = (
            tables_sql["PRODUIT"]["price_date"]
            .dt.strftime("%Y-%m-%d")
        )

        tables_sql["PANIER"]["date"] = (
            tables_sql["PANIER"]["date"]
            .dt.strftime("%Y-%m-%d")
        )

        # Insertion dans le bon ordre
        tables_sql["CLIENT"].to_sql(
            "CLIENT",
            connexion,
            if_exists="append",
            index=False
        )

        tables_sql["PRODUIT"].to_sql(
            "PRODUIT",
            connexion,
            if_exists="append",
            index=False
        )

        tables_sql["PANIER"].to_sql(
            "PANIER",
            connexion,
            if_exists="append",
            index=False
        )

        tables_sql["LIGNE_PANIER"].to_sql(
            "LIGNE_PANIER",
            connexion,
            if_exists="append",
            index=False
        )

        connexion.commit()

    print(
        "Base SQLite alimentée :",
        database_path.name
    )

    return database_path


# ============================================================
# ORCHESTRATION
# ============================================================

def executer_pipeline(
    raw_dir,
    processed_dir,
    reports_dir
):
    """
    Exécute l'intégralité du pipeline de données.

    Étapes :
    1. Chargement des sources
    2. Conversion des types
    3. Transformation des données
    4. Contrôles qualité
    5. Génération du rapport
    6. Export des tables si les contrôles bloquants sont conformes

    Retour
    ------
    dict
        Résultats principaux de l'exécution.
    """

    print("=" * 60)
    print("DÉMARRAGE DU PIPELINE LEROUGE MOULIN")
    print("=" * 60)

    try:
        # 1. Chargement
        (
            clients,
            products_csv,
            products_xml,
            transactions
        ) = charger_donnees(raw_dir)

        # 2. Conversion
        (
            clients,
            products_all,
            transactions
        ) = convertir_types(
            clients,
            products_csv,
            products_xml,
            transactions
        )

        # 3. Transformation
        tables = transformer_donnees(
            clients,
            products_all,
            transactions
        )

        # 4. Contrôles qualité
        (
            rapport_qualite_df,
            statut_pipeline,
            anomalies_bloquantes
        ) = verifier_qualite(
            clients,
            products_all,
            transactions,
            tables
        )

        # 5. Le rapport est toujours exporté
        chemin_rapport = generer_rapport(
            rapport_qualite_df,
            reports_dir
        )

        fichiers_exportes = {}
        chemin_base = None

        # 6. Export conditionnel des tables
        if statut_pipeline == "SUCCÈS":

            fichiers_exportes = exporter_tables(
                tables,
                processed_dir
            )

            chemin_base = alimenter_base_sqlite(
                tables,
                DATABASE_PATH
            )

            print()
            print(
                "Pipeline terminé avec succès : "
                "aucune anomalie bloquante détectée."
            )

        else:

            print()
            print(
                "Pipeline interrompu : "
                "des anomalies bloquantes ont été détectées."
            )

            print(anomalies_bloquantes.to_string(index=False))

        print("=" * 60)

        return {
            "statut": statut_pipeline,
            "tables": tables,
            "rapport_qualite": rapport_qualite_df,
            "anomalies_bloquantes": anomalies_bloquantes,
            "fichiers_exportes": fichiers_exportes,
            "chemin_rapport": chemin_rapport,
            "chemin_base": chemin_base
        }

    except Exception as erreur:

        print()
        print("ÉCHEC TECHNIQUE DU PIPELINE")
        print(type(erreur).__name__, ":", erreur)
        print("=" * 60)

        raise


# ============================================================
# POINT D'ENTRÉE
# ============================================================

if __name__ == "__main__":
    resultats_pipeline = executer_pipeline(
        RAW_DIR,
        PROCESSED_DIR,
        REPORTS_DIR
    )