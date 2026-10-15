"""F-02 (audit sécurité) : blocage django-axes par identifiant (changer d'adresse IP ne contourne plus le verrou) et durée de validité du mot de passe
initial ou temporaire (7 jours par défaut, réglable) ; au-delà, un supérieur doit le réinitialiser (F-05)."""
from datetime import timedelta

import pytest
from django.conf import settings
from django.utils import timezone

from compte import roles
from compte.models import Compte, JournalAction
from compte.services import comptes as C
from compte.services import nominations as N
from coptapp.models import Membre
from tests.test_F02_droits_roles import _compte, _nommer, monde  # noqa: F401
from tests.test_plan_url import hachage_rapide, jeu  # noqa: F401

MDP = 'Bon-mot-de-passe-1x'


@pytest.fixture
def va(monde):
    return _nommer(monde, roles.VA, antenne=monde['antenne_p'])


def _nomme(monde, va, nom='Zoe'):
    membre = Membre.objects.create(nom=nom, antenne=monde['antenne_p'], province=monde['P'], etat='actif')
    return N.nommer(va, membre, roles.AT, antenne=monde['antenne_p'])[0].compte


def test_F02_le_verrou_porte_sur_l_identifiant_meme_depuis_des_adresses_differentes(client, db):
    Compte.objects.create_user('cible', password=MDP)
    for i in range(settings.AXES_FAILURE_LIMIT):
        client.post('/connexion/', {'username': 'cible', 'password': 'faux'}, REMOTE_ADDR=f'10.1.0.{i + 1}')
    reponse = client.post('/connexion/', {'username': 'cible', 'password': MDP}, REMOTE_ADDR='10.9.9.9')
    assert reponse.status_code == 429 and '_auth_user_id' not in client.session
    Compte.objects.create_user('autre', password=MDP)
    assert client.post('/connexion/', {'username': 'autre', 'password': MDP}, REMOTE_ADDR='10.9.9.9').status_code == 302


def test_F02_duree_de_validite_par_defaut_et_reglable():
    assert settings.MOT_DE_PASSE_INITIAL_JOURS == 7


def test_F02_mot_de_passe_initial_expire_service(monde, va, settings):
    compte = _nomme(monde, va)
    assert compte.mot_de_passe_temporaire_le is not None and not C.mot_de_passe_temporaire_expire(compte)
    maintenant = timezone.now()
    assert not C.mot_de_passe_temporaire_expire(compte, maintenant + timedelta(days=6, hours=23))
    assert C.mot_de_passe_temporaire_expire(compte, maintenant + timedelta(days=7, minutes=1))
    settings.MOT_DE_PASSE_INITIAL_JOURS = 2
    assert C.mot_de_passe_temporaire_expire(compte, maintenant + timedelta(days=3))
    ordinaire = _compte('ordinaire')  # rien à changer : jamais expiré
    assert not C.mot_de_passe_temporaire_expire(ordinaire, maintenant + timedelta(days=400))
    ancien = _compte('ancien-temp', doit_changer_mot_de_passe=True)  # date vide : date de création du compte
    assert C.mot_de_passe_temporaire_expire(ancien, maintenant + timedelta(days=3))


def test_F02_connexion_refusee_apres_expiration_puis_reinitialisation_par_un_superieur(client, monde, va):
    compte = _nomme(monde, va)
    initial = compte.username
    Compte.objects.filter(pk=compte.pk).update(mot_de_passe_temporaire_le=timezone.now() - timedelta(days=6))
    assert client.post('/connexion/', {'username': initial, 'password': initial}).status_code == 302  # dans le délai
    client.post('/deconnexion/')
    Compte.objects.filter(pk=compte.pk).update(mot_de_passe_temporaire_le=timezone.now() - timedelta(days=8))
    reponse = client.post('/connexion/', {'username': initial, 'password': initial})
    corps = reponse.content.decode()
    assert reponse.status_code == 403 and '_auth_user_id' not in client.session and 'expiré' in corps and initial not in corps
    ligne = JournalAction.objects.filter(action=JournalAction.Action.ECHEC_CONNEXION).latest('id')
    assert 'expiré' in ligne.motif and initial not in f'{ligne.objet_libelle} {ligne.motif}'
    nouveau = N.reinitialiser_mot_de_passe(va, Compte.objects.get(pk=compte.pk))  # un supérieur réinitialise : le délai repart
    assert client.post('/connexion/', {'username': initial, 'password': nouveau}).status_code == 302


def test_F02_changer_son_mot_de_passe_efface_la_date(client, monde, va):
    compte = _nomme(monde, va)
    initial = compte.username
    assert client.post('/connexion/', {'username': initial, 'password': initial}).status_code == 302
    r = client.post('/mon-compte/securite/', {'old_password': initial, 'new_password1': 'Un-Tout-Nouveau-Secret-83', 'new_password2': 'Un-Tout-Nouveau-Secret-83'})
    assert r.status_code == 302
    apres = Compte.objects.get(pk=compte.pk)
    assert not apres.doit_changer_mot_de_passe and apres.mot_de_passe_temporaire_le is None and not C.mot_de_passe_temporaire_expire(apres, timezone.now() + timedelta(days=90))
