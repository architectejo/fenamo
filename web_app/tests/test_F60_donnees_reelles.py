"""Interrupteur « données réelles » du site : faux par défaut, SU seul, journalisé, purge ; l'API refuse (403) tout point d'accès de données
quand il est faux et garde la configuration minimale disponible."""
import json
from pathlib import Path

import pytest
from django.core.exceptions import PermissionDenied, ValidationError
from django.test import Client
from django.urls import reverse

from api.services import cles
from compte import roles
from compte.models import JournalAction
from tests.test_F02_droits_roles import _compte, _nommer, acteurs_roles, monde  # noqa: F401
from tests.test_plan_url import hachage_rapide, jeu  # noqa: F401
from virtrine.models import Article, Config
from virtrine.services import contenu, purge

A = JournalAction.Action
POINTS_DE_DONNEES = ['/api/v1/site/articles/', '/api/v1/site/articles/un-slug/', '/api/v1/site/galerie/', '/api/v1/site/comite/',
                     '/api/v1/site/coordinations/', '/api/v1/site/statistiques/']
FIXTURE = Path(__file__).resolve().parent.parent.parent / 'website' / 'tests' / 'fixtures' / 'api_site_inactif.json'


@pytest.fixture(autouse=True)
def media_temporaire(settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path


@pytest.fixture
def cle(db):
    return cles.creer_cle('Site public')[1]


def get(client, chemin, cle):
    return client.get(chemin, HTTP_X_SITE_KEY=cle)


def test_F60_defaut_faux(db):
    assert Config.instance().donnees_reelles_actif is False


@pytest.mark.parametrize('chemin', POINTS_DE_DONNEES)
def test_F60_points_de_donnees_403_inactif_quand_faux(client, cle, chemin):
    reponse = get(client, chemin, cle)
    assert reponse.status_code == 403 and json.loads(reponse.content) == {'statut': 'inactif', 'detail': 'Données réelles désactivées.'}
    assert reponse['Content-Type'].startswith('application/json') and reponse['Cache-Control'] == 'no-cache' and not reponse.cookies


def test_F60_aucune_donnee_reelle_meme_avec_un_contenu_publie(client, cle, db):
    from django.utils import timezone
    Article.objects.create(titre='Titre réel secret', statut='publie', date_publication=timezone.now())
    corps = get(client, '/api/v1/site/articles/', cle).content.decode()
    assert 'secret' not in corps and 'resultats' not in corps


def test_F60_config_toujours_disponible_et_minimale_quand_faux(client, cle, db):
    config = Config.instance()
    config.nom, config.adresse, config.gmail, config.slogant = 'Nom réel', 'Adresse réelle secrète', 'reel@example.invalid', 'Devise réelle'
    config.save()
    reponse = get(client, '/api/v1/site/config/', cle)
    assert reponse.status_code == 200
    assert json.loads(reponse.content) == {'nom': 'FENAMO-RDC', 'devise': 'Unité, Discipline et Progrès', 'langues_actives': ['fr'],
                                          'donnees_reelles': False}
    assert 'secrète' not in reponse.content.decode() and 'reel@' not in reponse.content.decode()


def test_F60_config_complete_et_drapeau_vrai_quand_actif(client, cle, db):
    config = Config.instance()
    config.donnees_reelles_actif = True
    config.save()
    donnees = json.loads(get(client, '/api/v1/site/config/', cle).content)
    assert donnees['donnees_reelles'] is True and 'telephones' in donnees and 'partenaires' in donnees
    assert get(client, '/api/v1/site/statistiques/', cle).status_code == 200


def test_F60_cle_et_methode_controlees_avant_l_interrupteur(client, cle, db):
    assert client.get('/api/v1/site/articles/').status_code == 401  # sans clé : 401, pas 403
    assert client.post('/api/v1/site/articles/', HTTP_X_SITE_KEY=cle).status_code == 405
    assert get(client, '/api/v1/site/inexistant/', cle).status_code == 404  # route inconnue : toujours 404


def test_F60_contrat_avec_la_fixture_du_site(client, cle, db):
    if not FIXTURE.exists():
        pytest.skip('fixture du site absente')
    contrat = json.loads(FIXTURE.read_text(encoding='utf-8'))
    assert json.loads(get(client, '/api/v1/site/config/', cle).content) == contrat['config']['body']
    reponse = get(client, '/api/v1/site/comite/', cle)
    assert reponse.status_code == contrat['autres']['status'] and json.loads(reponse.content) == contrat['autres']['body']


# ---------------------------------------------------------------- service

def test_F60_service_super_utilisateur_seul(monde, acteurs_roles):
    editeur = _nommer(monde, roles.ED)
    for compte in (editeur, acteurs_roles['PR'], acteurs_roles['VA'], acteurs_roles['VI']):
        with pytest.raises(PermissionDenied):
            contenu.definir_donnees_reelles(compte, True)
    assert Config.instance().donnees_reelles_actif is False


def test_F60_service_journal_idempotence_et_motif(monde):
    su = monde['compte']
    contenu.definir_donnees_reelles(su, True, '  Mise en ligne officielle  ')
    ligne = JournalAction.objects.get(action=A.MODIFICATION, apres__champs_modifies=['donnees_reelles_actif'])
    assert ligne.auteur == su and ligne.avant == {'donnees_reelles_actif': False} and ligne.apres['donnees_reelles_actif'] is True
    assert ligne.motif == 'Mise en ligne officielle'
    contenu.definir_donnees_reelles(su, True)  # inchangé : rien de plus
    assert JournalAction.objects.filter(apres__champs_modifies=['donnees_reelles_actif']).count() == 1
    contenu.definir_donnees_reelles(su, False)
    assert Config.instance().donnees_reelles_actif is False
    assert JournalAction.objects.filter(apres__champs_modifies=['donnees_reelles_actif']).count() == 2
    with pytest.raises(ValidationError):
        contenu.definir_donnees_reelles(su, True, 'm' * 501)


def test_F60_service_demande_la_purge_apres_le_commit(monde, monkeypatch, django_capture_on_commit_callbacks):
    appels = []
    monkeypatch.setattr(purge, 'envoyer_purge', lambda: appels.append(1) or True)
    with django_capture_on_commit_callbacks(execute=False) as rappels:
        contenu.definir_donnees_reelles(monde['compte'], True)
    assert appels == [] and len(rappels) == 1
    rappels[0]()
    assert appels == [1]
    with django_capture_on_commit_callbacks(execute=False) as rien:
        contenu.definir_donnees_reelles(monde['compte'], True)  # inchangé : pas de purge
    assert rien == []


# ---------------------------------------------------------------- vue

def test_F60_vue_super_utilisateur_seul_post_csrf_et_htmx(client, monde, acteurs_roles):
    url = reverse('donnees-reelles')
    client.force_login(acteurs_roles['PR'])
    assert client.get(url).status_code == 403 and client.post(url, {'actif': '1'}).status_code == 403
    assert Config.instance().donnees_reelles_actif is False
    client.force_login(monde['compte'])
    modale = client.get(url)
    assert modale.status_code == 200 and modale.context['cible'] is True and modale.context['actif'] is False
    protege = Client(enforce_csrf_checks=True)
    protege.force_login(monde['compte'])
    assert protege.post(url, {'actif': '1'}).status_code == 403 and Config.instance().donnees_reelles_actif is False  # CSRF exigé
    ok = client.post(url, {'actif': '1', 'motif': 'Ouverture'}, HTTP_HX_REQUEST='true')
    assert ok.status_code == 204 and 'donneesReellesModifiees' in ok['HX-Trigger'] and 'toast' in ok['HX-Trigger']
    assert Config.instance().donnees_reelles_actif is True
    assert client.post(url, {'actif': '0'}).status_code == 302 and Config.instance().donnees_reelles_actif is False  # page complète
    erreur = client.post(url, {'actif': '1', 'motif': 'm' * 501})
    assert erreur.status_code == 422 and Config.instance().donnees_reelles_actif is False


def test_F60_get_sans_effet_et_cle_est_su_dans_le_menu(client, monde, acteurs_roles):
    from compte.services.droits import droits_menu
    client.force_login(monde['compte'])
    avant = JournalAction.objects.count()
    client.get(reverse('donnees-reelles'))
    assert Config.instance().donnees_reelles_actif is False and JournalAction.objects.count() == avant
    assert droits_menu(monde['compte'])['est_su'] is True and droits_menu(acteurs_roles['PR'])['est_su'] is False
