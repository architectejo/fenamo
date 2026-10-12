"""Liste des membres : recherche, filtres et pagination (F-28). Règle métier testable, appelée par la vue.

Le périmètre vient de `droits_provisoires.membres_du_perimetre` (provisoire, remplacé au sous-lot 2e) ; les
membres sans nom (fiches vides héritées) sont exclus ici, au niveau du queryset.
"""
from dataclasses import dataclass

from django.core.paginator import Paginator
from django.db.models import Q

from coptapp.models import Antenne, AssociationMembre
from coptapp.services.droits_provisoires import membres_du_perimetre
from coptapp.services.etats import ETATS, filtrer_membres_par_etat

PAR_PAGE = 25
QUALITES = ('MOTARD', 'PROPRIETAIRE', 'MOTARD ET PROPRIETAIRE')
Q_LONGUEUR_MAX = 100
ENTIER_MAX = 2**63 - 1


@dataclass
class ResultatListe:
    """Résultat de `lister_membres`."""
    page_obj: object      # Page Django : itérable de Membre, .paginator.count, .number, .has_next()…
    filtres: dict         # valeurs normalisées des filtres (chaînes), pour préremplir le formulaire
    filtres_actifs: bool  # vrai si au moins un filtre ou une recherche est posé


def _entier(valeur):
    """Entier strictement positif et assez petit pour la base (sinon None : le filtre est ignoré)."""
    try:
        nombre = int(valeur)
    except (TypeError, ValueError):
        return None
    return nombre if 0 < nombre <= ENTIER_MAX else None


def normaliser_filtres(params):
    """Extrait q, etat, qualite, antenne, association de `params` (QueryDict ou dict) ; valeurs invalides ignorées."""
    q = (params.get('q') or '').strip()[:Q_LONGUEUR_MAX]
    etat = (params.get('etat') or '').strip().replace('-', '_')
    qualite = (params.get('qualite') or '').strip().upper()
    return {
        'q': q,
        'etat': etat if etat in ETATS else '',
        'qualite': qualite if qualite in QUALITES else '',
        'antenne': _entier(params.get('antenne')) or '',
        'association': _entier(params.get('association')) or '',
    }


def membres_filtres(user, filtres):
    """Queryset des membres de `user` filtré, trié par nom ; sans les membres sans nom."""
    membres = (
        membres_du_perimetre(user)
        .exclude(nom__isnull=True).exclude(nom='')
        .select_related('antenne', 'structure', 'user')
    )
    q = filtres.get('q')
    if q:
        membres = membres.filter(
            Q(nom__icontains=q) | Q(idf__icontains=q) | Q(numero_carte_de_membre__icontains=q) | Q(telephone__icontains=q)
        )
    if filtres.get('etat'):
        membres = filtrer_membres_par_etat(membres, filtres['etat'])
    if filtres.get('qualite'):
        membres = membres.filter(qualite__iexact=filtres['qualite'])
    if filtres.get('antenne'):
        membres = membres.filter(antenne_id=filtres['antenne'])
    if filtres.get('association'):
        membres = membres.filter(structure_id=filtres['association'])
    return membres.order_by('nom', 'id')


def lister_membres(user, params, numero_page=None, par_page=PAR_PAGE):
    """Page de membres visibles par `user` pour les filtres de `params`.

    Une page hors bornes ou illisible ramène à la dernière ou à la première page (jamais d'erreur).
    """
    filtres = normaliser_filtres(params)
    page_obj = Paginator(membres_filtres(user, filtres), par_page).get_page(numero_page)
    return ResultatListe(page_obj=page_obj, filtres=filtres, filtres_actifs=any(filtres.values()))


def choix_filtres(user):
    """Antennes et associations membres proposées dans les filtres : celles des membres du périmètre."""
    visibles = membres_du_perimetre(user)
    return {
        'antennes': Antenne.objects.filter(pk__in=visibles.exclude(antenne=None).values('antenne')).exclude(nom=None).order_by('nom'),
        'associations': AssociationMembre.objects.filter(pk__in=visibles.exclude(structure=None).values('structure')).order_by('sigle', 'nom'),
        'qualites': QUALITES,
        'etats': tuple(e for e in ETATS if e in ('saisi', 'valide_antenne', 'actif')),
    }
