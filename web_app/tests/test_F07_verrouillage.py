"""F-07 : verrouillage de l'application (SU seul, message obligatoire, journal, middleware à chaque requête, connexion, API, /mob/, HTMX,
commande d'urgence, aucune donnée modifiée)."""
import json

import pytest
from django.core.exceptions import PermissionDenied
from django.core.management import call_command
from django.test import Client
from django.urls import reverse

from compte import roles
from compte.models import Compte, EtatApplication, JournalAction
from compte.services import verrou_application as V
from coptapp.models import Membre
from tests.test_F02_droits_roles import _compte, _nommer, acteurs_roles, monde  # noqa: F401
from tests.test_plan_url import hachage_rapide, jeu  # noqa: F401

A = JournalAction.Action
MESSAGE = 'Maintenance : retour demain.'


def _verrouiller(monde, message=MESSAGE, motif='Migration de la base'):
    return V.verrouiller(monde['compte'], message, motif)


# ---------------------------------------------------------------- service

def test_F07_etat_initial_deverrouille_sans_ecriture(monde, django_assert_num_queries):
    assert EtatApplication.objects.filter(pk=1, verrouillee=False).exists()  # ligne créée par la migration
    with django_assert_num_queries(1):
        assert V.est_verrouillee() is False
    EtatApplication.objects.all().delete()  # base vidée : un état déverrouillé, rien n'est écrit en lecture
    assert V.est_verrouillee() is False and not EtatApplication.objects.exists()


def test_F07_seul_le_super_utilisateur_verrouille_et_deverrouille(monde, acteurs_roles):
    for role in ('PR', 'VN', 'VP', 'VA', 'AT', 'VI', 'ED'):
        with pytest.raises(PermissionDenied):
            V.verrouiller(acteurs_roles[role], MESSAGE)
    with pytest.raises(PermissionDenied):
        V.verrouiller(None, MESSAGE)  # l'auteur absent n'est accepté que pour déverrouiller (commande)
    _verrouiller(monde)
    for role in ('PR', 'VA', 'ED'):
        with pytest.raises(PermissionDenied):
            V.deverrouiller(acteurs_roles[role])
    assert V.est_verrouillee()


def test_F07_message_obligatoire_et_borne(monde):
    for vide in ('', '   ', None):
        with pytest.raises(V.RegleVerrou):
            V.verrouiller(monde['compte'], vide)
    with pytest.raises(V.RegleVerrou):
        V.verrouiller(monde['compte'], 'x' * 501)
    with pytest.raises(V.RegleVerrou):
        V.verrouiller(monde['compte'], 'ok', 'm' * 501)
    assert not V.est_verrouillee() and not JournalAction.objects.filter(action=A.VERROUILLAGE_APPLICATION).exists()


def test_F07_verrouillage_et_deverrouillage_journalises(monde):
    _verrouiller(monde)
    ligne = JournalAction.objects.get(action=A.VERROUILLAGE_APPLICATION)
    assert ligne.auteur == monde['compte'] and ligne.avant == {'verrouillee': False} and ligne.apres['verrouillee'] is True
    assert ligne.motif == 'Migration de la base'
    etat = V.etat()
    assert etat.verrouillee and etat.message == MESSAGE and etat.par == monde['compte'] and etat.depuis is not None
    assert V.deverrouiller(monde['compte'], 'Fin de maintenance') is True
    ligne = JournalAction.objects.get(action=A.DEVERROUILLAGE_APPLICATION)
    assert ligne.auteur == monde['compte'] and ligne.avant == {'verrouillee': True} and ligne.apres == {'verrouillee': False}
    assert ligne.motif == 'Fin de maintenance' and not V.est_verrouillee() and V.etat().message == ''
    assert V.deverrouiller(monde['compte']) is False  # déjà déverrouillée : rien n'est écrit
    assert JournalAction.objects.filter(action=A.DEVERROUILLAGE_APPLICATION).count() == 1


def test_F07_chemins_exemptes():
    for chemin in ('/static/css/app.css', '/connexion/', '/deconnexion/'):
        assert V.chemin_exempte(chemin), chemin
    for chemin in ('/membres/', '/api/v1/sante/', '/mob/', '/media/x.png', '/application/verrou/', '/gestion-technique/', '/gestion-technique/login/'):
        assert not V.chemin_exempte(chemin), chemin


# ---------------------------------------------------------------- middleware

def test_F07_le_super_utilisateur_passe_partout(client, monde):
    _verrouiller(monde)
    client.force_login(monde['compte'])
    assert client.get(reverse('liste-membre')).status_code == 200
    assert client.get(reverse('tableau-bord')).status_code == 200
    assert client.get(reverse('verrou-application')).status_code == 200


def test_F07_session_d_un_president_fermee_a_la_requete_suivante(client, monde, acteurs_roles):
    pr = acteurs_roles['PR']
    client.force_login(pr)
    assert client.get(reverse('liste-membre')).status_code == 200
    _verrouiller(monde)
    reponse = client.get(reverse('liste-membre'))
    assert reponse.status_code == 503 and MESSAGE in reponse.content.decode()
    assert '_auth_user_id' not in client.session  # session fermée, pas seulement bloquée
    V.deverrouiller(monde['compte'])
    assert client.get(reverse('liste-membre')).status_code == 302  # plus connecté : retour à la connexion


def test_F07_page_503_cache_interdit_et_message_seul(client, monde, acteurs_roles):
    _verrouiller(monde, motif='Secret interne XYZ')
    client.force_login(acteurs_roles['VA'])
    reponse = client.get(reverse('liste-membre'))
    corps = reponse.content.decode()
    assert reponse.status_code == 503 and MESSAGE in corps and 'Secret interne XYZ' not in corps and monde['compte'].username not in corps
    assert 'no-store' in reponse['Cache-Control']


def test_F07_htmx_recoit_une_redirection_vers_la_connexion(client, monde, acteurs_roles):
    client.force_login(acteurs_roles['PR'])
    _verrouiller(monde)
    reponse = client.get(reverse('liste-membre'), HTTP_HX_REQUEST='true')
    assert reponse.status_code == 200 and reponse['HX-Redirect'] == reverse('application')


def test_F07_api_503_json_sans_motif_ni_auteur(client, monde):
    _verrouiller(monde, motif='Secret interne XYZ')
    reponse = client.get('/api/v1/site/communiques/')
    assert reponse.status_code in (503,)
    donnees = json.loads(reponse.content)
    assert donnees == {'statut': 'suspendu', 'detail': 'Service suspendu.', 'message': MESSAGE}
    assert 'Secret' not in reponse.content.decode() and monde['compte'].username not in reponse.content.decode()
    assert 'no-store' in reponse['Cache-Control']


def test_F07_sante_repond_200_suspendu(client, monde):
    assert json.loads(client.get('/api/v1/sante/').content)['statut'] == 'ok'
    _verrouiller(monde)
    reponse = client.get('/api/v1/sante/')
    assert reponse.status_code == 200 and json.loads(reponse.content) == {'statut': 'suspendu', 'version': 'v1'}


def test_F07_mob_503_et_session_mobile_videe(client, monde):
    session = client.session
    session['mob_membre_id'], session['mob_empreinte'] = 1, 'abc'
    session.save()
    _verrouiller(monde)
    reponse = client.get('/mob/')
    assert reponse.status_code == 503 and MESSAGE in reponse.content.decode()
    assert 'mob_membre_id' not in client.session and 'mob_empreinte' not in client.session


def test_F07_statiques_et_connexion_restent_accessibles(client, monde, acteurs_roles):
    _verrouiller(monde)
    assert client.get(reverse('application')).status_code == 200  # bandeau d'information
    assert MESSAGE in client.get(reverse('application')).content.decode()
    assert client.get('/static/css/app.css').status_code != 503
    assert client.get('/gestion-technique/login/').status_code == 503  # V2 : l'administration n'est pas exemptée
    client.force_login(acteurs_roles['PR'])
    assert client.post(reverse('deconnexion')).status_code == 302  # la déconnexion passe


def test_F07_medias_bloques_pour_les_non_su(client, monde):
    _verrouiller(monde)
    assert client.get('/media/anything.png').status_code == 503


def test_F07_le_verrou_est_lu_a_chaque_requete_sans_cache(client, monde, acteurs_roles):
    client.force_login(monde['compte'])
    assert client.get(reverse('tableau-bord')).status_code == 200
    _verrouiller(monde)
    autre = Client()
    autre.force_login(acteurs_roles['PR'])
    assert autre.get(reverse('tableau-bord')).status_code == 503
    V.deverrouiller(monde['compte'])
    autre.force_login(acteurs_roles['PR'])
    assert autre.get(reverse('tableau-bord')).status_code == 200


# ---------------------------------------------------------------- connexion

def test_F07_connexion_su_acceptee_non_su_refusee_et_journalisee(client, monde, acteurs_roles):
    _compte('pr-connexion')
    pr = Compte.objects.get(username='pr-connexion')
    pr.set_password('Secret-Fenamo-1')
    pr.save()
    _verrouiller(monde)
    reponse = client.post(reverse('application'), {'username': 'pr-connexion', 'password': 'Secret-Fenamo-1'})
    assert reponse.status_code == 503 and MESSAGE in reponse.content.decode() and '_auth_user_id' not in client.session
    ligne = JournalAction.objects.filter(action=A.ECHEC_CONNEXION, motif='application verrouillée').get()
    assert ligne.objet_libelle == 'pr-connexion'
    su = Compte.objects.get(pk=monde['compte'].pk)
    su.set_password('Secret-Fenamo-2')
    su.save()
    reponse = client.post(reverse('application'), {'username': su.username, 'password': 'Secret-Fenamo-2'})
    assert reponse.status_code == 302 and '_auth_user_id' in client.session


# ---------------------------------------------------------------- vues

def test_F07_vues_reservees_au_super_utilisateur(client, monde, acteurs_roles):
    for nom in ('verrou-application', 'verrou-verrouiller', 'verrou-deverrouiller'):
        client.force_login(acteurs_roles['PR'])
        assert client.get(reverse(nom)).status_code == 403, nom
    client.force_login(acteurs_roles['PR'])
    assert client.post(reverse('verrou-verrouiller'), {'message': MESSAGE}).status_code == 403
    assert not V.est_verrouillee()


def test_F07_vue_verrouiller_post_csrf_message_obligatoire_et_htmx(client, monde):
    url = reverse('verrou-verrouiller')
    client.force_login(monde['compte'])
    assert client.get(url).status_code == 200  # modale
    vide = client.post(url, {'message': ''}, HTTP_HX_REQUEST='true')
    assert vide.status_code == 422 and not V.est_verrouillee()
    ok = client.post(url, {'message': MESSAGE, 'motif': 'Test'}, HTTP_HX_REQUEST='true')
    assert ok.status_code == 204 and 'verrouModifie' in ok['HX-Trigger'] and V.est_verrouillee()
    lever = client.post(reverse('verrou-deverrouiller'), {'motif': 'Fini'}, HTTP_HX_REQUEST='true')
    assert lever.status_code == 204 and 'verrouModifie' in lever['HX-Trigger'] and not V.est_verrouillee()


def test_F07_csrf_exige_et_get_sans_effet(monde):
    client = Client(enforce_csrf_checks=True)
    client.force_login(monde['compte'])
    assert client.post(reverse('verrou-verrouiller'), {'message': MESSAGE}).status_code == 403
    assert not V.est_verrouillee()
    avant = JournalAction.objects.count()
    for nom in ('verrou-application', 'verrou-verrouiller', 'verrou-deverrouiller'):
        assert client.get(reverse(nom)).status_code == 200
    assert not V.est_verrouillee() and JournalAction.objects.count() == avant


def test_F07_bandeau_du_super_utilisateur_tant_que_verrouillee(client, monde, django_assert_num_queries):
    client.force_login(monde['compte'])
    assert 'bandeau-verrou' not in client.get(reverse('tableau-bord')).content.decode()
    _verrouiller(monde)
    page = client.get(reverse('tableau-bord')).content.decode()
    assert 'bandeau-verrou' in page  # le message du SU n'est affiché que par _message_su (écran, 503, connexion), pas dans le bandeau


# ---------------------------------------------------------------- commande d'urgence, aucune donnée modifiée

def test_F07_commande_d_urgence_deverrouille_sans_auteur(monde, capsys):
    _verrouiller(monde)
    call_command('deverrouiller_application', '--motif', 'Accès perdu')
    assert not V.est_verrouillee()
    ligne = JournalAction.objects.get(action=A.DEVERROUILLAGE_APPLICATION)
    assert ligne.auteur is None and ligne.motif == 'Accès perdu'
    call_command('deverrouiller_application')  # déjà déverrouillée : code de retour 0, aucune ligne de plus
    assert JournalAction.objects.filter(action=A.DEVERROUILLAGE_APPLICATION).count() == 1


def test_F07_le_verrouillage_ne_modifie_aucune_donnee_metier(monde, acteurs_roles):
    avant = (list(Membre.objects.values_list('pk', 'etat', 'nom')), list(Compte.objects.values_list('pk', 'is_active')))
    _verrouiller(monde)
    V.deverrouiller(monde['compte'])
    assert (list(Membre.objects.values_list('pk', 'etat', 'nom')), list(Compte.objects.values_list('pk', 'is_active'))) == avant


def test_F07_admin_etat_application_lecture_seule(rf, monde):
    from django.contrib import admin
    modele_admin = admin.site._registry[EtatApplication]
    requete = rf.get('/')
    requete.user = monde['compte']
    assert modele_admin.has_view_permission(requete)
    assert not modele_admin.has_add_permission(requete) and not modele_admin.has_change_permission(requete)
    assert not modele_admin.has_delete_permission(requete)
