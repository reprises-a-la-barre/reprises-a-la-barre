# Reprises à la barre : mise en ligne pas à pas

Ce dossier contient le vrai site. Il ne demande ni serveur ni abonnement : il vit sur GitHub, qui le
reconstruit tout seul chaque matin. Coût : zéro, hors nom de domaine (dix à quinze euros par an, plus tard).

## Ce que fait le site

| Partie | Source | Mise à jour |
| --- | --- | --- |
| Procédures ouvertes (redressements et liquidations) | BODACC, complété par l'Annuaire des entreprises | Automatique, chaque matin |
| Appels d'offres avec date limite et lecture de l'avocat | Un fichier texte par dossier, écrit par toi | À la main |
| Alertes par e-mail selon les critères de chaque inscrit | Brevo | Automatique, chaque matin et le vendredi |

Le BODACC dit qui entre en procédure. Il ne donne ni la date limite de dépôt des offres ni le périmètre
à vendre : c'est pourquoi les appels d'offres restent saisis à la main, tant qu'aucun accord avec le
CNAJMJ ou les études ne fournit un flux.

## Ce qui a été essayé, et ce qui ne l'a pas été

Essayé ici, sur des données fictives : le tri des annonces, les filtres, les alertes, la construction des
pages, puis les pages elles-mêmes dans un navigateur (ordinateur et téléphone), filtres et formulaire compris.

**Pas encore essayé : le dialogue réel avec le BODACC, l'Annuaire des entreprises et Brevo.** L'endroit où
ce code a été écrit n'a pas accès à Internet. Le premier lancement (étape 4) est donc le vrai test. Si une
étape s'affiche en rouge, ouvre-la, copie les dernières lignes et envoie-les à Claude.

## Étape 1 : créer le dépôt

1. Créer un compte sur github.com.
2. Bouton **New repository**. Nom : `reprises-a-la-barre`. Visibilité : **Public** (condition de la
   gratuité). Ne rien cocher d'autre. Valider.
3. Le dépôt est public : n'importe qui peut en lire les fichiers. Aucun secret n'y figure ; la clé de Brevo
   se range ailleurs (étape 6).

## Étape 2 : activer l'hébergement

Dans le dépôt : **Settings**, puis **Pages**, puis sous « Build and deployment », **Source : GitHub Actions**.

## Étape 3 : déposer les fichiers

1. Sur la page du dépôt, lien **uploading an existing file**.
2. Glisser dans la fenêtre tout le contenu du dossier décompressé (le contenu, pas le dossier lui-même).
   Bouton **Commit changes**.
3. Le répertoire `.github` est caché sur la plupart des ordinateurs et ne suit pas toujours. Pour être sûr :
   **Add file**, **Create new file**, taper comme nom `.github/workflows/quotidien.yml`, y coller le contenu
   du fichier `flux-github/quotidien.yml`, puis **Commit changes**.

Une ou deux minutes plus tard, le site est en ligne à l'adresse
`https://TON-COMPTE.github.io/reprises-a-la-barre/`, avec le dossier d'exemple et aucune procédure.
L'onglet **Actions** montre l'avancement : une coche verte quand c'est fait.

Reporter cette adresse dans `config.toml`, ligne `adresse` (ouvrir le fichier, crayon en haut à droite,
modifier, **Commit changes**).

## Étape 4 : lancer la première collecte

Onglet **Actions**, **Mise à jour quotidienne**, bouton **Run workflow**. La première fois, le site relit
dix jours de BODACC : compter un quart d'heure à une demi-heure. Ensuite, tout se fait seul chaque matin.

Regarder le résultat de l'étape « Collecter les procédures au BODACC » : elle affiche, jour par jour,
le nombre d'annonces lues et retenues. C'est là que se voit un éventuel problème.

## Étape 5 : le quotidien

**Ajouter un appel d'offres.** Dans `donnees/dossiers/`, ouvrir `_modele.md` et en copier le contenu.
**Add file**, **Create new file**, nom sans espace ni accent finissant par `.md`
(exemple : `menuiserie-saint-priest.md`), coller, remplir, **Commit changes**. Le site se met à jour seul.
Seules les lignes `titre` et `date_limite` sont obligatoires. Passé sa date limite, le dossier quitte les
listes de lui-même.

**Retirer un dossier.** Ouvrir son fichier, menu « ... », **Delete file**.

**Régler le site.** Tout est dans `config.toml`, commenté ligne à ligne : textes, coordonnées, seuil de
taille des sociétés reprises du BODACC, durée d'affichage.

**Garamond.** Suivre `site/polices/LISEZMOI.txt`. Tant que le fichier manque, les titres s'affichent dans
une police de secours.

**Photo.** Déposer un portrait nommé `photo.jpg` dans `site/` : il apparaît sur la page « L'avocat ».

## Étape 6 : les alertes (à faire avec Claude)

Les écrans de Brevo changent souvent : si un nom diffère de ce qui suit, copie ce que tu vois à Claude.

1. Créer un compte gratuit sur brevo.com.
2. Dans les réglages des contacts, créer un **attribut de contact** de type texte nommé `CRITERES`.
3. Créer une **liste** de contacts (« Alertes ») et noter son numéro.
4. Créer un **formulaire d'inscription** avec confirmation par e-mail (double opt-in), relié à cette liste,
   avec trois champs : e-mail, `CRITERES`, case de consentement. Page d'arrivée après inscription :
   `ADRESSE-DU-SITE/alertes/merci/`.
5. Afficher le code HTML du formulaire et l'envoyer à Claude : il contient l'adresse d'envoi et le nom
   exact des champs, à reporter dans le site.
6. Créer un **formulaire de désinscription** et noter son adresse.
7. Valider l'adresse d'expédition des e-mails.
8. Créer une **clé API**. Dans GitHub : **Settings**, **Secrets and variables**, **Actions**,
   **New repository secret**, nom `BREVO_API_KEY`, valeur : la clé. Elle ne doit figurer nulle part ailleurs.
9. Dans `config.toml`, rubrique `[alertes]` : remplir les lignes, puis `actives = true`.

## Avant l'ouverture au public

Tant que `indexation = false`, le site demande aux moteurs de recherche de l'ignorer : c'est le bon réglage
jusqu'à l'avis de l'Ordre. Avant de passer à `true` :

- supprimer `donnees/dossiers/exemple-menuiserie.md` ;
- remplir dans `config.toml` le SIRET et l'hébergeur (pour GitHub Pages : GitHub, Inc., dont l'adresse
  postale est à relever sur son site) ;
- relire les pages « Mentions légales » et « Confidentialité », écrites comme des projets ;
- brancher le nom de domaine retenu : **Settings**, **Pages**, **Custom domain**.

Si ces mentions manquent, le site refuse de passer en mode public et le dit dans l'onglet Actions.

## Les garde-fous déjà en place

- Seules les personnes morales sont reprises du BODACC ; les entrepreneurs individuels sont écartés.
- Une procédure disparaît du site au bout de 45 jours.
- Aucun cookie, aucun traceur, aucune police chargée chez un tiers.
- Si le BODACC ne répond pas un matin, le site garde les données de la veille.

## Le contenu du dossier

| Fichier | Rôle |
| --- | --- |
| `config.toml` | Tous les réglages |
| `donnees/dossiers/` | Un fichier par appel d'offres |
| `donnees/procedures.json`, `donnees/etat.json` | Tenus par l'automate, ne pas modifier |
| `outils/collecte.py` | Lecture du BODACC |
| `outils/alertes.py` | Envoi des alertes |
| `outils/construire.py` | Fabrication des pages |
| `outils/essais.py`, `essais/` | Essais hors ligne |
| `site/` | Mise en forme et comportements des pages |
| `.github/workflows/quotidien.yml` | L'automate du matin |
