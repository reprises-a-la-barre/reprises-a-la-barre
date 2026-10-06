"""Construit le site dans le répertoire public/ à partir des réglages et des données.

    python outils/construire.py

Le site est fait de pages fixes : aucun serveur à entretenir, aucune base de données.
"""
import datetime as dt
import html
import shutil
import sys
import urllib.parse
from pathlib import Path

from commun import (DONNEES, MOIS, MOIS_COURTS, RACINE, REGIONS, SECTEURS, TAILLES, charger_config,
                    date_longue, ecrire_json, jours_restants, lieu, lire_dossiers, lire_json,
                    sans_accents)

SORTIE = RACINE / "public"
e = html.escape

CHEVRON = ('<svg width="11" height="18" viewBox="0 0 11 18" fill="none" stroke="currentColor" '
           'stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">'
           '<path d="M9 2 2 9l7 7"></path></svg>')

FAVICON = ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64"><rect width="64" height="64" '
           'rx="14" fill="#12284C"/><rect x="16" y="40" width="32" height="4" fill="#C9A24B"/>'
           '<rect x="16" y="20" width="32" height="4" fill="#FFFFFF"/></svg>\n')

ETAPES_REPRISE = [
    ("L'annonce paraît", "L'administrateur judiciaire fixe une date limite de dépôt des offres. "
                         "Le délai se compte en semaines."),
    ("Vous accédez au dossier", "Contre un engagement de confidentialité, vous consultez les comptes, "
                                "les contrats et l'état du personnel."),
    ("Vous déposez une offre", "Elle fixe le périmètre repris, le prix, les emplois conservés et le "
                               "financement. Une fois déposée, elle ne peut plus qu'être améliorée."),
    ("Le tribunal choisit", "Il retient l'offre qui assure le mieux l'emploi, le paiement des "
                            "créanciers et les garanties d'exécution."),
]

ETAPES_AVOCAT = [
    ("Lire le dossier", "Comptes, contrats, baux, état du personnel : ce que vous achetez vraiment, "
                        "et ce qui restera à votre charge."),
    ("Construire l'offre", "Périmètre, prix, emplois repris, contrats transférés, financement : "
                           "chaque ligne sera lue par le tribunal."),
    ("Déposer, puis améliorer", "L'offre est remise à l'administrateur judiciaire avant la date limite. "
                                "Elle peut ensuite être améliorée, jamais retirée."),
    ("Défendre l'offre à l'audience", "L'avocat présente votre offre devant le tribunal et répond aux "
                                      "questions qu'elle soulève."),
    ("Sécuriser l'entrée en jouissance", "Après le jugement, les actes de cession restent à rédiger "
                                         "et à signer."),
]

REGLES = [
    ("Un seul candidat par dossier", "L'avocat qui vous accompagne sur un dossier n'y conseille "
                                     "aucun autre candidat."),
    ("Les honoraires fixés avant de commencer", "Une convention d'honoraires est signée avant toute "
                                                "intervention. Vous savez ce que vous engagez."),
    ("Aucun démarchage", "S'inscrire aux alertes ne déclenche aucun appel. Si un dossier vous "
                         "intéresse, c'est vous qui prenez contact."),
]


# ---------------------------------------------------------------------------
# Éléments communs
# ---------------------------------------------------------------------------

def gabarit(cfg, titre, corps, racine, courant="", description=""):
    site, editeur = cfg["site"], cfg["editeur"]
    nom = e(site["nom"])
    titre_complet = f"{e(titre)} | {nom}" if titre else nom
    robots = "" if site.get("indexation") else '<meta name="robots" content="noindex, nofollow">\n'
    liens = []
    for chemin, libelle, cle in (("dossiers/", "Dossiers", "dossiers"), ("alertes/", "Alertes", "alertes"),
                                 ("avocat/", "L'avocat", "avocat")):
        actif = ' aria-current="page"' if courant == cle else ""
        liens.append(f'<a href="{racine}{chemin}"{actif}>{e(libelle)}</a>')
    navigation = "\n".join(liens)
    resume = e(description or site["description"])
    return f"""<!doctype html>
<html lang="fr">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{titre_complet}</title>
<meta name="description" content="{resume}">
{robots}<link rel="icon" type="image/svg+xml" href="{racine}favicon.svg">
<link rel="stylesheet" href="{racine}style.css">
</head>
<body data-racine="{racine}">
<a class="aller-contenu" href="#contenu">Aller au contenu</a>
<header class="entete"><div class="conteneur">
<a class="marque" href="{racine}"><span class="marque__nom">{nom}</span><span class="marque__barre"></span></a>
<nav class="nav" aria-label="Navigation principale">
{navigation}
</nav>
</div></header>
<main id="contenu">
{corps}
</main>
<footer class="pied"><div class="conteneur"><div class="pied__contenu">
<div class="pied__identite"><span class="pied__nom">{nom}</span><span>Un service édité par {e(editeur["nom"])}, {e(editeur["qualite"])}.</span><span>{e(editeur["adresse"])}</span></div>
<nav class="pied__liens" aria-label="Informations légales"><a href="{racine}mentions-legales/">Mentions légales</a><a href="{racine}confidentialite/">Confidentialité</a></nav>
</div></div></footer>
<script src="{racine}app.js" defer></script>
</body>
</html>
"""


def vignette(jour, neutre=False):
    classe = "vignette vignette--neutre" if neutre else "vignette"
    return (f'<span class="{classe}"><span class="vignette__jour">{jour.day}</span>'
            f'<span class="vignette__mois">{MOIS_COURTS[jour.month - 1]}</span></span>')


def etapes(liste):
    lignes = []
    for rang, (titre, texte) in enumerate(liste, 1):
        lignes.append(f'<li class="etape"><span class="numero">{rang}</span><div class="etape__texte">'
                      f'<h3 class="titre-ligne">{e(titre)}</h3><p>{e(texte)}</p></div></li>')
    return '<ol class="carte duo__liste">\n' + "\n".join(lignes) + "\n</ol>"


def panneau_alertes(racine, phrase, niveau="titre-section"):
    return (f'<div class="panneau panneau--ligne"><h2 class="{niveau}">{e(phrase)}</h2>'
            f'<a class="bouton bouton--or" href="{racine}alertes/">Recevoir les alertes</a></div>')


def majuscule(texte):
    return texte[:1].upper() + texte[1:]


# ---------------------------------------------------------------------------
# Accueil
# ---------------------------------------------------------------------------

def page_accueil(cfg, ouverts, procedures, aujourdhui):
    site = cfg["site"]
    if ouverts:
        titre_carte, pied, lignes = "Prochaines dates limites", ("dossiers/", "Tous les dossiers"), []
        for d in ouverts[:4]:
            reste = (d["date_limite"] - aujourdhui).days
            proche = " ligne__echeance--proche" if reste <= 7 else ""
            precision = ", ".join(x for x in (d["ville"], d["procedure"].lower()) if x)
            lignes.append(
                f'<a class="ligne" href="dossiers/{d["slug"]}/">{vignette(d["date_limite"])}'
                f'<span class="ligne__principal"><span class="ligne__titre">{e(d["titre"])}</span>'
                f'<span class="ligne__lieu">{e(precision)}</span></span>'
                f'<span class="ligne__echeance{proche}" data-echeance="{d["date_limite"].isoformat()}" '
                f'data-format="court">{e(jours_restants(d["date_limite"], aujourdhui).replace("dans ", ""))}</span></a>')
    elif procedures:
        titre_carte, pied, lignes = "Dernières procédures ouvertes", ("dossiers/#procedures", "Toutes les procédures"), []
        for p in procedures[:4]:
            jour = dt.date.fromisoformat(p["date"])
            nature = {"rj": "redressement judiciaire", "lj": "liquidation judiciaire",
                      "conv": "conversion en liquidation"}.get(p["type"], "")
            precision = ", ".join(x for x in (p.get("ville", ""), nature) if x)
            lignes.append(
                f'<a class="ligne" href="dossiers/#procedures">{vignette(jour, neutre=True)}'
                f'<span class="ligne__principal"><span class="ligne__titre">{e(p["nom"])}</span>'
                f'<span class="ligne__lieu">{e(precision)}</span></span></a>')
    else:
        titre_carte, pied = "Prochaines dates limites", ("alertes/", "Recevoir les alertes")
        lignes = ['<p class="element second">Les premiers dossiers arrivent. Créez une alerte pour être prévenu.</p>']

    carte = (f'<div class="carte"><h2 class="carte__titre">{titre_carte}</h2>\n' + "\n".join(lignes) +
             f'\n<a class="carte__pied" href="{pied[0]}">{pied[1]}</a></div>')
    note = ""
    if any(d["exemple"] for d in ouverts[:4]):
        note = '<p class="note">Dossier fictif, fourni à titre d\'exemple.</p>'

    corps = f"""<section class="hero"><div class="conteneur hero__grille">
<div class="hero__texte">
<h1 class="titre-page titre-page--grand">{e(site["accroche"])}</h1>
<p class="chapeau">{e(site["description"])}</p>
<div class="actions"><a class="bouton" href="alertes/">Recevoir les alertes</a><a class="lien-action" href="dossiers/">Parcourir les dossiers</a></div>
<p class="second petit">Gratuit, sans abonnement.</p>
</div>
<div class="hero__carte">
{carte}
{note}
</div>
</div></section>

<section class="bloc"><div class="conteneur duo">
<div class="duo__texte">
<h2 class="titre-section">De l'annonce au jugement</h2>
<p class="sous-titre">Une reprise à la barre suit un calendrier court. Un avocat sert dès la deuxième étape.</p>
<a class="lien-action" href="avocat/">Voir l'accompagnement</a>
</div>
{etapes(ETAPES_REPRISE)}
</div></section>

<section class="bloc"><div class="conteneur grille">
<div class="carte carte--texte">
<h2 class="titre-bloc">D'où viennent les dossiers</h2>
<p class="second">Les procédures ouvertes viennent du BODACC, le bulletin officiel des annonces commerciales. Les appels d'offres viennent des annonces des administrateurs et mandataires judiciaires : chaque fiche renvoie à l'annonce d'origine, et le dossier complet reste entre les mains du mandataire de justice.</p>
</div>
<div class="carte carte--texte">
<h2 class="titre-bloc">Un avocat derrière chaque fiche</h2>
<p class="second">Chaque appel d'offres est lu par un avocat, qui accompagne les repreneurs de la lecture du dossier à l'audience. Un seul candidat par dossier.</p>
<a class="lien-action" href="avocat/">Voir l'avocat</a>
</div>
</div></section>

<section class="bloc"><div class="conteneur">
{panneau_alertes("", "Un dossier dans votre secteur ? Soyez prévenu le jour de sa parution.")}
</div></section>"""
    return gabarit(cfg, "", corps, "./")


# ---------------------------------------------------------------------------
# Liste des dossiers
# ---------------------------------------------------------------------------

def pastilles(nom, general, valeurs, attribut="data-filtre", libelles=None):
    boutons = [f'<button type="button" class="pastille" data-valeur="" aria-pressed="true">{e(general)}</button>']
    for valeur in valeurs:
        libelle = libelles[valeur] if libelles else valeur
        boutons.append(f'<button type="button" class="pastille" data-valeur="{e(valeur)}" '
                       f'aria-pressed="false">{e(libelle)}</button>')
    return f'<div class="pastilles" {attribut}="{nom}">\n' + "\n".join(boutons) + "\n</div>"


def page_dossiers(cfg, ouverts, procedures, aujourdhui):
    lignes = []
    for d in ouverts:
        endroit = ", ".join(x for x in (lieu(d["ville"], d["departement"]), d["tribunal"]) if x)
        effectif = f'{d["effectif"]} salariés' if d["effectif"] is not None else "Effectif non communiqué"
        chiffre = f'Chiffre d\'affaires de {d["chiffre_affaires"]}' if d["chiffre_affaires"] else ""
        botte = " ".join([d["titre"], d["ville"], d["departement"], d["region"], d["secteur"],
                          d["tribunal"], d["procedure"]])
        exemple = ' <span class="etiquette">Exemple</span>' if d["exemple"] else ""
        lignes.append(
            f'<a class="ligne ligne--large" href="{d["slug"]}/" data-secteur="{e(d["secteur"])}" '
            f'data-taille="{d["taille"]}" data-region="{e(d["region"])}" data-texte="{e(botte)}">'
            f'{vignette(d["date_limite"])}'
            f'<span class="ligne__principal"><span class="ligne__titre">{e(d["titre"])}{exemple}</span>'
            f'<span class="ligne__lieu">{e(endroit)}</span></span>'
            f'<span class="ligne__colonne"><span>{e(effectif)}</span><span class="second">{e(chiffre)}</span></span>'
            f'<span class="ligne__colonne"><span>{e(d["procedure"])}</span>'
            f'<span class="ligne__echeance" data-echeance="{d["date_limite"].isoformat()}" data-majuscule="1">'
            f'{e(majuscule(jours_restants(d["date_limite"], aujourdhui)))}</span></span></a>')
    regions = "\n".join(f'<option value="{e(r)}">{e(r)}</option>' for r in REGIONS)
    jours = int(cfg["collecte"].get("jours_conserves", 45))

    corps = f"""<div class="conteneur page" id="page-dossiers">
<div class="page__tete">
<h1 class="titre-page">Dossiers ouverts</h1>
<p class="sous-titre" id="explication-offres">Entreprises et fonds de commerce pour lesquels un appel d'offres est ouvert. La date affichée est la date limite de dépôt des offres.</p>
<p class="sous-titre" id="explication-procedures" hidden>Sociétés entrées en redressement ou en liquidation judiciaire depuis {jours} jours, d'après le BODACC. Dès l'ouverture d'un redressement, un tiers peut soumettre une offre de reprise à l'administrateur. La date affichée est celle du jugement.</p>
</div>

<div class="segments" role="group" aria-label="Type de dossiers">
<button type="button" class="segment" data-vue="offres" aria-pressed="true">Appels d'offres <span class="segment__nombre">{len(ouverts)}</span></button>
<button type="button" class="segment" data-vue="procedures" aria-pressed="false">Procédures ouvertes <span class="segment__nombre" data-nombre="procedures">{len(procedures)}</span></button>
</div>

<div class="filtres">
<div class="champ-bloc"><label for="q">Rechercher</label>
<input class="champ" id="q" type="search" placeholder="Activité, société, ville ou région" autocomplete="off"></div>
<fieldset><legend>Secteur</legend>
{pastilles("secteur", "Tous les secteurs", SECTEURS)}
</fieldset>
<fieldset><legend>Taille</legend>
{pastilles("taille", "Toutes les tailles", list(TAILLES), libelles=TAILLES)}
</fieldset>
<div class="filtres__ligne">
<div class="champ-bloc"><label for="region">Région</label>
<select class="champ" id="region"><option value="">France entière</option>
{regions}
</select></div>
<label class="case" id="case-aj" hidden><input type="checkbox" id="aj"><span>Avec administrateur judiciaire</span></label>
</div>
</div>

<div class="resultats">
<div class="resultats__tete"><p id="compte" aria-live="polite">{len(ouverts)} appels d'offres ouverts</p>
<button type="button" class="bouton-texte" id="effacer" hidden>Effacer les critères</button></div>
<div class="carte" id="vue-offres">
{chr(10).join(lignes)}
<div class="vide"{"" if not ouverts else " hidden"}>
<p class="titre-bloc">Aucun appel d'offres ne correspond pour l'instant.</p>
<p class="second">Créez une alerte : vous serez prévenu le jour où un dossier paraît.</p>
<a class="bouton" href="../alertes/">Recevoir les alertes</a>
</div>
</div>
<div class="carte" id="vue-procedures" hidden>
<ul id="liste-procedures"></ul>
<div class="vide" hidden>
<p class="titre-bloc">Aucune procédure ne correspond à ces critères.</p>
<p class="second">Élargissez la recherche, ou créez une alerte.</p>
<a class="bouton" href="../alertes/">Recevoir les alertes</a>
</div>
<button type="button" class="carte__pied" id="plus" hidden>Afficher plus</button>
<noscript><p class="element second">La liste des procédures demande JavaScript.</p></noscript>
</div>
</div>

{panneau_alertes("../", "Les nouveaux dossiers par e-mail, selon vos critères.", "titre-bloc")}
</div>"""
    return gabarit(cfg, "Dossiers ouverts", corps, "../", "dossiers",
                   "Appels d'offres et procédures collectives ouvertes : entreprises et fonds de commerce à reprendre.")


# ---------------------------------------------------------------------------
# Fiche d'un appel d'offres
# ---------------------------------------------------------------------------

def page_fiche(cfg, d, aujourdhui):
    passe = d["date_limite"] < aujourdhui
    situation = ". ".join(x for x in (lieu(d["ville"], d["departement"]),
                                      f'{d["procedure"]}, {d["tribunal"]}' if d["tribunal"] else d["procedure"]) if x)
    blocs = []
    if d["a_vendre"]:
        lots = "\n".join(f'<li class="element">{e(lot)}</li>' for lot in d["a_vendre"])
        blocs.append(f'<section class="pile"><h2 class="titre-bloc">Ce qui est à vendre</h2>\n'
                     f'<ul class="carte">\n{lots}\n</ul></section>')
    if d["lecture"]:
        points = "\n".join(f'<div class="element element--point"><h3 class="titre-ligne">{e(p["titre"])}</h3>'
                           f'<p>{e(p["texte"])}</p></div>' for p in d["lecture"])
        blocs.append(f'<section class="pile"><h2 class="titre-bloc">La lecture de l\'avocat</h2>\n'
                     f'<div class="carte">\n{points}\n</div></section>')
    heure = f', à {d["heure_limite"]}' if d["heure_limite"] else ""
    audience = d["audience"] or "Date fixée par le tribunal"
    blocs.append(f"""<section class="pile"><h2 class="titre-bloc">Calendrier</h2>
<dl class="definitions">
<div><dt>Dépôt des offres</dt><dd>Au plus tard le {e(date_longue(d["date_limite"]))}{e(heure)}</dd></div>
<div><dt>Audience d'examen des offres</dt><dd>{e(audience)}</dd></div>
<div><dt>Entrée en jouissance</dt><dd>Fixée par le jugement qui arrête le plan</dd></div>
</dl></section>""")
    source = "Le dossier complet se demande à l'étude, contre engagement de confidentialité."
    if d["etude"]:
        source = f'Source : annonce de {d["etude"]}. ' + source
    lien = (f' <a href="{e(d["lien"])}" target="_blank" rel="noopener">Voir l\'annonce d\'origine</a>'
            if d["lien"].startswith("http") else "")
    blocs.append(f'<p class="note" id="source">{e(source)}{lien}</p>')

    chiffres = []
    if d["effectif"] is not None:
        chiffres.append(("Effectif", f'{d["effectif"]} salariés'))
    if d["chiffre_affaires"]:
        chiffres.append(("Chiffre d'affaires", d["chiffre_affaires"]))
    if d["procedure"]:
        chiffres.append(("Procédure", d["procedure"]))
    if d["etude"]:
        chiffres.append(("Mandataire", d["etude"]))
    lignes = "\n".join(f"<div><dt>{e(a)}</dt><dd>{e(b)}</dd></div>" for a, b in chiffres)
    precision = majuscule(date_longue(d["date_limite"]).split(" ")[0]) + heure
    notes = []
    if passe:
        notes.append('<p class="bandeau">La date limite de dépôt des offres est passée.</p>')
    if d["exemple"]:
        notes.append('<p class="note">Dossier fictif, fourni à titre d\'exemple.</p>')

    corps = f"""<div class="conteneur page">
<a class="lien-action retour" href="../">{CHEVRON}<span>Dossiers</span></a>
<div class="page__tete">
<h1 class="titre-page">{e(d["titre"])}</h1>
<p class="sous-titre">{e(situation)}.</p>
{chr(10).join(notes)}
</div>
<div class="fiche">
<div class="fiche__principal">
{chr(10).join(blocs)}
</div>
<aside class="fiche__panneau">
<div class="echeance">
<span class="echeance__libelle">Date limite de dépôt des offres</span>
<div class="echeance__date"><span class="echeance__jour">{d["date_limite"].day}</span><span class="echeance__mois">{MOIS[d["date_limite"].month - 1]} {d["date_limite"].year}</span></div>
<span class="echeance__precision">{e(precision)}</span>
<span class="echeance__reste" data-echeance="{d["date_limite"].isoformat()}" data-majuscule="1">{e(majuscule(jours_restants(d["date_limite"], aujourdhui)))}</span>
</div>
<dl class="chiffres">
{lignes}
</dl>
<div class="pile">
<a class="bouton bouton--or bouton--large" href="../../avocat/#contact">Contacter l'avocat</a>
<a class="bouton bouton--contour bouton--large" href="../../alertes/">Recevoir les alertes</a>
</div>
<p class="note">Un seul candidat accompagné par dossier.</p>
</aside>
</div>
</div>"""
    resume = f'{d["titre"]} : {situation}. Offres à déposer au plus tard le {date_longue(d["date_limite"])}.'
    return gabarit(cfg, d["titre"], corps, "../../", "dossiers", resume)


# ---------------------------------------------------------------------------
# Alertes
# ---------------------------------------------------------------------------

def page_alertes(cfg):
    alertes = cfg["alertes"]
    pret = bool(alertes.get("url_formulaire"))
    action = f' action="{e(alertes["url_formulaire"])}"' if pret else ""
    attente = "" if pret else '<p class="bandeau">Les inscriptions ouvriront bientôt.</p>'
    rythmes = ('<div class="pastilles" data-choix="rythme" data-unique>\n'
               '<button type="button" class="pastille" data-valeur="now" aria-pressed="true">Dès la parution d\'un dossier</button>\n'
               '<button type="button" class="pastille" data-valeur="weekly" aria-pressed="false">Chaque vendredi, la sélection de la semaine</button>\n'
               '</div>')
    corps = f"""<div class="conteneur page">
<div class="page__tete">
<h1 class="titre-page">Soyez prévenu le jour où un dossier paraît.</h1>
<p class="sous-titre">Indiquez vos critères : vous recevez les dossiers qui y correspondent, et rien d'autre. Gratuit, sans abonnement.</p>
</div>
<div class="formulaire-zone">
<form class="formulaire" id="alerte" method="post"{action} data-pret="{"1" if pret else "0"}" novalidate>
{attente}
<div class="champ-bloc"><label for="email">Votre adresse e-mail</label>
<input class="champ" id="email" name="EMAIL" type="email" placeholder="nom@entreprise.fr" autocomplete="email" required></div>
<fieldset><legend>Secteurs</legend>
{pastilles("secteurs", "Tous les secteurs", SECTEURS, "data-choix")}
</fieldset>
<fieldset><legend>Régions</legend>
{pastilles("regions", "France entière", REGIONS, "data-choix")}
</fieldset>
<fieldset><legend>Taille</legend>
{pastilles("tailles", "Toutes les tailles", list(TAILLES), "data-choix", TAILLES)}
</fieldset>
<fieldset><legend>Rythme</legend>
{rythmes}
</fieldset>
<label class="case"><input type="checkbox" id="alerte-aj"><span>Parmi les procédures ouvertes, seulement celles qui ont un administrateur judiciaire</span></label>
<label class="case case--encadree"><input type="checkbox" name="OPT_IN" value="1" required><span>J'accepte de recevoir par e-mail les alertes correspondant à mes critères. Je peux me désinscrire à tout moment.</span></label>
<input type="hidden" name="CRITERES" value="">
<input type="hidden" name="locale" value="fr">
<input class="piege" type="text" name="email_address_check" value="" tabindex="-1" autocomplete="off" aria-hidden="true">
<p class="erreur" id="erreur" role="alert" hidden></p>
<div><button type="submit" class="bouton">Créer mon alerte</button></div>
</form>
<aside class="formulaire__cote">
<div class="carte">
<h2 class="carte__titre">Ce que vous recevrez</h2>
<ul>
<li class="element">Un e-mail les jours où un dossier correspond, ou la sélection du vendredi</li>
<li class="element">Pour chaque appel d'offres : ce qui est à vendre, la date limite, la lecture de l'avocat</li>
<li class="element">Rien d'autre : ni lettre commerciale, ni appel</li>
</ul>
</div>
<p class="note">Votre adresse ne sert qu'à l'envoi des alertes. Elle n'est ni cédée ni partagée. <a href="../confidentialite/">En savoir plus</a></p>
</aside>
</div>
</div>"""
    return gabarit(cfg, "Recevoir les alertes", corps, "../", "alertes",
                   "Recevez par e-mail les entreprises à reprendre qui correspondent à vos critères.")


def page_merci(cfg):
    corps = """<div class="conteneur page">
<div class="page__tete">
<h1 class="titre-page">Encore une étape.</h1>
<p class="sous-titre">Un e-mail de confirmation vient de vous être envoyé. Cliquez sur le lien qu'il contient pour activer votre alerte. S'il n'arrive pas, regardez dans les courriers indésirables.</p>
</div>
<div class="actions"><a class="bouton" href="../../dossiers/">Parcourir les dossiers</a></div>
</div>"""
    return gabarit(cfg, "Confirmez votre adresse", corps, "../../", "alertes")


# ---------------------------------------------------------------------------
# L'avocat
# ---------------------------------------------------------------------------

def page_avocat(cfg, avec_photo):
    editeur = cfg["editeur"]
    photo = f'<img src="../photo.jpg" alt="{e(editeur["nom"])}" width="260" height="320">' if avec_photo else ""
    paragraphes = "\n".join(f"<p>{e(p)}</p>" for p in editeur.get("presentation", []))
    regles = "\n".join(f'<div class="regle"><h3>{e(t)}</h3><p>{e(x)}</p></div>' for t, x in REGLES)

    cartes = []
    honoraires = [("Premier avis sur un dossier", editeur.get("honoraires_premier_avis", "")),
                  ("Accompagnement jusqu'au jugement", editeur.get("honoraires_accompagnement", ""))]
    honoraires = [(a, b) for a, b in honoraires if b]
    if honoraires:
        lignes = "\n".join(f"<div><dt>{e(a)}</dt><dd>{e(b)}</dd></div>" for a, b in honoraires)
        cartes.append(f'<div class="pile"><h2 class="titre-bloc">Honoraires</h2>\n<dl class="definitions">\n{lignes}\n</dl></div>')
    contact = [("E-mail", editeur["email"])]
    if editeur.get("telephone"):
        contact.append(("Téléphone", editeur["telephone"]))
    contact.append(("Cabinet", editeur["adresse"]))
    lignes = "\n".join(f"<div><dt>{e(a)}</dt><dd>{e(b)}</dd></div>" for a, b in contact)
    civilite = "Me " + editeur["nom"].split(" ")[-1]
    cartes.append(f'<div class="pile" id="contact"><h2 class="titre-bloc">Contact</h2>\n'
                  f'<dl class="definitions">\n{lignes}\n</dl>\n'
                  f'<div><a class="bouton" href="mailto:{e(editeur["email"])}">Écrire à {e(civilite)}</a></div></div>')

    corps = f"""<div class="conteneur page page--aeree">
<section class="portrait">
{photo}
<div class="portrait__texte">
<div><h1 class="titre-page titre-page--grand">{e(editeur["nom"])}</h1>
<p class="portrait__qualite">{e(majuscule(editeur["qualite"]))}</p></div>
{paragraphes}
</div>
</section>

<section class="duo">
<div class="duo__texte">
<h2 class="titre-section">L'accompagnement d'un repreneur</h2>
<p class="sous-titre">De la première lecture du dossier à la signature des actes.</p>
</div>
{etapes(ETAPES_AVOCAT)}
</section>

<section class="panneau regles">
<h2 class="titre-section">Trois règles</h2>
<div class="regles__grille">
{regles}
</div>
</section>

<section class="grille grille--large">
{chr(10).join(cartes)}
</section>
</div>"""
    return gabarit(cfg, "L'avocat", corps, "../", "avocat",
                   f'{editeur["nom"]}, {editeur["qualite"]}, accompagne les repreneurs d\'entreprises en difficulté.')


# ---------------------------------------------------------------------------
# Pages de texte
# ---------------------------------------------------------------------------

def ou_manque(valeur, libelle):
    return e(valeur) if valeur else f'<span class="manque">[à compléter : {e(libelle)}]</span>'


def page_mentions(cfg):
    ed = cfg["editeur"]
    lignes = [f'{e(ed["nom"])}, {e(ed["qualite"])}', e(ed["adresse"]), f'E-mail : {e(ed["email"])}']
    if ed.get("telephone"):
        lignes.append(f'Téléphone : {e(ed["telephone"])}')
    lignes.append(f'SIRET : {ou_manque(ed.get("siret"), "SIRET")}')
    if ed.get("tva"):
        lignes.append(f'TVA intracommunautaire : {e(ed["tva"])}')
    corps = f"""<div class="conteneur page">
<div class="page__tete"><h1 class="titre-page">Mentions légales</h1></div>
<div class="prose">
<h2>Éditeur</h2>
<p>{"<br>".join(lignes)}</p>
<p>Directeur de la publication : {e(ed["nom"])}.</p>
<h2>Profession réglementée</h2>
<p>{e(ed["nom"])} est {e(ed["qualite"])}. Le titre d'avocat a été obtenu en France. La profession est régie notamment par la loi n° 71-1130 du 31 décembre 1971, le décret n° 2023-552 du 30 juin 2023 portant code de déontologie des avocats et le Règlement intérieur national de la profession d'avocat.</p>
<h2>Hébergeur</h2>
<p>{ou_manque(ed.get("hebergeur"), "nom et adresse de l'hébergeur")}</p>
<h2>Sources des informations</h2>
<p>Les procédures ouvertes proviennent du Bulletin officiel des annonces civiles et commerciales (BODACC), diffusé par la Direction de l'information légale et administrative sous Licence Ouverte, et de l'Annuaire des entreprises. Les appels d'offres renvoient à l'annonce d'origine de l'administrateur ou du mandataire judiciaire, seule à faire foi.</p>
<p>Les informations publiées sur ce site sont générales. Elles ne constituent pas une consultation juridique.</p>
</div>
</div>"""
    return gabarit(cfg, "Mentions légales", corps, "../")


def page_confidentialite(cfg):
    ed = cfg["editeur"]
    jours = int(cfg["collecte"].get("jours_conserves", 45))
    corps = f"""<div class="conteneur page">
<div class="page__tete"><h1 class="titre-page">Confidentialité</h1></div>
<div class="prose">
<p>Ce site ne dépose aucun cookie et n'utilise aucun outil de mesure d'audience.</p>
<h2>Si vous créez une alerte</h2>
<p>Votre adresse e-mail et vos critères (secteurs, régions, taille, rythme) sont enregistrés pour vous envoyer les dossiers correspondants, et pour rien d'autre. Ce traitement repose sur votre consentement, que vous retirez à tout moment par le lien de désinscription présent dans chaque e-mail.</p>
<p>Ces données sont confiées à Brevo, prestataire français d'envoi d'e-mails, qui agit pour le compte de l'éditeur. Elles ne sont ni cédées ni partagées. Elles sont conservées jusqu'à votre désinscription, puis supprimées.</p>
<h2>Vos droits</h2>
<p>Le responsable du traitement est {e(ed["nom"])}, {e(ed["qualite"])}, {e(ed["adresse"])}. Vous disposez d'un droit d'accès, de rectification, d'effacement et d'opposition, que vous exercez en écrivant à {e(ed["email"])}. Vous pouvez aussi saisir la CNIL.</p>
<h2>Les sociétés citées</h2>
<p>Les informations sur les sociétés en procédure collective proviennent du BODACC, publication légale diffusée par l'État sous licence ouverte. Seules des personnes morales sont affichées, pendant {jours} jours.</p>
<h2>Hébergement</h2>
<p>L'hébergeur du site conserve, pour des raisons techniques, des journaux de connexion.</p>
</div>
</div>"""
    return gabarit(cfg, "Confidentialité", corps, "../")


def page_introuvable(cfg):
    # La page 404 peut s'afficher à n'importe quelle profondeur : ses liens partent de la racine du site.
    chemin = urllib.parse.urlparse(cfg["site"].get("adresse") or "").path.rstrip("/") + "/"
    corps = f"""<div class="conteneur page">
<div class="page__tete"><h1 class="titre-page">Cette page n'existe pas.</h1>
<p class="sous-titre">Le dossier a peut-être été retiré après sa date limite.</p></div>
<div class="actions"><a class="bouton" href="{e(chemin)}">Revenir à l'accueil</a></div>
</div>"""
    return gabarit(cfg, "Page introuvable", corps, e(chemin))


# ---------------------------------------------------------------------------
# Construction
# ---------------------------------------------------------------------------

def ecrire(sortie, chemin, contenu):
    cible = Path(sortie) / chemin
    cible.parent.mkdir(parents=True, exist_ok=True)
    cible.write_text(contenu, encoding="utf-8")


def construire(sortie=SORTIE, aujourdhui=None, cfg=None, dossiers=None, erreurs=None, procedures=None):
    """Construit tout le site. Renvoie la liste des avertissements."""
    aujourdhui = aujourdhui or dt.date.today()
    cfg = cfg or charger_config()
    if dossiers is None:
        dossiers, erreurs = lire_dossiers()
    if procedures is None:
        procedures = lire_json(DONNEES / "procedures.json", [])
    avis = list(erreurs or [])
    public = bool(cfg["site"].get("indexation"))

    if public:
        manque = [nom for nom, valeur in (("editeur.hebergeur", cfg["editeur"].get("hebergeur")),
                                          ("editeur.siret", cfg["editeur"].get("siret")),
                                          ("site.adresse", cfg["site"].get("adresse"))) if not valeur]
        if manque:
            raise SystemExit("Le site est déclaré ouvert au public (indexation = true) mais il manque dans "
                             "config.toml : " + ", ".join(manque) + ".")
        exemples = [d["slug"] for d in dossiers if d["exemple"]]
        if exemples:
            avis.append("Dossiers d'exemple ignorés car le site est public : " + ", ".join(exemples) + ".")
        dossiers = [d for d in dossiers if not d["exemple"]]
    else:
        avis.append("Site en phase d'essai : les moteurs de recherche sont priés de ne pas le référencer "
                    "(indexation = false dans config.toml).")
        for nom, valeur in (("l'hébergeur", cfg["editeur"].get("hebergeur")),
                            ("le SIRET", cfg["editeur"].get("siret")),
                            ("l'adresse du site", cfg["site"].get("adresse"))):
            if not valeur:
                avis.append(f"À compléter dans config.toml avant l'ouverture au public : {nom}.")

    ouverts = [d for d in dossiers if d["date_limite"] >= aujourdhui]
    sortie = Path(sortie)
    if sortie.exists():
        shutil.rmtree(sortie)
    shutil.copytree(RACINE / "site", sortie)
    police = sortie / "polices" / "EBGaramond-VariableFont_wght.ttf"
    if not police.exists():
        avis.append("Police Garamond absente (site/polices/) : les titres s'affichent dans une police de secours.")
    avec_photo = (sortie / "photo.jpg").exists()

    ecrire(sortie, "favicon.svg", FAVICON)
    ecrire(sortie, "index.html", page_accueil(cfg, ouverts, procedures, aujourdhui))
    ecrire(sortie, "dossiers/index.html", page_dossiers(cfg, ouverts, procedures, aujourdhui))
    for d in dossiers:
        ecrire(sortie, f'dossiers/{d["slug"]}/index.html', page_fiche(cfg, d, aujourdhui))
    ecrire(sortie, "alertes/index.html", page_alertes(cfg))
    ecrire(sortie, "alertes/merci/index.html", page_merci(cfg))
    ecrire(sortie, "avocat/index.html", page_avocat(cfg, avec_photo))
    ecrire(sortie, "mentions-legales/index.html", page_mentions(cfg))
    ecrire(sortie, "confidentialite/index.html", page_confidentialite(cfg))
    ecrire(sortie, "404.html", page_introuvable(cfg))
    ecrire(sortie, "robots.txt", "User-agent: *\n" + ("Allow: /\n" if public else "Disallow: /\n"))
    ecrire(sortie, ".nojekyll", "")

    champs = ("id", "nom", "ville", "dept", "region", "tribunal", "type", "date", "aj", "texte", "url",
              "secteur", "effectif")
    ecrire_json(sortie / "donnees" / "procedures.json",
                [{c: p.get(c, "") for c in champs} for p in procedures], compact=True)
    return avis, len(ouverts), len(procedures)


if __name__ == "__main__":
    avertissements, nombre_offres, nombre_procedures = construire()
    for ligne in avertissements:
        print("ATTENTION :", ligne)
    print(f"Site construit dans public/ : appels d'offres ouverts : {nombre_offres}, "
          f"procédures affichées : {nombre_procedures}.")
    sys.exit(0)
