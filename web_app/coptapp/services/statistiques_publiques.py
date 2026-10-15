"""Statistiques publiques du site (S-09) : agrégats uniquement, aucune donnée personnelle.

- « Membre actif » = état ``actif`` seul (ni « à renouveler », ni les dossiers en cours, ni les supprimés) ;
- une coordination est celle de l'antenne du membre, à défaut sa coordination propre ;
- les engins sont MASQUÉS (``None``) tant que leurs états ne sont pas faits (F-30, F-32) ;
- UNE requête par série (coordinations, membres actifs, associations membres, antennes).
"""
from django.db.models import Count
from django.db.models.functions import Coalesce

from coptapp.models import Antenne, AssociationMembre, Membre, Province


def statistiques_publiques():
    """{'national': {...}, 'coordinations': [{code, nom, membres_actifs, associations, antennes, engins}]} ; engins toujours None."""
    coordinations = list(Province.objects.filter(code__isnull=False).order_by('ordre', 'nom').values('pk', 'code', 'nom'))
    membres = dict(Membre.objects.filter(etat='actif').annotate(coord=Coalesce('antenne__coordination', 'province'))
                   .exclude(coord=None).values_list('coord').annotate(n=Count('pk')).order_by())
    associations = dict(AssociationMembre.objects.annotate(coord=Coalesce('antenne__coordination', 'province'))
                        .exclude(coord=None).values_list('coord').annotate(n=Count('pk')).order_by())
    antennes = dict(Antenne.objects.exclude(coordination=None).values_list('coordination').annotate(n=Count('pk')).order_by())
    lignes = [{'code': c['code'], 'nom': c['nom'], 'membres_actifs': membres.get(c['pk'], 0), 'associations': associations.get(c['pk'], 0),
               'antennes': antennes.get(c['pk'], 0), 'engins': None} for c in coordinations]
    return {
        'national': {'membres_actifs': sum(l['membres_actifs'] for l in lignes), 'associations': sum(l['associations'] for l in lignes),
                     'antennes': sum(l['antennes'] for l in lignes), 'coordinations': len(lignes), 'engins': None},
        'coordinations': lignes,
    }
