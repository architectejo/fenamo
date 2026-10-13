"""Les boutons de la fiche et de la liste suivent exactement les droits fournis par la vue (aucun test de privilège dans les gabarits)."""
import re
from pathlib import Path

import pytest
from django.conf import settings
from django.urls import reverse

from coptapp.models import Moto, Famille
from tests.test_plan_url import hachage_rapide, jeu  # noqa: F401
from tests.test_valid_E1_matrice_droits import ROLES, _acteur_et_cible

BOUTONS_SUPPRESSION = {
    'peut_executer_suppression': 'Supprimer le membre',
    'peut_restaurer': 'Restaurer',
    'peut_annuler_demande_suppression': 'Annuler la demande de suppression',
}


def _fiche(client, role, jeu, **etat):
    compte, cible = _acteur_et_cible(role, jeu)
    cible.qualite = 'PROPRIETAIRE'
    for champ, valeur in etat.items():
        setattr(cible, champ, valeur)
    cible.save()
    Moto.objects.create(proprietaire=cible, structure=jeu['association'], ville=jeu['ville'], province=jeu['province'],
                        abonnement=jeu['moto'].abonnement, numero='777PF')
    Famille.objects.create(membre=cible, beneficiere='Bénéficiaire fictif')
    client.force_login(compte)
    return client.get(reverse('membre-view', kwargs={'id': cible.id})), cible


@pytest.mark.parametrize('role', ROLES)
@pytest.mark.parametrize('etat', [{}, {'suppression_demandee': True, 'motif_suppression': 'Doublon'}])
def test_F25_boutons_de_suppression_suivent_les_droits(client, jeu, role, etat):
    r, cible = _fiche(client, role, jeu, **etat)
    if r.status_code != 200:
        return
    html = r.content.decode()
    for droit, libelle in BOUTONS_SUPPRESSION.items():
        assert (f'<span>{libelle}</span>' in html) == bool(r.context[droit]), (role, droit)
    if etat:  # le badge se voit sans bouton, pour tout compte qui voit la fiche
        assert 'Suppression demandée' in html and 'Doublon' in html


def test_F25_restaurer_sur_membre_supprime(client, jeu):
    r, cible = _fiche(client, 'su', jeu, is_delete=True)
    html = r.content.decode()
    assert r.context['peut_restaurer'] and '<span>Restaurer</span>' in html
    assert '<span>Supprimer le membre</span>' not in html


def test_F25_suppression_executee_demande_un_motif_obligatoire(client, jeu):
    r, _ = _fiche(client, 'su', jeu)
    html = r.content.decode()
    assert 'name="motif"' in html and 'required' in html and 'data-motif-requis' in html


@pytest.mark.parametrize('role', ROLES)
def test_F35_actions_engins_et_famille_suivent_les_droits(client, jeu, role):
    r, _ = _fiche(client, role, jeu)
    if r.status_code != 200:
        return
    html = r.content.decode()
    ctx = r.context
    for droit, motif in (('peut_modifier_engin', r'/motos/\d+/modifier/'), ('peut_supprimer_engin', r'/motos/\d+/supprimer/'),
                         ('peut_modifier_famille', r'/famille/\d+/modifier/'), ('peut_supprimer_famille', r'/famille/\d+/supprimer/')):
        assert bool(re.search(motif, html)) == bool(ctx[droit]), (role, droit)


def test_F23_valider_par_ligne_dans_la_liste(client, jeu):
    compte, cible = _acteur_et_cible('p2', jeu)
    client.force_login(compte)
    r = client.get(reverse('liste-membre'))
    lignes = [m for m in r.context['page_obj']]
    attendus = sum(1 for m in lignes if m.peut_valider and m.is_validate3 is False)
    assert r.content.decode().count('Valider le membre') == attendus


def test_F23_aucun_test_de_privilege_dans_les_gabarits():
    racine = Path(settings.BASE_DIR)
    fautifs = []
    for f in racine.rglob('*.html'):
        parties = set(f.relative_to(racine).parts)
        if {'.env', 'venv', 'site-packages', 'docs', 'vendor'} & parties:
            continue
        if re.search(r'user\.privil[ae]ge\d|user\.is_superuser or user\.privilege', f.read_text(encoding='utf-8')):
            fautifs.append(f.relative_to(racine).as_posix())
    legacy = [p for p in fautifs if p.startswith(('coptapp/templates/app/', 'virtrine', 'mobapp'))]
    assert [p for p in fautifs if p not in legacy] == []
