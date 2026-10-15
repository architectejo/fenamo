# Décisions de l'utilisateur dérogeant ou précisant les cahiers des charges

Ce fichier consigne les décisions explicites de l'utilisateur. Le cahier des charges n'est pas modifié.

## 2026-10-15 : identifiant et mot de passe initial d'un membre nommé (dérogation à F-02)

**F-02** prévoit un mot de passe temporaire aléatoire à changer à la première connexion.

**Décision de l'utilisateur** (prévenu du risque, il a choisi) : à la **nomination d'un membre** (`compte.services.nominations.nommer`, via
`comptes.creer_compte_pour_membre`), le nom d'utilisateur **et** le mot de passe initial sont tous deux `prenom[nombre]@fenamordc.hub` :

- prénom = premier mot du nom du membre, en minuscules ASCII, sans accents, espaces, apostrophes ni tirets (« Jean-Pierre » donne `jeanpierre`,
  « Élise » donne `elise`) ;
- nombre = 4 chiffres (1000 à 9999) tirés avec le module `secrets` (jamais un compteur) ; nouveau tirage en cas de collision, unicité sans tenir
  compte de la casse, 50 tirages au plus puis erreur explicite ;
- un membre qui a déjà un compte garde ses identifiants.

**Inchangé** : F-03 (comptes visiteur et éditeur) et F-05 (réinitialisation) gardent un mot de passe aléatoire de 12 caractères.

**Risque connu** : tant que la première connexion n'a pas eu lieu, le mot de passe est prévisible (déductible du nom d'utilisateur, qui est le
prénom plus 9000 possibilités). Quiconque connaît ou devine l'identifiant peut prendre le compte avant son titulaire.

**Garde-fous**
1. Le compte est créé avec `doit_changer_mot_de_passe=True` ; `ChangementMotDePasseMiddleware` bloque toute autre page (API comprise) tant que
   le mot de passe n'est pas changé ; seules la page de changement, la déconnexion et les fichiers statiques restent accessibles.
2. Le nouveau mot de passe passe `validate_password`, diffère de l'ancien et ne contient ni le nom d'utilisateur ni sa partie avant `@`.
3. L'identifiant et le mot de passe initial sont renvoyés **une seule fois** à l'auteur de la nomination, dans la réponse directe (`no-store`,
   `hx-history=false`) : jamais en messages, en session, en `HX-Trigger` ni au journal ; le journal ne contient jamais le mot de passe, même haché.
4. django-axes continue de limiter les essais de connexion ; l'auteur doit communiquer l'identifiant au membre sans délai.
5. Recommandation : nommer le membre au moment où il peut se connecter immédiatement, et réinitialiser (F-05) un compte jamais utilisé.

### Compléments à la dérogation F-02 (audit sécurité du 2026-10-15)

6. **Jamais affiché** : tant que `doit_changer_mot_de_passe` est vrai, l'identifiant « prenom1234@fenamordc.hub » (qui est le mot de passe initial)
   s'affiche masqué « prenom****@fenamordc.hub » partout sauf dans la réponse unique de la nomination : fiche du membre, vue de l'antenne,
   modales de gestion des comptes, historique, journal, communiqués (`compte.services.journal.identifiant_affichable`, filtre `identifiant_affiche`).
7. **Blocage par identifiant** : `AXES_LOCKOUT_PARAMETERS = ['username']`. Cinq échecs sur un même identifiant bloquent la connexion 30 minutes,
   quelle que soit l'adresse IP (avant : couple identifiant + adresse, contourné en changeant d'adresse). Le blocage par adresse seule reste à part
   (`IP_ECHECS_MAX`, 30). Contrepartie acceptée : un tiers qui connaît un identifiant peut le bloquer 30 minutes (déni de service limité, sans accès).
8. **Durée de validité** : un mot de passe initial ou temporaire (nomination, compte externe, réinitialisation F-05, compte créé par la gestion
   technique) expire au bout de `MOT_DE_PASSE_INITIAL_JOURS` jours (7 par défaut, réglable dans `.env`). Au-delà, la connexion est refusée (403,
   journalisée « mot de passe initial expiré », sans session) jusqu'à ce qu'un supérieur le réinitialise (F-05), ce qui relance le délai. Date de
   référence : `Compte.mot_de_passe_temporaire_le` (vide : date de création du compte). Changer son mot de passe efface la date.

## 2026-10-15 : interrupteur « données réelles » et mode exemple du site (identifiant DR-01)

**Extension demandée par `instructions.md`, point 3** : elle ne figure pas dans le cahier des charges (F-60 désigne les articles et la galerie, F-65
le paiement en ligne) ; elle porte l'identifiant **DR-01** pour ne pas être confondue avec une fonction F-xx.

- `Config.donnees_reelles_actif` (faux par défaut) : tant qu'il est faux, le site public affiche son **jeu d'exemple** (mode exemple) et les points
  d'accès `/api/v1/site/` de données répondent 403 ; vrai, le site affiche les données réelles.
- **Super-utilisateur seul**, par une modale de confirmation (POST + CSRF), motif facultatif de 500 caractères au plus (`contenu.MOTIF_MAX`).
- Chaque changement est journalisé (F-70 : auteur, date, avant / après, motif) puis demande la purge du cache du site.
- La lecture de l'état (`virtrine.services.etat_donnees_reelles`) est en lecture seule : un GET ne crée jamais la ligne de configuration.
- Le site `website/` bascule en mode exemple de son côté quand l'API refuse (voir `website/docs`).

## 2026-10-15 : retrait de `/ancien-site/` (audit sécurité, F-60)

Les routes publiques de l'ancien site (`/ancien-site/`, `activites/`, `article/<id>`, `portail/`, `a-propos-de-nous/`, `confidentiel/`) sont retirées :
elles ignoraient l'interrupteur « données réelles », exposaient les brouillons, donnaient une erreur 500 sur un identifiant inconnu et le portail
créait une association membre sans connexion. Le site public passe uniquement par `/api/v1/site/`. Gabarits, ressources et tests morts supprimés ;
`/contenu-site/configuration/` est conservé (gabarit simplifié). **À noter** : `POST /api/v1/site/contact/` (cahier § 2.4) n'est pas encore
implémenté ; en attendant, plus aucun message de contact ne peut être déposé.
