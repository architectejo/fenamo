"""Les huit rôles de l'application (cahier des charges web § 4.1) et leurs périmètres.

Un rôle s'exerce dans un PÉRIMÈTRE : national, une coordination provinciale, une antenne (éventuellement une association
membre pour l'agent de terrain). Les durées de mandat suivent la charte (art. 72 à 75) : comité d'antenne 3 ans,
coordination provinciale 4 ans, comité national 5 ans.
"""
from django.utils.translation import gettext_lazy as _

SU, PR, VN, VP, VA, AT, VI, ED = 'SU', 'PR', 'VN', 'VP', 'VA', 'AT', 'VI', 'ED'
ROLES = (SU, PR, VN, VP, VA, AT, VI, ED)

LIBELLES = {
    SU: _('Super-utilisateur'),
    PR: _('Président'),
    VN: _('Validateur national'),
    VP: _('Validateur provincial'),
    VA: _("Validateur d'antenne"),
    AT: _('Agent de terrain'),
    VI: _('Visiteur'),
    ED: _('Éditeur'),
}

NATIONAL, COORDINATION, ANTENNE = 'national', 'coordination', 'antenne'
# Niveau de périmètre OBLIGATOIRE de chaque rôle ; VI : « au choix » (national, coordination ou antenne, fixé à la création).
PERIMETRE_DU_ROLE = {SU: NATIONAL, PR: NATIONAL, VN: NATIONAL, VP: COORDINATION, VA: ANTENNE, AT: ANTENNE, VI: None, ED: None}
# Rôles sans périmètre géographique (le contenu du site n'est pas géographique).
SANS_PERIMETRE = (ED,)

DUREES_MANDAT_ANS = {ANTENNE: 3, COORDINATION: 4, NATIONAL: 5}
# Durée par défaut selon le rôle : comité d'antenne (VA, AT), coordination (VP), comité national (PR, VN).
DUREE_DU_ROLE = {VA: DUREES_MANDAT_ANS[ANTENNE], AT: DUREES_MANDAT_ANS[ANTENNE], VP: DUREES_MANDAT_ANS[COORDINATION],
                 PR: DUREES_MANDAT_ANS[NATIONAL], VN: DUREES_MANDAT_ANS[NATIONAL]}

# Rang hiérarchique (plus petit = plus haut) : qui peut nommer qui (§ 4.2, appliqué aux nominations au sous-lot suivant).
RANG = {SU: 0, PR: 1, VN: 2, VP: 3, VA: 4, AT: 5, VI: 6, ED: 6}

# Qui peut nommer quel rôle (§ 4.3, ligne « Nommer des utilisateurs »). Le rôle SU n'est jamais nommable : les comptes SU sont
# réservés au prestataire technique (F-07) ; ED se nomme par SU seulement ; VI par PR et SU.
NOMMABLES = {
    SU: (PR, VN, VP, VA, AT, VI, ED),
    PR: (VN, VP, VA, AT, VI),
    VN: (VP, VA, AT),
    VP: (VA, AT),
    VA: (AT,),
}

PREFIXE_GROUPE = 'role_'


def nom_du_groupe(role):
    """Nom du groupe Django miroir d'un rôle : ``role_SU``, ``role_PR``…"""
    return f'{PREFIXE_GROUPE}{role}'


def duree_par_defaut(role):
    """Durée de mandat en années pour `role` (None si le rôle n'a pas de mandat : SU, VI, ED)."""
    return DUREE_DU_ROLE.get(role)


def roles_nommables_par(role):
    """Rôles qu'un compte de rôle `role` peut nommer (tuple vide : aucun)."""
    return NOMMABLES.get(role, ())
