"""Données de la fiche d'un membre (lecture) : tout ce que le gabarit de la fiche affiche en dehors des droits."""
from datetime import date

from compte.services.comptes import compte_du_membre
from coptapp.models import Antenne, AssociationMembre, Famille, Moto, Ville
from coptapp.services.historique import historique_objet

PRIVILEGES = ('privilege1', 'privilege2', 'privilege3', 'privilege4', 'privilege5')


def cases_privileges(compte):
    """{'checked1': 'checked', …} pour les privilèges hérités accordés à `compte` (None : aucun)."""
    if compte is None:
        return {}
    return {f'checked{i}': 'checked' for i, nom in enumerate(PRIVILEGES, start=1) if getattr(compte, nom)}


def contexte_fiche(user, membre, droits):
    """Contexte explicite de la fiche de `membre` vue par `user` (les droits sont fournis par l'appelant).

    Clés : structure (première association du compte), membreUser (compte du membre), villes, structures, antennes,
    familles, motos, nbrMoto, motoAttr (engin dont le membre est motard), age, historique (lignes du journal, vide sans
    le droit de le voir) et checked1 à checked5 (privilèges du compte du membre).
    """
    compte = compte_du_membre(membre.id)
    naissance = membre.date_naissance
    motos = Moto.objects.filter(proprietaire=membre, is_delete=False)
    contexte = {
        'structure': AssociationMembre.objects.filter(users=user).first(),
        'membreUser': compte,
        'villes': Ville.objects.filter(province=membre.province).exclude(nom=None),
        'structures': AssociationMembre.objects.filter(province=membre.province),
        'antennes': (Antenne.objects.filter(structure__ville=membre.ville).exclude(nom=None)
                     if membre.ville else Antenne.objects.order_by('nom')),
        'familles': Famille.objects.filter(membre=membre),
        'motos': motos,
        'nbrMoto': motos.count(),
        'motoAttr': Moto.objects.filter(motard_id=membre.id).first(),
        'age': date.today().year - naissance.year if naissance else None,
        'historique': historique_objet(membre) if droits['peut_voir_historique'] else [],
    }
    contexte.update(cases_privileges(compte))
    return contexte
