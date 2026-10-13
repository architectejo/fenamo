"""F-20 / § 9.1 : /mob/ (mobapp) repris au sous-lot 2c : non-régression des écrans et comportements de sécurité.

Les sept constats de sécurité de la revalidation 2b (GET qui modifie, espace ouvert à tous, connexion sans mot de passe,
mot de passe en clair, aucune limite de tentatives, engin ajouté par un anonyme, inscription sans antirobot) sont
désormais des tests NORMAUX qui passent.
"""
from datetime import date

import pytest
from django.contrib.auth.hashers import check_password, make_password
from django.urls import reverse

from coptapp.models import AssociationMembre, Membre, Moto, Ville
from tests.test_plan_url import hachage_rapide, jeu  # noqa: F401

MDP = 'Secret-fictif-91x'


def connecter(client, membre):
    """Ouvre la session mobile du membre comme le fait la connexion."""
    session = client.session
    session['mob_membre_id'] = membre.id
    session.save()


@pytest.fixture
def mob(jeu):
    """Un membre sans mot de passe (MBR0000001) et un membre avec mot de passe HACHÉ (MBR0000002)."""
    jeu['membre'].idf = 'MBR0000001'
    jeu['membre'].save()
    avec_mdp = Membre.objects.create(nom='Avec mot de passe', idf='MBR0000002', password=make_password(MDP),
                                     province=jeu['province'], ville=jeu['ville'], structure=jeu['association'])
    return {**jeu, 'avec_mdp': avec_mdp}


def _donnees_inscription(mob, **extra):
    d = {'province': mob['province'].id, 'nom': 'Inscrit Fictif', 'genre': 'HOMME', 'qualite': 'PROPRIETAIRE',
         'date_naissance': '1990-05-05', 'lieux_naissance': 'Kinshasa', 'password1': MDP, 'password2': MDP}
    d.update(extra)
    return d


ENGIN = {'num_plaque': 'AA-111', 'num_moteur': 'M1', 'num_chassie': 'C1', 'marque': 'X', 'couleur': 'ROUGE'}


# ---------------------------------------------------------------- non-régression : écrans et messages

def test_F20_mob_accueil_repond_200_anonyme(client, mob):
    r = client.get(reverse('home-mob'))
    assert r.status_code == 200 and 'mob/home.html' in [t.name for t in r.templates]


def test_F20_mob_identifiant_inconnu(client, mob):
    r = client.post(reverse('home-mob'), {'idf': 'INCONNU', 'pass': ''})
    assert r.status_code == 200 and 'Identifiant non reconnu' in r.content.decode()


def test_F20_mob_mauvais_mot_de_passe(client, mob):
    r = client.post(reverse('home-mob'), {'idf': 'MBR0000002', 'pass': 'faux'})
    assert r.status_code == 200 and 'Mot de passe incorrect' in r.content.decode()


def test_F20_mob_bon_mot_de_passe_ouvre_la_session_et_redirige_vers_l_espace(client, mob):
    r = client.post(reverse('home-mob'), {'idf': 'MBR0000002', 'pass': MDP})
    assert r.status_code == 302 and r['Location'] == reverse('session', kwargs={'id': mob['avec_mdp'].id})
    assert client.session['mob_membre_id'] == mob['avec_mdp'].id
    assert client.get(r['Location']).status_code == 200


def test_F20_mob_espace_et_donnees_du_membre_connecte(client, mob):
    connecter(client, mob['membre'])
    assert client.get(reverse('session', kwargs={'id': mob['membre'].id})).status_code == 200
    r = client.get(reverse('data', kwargs={'id': mob['membre'].id}))  # déjà rattaché à une antenne : retour à l'espace
    assert r.status_code == 302 and r['Location'] == reverse('session', kwargs={'id': mob['membre'].id})
    sans_ville = Membre.objects.create(nom='Sans ville', province=mob['province'])
    connecter(client, sans_ville)
    assert client.get(reverse('data', kwargs={'id': sans_ville.id})).status_code == 200


def test_F20_mob_inscription_page_creation_et_session(client, mob):
    assert client.get(reverse('register')).status_code == 200
    r = client.post(reverse('register'), _donnees_inscription(mob))
    membre = Membre.objects.get(nom='Inscrit Fictif')
    assert r.status_code == 302 and membre.idf == 'MBR' + str(membre.id).zfill(7)
    assert not membre.is_validate3 and not membre.is_delete and not membre.suppression_demandee
    assert client.session['mob_membre_id'] == membre.id and r['Location'] == reverse('data', kwargs={'id': membre.id})


def test_F20_mob_attribution_par_post_du_membre_connecte(client, mob):
    sans = Membre.objects.create(nom='Sans rattachement', province=mob['province'])
    connecter(client, sans)
    r = client.post(reverse('attribut-str', kwargs={'id': sans.id, 'id_str': mob['association'].id}))
    assert r.status_code == 302 and r['Location'] == reverse('data', kwargs={'id': sans.id})
    r = client.post(reverse('attribut-ville', kwargs={'id': sans.id, 'id_ville': mob['ville'].id}))
    assert r.status_code == 302 and r['Location'] == reverse('data', kwargs={'id': sans.id})
    sans.refresh_from_db()
    assert sans.structure_id == mob['association'].id and sans.ville_id == mob['ville'].id


@pytest.mark.parametrize('route, kwargs', [('home-mob', {}), ('register', {})])
def test_F20_mob_pages_publiques_sans_redirection_vers_la_connexion(client, mob, route, kwargs):
    r = client.get(reverse(route, kwargs=kwargs))
    assert r.status_code == 200 and '/connexion/' not in r.get('Location', '')


# ---------------------------------------------------------------- formulaire public : champs internes

def test_F20_mob_inscription_ne_pose_pas_les_champs_internes(client, mob):
    donnees = _donnees_inscription(
        mob, nom='Pirate Fictif', is_validate3='on', is_validate2='on', is_delete='on', suppression_demandee='on',
        motif_suppression='injecté', is_user='on', user=mob['compte'].id, structure=mob['association'].id, idf='MBR9999999')
    client.post(reverse('register'), donnees)
    membre = Membre.objects.get(nom='Pirate Fictif')
    assert not membre.is_validate3 and not membre.is_validate2 and not membre.is_delete
    assert not membre.suppression_demandee and membre.motif_suppression == ''
    assert not membre.is_user and membre.user_id is None and membre.structure_id is None
    assert membre.idf != 'MBR9999999' and membre.password != MDP and check_password(MDP, membre.password)


# ---------------------------------------------------------------- anciens constats de sécurité, maintenant corrigés

def test_F20_mob_un_GET_anonyme_ne_modifie_rien(client, mob):
    sans = Membre.objects.create(nom='Cible GET', province=mob['province'])
    autre = AssociationMembre.objects.create(nom='Autre', sigle='AU', num_justice='F-MOB-2', province=mob['province'])
    ville = Ville.objects.create(nom='Autre ville', province=mob['province'])
    for route, kwargs in (('attribut-str', {'id': sans.id, 'id_str': autre.id}),
                          ('attribut-ville', {'id': sans.id, 'id_ville': ville.id})):
        assert client.get(reverse(route, kwargs=kwargs)).status_code == 405  # POST seulement
        assert client.post(reverse(route, kwargs=kwargs)).status_code == 403  # et authentifié
    sans.refresh_from_db()
    assert sans.structure_id is None and sans.ville_id is None


def test_F20_mob_l_espace_d_un_membre_demande_une_authentification(client, mob):
    Moto.objects.create(proprietaire=mob['avec_mdp'], abonnement=date(2026, 1, 1), numero='SECRET1', num_plaque='ZZ-999')
    for route in ('session', 'data'):
        r = client.get(reverse(route, kwargs={'id': mob['avec_mdp'].id}))
        assert r.status_code == 403 and 'ZZ-999' not in r.content.decode()
    connecter(client, mob['membre'])  # connecté, mais pas en tant que ce membre
    assert client.get(reverse('session', kwargs={'id': mob['avec_mdp'].id})).status_code == 403
    connecter(client, mob['avec_mdp'])
    assert 'ZZ-999' in client.get(reverse('session', kwargs={'id': mob['avec_mdp'].id})).content.decode()


def test_F20_mob_membre_sans_mot_de_passe_ne_se_connecte_pas(client, mob):
    r = client.post(reverse('home-mob'), {'idf': 'MBR0000001', 'pass': ''})
    assert r.status_code == 200 and 'Mot de passe à définir' in r.content.decode() and 'contactez votre agent' in r.content.decode()
    assert 'mob_membre_id' not in client.session
    r = client.post(reverse('home-mob'), {'idf': 'MBR0000001', 'pass': 'nimporte'})
    assert r.status_code == 200 and 'mob_membre_id' not in client.session


def test_F20_mob_mot_de_passe_enregistre_hache(mob):
    mob['avec_mdp'].refresh_from_db()
    assert mob['avec_mdp'].password != MDP and check_password(MDP, mob['avec_mdp'].password)


def test_F20_mob_limite_de_tentatives(client, mob, settings):
    for _ in range(settings.AXES_FAILURE_LIMIT):
        assert client.post(reverse('home-mob'), {'idf': 'MBR0000002', 'pass': 'faux'}).status_code == 200
    r = client.post(reverse('home-mob'), {'idf': 'MBR0000002', 'pass': MDP})  # même le bon mot de passe est refusé
    assert r.status_code == 429 and 'mob_membre_id' not in client.session
    assert client.post(reverse('home-mob'), {'idf': 'MBR0000001', 'pass': 'x'}).status_code == 200  # autre identifiant : libre


def test_F20_mob_succes_efface_les_echecs(client, mob, settings):
    for _ in range(settings.AXES_FAILURE_LIMIT - 1):
        client.post(reverse('home-mob'), {'idf': 'MBR0000002', 'pass': 'faux'})
    assert client.post(reverse('home-mob'), {'idf': 'MBR0000002', 'pass': MDP}).status_code == 302
    for _ in range(settings.AXES_FAILURE_LIMIT - 1):
        client.post(reverse('home-mob'), {'idf': 'MBR0000002', 'pass': 'faux'})
    assert client.post(reverse('home-mob'), {'idf': 'MBR0000002', 'pass': 'faux'}).status_code == 200


def test_F20_mob_identifiants_inconnus_comptent_aussi(client, mob, settings):
    for i in range(settings.IP_ECHECS_MAX):
        client.post(reverse('home-mob'), {'idf': f'DEVINE{i}', 'pass': 'x'})
    assert client.post(reverse('home-mob'), {'idf': 'MBR0000002', 'pass': MDP}).status_code == 429


def test_F20_mob_un_anonyme_ne_peut_pas_ajouter_un_engin(client, mob):
    avant = Moto.objects.filter(proprietaire=mob['avec_mdp']).count()
    assert client.post(reverse('session', kwargs={'id': mob['avec_mdp'].id}), ENGIN).status_code == 403
    assert Moto.objects.filter(proprietaire=mob['avec_mdp']).count() == avant


def test_F20_mob_engin_ajoute_par_son_proprietaire_numerote_sous_verrou(client, mob):
    connecter(client, mob['avec_mdp'])
    url = reverse('session', kwargs={'id': mob['avec_mdp'].id})
    assert client.post(url, ENGIN).status_code == 200
    assert client.post(url, {**ENGIN, 'num_chassie': 'C2', 'num_moteur': 'M2'}).status_code == 200
    assert client.post(url, ENGIN).status_code == 200  # même châssis et moteur : refusé sans doublon
    numeros = sorted(Moto.objects.filter(proprietaire=mob['avec_mdp']).values_list('numero', flat=True))
    assert numeros == ['001PF', '002PF'] or numeros == ['002PF', '003PF']  # le jeu possède déjà l'engin 001PF


def test_F20_mob_engin_trop_long_refuse_et_coordination_inconnue_signalee(client, mob):
    connecter(client, mob['avec_mdp'])
    url = reverse('session', kwargs={'id': mob['avec_mdp'].id})
    avant = Moto.objects.count()
    client.post(url, {**ENGIN, 'num_plaque': 'x' * 40})
    assert Moto.objects.count() == avant
    sans_coordination = Membre.objects.create(nom='Sans coordination', password=make_password(MDP))
    connecter(client, sans_coordination)
    r = client.post(reverse('session', kwargs={'id': sans_coordination.id}), ENGIN)
    assert 'coordination provinciale est inconnue' in r.content.decode() and Moto.objects.count() == avant


def test_F20_mob_inscription_exige_un_mot_de_passe_valide(client, mob):
    for extra in ({'password1': '', 'password2': ''}, {'password2': 'autre-chose'}, {'password1': '123', 'password2': '123'}):
        r = client.post(reverse('register'), _donnees_inscription(mob, nom='Sans mdp', **extra))
        assert r.status_code == 200
    assert not Membre.objects.filter(nom='Sans mdp').exists()


def test_F20_mob_inscription_antirobot_champ_piege_et_limite_par_adresse(client, mob, settings):
    client.post(reverse('register'), _donnees_inscription(mob, nom='Robot piege', piege='http://spam'))
    assert not Membre.objects.filter(nom='Robot piege').exists()
    for i in range(settings.MOB_INSCRIPTIONS_PAR_HEURE):
        assert client.post(reverse('register'), _donnees_inscription(mob, nom=f'Robot {i}')).status_code == 302
    r = client.post(reverse('register'), _donnees_inscription(mob, nom='Robot de trop'))
    assert r.status_code == 429 and not Membre.objects.filter(nom='Robot de trop').exists()
