# Correspondance anciens booléens et état unique du membre

Sert à la migration `coptapp/migrations/0062_membre_etat_donnees.py` et, plus tard, à la reprise de l'ancien projet « coptam » (`is_validate2`, `is_validate3`, `is_delete`, plus `renvoye` côté nouveau projet). `is_validate1` n'est pas repris : il vaut vrai pour tous.

## Sens direct (dans cet ordre, rien n'est dégradé si on rejoue)

| Étape | Condition | État obtenu |
|---|---|---|
| 1 | tous | `saisi` |
| 2 | `is_validate2` | `valide_antenne` |
| 3 | `is_validate3` (même sans `is_validate2`) | `actif` |
| 4 | `renvoye` | `renvoye`, `etat_precedent` = état des étapes 1 à 3 |
| 5 | `is_delete` | `etat_precedent` = état courant, puis `etat` = `supprime` (deux mises à jour) |

Les booléens ne sont pas modifiés dans ce sens. Les états `valide_province` et `a_renouveler` n'existent pas dans l'ancien modèle : ils ne sont produits que par l'application.

## Cas ambigus (à confirmer avec l'utilisateur)

- `is_validate3` sans `is_validate2` : converti en `actif`.
- Renvoyé et supprimé : l'état d'avant la suppression est `renvoye` ; l'état de validation d'origine est perdu.
- Renvoyé avec validations : elles ne sont conservées que dans `etat_precedent` (que `save()` efface au prochain enregistrement du membre).

`manage.py verifier_etats_membres` les liste (id et idf seulement). `--corriger` ne resynchronise que les booléens depuis `etat` ; `--dry-run` n'écrit rien.

## Sens inverse

Les booléens sont recalculés depuis `etat` : `valide_province` redevient `is_validate2` seul ; `supprime` et `renvoye` reprennent les validations de `etat_precedent` ; `is_delete` vaut vrai si `etat` = `supprime`.
