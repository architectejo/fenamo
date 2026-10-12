"""F-21 : modification d'un membre par formulaire (erreurs sans 500), journalisée avant / après ; libellés d'état uniques."""
from django.urls import reverse

from compte.models import JournalAction
from coptapp.models import Membre
from coptapp.services.etats import ETATS, LIBELLES
from coptapp.services.membres import demander_modification
from coptapp.services.tableau_bord import indicateurs_tableau_bord
from tests.test_plan_url import hachage_rapide, jeu  # noqa: F401

A = JournalAction.Action


def _poster(client, jeu, **donnees):
    base = {'modifier': '1', 'nom': 'Nouveau Nom', 'date': '02-03-1991'}
    base.update(donnees)
    client.force_login(jeu['compte'])
    return client.post(reverse('membre-view', args=[jeu['membre'].id]), base)


def test_F21_modification_journalisee_avant_apres(client, jeu):
    r = _poster(client, jeu, telephone='+243810000000', numero_carte_d_electeur='SECRET-123')
    assert r.status_code == 200
    jeu['membre'].refresh_from_db()
    assert jeu['membre'].nom == 'Nouveau Nom' and jeu['membre'].telephone == '+243810000000'
    ligne = JournalAction.objects.get(action=A.MODIFICATION)
    assert ligne.avant['nom'] == 'Membre Fictif' and ligne.apres['nom'] == 'Nouveau Nom'
    assert ligne.objet_id == jeu['membre'].id and ligne.auteur == jeu['compte']
    assert ligne.apres['numero_carte_d_electeur'] == '***' and 'SECRET-123' not in str(ligne.apres)
    assert 'date_naissance' in ligne.apres


def test_F21_champs_absents_gardent_leur_valeur(client, jeu):
    Membre.objects.filter(pk=jeu['membre'].pk).update(telephone='+243999', adresse='Rue 1')
    _poster(client, jeu)  # seuls nom et date sont envoyés
    jeu['membre'].refresh_from_db()
    assert jeu['membre'].telephone == '+243999' and jeu['membre'].adresse == 'Rue 1' and jeu['membre'].nom == 'Nouveau Nom'


def test_F21_aucun_changement_aucune_ligne(client, jeu):
    _poster(client, jeu, nom='Membre Fictif', date='01-01-1990')
    assert not JournalAction.objects.filter(action=A.MODIFICATION).exists()


def test_F21_champ_obligatoire_manquant_ou_date_invalide_donne_une_erreur_pas_un_500(client, jeu):
    client.force_login(jeu['compte'])
    url = reverse('membre-view', args=[jeu['membre'].id])
    for donnees in ({'modifier': '1'}, {'modifier': '1', 'nom': 'X'}, {'modifier': '1', 'nom': 'X', 'date': 'pas-une-date'},
                    {'modifier': '1', 'nom': '', 'date': '02-03-1991'}):
        r = client.post(url, donnees)
        assert r.status_code == 400, donnees
        assert r.context['erreurs_modifier']
    jeu['membre'].refresh_from_db()
    assert jeu['membre'].nom == 'Membre Fictif'
    assert not JournalAction.objects.filter(action=A.MODIFICATION).exists()


def test_F21_demande_de_modification_service(jeu):
    assert demander_modification(jeu['compte'], jeu['membre'], '  ') == 'vide'
    assert demander_modification(jeu['compte'], jeu['membre'], 'Corriger') == 'creee'
    assert demander_modification(jeu['compte'], jeu['membre'], 'Corriger') == 'existante'


def test_F23_une_seule_table_de_libelles_d_etat(jeu):
    assert set(LIBELLES) == set(ETATS)
    ind = indicateurs_tableau_bord(jeu['compte'])
    assert ind['graphique']['libelles'] == [str(LIBELLES['saisi']), str(LIBELLES['valide_antenne']), str(LIBELLES['actif'])]
