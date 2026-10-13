"""F-20 / § 9.1 : mots de passe de l'espace mobile (migration de hachage, définition par un agent) et numérotation des engins."""
import json
from datetime import date
from io import StringIO

import pytest
from django.contrib.auth.hashers import check_password, identify_hasher, make_password
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import Client
from django.urls import reverse

from compte.models import Compte, JournalAction
from compte.services.mobile import definir_mot_de_passe_membre, mot_de_passe_temporaire
from coptapp.models import Membre, Moto, Province
from coptapp.services.engins import enregistrer_engin, numero_suivant
from tests.test_F21_matrice_routes import acteurs  # noqa: F401
from tests.test_plan_url import hachage_rapide, jeu  # noqa: F401


# ---------------------------------------------------------------- migration de hachage (base fictive)

@pytest.mark.django_db(transaction=True)
def test_F20_migration_hache_les_mots_de_passe_en_clair_et_se_rejoue():
    executeur = MigrationExecutor(connection)
    executeur.migrate([('coptapp', '0054_membre_password_128')])
    ancien = executeur.loader.project_state([('coptapp', '0054_membre_password_128')]).apps.get_model('coptapp', 'Membre')
    deja = make_password('deja-hache')
    ancien.objects.create(nom='Clair', password='motdepasse-en-clair')
    ancien.objects.create(nom='Hache', password=deja)
    ancien.objects.create(nom='Vide', password='')
    ancien.objects.create(nom='Nul', password=None)
    executeur = MigrationExecutor(connection)
    executeur.migrate([('coptapp', '0055_hacher_mots_de_passe_des_membres')])
    from django.apps import apps
    Membre_ = executeur.loader.project_state([('coptapp', '0055_hacher_mots_de_passe_des_membres')]).apps.get_model('coptapp', 'Membre')
    clair = Membre_.objects.get(nom='Clair')
    assert clair.password != 'motdepasse-en-clair' and identify_hasher(clair.password) and check_password('motdepasse-en-clair', clair.password)
    assert Membre_.objects.get(nom='Hache').password == deja  # déjà un hachage : inchangé
    assert Membre_.objects.get(nom='Vide').password == '' and Membre_.objects.get(nom='Nul').password is None
    # rejouée (retour en arrière = no-op, puis nouvelle application) : aucun double hachage
    executeur = MigrationExecutor(connection)
    executeur.migrate([('coptapp', '0054_membre_password_128')])
    assert Membre_.objects.get(nom='Clair').password == clair.password
    executeur = MigrationExecutor(connection)
    executeur.migrate(executeur.loader.graph.leaf_nodes())
    assert Membre_.objects.get(nom='Clair').password == clair.password


# ---------------------------------------------------------------- définition d'un mot de passe temporaire

def test_F20_mot_de_passe_temporaire_aleatoire_et_lisible():
    mots = {mot_de_passe_temporaire() for _ in range(50)}
    assert len(mots) == 50 and all(len(m) == 8 and m.isalnum() and not set('0o1li') & set(m) for m in mots)


def test_F20_definir_mot_de_passe_hache_journalise_sans_le_mot_de_passe(jeu):
    jeu['membre'].idf = 'MBR0000001'
    jeu['membre'].save()
    clair = definir_mot_de_passe_membre(jeu['compte'], jeu['membre'])
    jeu['membre'].refresh_from_db()
    assert jeu['membre'].password != clair and check_password(clair, jeu['membre'].password)
    ligne = JournalAction.objects.get(action=JournalAction.Action.CHANGEMENT_MOT_DE_PASSE, objet_id=jeu['membre'].id)
    assert ligne.auteur == jeu['compte'] and clair not in json.dumps([ligne.avant, ligne.apres, ligne.motif, ligne.objet_libelle])
    assert clair not in jeu['membre'].password


def test_F20_commande_definir_mot_de_passe_membre(jeu):
    jeu['membre'].idf = 'MBR0000001'
    jeu['membre'].save()
    sortie = StringIO()
    call_command('definir_mot_de_passe_membre', 'MBR0000001', '--auteur', jeu['compte'].username, stdout=sortie)
    clair = sortie.getvalue().strip().rsplit(' ', 1)[1]
    jeu['membre'].refresh_from_db()
    assert check_password(clair, jeu['membre'].password)
    with pytest.raises(CommandError):
        call_command('definir_mot_de_passe_membre', 'INCONNU', '--auteur', jeu['compte'].username)
    with pytest.raises(CommandError):
        call_command('definir_mot_de_passe_membre', 'MBR0000001', '--auteur', 'personne')
    nu = Compte.objects.create_user('nu', password='x')
    with pytest.raises(CommandError):
        call_command('definir_mot_de_passe_membre', 'MBR0000001', '--auteur', 'nu')


def test_F20_vue_definir_mot_de_passe_mobile_affiche_une_fois_et_respecte_les_droits(client, acteurs):
    Membre.objects.filter(pk=acteurs['membre'].pk).update(idf='MBR0000009')
    url = reverse('mot-de-passe-mobile', kwargs={'id': acteurs['membre'].id})
    client.force_login(acteurs['comptes']['p1'])  # agent : saisie de ce membre
    r = client.post(url, follow=True)
    corps = r.content.decode()
    assert r.status_code == 200 and 'Mot de passe temporaire' in corps and 'MBR0000009' in corps
    assert 'Mot de passe temporaire' not in client.get(reverse('membre-view', kwargs={'id': acteurs['membre'].id})).content.decode()
    acteurs['membre'].refresh_from_db()
    assert acteurs['membre'].password and acteurs['membre'].password.startswith(('pbkdf2', 'md5'))
    for profil, statut in (('p4', 404), ('nu', 404), ('ed', 404)):
        client.force_login(acteurs['comptes'][profil])
        assert client.post(url).status_code == statut, profil
    assert client.get(url).status_code == 405


# ---------------------------------------------------------------- numérotation des engins (F-31)

def test_F31_numero_suivant_par_coordination_et_code(jeu):
    assert numero_suivant(jeu['province']) == '002PF'  # le jeu possède déjà l'engin 001PF
    autre = Province.objects.create(nom='Autre province', sigle='AP')
    assert numero_suivant(autre) == '001AP'


def test_F31_numeros_uniques_et_croissants_apres_une_suppression(jeu):
    donnees = {'num_plaque': 'P', 'num_moteur': 'M1', 'num_chassie': 'C1', 'marque': 'X', 'couleur': 'ROUGE'}
    a = enregistrer_engin(jeu['membre'], jeu['compte'], donnees)
    b = enregistrer_engin(jeu['membre'], jeu['compte'], {**donnees, 'num_chassie': 'C2', 'num_moteur': 'M2'})
    Moto.objects.filter(pk=a.pk).update(is_delete=True)  # un engin supprimé ne libère jamais son numéro
    c = enregistrer_engin(jeu['membre'], jeu['compte'], {**donnees, 'num_chassie': 'C3', 'num_moteur': 'M3'})
    assert [a.numero, b.numero, c.numero] == ['002PF', '003PF', '004PF']
    assert Moto.objects.filter(province=jeu['province']).count() == len({m.numero for m in Moto.objects.filter(province=jeu['province'])})


def test_F31_numero_au_dela_de_cent_et_numeros_de_forme_inattendue(jeu):
    Moto.objects.create(proprietaire=jeu['membre'], province=jeu['province'], abonnement=date(2030, 1, 1), numero='099PF')
    Moto.objects.create(proprietaire=jeu['membre'], province=jeu['province'], abonnement=date(2030, 1, 1), numero='ancien-format-PF')
    assert numero_suivant(jeu['province']) == '100PF'


def test_F31_ajout_web_utilise_le_meme_service(client, jeu):
    client.force_login(jeu['compte'])
    r = client.post(reverse('add-moto', kwargs={'id': jeu['membre'].id}),
                    {k: 'x' for k in ('plaque', 'chassie', 'moteur', 'marque', 'couleur')})
    assert r.status_code == 200
    assert Moto.objects.filter(proprietaire=jeu['membre']).exclude(pk=jeu['moto'].pk).get().numero == '002PF'
    sans = Membre.objects.create(nom='Sans coordination', is_validate2=True, user=jeu['compte'])
    r = client.post(reverse('add-moto', kwargs={'id': sans.id}), {k: 'y' for k in ('plaque', 'chassie', 'moteur', 'marque', 'couleur')})
    assert r.status_code == 400 and 'coordination provinciale' in r.content.decode()


def test_F31_doublon_d_engin_global_chassis_et_moteur_tous_proprietaires(jeu):
    from coptapp.services.engins import EnginDejaEnregistre
    donnees = {'num_plaque': 'P', 'num_moteur': 'MOT-1', 'num_chassie': 'CHA-1', 'marque': 'X', 'couleur': 'ROUGE'}
    enregistrer_engin(jeu['membre'], jeu['compte'], donnees)
    autre = Membre.objects.create(nom='Autre propriétaire', province=jeu['province'])
    with pytest.raises(EnginDejaEnregistre):
        enregistrer_engin(autre, jeu['compte'], donnees)  # même engin, autre propriétaire : refusé
    enregistrer_engin(autre, jeu['compte'], {**donnees, 'num_moteur': 'MOT-2'})  # moteur différent : accepté
    enregistrer_engin(autre, jeu['compte'], {**donnees, 'num_moteur': '', 'num_chassie': ''})
    enregistrer_engin(autre, jeu['compte'], {**donnees, 'num_moteur': '', 'num_chassie': ''})  # champs vides : pas un doublon


def test_F31_message_clair_de_doublon_sur_mobile_et_sur_le_web(client, jeu):
    from django.contrib.auth.hashers import make_password

    from compte.services.mobile import empreinte_session
    donnees = {'num_plaque': 'P', 'num_moteur': 'MOT-9', 'num_chassie': 'CHA-9', 'marque': 'X', 'couleur': 'ROUGE'}
    enregistrer_engin(jeu['membre'], jeu['compte'], donnees)
    m = Membre.objects.create(nom='Mob', idf='MBR0000055', password=make_password('x'), province=jeu['province'])
    s = client.session
    s['mob_membre_id'] = m.id
    s['mob_empreinte'] = empreinte_session(m)
    s.save()
    r = client.post(reverse('session', kwargs={'id': m.id}), donnees)
    assert 'déjà enregistré' in r.content.decode() and 'châssis' in r.content.decode()
    client.force_login(jeu['compte'])
    r = client.post(reverse('add-moto', kwargs={'id': jeu['membre'].id}),
                    {'plaque': 'P', 'moteur': 'MOT-9', 'chassie': 'CHA-9', 'marque': 'X', 'couleur': 'ROUGE'})
    assert r.status_code == 400 and 'déjà enregistré' in r.content.decode()


def test_F31_deux_coordinations_au_meme_sigle_ne_produisent_jamais_le_meme_numero(jeu):
    autre = Province.objects.create(nom='Doublon de sigle', sigle=jeu['province'].sigle)
    membre_autre = Membre.objects.create(nom='Autre', province=autre)
    donnees = {'num_plaque': 'P', 'num_moteur': 'M1', 'num_chassie': 'C1', 'marque': 'X', 'couleur': 'ROUGE'}
    a = enregistrer_engin(jeu['membre'], jeu['compte'], donnees)
    b = enregistrer_engin(membre_autre, jeu['compte'], {**donnees, 'num_moteur': 'M2', 'num_chassie': 'C2'})
    c = enregistrer_engin(jeu['membre'], jeu['compte'], {**donnees, 'num_moteur': 'M3', 'num_chassie': 'C3'})
    assert len({a.numero, b.numero, c.numero}) == 3
