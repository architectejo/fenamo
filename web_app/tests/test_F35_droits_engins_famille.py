"""F-35 / F-26 : modifier et supprimer engins et famille (agent avant la 1re validation, rôles supérieurs ensuite)."""
from datetime import date

import pytest
from django.urls import reverse

from compte.models import Compte
from coptapp.models import Famille, Membre, Moto
from compte.services.droits import droits_membre
from tests.test_plan_url import hachage_rapide, jeu  # noqa: F401

CLES = ('peut_modifier_engin', 'peut_supprimer_engin', 'peut_modifier_famille', 'peut_supprimer_famille')
ENGIN = {k: 'x' for k in ('plaque', 'chassie', 'moteur', 'marque', 'couleur')}
FAM = {'nom': 'Proche', 'qualite': 'ENFANT', 'genre': 'F', 'annee': '2010'}


def _compte(nom, **kw):
    return Compte.objects.create_user(nom, password='x', **kw)


@pytest.fixture
def saisie(jeu):
    """Un membre saisi par l'agent, dans l'association du jeu, avec un engin et un proche."""
    agent = _compte('agent', privilege1=True)
    jeu['association'].users.add(agent)
    membre = Membre.objects.create(nom='Saisie agent', user=agent, structure=jeu['association'])
    moto = Moto.objects.create(proprietaire=membre, abonnement=date(2030, 1, 1), numero='500AA')
    famille = Famille.objects.create(membre=membre, beneficiere='Proche')
    return {**jeu, 'agent': agent, 'membre': membre, 'moto': moto, 'famille': famille}


def _vrais(droits):
    return {c for c in CLES if droits[c]}


def test_F35_agent_modifie_et_supprime_avant_la_premiere_validation(saisie):
    assert _vrais(droits_membre(saisie['agent'], saisie['membre'])) == set(CLES)


def test_F35_agent_perd_la_main_apres_la_premiere_validation(saisie):
    Membre.objects.filter(pk=saisie['membre'].pk).update(is_validate2=True)
    membre = Membre.objects.get(pk=saisie['membre'].pk)
    droits = droits_membre(saisie['agent'], membre)
    assert _vrais(droits) == set() and droits['peut_ajouter_engin'] and droits['peut_ajouter_famille']  # ajouter reste permis


def test_F35_roles_superieurs_gardent_la_main(saisie):
    Membre.objects.filter(pk=saisie['membre'].pk).update(is_validate2=True)
    membre = Membre.objects.get(pk=saisie['membre'].pk)
    p3 = _compte('p3e', privilege3=True)
    saisie['association'].users.add(p3)
    assert _vrais(droits_membre(p3, membre)) == set(CLES)
    assert _vrais(droits_membre(saisie['compte'], membre)) == set(CLES)
    assert _vrais(droits_membre(_compte('p5e', privilege5=True), membre)) == set(CLES)
    assert _vrais(droits_membre(_compte('p4e', privilege4=True, privilege3=True), membre)) == set()


def test_F35_vues_exigent_le_droit_precis(client, saisie):
    client.force_login(saisie['agent'])
    assert client.get(reverse('edit-moto', args=[saisie['moto'].id])).status_code == 200
    assert client.post(reverse('edit-family', args=[saisie['famille'].id]), FAM).status_code == 200
    Membre.objects.filter(pk=saisie['membre'].pk).update(is_validate2=True)
    assert client.get(reverse('edit-moto', args=[saisie['moto'].id])).status_code == 403
    assert client.post(reverse('edit-moto', args=[saisie['moto'].id]), ENGIN).status_code == 403
    assert client.post(reverse('delete-moto', args=[saisie['moto'].id])).status_code == 403
    assert client.post(reverse('edit-family', args=[saisie['famille'].id]), FAM).status_code == 403
    assert client.post(reverse('delete-family', args=[saisie['famille'].id])).status_code == 403
    assert Moto.objects.get(pk=saisie['moto'].pk).is_delete is False
    assert Famille.objects.filter(pk=saisie['famille'].pk).exists()
    assert client.get(reverse('add-moto', args=[saisie['membre'].id])).status_code == 200  # ajouter reste permis
    client.force_login(saisie['compte'])
    assert client.post(reverse('delete-moto', args=[saisie['moto'].id])).status_code == 302
    assert client.post(reverse('delete-family', args=[saisie['famille'].id])).status_code == 302


def test_F26_agent_supprime_le_proche_de_sa_saisie_avant_validation(client, saisie):
    client.force_login(saisie['agent'])
    assert client.post(reverse('delete-family', args=[saisie['famille'].id])).status_code == 302
    assert not Famille.objects.filter(pk=saisie['famille'].pk).exists()


def test_F35_membre_supprime_ni_ajout_ni_modification_ni_suppression(saisie):
    from compte.services.droits import etapes_a_valider
    Membre.objects.filter(pk=saisie['membre'].pk).update(is_delete=True)
    membre = Membre.objects.get(pk=saisie['membre'].pk)
    cles = CLES + ('peut_ajouter_engin', 'peut_ajouter_famille', 'peut_modifier', 'peut_valider', 'peut_demander_modification')
    for compte in (saisie['compte'], _compte('p5d', privilege5=True), saisie['agent']):
        droits = droits_membre(compte, membre)
        assert not any(droits[c] for c in cles), compte.username
        assert etapes_a_valider(compte, membre) == []
    assert droits_membre(saisie['compte'], membre)['peut_restaurer']  # seule la restauration reste
