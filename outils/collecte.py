"""Collecte quotidienne des procédures collectives publiées au BODACC.

Source 1 : l'API ouverte du BODACC (DILA, Licence Ouverte), sans clé.
Source 2 : l'API Recherche d'entreprises (Annuaire des entreprises), sans clé,
           pour l'activité et la tranche d'effectif.

Le résultat est écrit dans donnees/procedures.json. En cas de panne d'une source,
le fichier existant est laissé intact : le site continue de s'afficher.
"""
import datetime as dt
import json
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

from commun import (DONNEES, ORDRE_TRANCHES, charger_config, ecrire_json, lire_date, lire_json,
                    sans_accents, secteur_naf)

BODACC = ("https://bodacc-datadila.opendatasoft.com/api/explore/v2.1/"
          "catalog/datasets/annonces-commerciales")
ANNUAIRE = "https://recherche-entreprises.api.gouv.fr/search"
AGENT = "reprises-a-la-barre/1.0 (site d'information juridique)"
PAUSE = 0.2  # secondes entre deux appels à l'Annuaire des entreprises (limite : 7 appels par seconde)

OUTRE_MER = ("guadeloupe", "martinique", "guyane", "la reunion", "mayotte")

# Repère la désignation d'un administrateur judiciaire dans le texte du jugement
# (« désignant administrateur SELARL… », « en qualité d'administrateur judiciaire »).
AVEC_ADMINISTRATEUR = re.compile(
    r"(designant|nomm\w+)\s+(comme\s+|en qualite d'\s*)?(l'\s*)?administrateur"
    r"|en qualite d'\s*administrateur|administrateur judiciaire\s*:")

# Plusieurs écritures du même filtre : la première que l'API accepte est retenue.
FILTRES = [
    "familleavis=\"collective\" AND dateparution=date'{jour}'",
    "familleavis=\"collective\" AND dateparution>=date'{jour}' AND dateparution<=date'{jour}'",
    "familleavis=\"collective\" AND dateparution=\"{jour}\"",
]
_filtre_valide = None


def appel(url, essais=4):
    """Appelle une adresse et renvoie le JSON. Patiente et réessaie si le serveur est saturé."""
    derniere = None
    for tentative in range(essais):
        try:
            requete = urllib.request.Request(url, headers={"User-Agent": AGENT,
                                                           "Accept": "application/json"})
            with urllib.request.urlopen(requete, timeout=90) as reponse:
                return json.loads(reponse.read().decode("utf-8"))
        except urllib.error.HTTPError as erreur:
            derniere = erreur
            if erreur.code == 429 or erreur.code >= 500:
                pause = erreur.headers.get("Retry-After", "")
                time.sleep(float(pause) if pause.isdigit() else 2.0 * (tentative + 1))
                continue
            raise
        except (urllib.error.URLError, TimeoutError, ValueError) as erreur:
            derniere = erreur
            time.sleep(2.0 * (tentative + 1))
    raise RuntimeError(f"Pas de réponse exploitable : {url} ({derniere})")


def annonces_du_jour(jour):
    """Toutes les annonces de procédures collectives parues un jour donné."""
    global _filtre_valide
    filtres = [_filtre_valide] if _filtre_valide else FILTRES
    derniere = None
    for filtre in filtres:
        condition = filtre.format(jour=jour.isoformat())
        try:
            # 1. Export complet en une requête.
            url = BODACC + "/exports/json?" + urllib.parse.urlencode({"where": condition, "limit": -1})
            resultat = appel(url, essais=2)
            if isinstance(resultat, list):
                _filtre_valide = filtre
                return resultat
        except Exception as erreur:  # noqa: BLE001 - on tente la voie suivante
            derniere = erreur
        try:
            # 2. À défaut, lecture page par page.
            annonces, debut = [], 0
            while True:
                url = BODACC + "/records?" + urllib.parse.urlencode(
                    {"where": condition, "limit": 100, "offset": debut, "order_by": "id"})
                page = appel(url, essais=2).get("results", [])
                annonces.extend(page)
                debut += 100
                if len(page) < 100 or debut >= 9900:
                    break
            _filtre_valide = filtre
            return annonces
        except Exception as erreur:  # noqa: BLE001
            derniere = erreur
    raise RuntimeError(f"Le BODACC n'a accepté aucune des requêtes prévues ({derniere})")


def objet(valeur):
    """Certains champs arrivent tantôt en objet, tantôt en texte JSON."""
    if isinstance(valeur, (dict, list)):
        return valeur
    if isinstance(valeur, str) and valeur.strip().startswith(("{", "[")):
        try:
            return json.loads(valeur)
        except ValueError:
            return {}
    return {}


def personnes(annonce):
    liste = objet(annonce.get("listepersonnes"))
    if isinstance(liste, dict):
        liste = liste.get("personne", liste)
    if isinstance(liste, dict):
        liste = [liste]
    return [p for p in (liste or []) if isinstance(p, dict)]


def siren_de(annonce):
    brut = annonce.get("registre")
    if isinstance(brut, list):
        brut = " ".join(str(x) for x in brut)
    trouve = re.search(r"\d{3}\s?\d{3}\s?\d{3}", str(brut or ""))
    if not trouve:
        trouve = re.search(r"\d{3}\s?\d{3}\s?\d{3}", json.dumps(objet(annonce.get("listepersonnes"))))
    return re.sub(r"\s", "", trouve.group(0)) if trouve else ""


def type_de_procedure(nature):
    """rj, lj, conv, ou None si l'annonce ne signale pas une entreprise à reprendre."""
    n = sans_accents(nature)
    if "sauvegarde" in n and "conversion" not in n:
        return None
    for ecarte in ("cloture", "plan", "extension", "resolution", "reprise", "faillite",
                   "interdiction", "modifiant", "depot", "arret"):
        if ecarte in n:
            return None
    if "conversion" in n and "liquidation" in n:
        return "conv"
    if "conversion" in n and "redressement" in n:
        return "rj"
    if "ouverture" in n and "liquidation" in n:
        return "lj"
    if "ouverture" in n and "redressement" in n:
        return "rj"
    if "prononc" in n and "liquidation" in n:
        return "lj"
    return None


def capitales(texte):
    """« SAINT-PRIEST » devient « Saint-Priest » ; un texte déjà en minuscules est laissé tel quel."""
    texte = str(texte or "").strip()
    if texte.isupper():
        texte = re.sub(r"[A-Za-zÀ-ÿ]+", lambda m: m.group(0).capitalize(), texte.lower())
    return texte


def analyser(annonce, personnes_morales_seulement=True):
    """Transforme une annonce du BODACC en fiche du site. None si elle n'est pas retenue."""
    avis = sans_accents(annonce.get("typeavis") or "")
    if "annulation" in avis or "rectificatif" in avis:
        return None
    jugement = objet(annonce.get("jugement"))
    if not isinstance(jugement, dict):
        return None
    categorie = type_de_procedure(f"{jugement.get('nature') or ''} {jugement.get('famille') or ''}")
    if categorie is None:
        return None
    gens = personnes(annonce)
    genres = {sans_accents(p.get("typePersonne") or "") for p in gens}
    if personnes_morales_seulement and "pp" in genres:
        return None
    nom = str(annonce.get("commercant") or "").strip()
    if not nom and gens:
        nom = str(gens[0].get("denomination") or "").strip()
    if not nom or nom == "[ND]":
        return None
    complement = re.sub(r"\s+", " ", str(jugement.get("complementJugement") or "")).strip()
    avec_aj = bool(AVEC_ADMINISTRATEUR.search(sans_accents(complement).replace("\u2019", "'")))
    if len(complement) > 360:
        complement = complement[:357].rsplit(" ", 1)[0] + "…"
    region = str(annonce.get("region_nom_officiel") or "")
    if sans_accents(region) in OUTRE_MER:
        region = "Outre-mer"
    parution = lire_date(annonce.get("dateparution"))
    jour = lire_date(jugement.get("date")) or parution
    if parution is None or jour is None:
        return None
    return {
        "id": str(annonce.get("id") or ""),
        "nom": nom,
        "siren": siren_de(annonce),
        "ville": capitales(annonce.get("ville")),
        "dept": str(annonce.get("departement_nom_officiel") or ""),
        "region": region,
        "tribunal": str(annonce.get("tribunal") or ""),
        "type": categorie,
        "date": jour.isoformat(),
        "parution": parution.isoformat(),
        "aj": avec_aj,
        "texte": complement,
        "url": str(annonce.get("url_complete") or ""),
        "morale": "pm" in genres,
        "naf": "", "secteur": "", "effectif": "",
    }


def annuaire(siren):
    """Activité, tranche d'effectif et forme juridique d'une entreprise. {} si introuvable."""
    if not re.fullmatch(r"\d{9}", siren or ""):
        return {}
    url = ANNUAIRE + "?" + urllib.parse.urlencode({"q": siren, "per_page": 1})
    try:
        resultats = appel(url).get("results", [])
    except Exception:  # noqa: BLE001 - l'enrichissement est facultatif
        return {}
    for entreprise in resultats:
        if str(entreprise.get("siren")) == siren:
            return {
                "naf": str(entreprise.get("activite_principale") or ""),
                "effectif": str(entreprise.get("tranche_effectif_salarie") or ""),
                "forme": str(entreprise.get("nature_juridique") or ""),
            }
    return {}


def retenir(fiche, reglages):
    """Applique les seuils du fichier de réglages à une fiche enrichie."""
    if fiche["type"] != "rj" and not reglages.get("inclure_liquidations", True):
        return False
    if reglages.get("personnes_morales_seulement", True):
        if fiche.get("forme", "").startswith("1"):
            return False
        if not fiche.get("morale") and not fiche.get("forme"):
            return False
    if fiche["aj"]:
        return True
    minimum = reglages.get("effectif_minimum", "01")
    if minimum not in ORDRE_TRANCHES or ORDRE_TRANCHES.index(minimum) <= 1:
        return True
    if fiche["effectif"] not in ORDRE_TRANCHES:
        return False
    return ORDRE_TRANCHES.index(fiche["effectif"]) >= ORDRE_TRANCHES.index(minimum)


def traiter(annonces, connus, reglages, aujourdhui, enrichir=None, pause=None):
    """Analyse, enrichit et filtre un lot d'annonces. Renvoie (fiches retenues, identifiants vus)."""
    enrichir = enrichir or annuaire
    pause = PAUSE if pause is None else pause
    retenues, vus = [], []
    for annonce in annonces:
        fiche = analyser(annonce, reglages.get("personnes_morales_seulement", True))
        if fiche is None or not fiche["id"] or fiche["id"] in connus:
            continue
        connus.add(fiche["id"])
        vus.append(fiche["id"])
        complement = enrichir(fiche["siren"])
        if pause:
            time.sleep(pause)
        fiche["naf"] = complement.get("naf", "")
        fiche["effectif"] = complement.get("effectif", "")
        fiche["forme"] = complement.get("forme", "")
        fiche["secteur"] = secteur_naf(fiche["naf"]) if fiche["naf"] else ""
        if retenir(fiche, reglages):
            fiche["ajoute"] = aujourdhui.isoformat()
            fiche.pop("forme", None)
            fiche.pop("morale", None)
            retenues.append(fiche)
    return retenues, vus


def principal(aujourdhui=None):
    reglages = charger_config()["collecte"]
    aujourdhui = aujourdhui or dt.date.today()
    etat = lire_json(DONNEES / "etat.json", {})
    procedures = lire_json(DONNEES / "procedures.json", [])
    vus = etat.get("vus", {})
    connus = {p["id"] for p in procedures} | set(vus)

    derniere = lire_date(etat.get("derniere_parution"))
    if derniere is None:
        debut = aujourdhui - dt.timedelta(days=int(reglages.get("jours_au_premier_lancement", 10)))
    else:
        # On relit les trois derniers jours : certaines annonces sont mises en ligne avec retard.
        debut = min(derniere + dt.timedelta(days=1), aujourdhui - dt.timedelta(days=3))

    nouvelles, jour, lues = [], debut, 0
    while jour <= aujourdhui:
        annonces = annonces_du_jour(jour)
        lues += len(annonces)
        retenues, identifiants = traiter(annonces, connus, reglages, aujourdhui)
        nouvelles.extend(retenues)
        for identifiant in identifiants:
            vus[identifiant] = jour.isoformat()
        if annonces:
            etat["derniere_parution"] = jour.isoformat()
        print(f"{jour.isoformat()} : {len(annonces)} annonces lues, {len(retenues)} retenues")
        jour += dt.timedelta(days=1)

    limite = (aujourdhui - dt.timedelta(days=int(reglages.get("jours_conserves", 45)))).isoformat()
    procedures = [p for p in procedures + nouvelles if p.get("parution", p["date"]) >= limite]
    procedures.sort(key=lambda p: (p["date"], p["id"]), reverse=True)
    garde = (aujourdhui - dt.timedelta(days=10)).isoformat()
    etat["vus"] = {i: j for i, j in vus.items() if j >= garde}

    ecrire_json(DONNEES / "procedures.json", procedures)
    ecrire_json(DONNEES / "etat.json", etat)
    print(f"Terminé : {lues} annonces lues, {len(nouvelles)} nouvelles procédures, "
          f"{len(procedures)} affichées.")


if __name__ == "__main__":
    try:
        principal()
    except Exception as erreur:  # noqa: BLE001
        print(f"COLLECTE INTERROMPUE : {erreur}", file=sys.stderr)
        print("Les données précédentes sont conservées.", file=sys.stderr)
        sys.exit(1)
