"""Liste des membres : recherche, filtres et pagination (F-28). Règle métier testable, appelée par la vue.

Le périmètre vient de `droits_provisoires.membres_du_perimetre` (provisoire, remplacé au sous-lot 2e) ; les
membres sans nom (fiches vides héritées) sont exclus ici, au niveau du queryset.
"""
from dataclasses import dataclass

from django import forms
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.db.models import Q

from compte.models import JournalAction
from compte.services.journal import instantane, journaliser
from coptapp.models import Antenne, AssociationMembre, Membre, Notification
from coptapp.services.droits_provisoires import droits_membre, etapes_a_valider, membres_du_perimetre
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
    # Droit de valider PAR MEMBRE (étape précédente exigée, jamais sa propre fiche) : calcul en mémoire, sans requête.
    page_obj.object_list = list(page_obj.object_list)
    for membre in page_obj.object_list:
        membre.peut_valider = bool(etapes_a_valider(user, membre))
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


# ---------------------------------------------------------------- modification d'un membre (F-21)

CHAMPS_MODIFIABLES = (
    'nom', 'a_propos', 'date_naissance', 'genre', 'titre', 'fonction', 'comite', 'nation', 'brevet', 'etat_civil',
    'adresse', 'telephone', 'mail', 'categorie', 'permis', 'qualite', 'autre_asb', 'numero_carte_d_electeur',
    'numero_carte_de_membre', 'nom_pere', 'nom_mere', 'village', 'chefferie', 'territoire', 'province_origine',
)
# Noms envoyés par la modale de la fiche -> champs du modèle.
ALIAS_POST = {'about': 'a_propos', 'date': 'date_naissance', 'autre_asbl': 'autre_asb'}
OBLIGATOIRES = ('nom', 'date_naissance')
# Le journal garde l'existence du changement mais pas la valeur de ces champs d'identité.
MASQUES_AU_JOURNAL = ('numero_carte_d_electeur', 'permis', 'brevet')


class MembreModificationForm(forms.ModelForm):
    """Formulaire de modification : `nom` et la date de naissance sont obligatoires (erreur de formulaire s'ils
    manquent) ; un autre champ absent du POST garde sa valeur actuelle. Date au format JJ-MM-AAAA (ou AAAA-MM-JJ)."""

    date_naissance = forms.DateField(input_formats=['%d-%m-%Y', '%Y-%m-%d'], required=True)

    class Meta:
        model = Membre
        fields = CHAMPS_MODIFIABLES + ('photo',)

    def __init__(self, data=None, files=None, instance=None, **kwargs):
        if data is not None:
            data = data.copy()
            for alias, champ in ALIAS_POST.items():
                if alias in data and champ not in data:
                    data[champ] = data[alias]
            for champ in CHAMPS_MODIFIABLES:
                if champ not in data and champ not in OBLIGATOIRES and instance is not None:
                    valeur = getattr(instance, champ)
                    data[champ] = '' if valeur is None else str(valeur)
        super().__init__(data, files, instance=instance, **kwargs)
        self.fields['nom'].required = True


def modifier_membre(auteur, membre, donnees, fichiers=None):
    """Modifie `membre` (F-21). Retourne (formulaire, modifie). 403 si `auteur` ne peut pas modifier ce membre.

    Formulaire invalide : rien n'est enregistré. Une modification réelle est journalisée (avant / après, valeurs
    d'identité masquées) ; aucun changement : rien n'est écrit.
    """
    if not droits_membre(auteur, membre)['peut_modifier']:
        raise PermissionDenied
    avant = instantane(membre, CHAMPS_MODIFIABLES)
    formulaire = MembreModificationForm(donnees, fichiers, instance=membre)
    if not formulaire.is_valid():
        return formulaire, False
    if not formulaire.changed_data:
        return formulaire, False
    formulaire.save()
    apres = instantane(membre, CHAMPS_MODIFIABLES)
    changes = [c for c in formulaire.changed_data if c in CHAMPS_MODIFIABLES]
    masque = lambda dic: {c: ('***' if c in MASQUES_AU_JOURNAL else dic[c]) for c in changes}  # noqa: E731
    journaliser(auteur, JournalAction.Action.MODIFICATION, membre, avant=masque(avant), apres=masque(apres),
                motif='photo remplacée' if 'photo' in formulaire.changed_data else '')
    return formulaire, True


def demander_modification(auteur, membre, texte):
    """Enregistre une demande de modification (notification) ; 403 sans droit. Retourne 'creee', 'existante' ou 'vide'."""
    if not droits_membre(auteur, membre)['peut_demander_modification']:
        raise PermissionDenied
    texte = (texte or '').strip()
    if not texte:
        return 'vide'
    _, creee = Notification.objects.get_or_create(
        user=auteur, membre=membre, titre='Demande de modification', description=texte)
    return 'creee' if creee else 'existante'
