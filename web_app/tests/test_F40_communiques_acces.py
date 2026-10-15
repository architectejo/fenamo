"""F-40 : complément d'accès (anonyme redirigé, pagination hors limites, aucune écriture en GET)."""
import pytest
from django.test import Client
from django.urls import reverse

from coptapp.models import Communique, LectureCommunique
from coptapp.services import communiques as S
from tests.test_F40_communiques import equipe  # noqa: F401
from tests.test_F02_droits_roles import acteurs_roles, monde  # noqa: F401
from tests.test_plan_url import hachage_rapide, jeu  # noqa: F401


def test_F40_anonyme_redirige_sur_toutes_les_vues(monde, equipe):
    c = S.publier(equipe['ED'], 'Public', 'm')
    avant = Communique.objects.count()
    anonyme = Client()
    for nom, kw in (('list-message', {}), ('message', {}), ('communique', {'id': c.pk}), ('communique-lu', {'id': c.pk})):
        for methode in ('get', 'post'):
            r = getattr(anonyme, methode)(reverse(nom, kwargs=kw))
            assert r.status_code in (302, 403) and (r.status_code == 403 or 'login' in r['Location'] or 'connexion' in r['Location'].lower()), (nom, methode)
    assert not LectureCommunique.objects.exists() and Communique.objects.count() == avant


def test_F40_pagination_hors_limites_sans_erreur(client, monde, equipe):
    S.publier(equipe['ED'], 'Un', 'm')
    client.force_login(equipe['VA_P'])
    for page in ('999', '0', '-1', 'abc'):
        assert client.get(reverse('list-message'), {'page': page}).status_code in (200, 404)


def test_F40_get_sur_publication_ne_cree_rien(client, monde, equipe):
    avant = Communique.objects.count()
    client.force_login(equipe['ED'])
    client.get(reverse('message'))
    assert Communique.objects.count() == avant
