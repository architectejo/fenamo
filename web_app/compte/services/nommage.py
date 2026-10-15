"""Aides de nomination pour les listes (F-02) : rôle déjà porté, membre nommable ou raison pour laquelle il ne l'est pas."""
from django.utils.translation import gettext as _

from compte import roles
from compte.models import Nomination
from compte.services import nominations as noms


def raison_non_nommable(membre, avec_nomination):
    if membre.pk in avec_nomination:
        return _("Déjà nommé : %(role)s.") % {'role': str(roles.LIBELLES.get(avec_nomination[membre.pk], '')).lower()}
    if membre.etat != 'actif':
        return _("Pas encore actif : la validation nationale manque.")
    return _("Ce membre ne peut pas être nommé.")


def annoter_nommage(auteur, membres):
    """Pour la liste des membres : pose sur chaque membre de `membres` (liste ou page) ``role_nomme`` (code du rôle actif ou ''),
    ``nommable`` et ``raison_non_nommable`` (texte du survol). Deux requêtes pour toute la page. Sans droit de nommer : tout reste vide."""
    membres = list(membres)
    if not membres:
        return membres
    ids = [m.pk for m in membres]
    par_membre = {n.compte.membreId: n.role for n in Nomination.objects.filter(active=True, compte__membreId__in=ids).select_related('compte')}
    nommables = set(noms.membres_nommables(auteur).filter(pk__in=ids).values_list('pk', flat=True))
    for m in membres:
        m.role_nomme = par_membre.get(m.pk, '')
        m.role_nomme_libelle = roles.LIBELLES.get(m.role_nomme, '') if m.role_nomme else ''
        m.nommable = m.pk in nommables
        m.raison_non_nommable = '' if m.nommable else raison_non_nommable(m, par_membre)
    return membres
