"""F-02 : bouton « Nommer » sur chaque ligne de la liste des membres, modale préremplie, identifiants à lecture unique."""
from datetime import date

from django.urls import reverse

from compte import roles
from compte.models import Compte, Nomination
from coptapp.models import Membre
from tests.test_plan_url import hachage_rapide, jeu  # noqa: F401

HX = {'HTTP_HX_REQUEST': 'true'}


def _membre(jeu, nom, etat='actif'):
    return Membre.objects.create(nom=nom, date_naissance=date(1990, 1, 1), province=jeu['province'], ville=jeu['ville'],
                                 antenne=jeu['antenne'], structure=jeu['association'], etat=etat)


def _compte(jeu, nom, role, **perimetre):
    c = Compte.objects.create_user(nom, password='x')
    Nomination.objects.create(compte=c, role=role, nomme_par=jeu['compte'], **perimetre)
    return c


def test_F02_bouton_nommer_visible_pour_le_membre_nommable_seulement(client, jeu):
    actif = _membre(jeu, 'Zacharie Actif')
    saisi = _membre(jeu, 'Yves Saisi', etat='saisi')
    client.force_login(jeu['compte'])
    html = client.get(reverse('liste-membre'), **HX).content.decode()
    assert f'utilisateurs/nommer/?membre={actif.id}&amp;fixe=1' in html and '#i-user-cog' in html
    assert f'membre={saisi.id}' not in html
    assert 'Pas encore actif' not in html or 'disabled' in html


def test_F02_ligne_deja_utilisateur_affiche_le_role_sans_bouton(client, jeu):
    deja = _membre(jeu, 'Dora Déjà')
    compte = Compte.objects.create_user('dora', password='x')
    compte.membreId = deja.id
    compte.save()
    Nomination.objects.create(compte=compte, role=roles.AT, antenne=jeu['antenne'], nomme_par=jeu['compte'])
    client.force_login(jeu['compte'])
    html = client.get(reverse('liste-membre'), **HX).content.decode()
    assert 'role-code' in html and f'membre={deja.id}&amp;fixe=1' not in html


def test_F02_bouton_cache_sans_droit_de_nommer(client, jeu):
    _membre(jeu, 'Walter Actif')
    vi = _compte(jeu, 'visiteur', roles.VI)
    client.force_login(vi)
    r = client.get(reverse('liste-membre'), **HX)
    assert r.status_code == 200 and 'utilisateurs/nommer' not in r.content.decode()


def test_F02_modale_preremplie_sans_recherche_et_raison_si_refus(client, jeu):
    actif = _membre(jeu, 'Xavier Actif')
    saisi = _membre(jeu, 'Yvonne Saisie', etat='saisi')
    client.force_login(jeu['compte'])
    html = client.get(reverse('utilisateurs-nommer'), {'membre': actif.id, 'fixe': '1'}, **HX).content.decode()
    assert 'data-etape="2"' in html and 'Xavier Actif' in html and 'name="fixe"' in html and 'Changer' not in html
    assert 'Début du mandat' in html and 'Fin du mandat' in html and 'art. 72 à 75' in html
    refus = client.get(reverse('utilisateurs-nommer'), {'membre': saisi.id, 'fixe': '1'}, **HX).content.decode()
    assert 'Pas encore actif' in refus and 'disabled' in refus


def test_F02_post_nominal_identifiants_a_lecture_unique(client, jeu):
    actif = _membre(jeu, 'Élise Martin')
    client.force_login(jeu['compte'])
    r = client.post(reverse('utilisateurs-nommer'), {'membre': actif.id, 'role': 'AT', 'antenne': jeu['antenne'].id, 'fixe': '1'}, **HX)
    assert r.status_code == 200
    html = r.content.decode()
    compte = Compte.objects.get(membreId=actif.id)
    assert compte.username.startswith('elise') and compte.username.endswith('@fenamordc.hub')
    assert html.count(compte.username) >= 3 and html.count('data-copier=') == 2 and 'hx-history="false"' in html
    assert 'première connexion' in html
    assert 'no-store' in r['Cache-Control']
    assert compte.username not in r.get('HX-Trigger', '')
    assert compte.username not in ''.join(str(m) for m in client.session.get('_messages', ''))
    assert compte.doit_changer_mot_de_passe
    # la liste se rafraîchit seule : événement + ligne passée à « utilisateur »
    assert 'membresMaj' in r['HX-Trigger']
    liste = client.get(reverse('liste-membre'), **HX).content.decode()
    assert 'role-code' in liste and f'membre={actif.id}&amp;fixe=1' not in liste


def test_F02_refus_403_sans_droit_et_404_hors_perimetre(client, jeu):
    actif = _membre(jeu, 'Victor Actif')
    vi = _compte(jeu, 'visiteur2', roles.VI)
    client.force_login(vi)
    assert client.post(reverse('utilisateurs-nommer'), {'membre': actif.id, 'role': 'AT', 'antenne': jeu['antenne'].id}).status_code == 403
    assert client.get(reverse('utilisateurs-nommer'), {'membre': actif.id}).status_code == 403
    client.force_login(jeu['compte'])
    assert client.get(reverse('utilisateurs-nommer'), {'membre': 999999, 'fixe': '1'}).status_code == 404
