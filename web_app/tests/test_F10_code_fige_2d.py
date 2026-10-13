"""F-10 (2d) : le code d'une coordination est figé seulement par un engin numéroté AVEC ce code ; règle valable aussi dans save()."""
from datetime import date

import pytest
from django.core.exceptions import ValidationError

from coptapp.models import Moto, Province
from tests.test_plan_url import hachage_rapide, jeu  # noqa: F401


def _engin(jeu, province, numero):
    return Moto.objects.create(proprietaire=jeu['membre'], province=province, abonnement=date(2030, 1, 1), numero=numero)


def test_F10_code_fige_seulement_par_un_engin_numerote_avec_ce_code(jeu):
    p = Province.objects.create(nom='Ancienne', sigle='AN')  # pas de code
    _engin(jeu, p, '001AN')  # ancien numéro (sigle)
    assert not p.code_fige()
    p.code = 'ANC'  # None -> code : permis malgré d'anciens engins
    p.full_clean()
    p.save()
    assert Province.objects.get(pk=p.pk).code == 'ANC' and not p.code_fige()  # les anciens numéros ne portent pas ce code
    _engin(jeu, p, '001ANC')
    assert p.code_fige()
    p.code = None  # même retirer le code est refusé
    with pytest.raises(ValidationError):
        p.full_clean()


def test_F10_la_regle_du_code_fige_vaut_aussi_hors_formulaire(jeu):
    p = Province.objects.create(nom='Neuve', code='NV')
    _engin(jeu, p, '007NV')
    p.code = 'XX'
    with pytest.raises(ValidationError):
        p.save()  # sans passer par clean() : refusé aussi
    assert Province.objects.get(pk=p.pk).code == 'NV'
    p.code = ' nv '  # même code autrement écrit : normalisé en NV (dans save), donc inchangé : permis
    p.save()
    assert Province.objects.get(pk=p.pk).code == 'NV'


def test_F10_un_numero_qui_se_termine_comme_le_code_sans_chiffres_ne_fige_pas(jeu):
    p = Province.objects.create(nom='Neuve', code='NV')
    _engin(jeu, p, 'ancien-NV')
    assert not p.code_fige()
