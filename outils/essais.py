"""Essais hors ligne : rien n'est envoyé, rien n'est téléchargé.

    python outils/essais.py

Les données viennent du répertoire essais/ : des annonces fictives, écrites au format
de l'API du BODACC, et des inscrits fictifs, au format de Brevo.
"""
import datetime as dt
import html.parser
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import alertes
import collecte
import construire
from commun import RACINE, charger_config, lire_dossiers, lire_json, secteur_naf

ECHECS = []


def verifier(condition, message):
    print(("  ok    " if condition else "  ÉCHEC ") + message)
    if not condition:
        ECHECS.append(message)


ANNUAIRE_FICTIF = {
    "111222333": {"naf": "25.12Z", "effectif": "12", "forme": "5710"},
    "222333444": {"naf": "10.71C", "effectif": "01", "forme": "5499"},
    "333444555": {"naf": "70.22Z", "effectif": "NN", "forme": "5710"},
    "777888999": {"naf": "49.41A", "effectif": "21", "forme": "5710"},
    "131313131": {"naf": "10.20Z", "effectif": "03", "forme": "5499"},
    "141414141": {"naf": "56.10A", "effectif": "01", "forme": "1000"},
}

VIDES = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "source", "track", "wbr"}


class Controle(html.parser.HTMLParser):
    """Vérifie que chaque balise ouverte est refermée dans l'ordre."""

    def __init__(self):
        super().__init__()
        self.pile, self.fautes = [], []

    def handle_starttag(self, balise, attributs):
        if balise not in VIDES:
            self.pile.append(balise)

    def handle_endtag(self, balise):
        if balise in VIDES:
            return
        if not self.pile or self.pile[-1] != balise:
            self.fautes.append(f"</{balise}> inattendue (ouverte : {self.pile[-1] if self.pile else 'aucune'})")
            if balise in self.pile:
                while self.pile and self.pile.pop() != balise:
                    pass
        else:
            self.pile.pop()


def essai_classement():
    print("Classement des jugements")
    cas = {
        "Jugement d'ouverture d'une procédure de redressement judiciaire": "rj",
        "Jugement d'ouverture de liquidation judiciaire": "lj",
        "Jugement d'ouverture de liquidation judiciaire simplifiée": "lj",
        "Jugement de conversion en liquidation judiciaire de la procédure de redressement judiciaire": "conv",
        "Jugement de conversion en redressement judiciaire de la procédure de sauvegarde": "rj",
        "Jugement prononçant la liquidation judiciaire": "lj",
        "Jugement d'ouverture d'une procédure de sauvegarde": None,
        "Jugement de clôture pour insuffisance d'actif": None,
        "Jugement arrêtant le plan de cession": None,
        "Jugement arrêtant le plan de redressement": None,
        "Jugement modifiant la date de cessation des paiements": None,
        "Jugement prononçant la faillite personnelle": None,
        "Dépôt de l'état des créances": None,
        "Jugement prononçant la reprise de la procédure de liquidation judiciaire": None,
        "": None,
    }
    for nature, attendu in cas.items():
        verifier(collecte.type_de_procedure(nature) == attendu, f"« {nature or '(vide)'} » → {attendu}")
    verifier(secteur_naf("10.71C") == "Commerce" and secteur_naf("25.12Z") == "Industrie"
             and secteur_naf("49.41A") == "Transport" and secteur_naf("62.01Z") == "Numérique",
             "secteurs tirés des codes d'activité")


def essai_collecte():
    print("Tri des annonces du BODACC")
    annonces = lire_json(RACINE / "essais" / "bodacc_exemple.json", [])
    reglages = {"effectif_minimum": "01", "inclure_liquidations": True, "personnes_morales_seulement": True}
    retenues, vus = collecte.traiter(annonces, set(), reglages, dt.date(2026, 10, 6),
                                     enrichir=lambda siren: ANNUAIRE_FICTIF.get(siren, {}), pause=0)
    par_id = {f["id"][-4:]: f for f in retenues}
    verifier(sorted(par_id) == ["0001", "0002", "0007", "0011"],
             f"4 annonces retenues sur {len(annonces)} : {sorted(par_id)}")
    un = par_id.get("0001", {})
    verifier(un.get("type") == "rj" and un.get("aj") is True, "redressement avec administrateur reconnu")
    verifier(un.get("ville") == "Saint-Priest" and un.get("siren") == "111222333", "ville et SIREN lus")
    verifier(un.get("secteur") == "Industrie" and un.get("effectif") == "12", "activité et effectif ajoutés")
    verifier(len(un.get("texte", "")) <= 360 and un.get("texte", "").endswith("…"), "texte du jugement abrégé")
    verifier(un.get("date") == "2026-09-30" and un.get("ajoute") == "2026-10-06", "dates du jugement et d'ajout")
    sept = par_id.get("0007", {})
    verifier(sept.get("type") == "conv" and sept.get("aj") is False,
             "conversion en liquidation : la fin de mission de l'administrateur n'est pas prise pour une désignation")
    onze = par_id.get("0011", {})
    verifier(onze.get("region") == "Outre-mer" and onze.get("ville") == "Les Abymes"
             and onze.get("siren") == "131313131", "outre-mer, ville et SIREN au format texte")
    verifier("forme" not in un and "morale" not in un, "champs de travail retirés du résultat")
    encore, _ = collecte.traiter(annonces, set(vus), reglages, dt.date(2026, 10, 7),
                                 enrichir=lambda siren: ANNUAIRE_FICTIF.get(siren, {}), pause=0)
    verifier(encore == [], "une annonce déjà vue n'est pas reprise")
    stricts = dict(reglages, effectif_minimum="11")
    gros, _ = collecte.traiter(annonces, set(), stricts, dt.date(2026, 10, 6),
                               enrichir=lambda siren: ANNUAIRE_FICTIF.get(siren, {}), pause=0)
    verifier(sorted(f["id"][-4:] for f in gros) == ["0001", "0007"], "seuil d'effectif relevé à 10 salariés")
    sans_lj = dict(reglages, inclure_liquidations=False)
    rj, _ = collecte.traiter(annonces, set(), sans_lj, dt.date(2026, 10, 6),
                             enrichir=lambda siren: ANNUAIRE_FICTIF.get(siren, {}), pause=0)
    verifier(sorted(f["id"][-4:] for f in rj) == ["0001", "0011"], "liquidations écartées sur demande")
    return retenues


def essai_requetes():
    print("Dialogue avec le BODACC (simulé)")
    lot = lire_json(RACINE / "essais" / "bodacc_exemple.json", [])
    jour = dt.date(2026, 10, 5)
    appels = []
    origine = (collecte.appel, collecte._filtre_valide)

    def export_direct(url, essais=4):
        appels.append(url)
        return lot
    collecte.appel, collecte._filtre_valide = export_direct, None
    verifier(len(collecte.annonces_du_jour(jour)) == len(lot) and "/exports/json?" in appels[0]
             and "familleavis" in appels[0] and "2026-10-05" in appels[0], "export complet en une requête")

    def par_pages(url, essais=4):
        appels.append(url)
        if "/exports/" in url:
            raise RuntimeError("export indisponible")
        debut = int(url.split("offset=")[1].split("&")[0])
        return {"results": (lot * 20)[debut:debut + 100]}
    appels.clear()
    collecte.appel, collecte._filtre_valide = par_pages, None
    verifier(len(collecte.annonces_du_jour(jour)) == len(lot) * 20, "à défaut, lecture page par page")

    def second_filtre(url, essais=4):
        appels.append(url)
        if "date%27" in url and "%3E%3D" not in url:
            raise RuntimeError("écriture refusée")
        return lot
    appels.clear()
    collecte.appel, collecte._filtre_valide = second_filtre, None
    collecte.annonces_du_jour(jour)
    avant = len(appels)
    collecte.annonces_du_jour(jour)
    verifier(avant == 3 and len(appels) == avant + 1, "l'écriture acceptée par l'API est retenue pour la suite")

    def panne(url, essais=4):
        raise RuntimeError("serveur muet")
    collecte.appel, collecte._filtre_valide = panne, None
    try:
        collecte.annonces_du_jour(jour)
        verifier(False, "panne du BODACC signalée")
    except RuntimeError:
        verifier(True, "panne du BODACC signalée")
    collecte.appel, collecte._filtre_valide = origine

    # Collecte complète, deux jours de suite, dans un répertoire provisoire.
    provisoire = Path(tempfile.mkdtemp())
    sauvegarde = (collecte.DONNEES, collecte.annonces_du_jour, collecte.annuaire, collecte.PAUSE)
    collecte.DONNEES = provisoire
    collecte.annonces_du_jour = lambda j: lot if j == jour else []
    collecte.annuaire = lambda siren: ANNUAIRE_FICTIF.get(siren, {})
    collecte.PAUSE = 0
    try:
        import contextlib
        import io
        with contextlib.redirect_stdout(io.StringIO()):
            collecte.principal(aujourdhui=dt.date(2026, 10, 6))
            premier = lire_json(provisoire / "procedures.json", [])
            collecte.principal(aujourdhui=dt.date(2026, 10, 7))
            second = lire_json(provisoire / "procedures.json", [])
            collecte.principal(aujourdhui=dt.date(2026, 12, 15))
            tardif = lire_json(provisoire / "procedures.json", [])
        etat = lire_json(provisoire / "etat.json", {})
        verifier(len(premier) == 4 and len(second) == 4, "collecte : 4 procédures, sans doublon le lendemain")
        verifier(etat.get("derniere_parution") == "2026-10-05", "collecte : dernière parution mémorisée")
        verifier(tardif == [], "collecte : les procédures de plus de 45 jours sont retirées")
    finally:
        collecte.DONNEES, collecte.annonces_du_jour, collecte.annuaire, collecte.PAUSE = sauvegarde
        shutil.rmtree(provisoire, ignore_errors=True)


def essai_alertes(procedures, dossiers, cfg):
    print("Alertes")
    contacts = [c for c in lire_json(RACINE / "essais" / "contacts_exemple.json", []) if not c["emailBlacklisted"]]
    c = alertes.lire_criteres("secteurs=Industrie|Commerce;regions=Bretagne;tailles=pme|eti;rythme=weekly;aj=1")
    verifier(c == {"secteurs": ["Industrie", "Commerce"], "regions": ["Bretagne"], "tailles": ["pme", "eti"],
                   "rythme": "weekly", "aj": True}, "lecture des critères d'un inscrit")
    verifier(alertes.lire_criteres(None)["rythme"] == "now", "critères absents : tout, dès la parution")

    mardi, vendredi = dt.date(2026, 10, 6), dt.date(2026, 10, 9)
    envois = {email: (o, p) for email, o, p in alertes.preparer(contacts, dossiers, procedures, {}, mardi)}
    verifier(set(envois) == {"tout@exemple.invalid", "industrie-aura@exemple.invalid",
                             "avec-aj@exemple.invalid", "sans-critere@exemple.invalid"},
             f"un mardi : {sorted(envois)}")
    verifier(len(envois["tout@exemple.invalid"][1]) == 4, "sans critère : les 4 procédures")
    verifier([p["id"][-4:] for p in envois["industrie-aura@exemple.invalid"][1]] == ["0001"],
             "Industrie en Auvergne-Rhône-Alpes : 1 procédure")
    verifier([p["id"][-4:] for p in envois["avec-aj@exemple.invalid"][1]] == ["0001"],
             "avec administrateur seulement : 1 procédure")
    verifier("bretagne@exemple.invalid" not in envois, "Bretagne : rien à envoyer")

    etat = {}
    alertes.preparer(contacts, dossiers, procedures, etat, mardi)
    lendemain = alertes.preparer(contacts, dossiers, procedures, etat, mardi + dt.timedelta(days=1))
    verifier(lendemain == [], "le lendemain, sans nouveauté : aucun e-mail")
    du_vendredi = {email for email, _, _ in alertes.preparer(contacts, dossiers, procedures, etat, vendredi)}
    verifier(du_vendredi == {"vendredi@exemple.invalid"}, "le vendredi : la sélection de la semaine")

    cfg = dict(cfg, site=dict(cfg["site"], adresse="https://exemple.invalid/site"),
               alertes=dict(cfg["alertes"], url_desinscription="https://exemple.invalid/stop"))
    offres, ouvertes = envois["tout@exemple.invalid"]
    objet, corps, texte = alertes.composer(offres, ouvertes, cfg, 30)
    controle = Controle()
    controle.feed(corps)
    verifier(not controle.fautes and not controle.pile, "e-mail : balises équilibrées")
    verifier("https://exemple.invalid/stop" in corps and "https://exemple.invalid/stop" in texte,
             "e-mail : lien de désinscription présent")
    verifier(cfg["editeur"]["nom"] in corps and "ATELIERS FICTIFS DU PARC" in corps, "e-mail : éditeur et dossier cités")
    verifier("nouveaux dossiers" in objet, f"objet : « {objet} »")


def essai_site(procedures, dossiers, cfg):
    print("Construction du site")
    sortie = Path(tempfile.mkdtemp())
    try:
        avis, nombre, _ = construire.construire(sortie=sortie, aujourdhui=dt.date(2026, 10, 6), cfg=cfg,
                                                dossiers=dossiers, erreurs=[], procedures=procedures)
        pages = sorted(str(p.relative_to(sortie)) for p in sortie.rglob("*.html"))
        attendues = ["404.html", "alertes/index.html", "alertes/merci/index.html", "avocat/index.html",
                     "confidentialite/index.html", "dossiers/index.html", "index.html",
                     "mentions-legales/index.html"] + [f"dossiers/{d['slug']}/index.html" for d in dossiers]
        verifier(sorted(attendues) == pages, f"{len(pages)} pages produites")
        for page in pages:
            controle = Controle()
            controle.feed((sortie / page).read_text(encoding="utf-8"))
            verifier(not controle.fautes and not controle.pile,
                     f"{page} : balises équilibrées" + (f" ({controle.fautes[:2]})" if controle.fautes else ""))
        accueil = (sortie / "index.html").read_text(encoding="utf-8")
        verifier("Prochaines dates limites" in accueil and 'content="noindex, nofollow"' in accueil,
                 "accueil : dates limites affichées, site non référencé en phase d'essai")
        liste = (sortie / "dossiers" / "index.html").read_text(encoding="utf-8")
        verifier('data-secteur="Industrie"' in liste and 'data-taille="pme"' in liste, "liste : filtres renseignés")
        donnees = lire_json(sortie / "donnees" / "procedures.json", None)
        verifier(isinstance(donnees, list) and len(donnees) == len(procedures)
                 and "siren" not in donnees[0], "procédures publiées, sans champ inutile")
        vide = Path(tempfile.mkdtemp())
        construire.construire(sortie=vide, aujourdhui=dt.date(2026, 10, 6), cfg=cfg, dossiers=[], erreurs=[],
                              procedures=procedures)
        verifier("Dernières procédures ouvertes" in (vide / "index.html").read_text(encoding="utf-8"),
                 "sans appel d'offres, l'accueil montre les dernières procédures")
        shutil.rmtree(vide)
        public = dict(cfg, site=dict(cfg["site"], indexation=True))
        try:
            construire.construire(sortie=Path(tempfile.mkdtemp()), cfg=public, dossiers=dossiers, erreurs=[],
                                  procedures=procedures)
            verifier(False, "ouverture au public refusée tant que les mentions manquent")
        except SystemExit:
            verifier(True, "ouverture au public refusée tant que les mentions manquent")
        complet = dict(public, site=dict(public["site"], adresse="https://exemple.invalid/site"),
                       editeur=dict(cfg["editeur"], hebergeur="Hébergeur d'exemple", siret="000 000 000 00000"))
        ouvert = Path(tempfile.mkdtemp())
        avis, nombre, _ = construire.construire(sortie=ouvert, aujourdhui=dt.date(2026, 10, 6), cfg=complet,
                                                dossiers=dossiers, erreurs=[], procedures=procedures)
        verifier(nombre == 0 and "noindex" not in (ouvert / "index.html").read_text(encoding="utf-8"),
                 "site public : dossier d'exemple retiré, référencement autorisé")
        verifier('href="/site/style.css"' in (ouvert / "404.html").read_text(encoding="utf-8"),
                 "page 404 : liens depuis la racine du site")
        shutil.rmtree(ouvert)
    finally:
        shutil.rmtree(sortie, ignore_errors=True)


def essai_navigateur():
    print("Fonctions du navigateur")
    if shutil.which("node") is None:
        print("  (Node.js absent : essais du script du navigateur non lancés)")
        return
    resultat = subprocess.run(["node", str(RACINE / "essais" / "app.test.js")], capture_output=True, text=True)
    print(resultat.stdout.rstrip())
    verifier(resultat.returncode == 0, "script du navigateur" + (f" : {resultat.stderr[:300]}" if resultat.returncode else ""))


if __name__ == "__main__":
    reglages = charger_config()
    lus, _ = lire_dossiers()
    essai_classement()
    retenues = essai_collecte()
    essai_requetes()
    essai_alertes(retenues, lus, reglages)
    essai_site(retenues, lus, reglages)
    essai_navigateur()
    print()
    if ECHECS:
        print(f"{len(ECHECS)} essai(s) en échec.")
        sys.exit(1)
    print("Tous les essais passent.")
