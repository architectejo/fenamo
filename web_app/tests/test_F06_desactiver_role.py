"""F-06 : désactiver, réactiver, terminer une nomination, changer de rôle ou de périmètre (comptes gérables)."""
import pytest
from django.contrib.auth.hashers import make_password
from django.test import Client
from django.urls import reverse

from compte import roles
from compte.models import Compte, JournalAction, Nomination
from compte.services import droits
from compte.services import nominations as N
from compte.services.nominations import DroitInsuffisant, HorsPerimetre, RegleMetier
from tests.test_F02_droits_roles import _compte, _nommer, monde  # noqa: F401
from tests.test_plan_url import hachage_rapide, jeu  # noqa: F401

A = JournalAction.Action


@pytest.fixture
def equipe(monde):
    pr = _nommer(monde, roles.PR)
    vn = _nommer(monde, roles.VN)
    vp = _nommer(monde, roles.VP, coordination=monde['P'])
    va = _nommer(monde, roles.VA, antenne=monde['antenne_p'])
    at = _nommer(monde, roles.AT, antenne=monde['antenne_p'])
    return {'PR': pr, 'VN': vn, 'VP': vp, 'VA': va, 'AT': at}


# ---------------------------------------------------------------- désactivation / réactivation

def test_F06_desactiver_puis_reactiver_journal_et_connexion(equipe):
    cible, auteur = equipe['AT'], equipe['VA']
    N.desactiver(auteur, cible, 'Départ')
    cible.refresh_from_db()
    assert not cible.is_active and Nomination.objects.get(compte=cible).active  # la nomination est conservée
    ligne = JournalAction.objects.get(action=A.DESACTIVATION_COMPTE)
    assert ligne.auteur == auteur and ligne.objet_id == cible.id and ligne.motif == 'Départ' and ligne.apres == {'is_active': False}
    assert droits.profil_de(Compte.objects.get(pk=cible.pk)).mode == 'aucun'  # un compte inactif n'a aucun droit
    Compte.objects.filter(pk=cible.pk).update(password=make_password('Mdp-test-9x'))
    c = Client()
    c.post(reverse('application'), {'username': cible.username, 'password': 'Mdp-test-9x'})
    assert '_auth_user_id' not in c.session  # compte désactivé : connexion refusée
    N.reactiver(auteur, cible, 'Retour')
    cible.refresh_from_db()
    assert cible.is_active and JournalAction.objects.get(action=A.REACTIVATION_COMPTE).motif == 'Retour'
    assert droits.profil_de(Compte.objects.get(pk=cible.pk)).role == 'AT'


def test_F06_idempotent_pas_de_double_journal(equipe):
    N.desactiver(equipe['PR'], equipe['VN'])
    N.desactiver(equipe['PR'], Compte.objects.get(pk=equipe['VN'].pk))
    assert JournalAction.objects.filter(action=A.DESACTIVATION_COMPTE).count() == 1
    N.reactiver(equipe['PR'], Compte.objects.get(pk=equipe['VN'].pk))
    N.reactiver(equipe['PR'], Compte.objects.get(pk=equipe['VN'].pk))
    assert JournalAction.objects.filter(action=A.REACTIVATION_COMPTE).count() == 1


@pytest.mark.parametrize('auteur, cible', [('VN', 'PR'), ('VN', 'VN'), ('VP', 'VP'), ('VA', 'VA'), ('VA', 'VP'), ('AT', 'AT'), ('PR', 'PR')])
def test_F06_refus_role_egal_ou_superieur_et_soi_meme(equipe, auteur, cible):
    # le président et le validateur provincial d'une autre portée sont « hors périmètre » du VA (404), les autres cas sont des refus de droit
    with pytest.raises((DroitInsuffisant, HorsPerimetre)):
        N.desactiver(equipe[auteur], equipe[cible])
    assert not N.peut_gerer(equipe[auteur], equipe[cible])
    equipe[cible].refresh_from_db()
    assert equipe[cible].is_active


def test_F06_un_su_ne_se_desactive_pas_par_un_autre_role_ni_lui_meme(monde, equipe):
    with pytest.raises(HorsPerimetre):
        N.desactiver(equipe['PR'], monde['compte'])
    with pytest.raises(DroitInsuffisant):
        N.desactiver(monde['compte'], monde['compte'])
    monde['compte'].refresh_from_db()
    assert monde['compte'].is_active
    assert N.desactiver(monde['compte'], equipe['PR'])  # le SU désactive un président


def test_F06_hors_perimetre_404_et_compte_sans_nomination_reserve_au_su(monde, equipe):
    at_q = _nommer(monde, roles.AT, antenne=monde['antenne_q'])
    with pytest.raises(HorsPerimetre):
        N.desactiver(equipe['VP'], at_q)
    with pytest.raises(HorsPerimetre):
        N.desactiver(equipe['VA'], at_q)
    legacy = _compte('legacy-6', privilege2=True)
    with pytest.raises(HorsPerimetre):
        N.desactiver(equipe['PR'], legacy)
    assert N.desactiver(monde['compte'], legacy)


def test_F06_celui_qui_a_nomme_peut_desactiver(monde):
    va = _nommer(monde, roles.VA, antenne=monde['antenne_p'])
    cible = _compte('nomme-6')
    N.creer_nomination(va, cible, roles.AT, antenne=monde['antenne_p'])
    assert N.desactiver(va, Compte.objects.get(pk=cible.pk)).is_active is False


# ---------------------------------------------------------------- terminer

def _su_de(equipe):
    return Compte.objects.get(is_superuser=True)


def test_F06_terminer_la_nomination_retire_les_droits_de_role_et_conserve_la_ligne(equipe):
    N.terminer(equipe['VA'], equipe['AT'], 'Mandat clos')
    n = Nomination.objects.get(compte=equipe['AT'])
    assert not n.active and n.terminee_par == equipe['VA'] and n.motif_fin == 'Mandat clos'
    assert droits.profil_de(Compte.objects.get(pk=equipe['AT'].pk)).mode == 'herite'
    with pytest.raises(HorsPerimetre):  # sans nomination active, le compte n'est plus gérable que par le SU
        N.terminer(equipe['VA'], Compte.objects.get(pk=equipe['AT'].pk))
    with pytest.raises(RegleMetier):
        N.terminer(equipe['VA'] if False else _su_de(equipe), Compte.objects.get(pk=equipe['AT'].pk))
    with pytest.raises(DroitInsuffisant):
        N.terminer(equipe['VA'], equipe['VA'])


# ---------------------------------------------------------------- changer de rôle ou de périmètre

def test_F06_changer_de_role_cloture_l_ancienne_et_ouvre_la_nouvelle(monde, equipe):
    cible = equipe['AT']
    nouvelle = N.changer_role_perimetre(equipe['VP'], cible, roles.VA, antenne=monde['antenne_p'], motif='Promotion')
    anciennes = Nomination.objects.filter(compte=cible, active=False)
    assert nouvelle.role == 'VA' and nouvelle.active and nouvelle.nomme_par == equipe['VP'] and nouvelle.duree_mandat_ans == 3
    assert anciennes.count() == 1 and anciennes.get().role == 'AT' and anciennes.get().motif_fin == 'Promotion'
    assert Nomination.objects.filter(compte=cible, active=True).count() == 1
    assert list(Compte.objects.get(pk=cible.pk).groups.values_list('name', flat=True)) == ['role_VA']
    ligne = JournalAction.objects.get(action=A.CHANGEMENT_ROLE)
    assert ligne.avant == {'role': 'AT'} and ligne.apres == {'role': 'VA'} and ligne.motif == 'Promotion' and ligne.auteur == equipe['VP']
    assert droits.role_de(Compte.objects.get(pk=cible.pk)) == 'VA'


def test_F06_changer_de_perimetre_garde_la_fiche_membre(monde, equipe):
    from coptapp.models import Membre
    membre = Membre.objects.create(nom='Avec fiche', antenne=monde['antenne_p'], province=monde['P'], is_validate2=True, is_validate3=True)
    compte = _compte('avec-fiche', membreId=membre.id)
    N.creer_nomination(equipe['VN'], compte, roles.VA, membre=membre, antenne=monde['antenne_p'])
    nouvelle = N.changer_role_perimetre(equipe['VN'], Compte.objects.get(pk=compte.pk), roles.VA, antenne=monde['antenne_q'])
    assert nouvelle.membre == membre and nouvelle.antenne == monde['antenne_q']


def test_F06_changement_refuse_tout_ou_rien(monde, equipe):
    cible = equipe['AT']
    for role, kw, erreur in ((roles.PR, {}, DroitInsuffisant), (roles.VP, {'coordination': monde['P']}, DroitInsuffisant),
                             (roles.AT, {'antenne': monde['antenne_q']}, HorsPerimetre), (roles.AT, {}, HorsPerimetre)):
        with pytest.raises(erreur):
            N.changer_role_perimetre(equipe['VA'] if role == roles.AT and kw else equipe['VP'], cible, role, **kw)
    actives = Nomination.objects.filter(compte=cible, active=True)
    assert actives.count() == 1 and actives.get().role == 'AT' and Nomination.objects.filter(compte=cible).count() == 1
    assert not JournalAction.objects.filter(action=A.CHANGEMENT_ROLE).exists()


def test_F06_changement_sans_nomination_active_refuse(monde, equipe):
    N.terminer(equipe['VA'], equipe['AT'])
    with pytest.raises(HorsPerimetre):  # sans nomination active, plus gérable que par le SU
        N.changer_role_perimetre(equipe['VA'], Compte.objects.get(pk=equipe['AT'].pk), roles.AT, antenne=monde['antenne_p'])
    with pytest.raises(RegleMetier):
        N.changer_role_perimetre(monde['compte'], Compte.objects.get(pk=equipe['AT'].pk), roles.AT, antenne=monde['antenne_p'])


def test_F06_le_changement_est_atomique(monde, equipe, monkeypatch):
    def echec(*a, **k):
        raise RuntimeError('panne')

    monkeypatch.setattr(N, 'creer_nomination', echec)
    with pytest.raises(RuntimeError):
        N.changer_role_perimetre(equipe['VP'], equipe['AT'], roles.VA, antenne=monde['antenne_p'])
    actives = Nomination.objects.filter(compte=equipe['AT'])
    assert actives.count() == 1 and actives.get().active  # l'ancienne n'est pas clôturée si la nouvelle échoue


# ---------------------------------------------------------------- comptes gérables, peut_gerer

def _noms(auteur):
    return set(N.comptes_gerables(auteur).values_list('username', flat=True))


def test_F06_comptes_gerables_par_role(monde, equipe):
    at_q = _nommer(monde, roles.AT, antenne=monde['antenne_q'])
    legacy = _compte('legacy-g', privilege1=True)
    tous = {c.username for c in Compte.objects.exclude(is_superuser=True)}
    assert _noms(monde['compte']) == tous                                           # le SU : tous les autres comptes non SU
    assert _noms(equipe['PR']) == {equipe[r].username for r in ('VN', 'VP', 'VA', 'AT')} | {at_q.username}
    assert _noms(equipe['VN']) == {equipe[r].username for r in ('VP', 'VA', 'AT')} | {at_q.username}
    assert _noms(equipe['VP']) == {equipe['VA'].username, equipe['AT'].username}      # sa coordination seulement
    assert _noms(equipe['VA']) == {equipe['AT'].username}
    assert _noms(equipe['AT']) == set()
    assert legacy.username not in _noms(equipe['PR']) and monde['compte'].username not in _noms(equipe['PR'])


def test_F06_comptes_gerables_incluent_ceux_que_l_on_a_nommes(monde):
    va = _nommer(monde, roles.VA, antenne=monde['antenne_p'])
    cible = _compte('nomme-g')
    N.creer_nomination(va, cible, roles.AT, antenne=monde['antenne_p'])
    assert 'nomme-g' in _noms(va) and va.username not in _noms(va)


def test_F06_peut_gerer_jamais_soi_meme_jamais_un_su(monde, equipe):
    assert not N.peut_gerer(equipe['PR'], equipe['PR']) and not N.peut_gerer(equipe['PR'], monde['compte'])
    assert N.peut_gerer(equipe['PR'], equipe['VN']) and N.peut_gerer(monde['compte'], equipe['PR'])
    assert not N.peut_gerer(monde['compte'], monde['compte'])
    assert not N.peut_gerer(equipe['VA'], equipe['VP'])
