"""F-70 (b1) : le journal d'activités reçoit une ligne par changement d'état, sans secret."""
import json

import pytest
from django.contrib.auth.models import AnonymousUser
from django.urls import reverse

from compte.models import Compte, JournalAction
from compte.services.journal import CHAMPS_INTERDITS, journaliser, purger
from tests.test_plan_url import hachage_rapide, jeu  # noqa: F401

MDP = 'Bon-mot-de-passe-1x'
A = JournalAction.Action


def lignes(action):
    return JournalAction.objects.filter(action=action)


def sans_secret(ligne):
    texte = json.dumps([ligne.avant, ligne.apres, ligne.objet_libelle, ligne.motif], ensure_ascii=False).lower()
    return 'password' not in texte and 'pbkdf2' not in texte and MDP.lower() not in texte


# ---------------------------------------------------------------- service

def test_F70_purger_retire_les_champs_interdits_recursivement():
    brut = {'nom': 'x', 'password': 'a', 'Old_Password': 'b', 'jeton_qr': 'c', 'photo': 'd.jpg',
            'imbrique': {'new_password1': 'e', 'ok': 1, 'liste': [{'token': 't', 'v': 2}]}}
    assert purger(brut) == {'nom': 'x', 'imbrique': {'ok': 1, 'liste': [{'v': 2}]}}


def test_F70_journaliser_refuse_une_action_inconnue(jeu):
    with pytest.raises(ValueError):
        journaliser(jeu['compte'], 'inconnue', jeu['membre'])


def test_F70_journaliser_enregistre_auteur_role_objet_perimetre(jeu):
    ligne = journaliser(jeu['compte'], A.VALIDATION, jeu['membre'], avant={'a': 1, 'password': 'x'}, apres={'a': 2},
                        motif='essai')
    assert ligne.auteur == jeu['compte'] and ligne.role == 'SU'
    assert ligne.objet_id == jeu['membre'].id and ligne.objet_type.model == 'membre'
    assert ligne.objet_libelle == 'Membre Fictif'
    assert ligne.coordination == jeu['province'] and ligne.antenne == jeu['antenne']
    assert ligne.avant == {'a': 1} and ligne.apres == {'a': 2} and ligne.motif == 'essai'


def test_F70_auteur_anonyme_devient_null(db):
    ligne = journaliser(AnonymousUser(), A.ECHEC_CONNEXION, libelle='x')
    assert ligne.auteur is None


def test_F70_une_ligne_ne_se_modifie_pas(jeu):
    ligne = journaliser(jeu['compte'], A.EXPORT, libelle='x')
    ligne.motif = 'autre'
    with pytest.raises(ValueError):
        ligne.save()


# ---------------------------------------------------------------- connexion

def test_F70_connexion_deconnexion_echec_sans_mot_de_passe(client, db):
    Compte.objects.create_user('agent', password=MDP)
    client.post('/connexion/', {'username': 'agent', 'password': 'faux-secret-123'})
    client.post('/connexion/', {'username': 'agent', 'password': MDP})
    client.post('/deconnexion/')
    assert lignes(A.ECHEC_CONNEXION).filter(objet_libelle='agent').count() == 1
    assert lignes(A.CONNEXION).filter(auteur__username='agent').count() == 1
    assert lignes(A.DECONNEXION).filter(auteur__username='agent').count() == 1
    for ligne in JournalAction.objects.all():
        assert sans_secret(ligne) and 'faux-secret' not in json.dumps(ligne.apres)


def test_F70_blocage_axes_journalise(client, db):
    Compte.objects.create_user('cible', password=MDP)
    for _ in range(5):
        client.post('/connexion/', {'username': 'cible', 'password': 'faux'})
    assert lignes(A.VERROUILLAGE_CONNEXION).filter(objet_libelle='cible').exists()


# ---------------------------------------------------------------- comptes

def test_F70_creation_de_compte_adminer_et_add_user(client, jeu):
    Compte.objects.filter(pk=jeu['compte'].pk).update(membreId=None)
    client.force_login(jeu['compte'])
    r = client.post(reverse('adminer', kwargs={'id': jeu['membre'].id}))
    mdp = r.content.decode().split('<strong class="secret">')[1].split('</strong>')[0]
    client.post(reverse('add-user'), {'username': 'direct', 'email': 'd@example.invalid'})
    assert lignes(A.CREATION_COMPTE).count() == 2
    for ligne in lignes(A.CREATION_COMPTE):
        assert ligne.auteur == jeu['compte'] and sans_secret(ligne) and mdp not in json.dumps(ligne.apres)


def test_F70_attribution_de_privileges(client, jeu):
    Compte.objects.create_user('cible', password=MDP, membreId=jeu['membre'].id)
    Compte.objects.filter(pk=jeu['compte'].pk).update(membreId=None)
    client.force_login(jeu['compte'])
    client.post(reverse('membre-view', kwargs={'id': jeu['membre'].id}), {'privilege': '1', 'privilege3': 'on'})
    ligne = lignes(A.ATTRIBUTION_PRIVILEGES).get()
    assert ligne.avant['privilege3'] is False and ligne.apres['privilege3'] is True
    assert ligne.objet_libelle == 'cible' and sans_secret(ligne)


def test_F70_changement_de_mot_de_passe(client, db):
    c = Compte.objects.create_user('u', password=MDP, doit_changer_mot_de_passe=True)
    client.force_login(c)
    nouveau = 'Nouveau-mdp-9876'
    client.post(reverse('securite'), {'old_password': MDP, 'new_password1': nouveau, 'new_password2': nouveau})
    ligne = lignes(A.CHANGEMENT_MOT_DE_PASSE).get()
    assert ligne.auteur == c and ligne.avant == {'changement_impose': True}
    assert sans_secret(ligne) and nouveau.lower() not in json.dumps(ligne.apres).lower()


def test_F70_mot_de_passe_change_et_compte_cree_via_l_admin(client, jeu):
    client.force_login(jeu['compte'])
    client.post('/gestion-technique/compte/compte/add/', {
        'username': 'par-admin', 'password1': 'Mdp-admin-test-7391', 'password2': 'Mdp-admin-test-7391'})
    cible = Compte.objects.get(username='par-admin')
    client.post(f'/gestion-technique/compte/compte/{cible.pk}/password/',
                {'password1': 'Autre-mdp-admin-5521', 'password2': 'Autre-mdp-admin-5521'})
    assert lignes(A.CREATION_COMPTE).filter(objet_libelle='par-admin').exists()
    ligne = lignes(A.CHANGEMENT_MOT_DE_PASSE).get(objet_libelle='par-admin')
    assert ligne.auteur == jeu['compte'] and sans_secret(ligne)


# ---------------------------------------------------------------- membres et engins

def test_F70_validation_puis_renvoi_d_un_membre(client, jeu):
    client.force_login(jeu['compte'])
    url = reverse('validate', kwargs={'id': jeu['membre'].id})
    client.post(url)
    client.post(url)
    v, r = lignes(A.VALIDATION).get(), lignes(A.RENVOI).get()
    assert v.avant['is_validate3'] is False and v.apres['is_validate3'] is True
    assert r.avant['is_validate3'] is True and r.apres['is_validate3'] is False
    assert v.objet_id == jeu['membre'].id and v.antenne == jeu['antenne']


def test_F70_suppression_logique_et_annulation_membre(client, jeu):
    client.force_login(jeu['compte'])
    url = reverse('delete-membre', kwargs={'id': jeu['membre'].id})
    client.post(url)
    client.post(url)
    assert lignes(A.SUPPRESSION).get().apres == {'is_delete': True}
    assert lignes(A.RESTAURATION).get().apres == {'is_delete': False}


def test_F70_suppression_logique_d_un_engin(client, jeu):
    client.force_login(jeu['compte'])
    client.post(reverse('delete-moto', kwargs={'id': jeu['moto'].id}))
    ligne = lignes(A.SUPPRESSION).get()
    assert ligne.objet_type.model == 'moto' and ligne.objet_libelle == '001PF'


def test_F70_rattachements(client, jeu):
    client.force_login(jeu['compte'])
    m = jeu['membre'].id
    client.post(reverse('structure-attribution', kwargs={'idM': m, 'id': jeu['association'].id}))
    client.post(reverse('ville-attribution', kwargs={'idM': m, 'id': jeu['ville'].id}))
    client.post(reverse('antenne-attribution', kwargs={'idM': m, 'id': jeu['antenne'].id}))
    client.post(reverse('ville-attr', kwargs={'sid': jeu['association'].id, 'id': jeu['ville'].id}))
    champs = sorted(next(k for k in ligne.apres if not k.endswith('_libelle')) for ligne in lignes(A.RATTACHEMENT))
    assert champs == ['antenne', 'structure', 'ville', 'ville']


def test_F70_attribution_d_un_engin_a_un_membre(client, jeu):
    client.force_login(jeu['compte'])
    client.post(reverse('moto-attribution', kwargs={'id': jeu['membre'].id}), {'numero': '001PF'})
    ligne = lignes(A.RATTACHEMENT).get()
    assert ligne.apres == {'motard_id': str(jeu['membre'].id)}


def test_F70_aucune_ecriture_au_journal_sur_un_simple_get(client, jeu):
    client.force_login(jeu['compte'])
    avant = JournalAction.objects.count()
    for nom in ('liste-membre', 'str-list', 'tableau-bord'):
        client.get(reverse(nom))
    assert JournalAction.objects.count() == avant


def test_F70_liste_noire_couvre_les_secrets():
    for mot in ('password', 'token', 'jeton', 'photo', 'piece'):
        assert mot in CHAMPS_INTERDITS
