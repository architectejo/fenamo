"""F-07 : corrections de l'audit (V1 connexion sans fuite, V2 administration, path_info, re-verrouillage, erreurs des modales, vues minces)."""
import datetime
import logging

import pytest
from django.contrib.auth.models import AnonymousUser
from django.contrib.sessions.models import Session
from django.http import HttpResponse
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from compte.middleware import VerrouApplicationMiddleware
from compte.models import Compte, JournalAction
from compte.services import verrou_application as V
from compte.services.journal_lecture import lister_journal
from tests.test_F02_droits_roles import _compte, acteurs_roles, monde  # noqa: F401
from tests.test_plan_url import hachage_rapide, jeu  # noqa: F401

A = JournalAction.Action
MESSAGE = 'Maintenance : retour demain.'


def _verrouiller(monde, message=MESSAGE, motif='Migration de la base'):
    return V.verrouiller(monde['compte'], message, motif)


def _requete(rf, chemin, script=''):
    requete = rf.get(chemin, SCRIPT_NAME=script)
    requete.user, requete.session = AnonymousUser(), {}
    return requete


def test_F07_V1_connexion_meme_reponse_pour_mot_de_passe_faux_compte_inconnu_et_non_su(client, monde):
    pr = _compte('pr-v1')
    pr.set_password('Secret-Fenamo-1')
    pr.save()
    _verrouiller(monde)
    reponses = [
        client.post(reverse('application'), {'username': 'pr-v1', 'password': 'Secret-Fenamo-1'}),  # non SU, bon mot de passe
        Client().post(reverse('application'), {'username': 'pr-v1', 'password': 'mauvais'}),  # mot de passe faux
        Client().post(reverse('application'), {'username': 'inconnu-v1', 'password': 'Secret-Fenamo-1'}),  # compte inconnu
    ]
    assert {r.status_code for r in reponses} == {503}
    corps = [r.content.decode() for r in reponses]
    assert all(MESSAGE in c for c in corps)
    assert len({len(c) for c in corps}) <= 2  # même page, au jeton CSRF près
    assert 'incorrect' not in ' '.join(corps)  # jamais « mot de passe incorrect » : on ne dit pas si l'identifiant existe


def test_F07_V1_le_bon_mot_de_passe_d_un_non_su_compte_comme_echec_pour_axes(client, monde):
    from axes.models import AccessAttempt
    pr = _compte('pr-axes')
    pr.set_password('Secret-Fenamo-1')
    pr.save()
    _verrouiller(monde)
    client.post(reverse('application'), {'username': 'pr-axes', 'password': 'Secret-Fenamo-1'})
    assert AccessAttempt.objects.filter(username='pr-axes', failures_since_start__gte=1).exists()


def test_F07_V1_un_su_au_bon_mot_de_passe_passe_normalement(client, monde):
    su = Compte.objects.get(pk=monde['compte'].pk)
    su.set_password('Secret-Fenamo-2')
    su.save()
    _verrouiller(monde)
    reponse = client.post(reverse('application'), {'username': su.username, 'password': 'Secret-Fenamo-2'})
    assert reponse.status_code == 302 and '_auth_user_id' in client.session


def test_F07_V2_administration_refusee_a_un_non_su_et_ouverte_a_un_su_connecte(client, monde):
    _verrouiller(monde)
    staff = _compte('staff-v2', is_staff=True)
    staff.set_password('Secret-Fenamo-1')
    staff.save()
    assert client.post('/gestion-technique/login/', {'username': 'staff-v2', 'password': 'Secret-Fenamo-1'}).status_code == 503
    assert '_auth_user_id' not in client.session
    client.force_login(monde['compte'])
    assert client.get('/gestion-technique/').status_code == 200


def test_F07_F1_le_middleware_lit_path_info_et_non_path(rf, monde):
    _verrouiller(monde)
    intermediaire = VerrouApplicationMiddleware(lambda requete: pytest.fail('atteint malgré le verrou'))
    api = intermediaire(_requete(rf, '/api/v1/site/x/', '/app'))  # servie sous /app : path = /app/api/..., path_info = /api/...
    assert api.status_code == 503 and api['Content-Type'] == 'application/json'
    sante = intermediaire(_requete(rf, '/api/v1/sante/', '/app'))
    assert sante.status_code == 200
    assert V.chemin_exempte('/static/x.css') and not V.chemin_exempte('/app/static/x.css')  # chemin_exempte attend un path_info


def test_F07_exemptions_testees_avant_la_lecture_en_base(rf, monde, django_assert_num_queries):
    _verrouiller(monde)
    intermediaire = VerrouApplicationMiddleware(lambda requete: HttpResponse('ok'))
    with django_assert_num_queries(0):
        assert intermediaire(_requete(rf, '/static/css/app.css')).status_code == 200
        assert intermediaire(_requete(rf, '/connexion/')).status_code == 200


def test_F07_re_verrouiller_conserve_l_heure_de_debut_et_l_auteur(monde):
    autre_su = Compte.objects.create_superuser('autre-su', 'a@example.invalid', 'x')
    _verrouiller(monde)
    debut = V.etat().depuis
    V.verrouiller(autre_su, 'Nouveau message', 'Nouveau motif')
    etat = V.etat()
    assert etat.depuis == debut and etat.par == monde['compte'] and etat.message == 'Nouveau message' and etat.motif == 'Nouveau motif'
    assert JournalAction.objects.filter(action=A.VERROUILLAGE_APPLICATION).count() == 2  # le remplacement est journalisé
    V.deverrouiller(monde['compte'])
    V.verrouiller(autre_su, 'Après déverrouillage')
    assert V.etat().depuis > debut and V.etat().par == autre_su


def test_F07_en_tete_de_cache_unique_no_store(client, monde):
    _verrouiller(monde)
    for url in ('/membres/', '/api/v1/site/x/', '/mob/'):
        assert client.get(url)['Cache-Control'] == 'no-store', url


def test_F07_modale_verrouiller_affiche_l_erreur_reelle_a_cote_du_bon_champ(client, monde):
    client.force_login(monde['compte'])
    url = reverse('verrou-verrouiller')
    vide = client.post(url, {'message': ' ', 'motif': 'ok'})
    page = vide.content.decode()
    assert vide.status_code == 422 and 'v-message-erreur' in page and 'Indiquez le message' in page and 'v-motif-erreur' not in page
    long_motif = client.post(url, {'message': 'ok', 'motif': 'm' * 501})
    page = long_motif.content.decode()
    assert long_motif.status_code == 422 and 'v-motif-erreur' in page and 'limités à 500' in page and 'v-message-erreur' not in page
    assert not V.est_verrouillee()


def test_F07_modale_deverrouiller_affiche_l_erreur_422(client, monde):
    _verrouiller(monde)
    client.force_login(monde['compte'])
    reponse = client.post(reverse('verrou-deverrouiller'), {'motif': 'm' * 501})
    assert reponse.status_code == 422 and 'limité à 500' in reponse.content.decode() and V.est_verrouillee()


def test_F07_sessions_ouvertes_comptees_separement_et_bornees(monde, acteurs_roles):
    for compte in (monde['compte'], acteurs_roles['PR'], acteurs_roles['VA']):
        Client().force_login(compte)
    su, autres = V.sessions_ouvertes()
    assert su >= 1 and autres >= 2 and V.SESSIONS_MAX == 500


def test_F07_session_illisible_signalee_sans_bloquer(monde, caplog):
    Session.objects.create(session_key='illisible', session_data='pas-du-tout-une-session', expire_date=timezone.now() + datetime.timedelta(days=1))
    with caplog.at_level(logging.WARNING):
        resultat = V.sessions_ouvertes()  # Django signale lui-même la donnée corrompue ; le décompte ne plante pas
    assert isinstance(resultat, tuple) and 'corrupted' in caplog.text


def test_F07_filtre_heure_fr(monde):
    from fenamo.balises import heure_fr
    assert str(heure_fr(datetime.datetime(2026, 10, 15, 7, 40))) == '07&nbsp;h&nbsp;40' and heure_fr(None) == ''


def test_F07_lien_du_journal_inclut_les_deverrouillages(client, monde):
    _verrouiller(monde)
    V.deverrouiller(monde['compte'], 'Fini')
    client.force_login(monde['compte'])
    assert 'verrouillage_application,deverrouillage_application' in client.get(reverse('verrou-application')).content.decode()
    actions = {ligne.action for ligne in lister_journal({'action': 'verrouillage_application,deverrouillage_application'}).object_list}
    assert actions == {A.VERROUILLAGE_APPLICATION, A.DEVERROUILLAGE_APPLICATION}


def test_F07_ecran_de_verrouillage_vue_mince_et_bandeau_une_seule_fois(client, monde):
    _verrouiller(monde)
    client.force_login(monde['compte'])
    page = client.get(reverse('verrou-application')).content.decode()
    assert page.count('class="bandeau-verrou"') == 1 and 'aria-current="page"' in page
    for nom in ('duree_en_texte', 'sessions_ouvertes', 'historique_verrou', 'contexte_etat'):
        assert hasattr(V, nom), nom
    import compte.views_verrou as vues
    assert not any(hasattr(vues, nom) for nom in ('duree_en_texte', 'sessions_ouvertes', 'historique_verrou', 'contexte_etat'))
