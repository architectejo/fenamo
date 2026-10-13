"""F-28 : puces de la liste des membres au pluriel, un seul code d'état (snake_case) dans les liens et les filtres."""
import re

from django.urls import reverse

from coptapp.services.etats import ETATS, LIBELLES
from fenamo.balises import LIBELLES_PLURIELS, libelle_pluriel_etat
from tests.test_plan_url import hachage_rapide, jeu  # noqa: F401


def test_F28_pluriels_couvrent_exactement_les_codes_du_service():
    assert set(LIBELLES_PLURIELS) == set(ETATS)
    assert libelle_pluriel_etat('saisi') == 'Saisis' and libelle_pluriel_etat('actif') == 'Actifs'
    assert libelle_pluriel_etat('inconnu') == 'inconnu'  # repli sur le code, jamais d'erreur


def test_F28_puces_au_pluriel_et_valeurs_snake_case(client, jeu):
    client.force_login(jeu['compte'])
    html = client.get(reverse('liste-membre')).content.decode()
    for code in ('saisi', 'valide_antenne', 'actif'):
        assert f'<input type="radio" name="etat" value="{code}"' in html
        assert f'<span>{libelle_pluriel_etat(code)}</span>' in html
        assert f'<span>{LIBELLES[code]}</span>' not in html  # singulier de la table : pas sur les puces
    assert 'Validés antenne' in html


def test_F28_aucun_lien_de_la_liste_avec_etat_a_tiret(client, jeu):
    client.force_login(jeu['compte'])
    for params in ({}, {'etat': 'valide_antenne'}, {'etat': 'actif', 'q': 'a'}):
        for en_tete in ({}, {'HTTP_HX_REQUEST': 'true'}):
            html = client.get(reverse('liste-membre'), params, **en_tete).content.decode()
            assert not re.search(r'etat=[a-z_]*-[a-z_-]*', html), (params, en_tete)
            assert not re.search(r'name="etat" value="[a-z_]*-', html)
