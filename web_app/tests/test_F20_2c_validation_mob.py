"""Validation indépendante 2c : /mob/ (connexion, 429, session, CSRF, photo, inscription), verrou IP partagé avec la
connexion web et anciens constats de sécurité, aujourd'hui corrigés (plus aucun xfail ; ils auraient échoué, en strict, le jour où
backend-django aura corrigé : retirer alors le marqueur)."""
import re
from html import unescape

import pytest
from axes.models import AccessFailureLog
from django.contrib.auth.hashers import check_password, make_password
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from coptapp.models import AssociationMembre, Membre
from compte.services.mobile import definir_mot_de_passe_membre, empreinte_session
from tests.test_plan_url import hachage_rapide, jeu  # noqa: F401

MDP = 'Secret-fictif-91x'


@pytest.fixture
def mob(jeu):
    jeu['membre'].idf = 'MBR0000001'
    jeu['membre'].save()
    avec = Membre.objects.create(nom='Avec mdp', idf='MBR0000002', password=make_password(MDP), province=jeu['province'],
                                 ville=jeu['ville'], structure=jeu['association'])
    autre = Membre.objects.create(nom='Autre membre', idf='MBR0000003', password=make_password(MDP),
                                  province=jeu['province'])
    return {**jeu, 'avec': avec, 'autre': autre}


def connecter(client, membre):
    s = client.session
    s['mob_membre_id'] = membre.id
    s['mob_empreinte'] = empreinte_session(Membre.objects.get(pk=membre.pk))
    s.save()


PHRASES = ('Identifiant ou mot de passe incorrect', "Trop d'essais")


def _msg(r):
    """La phrase d'erreur de la page (ou None si aucune des phrases connues)."""
    corps = unescape(r.content.decode())
    trouvees = [p for p in PHRASES if p in corps]
    return trouvees[0] if trouvees else None


def _post(client, idf, mdp):
    return client.post(reverse('home-mob'), {'idf': idf, 'pass': mdp})


# ---------------------------------------------------------------- connexion

def test_F20_2c_connexion_mot_de_passe_correct(client, mob):
    r = _post(client, 'MBR0000002', MDP)
    assert r.status_code == 302 and client.session['mob_membre_id'] == mob['avec'].id


@pytest.mark.parametrize('idf, mdp', [
    ('MBR0000002', 'mauvais'), ('MBR0000002', ''), ('MBR0000002', MDP.upper()), ('MBR0000002', MDP + ' '),
    ('MBR0000001', ''), ('MBR0000001', 'x'), ('INCONNU', MDP), ('', ''), ('', MDP), ('   ', MDP), ('MBR0000002 ', 'faux'),
    ('mbr0000002', MDP),
])
def test_F20_2c_connexion_refusee_sans_session(client, mob, idf, mdp):
    r = _post(client, idf, mdp)
    assert r.status_code == 200 and 'mob_membre_id' not in client.session


def test_F20_2c_connexion_membre_supprime_refusee(client, mob):
    Membre.objects.filter(pk=mob['avec'].pk).update(etat='supprime', etat_precedent='saisi')
    assert _post(client, 'MBR0000002', MDP).status_code == 200 and 'mob_membre_id' not in client.session


def test_F20_2c_connexion_get_ne_cree_pas_de_session_membre(client, mob):
    assert client.get(reverse('home-mob'), {'idf': 'MBR0000002', 'pass': MDP}).status_code == 200
    assert 'mob_membre_id' not in client.session


def test_F20_2c_message_unique_pour_tout_echec(client, mob):
    inconnu = _msg(_post(client, 'INCONNU', 'x'))
    faux = _msg(_post(Client(), 'MBR0000002', 'x'))
    sans = _msg(_post(Client(), 'MBR0000001', 'x'))
    assert inconnu == faux == sans == 'Identifiant ou mot de passe incorrect'


def test_F20_2c_echec_compte_dans_toutes_les_branches_y_compris_sans_mot_de_passe(client, mob, settings):
    for _ in range(settings.AXES_FAILURE_LIMIT):
        assert _post(client, 'MBR0000001', 'x').status_code == 200  # membre SANS mot de passe
    assert _post(client, 'MBR0000001', 'x').status_code == 429


def test_F20_2c_hachage_factice_pour_un_identifiant_inconnu(client, mob, monkeypatch):
    appels = []
    import compte.services.mobile as mobile
    vrai = mobile.check_password
    monkeypatch.setattr(mobile, 'check_password', lambda mot, hache: appels.append(hache) or vrai(mot, hache))
    _post(client, 'INCONNU', 'x')
    _post(Client(), 'MBR0000001', 'x')  # sans mot de passe
    assert len(appels) == 2  # un hachage est toujours calculé, même sans membre ou sans mot de passe


def test_F20_2c_meme_message_pour_tout_echec(mob):
    messages = {_msg(_post(Client(), 'INCONNU', 'x')), _msg(_post(Client(), 'MBR0000002', 'x')),
                _msg(_post(Client(), 'MBR0000001', 'x'))}
    assert None not in messages and len(messages) == 1


def test_F20_2c_429_apres_n_echecs_meme_avec_le_bon_mot_de_passe(client, mob, settings):
    for _ in range(settings.AXES_FAILURE_LIMIT):
        assert _post(client, 'MBR0000002', 'faux').status_code == 200
    r = _post(client, 'MBR0000002', MDP)
    assert r.status_code == 429 and 'mob_membre_id' not in client.session
    assert _post(client, 'mbr0000002', MDP).status_code == 429  # la casse ne contourne pas le verrou
    assert _post(client, ' MBR0000002 ', MDP).status_code == 429  # ni les espaces autour
    assert _post(client, 'MBR0000003', MDP).status_code == 302  # un autre identifiant n'est pas touché


def test_F20_2c_429_ne_depend_pas_du_contenu_pour_un_identifiant_inconnu(client, mob, settings):
    for _ in range(settings.AXES_FAILURE_LIMIT):
        _post(client, 'FANTOME', 'x')
    assert _post(client, 'FANTOME', 'x').status_code == 429


def test_F20_2c_succes_efface_les_echecs_de_cet_identifiant_seulement(client, mob, settings):
    for _ in range(settings.AXES_FAILURE_LIMIT - 1):
        _post(client, 'MBR0000002', 'faux')
        _post(client, 'MBR0000003', 'faux')
    assert _post(client, 'MBR0000002', MDP).status_code == 302
    c = Client()
    assert AccessFailureLog.objects.filter(username='mob:mbr0000002').count() == 0
    assert AccessFailureLog.objects.filter(username='mob:mbr0000003').count() == settings.AXES_FAILURE_LIMIT - 1
    _post(c, 'MBR0000003', 'faux')
    assert _post(c, 'MBR0000003', MDP).status_code == 429


def test_F20_2c_echecs_et_inscriptions_mob_ne_bloquent_pas_la_connexion_web(client, mob, settings):
    """Les échecs /mob/ (pseudos « mob:… ») et les inscriptions (« mob-inscription ») ne comptent pas dans le verrou par
    adresse IP de /connexion/ : /mob/ a son propre compteur."""
    for i in range(settings.IP_ECHECS_MAX):
        _post(Client(), f'FANTOME{i}', 'x')
    for _ in range(settings.IP_ECHECS_MAX):
        AccessFailureLog.objects.create(username='mob-inscription', ip_address='127.0.0.1', user_agent='t', http_accept='',
                                        path_info='/mob/register/', attempt_time=timezone.now(), locked_out=False)
    r = Client().post(reverse('application'), {'username': 'admin-test', 'password': 'mot-de-passe-test-123'})
    assert r.status_code != 429


def test_F20_2c_verrou_web_ne_bloque_pas_mob(client, mob, settings):
    for _ in range(settings.IP_ECHECS_MAX + 2):
        AccessFailureLog.objects.create(username='quelquun', ip_address='127.0.0.1', user_agent='t', http_accept='',
                                        path_info='/connexion/', attempt_time=timezone.now(), locked_out=False)
    assert _post(client, 'MBR0000002', MDP).status_code == 302


# ---------------------------------------------------------------- espace, données, attributs, photo

@pytest.mark.parametrize('route', ['session', 'data'])
def test_F20_2c_espace_et_data_d_un_autre_membre_403(client, mob, route):
    connecter(client, mob['autre'])
    r = client.get(reverse(route, kwargs={'id': mob['avec'].id}))
    assert r.status_code == 403 and 'Avec mdp' not in r.content.decode()
    r = client.post(reverse(route, kwargs={'id': mob['avec'].id}), {})
    assert r.status_code == 403


@pytest.mark.parametrize('route, args', [('attribut-str', 'id_str'), ('attribut-ville', 'id_ville')])
def test_F20_2c_attribut_get_405_post_autre_membre_403(client, mob, route, args):
    cible = mob['association'].id if args == 'id_str' else mob['ville'].id
    sans = Membre.objects.create(nom='Sans rattachement', province=mob['province'])
    url = reverse(route, kwargs={'id': sans.id, args: cible})
    connecter(client, sans)
    assert client.get(url).status_code == 405
    connecter(client, mob['autre'])
    assert client.post(url).status_code == 403
    sans.refresh_from_db()
    assert sans.structure_id is None and sans.ville_id is None


@pytest.mark.parametrize('route, args', [('attribut-str', 'id_str'), ('attribut-ville', 'id_ville')])
def test_F20_2c_attribut_post_sans_csrf_403_avec_csrf_302(mob, route, args):
    cible = mob['association'].id if args == 'id_str' else mob['ville'].id
    sans = Membre.objects.create(nom='Sans rattachement', province=mob['province'])
    c = Client(enforce_csrf_checks=True)
    connecter(c, sans)
    url = reverse(route, kwargs={'id': sans.id, args: cible})
    assert c.post(url).status_code == 403
    sans.refresh_from_db()
    assert sans.structure_id is None and sans.ville_id is None
    page = c.get(reverse('data', kwargs={'id': sans.id}))
    jeton = c.cookies['csrftoken'].value
    assert page.status_code == 200
    assert c.post(url, HTTP_X_CSRFTOKEN=jeton).status_code == 302


def test_F20_2c_attribut_hors_coordination_du_membre_404(client, mob):
    autre_province = type(mob['province']).objects.create(nom='Autre province', sigle='AP')
    etrangere = AssociationMembre.objects.create(nom='Etrangère', sigle='ET', province=autre_province, ville=None,
                                                 num_justice='F-9')
    sans = Membre.objects.create(nom='Sans', province=mob['province'])
    connecter(client, sans)
    assert client.post(reverse('attribut-str', kwargs={'id': sans.id, 'id_str': etrangere.id})).status_code == 404


def _jpeg():
    import io

    from PIL import Image
    t = io.BytesIO()
    Image.new('RGB', (40, 40)).save(t, 'JPEG')
    return t.getvalue()


def test_F20_2c_photo_mob_autre_membre_ou_anonyme_403(client, mob, settings, tmp_path):
    settings.PRIVATE_MEDIA_ROOT = tmp_path / 'prive'
    mob['avec'].photo = SimpleUploadedFile('p.jpg', _jpeg())
    mob['avec'].save()
    url = reverse('photo-mob', kwargs={'id': mob['avec'].id})
    assert client.get(url).status_code == 403
    connecter(client, mob['autre'])
    assert client.get(url).status_code == 403 and client.get(url, {'vignette': '1'}).status_code == 403
    connecter(client, mob['avec'])
    r = client.get(url)
    r.close()
    assert r.status_code == 200 and r['X-Content-Type-Options'] == 'nosniff' and r['Content-Type'] == 'image/jpeg'
    assert 'secret' not in r['Content-Disposition']


# ---------------------------------------------------------------- inscription

def _insc(mob, **extra):
    d = {'province': mob['province'].id, 'nom': 'Inscrit', 'genre': 'HOMME', 'qualite': 'PROPRIETAIRE',
         'date_naissance': '1990-05-05', 'lieux_naissance': 'Kinshasa', 'password1': MDP, 'password2': MDP}
    d.update(extra)
    return d


@pytest.mark.parametrize('extra', [
    {'password2': 'Different-9x'}, {'password1': '', 'password2': ''}, {'password1': '12345678', 'password2': '12345678'},
    {'password1': 'court', 'password2': 'court'}, {'password1': 'azertyuiop', 'password2': 'azertyuiop'},
    {'piege': 'x'}, {'piege': 'http://spam.invalid'},
])
def test_F20_2c_inscription_refusee(client, mob, extra):
    avant = Membre.objects.count()
    r = client.post(reverse('register'), _insc(mob, nom='Refuse', **extra))
    assert r.status_code == 200 and Membre.objects.count() == avant and 'mob_membre_id' not in client.session


def test_F20_2c_inscription_refusee_ne_compte_pas_dans_la_limite_horaire(client, mob, settings):
    for _ in range(settings.MOB_INSCRIPTIONS_PAR_HEURE + 3):
        client.post(reverse('register'), _insc(mob, nom='Refuse', password2='autre'))
    assert client.post(reverse('register'), _insc(mob, nom='Premier valide')).status_code == 302


def test_F20_2c_sixieme_inscription_par_heure_refusee(client, mob, settings):
    assert settings.MOB_INSCRIPTIONS_PAR_HEURE == 5
    for i in range(5):
        assert Client().post(reverse('register'), _insc(mob, nom=f'Robot {i}')).status_code == 302
    r = Client().post(reverse('register'), _insc(mob, nom='Sixieme'))
    assert r.status_code == 429 and not Membre.objects.filter(nom='Sixieme').exists()
    # une heure plus tard : de nouveau possible
    AccessFailureLog.objects.filter(username='mob-inscription').update(attempt_time=timezone.now() - timezone.timedelta(hours=2))
    assert Client().post(reverse('register'), _insc(mob, nom='Septieme')).status_code == 302


def test_F20_2c_inscription_mot_de_passe_hache_et_session_ouverte(client, mob):
    r = client.post(reverse('register'), _insc(mob, nom='Nouveau'))
    m = Membre.objects.get(nom='Nouveau')
    assert r.status_code == 302 and m.password != MDP and check_password(MDP, m.password)
    assert client.session['mob_membre_id'] == m.id and m.idf.startswith('MBR')
    assert client.get(reverse('session', kwargs={'id': m.id})).status_code == 200


# ---------------------------------------------------------------- anciens constats de sécurité, corrigés

def test_F20_2c_session_mobile_invalidee_par_changement_de_mot_de_passe(client, mob):
    assert _post(client, 'MBR0000002', MDP).status_code == 302
    url = reverse('session', kwargs={'id': mob['avec'].id})
    assert client.get(url).status_code == 200
    definir_mot_de_passe_membre(mob['compte'], mob['avec'])  # un agent réinitialise le mot de passe
    assert client.get(url).status_code == 403


def test_F20_2c_mob_pages_personnelles_no_store(client, mob):
    connecter(client, mob['avec'])
    r = client.get(reverse('session', kwargs={'id': mob['avec'].id}))
    assert r.status_code == 200 and 'no-store' in r.get('Cache-Control', '')


def test_F20_2c_formulaire_public_sans_numero_de_carte_de_membre(client, mob):
    from mobapp.forms import InscriptionMobileForm
    assert 'numero_carte_de_membre' not in InscriptionMobileForm().fields
    client.post(reverse('register'), _insc(mob, nom='Carte forgée', numero_carte_de_membre='CARTE-FORGEE'))
    assert Membre.objects.get(nom='Carte forgée').numero_carte_de_membre in (None, '')


def test_F20_2c_deconnexion_post_seulement_ferme_la_session_mobile(client, mob):
    connecter(client, mob['avec'])
    url = reverse('session', kwargs={'id': mob['avec'].id})
    assert client.get(url).status_code == 200
    assert client.get(reverse('deconnexion-mob')).status_code == 405
    assert client.get(url).status_code == 200  # un GET ne déconnecte pas
    r = client.post(reverse('deconnexion-mob'))
    assert r.status_code == 302 and r['Location'] == reverse('home-mob')
    assert 'mob_membre_id' not in client.session and client.get(url).status_code == 403


def test_F20_2c_la_deconnexion_mobile_garde_la_session_du_site(client, mob):
    client.force_login(mob['compte'])
    connecter(client, mob['avec'])
    client.post(reverse('deconnexion-mob'))
    assert client.get(reverse('tableau-bord')).status_code == 200  # toujours connecté à l'application web


def test_F20_2c_session_mobile_sans_empreinte_ou_avec_une_autre_refusee(client, mob):
    url = reverse('session', kwargs={'id': mob['avec'].id})
    s = client.session
    s['mob_membre_id'] = mob['avec'].id  # identifiant seul, sans empreinte : forgé
    s.save()
    assert client.get(url).status_code == 403
    s['mob_empreinte'] = 'x' * 40
    s.save()
    assert client.get(url).status_code == 403
    connecter(client, mob['autre'])
    s = client.session
    s['mob_membre_id'] = mob['avec'].id  # empreinte d'un autre membre
    s.save()
    assert client.get(url).status_code == 403


@pytest.mark.parametrize('route', ['session', 'data'])
def test_F20_2c_pages_mob_no_store_aussi_quand_la_session_mobile_existe(client, mob, route):
    sans_ville = Membre.objects.create(nom='Sans ville', password=make_password(MDP), province=mob['province'])
    connecter(client, sans_ville)
    r = client.get(reverse(route, kwargs={'id': sans_ville.id}))
    assert r.status_code in (200, 302) and 'no-store' in r['Cache-Control']
    assert 'no-store' in client.get(reverse('home-mob'))['Cache-Control']
    assert 'no-store' in client.get(reverse('register'))['Cache-Control']
