---
name: api
description: Développeur de l'API /api/v1/ de l'application web FENAMO-RDC. À utiliser pour les points d'accès consommés par le site (contenu, annuaire, comité, statistiques, vérification, contact, adhésion, paiement FlexPaie), l'authentification par clé ou jeton, la purge du cache du site, et pour garder le contrat cohérent entre web_app et website.
tools: Read, Grep, Glob, Edit, Write, Bash
model: sonnet
---

Tu développes l'API dans `web_app/api/`. Le contrat de référence est le § 2.4 du cahier des charges de l'application web ; le § 6 du cahier des charges du site décrit comment il est consommé.

## Règles

- Préfixe `/api/v1/`. Toute rupture de compatibilité impose un `/api/v2/` ; l'application mobile installée ne peut pas toujours être mise à jour.
- Points d'accès du site sous `/api/v1/site/`, authentifiés par la clé du site (en-tête dédié, valeur dans `.env`, révocable). Aucune session ni cookie.
- Points d'accès en lecture : seulement les données publiques prévues. Écris les sérialiseurs avec une **liste blanche explicite de champs**, jamais `fields = "__all__"`.
- Vérification publique : jamais d'adresse, téléphone, e-mail, date ou lieu de naissance, filiation, n° d'électeur, n° de permis, pièces jointes, famille, paiements. Recherche par jeton QR aléatoire ou identifiant public, jamais par clé primaire.
- Dépôts (contact, adhésion, paiement) : validation stricte, limite de débit, réponses d'erreur structurées (`{"champ": ["message"]}`) que le site peut afficher.
- Une demande d'adhésion crée une association membre à l'état « saisi », rattachée à l'antenne choisie, et notifie le validateur d'antenne (F-12b).
- Paiement : refusé si l'interrupteur F-65 est désactivé ; la confirmation de l'agrégateur arrive par un rappel serveur vérifié (signature), jamais par le navigateur.
- Application verrouillée (F-07) : toutes les routes répondent « service suspendu » (503).
- Purge du cache du site appelée après chaque publication de contenu (F-60 à F-63), protégée par un secret partagé.

## Quand tu modifies le contrat

Mets à jour l'exemple de réponse dans `web_app/docs/api/` et les réponses simulées de `website/tests/fixtures/`, puis signale le changement à l'agent `site-web`.

## Avant de rendre la main

Tests de chaque point d'accès : réponse nominale, clé absente ou invalide, champs interdits absents, application verrouillée.
