"""Outils partagés : réglages, dates, secteurs, lecture des dossiers saisis à la main."""
import datetime as dt
import json
import re
import tomllib
import unicodedata
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
DONNEES = RACINE / "donnees"

MOIS = ["janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août",
        "septembre", "octobre", "novembre", "décembre"]
MOIS_COURTS = ["janv.", "févr.", "mars", "avr.", "mai", "juin", "juil.", "août",
               "sept.", "oct.", "nov.", "déc."]
JOURS = ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"]

SECTEURS = ["Industrie", "Bâtiment", "Commerce", "Restauration et hôtellerie", "Transport",
            "Numérique", "Agroalimentaire", "Agriculture", "Services"]

REGIONS = ["Auvergne-Rhône-Alpes", "Bourgogne-Franche-Comté", "Bretagne", "Centre-Val de Loire",
           "Corse", "Grand Est", "Hauts-de-France", "Île-de-France", "Normandie",
           "Nouvelle-Aquitaine", "Occitanie", "Pays de la Loire", "Provence-Alpes-Côte d'Azur",
           "Outre-mer"]

# Tranches d'effectif de l'INSEE, de la plus petite à la plus grande.
TRANCHES = {
    "NN": "Sans salarié", "00": "Sans salarié", "01": "1 à 2 salariés", "02": "3 à 5 salariés",
    "03": "6 à 9 salariés", "11": "10 à 19 salariés", "12": "20 à 49 salariés",
    "21": "50 à 99 salariés", "22": "100 à 199 salariés", "31": "200 à 249 salariés",
    "32": "250 à 499 salariés", "41": "500 à 999 salariés", "42": "1 000 à 1 999 salariés",
    "51": "2 000 à 4 999 salariés", "52": "5 000 à 9 999 salariés", "53": "10 000 salariés et plus",
}
ORDRE_TRANCHES = list(TRANCHES)

TYPES = {"rj": "Redressement judiciaire", "lj": "Liquidation judiciaire",
         "conv": "Conversion en liquidation judiciaire"}

TAILLES = {"tpe": "Moins de 10 salariés", "pme": "10 à 49 salariés", "eti": "50 salariés et plus"}


def charger_config():
    with open(RACINE / "config.toml", "rb") as f:
        return tomllib.load(f)


def lire_json(chemin, defaut):
    try:
        with open(chemin, encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, ValueError):
        return defaut


def ecrire_json(chemin, donnees, compact=False):
    Path(chemin).parent.mkdir(parents=True, exist_ok=True)
    with open(chemin, "w", encoding="utf-8") as f:
        if compact:
            json.dump(donnees, f, ensure_ascii=False, separators=(",", ":"))
        else:
            json.dump(donnees, f, ensure_ascii=False, indent=1)
        f.write("\n")


def sans_accents(texte):
    decompose = unicodedata.normalize("NFD", str(texte or ""))
    return "".join(c for c in decompose if unicodedata.category(c) != "Mn").lower()


def slug(texte):
    return re.sub(r"[^a-z0-9]+", "-", sans_accents(texte)).strip("-") or "dossier"


def secteur_naf(naf):
    """Secteur d'activité à partir d'un code NAF (ex. « 25.12Z »)."""
    try:
        division = int(str(naf)[:2])
    except (TypeError, ValueError):
        return "Services"
    if str(naf).startswith(("10.71", "10.13B")):
        return "Commerce"  # boulangeries, pâtisseries et charcuteries artisanales
    if 1 <= division <= 3:
        return "Agriculture"
    if division in (10, 11, 12):
        return "Agroalimentaire"
    if 5 <= division <= 39:
        return "Industrie"
    if 41 <= division <= 43:
        return "Bâtiment"
    if 45 <= division <= 47:
        return "Commerce"
    if 49 <= division <= 53:
        return "Transport"
    if 55 <= division <= 56:
        return "Restauration et hôtellerie"
    if 58 <= division <= 63:
        return "Numérique"
    return "Services"


def taille_tranche(code):
    """Classe de taille (tpe, pme, eti) à partir d'un code de tranche INSEE."""
    if code not in ORDRE_TRANCHES:
        return ""
    rang = ORDRE_TRANCHES.index(code)
    if rang <= ORDRE_TRANCHES.index("03"):
        return "tpe"
    if rang <= ORDRE_TRANCHES.index("12"):
        return "pme"
    return "eti"


def taille_effectif(nombre):
    if nombre is None:
        return ""
    if nombre < 10:
        return "tpe"
    if nombre < 50:
        return "pme"
    return "eti"


def lire_date(texte):
    """Accepte 16/10/2026 comme 2026-10-16. Renvoie None si la date est illisible."""
    texte = str(texte or "").strip()
    m = re.fullmatch(r"(\d{1,2})[/.-](\d{1,2})[/.-](\d{4})", texte)
    try:
        if m:
            return dt.date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
        return dt.date.fromisoformat(texte[:10])
    except ValueError:
        return None


def date_longue(jour, avec_jour=True):
    numero = "1er" if jour.day == 1 else str(jour.day)
    texte = f"{numero} {MOIS[jour.month - 1]} {jour.year}"
    return f"{JOURS[jour.weekday()]} {texte}" if avec_jour else texte


def jours_restants(jour, aujourdhui):
    ecart = (jour - aujourdhui).days
    if ecart < 0:
        return "date passée"
    if ecart == 0:
        return "aujourd'hui"
    if ecart == 1:
        return "demain"
    return f"dans {ecart} jours"


def lieu(ville, departement):
    if ville and departement and sans_accents(ville) != sans_accents(departement):
        return f"{ville} ({departement})"
    return ville or departement


# ---------------------------------------------------------------------------
# Dossiers saisis à la main : un fichier texte par dossier dans donnees/dossiers/
# ---------------------------------------------------------------------------

def _cle(texte):
    return re.sub(r"[^a-z0-9]+", "_", sans_accents(texte)).strip("_")


def lire_dossier(chemin):
    """Lit un fichier de dossier. Renvoie (dossier, None) ou (None, message d'erreur)."""
    lignes = Path(chemin).read_text(encoding="utf-8").splitlines()
    champs, a_vendre, lecture = {}, [], []
    rubrique, point = None, None
    for brute in lignes:
        ligne = brute.strip()
        if ligne.startswith("###"):
            point = {"titre": ligne.lstrip("#").strip(), "texte": ""}
            if rubrique == "lecture":
                lecture.append(point)
            continue
        if ligne.startswith("##"):
            rubrique, point = _cle(ligne.lstrip("#")), None
            continue
        if rubrique is None:
            if not ligne or ligne.startswith("#") or ":" not in ligne:
                continue
            cle, valeur = ligne.split(":", 1)
            champs[_cle(cle)] = valeur.strip()
        elif rubrique == "a_vendre":
            if ligne.startswith(("-", "*", "•")):
                a_vendre.append(ligne[1:].strip())
        elif rubrique == "lecture" and point is not None and ligne:
            point["texte"] = (point["texte"] + " " + ligne).strip()

    nom = Path(chemin).name
    if not champs.get("titre"):
        return None, f"{nom} : la ligne « titre » manque."
    echeance = lire_date(champs.get("date_limite"))
    if echeance is None:
        return None, f"{nom} : la ligne « date_limite » manque ou est illisible (exemple : 16/10/2026)."
    chiffres = re.sub(r"\D", "", champs.get("effectif", ""))
    effectif = int(chiffres) if chiffres else None
    secteur = champs.get("secteur", "")
    proches = [s for s in SECTEURS if sans_accents(s) == sans_accents(secteur)]
    if proches:
        secteur = proches[0]
    region = champs.get("region", "")
    proches = [r for r in REGIONS if sans_accents(r) == sans_accents(region)]
    if proches:
        region = proches[0]
    return {
        "slug": slug(Path(chemin).stem),
        "titre": champs["titre"],
        "ville": champs.get("ville", ""),
        "departement": champs.get("departement", ""),
        "region": region,
        "secteur": secteur,
        "effectif": effectif,
        "taille": taille_effectif(effectif),
        "chiffre_affaires": champs.get("chiffre_affaires", ""),
        "procedure": champs.get("procedure", ""),
        "tribunal": champs.get("tribunal", ""),
        "date_limite": echeance,
        "heure_limite": champs.get("heure_limite", ""),
        "audience": champs.get("audience", ""),
        "etude": champs.get("etude", ""),
        "lien": champs.get("lien", ""),
        "exemple": sans_accents(champs.get("exemple", "")) in ("oui", "o", "yes", "true", "1"),
        "a_vendre": a_vendre,
        "lecture": [p for p in lecture if p["titre"]],
    }, None


def lire_dossiers():
    """Tous les dossiers lisibles, triés par date limite. Les fichiers commençant par _ sont ignorés."""
    dossiers, erreurs = [], []
    for chemin in sorted((DONNEES / "dossiers").glob("*.md")):
        if chemin.name.startswith("_"):
            continue
        dossier, erreur = lire_dossier(chemin)
        if erreur:
            erreurs.append(erreur)
        else:
            dossiers.append(dossier)
    dossiers.sort(key=lambda d: d["date_limite"])
    return dossiers, erreurs
