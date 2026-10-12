"""Indicateurs du tableau de bord (agrégats seulement, aucune donnée personnelle).

PROVISOIRE : membres, engins et associations membres sont comptés dans le MÊME périmètre, celui de
`droits_provisoires.membres_du_perimetre` (privilèges hérités) :
- membres : ceux du périmètre ;
- engins : engins non supprimés dont le propriétaire est dans le périmètre (tous pour SU / privilege5) ;
- associations membres : celles des membres du périmètre et celles du compte (tous pour SU / privilege5).
TODO : remplacé par le périmètre des rôles (F-16, F-51) au sous-lot 2e.
"""
from django.utils.translation import gettext_lazy as _

from coptapp.models import AssociationMembre, Moto
from coptapp.services.droits_provisoires import membres_du_perimetre, voit_tout  # noqa: F401 (membres_du_perimetre réexporté)

LIBELLES = {
    'saisi': _('Saisi'),
    'valide-antenne': _('Validé antenne'),
    'actif': _('Actif'),
}


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
