"""T6 : plan d'URL (cahier des charges web § 7.3 et annexe B), sur un jeu d'essai fictif."""
from datetime import date

import pytest
from django.urls import NoReverseMatch, resolve, reverse

from compte.models import Compte
from coptapp.models import (
    AssociationMembre, Antenne, Communique, Famille, Membre, Moto, Province, Ville,
)
from virtrine.models import Article, Contact


@pytest.fixture(autouse=True)
def hachage_rapide(settings):
    settings.PASSWORD_HASHERS = ['django.contrib.auth.hashers.MD5PasswordHasher']


@pytest.fixture
def jeu(db):
    province = Province.objects.create(nom="Province fictive", sigle="PF")
    ville = Ville.objects.create(nom="Antenne fictive", province=province)
    association = AssociationMembre.objects.create(
        nom="Association fictive", sigle="AF", province=province, ville=ville,
        num_justice="F-0001", type_de_structure="ASBL",
    )
    antenne = Antenne.objects.create(nom="Antenne A", structure=association)
    membre = Membre.objects.create(
        nom="Membre Fictif", date_naissance=date(1990, 1, 1), province=province, ville=ville, antenne=antenne, structure=association,
    )
    compte = Compte.objects.create_superuser("admin-test", "admin@example.invalid", "mot-de-passe-test-123")
    compte.membreId = membre.id
    compte.save()
    moto = Moto.objects.create(
        proprietaire=membre, structure=association, ville=ville, province=province,
        abonnement=date(2026, 1, 1), numero="001PF",
    )
    return {
        'compte': compte, 'province': province, 'ville': ville, 'association': association,
        'antenne': antenne, 'membre': membre, 'moto': moto,
        'famille': Famille.objects.create(membre=membre, beneficiere="Proche fictif"),
        'communique': Communique.objects.create(user=compte, membre=membre, message="Message fictif"),
        'article': Article.objects.create(user=compte, titre="Article fictif"),
        'contact': Contact.objects.create(nom="Visiteur fictif"),
    }


def table(j):
    a, m, mo = j['association'].id, j['membre'].id, j['moto'].id
    return [
        # (nom de route, arguments, adresse cible)
        ('application', {}, '/connexion/'),
        ('deconnexion', {}, '/deconnexion/'),
        ('adminer', {'id': m}, f'/membres/{m}/creer-compte/'),
        ('add-user', {}, '/comptes/ajouter/'),
        ('securite', {}, '/mon-compte/securite/'),
        ('tableau-bord', {}, '/'),
        ('home-session', {}, '/associations/mon-association/'),
        ('structure-admin', {'id': a}, f'/associations/{a}/'),
        ('add-structure', {}, '/associations/ajouter/'),
        ('edit-structure', {'id': a}, f'/associations/{a}/modifier/'),
        ('str-list', {}, '/associations/'),
        ('add-province', {}, '/provinces/ajouter/'),
        ('province-view', {'id': j['province'].id}, f"/provinces/{j['province'].id}/"),
        ('add-ville', {'id': j['province'].id}, f"/provinces/{j['province'].id}/villes/ajouter/"),
        ('ville-view', {'id': j['ville'].id}, f"/villes/{j['ville'].id}/"),
        ('ville-select', {'id': a}, f'/villes/{a}/selectionner/'),
        ('add-antenne', {'id': a}, f'/associations/{a}/antennes/ajouter/'),
        ('edit-antenne', {'id': j['antenne'].id}, f"/antennes/{j['antenne'].id}/modifier/"),
        ('antenne-view', {'id': j['antenne'].id}, f"/antennes/{j['antenne'].id}/"),
        ('liste-membre', {}, '/membres/'),
        ('add-fenamo-membre', {}, '/membres/ajouter/'),
        ('add-membre', {'id': a}, f'/membres/ajouter/association/{a}/'),
        ('membre-view', {'id': m}, f'/membres/{m}/'),
        ('validate', {'id': m}, f'/membres/{m}/valider/'),
        ('delete-membre', {'id': m}, f'/membres/{m}/supprimer/'),
        ('view-user', {'id': m}, f'/membres/{m}/compte/'),
        ('add-family', {'id': m}, f'/membres/{m}/famille/ajouter/'),
        ('edit-family', {'id': j['famille'].id}, f"/famille/{j['famille'].id}/modifier/"),
        ('delete-family', {'id': j['famille'].id}, f"/famille/{j['famille'].id}/supprimer/"),
        ('add-moto', {'id': m}, f'/membres/{m}/motos/ajouter/'),
        ('view-moto', {'id': mo}, f'/motos/{mo}/'),
        ('edit-moto', {'id': mo}, f'/motos/{mo}/modifier/'),
        ('delete-moto', {'id': mo}, f'/motos/{mo}/supprimer/'),
        ('moto-attribution', {'id': m}, f'/motos/{m}/attribuer/'),
        ('recherche', {}, '/recherche/'),
        ('notifys', {}, '/notifications/'),
        ('message', {}, '/communiques/ajouter/'),
        ('list-message', {}, '/communiques/'),
        ('communique', {'id': j['communique'].id}, f"/communiques/{j['communique'].id}/"),
        ('site', {}, '/contenu-site/'),
        ('article', {'id': j['article'].id}, f"/contenu-site/articles/{j['article'].id}/modifier/"),
        ('delete-article', {'id': j['article'].id}, f"/contenu-site/articles/{j['article'].id}/supprimer/"),
        ('contact', {}, '/contenu-site/messages/'),
        ('contact-view', {'id': j['contact'].id}, f"/contenu-site/messages/{j['contact'].id}/"),
        ('config', {}, '/contenu-site/configuration/'),
        # Rattachements : trois routes distinctes (l'annexe B n'en nomme qu'une)
        ('structure-attribution', {'idM': m, 'id': a}, f'/membres/{m}/rattachement/association/{a}/'),
        ('ville-attribution', {'idM': m, 'id': j['ville'].id}, f"/membres/{m}/rattachement/ville/{j['ville'].id}/"),
        ('antenne-attribution', {'idM': m, 'id': j['antenne'].id}, f"/membres/{m}/rattachement/antenne/{j['antenne'].id}/"),
        ('ville-attr', {'sid': a, 'id': j['ville'].id}, f"/associations/{a}/ville/{j['ville'].id}/"),
    ]


# Routes qui modifient des données : POST seulement (GET -> 405).
ROUTES_POST_SEULEMENT = {
    'deconnexion', 'adminer', 'validate', 'delete-membre', 'structure-attribution', 'ville-attribution',
    'antenne-attribution', 'ville-attr', 'delete-family', 'delete-moto', 'delete-article', 'moto-attribution',
}


def test_adresses_cibles(jeu):
    for nom, kwargs, cible in table(jeu):
        assert reverse(nom, kwargs=kwargs) == cible, nom


NOMS_ECRANS = [
    'application', 'adminer', 'add-user', 'securite', 'tableau-bord', 'home-session', 'structure-admin',
    'add-structure', 'edit-structure', 'str-list', 'add-province', 'province-view', 'add-ville',
    'ville-view', 'ville-select', 'add-antenne', 'edit-antenne', 'antenne-view', 'liste-membre',
    'add-fenamo-membre', 'add-membre', 'membre-view', 'validate', 'delete-membre', 'view-user',
    'add-family', 'edit-family', 'delete-family', 'add-moto', 'view-moto', 'edit-moto',
    'delete-moto', 'moto-attribution', 'recherche', 'notifys', 'message', 'list-message',
    'communique', 'site', 'article', 'delete-article', 'contact', 'contact-view', 'config',
    'structure-attribution', 'ville-attribution', 'antenne-attribution', 'ville-attr',
]


@pytest.mark.parametrize('nom', NOMS_ECRANS)
def test_chaque_ecran_repond(client, jeu, nom):
    """Un utilisateur connecté obtient 200 ou 302 (base neuve pour chaque écran)."""
    client.force_login(jeu['compte'])
    cible = next(c for n, _, c in table(jeu) if n == nom)
    reponse = client.get(cible)
    attendus = (405,) if nom in ROUTES_POST_SEULEMENT else (200, 302)
    assert reponse.status_code in attendus, f"{nom} {cible} -> {reponse.status_code}"


def test_deconnexion_et_page_de_suppression(client, jeu):
    client.force_login(jeu['compte'])
    assert client.get('/comptes/desactiver/').status_code == 404
    assert client.get('/deconnexion/').status_code == 405
    assert client.post('/deconnexion/').status_code == 302


def test_connexion_anonyme(client, db):
    assert client.get('/connexion/').status_code == 200


def test_sante_api(client, db):
    for adresse in ('/api/v1/sante/', '/api/v1/'):
        assert client.get(adresse).json() == {'statut': 'ok', 'version': 'v1'}
    reponse = client.get('/api/v1/sante/')
    assert reponse.status_code == 200
    assert reponse.json() == {'statut': 'ok', 'version': 'v1'}
    assert client.post('/api/v1/sante/').status_code == 405
    assert client.post('/api/v1/').status_code == 405


def test_anciennes_adresses_disparues(client, jeu):
    for ancien in ('/app/', '/auth/', '/auth/session', '/admin/', '/app/deconnexion/'):
        assert client.get(ancien).status_code == 404, ancien


def test_mobapp_inchange(client, db):
    assert resolve('/mob/').url_name == 'home-mob'
    assert reverse('session', kwargs={'id': 1}) == '/mob/espace/1'
    assert reverse('register') == '/mob/register/'
    assert client.get('/mob/').status_code == 200


def test_pages_publiques_hors_racine(client, db):
    assert reverse('home') == '/ancien-site/'
    with pytest.raises(NoReverseMatch):
        reverse('config', kwargs={'id': 1})
