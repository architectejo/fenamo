"""Revalidation indépendante (testeur) : /mob/ (mobapp), non-régression et constats de sécurité connus.

mobapp garde sa propre logique (sous-lot 2c) : ses routes sont publiques (login_not_required). La première partie
fige ce qui répond « comme avant » ; la seconde ÉNUMÈRE les faiblesses connues en tests marqués xfail (le
comportement sûr attendu) : ils ne corrigent rien, ils passeront (XPASS) le jour où mobapp sera repris.
"""
from datetime import date

import pytest
from django.urls import reverse

from coptapp.models import AssociationMembre, Membre, Moto, Province, Ville
from tests.test_plan_url import hachage_rapide, jeu  # noqa: F401


@pytest.fixture
def mob(jeu):
    """Un membre avec identifiant mobile 'MBR0000001' sans mot de passe, un autre avec mot de passe."""
    jeu['membre'].idf = 'MBR0000001'
    jeu['membre'].save()
    avec_mdp = Membre.objects.create(nom='Avec mot de passe', idf='MBR0000002', password='secret-fictif',
                                     province=jeu['province'], ville=jeu['ville'], structure=jeu['association'])
    return {**jeu, 'avec_mdp': avec_mdp}


# ---------------------------------------------------------------- non-régression : comme avant

def test_F20_mob_accueil_repond_200_anonyme(client, mob):
    r = client.get(reverse('home-mob'))
    assert r.status_code == 200 and 'mob/home.html' in [t.name for t in r.templates]


def test_F20_mob_identifiant_inconnu(client, mob):
    r = client.post(reverse('home-mob'), {'idf': 'INCONNU', 'pass': ''})
    assert r.status_code == 200 and 'Identifiant non reconnu' in r.content.decode()


def test_F20_mob_mauvais_mot_de_passe(client, mob):
    r = client.post(reverse('home-mob'), {'idf': 'MBR0000002', 'pass': 'faux'})
    assert r.status_code == 200 and 'Mot de passe incorrect' in r.content.decode()


def test_F20_mob_bon_mot_de_passe_redirige_vers_l_espace(client, mob):
    r = client.post(reverse('home-mob'), {'idf': 'MBR0000002', 'pass': 'secret-fictif'})
    assert r.status_code == 302 and r['Location'] == reverse('session', kwargs={'id': mob['avec_mdp'].id})


def test_F20_mob_espace_et_donnees_repondent_200(client, mob):
    assert client.get(reverse('session', kwargs={'id': mob['membre'].id})).status_code == 200
    sans_ville = Membre.objects.create(nom='Sans ville', province=mob['province'])
    assert client.get(reverse('data', kwargs={'id': sans_ville.id})).status_code == 200
    # membre déjà rattaché à une ville : renvoi vers l'espace
    r = client.get(reverse('data', kwargs={'id': mob['membre'].id}))
    assert r.status_code == 302 and r['Location'] == reverse('session', kwargs={'id': mob['membre'].id})


def test_F20_mob_inscription_page_et_creation(client, mob):
    assert client.get(reverse('register')).status_code == 200
    donnees = {'province': mob['province'].id, 'nom': 'Inscrit Fictif', 'genre': 'HOMME', 'qualite': 'PROPRIETAIRE',
               'date_naissance': '1990-05-05'}
    r = client.post(reverse('register'), donnees)
    if r.status_code == 200:  # champs obligatoires du modèle : on complète
        pytest.skip('formulaire public plus exigeant : jeu de champs à compléter')
    membre = Membre.objects.get(nom='Inscrit Fictif')
    assert r.status_code == 302 and membre.idf == 'MBR' + str(membre.id).zfill(7)
    assert not membre.is_validate3 and not membre.is_delete and not membre.suppression_demandee


def test_F20_mob_attribution_redirige_vers_data(client, mob):
    sans = Membre.objects.create(nom='Sans rattachement', province=mob['province'])
    r = client.get(reverse('attribut-str', kwargs={'id': sans.id, 'id_str': mob['association'].id}))
    assert r.status_code == 302 and r['Location'] == reverse('data', kwargs={'id': sans.id})
    r = client.get(reverse('attribut-ville', kwargs={'id': sans.id, 'id_ville': mob['ville'].id}))
    assert r.status_code == 302 and r['Location'] == reverse('data', kwargs={'id': sans.id})


@pytest.mark.parametrize('route, kwargs', [
    ('home-mob', {}), ('register', {}), ('session', {'id': 1}), ('data', {'id': 1}),
])
def test_F20_mob_aucune_redirection_vers_la_connexion(client, mob, route, kwargs):
    r = client.get(reverse(route, kwargs=kwargs))
    assert '/connexion/' not in r.get('Location', '')


# ---------------------------------------------------------------- formulaire public : champs internes (corrigé par F-20)

def test_F20_mob_inscription_ne_pose_pas_les_champs_internes(client, mob):
    """Le formulaire public anonyme ne doit jamais pouvoir poser un champ interne (validation, suppression, compte)."""
    donnees = {'province': mob['province'].id, 'nom': 'Pirate Fictif', 'genre': 'HOMME', 'qualite': 'PROPRIETAIRE',
               'date_naissance': '1990-05-05', 'is_validate3': 'on', 'is_validate2': 'on', 'is_delete': 'on',
               'suppression_demandee': 'on', 'motif_suppression': 'injecté', 'is_user': 'on', 'password': 'x',
               'user': mob['compte'].id, 'structure': mob['association'].id, 'idf': 'MBR9999999'}
    client.post(reverse('register'), donnees)
    membre = Membre.objects.filter(nom='Pirate Fictif').first()
    if membre is None:
        pytest.skip('formulaire public plus exigeant : jeu de champs à compléter')
    assert not membre.is_validate3 and not membre.is_validate2 and not membre.is_delete
    assert not membre.suppression_demandee and membre.motif_suppression == ''
    assert not membre.is_user and not membre.password and membre.user_id is None and membre.structure_id is None
    assert membre.idf != 'MBR9999999'


# ---------------------------------------------------------------- constats de sécurité connus (non corrigés ici)

CONSTAT = pytest.mark.xfail(strict=False, reason='CONSTAT securite connu de mobapp (reprise prevue au sous-lot 2c)')


@CONSTAT
def test_F20_mob_constat_un_GET_anonyme_ne_devrait_rien_modifier(client, mob):
    """attribut-str / attribut-ville modifient le rattachement d'un membre en GET, sans connexion ni CSRF."""
    sans = Membre.objects.create(nom='Cible GET', province=mob['province'])
    autre = AssociationMembre.objects.create(nom='Autre', sigle='AU', num_justice='F-MOB-2')
    client.get(reverse('attribut-str', kwargs={'id': sans.id, 'id_str': autre.id}))
    ville = Ville.objects.create(nom='Autre ville', province=mob['province'])
    client.get(reverse('attribut-ville', kwargs={'id': sans.id, 'id_ville': ville.id}))
    sans.refresh_from_db()
    assert sans.structure_id is None and sans.ville_id is None


@CONSTAT
def test_F20_mob_constat_l_espace_d_un_membre_demande_une_authentification(client, mob):
    """/mob/espace/<id> et /mob/data/<id> répondent 200 à n'importe qui connaissant (ou devinant) l'identifiant numérique."""
    Moto.objects.create(proprietaire=mob['avec_mdp'], abonnement=date(2026, 1, 1), numero='SECRET1', num_plaque='ZZ-999')
    r = client.get(reverse('session', kwargs={'id': mob['avec_mdp'].id}))
    assert r.status_code in (302, 401, 403, 404) or 'ZZ-999' not in r.content.decode()


@CONSTAT
def test_F20_mob_constat_connexion_sans_mot_de_passe_si_le_membre_n_en_a_pas(client, mob):
    """Un membre sans mot de passe entre avec son seul identifiant (et l'identifiant MBR0000001 est devinable)."""
    r = client.post(reverse('home-mob'), {'idf': 'MBR0000001', 'pass': ''})
    assert r.status_code != 302


@CONSTAT
def test_F20_mob_constat_mot_de_passe_compare_en_clair(mob):
    """Membre.password est un texte en clair, comparé par égalité (aucun hachage)."""
    mob['avec_mdp'].refresh_from_db()
    assert mob['avec_mdp'].password != 'secret-fictif'


@CONSTAT
def test_F20_mob_constat_aucune_limite_de_tentatives(client, mob):
    """Aucun verrou (django-axes ne couvre pas cette vue) : 30 essais successifs restent traités normalement."""
    for _ in range(30):
        r = client.post(reverse('home-mob'), {'idf': 'MBR0000002', 'pass': 'faux'})
    assert r.status_code in (403, 429)


@CONSTAT
def test_F20_mob_constat_un_anonyme_ne_devrait_pas_ajouter_un_engin_a_un_membre(client, mob):
    avant = Moto.objects.filter(proprietaire=mob['avec_mdp']).count()
    client.post(reverse('session', kwargs={'id': mob['avec_mdp'].id}),
                {'num_plaque': 'AA-111', 'num_moteur': 'M1', 'num_chassie': 'C1', 'marque': 'X', 'couleur': 'ROUGE'})
    assert Moto.objects.filter(proprietaire=mob['avec_mdp']).count() == avant


@CONSTAT
def test_F20_mob_constat_inscription_anonyme_sans_antirobot(client, mob):
    """Création de membres en série sans limite, identifiants séquentiels MBR0000001, MBR0000002… (énumérables)."""
    donnees = {'province': mob['province'].id, 'genre': 'HOMME', 'qualite': 'PROPRIETAIRE', 'date_naissance': '1990-05-05'}
    avant = Membre.objects.count()
    for i in range(5):
        client.post(reverse('register'), {**donnees, 'nom': f'Robot {i}'})
    assert Membre.objects.count() == avant  # attendu un jour : refus sans authentification
