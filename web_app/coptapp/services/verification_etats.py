"""Contrôle de cohérence entre l'état unique du membre et ses booléens miroirs (§ 4.4). Aucune donnée personnelle en sortie :
seuls ``id`` et ``idf`` sont rapportés."""
from django.db import models

from coptapp.models import CHAMPS_MIROIRS, ETATS_MEMBRE, Membre, miroirs_de

LOT_AFFICHAGE = 50


def _ambigu(m):
    """Raisons d'ambiguïté d'un membre, lues sur son état et ses miroirs (liste vide si aucune)."""
    raisons = []
    if m['is_validate3'] and not m['is_validate2']:
        raisons.append('validation province sans validation antenne')
    if m['renvoye'] and m['is_delete']:
        raisons.append('renvoyé et supprimé à la fois')
    if m['etat'] == 'renvoye' and (m['is_validate2'] or m['is_validate3']):
        raisons.append('renvoyé avec des validations conservées')
    if m['etat'] == 'supprime' and m['etat_precedent'] not in ETATS_MEMBRE:
        raisons.append('supprimé sans état précédent valide')
    return raisons


def verifier(corriger=False, dry_run=False):
    """Compte les membres par état, repère les écarts état/miroirs et les cas ambigus.

    ``corriger`` ne fait que resynchroniser les miroirs depuis ``etat`` (jamais l'inverse) ; ``dry_run`` n'écrit rien."""
    champs = ('pk', 'idf', 'etat', 'etat_precedent', *CHAMPS_MIROIRS)
    lignes = list(Membre.objects.values(*champs))
    par_etat = {e: 0 for e in ETATS_MEMBRE}
    inconnus = []
    ecarts, ambigus, groupes = [], [], {}
    for m in lignes:
        if m['etat'] in par_etat:
            par_etat[m['etat']] += 1
        else:
            inconnus.append(m)
        raisons = _ambigu(m)
        if raisons:
            ambigus.append((m['pk'], m['idf'], raisons))
        attendu = miroirs_de(m['etat'], m['etat_precedent'])
        if any(m[c] != attendu[c] for c in CHAMPS_MIROIRS):
            ecarts.append((m['pk'], m['idf'], [c for c in CHAMPS_MIROIRS if m[c] != attendu[c]]))
            groupes.setdefault((m['etat'], m['etat_precedent']), []).append(m['pk'])
    corriges = 0
    if corriger and not dry_run:
        for (etat, precedent), pks in groupes.items():
            for i in range(0, len(pks), 500):
                # QuerySet de base : Membre.objects.update() traduirait les booléens en état, ce qu'on veut éviter ici
                corriges += models.QuerySet(model=Membre).filter(pk__in=pks[i:i + 500]).update(**miroirs_de(etat, precedent))
    return {'total': len(lignes), 'par_etat': par_etat, 'inconnus': [(m['pk'], m['idf']) for m in inconnus],
            'ecarts': ecarts, 'ambigus': ambigus, 'corriges': corriges}
