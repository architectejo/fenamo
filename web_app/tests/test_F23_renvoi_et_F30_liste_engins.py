"""F-23 : renvoi d'un membre avec motif (service, droits, état, notification, journal, reprise) ; F-30 : liste des engins."""
import pytest
from django.core.exceptions import PermissionDenied
from django.urls import reverse

from compte import roles
from compte.models import JournalAction
from compte.services.droits import droits_membre
from coptapp.models import Moto, Notification
from coptapp.models import Membre
from coptapp.services import transitions
from coptapp.services.engins import enregistrer_engin, lister_engins
from coptapp.services.etats import etat_de, filtrer_membres_par_etat
from coptapp.services.membres import modifier_membre
from tests.test_F02_droits_roles import _compte, _nommer, monde  # noqa: F401
from tests.test_plan_url import hachage_rapide, jeu  # noqa: F401


@pytest.fixture
def equipe(monde):
    return {'PR': _nommer(monde, roles.PR), 'VN': _nommer(monde, roles.VN),
            'VA': _nommer(monde, roles.VA, antenne=monde['antenne_p']),
            'AT': _nommer(monde, roles.AT, antenne=monde['antenne_p'])}


def _saisi(monde, equipe, nom='Saisi Test', **etat):
    return Membre.objects.create(nom=nom, antenne=monde['antenne_p'], province=monde['P'], user=equipe['AT'], **etat)


def test_F23_renvoi_motif_obligatoire_et_etat_renvoye(monde, equipe):
    m = _saisi(monde, equipe)
    assert transitions.renvoyer(equipe['VA'], m, '   ') == 'motif_requis' and etat_de(Membre.objects.get(pk=m.pk)) == 'saisi'
    assert transitions.renvoyer(equipe['VA'], m, 'x' * 501) == 'motif_trop_long'
    assert transitions.renvoyer(equipe['VA'], m, 'Photo illisible') == 'renvoye'
    m.refresh_from_db()
    assert m.renvoye and m.motif_renvoi == 'Photo illisible' and etat_de(m) == 'renvoye'
    assert filtrer_membres_par_etat(Membre.objects.all(), 'renvoye').filter(pk=m.pk).exists()
    assert not filtrer_membres_par_etat(Membre.objects.all(), 'saisi').filter(pk=m.pk).exists()


def test_F23_renvoi_journal_notification_et_retrait_de_l_etape(monde, equipe):
    m = _saisi(monde, equipe, etat='valide_province')
    assert transitions.renvoyer(equipe['VN'], m, 'Pièce manquante') == 'renvoye'
    m.refresh_from_db()
    assert m.etat == 'valide_antenne' and not m.renvoye and m.motif_renvoi == 'Pièce manquante'  # recul d'un cran, motif affiché
    ligne = JournalAction.objects.get(action=JournalAction.Action.RENVOI)
    assert ligne.auteur == equipe['VN'] and ligne.motif == 'Pièce manquante' and ligne.apres == {'etat': 'valide_antenne'} and ligne.avant == {'etat': 'valide_province'}
    notif = Notification.objects.get(user=equipe['AT'], membre=m)
    assert 'Pièce manquante' in notif.description


def test_F23_renvoi_droits_et_cles(monde, equipe):
    m = _saisi(monde, equipe)
    assert droits_membre(equipe['VA'], m)['peut_renvoyer'] and droits_membre(equipe['VA'])['peut_renvoyer']
    for role in ('AT', 'VN'):  # l'agent ne valide pas ; le VN n'a rien à faire sur une fiche non validée par l'antenne
        assert not droits_membre(equipe[role], m)['peut_renvoyer']
        with pytest.raises(PermissionDenied):
            transitions.renvoyer(equipe[role], m, 'Motif')
    transitions.renvoyer(equipe['VA'], m, 'Motif')
    m.refresh_from_db()
    assert not droits_membre(equipe['VA'], m)['peut_renvoyer'] and not droits_membre(equipe['VA'], m)['peut_valider']
    assert transitions.valider(equipe['VA'], m) == []  # un renvoyé n'est pas validable avant sa reprise


def test_F23_la_modification_par_l_auteur_remet_dans_le_circuit(monde, equipe):
    m = _saisi(monde, equipe)
    transitions.renvoyer(equipe['VA'], m, 'Fonction à corriger')
    m.refresh_from_db()
    formulaire, modifie = modifier_membre(equipe['AT'], m, {'nom': 'Saisi Corrige', 'date_naissance': '1990-01-01', 'qualite': 'MOTARD', 'fonction': 'Chauffeur'})
    m.refresh_from_db()
    assert modifie, formulaire.errors
    assert not m.renvoye and m.motif_renvoi == '' and etat_de(m) == 'saisi'
    assert transitions.valider(equipe['VA'], m) == ['valide_antenne']


def test_F23_vue_post_csrf_et_refus(client, monde, equipe):
    m = _saisi(monde, equipe)
    url = reverse('renvoyer-membre', args=[m.id])
    client.force_login(equipe['VA'])
    assert client.get(url).status_code == 405
    assert client.post(url, {'motif': ''}).status_code == 302 and not Membre.objects.get(pk=m.pk).renvoye
    assert client.post(url, {'motif': 'Photo floue'}).status_code == 302 and Membre.objects.get(pk=m.pk).renvoye
    client.force_login(equipe['AT'])
    assert client.post(reverse('renvoyer-membre', args=[_saisi(monde, equipe, 'Autre').id]), {'motif': 'x'}).status_code == 403


# ---------------------------------------------------------------- F-30 : liste des engins

def _engin(membre, auteur, n):
    return enregistrer_engin(membre, auteur, {'num_plaque': f'P{n}', 'num_moteur': f'MOT-{n}', 'num_chassie': f'CHA-{n}', 'marque': 'TVS', 'couleur': 'Rouge'})


def test_F30_liste_engins_perimetre_recherche_pagination(monde, equipe):
    proprio = _saisi(monde, equipe, 'Proprio Alpha', etat='actif')
    for n in range(30):
        _engin(proprio, equipe['AT'], n)
    res = lister_engins(equipe['PR'], {}, 1, par_page=25)
    assert res.page_obj.paginator.count >= 30 and len(res.page_obj) == 25 and not res.filtres_actifs
    assert lister_engins(equipe['PR'], {'q': 'CHA-7'}).page_obj.paginator.count == 1
    assert lister_engins(equipe['PR'], {'q': 'alpha'}).page_obj.paginator.count == 30
    assert lister_engins(equipe['PR'], {'antenne': monde['antenne_p'].id}).filtres_actifs
    assert lister_engins(equipe['PR'], {'coordination': 99999999999999999999}).filtres['coordination'] == ''  # entier géant ignoré
    assert lister_engins(equipe['PR'], {'page': 'x'}, 'x').page_obj.number == 1
    hors = _compte('sans-engin-visible')
    assert lister_engins(hors, {}).page_obj.paginator.count == 0  # hors périmètre : rien


def test_F30_vue_liste_engins_get_page_et_fragment(client, monde, equipe):
    proprio = _saisi(monde, equipe, 'Proprio Beta', etat='actif')
    _engin(proprio, equipe['AT'], 1)
    url = reverse('engin-liste')
    assert client.get(url).status_code == 302  # anonyme : connexion
    client.force_login(equipe['VA'])
    page = client.get(url, {'q': 'CHA-1'})
    assert page.status_code == 200 and '<html' in page.content.decode()
    fragment = client.get(url, {'q': 'CHA-1'}, HTTP_HX_REQUEST='true')
    assert fragment.status_code == 200 and '<html' not in fragment.content.decode() and 'Proprio Beta' in fragment.content.decode()
