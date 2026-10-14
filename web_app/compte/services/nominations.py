"""Nominations : création, fin, cohérence rôle / périmètre, groupes Django miroirs (cahier des charges web § 4 et F-02).

Règles de cohérence rôle / périmètre :
- SU, PR, VN : national, aucun périmètre géographique ;
- VP : une coordination provinciale (pas d'antenne) ;
- VA : une antenne ; AT : une antenne, éventuellement une association membre ;
- VI : national (aucun périmètre), OU une coordination, OU une antenne (fixé à la création) ;
- ED : aucun périmètre (le contenu du site n'est pas géographique).
Un compte n'a qu'UNE nomination active. Ce module ne contrôle PAS qui peut nommer qui (§ 4.2) : c'est l'affaire de la vue de nomination.
"""
from datetime import date

from django.contrib.auth.models import Group
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone
from django.utils.translation import gettext as _

from compte import roles
from compte.models import JournalAction, Nomination
from compte.services.journal import journaliser


def valider_coherence(role, coordination_id=None, antenne_id=None, association_id=None):
    """Lève ValidationError si le périmètre ne convient pas au rôle."""
    if role not in roles.ROLES:
        raise ValidationError({'role': _("Rôle inconnu.")})
    erreurs = {}
    if role in (roles.SU, roles.PR, roles.VN, roles.ED):
        if coordination_id or antenne_id or association_id:
            erreurs['__all__'] = _("Ce rôle n'a pas de périmètre géographique.")
    elif role == roles.VP:
        if not coordination_id:
            erreurs['coordination'] = _("Le validateur provincial exerce dans une coordination provinciale.")
        elif antenne_id or association_id:
            erreurs['__all__'] = _("Le validateur provincial n'a pas d'antenne ni d'association : sa coordination suffit.")
    elif role in (roles.VA, roles.AT):
        if not antenne_id:
            erreurs['antenne'] = _("Ce rôle exerce dans une antenne.")
        elif coordination_id:
            erreurs['__all__'] = _("Ce rôle se définit par son antenne, pas par une coordination.")
        elif association_id and role == roles.VA:
            erreurs['__all__'] = _("Le validateur d'antenne n'est pas limité à une association membre.")
    elif role == roles.VI:
        if coordination_id and antenne_id:
            erreurs['__all__'] = _("Le visiteur a un seul périmètre : national, une coordination OU une antenne.")
        elif association_id:
            erreurs['__all__'] = _("Le visiteur n'est pas limité à une association membre.")
    if erreurs:
        raise ValidationError(erreurs)


def synchroniser_groupe(compte):
    """Groupes Django miroirs : le compte est dans le groupe ``role_<ROLE>`` de sa nomination active, dans aucun autre."""
    voulu = Nomination.objects.filter(compte=compte, active=True).values_list('role', flat=True).first()
    miroirs = Group.objects.filter(name__startswith=roles.PREFIXE_GROUPE)
    compte.groups.remove(*miroirs.exclude(name=roles.nom_du_groupe(voulu))) if voulu else compte.groups.remove(*miroirs)
    if voulu:
        groupe, _cree = Group.objects.get_or_create(name=roles.nom_du_groupe(voulu))
        compte.groups.add(groupe)


@transaction.atomic
def creer_nomination(auteur, compte, role, *, membre=None, coordination=None, antenne=None, association=None,
                     debut=None, fin=None, duree_mandat_ans=None):
    """Nomme `compte` dans `role` ; retourne la Nomination. Une seule nomination active par compte (ValidationError sinon).

    Sans `fin`, elle est calculée à partir de la durée de mandat du rôle (``roles.duree_par_defaut``) quand il en a une.
    `auteur` est inscrit comme ayant nommé et au journal d'activités (NOMINATION).
    """
    valider_coherence(role, getattr(coordination, 'pk', None), getattr(antenne, 'pk', None), getattr(association, 'pk', None))
    if Nomination.objects.select_for_update().filter(compte=compte, active=True).exists():
        raise ValidationError(_("Ce compte a déjà une nomination active : terminez-la d'abord."))
    debut = debut or timezone.localdate()
    duree = duree_mandat_ans if duree_mandat_ans is not None else roles.duree_par_defaut(role)
    if fin is None and duree:
        try:
            fin = debut.replace(year=debut.year + duree)
        except ValueError:  # 29 février
            fin = date(debut.year + duree, 3, 1)
    nomination = Nomination.objects.create(
        compte=compte, membre=membre, role=role, coordination=coordination, antenne=antenne, association=association,
        debut=debut, fin=fin, duree_mandat_ans=duree, nomme_par=auteur if getattr(auteur, 'pk', None) else None)
    synchroniser_groupe(compte)
    oublier_profil(compte)
    journaliser(auteur, JournalAction.Action.NOMINATION, compte, apres={'role': role, 'debut': debut, 'fin': fin},
                libelle=getattr(compte, 'username', ''))
    return nomination


@transaction.atomic
def terminer_nomination(auteur, nomination, motif=''):
    """Met fin à la nomination (elle est conservée, marquée terminée) ; le compte perd ses droits de rôle."""
    if not nomination.active:
        return nomination
    nomination.active = False
    nomination.terminee_le = timezone.now()
    nomination.terminee_par = auteur if getattr(auteur, 'pk', None) else None
    nomination.motif_fin = motif or ''
    nomination.save(update_fields=['active', 'terminee_le', 'terminee_par', 'motif_fin'])
    synchroniser_groupe(nomination.compte)
    oublier_profil(nomination.compte)
    journaliser(auteur, JournalAction.Action.FIN_NOMINATION, nomination.compte, avant={'role': nomination.role, 'active': True},
                apres={'active': False}, motif=motif or '', libelle=getattr(nomination.compte, 'username', ''))
    return nomination


def oublier_profil(compte):
    """Efface le profil de droits mis en cache sur l'objet `compte` (voir ``compte.services.droits``)."""
    for attribut in ('_fenamo_profil',):
        if hasattr(compte, attribut):
            delattr(compte, attribut)
