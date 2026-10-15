"""F-02, F-03, F-05, F-06 : écran Utilisateurs (liste, mandats, modales, droits 403/404, mot de passe à lecture unique)."""
from datetime import date, timedelta

from django.test import Client
from django.urls import reverse
from django.utils import timezone

from compte import roles
from compte.models import Compte, JournalAction, Nomination
from coptapp.models import Membre
from tests.test_plan_url import hachage_rapide, jeu  # noqa: F401


def _pr(jeu):
    pr = Compte.objects.create_user('le-president', password='x')
    Nomination.objects.create(compte=pr, role=roles.PR, nomme_par=jeu['compte'])
    return pr


def _membre_actif(jeu, nom='Membre Nommable'):
    return Membre.objects.create(nom=nom, date_naissance=date(1990, 1, 1), province=jeu['province'], antenne=jeu['antenne'],
                                 structure=jeu['association'], etat='actif')


def _compte_nomme(jeu, auteur, nom='agent', role=roles.AT, **kw):
    compte = Compte.objects.create_user(nom, password='x')
    Nomination.objects.create(compte=compte, role=role, antenne=jeu['antenne'], nomme_par=auteur, **kw)
    return compte


def test_F02_ecran_reserve_a_ceux_qui_nomment(client, jeu):
    client.force_login(jeu['compte'])
    assert client.get(reverse('utilisateurs')).status_code == 200
    simple = _compte_nomme(jeu, jeu['compte'], 'simple-agent')
    client.force_login(simple)
    assert client.get(reverse('utilisateurs')).status_code == 403
    assert Client().get(reverse('utilisateurs')).status_code == 302


def test_F02_liste_page_complete_et_fragment(client, jeu):
    client.force_login(jeu['compte'])
    _compte_nomme(jeu, jeu['compte'], 'agent-un')
    reponse = client.get(reverse('utilisateurs'))
    page = reponse.content.decode()
    assert 'Nommer un membre' in page and 'agent-un' in page and 'hx-history="false"' in page and 'Mandats à traiter' in page
    assert 'no-store' in reponse['Cache-Control']
    frag = client.get(reverse('utilisateurs'), {'zone': 'comptes', 'q': 'agent-un'}, HTTP_HX_REQUEST='true').content.decode()
    assert '<html' not in frag and 'agent-un' in frag
    vide = client.get(reverse('utilisateurs'), {'zone': 'comptes', 'q': 'zzzz'}, HTTP_HX_REQUEST='true').content.decode()
    assert 'Aucun utilisateur ne correspond' in vide


def test_F02_ligne_vous_sans_action_et_actions_selon_droit(client, jeu):
    pr = _pr(jeu)
    agent = _compte_nomme(jeu, pr, 'agent-du-pr')
    client.force_login(pr)
    html = client.get(reverse('utilisateurs')).content.decode()
    assert 'Votre compte' in html
    assert reverse('utilisateurs-desactiver', kwargs={'id': agent.id}) in html
    assert reverse('utilisateurs-desactiver', kwargs={'id': pr.id}) not in html


def test_F06_personne_n_agit_sur_son_propre_compte(client, jeu):
    pr = _pr(jeu)
    client.force_login(pr)
    for nom in ('utilisateurs-reinitialiser', 'utilisateurs-desactiver', 'utilisateurs-reactiver', 'utilisateurs-role', 'utilisateurs-renouveler'):
        assert client.get(reverse(nom, kwargs={'id': pr.id})).status_code == 403, nom
        assert client.post(reverse(nom, kwargs={'id': pr.id})).status_code == 403, nom


def test_F06_compte_hors_perimetre_404_et_get_sans_effet(client, jeu):
    pr = _pr(jeu)
    su = Compte.objects.create_superuser('autre-su', 'a@example.invalid', 'x')
    client.force_login(pr)
    assert client.get(reverse('utilisateurs-desactiver', kwargs={'id': su.id})).status_code == 404
    assert client.post(reverse('utilisateurs-desactiver', kwargs={'id': 99999}), {'motif': 'x'}).status_code == 404
    agent = _compte_nomme(jeu, pr, 'agent-get')
    client.get(reverse('utilisateurs-desactiver', kwargs={'id': agent.id}))
    agent.refresh_from_db()
    assert agent.is_active  # un GET ne modifie rien


def test_F06_desactiver_exige_un_motif_puis_reactiver(client, jeu):
    pr = _pr(jeu)
    agent = _compte_nomme(jeu, pr, 'agent-a-couper')
    client.force_login(pr)
    url = reverse('utilisateurs-desactiver', kwargs={'id': agent.id})
    r = client.post(url, {'motif': '  '}, HTTP_HX_REQUEST='true')
    assert r.status_code == 422 and 'Indiquez le motif' in r.content.decode()
    agent.refresh_from_db()
    assert agent.is_active
    r = client.post(url, {'motif': 'Départ'}, HTTP_HX_REQUEST='true')
    assert r.status_code == 204 and 'utilisateursModifies' in r['HX-Trigger']
    agent.refresh_from_db()
    assert not agent.is_active
    r = client.post(reverse('utilisateurs-reactiver', kwargs={'id': agent.id}), HTTP_HX_REQUEST='true')
    assert r.status_code == 204
    agent.refresh_from_db()
    assert agent.is_active


def test_F05_mot_de_passe_reinitialise_lecture_unique_sans_cache(client, jeu):
    pr = _pr(jeu)
    agent = _compte_nomme(jeu, pr, 'agent-mdp')
    client.force_login(pr)
    r = client.post(reverse('utilisateurs-reinitialiser', kwargs={'id': agent.id}), HTTP_HX_REQUEST='true')
    assert r.status_code == 200
    html = r.content.decode()
    assert 'Mot de passe réinitialisé' in html and 'hx-history="false"' in html and 'data-copier' in html
    assert 'no-store' in r['Cache-Control']
    agent.refresh_from_db()
    assert agent.doit_changer_mot_de_passe
    valeur = html.split('data-valeur="')[-1].split('"')[0]  # le dernier : le mot de passe (le premier est l'identifiant)
    assert agent.check_password(valeur) and len(valeur) == 12
    assert valeur not in str(list(client.session.items()))
    assert valeur not in r['HX-Trigger']
    assert valeur not in client.get(reverse('utilisateurs')).content.decode()  # jamais réaffiché
    assert not JournalAction.objects.filter(motif__contains=valeur).exists()


def test_F02_nommer_par_modale_puis_mot_de_passe_une_fois(client, jeu):
    pr = _pr(jeu)
    membre = _membre_actif(jeu)
    client.force_login(pr)
    r = client.get(reverse('utilisateurs-nommer'), {'membre': membre.id}, HTTP_HX_REQUEST='true')
    assert r.status_code == 200 and 'Nommer le membre' in r.content.decode()
    rech = client.get(reverse('utilisateurs-membres-nommables'), {'q': 'Nommable'}, HTTP_HX_REQUEST='true').content.decode()
    assert 'Membre Nommable' in rech
    r = client.post(reverse('utilisateurs-nommer'), {'membre': membre.id, 'role': 'VA', 'antenne': jeu['antenne'].id}, HTTP_HX_REQUEST='true')
    assert r.status_code == 200 and 'Membre nommé' in r.content.decode() and 'no-store' in r['Cache-Control']
    assert Nomination.objects.filter(membre=membre, role='VA', active=True).exists() or Nomination.objects.filter(compte__membreId=membre.id, role='VA').exists()
    assert client.post(reverse('utilisateurs-nommer'), {'membre': membre.id, 'role': 'PR'}).status_code == 403
    r = client.post(reverse('utilisateurs-nommer'), {'membre': membre.id, 'role': 'VA', 'antenne': jeu['antenne'].id})
    assert r.status_code == 422


def test_F02_nommer_membre_non_actif_erreur_lisible(client, jeu):
    pr = _pr(jeu)
    membre = Membre.objects.create(nom='Pas Actif', date_naissance=date(1990, 1, 1), province=jeu['province'], antenne=jeu['antenne'],
                                   structure=jeu['association'])
    client.force_login(pr)
    r = client.post(reverse('utilisateurs-nommer'), {'membre': membre.id, 'role': 'AT', 'antenne': jeu['antenne'].id})
    assert r.status_code == 422 and 'actif' in r.content.decode()


def test_F03_compte_externe_pr_et_su_seulement(client, jeu):
    pr = _pr(jeu)
    client.force_login(pr)
    assert client.get(reverse('utilisateurs-externe')).status_code == 200
    r = client.post(reverse('utilisateurs-externe'), {'type': 'VI', 'username': 'vi.test', 'portee': 'national'}, HTTP_HX_REQUEST='true')
    assert r.status_code == 200 and 'Compte créé' in r.content.decode()
    assert client.post(reverse('utilisateurs-externe'), {'type': 'ED', 'username': 'ed.test'}).status_code == 403  # éditeur : SU seulement
    va = _compte_nomme(jeu, pr, 'un-va', role=roles.VA)
    client.force_login(va)
    assert client.get(reverse('utilisateurs-externe')).status_code == 403


def test_F06_mandats_a_traiter_et_renouvellement(client, jeu):
    pr = _pr(jeu)
    aujourdhui = timezone.localdate()
    echu = _compte_nomme(jeu, pr, 'mandat-echu', fin=aujourdhui - timedelta(days=5))
    _compte_nomme(jeu, pr, 'mandat-bientot', fin=aujourdhui + timedelta(days=20))
    client.force_login(pr)
    frag = client.get(reverse('utilisateurs'), {'zone': 'mandats'}, HTTP_HX_REQUEST='true').content.decode()
    assert 'échu depuis' in frag and 'dans 20 jours' in frag and 'Renouveler' in frag
    r = client.post(reverse('utilisateurs-renouveler', kwargs={'id': echu.id}), HTTP_HX_REQUEST='true')
    assert r.status_code == 204
    assert Nomination.objects.get(compte=echu, active=True).fin > aujourdhui + timedelta(days=365)
    assert Nomination.objects.filter(compte=echu, active=False).exists()


def test_F06_changer_de_role(client, jeu):
    pr = _pr(jeu)
    agent = _compte_nomme(jeu, pr, 'agent-promu')
    client.force_login(pr)
    r = client.post(reverse('utilisateurs-role', kwargs={'id': agent.id}), {'role': 'VA', 'antenne': jeu['antenne'].id}, HTTP_HX_REQUEST='true')
    assert r.status_code == 204
    assert Nomination.objects.get(compte=agent, active=True).role == 'VA'
    assert client.post(reverse('utilisateurs-role', kwargs={'id': agent.id}), {'role': 'VP'}).status_code == 422


def test_F02_menu_et_fiche_proposent_utilisateurs_et_nommer(client, jeu):
    pr = _pr(jeu)
    membre = _membre_actif(jeu)
    client.force_login(pr)
    assert reverse('utilisateurs') in client.get(reverse('liste-membre')).content.decode()
    fiche = client.get(reverse('membre-view', kwargs={'id': membre.id})).content.decode()
    assert reverse('utilisateurs-nommer') + '?membre=%d' % membre.id in fiche
    simple = _compte_nomme(jeu, pr, 'sans-droit')
    client.force_login(simple)
    assert reverse('utilisateurs') not in client.get(reverse('liste-membre')).content.decode()
