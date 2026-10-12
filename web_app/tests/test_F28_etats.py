"""Service d'état du circuit de validation (§ 4.4) sur les booléens hérités."""
from datetime import date, timedelta

import pytest

from coptapp.models import Membre
from coptapp.services.etats import ETATS, etat_de
from tests.test_plan_url import hachage_rapide, jeu  # noqa: F401


def membre(**drapeaux):
    return Membre(nom='X', **drapeaux)


def test_F28_etat_saisi_par_defaut_meme_si_is_validate1_vrai():
    assert Membre(nom='X').is_validate1 is True  # défaut du modèle
    assert etat_de(Membre(nom='X')) == 'saisi'


def test_F28_etat_valide_antenne_puis_actif():
    assert etat_de(membre(is_validate2=True)) == 'valide_antenne'
    assert etat_de(membre(is_validate2=True, is_validate3=True)) == 'actif'
    assert etat_de(membre(is_validate3=True)) == 'actif'


def test_F28_etat_supprime_prioritaire():
    assert etat_de(membre(is_validate2=True, is_validate3=True, is_delete=True)) == 'supprime'


def test_F28_etat_explicite_prioritaire_quand_le_champ_existera():
    m = membre(is_validate3=True)
    m.etat = 'renvoye'
    assert etat_de(m) == 'renvoye'
    m.etat = 'inconnu'
    assert etat_de(m) == 'actif'


def test_F28_etat_engin(jeu):
    moto = jeu['moto']
    moto.abonnement = date.today() + timedelta(days=30)
    assert etat_de(moto) == 'actif'
    moto.abonnement = date.today() - timedelta(days=1)
    assert etat_de(moto) == 'a_renouveler'
    assert etat_de(moto, aujourdhui=date.today() - timedelta(days=5)) == 'actif'
    moto.is_delete = True
    assert etat_de(moto) == 'supprime'


def test_F28_etat_suit_les_actions_de_la_vue_validate(client, jeu):
    from django.urls import reverse
    m = jeu['membre']
    assert etat_de(m) == 'saisi'
    client.force_login(jeu['compte'])
    client.post(reverse('validate', kwargs={'id': m.id}))
    m.refresh_from_db()
    assert etat_de(m) == 'actif'  # un SU valide tous les niveaux d'un coup
    client.post(reverse('validate', kwargs={'id': m.id}))
    m.refresh_from_db()
    assert etat_de(m) == 'saisi'  # puis les renvoie


@pytest.mark.parametrize('etat', ETATS)
def test_F28_codes_connus(etat):
    assert '-' not in etat  # codes en snake_case ; le filtre de gabarit peut les convertir
