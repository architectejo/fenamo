"""F-31 (2d) : numérotation des engins sur le code officiel de la coordination, repli sur l'ancien sigle, code figé."""
import pytest
from django.core.exceptions import ValidationError

from coptapp.models import Membre, Moto, Province
from coptapp.services.engins import CoordinationInconnue, code_de_numerotation, enregistrer_engin, numero_suivant
from tests.test_plan_url import hachage_rapide, jeu  # noqa: F401

DONNEES = {'num_plaque': 'P', 'num_moteur': 'M1', 'num_chassie': 'C1', 'marque': 'X', 'couleur': 'ROUGE'}


def _d(i):
    return {**DONNEES, 'num_moteur': f'M{i}', 'num_chassie': f'C{i}'}


def test_F31_2d_repli_sur_le_sigle_tant_que_le_code_manque(jeu):
    assert jeu['province'].code is None and code_de_numerotation(jeu['province']) == 'PF'
    e = enregistrer_engin(jeu['membre'], jeu['compte'], _d(1))
    assert e.numero == '002PF'  # l'engin du jeu porte déjà 001PF : la numérotation continue


def test_F31_2d_le_code_officiel_prime_sur_le_sigle(jeu):
    jeu['province'].code = 'KNE'
    jeu['province'].save()
    assert code_de_numerotation(jeu['province']) == 'KNE'
    assert enregistrer_engin(jeu['membre'], jeu['compte'], _d(1)).numero == '001KNE'  # nouveau code : nouveau compteur
    assert enregistrer_engin(jeu['membre'], jeu['compte'], _d(2)).numero == '002KNE'


def test_F31_2d_anciens_numeros_jamais_modifies(jeu):
    avant = {m.pk: m.numero for m in Moto.objects.all()}
    jeu['province'].code = 'KNE'
    jeu['province'].save()
    enregistrer_engin(jeu['membre'], jeu['compte'], _d(1))
    assert all(Moto.objects.get(pk=pk).numero == numero for pk, numero in avant.items())


def test_F31_2d_coordination_inconnue_seulement_sans_code_ni_sigle(jeu):
    sans_rien = Province.objects.create(nom='Sans rien', sigle=None, code=None)
    vide = Province.objects.create(nom='Vide', sigle='  ', code=None)
    for province in (sans_rien, vide):
        with pytest.raises(CoordinationInconnue):
            enregistrer_engin(Membre.objects.create(nom=province.nom, province=province), jeu['compte'], _d(1))
    avec_code_seul = Province.objects.create(nom='Code seul', sigle=None, code='CS')
    assert enregistrer_engin(Membre.objects.create(nom='CS', province=avec_code_seul), jeu['compte'], _d(2)).numero == '001CS'
    with pytest.raises(CoordinationInconnue):
        enregistrer_engin(Membre.objects.create(nom='Sans coordination'), jeu['compte'], _d(3))


def test_F31_2d_un_sigle_herite_identique_a_un_code_ne_produit_pas_de_doublon(jeu):
    autre = Province.objects.create(nom='Autre', sigle='ZZ', code='PF')  # son code coïncide avec le sigle du jeu
    membre_autre = Membre.objects.create(nom='Autre', province=autre)
    a = enregistrer_engin(jeu['membre'], jeu['compte'], _d(1))        # sigle PF
    b = enregistrer_engin(membre_autre, jeu['compte'], _d(2))         # code PF
    c = enregistrer_engin(jeu['membre'], jeu['compte'], _d(3))
    assert len({a.numero, b.numero, c.numero}) == 3 and numero_suivant(autre) == '005PF'


def test_F31_2d_le_verrou_porte_sur_la_ligne_de_la_coordination(jeu, monkeypatch):
    from django.db.models.query import QuerySet
    verrous = []
    vrai = QuerySet.select_for_update

    def espion(self, *a, **k):
        verrous.append(self.model.__name__)
        return vrai(self, *a, **k)

    monkeypatch.setattr(QuerySet, 'select_for_update', espion)
    enregistrer_engin(jeu['membre'], jeu['compte'], _d(1))
    assert 'Province' in verrous


def test_F31_2d_code_fige_des_le_premier_engin_numerote(jeu):
    p = Province.objects.create(nom='Neuve', code='NV')
    membre = Membre.objects.create(nom='M', province=p)
    p.code = 'NW'
    p.full_clean()  # aucun engin encore : modifiable
    p.save()
    enregistrer_engin(membre, jeu['compte'], _d(1))
    p.refresh_from_db()
    p.code = 'NZ'
    with pytest.raises(ValidationError):
        p.full_clean()
    p.refresh_from_db()
    assert p.code == 'NW'
    p.full_clean()
    assert Moto.objects.filter(province=p).get().numero == '001NW'


def test_F31_2d_numerotation_web_et_mobile_utilisent_le_code(client, jeu):
    from django.urls import reverse
    jeu['province'].code = 'WEB'
    jeu['province'].save()
    client.force_login(jeu['compte'])
    client.post(reverse('add-moto', kwargs={'id': jeu['membre'].id}), {k: 'x' for k in ('plaque', 'chassie', 'moteur', 'marque', 'couleur')})
    assert Moto.objects.filter(numero='001WEB').exists()
