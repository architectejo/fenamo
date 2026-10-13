"""F-11 (2d) : inscription mobile sur une coordination neuve, périmètre des écrans d'association, formulaire d'antenne."""
import pytest
from django.contrib.auth.hashers import make_password
from django.urls import reverse

from compte.models import Compte
from compte.services.mobile import empreinte_session
from coptapp.models import Antenne, AssociationMembre, Membre, Province, Ville
from tests.test_plan_url import hachage_rapide, jeu  # noqa: F401


def _session_mobile(client, membre):
    s = client.session
    s['mob_membre_id'] = membre.id
    s['mob_empreinte'] = empreinte_session(membre)
    s.save()


def test_F11_inscription_mobile_sur_une_coordination_neuve_peut_terminer_l_etape_donnees(client, jeu):
    neuve = Province.objects.create(nom='Tshopo', code='TSH', ordre=3)
    antenne = Antenne.objects.create(nom='Kisangani', coordination=neuve)  # aucune ville héritée
    association = AssociationMembre.objects.create(nom='Assoc Tshopo', sigle='AT', num_justice='F-TSH', antenne=antenne)
    donnees = {'province': neuve.id, 'nom': 'Nouveau', 'genre': 'HOMME', 'qualite': 'PROPRIETAIRE',
               'date_naissance': '1990-01-01', 'lieux_naissance': 'Kisangani',
               'password1': 'Mot-de-passe-9x', 'password2': 'Mot-de-passe-9x'}
    assert client.post(reverse('register'), donnees).status_code == 302
    membre = Membre.objects.get(nom='Nouveau')
    page = client.get(reverse('data', kwargs={'id': membre.id})).content.decode()
    assert 'Kisangani' in page and 'Assoc Tshopo' in page
    r = client.post(reverse('data', kwargs={'id': membre.id}), {'antenne': antenne.id})
    membre.refresh_from_db()
    assert r.status_code == 302 and membre.antenne_id == antenne.id
    assert client.get(reverse('data', kwargs={'id': membre.id})).status_code == 302  # l'étape est terminée
    # ... ou par l'association rattachée à une antenne
    deuxieme = Membre.objects.create(nom='Deux', idf='MBR0000099', password=make_password('x'), province=neuve)
    _session_mobile(client, deuxieme)
    client.post(reverse('data', kwargs={'id': deuxieme.id}), {'structure': association.id})
    deuxieme.refresh_from_db()
    assert deuxieme.structure_id == association.id and deuxieme.antenne_id == antenne.id


def test_F11_formulaire_mobile_ne_liste_que_les_coordinations_reelles(db):
    from mobapp.forms import MembreFormRegister
    fantome = Province.objects.create(nom='Fantôme sans rien')
    avec_code = Province.objects.create(nom='Avec code', code='AC')
    avec_ville = Province.objects.create(nom='Avec ville')
    Ville.objects.create(nom='V', province=avec_ville)
    avec_antenne = Province.objects.create(nom='Avec antenne')
    Antenne.objects.create(nom='A', coordination=avec_antenne)
    avec_membre = Province.objects.create(nom='Avec membre')
    Membre.objects.create(nom='M', province=avec_membre)
    champ = MembreFormRegister().fields['province']
    proposees = set(champ.queryset)  # (les 27 coordinations préchargées, qui ont un code, y sont aussi)
    assert {avec_code, avec_ville, avec_antenne, avec_membre} <= proposees and fantome not in proposees
    assert all(p.code or p in (avec_ville, avec_antenne, avec_membre) for p in proposees)
    assert str(champ.label) == 'Coordination provinciale'
    assert len(champ.queryset) == len(set(champ.queryset))  # aucune ligne en double


def test_F11_mobile_membre_sans_coordination_ne_se_voit_rien_proposer(client, jeu):
    sans = Membre.objects.create(nom='Sans', idf='MBR0000098', password=make_password('x'))
    _session_mobile(client, sans)
    page = client.get(reverse('data', kwargs={'id': sans.id}))
    assert page.status_code == 200 and jeu['association'].nom not in page.content.decode()


def test_F11_ville_select_ne_reutilise_pas_une_ville_homonyme_d_une_autre_coordination(client, jeu):
    autre = Province.objects.create(nom='Autre', sigle='AU')
    homonyme = Ville.objects.create(nom='LEMBA', province=autre)
    sans_ville = AssociationMembre.objects.create(nom='Sans ville', province=jeu['province'], num_justice='F-HOM')
    client.force_login(jeu['compte'])
    assert client.post(reverse('ville-select', kwargs={'id': sans_ville.id}), {'ville': 'lemba'}).status_code == 302
    sans_ville.refresh_from_db()
    assert sans_ville.ville_id != homonyme.id and sans_ville.ville.province_id == jeu['province'].id
    assert sans_ville.antenne.ville_origine_id == sans_ville.ville_id
    assert Ville.objects.filter(nom='LEMBA').count() == 2  # l'homonyme d'ailleurs est intact


def test_F11_ville_attr_exige_une_ville_de_la_coordination_de_l_association(client, jeu):
    autre = Province.objects.create(nom='Autre', sigle='AU')
    etrangere = Ville.objects.create(nom='Etrangère', province=autre)
    client.force_login(jeu['compte'])
    assert client.post(reverse('ville-attr', kwargs={'id': etrangere.id, 'sid': jeu['association'].id})).status_code == 404
    jeu['association'].refresh_from_db()
    assert jeu['association'].ville_id == jeu['ville'].id


@pytest.mark.parametrize('privileges', [{'privilege1': True}, {'privilege2': True}, {'privilege3': True}, {'privilege4': True}, {}])
def test_F11_ni_agent_ni_validateur_ne_modifie_la_ville_ou_l_antenne_d_une_association(client, jeu, privileges):
    compte = Compte.objects.create_user('petit', password='x', **privileges)
    jeu['association'].users.add(compte)
    avant = AssociationMembre.objects.values('ville_id', 'antenne_id').get(pk=jeu['association'].pk)
    autre_ville = Ville.objects.create(nom='Autre ville', province=jeu['province'])
    client.force_login(compte)
    assert client.post(reverse('ville-attr', kwargs={'id': autre_ville.id, 'sid': jeu['association'].id})).status_code == 403
    assert client.get(reverse('ville-select', kwargs={'id': jeu['association'].id})).status_code == 403
    assert client.post(reverse('ville-select', kwargs={'id': jeu['association'].id}), {'ville': 'X'}).status_code == 403
    assert client.post(reverse('edit-structure', kwargs={'id': jeu['association'].id}),
                       {'antenne': jeu['antenne'].id}).status_code == 403
    assert AssociationMembre.objects.values('ville_id', 'antenne_id').get(pk=jeu['association'].pk) == avant


def test_F11_formulaire_d_association_ne_porte_pas_l_antenne():
    from coptapp.forms import AssociationMembreForm
    assert 'antenne' not in AssociationMembreForm.base_fields


def test_F11_formulaire_d_antenne_porte_type_et_coordination(client, jeu):
    client.force_login(jeu['compte'])
    autre = Province.objects.create(nom='Autre coordination', code='AC')
    client.post(reverse('add-antenne', kwargs={'id': jeu['association'].id}),
                {'nom': 'Territoire X', 'zone': 'Z', 'code': 'TX', 'type': 'territoire', 'coordination': autre.id})
    a = Antenne.objects.get(code='TX')
    assert a.type == 'territoire' and a.coordination_id == autre.id  # la coordination choisie n'est pas écrasée
    client.post(reverse('add-antenne', kwargs={'id': jeu['association'].id}), {'nom': 'Commune Y', 'zone': 'Z', 'code': 'CY'})
    assert Antenne.objects.get(code='CY').coordination_id == jeu['province'].id  # sinon celle de l'association
    client.post(reverse('add-antenne', kwargs={'id': jeu['association'].id}), {'nom': 'Z', 'code': 'ZZ', 'type': 'inconnu'})
    assert not Antenne.objects.filter(code='ZZ').exists()  # type hors liste : refusé


def test_F11_migration_0056_sans_doublon_ne_signale_rien(db, capsys):
    import importlib

    from django.apps import apps as vraies_apps
    m = importlib.import_module('coptapp.migrations.0056_geographie_champs')
    Antenne.objects.create(nom='A', code='X')
    m.normaliser_codes_d_antenne(vraies_apps, None)  # aucun doublon possible en base (unicité) : rien à signaler
    assert 'AVERTISSEMENT' not in capsys.readouterr().out
