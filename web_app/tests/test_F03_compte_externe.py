"""F-03 : compte visiteur (par PR ou SU) ou éditeur (par SU) sans fiche membre ; mot de passe temporaire à lecture unique."""
import json

import pytest
from django.contrib.auth.hashers import check_password
from django.test import Client
from django.urls import reverse

from compte import roles
from compte.models import Compte, JournalAction
from compte.services import nominations as N
from compte.services.nominations import DroitInsuffisant, HorsPerimetre, RegleMetier
from tests.test_F02_droits_roles import _compte, _nommer, monde  # noqa: F401
from tests.test_plan_url import hachage_rapide, jeu  # noqa: F401


@pytest.fixture
def pr(monde):
    return _nommer(monde, roles.PR)


def test_F03_pr_cree_un_visiteur_national_sans_fiche_membre(monde, pr):
    compte, nomination, mdp = N.creer_compte_externe(pr, 'ministere-transports', roles.VI, email='m@example.invalid')
    assert compte.membreId is None and compte.doit_changer_mot_de_passe and compte.email == 'm@example.invalid'
    assert nomination.role == 'VI' and nomination.membre is None and nomination.nomme_par == pr and nomination.fin is None
    assert check_password(mdp, compte.password) and len(mdp) == 12
    assert list(compte.groups.values_list('name', flat=True)) == ['role_VI']


def test_F03_le_perimetre_du_visiteur_est_fixe_a_la_creation(monde, pr):
    _c, n1, _m = N.creer_compte_externe(pr, 'vi-coordination', roles.VI, coordination=monde['P'])
    _c, n2, _m = N.creer_compte_externe(pr, 'vi-antenne', roles.VI, antenne=monde['antenne_p'])
    assert (n1.coordination, n1.antenne) == (monde['P'], None) and (n2.antenne, n2.coordination) == (monde['antenne_p'], None)
    with pytest.raises(RegleMetier):
        N.creer_compte_externe(pr, 'vi-double', roles.VI, coordination=monde['P'], antenne=monde['antenne_p'])
    assert not Compte.objects.filter(username='vi-double').exists()  # rien n'est créé en cas de refus


def test_F03_le_su_cree_un_editeur_et_un_visiteur(monde):
    ed_compte, ed, _mdp = N.creer_compte_externe(monde['compte'], 'redacteur', roles.ED)
    vi_compte, vi, _mdp = N.creer_compte_externe(monde['compte'], 'visiteur-su', roles.VI)
    assert ed.role == 'ED' and vi.role == 'VI' and not ed_compte.is_superuser


@pytest.mark.parametrize('auteur_role, role', [('PR', roles.ED), ('VN', roles.VI), ('VN', roles.ED), ('VP', roles.VI), ('VA', roles.VI)])
def test_F03_visiteur_par_pr_ou_su_editeur_par_su_seulement(monde, auteur_role, role):
    kw = {'PR': {}, 'VN': {}, 'VP': {'coordination': monde['P']}, 'VA': {'antenne': monde['antenne_p']}}[auteur_role]
    auteur = _nommer(monde, getattr(roles, auteur_role), **kw)
    with pytest.raises(DroitInsuffisant):
        N.creer_compte_externe(auteur, 'refuse', role)
    assert not Compte.objects.filter(username='refuse').exists()


@pytest.mark.parametrize('role', [roles.PR, roles.VN, roles.VP, roles.VA, roles.AT, roles.SU])
def test_F03_seuls_visiteur_et_editeur_se_creent_sans_fiche(monde, role):
    with pytest.raises(RegleMetier):
        N.creer_compte_externe(monde['compte'], 'pas-externe', role)
    assert not Compte.objects.filter(username='pas-externe').exists()


def test_F03_nom_d_utilisateur_obligatoire_et_unique_sans_tenir_compte_de_la_casse(monde, pr):
    N.creer_compte_externe(pr, 'Unique', roles.VI)
    for nom in ('unique', 'UNIQUE', '  ', ''):
        with pytest.raises(RegleMetier):
            N.creer_compte_externe(pr, nom, roles.VI)
    assert Compte.objects.filter(username__iexact='unique').count() == 1


def test_F03_visiteur_hors_du_perimetre_du_createur_refuse(monde):
    """Un PR est national : tout périmètre est le sien. Un VP ne crée pas de visiteur (droit refusé avant le périmètre)."""
    vp = _nommer(monde, roles.VP, coordination=monde['P'])
    with pytest.raises(DroitInsuffisant):
        N.creer_compte_externe(vp, 'vi-q', roles.VI, coordination=monde['Q'])


def test_F03_mot_de_passe_temporaire_changement_force_et_absent_du_journal(monde, pr):
    compte, _n, mdp = N.creer_compte_externe(pr, 'sans-fiche', roles.VI)
    client = Client()
    r = client.post(reverse('application'), {'username': 'sans-fiche', 'password': mdp})
    assert r.status_code == 302 and client.session.get('_auth_user_id') == str(compte.pk)  # connexion acceptée
    r = client.get('/')
    assert r.status_code == 302 and 'connexion' not in r['Location']  # redirigé vers le changement de mot de passe
    tout = json.dumps([[l.avant, l.apres, l.motif, l.objet_libelle] for l in JournalAction.objects.all()], default=str)
    assert mdp not in tout
    assert JournalAction.objects.filter(action=JournalAction.Action.CREATION_COMPTE, objet_id=compte.id).exists()
    assert JournalAction.objects.filter(action=JournalAction.Action.NOMINATION, objet_id=compte.id, auteur=pr).exists()


def test_F03_le_visiteur_cree_ne_voit_que_les_membres_actifs_de_son_perimetre(client, monde, pr):
    from coptapp.models import Membre
    compte, _n, mdp = N.creer_compte_externe(pr, 'vi-liste', roles.VI, antenne=monde['antenne_p'])
    Compte.objects.filter(pk=compte.pk).update(doit_changer_mot_de_passe=False)  # mot de passe déjà changé
    compte = Compte.objects.get(pk=compte.pk)
    Membre.objects.filter(pk=monde['M'].pk).update(is_validate2=True, is_validate3=True)
    client.force_login(compte)
    assert 'Membre Fictif' in client.get('/membres/').content.decode()
    assert client.post(f'/membres/{monde["M"].id}/valider/').status_code == 403
