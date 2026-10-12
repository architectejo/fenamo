"""Gabarits qui appellent `.photo.url` : chaque page doit répondre 200 pour un membre et un engin sans photo.

Vérifié au lot 1 : les neuf gabarits visés ont tous la garde `{% if x.photo %}` (les essais xfail
non stricts prévus ont tous réussi, ils sont donc devenus des tests ordinaires).
"""
import re
from pathlib import Path

from django.conf import settings
import pytest

from tests.test_plan_url import hachage_rapide, jeu  # noqa: F401

# (gabarit concerné, méthode, adresse construite depuis le jeu, données POST)
CAS = [
    ('antenne-view', 'get', lambda j: f"/antennes/{j['antenne'].id}/", None),
    ('index', 'get', lambda j: '/', None),
    ('list-message', 'get', lambda j: '/communiques/', None),
    ('membre-list', 'get', lambda j: '/membres/', None),
    ('membre', 'get', lambda j: f"/membres/{j['membre'].id}/", None),
    ('message-view', 'get', lambda j: f"/communiques/{j['communique'].id}/", None),
    ('moto-view', 'get', lambda j: f"/motos/{j['moto'].id}/", None),
    ('resultats-membre', 'post', lambda j: '/recherche/', {'search': '1', 'champ': 'Fictif'}),
    ('resultats-engin', 'post', lambda j: '/recherche/', {'search': '1', 'champ': '001PF'}),
    ('ville-view', 'get', lambda j: f"/villes/{j['ville'].id}/", None),
]


@pytest.mark.parametrize('nom,methode,adresse,donnees', CAS, ids=[c[0] for c in CAS])
def test_gabarit_sans_photo_repond_200(client, jeu, nom, methode, adresse, donnees):
    assert not jeu['membre'].photo and not jeu['moto'].photo
    client.force_login(jeu['compte'])
    cible = adresse(jeu)
    reponse = client.post(cible, donnees) if methode == 'post' else client.get(cible)
    assert reponse.status_code == 200, nom


def test_aucun_photo_url_sans_garde_dans_les_gabarits():
    """Chaque `X.photo.url` est précédé, dans les 3 lignes qui le précèdent, d'un `{% if X.photo %}`."""
    fautifs = []
    for chemin in Path(settings.BASE_DIR).glob('*/templates/**/*.html'):
        lignes = chemin.read_text(encoding='utf-8').splitlines()
        for i, ligne in enumerate(lignes):
            if ligne.strip().startswith('<!--'):
                continue
            for m in re.finditer(r'\{\{\s*([\w.]+)\.photo\.url', ligne):
                garde = f"{m.group(1)}.photo"
                if not any('{% if' in l and garde in l for l in lignes[max(0, i - 3):i + 1]):
                    fautifs.append(f"{chemin.name}:{i + 1}")
    assert fautifs == [], f"photo.url sans garde : {fautifs}"
