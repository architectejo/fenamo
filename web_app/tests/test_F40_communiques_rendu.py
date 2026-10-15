"""F-40 : rendu de l'interface des communiqués (bouton selon le rôle, échappement, badge, marquage lu à l'ouverture)."""
import pytest
from django.urls import reverse

from coptapp.services import communiques as S
from tests.test_F02_droits_roles import _compte, _nommer, acteurs_roles, monde  # noqa: F401
from tests.test_F40_communiques import equipe  # noqa: F401
from tests.test_plan_url import hachage_rapide, jeu  # noqa: F401

pytestmark = pytest.mark.django_db
INJECTION = '<script>alert(1)</script>'


def _html(reponse):
    return reponse.content.decode()


def test_F40_bouton_publier_seulement_pour_editeur_et_super_utilisateur(client, monde, equipe):
    url = reverse('list-message')
    client.force_login(equipe['ED'])
    assert reverse('message') in _html(client.get(url))
    for cle in ('PR', 'VA_P', 'AT_P', 'VI_NAT'):
        client.force_login(equipe[cle])
        reponse = client.get(url)
        assert reponse.status_code == 200 and 'Publier un communiqué' not in _html(reponse), cle


def test_F40_contenu_utilisateur_echappe_liste_et_lecture(client, monde, equipe):
    c = S.publier(equipe['ED'], INJECTION, INJECTION + '\nligne')
    client.force_login(equipe['VA_P'])
    liste = _html(client.get(reverse('list-message')))
    lecture = _html(client.get(reverse('communique', kwargs={'id': c.pk})))
    for page in (liste, lecture):
        assert INJECTION not in page and '&lt;script&gt;' in page


def test_F40_liste_met_en_evidence_les_non_lus_et_fragment_sans_coque(client, monde, equipe):
    S.publier(equipe['ED'], 'A lire', 'm')
    client.force_login(equipe['VA_P'])
    page = _html(client.get(reverse('list-message')))
    assert 'non-lu' in page and 'id="liste-zone"' in page and 'Non lu' in page
    fragment = _html(client.get(reverse('list-message'), HTTP_HX_REQUEST='true'))
    assert '<html' not in fragment and 'non-lu' in fragment
    vide = _html(client.get(reverse('list-message'), {'q': 'introuvable-xyz'}, HTTP_HX_REQUEST='true'))
    assert 'Aucun communiqué ne correspond' in vide


def test_F40_lecture_marque_lu_a_l_ouverture_seulement_si_non_lu(client, monde, equipe):
    c = S.publier(equipe['ED'], 'Titre', 'Texte')
    url_lu = reverse('communique-lu', kwargs={'id': c.pk})
    client.force_login(equipe['VA_P'])
    assert url_lu in _html(client.get(reverse('communique', kwargs={'id': c.pk})))
    client.post(url_lu, HTTP_HX_REQUEST='true')
    assert url_lu not in _html(client.get(reverse('communique', kwargs={'id': c.pk})))


def test_F40_badge_dans_la_barre_haute_et_fragment(client, monde, equipe):
    S.publier(equipe['ED'], 'Badge', 'm')
    client.force_login(equipe['VA_P'])
    page = _html(client.get(reverse('tableau-bord')))
    assert reverse('communique-compteur') in page and 'communiquesMaj from:body' in page and 'every 120s' in page
    badge = _html(client.get(reverse('communique-compteur'), HTTP_HX_REQUEST='true'))
    assert 'compteur-pastille' in badge and 'data-nb="1"' in badge and ' hidden' not in badge.split('>')[0]
    client.force_login(equipe['ED'])  # l'auteur ne compte pas ses propres communiqués
    assert ' hidden' in _html(client.get(reverse('communique-compteur'), HTTP_HX_REQUEST='true')).split('>')[0]


def test_F40_modale_publication_ciblage_et_compteur(client, monde, equipe):
    client.force_login(equipe['ED'])
    modale = _html(client.get(reverse('message'), HTTP_HX_REQUEST='true'))
    assert 'value="national"' in modale and 'data-compte-caracteres' in modale and 'maxlength="120"' in modale and 'maxlength="5000"' in modale
    erreur = client.post(reverse('message'), {'titre': '', 'message': 'texte conservé'}, HTTP_HX_REQUEST='true')
    assert erreur.status_code == 422 and 'texte conservé' in _html(erreur)
