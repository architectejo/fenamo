"""État d'un membre ou d'un engin dans le circuit de validation (cahier des charges § 4.4).

Circuit cible : saisi -> valide_antenne -> valide_province -> actif, plus renvoye, a_renouveler, supprime.
Les booléens hérités ne le représentent qu'en partie (ils seront remplacés par un champ d'état unique, § 4.4) ;
cette fonction est le SEUL endroit qui les interprète. Quand le champ `etat` existera, `etat_de` le lira en priorité.

Correspondance héritière retenue, d'après coptapp.views.validate et les listes de coptapp.views (à confirmer) :
- Membre.is_validate1 vaut True dès la création (défaut du modèle) et validate() ne le touche que pour le
  mettre à True : il ne signifie donc PAS « validé antenne » et n'est pas lu ici ;
- is_validate2 = première validation (privilege2) -> 'valide_antenne' ;
- is_validate3 = validation finale (privilege3), seule visible du public et comptée dans les effectifs -> 'actif' ;
- 'valide_province' n'est pas produit par les booléens hérités (une seule validation intermédiaire existe) ;
- 'renvoye' n'a aucun support hérité (ni drapeau ni motif) ;
- Moto n'a aucun drapeau de validation : un engin non supprimé est 'actif' ; 'a_renouveler' s'il est échu
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
    explicite = getattr(objet, 'etat', None)  # futur champ d'état unique
    if explicite in ETATS:
        return explicite
    if getattr(objet, 'is_delete', False):
        return 'supprime'
    if hasattr(objet, 'abonnement') and not hasattr(objet, 'is_validate3'):  # engin
        echeance = objet.abonnement
        if echeance and echeance < (aujourdhui or date.today()):
            return 'a_renouveler'
        return 'actif'
    if getattr(objet, 'is_validate3', False):
        return 'actif'
    if getattr(objet, 'is_validate2', False):
        return 'valide_antenne'
    return 'saisi'


def filtrer_membres_par_etat(membres, etat):
    """Restreint un queryset de Membre à un état du circuit (même lecture des booléens hérités que `etat_de`).

    `etat` : un code de ETATS. Les états qu'aucun booléen hérité ne produit ('valide_province', 'renvoye',
    'a_renouveler') et 'supprime' (les listes excluent les membres supprimés) donnent une liste vide.
    Un code inconnu ou vide ne filtre pas.
    """
    etat = (etat or '').replace('-', '_')  # les classes CSS utilisent des tirets
    if etat not in ETATS:
        return membres
    if etat == 'actif':
        return membres.filter(is_validate3=True, is_delete=False)
    if etat == 'valide_antenne':
        return membres.filter(is_validate2=True, is_validate3=False, is_delete=False)
    if etat == 'saisi':
        return membres.filter(is_validate2=False, is_validate3=False, is_delete=False)
    return membres.none()
