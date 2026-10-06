"""Envoi des alertes par e-mail, via Brevo.

Chaque inscrit a choisi ses critères sur le site ; ils sont rangés dans Brevo dans le champ
de contact CRITERES, sous la forme :
    secteurs=Industrie|Commerce;regions=Bretagne;tailles=pme|eti;rythme=now;aj=0

Rythme « now »    : un e-mail les jours où un nouveau dossier correspond.
Rythme « weekly » : un e-mail le vendredi, avec les dossiers de la semaine.

La clé Brevo n'est jamais écrite dans les fichiers : elle est lue dans la variable
d'environnement BREVO_API_KEY (un « secret » du dépôt GitHub).

    python outils/alertes.py            envoi réel
    python outils/alertes.py --essai    aucun envoi : affiche ce qui partirait
"""
import datetime as dt
import html
import json
import os
import sys
import urllib.error
import urllib.request

from commun import (DONNEES, RACINE, TRANCHES, TYPES, charger_config, date_longue, ecrire_json,
                    lieu, lire_dossiers, lire_json, taille_tranche)

BREVO = "https://api.brevo.com/v3"


def lire_criteres(texte):
    criteres = {"secteurs": [], "regions": [], "tailles": [], "rythme": "now", "aj": False}
    for bloc in str(texte or "").split(";"):
        if "=" not in bloc:
            continue
        cle, valeur = bloc.split("=", 1)
        cle = cle.strip().lower()
        valeurs = [v.strip() for v in valeur.split("|") if v.strip()]
        if cle in ("secteurs", "regions", "tailles"):
            criteres[cle] = valeurs
        elif cle == "rythme":
            criteres["rythme"] = "weekly" if "weekly" in valeurs else "now"
        elif cle == "aj":
            criteres["aj"] = valeurs == ["1"]
    return criteres


def convient(criteres, secteur, region, taille, avec_aj=True):
    if criteres["secteurs"] and secteur not in criteres["secteurs"]:
        return False
    if criteres["regions"] and region not in criteres["regions"]:
        return False
    if criteres["tailles"] and taille not in criteres["tailles"]:
        return False
    if criteres["aj"] and not avec_aj:
        return False
    return True


def selection(criteres, dossiers, procedures):
    """Les dossiers et procédures qui correspondent aux critères d'un inscrit."""
    offres = [d for d in dossiers if convient(criteres, d["secteur"], d["region"], d["taille"])]
    ouvertes = [p for p in procedures
                if convient(criteres, p.get("secteur", ""), p.get("region", ""),
                            taille_tranche(p.get("effectif", "")), bool(p.get("aj")))]
    return offres, ouvertes


def composer(offres, ouvertes, cfg, maximum):
    """Objet, version HTML et version texte d'un e-mail d'alerte."""
    e = html.escape
    site, editeur, alertes = cfg["site"], cfg["editeur"], cfg["alertes"]
    adresse = site["adresse"].rstrip("/")
    nombre = len(offres) + len(ouvertes)
    objet = (f"{nombre} nouveaux dossiers correspondent à vos critères" if nombre > 1
             else "Un nouveau dossier correspond à vos critères")
    lignes_html, lignes_texte = [], []
    style_titre = "font-family:Georgia,serif;font-size:20px;color:#12284C;margin:28px 0 8px"
    style_ligne = "padding:12px 0;border-top:1px solid #E4E7EE;font-size:15px;line-height:1.5;color:#12284C"
    gris = "color:#55627A"

    if offres:
        lignes_html.append(f'<h2 style="{style_titre}">Appels d\'offres</h2>')
        lignes_texte.append("APPELS D'OFFRES")
        for d in offres[:maximum]:
            lien = f"{adresse}/dossiers/{d['slug']}/"
            echeance = date_longue(d["date_limite"])
            lignes_html.append(
                f'<div style="{style_ligne}"><a href="{e(lien)}" style="color:#1D4E9E;font-weight:600;'
                f'text-decoration:none">{e(d["titre"])}</a><br>'
                f'<span style="{gris}">{e(lieu(d["ville"], d["departement"]))}. '
                f'Offres à déposer au plus tard le {e(echeance)}.</span></div>')
            lignes_texte.append(f"- {d['titre']}, {lieu(d['ville'], d['departement'])}. "
                                f"Date limite : {echeance}. {lien}")
    if ouvertes:
        lignes_html.append(f'<h2 style="{style_titre}">Procédures ouvertes</h2>')
        lignes_texte.append("PROCÉDURES OUVERTES")
        for p in ouvertes[:maximum]:
            precisions = [TYPES.get(p["type"], ""), TRANCHES.get(p.get("effectif", ""), ""),
                          p.get("secteur", "")]
            if p.get("aj"):
                precisions.append("administrateur judiciaire désigné")
            detail = ", ".join(x for x in precisions if x)
            lignes_html.append(
                f'<div style="{style_ligne}"><strong>{e(p["nom"])}</strong><br>'
                f'<span style="{gris}">{e(lieu(p.get("ville", ""), p.get("dept", "")))}. {e(detail)}.</span></div>')
            lignes_texte.append(f"- {p['nom']}, {lieu(p.get('ville', ''), p.get('dept', ''))}. {detail}.")
        reste = len(ouvertes) - maximum
        if reste > 0:
            lignes_html.append(f'<div style="{style_ligne};{gris}">Et {reste} autres sur le site.</div>')
            lignes_texte.append(f"Et {reste} autres sur le site.")

    pied = (f"{site['nom']} est un service édité par {editeur['nom']}, {editeur['qualite']}, "
            f"{editeur['adresse']}.")
    corps = (
        '<div style="max-width:600px;margin:0 auto;padding:24px;font-family:-apple-system,Segoe UI,'
        'Helvetica,Arial,sans-serif;background:#FFFFFF">'
        f'<p style="font-family:Georgia,serif;font-size:26px;color:#12284C;margin:0 0 4px">{e(site["nom"])}</p>'
        '<div style="width:36px;height:2px;background:#C9A24B"></div>'
        + "".join(lignes_html) +
        f'<p style="margin:28px 0 0"><a href="{e(adresse)}/dossiers/" style="display:inline-block;'
        'padding:14px 24px;background:#12284C;color:#FFFFFF;font-size:16px;font-weight:600;'
        'text-decoration:none;border-radius:12px">Voir tous les dossiers</a></p>'
        f'<p style="margin:32px 0 0;padding-top:16px;border-top:1px solid #E4E7EE;font-size:13px;'
        f'line-height:1.5;{gris}">{e(pied)}<br>Vous recevez cet e-mail parce que vous avez créé une '
        f'alerte sur le site. <a href="{e(alertes["url_desinscription"])}" style="color:#1D4E9E">'
        'Se désinscrire</a></p></div>')
    texte = "\n".join([site["nom"], ""] + lignes_texte + [
        "", f"Tous les dossiers : {adresse}/dossiers/", "", pied,
        f"Se désinscrire : {alertes['url_desinscription']}"])
    return objet, corps, texte


def brevo(methode, chemin, cle, donnees=None):
    corps = json.dumps(donnees).encode("utf-8") if donnees is not None else None
    requete = urllib.request.Request(BREVO + chemin, data=corps, method=methode, headers={
        "api-key": cle, "accept": "application/json", "content-type": "application/json"})
    with urllib.request.urlopen(requete, timeout=60) as reponse:
        contenu = reponse.read().decode("utf-8")
        return json.loads(contenu) if contenu.strip() else {}


def joignables(contacts):
    """Écarte les contacts sans adresse et ceux qui ont demandé à ne plus rien recevoir."""
    return [c for c in contacts if c.get("email") and not c.get("emailBlacklisted")]


def inscrits(cle, liste):
    """Tous les contacts de la liste Brevo qui n'ont pas demandé à ne plus recevoir d'e-mails."""
    contacts, debut = [], 0
    while True:
        page = brevo("GET", f"/contacts/lists/{liste}/contacts?limit=500&offset={debut}", cle)
        lot = page.get("contacts", [])
        contacts.extend(joignables(lot))
        debut += 500
        if len(lot) < 500:
            return contacts


def preparer(contacts, dossiers, procedures, etat, aujourdhui):
    """Pour chaque inscrit, ce qu'il doit recevoir aujourd'hui. Met à jour l'état des envois."""
    suivi = etat.setdefault("alertes", {})
    deja = set(suivi.get("dossiers_envoyes", []))
    hier = (aujourdhui - dt.timedelta(days=1)).isoformat()
    depuis_jour = suivi.get("quotidien", hier)
    depuis_semaine = suivi.get("hebdo", (aujourdhui - dt.timedelta(days=7)).isoformat())
    vendredi = aujourdhui.weekday() == 4

    ouverts = [d for d in dossiers if d["date_limite"] >= aujourdhui]
    offres_jour = [d for d in ouverts if d["slug"] not in deja]
    offres_semaine = [d for d in ouverts if d["slug"] not in set(suivi.get("dossiers_hebdo", []))]
    proc_jour = [p for p in procedures if p.get("ajoute", "") > depuis_jour]
    proc_semaine = [p for p in procedures if p.get("ajoute", "") > depuis_semaine]

    envois = []
    for contact in contacts:
        criteres = lire_criteres((contact.get("attributes") or {}).get("CRITERES"))
        if criteres["rythme"] == "weekly":
            if not vendredi:
                continue
            offres, ouvertes = selection(criteres, offres_semaine, proc_semaine)
        else:
            offres, ouvertes = selection(criteres, offres_jour, proc_jour)
        if offres or ouvertes:
            envois.append((contact["email"], offres, ouvertes))

    suivi["quotidien"] = aujourdhui.isoformat()
    suivi["dossiers_envoyes"] = sorted(deja | {d["slug"] for d in ouverts})
    if vendredi:
        suivi["hebdo"] = aujourdhui.isoformat()
        suivi["dossiers_hebdo"] = sorted({d["slug"] for d in ouverts})
    return envois


def principal(essai=False):
    cfg = charger_config()
    alertes = cfg["alertes"]
    aujourdhui = dt.date.today()
    dossiers, _ = lire_dossiers()
    procedures = lire_json(DONNEES / "procedures.json", [])
    etat = lire_json(DONNEES / "etat.json", {})

    if essai:
        contacts = joignables(lire_json(RACINE / "essais" / "contacts_exemple.json", []))
        cfg["site"]["adresse"] = cfg["site"]["adresse"] or "https://exemple.invalid"
    else:
        if not alertes.get("actives"):
            print("Alertes désactivées dans config.toml : rien à envoyer.")
            return
        manque = [nom for nom in ("expediteur_email", "url_desinscription") if not alertes.get(nom)]
        if not cfg["site"].get("adresse"):
            manque.append("site.adresse")
        if not alertes.get("liste_brevo"):
            manque.append("liste_brevo")
        cle = os.environ.get("BREVO_API_KEY", "")
        if not cle:
            manque.append("le secret BREVO_API_KEY")
        if manque:
            print("Alertes non envoyées, il manque : " + ", ".join(manque) + ".")
            return
        contacts = inscrits(cle, alertes["liste_brevo"])

    envois = preparer(contacts, dossiers, procedures, etat, aujourdhui)
    plafond = int(alertes.get("maximum_emails_par_jour", 280))
    partis = 0
    for email, offres, ouvertes in envois[:plafond]:
        objet, corps, texte = composer(offres, ouvertes, cfg, int(alertes.get("maximum_par_email", 30)))
        if essai:
            print(f"[essai] {email} : « {objet} » (appels d'offres : {len(offres)}, "
                  f"procédures : {len(ouvertes)})")
            partis += 1
            continue
        try:
            brevo("POST", "/smtp/email", cle, {
                "sender": {"name": alertes["expediteur_nom"], "email": alertes["expediteur_email"]},
                "to": [{"email": email}],
                "subject": objet, "htmlContent": corps, "textContent": texte})
            partis += 1
        except urllib.error.HTTPError as erreur:
            print(f"Envoi refusé par Brevo (code {erreur.code}) : {erreur.read()[:200]!r}")
        except urllib.error.URLError as erreur:
            print(f"Brevo injoignable : {erreur}")
    if len(envois) > plafond:
        print(f"Plafond quotidien atteint : {len(envois) - plafond} e-mails non envoyés.")
    if not essai:
        ecrire_json(DONNEES / "etat.json", etat)
    print(f"{len(contacts)} inscrits, {partis} e-mails {'simulés' if essai else 'envoyés'}.")


if __name__ == "__main__":
    principal(essai="--essai" in sys.argv)
