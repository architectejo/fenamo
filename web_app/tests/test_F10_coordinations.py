"""F-10 : coordinations provinciales : code officiel unique, ordre d'affichage, code figé dès qu'un engin est numéroté."""
from datetime import date

import pytest
from django.contrib.admin.sites import site
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import RequestFactory

from coptapp.models import Moto, Province
from tests.test_plan_url import hachage_rapide, jeu  # noqa: F401


def test_F10_code_unique_en_base(db):
    Province.objects.create(nom='Kinshasa-Est', code='KNE')
    with pytest.raises(IntegrityError), transaction.atomic():
        Province.objects.create(nom='Autre', code='KNE')


def test_F10_code_unique_aussi_a_la_validation(db):
    Province.objects.create(nom='Kinshasa-Est', code='KNE')
    with pytest.raises(ValidationError) as erreur:
        Province(nom='Autre', code='KNE').full_clean()
    assert 'code' in erreur.value.message_dict


def test_F10_plusieurs_coordinations_sans_code_permises(db):
    Province.objects.create(nom='A')
    Province.objects.create(nom='B', code=None)
    Province.objects.create(nom='C', code='')  # une chaîne vide devient NULL : jamais en conflit
    assert Province.objects.filter(code__isnull=True).count() == 3


def test_F10_code_normalise_en_majuscules_sans_espaces(db):
    p = Province.objects.create(nom='Fictive', code=' zz ')
    p.refresh_from_db()
    assert p.code == 'ZZ'
    with pytest.raises(IntegrityError), transaction.atomic():
        Province.objects.create(nom='Doublon', code='zz')


def test_F10_ordre_d_affichage_puis_nom(db):
    Province.objects.create(nom='Zeta', ordre=1)
    Province.objects.create(nom='Alpha', ordre=2)
    Province.objects.create(nom='Beta', ordre=2)
    # les 27 coordinations préchargées (0057) ont leur propre ordre : on ne compare que les trois créées ici
    assert [p.nom for p in Province.objects.filter(nom__in=['Zeta', 'Alpha', 'Beta'])] == ['Zeta', 'Alpha', 'Beta']


def test_F10_code_fige_apres_un_engin_de_la_coordination(jeu):
    p = Province.objects.create(nom='Neuve', code='PF1')
    assert not p.code_fige()
    p.code = 'PF2'
    p.full_clean()  # aucun engin : le code peut encore changer
    p.save()
    Moto.objects.create(proprietaire=jeu['membre'], province=p, abonnement=date(2030, 1, 1), numero='001PF2')
    assert p.code_fige()
    p.code = 'AUTRE'
    with pytest.raises(ValidationError) as erreur:
        p.full_clean()
    assert 'ne peut plus changer' in str(erreur.value)
    p.refresh_from_db()
    p.nom = 'Nouveau nom'  # tout le reste reste modifiable
    p.full_clean()
    p.save()
    assert Province.objects.get(pk=p.pk).code == 'PF2'


def test_F10_admin_affiche_code_et_ordre_et_fige_le_code(jeu):
    admin = site._registry[Province]
    assert {'code', 'ordre', 'nom'} <= set(admin.list_display)
    requete = RequestFactory().get('/')
    libre = Province.objects.create(nom='Libre', code='LB')
    assert admin.get_readonly_fields(requete, libre) == ()
    assert admin.get_readonly_fields(requete, None) == ()
    Moto.objects.create(proprietaire=jeu['membre'], province=libre, abonnement=date(2030, 1, 1), numero='001LB')
    assert admin.get_readonly_fields(requete, libre) == ('code',)
