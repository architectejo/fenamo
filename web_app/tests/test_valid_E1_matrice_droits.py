"""Validation indépendante : matrice rôle x action sur un membre (E1, F-23, F-25, F-28).

Référence : docstring de coptapp/services/droits_provisoires.py et rapport backend-django (règles restrictives) :
404 hors périmètre, 403 si l'action est interdite. Seuls les SU attribuent des privilèges.
"""
from datetime import date

import pytest
from django.urls import reverse

from compte.models import Compte
from coptapp.models import AssociationMembre, Membre
from tests.test_plan_url import hachage_rapide, jeu  # noqa: F401

CHAMPS = ('nom about genre titre fonction comite nation brevet etat_civil epouse adresse telephone mail categorie '
          'permis qualite autre_asbl numero_carte_d_electeur numero_carte_de_membre nom_pere nom_mere village '
          'chefferie territoire province_origine').split()


def _corps_modifier(nom='Nom changé'):
    d = {c: 'x' for c in CHAMPS}
    d.update({'nom': nom, 'date': '02-03-1991', 'modifier': '1', 'mail': 'a@example.invalid'})
    return d


def _membre(jeu, nom, **kw):
    base = dict(province=jeu['province'], antenne=jeu['antenne'], structure=jeu['association'],
                date_naissance=date(1990, 1, 1))
    base.update(kw)
    return Membre.objects.create(nom=nom, **base)


ROLES = ['su', 'p5', 'p3', 'p2', 'p1', 'p4', 'aucun']

# role -> (voit la liste ?, fiche, modifier, valider, supprimer, privilèges) sur la cible « visible » du rôle.
# 200/302 = autorisé ; 403 = interdit ; 404 = hors périmètre.
ATTENDU = {
    'su':    dict(fiche=200, modifier=200, valider=302, supprimer=302, privileges=200),
    'p5':    dict(fiche=200, modifier=200, valider=302, supprimer=302, privileges=403),
    'p3':    dict(fiche=200, modifier=200, valider=302, supprimer=302, privileges=403),
    'p2':    dict(fiche=200, modifier=403, valider=302, supprimer=302, privileges=403),
    'p1':    dict(fiche=200, modifier=403, valider=403, supprimer=302, privileges=403),
    'p4':    dict(fiche=200, modifier=403, valider=403, supprimer=403, privileges=403),
    'aucun': dict(fiche=200, modifier=403, valider=403, supprimer=403, privileges=403),
}


def _acteur_et_cible(role, jeu):
    """Crée le compte du rôle et une cible située dans son périmètre ; retourne (compte, cible)."""
    if role == 'su':
        return jeu['compte'], _membre(jeu, 'Cible', is_validate2=True)
    nom = f'u-{role}'
    if role == 'p5':
        compte = Compte.objects.create_user(nom, password='x', privilege5=True)
        return compte, _membre(jeu, 'Cible', is_validate2=True)
    if role == 'p3':
        compte = Compte.objects.create_user(nom, password='x', privilege3=True)
        jeu['association'].users.add(compte)
        return compte, _membre(jeu, 'Cible', is_validate2=True)
    if role == 'p2':
        compte = Compte.objects.create_user(nom, password='x', privilege2=True)
        return compte, _membre(jeu, 'Cible')  # is_validate1 par défaut, validate2 à poser
    if role == 'p1':
        compte = Compte.objects.create_user(nom, password='x', privilege1=True)
        return compte, _membre(jeu, 'Cible', user=compte)
    if role == 'p4':
        compte = Compte.objects.create_user(nom, password='x', privilege4=True)
        return compte, _membre(jeu, 'Cible', is_validate2=True, is_validate3=True)
    cible = _membre(jeu, 'Cible')
    compte = Compte.objects.create_user(nom, password='x', membreId=cible.id)
    return compte, cible


def _compte_cible(cible):
    """Donne un compte à la cible pour que l'attribution de privilèges ait un effet observable."""
    c = Compte.objects.create_user(f'cible{cible.id}', password='x', membreId=cible.id)
    cible.is_user = True
    cible.save(update_fields=['is_user'])
    return c


@pytest.mark.parametrize('role', ROLES)
def test_F28_matrice_voir_liste(client, jeu, role):
    compte, cible = _acteur_et_cible(role, jeu)
    client.force_login(compte)
    r = client.get('/membres/')
    assert r.status_code == 200
    assert cible.nom in [m.nom for m in r.context['page_obj']]


@pytest.mark.parametrize('role', ROLES)
def test_F23_matrice_voir_fiche(client, jeu, role):
    compte, cible = _acteur_et_cible(role, jeu)
    client.force_login(compte)
    assert client.get(reverse('membre-view', args=[cible.id])).status_code == ATTENDU[role]['fiche']


@pytest.mark.parametrize('role', ROLES)
def test_F21_matrice_modifier(client, jeu, role):
    compte, cible = _acteur_et_cible(role, jeu)
    client.force_login(compte)
    r = client.post(reverse('membre-view', args=[cible.id]), _corps_modifier())
    assert r.status_code == ATTENDU[role]['modifier']
    cible.refresh_from_db()
    assert (cible.nom == 'Nom changé') == (ATTENDU[role]['modifier'] == 200)


@pytest.mark.parametrize('role', ROLES)
def test_F23_matrice_valider(client, jeu, role):
    compte, cible = _acteur_et_cible(role, jeu)
    client.force_login(compte)
    avant = (cible.is_validate2, cible.is_validate3)
    r = client.post(reverse('validate', args=[cible.id]))
    assert r.status_code == ATTENDU[role]['valider']
    cible.refresh_from_db()
    apres = (cible.is_validate2, cible.is_validate3)
    if ATTENDU[role]['valider'] == 403:
        assert apres == avant
    elif role == 'p2':
        assert apres[0] is True  # pose l'étape intermédiaire seulement
        assert apres[1] is False
    else:
        assert apres[1] is True  # étape finale


@pytest.mark.parametrize('role', ROLES)
def test_F25_matrice_demander_suppression(client, jeu, role):
    compte, cible = _acteur_et_cible(role, jeu)
    client.force_login(compte)
    action = 'executer' if role in ('su', 'p5') else 'demander'
    r = client.post(reverse('delete-membre', args=[cible.id]), {'action': action, 'motif': 'Doublon'})
    assert r.status_code == ATTENDU[role]['supprimer']
    cible.refresh_from_db()
    # F-25 : SU et privilege5 exécutent ; les autres déposent seulement une demande
    assert cible.is_delete == (ATTENDU[role]['supprimer'] == 302 and role in ('su', 'p5'))
    assert cible.suppression_demandee == (ATTENDU[role]['supprimer'] == 302 and role not in ('su', 'p5'))


@pytest.mark.parametrize('role', ROLES)
def test_F02_matrice_attribuer_privileges(client, jeu, role):
    compte, cible = _acteur_et_cible(role, jeu)
    compte_cible = _compte_cible(cible)
    client.force_login(compte)
    r = client.post(reverse('membre-view', args=[cible.id]), {'privilege': '1', 'privilege5': 'on', 'privilege3': 'on'})
    assert r.status_code == ATTENDU[role]['privileges']
    compte_cible.refresh_from_db()
    if ATTENDU[role]['privileges'] != 200:
        assert not compte_cible.privilege5 and not compte_cible.privilege3


@pytest.mark.parametrize('role', ['su', 'p5', 'p3', 'p2', 'p1', 'p4', 'aucun'])
def test_F23_matrice_hors_perimetre_404_partout(client, jeu, role):
    """Un membre hors périmètre est introuvable (404) pour toutes les actions, sauf SU et privilege5 qui voient tout."""
    compte, _ = _acteur_et_cible(role, jeu)
    invisible = _membre(jeu, 'Invisible')  # validate2/3 à False, sans user : ni p3, ni p4, ni p1, ni aucun ne le voient
    client.force_login(compte)
    codes = [
        client.get(reverse('membre-view', args=[invisible.id])).status_code,
        client.post(reverse('membre-view', args=[invisible.id]), _corps_modifier('Pirate')).status_code,
        client.post(reverse('validate', args=[invisible.id])).status_code,
        client.post(reverse('delete-membre', args=[invisible.id]), {'action': 'demander', 'motif': 'x'}).status_code,
    ]
    invisible.refresh_from_db()
    if role in ('su', 'p5'):
        assert 404 not in codes
        return
    if role == 'p2':  # p2 voit tout is_validate1 (défaut True) : le membre est dans son périmètre
        assert codes[0] == 200
        return
    assert codes == [404, 404, 404, 404]
    assert invisible.nom == 'Invisible' and not invisible.is_delete and not invisible.is_validate2


def test_F23_compte_inactif_ne_voit_rien(client, jeu):
    from compte.services.droits import membres_du_perimetre
    compte = Compte.objects.create_user('inactif', password='x', privilege5=True, is_active=False)
    assert membres_du_perimetre(compte).count() == 0


# ---------------------------------------------------------------- GET sans effet, méthodes

# ---------------------------------------------------------------- validation idempotente (F-23)
