"""F-23 : droit de valider PAR MEMBRE dans la liste (étape précédente exigée, jamais sa propre fiche), sans N+1."""

from coptapp.models import Membre
from coptapp.services.membres import lister_membres
from tests.test_F35_droits_engins_famille import _compte, saisie  # noqa: F401
from tests.test_plan_url import hachage_rapide, jeu  # noqa: F401


def test_F23_liste_peut_valider_par_membre(saisie):
    Membre.objects.create(nom='Etape deux', etat='valide_antenne')
    Membre.objects.create(nom='Etape un')
    p2 = _compte('p2l', privilege2=True)
    attendu = {m.nom: m.peut_valider for m in lister_membres(p2, {}).page_obj}
    assert attendu['Etape un'] is True and attendu['Etape deux'] is False  # étape précédente exigée
    p3 = _compte('p3l', privilege3=True)
    attendu = {m.nom: m.peut_valider for m in lister_membres(p3, {}).page_obj}
    assert attendu['Etape deux'] is True
    attendu = {m.nom: m.peut_valider for m in lister_membres(saisie['compte'], {}).page_obj}
    assert attendu['Etape un'] is True


def test_F23_liste_sans_requete_supplementaire_par_membre(saisie, django_assert_max_num_queries):
    for i in range(30):
        Membre.objects.create(nom=f'M{i:02d}', etat='valide_antenne')
    p3 = _compte('p3q', privilege3=True)
    with django_assert_max_num_queries(6):
        page = lister_membres(p3, {}).page_obj
        assert len([m for m in page if m.peut_valider]) == 25
