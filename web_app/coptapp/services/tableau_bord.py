"""Indicateurs du tableau de bord (agrégats seulement, aucune donnée personnelle).

Membres, engins et associations membres sont comptés dans le MÊME périmètre que la liste :
- membres : ceux de `compte.services.droits.membres_du_perimetre` (rôle, ou droits hérités), comptés par ÉTAT UNIQUE en une seule
  agrégation ;
- engins : engins non supprimés dont le propriétaire est dans le périmètre (tous pour qui voit tout) ;
- associations membres : celles des membres du périmètre et celles du compte (toutes pour qui voit tout).
"""
from django.db.models import Count

from coptapp.models import AssociationMembre, Moto
from coptapp.services.etats import LIBELLES
from compte.services.droits import etapes_a_valider, membres_du_perimetre, voit_tout  # noqa: F401 (membres_du_perimetre réexporté)

def engins_du_perimetre(user):
    """Engins non supprimés dont le propriétaire est visible par `user`."""
    engins = Moto.objects.filter(is_delete=False)
    if voit_tout(user):
        return engins
    return engins.filter(proprietaire__in=membres_du_perimetre(user).values('pk'))


def associations_du_perimetre(user):
    """Associations membres des membres visibles par `user`, plus celles auxquelles le compte est rattaché."""
    associations = AssociationMembre.objects.all()
    if voit_tout(user):
        return associations
    if not (user.is_authenticated and user.is_active):
        return associations.none()
    visibles = membres_du_perimetre(user).exclude(structure=None).values('structure')
    return associations.filter(pk__in=visibles) | associations.filter(users=user)


ETATS_EN_ATTENTE = ('saisi', 'valide_antenne', 'valide_province')


def indicateurs_tableau_bord(user):
    membres = membres_du_perimetre(user)
    par_etat = {ligne['etat']: ligne['n'] for ligne in membres.values('etat').annotate(n=Count('pk'))}  # UNE agrégation
    en_attente = list(membres.filter(etat__in=ETATS_EN_ATTENTE).select_related('antenne').order_by('-updated', '-id')[:5])
    for membre in en_attente:
        membre.peut_valider = bool(etapes_a_valider(user, membre))  # bouton « Valider » selon CE membre (étape de l'utilisateur)
    valeurs = {e: par_etat.get(e, 0) for e in ('saisi', 'valide_antenne', 'valide_province', 'actif', 'renvoye')}
    return {
        'actifs': valeurs['actif'],
        'valides_antenne': valeurs['valide_antenne'],
        'valides_province': valeurs['valide_province'],
        'saisis': valeurs['saisi'],
        'renvoyes': valeurs['renvoye'],
        'en_attente_total': sum(valeurs[e] for e in ETATS_EN_ATTENTE),
        'engins': engins_du_perimetre(user).count(),
        'associations': associations_du_perimetre(user).distinct().count(),
        'en_attente': en_attente,
        'graphique': {
            'etats': list(valeurs),
            'libelles': [str(LIBELLES[e]) for e in valeurs],
            'valeurs': list(valeurs.values()),
            'lignes': [{'etat': e, 'libelle': str(LIBELLES[e]), 'valeur': v} for e, v in valeurs.items()],
        },
    }
