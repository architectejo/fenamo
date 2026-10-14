"""F-05 : réinitialiser un mot de passe (celui qui a nommé, rôles supérieurs dans le périmètre, SU)."""
import json

import pytest
from django.contrib.auth.hashers import check_password, make_password
from django.test import Client
from django.urls import reverse

from compte import roles
from compte.models import Compte, JournalAction
from compte.services import nominations as N
from compte.services.nominations import DroitInsuffisant, HorsPerimetre
from tests.test_F02_droits_roles import _compte, _nommer, monde  # noqa: F401
from tests.test_plan_url import hachage_rapide, jeu  # noqa: F401


def _journaux():
    return json.dumps([[l.avant, l.apres, l.motif, l.objet_libelle] for l in JournalAction.objects.all()], default=str)


def test_F05_nominal_mot_de_passe_temporaire_changement_force_journal_sans_mot_de_passe(monde):
    pr = _nommer(monde, roles.PR)
    vn = _nommer(monde, roles.VN)
    ancien = vn.password
    mdp = N.reinitialiser_mot_de_passe(pr, vn)
    vn.refresh_from_db()
    assert vn.password != ancien and check_password(mdp, vn.password) and vn.doit_changer_mot_de_passe and len(mdp) == 12
    ligne = JournalAction.objects.get(action=JournalAction.Action.REINITIALISATION_MOT_DE_PASSE)
    assert ligne.auteur == pr and ligne.objet_id == vn.id and ligne.apres == {'changement_impose': True}
    assert mdp not in _journaux() and vn.password not in _journaux()
    assert N.reinitialiser_mot_de_passe(pr, vn) != mdp  # chaque réinitialisation donne un mot de passe différent


@pytest.mark.parametrize('auteur_role, cible_role, kw_auteur, kw_cible', [
    ('PR', roles.VN, {}, {}), ('VN', roles.VP, {}, {'coordination': 'P'}), ('VP', roles.VA, {'coordination': 'P'}, {'antenne': 'antenne_p'}),
    ('VP', roles.AT, {'coordination': 'P'}, {'antenne': 'antenne_p'}), ('VA', roles.AT, {'antenne': 'antenne_p'}, {'antenne': 'antenne_p'}),
    ('PR', roles.VI, {}, {}),
])
def test_F05_roles_superieurs_dans_le_perimetre(monde, auteur_role, cible_role, kw_auteur, kw_cible):
    auteur = _nommer(monde, getattr(roles, auteur_role), **{k: monde[v] for k, v in kw_auteur.items()})
    cible = _nommer(monde, cible_role, **{k: monde[v] for k, v in kw_cible.items()})
    assert N.peut_gerer(auteur, cible) and N.reinitialiser_mot_de_passe(auteur, cible)


def test_F05_refus_soi_meme_role_egal_ou_superieur(monde):
    vn, pr = _nommer(monde, roles.VN), _nommer(monde, roles.PR)
    va = _nommer(monde, roles.VA, antenne=monde['antenne_p'])
    for auteur, cible in ((vn, vn), (pr, pr), (vn, pr), (vn, _nommer(monde, roles.VN)), (va, _nommer(monde, roles.VA, antenne=monde['antenne_p']))):
        with pytest.raises(DroitInsuffisant):
            N.reinitialiser_mot_de_passe(auteur, cible)
        assert not N.peut_gerer(auteur, cible)
    assert not JournalAction.objects.filter(action=JournalAction.Action.REINITIALISATION_MOT_DE_PASSE).exists()


def test_F05_un_su_n_est_jamais_gere_par_un_autre_role_et_le_su_gere_tout_le_monde(monde):
    pr = _nommer(monde, roles.PR)
    autre_su = _compte('autre-su', is_superuser=True)
    for cible in (monde['compte'], autre_su):
        with pytest.raises(HorsPerimetre):
            N.reinitialiser_mot_de_passe(pr, cible)
    vn = _nommer(monde, roles.VN)
    legacy = _compte('legacy', privilege3=True)
    assert N.reinitialiser_mot_de_passe(monde['compte'], vn) and N.reinitialiser_mot_de_passe(monde['compte'], legacy)
    assert N.reinitialiser_mot_de_passe(monde['compte'], autre_su)  # le SU gère un autre SU, jamais lui-même
    with pytest.raises(DroitInsuffisant):
        N.reinitialiser_mot_de_passe(monde['compte'], monde['compte'])


def test_F05_hors_perimetre_et_compte_sans_nomination_404(monde):
    vp = _nommer(monde, roles.VP, coordination=monde['P'])
    at_q = _nommer(monde, roles.AT, antenne=monde['antenne_q'])
    vn = _nommer(monde, roles.VN)
    legacy = _compte('legacy2', privilege1=True)
    for cible in (at_q, vn, legacy):
        with pytest.raises(HorsPerimetre):
            N.reinitialiser_mot_de_passe(vp, cible)
    pr = _nommer(monde, roles.PR)
    with pytest.raises(HorsPerimetre):
        N.reinitialiser_mot_de_passe(pr, legacy)  # un compte sans nomination ne se gère que par le SU


def test_F05_celui_qui_a_nomme_peut_reinitialiser(monde):
    va = _nommer(monde, roles.VA, antenne=monde['antenne_p'])
    cible = _compte('nomme-par-va')
    N.creer_nomination(va, cible, roles.AT, antenne=monde['antenne_p'])
    assert N.reinitialiser_mot_de_passe(va, Compte.objects.get(pk=cible.pk))


def test_F05_visiteur_editeur_et_agent_ne_reinitialisent_personne(monde):
    cible = _nommer(monde, roles.AT, antenne=monde['antenne_p'])
    for role, kw in ((roles.VI, {}), (roles.ED, {}), (roles.AT, {'antenne': monde['antenne_p']})):
        auteur = _nommer(monde, role, **kw)
        with pytest.raises((DroitInsuffisant, HorsPerimetre)):
            N.reinitialiser_mot_de_passe(auteur, cible)
    sans_role = _compte('sans-role-5', privilege5=True)
    with pytest.raises(HorsPerimetre):
        N.reinitialiser_mot_de_passe(sans_role, cible)


def test_F05_l_ancien_mot_de_passe_cesse_de_marcher(client, monde):
    pr = _nommer(monde, roles.PR)
    vn = _nommer(monde, roles.VN)
    Compte.objects.filter(pk=vn.pk).update(password=make_password('Ancien-9x'))

    def connexion(mdp):
        c = Client()
        c.post(reverse('application'), {'username': vn.username, 'password': mdp})
        return '_auth_user_id' in c.session

    assert connexion('Ancien-9x')
    mdp = N.reinitialiser_mot_de_passe(pr, Compte.objects.get(pk=vn.pk))
    assert not connexion('Ancien-9x') and connexion(mdp)
