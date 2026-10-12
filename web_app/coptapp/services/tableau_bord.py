"""Indicateurs du tableau de bord (agrégats seulement, aucune donnée personnelle).

PROVISOIRE : le périmètre reprend celui de la liste héritée des membres (privilèges hérités) ; il sera
remplacé par le périmètre des rôles (F-16, F-51) au sous-lot 2e.
"""
from django.utils.translation import gettext_lazy as _

from coptapp.models import AssociationMembre, Membre, Moto

LIBELLES = {
    'saisi': _('Saisi'),
    'valide-antenne': _('Validé antenne'),
    'actif': _('Actif'),
}


def membres_du_perimetre(user):
    """Membres non supprimés visibles par `user` (mêmes règles que coptapp.views.membreListe)."""
    membres = Membre.objects.filter(is_delete=False)
    if user.is_superuser or user.privilege5:
        return membres
    if user.privilege1 or user.privilege2:
        return membres.filter(is_validate1=True)
    if user.privilege3:
        return membres.filter(is_validate1=True, is_validate2=True)
    if user.privilege4:
        return membres.filter(is_validate3=True)
    return membres


def indicateurs_tableau_bord(user):
    membres = membres_du_perimetre(user)
    actifs = membres.filter(is_validate3=True).count()
    valides_antenne = membres.filter(is_validate2=True, is_validate3=False).count()
    saisis = membres.filter(is_validate2=False, is_validate3=False).count()
    en_attente = list(
        membres.filter(is_validate3=False).select_related('antenne').order_by('-updated', '-id')[:5]
    )
    valeurs = {'saisi': saisis, 'valide-antenne': valides_antenne, 'actif': actifs}
    return {
        'actifs': actifs,
        'valides_antenne': valides_antenne,
        'saisis': saisis,
        'en_attente_total': valides_antenne + saisis,
        'engins': Moto.objects.filter(is_delete=False).count(),
        'associations': AssociationMembre.objects.count(),
        'en_attente': en_attente,
        'graphique': {
            'etats': list(valeurs),
            'libelles': [str(LIBELLES[e]) for e in valeurs],
            'valeurs': list(valeurs.values()),
            'lignes': [{'etat': e, 'libelle': str(LIBELLES[e]), 'valeur': v} for e, v in valeurs.items()],
        },
    }
