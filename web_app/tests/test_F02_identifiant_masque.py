"""F-02 (audit sécurité) : l'identifiant « prenom1234@fenamordc.hub » EST le mot de passe initial ; il ne s'affiche jamais (fiche, antenne,
modales, historique) tant que le compte n'a pas changé son mot de passe."""
import pytest
from django.urls import reverse

from compte import roles
from compte.models import Compte
from compte.services.journal import identifiant_affichable
from coptapp.models import Membre
from tests.test_F02_droits_roles import _compte, _nommer, acteurs_roles, monde  # noqa: F401
from tests.test_plan_url import hachage_rapide, jeu  # noqa: F401

INITIAL = 'jeanne4321@fenamordc.hub'
MASQUE = 'jeanne****@fenamordc.hub'


@pytest.fixture
def titulaire(monde):
    """Un compte au mot de passe initial (identifiant = mot de passe), rattaché au membre M et auteur des saisies du membre N de l'antenne."""
    m = Membre.objects.create(nom='Jeanne Test', antenne=monde['antenne_p'], province=monde['P'], ville=monde['ville'], etat='actif', is_user=True)
    compte = Compte.objects.create_user(INITIAL, password=INITIAL, membreId=m.pk, doit_changer_mot_de_passe=True)
    Membre.objects.filter(pk=m.pk).update(user=compte)
    return compte


def _pages(client, monde, compte_connecte, titulaire):
    client.force_login(compte_connecte)
    pages = [reverse('membre-view', kwargs={'id': titulaire.membreId}), reverse('ville-view', kwargs={'id': monde['ville'].pk})]
    return [client.get(adresse) for adresse in pages]


@pytest.mark.parametrize('role', ['SU', 'PR', 'VN', 'VP', 'VA', 'AT', 'VI', 'ED'])
def test_F02_l_identifiant_initial_n_est_jamais_affiche_par_role(client, monde, acteurs_roles, titulaire, role):
    connecte = monde['compte'] if role == 'SU' else acteurs_roles[role]
    reponses = _pages(client, monde, connecte, titulaire)
    for reponse in reponses:
        assert INITIAL not in reponse.content.decode(), (role, reponse.status_code)
    if role in ('SU', 'PR'):  # ces rôles voient la fiche : l'identifiant y figure masqué
        assert reponses[0].status_code == 200 and MASQUE in reponses[0].content.decode()


def test_F02_l_identifiant_reapparait_une_fois_le_mot_de_passe_change(client, monde, titulaire):
    Compte.objects.filter(pk=titulaire.pk).update(doit_changer_mot_de_passe=False)
    fiche, ville = _pages(client, monde, monde['compte'], titulaire)
    assert INITIAL in fiche.content.decode() and MASQUE not in fiche.content.decode()
    assert INITIAL in ville.content.decode()


def test_F02_la_vue_de_l_antenne_masque_l_identifiant_du_titulaire(client, monde, titulaire):
    _fiche, ville = _pages(client, monde, monde['compte'], titulaire)
    html = ville.content.decode()
    assert ville.status_code == 200 and INITIAL not in html and MASQUE in html


def test_F02_identifiant_affichable_regles(monde, titulaire):
    assert identifiant_affichable(titulaire) == MASQUE
    assert identifiant_affichable(None) == '' and identifiant_affichable('Nom complet') == 'Nom complet'
    libre = _compte('pseudo-libre', doit_changer_mot_de_passe=True)  # pas le format initial : rien à masquer
    assert identifiant_affichable(libre) == 'pseudo-libre'
    Compte.objects.filter(pk=titulaire.pk).update(doit_changer_mot_de_passe=False)
    assert identifiant_affichable(Compte.objects.get(pk=titulaire.pk)) == INITIAL
