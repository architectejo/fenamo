"""F-07 côté API : contrat exact de la réponse « service suspendu » (503 JSON), en-têtes, méthodes, absence de fuite, vue de santé."""
import json

import pytest

from compte.services import verrou_application as V
from tests.test_F02_droits_roles import acteurs_roles, monde  # noqa: F401
from tests.test_plan_url import hachage_rapide, jeu  # noqa: F401

MESSAGE = 'Maintenance : retour demain.'
SECRET = 'Secret interne XYZ'
CLES_SUSPENDU = {'statut', 'detail', 'message'}


def _verrouiller(monde):
    return V.verrouiller(monde['compte'], MESSAGE, SECRET)


def test_F07_api_suspendu_en_tetes(client, monde):
    _verrouiller(monde)
    reponse = client.get('/api/v1/site/config/')
    assert reponse.status_code == 503
    assert reponse['Content-Type'].startswith('application/json')
    assert 'no-store' in reponse['Cache-Control']
    assert 'Set-Cookie' not in reponse.headers and not reponse.cookies  # aucune session ni cookie


@pytest.mark.parametrize('methode', ['get', 'post', 'put', 'patch', 'delete', 'options'])
def test_F07_api_suspendue_toutes_methodes(client, monde, methode):
    _verrouiller(monde)
    reponse = getattr(client, methode)('/api/v1/site/contact/')
    assert reponse.status_code == 503
    assert json.loads(reponse.content) == {'statut': 'suspendu', 'detail': 'Service suspendu.', 'message': MESSAGE}


@pytest.mark.parametrize('chemin', [
    '/api/v1/site/config/', '/api/v1/site/verifier/membre/MBR-000001/', '/api/v1/site/paiement/',
    '/api/v1/site/inexistant/', '/api/v1/', '/api/v2/site/config/', '/api/',
])
def test_F07_api_suspendue_toutes_routes_sans_fuite(client, monde, chemin):
    _verrouiller(monde)
    reponse = client.get(chemin)
    assert reponse.status_code == 503
    donnees = json.loads(reponse.content)
    assert set(donnees) == CLES_SUSPENDU
    corps = reponse.content.decode()
    assert SECRET not in corps and monde['compte'].username not in corps
    for interdit in ('motif', 'auteur', 'depuis', 'par'):
        assert interdit not in donnees


def test_F07_api_suspendue_avec_cle_du_site_ou_session_non_su(client, monde, acteurs_roles):
    _verrouiller(monde)
    reponse = client.get('/api/v1/site/config/', HTTP_X_FENAMO_SITE_KEY='cle-quelconque')
    assert reponse.status_code == 503  # le verrou passe avant la clé : aucune réponse métier
    client.force_login(acteurs_roles['PR'])
    reponse = client.get('/api/v1/site/config/')
    assert reponse.status_code == 503 and '_auth_user_id' not in client.session


def test_F07_sante_suspendue_en_tetes_et_corps_exact(client, monde):
    _verrouiller(monde)
    for url in ('/api/v1/sante/', '/api/v1/sante'):
        reponse = client.get(url)
        assert reponse.status_code == 200
        assert reponse['Content-Type'].startswith('application/json')
        assert 'no-store' in reponse['Cache-Control']
        assert json.loads(reponse.content) == {'statut': 'suspendu', 'version': 'v1'}
        assert MESSAGE not in reponse.content.decode()  # la santé n'expose pas le message


def test_F07_api_retablie_apres_deverrouillage(client, monde):
    _verrouiller(monde)
    assert client.get('/api/v1/site/config/').status_code == 503
    V.deverrouiller(monde['compte'])
    assert client.get('/api/v1/sante/').json() == {'statut': 'ok', 'version': 'v1'}
    assert client.get('/api/v1/site/config/').status_code != 503
