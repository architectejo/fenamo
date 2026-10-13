"""F-20 : les formulaires de membre fonctionnent par LISTE BLANCHE (aucun champ d'état, de suppression, de validation
ni de compte ne peut être posé par un POST forgé, surtout sur l'inscription mobile anonyme)."""
from django.urls import reverse

from compte.models import Compte
from coptapp.forms import MembreFenamoForm, MembreForm
from coptapp.models import Membre
from mobapp.forms import MembreFormRegister
from tests.test_plan_url import hachage_rapide, jeu  # noqa: F401

COMMUNS = [
    'nom', 'date_naissance', 'lieux_naissance', 'genre', 'titre', 'fonction', 'comite', 'brevet', 'etat_civil',
    'nom_epouse', 'nation', 'numero_carte_d_electeur', 'numero_carte_de_membre', 'nom_pere', 'nom_mere', 'village',
    'chefferie', 'territoire', 'province_origine', 'photo', 'adresse', 'telephone', 'mail', 'categorie', 'permis',
    'qualite',
]
ATTENDUS = {
    MembreForm: ['fiche_id', 'ville', 'code_parking'] + COMMUNS,
    MembreFenamoForm: ['fiche_id', 'province', 'code_parking'] + COMMUNS,
    MembreFormRegister: ['province'] + COMMUNS,
}
INTERDITS = ('suppression_demandee', 'motif_suppression', 'suppression_demandee_par', 'is_delete', 'is_validate1',
             'is_validate2', 'is_validate3', 'is_user', 'is_membre', 'user', 'structure', 'antenne', 'idf', 'password',
             'a_propos', 'autre_asb')


def test_F20_listes_blanches_exactes():
    for formulaire, attendus in ATTENDUS.items():
        assert list(formulaire.base_fields) == attendus, formulaire.__name__
        assert not set(INTERDITS) & set(formulaire.base_fields), formulaire.__name__
        assert formulaire._meta.fields is not None and formulaire._meta.exclude is None, formulaire.__name__


def test_F20_inscription_mobile_ignore_les_champs_forges(client, jeu):
    auteur = Compte.objects.create_user('victime', password='x')
    donnees = {'nom': 'Forgé', 'genre': 'HOMME', 'qualite': 'PROPRIETAIRE', 'province': jeu['province'].id,
               'date_naissance': '1992-05-06', 'lieux_naissance': 'Kinshasa',
               'password1': 'Mot-de-passe-9x', 'password2': 'Mot-de-passe-9x', 'suppression_demandee': 'on', 'motif_suppression': 'x', 'suppression_demandee_par': auteur.id,
               'is_validate2': 'on', 'is_validate3': 'on', 'is_delete': 'on', 'user': auteur.id, 'password': 'clair'}
    r = client.post(reverse('register'), donnees)
    assert r.status_code == 302
    membre = Membre.objects.get(nom='Forgé')
    assert not membre.suppression_demandee and membre.suppression_demandee_par is None and membre.motif_suppression == ''
    assert not membre.is_validate2 and not membre.is_validate3 and not membre.is_delete
    assert membre.user is None and membre.password != 'clair'


def test_F20_page_d_inscription_mobile_sans_nom_de_compte(client, jeu):
    Compte.objects.create_user('compte-secret-xyz', password='x')
    corps = client.get(reverse('register')).content.decode()
    assert 'compte-secret-xyz' not in corps and 'admin-test' not in corps
    assert 'suppression_demandee' not in corps and 'motif_suppression' not in corps


def test_F20_formulaires_herites_ignorent_les_champs_forges(client, jeu):
    client.force_login(jeu['compte'])
    donnees = {'nom': 'Forgé 2', 'genre': 'HOMME', 'qualite': 'PROPRIETAIRE', 'titre': 'MR', 'fonction': 'Membre simple',
               'comite': 'ANTENNE', 'etat_civil': 'Celibataire', 'categorie': 'H', 'date_naissance': '1992-05-06',
               'ville': jeu['ville'].id, 'suppression_demandee': 'on', 'is_validate3': 'on'}
    client.post(reverse('add-membre', args=[jeu['association'].id]), donnees)
    membre = Membre.objects.filter(nom='Forgé 2').first()
    if membre is not None:
        assert not membre.suppression_demandee and not membre.is_validate3


def test_F12_listes_blanches_association_antenne_engin_mobile():
    from coptapp.forms import AntenneForm, AssociationMembreForm, AssociationMembreIdentifyForm
    from mobapp.forms import MotoFormRegister
    communs = ['type_de_structure', 'num_justice', 'capture_justice', 'nom', 'nom_responsable', 'sigle', 'logo', 'adresse',
               'phone', 'email', 'preuve_de_paiement', 'twitter', 'facebook', 'instagram', 'linkedin']
    attendus = {
        AssociationMembreForm: ['ville'] + communs,
        AssociationMembreIdentifyForm: ['province'] + communs,
        AntenneForm: ['nom', 'zone', 'code'],
        MotoFormRegister: ['photo', 'num_plaque', 'num_moteur', 'num_chassie', 'marque', 'couleur'],
    }
    for formulaire, champs in attendus.items():
        assert list(formulaire.base_fields) == champs, formulaire.__name__
        assert formulaire._meta.exclude is None, formulaire.__name__
        assert not {'users', 'user', 'structure', 'is_delete', 'abonnement', 'numero', 'motard_id', 'proprietaire'} & set(
            formulaire.base_fields), formulaire.__name__
