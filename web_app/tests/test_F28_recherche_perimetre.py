"""Recherche de la barre du haut : périmètre du compte, supprimés exclus, engins filtrés par leur membre."""
from datetime import date

from django.urls import reverse

from compte.models import Compte
from coptapp.models import Membre, Moto
from tests.test_plan_url import hachage_rapide, jeu  # noqa: F401


def _chercher(client, champ):
    return client.post(reverse('recherche'), {'champ': champ, 'search': 'search'})


def _donnees(jeu):
    actif = Membre.objects.create(nom='Dupont Actif', is_validate2=True, is_validate3=True)
    Membre.objects.create(nom='Dupont Saisi')
    Membre.objects.create(nom='Dupont Supprime', is_delete=True, is_validate2=True, is_validate3=True)
    Moto.objects.create(proprietaire=actif, abonnement=date(2030, 1, 1), numero='777AA')
    saisi = Membre.objects.get(nom='Dupont Saisi')
    Moto.objects.create(proprietaire=saisi, abonnement=date(2030, 1, 1), numero='777BB')
    Moto.objects.create(proprietaire=actif, abonnement=date(2030, 1, 1), numero='777CC', is_delete=True)


def test_F28_recherche_visiteur_ne_voit_pas_la_liste_nationale(client, jeu):
    _donnees(jeu)
    client.force_login(Compte.objects.create_user('vis', password='x', privilege4=True))
    corps = _chercher(client, 'Dupont').content.decode()
    assert 'Dupont Actif' in corps and 'Dupont Saisi' not in corps and 'Dupont Supprime' not in corps
    corps = _chercher(client, '777').content.decode()
    assert '777AA' in corps and '777BB' not in corps and '777CC' not in corps


def test_F28_recherche_sans_privilege_ne_trouve_rien(client, jeu):
    _donnees(jeu)
    client.force_login(Compte.objects.create_user('nu', password='x'))
    corps = _chercher(client, 'Dupont').content.decode()
    assert 'Dupont Actif' not in corps and 'Dupont Saisi' not in corps and 'Aucun resultat' in corps
    corps = _chercher(client, '777').content.decode()
    assert '777AA' not in corps and '777BB' not in corps


def test_F28_recherche_su_voit_tout_sauf_les_supprimes(client, jeu):
    _donnees(jeu)
    client.force_login(jeu['compte'])
    corps = _chercher(client, 'Dupont').content.decode()
    assert 'Dupont Actif' in corps and 'Dupont Saisi' in corps and 'Dupont Supprime' not in corps
    corps = _chercher(client, '777').content.decode()
    assert '777AA' in corps and '777BB' in corps and '777CC' not in corps


def test_F28_recherche_vide_et_get(client, jeu):
    client.force_login(jeu['compte'])
    assert 'Aucun resultat' in _chercher(client, '').content.decode()
    assert client.get(reverse('recherche')).status_code == 200
