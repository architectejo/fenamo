"""Sécurité M1 : aucune valeur POST dans une expression Alpine (x-data) des modales de l'écran Utilisateurs (valeurs lues dans data-*)."""
import re
from datetime import date

from django.urls import reverse

from compte import roles
from compte.models import Compte, Nomination
from coptapp.models import Membre
from tests.test_plan_url import hachage_rapide, jeu  # noqa: F401

HOSTILE = "x'+alert(1)+'"


def _expressions_alpine(html):
    """Contenu de tous les attributs x-data, x-init, x-bind, @click et :attr : ce que le navigateur exécute."""
    return re.findall(r'(?:x-data|x-init|x-effect|@[\w.:-]+|:[\w-]+)="([^"]*)"', html)


def _aucune_injection(html):
    for expression in _expressions_alpine(html):
        assert 'alert(1)' not in expression, expression
        assert "x'+" not in expression, expression
    assert HOSTILE not in html  # l'apostrophe est échappée dans les attributs data-*


def _pr(jeu):
    pr = Compte.objects.create_user('le-pr', password='x')
    Nomination.objects.create(compte=pr, role=roles.PR, nomme_par=jeu['compte'])
    return pr


def test_F02_nommer_valeur_hostile_pas_dans_une_expression_alpine(client, jeu):
    pr = _pr(jeu)
    membre = Membre.objects.create(nom=HOSTILE, date_naissance=date(1990, 1, 1), province=jeu['province'], antenne=jeu['antenne'],
                                   structure=jeu['association'], etat='actif')
    client.force_login(pr)
    for donnees in ({'membre': membre.id, 'role': HOSTILE, 'fin': HOSTILE, 'debut': HOSTILE}, {'role': 'AT', 'fin': HOSTILE}):
        r = client.post(reverse('utilisateurs-nommer'), donnees)
        assert r.status_code in (403, 422)
        _aucune_injection(r.content.decode())
    r = client.get(reverse('utilisateurs-nommer'), {'membre': membre.id})
    _aucune_injection(r.content.decode())


def test_F06_changer_externe_desactiver_valeurs_hostiles(client, jeu):
    pr = _pr(jeu)
    agent = Compte.objects.create_user('agent-x', password='x')
    Nomination.objects.create(compte=agent, role=roles.AT, antenne=jeu['antenne'], nomme_par=pr)
    client.force_login(pr)
    r = client.post(reverse('utilisateurs-role', kwargs={'id': agent.id}), {'role': HOSTILE, 'fin': HOSTILE, 'motif': HOSTILE})
    assert r.status_code == 422
    _aucune_injection(r.content.decode())
    r = client.post(reverse('utilisateurs-externe'), {'type': HOSTILE, 'portee': HOSTILE, 'username': HOSTILE})
    assert r.status_code in (403, 422)
    _aucune_injection(r.content.decode())
    r = client.post(reverse('utilisateurs-desactiver', kwargs={'id': agent.id}), {'motif': HOSTILE * 80})
    assert r.status_code == 422
    _aucune_injection(r.content.decode())
