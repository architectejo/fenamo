"""F-28 : codes d'état en snake_case dans les classes CSS, libellés des puces issus de la table unique, maquettes cohérentes."""
import re
from pathlib import Path

import pytest
from django.urls import reverse

from coptapp.services.etats import ETATS, LIBELLES
from tests.test_F21_matrice_routes import acteurs  # noqa: F401
from tests.test_plan_url import hachage_rapide, jeu  # noqa: F401

RACINE = Path(__file__).resolve().parent.parent
CLASSE = re.compile(r'etat--([A-Za-z0-9_-]+)')


def test_F28_css_definit_une_classe_par_code_snake_case():
    css = (RACINE / 'static' / 'css' / 'app.css').read_text(encoding='utf-8')
    definis = set(CLASSE.findall(css))
    assert set(ETATS) <= definis, sorted(set(ETATS) - definis)
    assert not [c for c in definis if '-' in c], 'classe CSS d\'état en kebab-case : ' + str(sorted(definis))


def test_F28_maquettes_utilisent_les_memes_codes_et_libelles():
    trouves = {}
    for page in (RACINE / 'docs' / 'design' / 'maquettes').glob('*.html'):
        texte = page.read_text(encoding='utf-8')
        for m in re.finditer(r'<span class="etat etat--([A-Za-z0-9_-]+)">(.*?)</span></span>|'
                             r'<span class="etat etat--([A-Za-z0-9_-]+)">(?:<svg.*?</svg>)?([^<]+)</span>', texte, re.S):
            code = m.group(1) or m.group(3)
            trouves.setdefault(code, set()).add(page.name)
    assert trouves, 'aucune puce d\'état trouvée dans les maquettes'
    inconnus = {c: p for c, p in trouves.items() if c not in ETATS}
    assert not inconnus, f'codes de maquette absents de la table des états : {inconnus}'


def test_F28_maquette_composants_libelles_egaux_a_la_table():
    texte = (RACINE / 'docs' / 'design' / 'maquettes' / 'composants.html').read_text(encoding='utf-8')
    for code, libelle in LIBELLES.items():
        m = re.search(r'etat--%s">(?:.*?</span>|<svg.*?</svg>)?\s*([^<]+)</span>' % code, texte, re.S)
        assert m and m.group(1).strip() == str(libelle), (code, m and m.group(1))


@pytest.mark.parametrize('etat', ['saisi', 'valide_antenne', 'actif'])
def test_F28_fiche_et_liste_rendent_code_snake_case_et_libelle_de_la_table(client, acteurs, etat):
    m = acteurs['membre']
    m.is_validate1 = etat in ('valide_antenne', 'actif')
    m.is_validate2 = etat in ('valide_antenne', 'actif')
    m.is_validate3 = etat == 'actif'
    m.save()
    client.force_login(acteurs['comptes']['su'])
    for url in (reverse('membre-view', kwargs={'id': m.id}), reverse('liste-membre')):
        for en_tete in ({}, {'HTTP_HX_REQUEST': 'true'}):
            html = client.get(url, **en_tete).content.decode()
            codes = set(CLASSE.findall(html))
            assert not [c for c in codes if '-' in c], (url, codes)
            assert 'etat--' + etat in html, (url, etat, codes)
            assert str(LIBELLES[etat]) in html
