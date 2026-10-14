"""État d'un membre ou d'un engin dans le circuit de validation (cahier des charges § 4.4).

Circuit : saisi -> valide_antenne -> valide_province -> actif, plus renvoye, a_renouveler, supprime.
Pour un MEMBRE, la source de vérité est le champ unique ``Membre.etat`` (les anciens booléens is_delete, is_validate2, is_validate3 et
renvoye n'en sont que des miroirs, recalculés par ``Membre.save``) ; les changements d'état passent par ``coptapp.services.transitions``.
Un Moto n'a aucun drapeau de validation : un engin non supprimé est 'actif' ; 'a_renouveler' s'il est échu
(Moto.abonnement < aujourd'hui, à confirmer comme « identification annuelle échue »).
"""
from datetime import date

from django.utils.translation import gettext_lazy as _

ETATS = ('saisi', 'valide_antenne', 'valide_province', 'actif', 'renvoye', 'a_renouveler', 'supprime')


# Table UNIQUE des libellés d'état (codes en snake_case) : les gabarits, les balises et le tableau de bord la lisent.
LIBELLES = {
    'saisi': _('Saisi'),
    'valide_antenne': _('Validé antenne'),
    'valide_province': _('Validé province'),
    'actif': _('Actif'),
    'renvoye': _('Renvoyé'),
    'a_renouveler': _('À renouveler'),
    'supprime': _('Supprimé'),
}


def etat_de(objet, aujourdhui=None):
    """Code d'état de `objet` (Membre ou Moto), parmi ETATS."""
    explicite = getattr(objet, 'etat', None)
    if explicite in ETATS:
        return explicite
    if getattr(objet, 'is_delete', False):
        return 'supprime'
    if hasattr(objet, 'abonnement'):  # engin : pas de circuit propre pour l'instant
        echeance = objet.abonnement
        if echeance and echeance < (aujourdhui or date.today()):
            return 'a_renouveler'
        return 'actif'
    return 'saisi'


def filtrer_membres_par_etat(membres, etat):
    """Restreint un queryset de Membre à un état du circuit (champ unique ``etat``).

    `etat` : un code de ETATS. 'supprime' donne une liste vide (les listes excluent les membres supprimés). Un code inconnu ou
    vide ne filtre pas."""
    if etat not in ETATS:
        return membres
    if etat == 'supprime':
        return membres.none()
    return membres.filter(etat=etat)
