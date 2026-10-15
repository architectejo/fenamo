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
