"""F-02 : nommer un membre actif dans un rôle inférieur au sien, dans son périmètre (§ 4.2, matrice § 4.3)."""
import json

import pytest
from django.contrib.auth.hashers import check_password

from compte import roles
from compte.models import Compte, JournalAction, Nomination
from compte.services import nominations as N
from compte.services.nominations import DroitInsuffisant, HorsPerimetre, RegleMetier
from coptapp.models import Membre
from tests.test_F02_droits_roles import _compte, _nommer, monde  # noqa: F401
from tests.test_plan_url import hachage_rapide, jeu  # noqa: F401


def actif(monde, nom, antenne=None, province=None, **kw):
    """Un membre ACTIF (validé aux trois niveaux) de l'antenne / coordination donnée."""
    return Membre.objects.create(nom=nom, antenne=antenne or monde['antenne_p'], province=province or monde['P'],
                                 is_validate2=True, is_validate3=True, **kw)


@pytest.fixture
def chefs(monde):
    return {
        'PR': _nommer(monde, roles.PR), 'VN': _nommer(monde, roles.VN),
        'VP': _nommer(monde, roles.VP, coordination=monde['P']), 'VA': _nommer(monde, roles.VA, antenne=monde['antenne_p']),
        'AT': _nommer(monde, roles.AT, antenne=monde['antenne_p']), 'VI': _nommer(monde, roles.VI), 'ED': _nommer(monde, roles.ED),
    }


# ---------------------------------------------------------------- rôles nommables (table § 4.3)

@pytest.mark.parametrize('role, attendus', [
    ('PR', {'VN', 'VP', 'VA', 'AT', 'VI'}), ('VN', {'VP', 'VA', 'AT'}), ('VP', {'VA', 'AT'}), ('VA', {'AT'}),
    ('AT', set()), ('VI', set()), ('ED', set()),
])
def test_F02_roles_nommables_par_role(chefs, role, attendus):
    assert set(N.roles_nommables(chefs[role])) == attendus


def test_F02_le_su_nomme_tout_sauf_un_su_et_les_comptes_sans_role_ne_nomment_rien(monde):
    assert set(N.roles_nommables(monde['compte'])) == set(roles.ROLES) - {'SU'}
    assert N.roles_nommables(_compte('sans-role', privilege5=True)) == ()  # les droits hérités ne donnent pas le droit de nommer


# ---------------------------------------------------------------- nominal

def test_F02_pr_nomme_un_vn_compte_cree_mot_de_passe_temporaire_a_lecture_unique(monde, chefs):
    membre = actif(monde, 'Futur VN')
    nomination, mdp = N.nommer(chefs['PR'], membre, roles.VN)
    compte = nomination.compte
    assert nomination.role == 'VN' and nomination.membre == membre and nomination.nomme_par == chefs['PR'] and nomination.active
    assert nomination.duree_mandat_ans == 5 and nomination.fin.year == nomination.debut.year + 5
    assert compte.membreId == membre.id and compte.doit_changer_mot_de_passe and check_password(mdp, compte.password) and len(mdp) == 12
    assert list(compte.groups.values_list('name', flat=True)) == ['role_VN']
    lignes = JournalAction.objects.filter(action=JournalAction.Action.NOMINATION, objet_id=compte.id)
    assert lignes.count() == 1 and lignes.get().auteur == chefs['PR'] and lignes.get().apres['role'] == 'VN'
    tout = json.dumps([[l.avant, l.apres, l.motif, l.objet_libelle] for l in JournalAction.objects.all()], default=str)
    assert mdp not in tout  # jamais de mot de passe au journal


def test_F02_compte_existant_du_membre_reutilise_sans_nouveau_mot_de_passe(monde, chefs):
    membre = actif(monde, 'A déjà un compte')
    existant = _compte('deja-la', membreId=membre.id)
    nomination, mdp = N.nommer(chefs['VN'], membre, roles.VA, antenne=monde['antenne_p'])
    assert mdp is None and nomination.compte == existant and Compte.objects.filter(membreId=membre.id).count() == 1


@pytest.mark.parametrize('auteur, role, perimetre', [
    ('VN', roles.VP, {'coordination': 'P'}), ('VN', roles.VA, {'antenne': 'antenne_p'}), ('VN', roles.AT, {'antenne': 'antenne_q'}),
    ('PR', roles.VI, {}), ('PR', roles.VI, {'coordination': 'Q'}), ('PR', roles.VI, {'antenne': 'antenne_p'}),
    ('VP', roles.VA, {'antenne': 'antenne_p'}), ('VP', roles.AT, {'antenne': 'antenne_p'}), ('VA', roles.AT, {'antenne': 'antenne_p'}),
])
def test_F02_nominations_permises(monde, chefs, auteur, role, perimetre):
    kw = {cle: monde[valeur] for cle, valeur in perimetre.items()}
    membre = actif(monde, f'Nommé {auteur}{role}', antenne=monde['antenne_p'])
    nomination, _ = N.nommer(chefs[auteur], membre, role, **kw)
    assert nomination.role == role and nomination.active


def test_F02_le_su_nomme_un_president_et_un_editeur_membre(monde):
    pr, _mdp = N.nommer(monde['compte'], actif(monde, 'Futur PR'), roles.PR)
    ed, _mdp = N.nommer(monde['compte'], actif(monde, 'Futur ED'), roles.ED)
    assert pr.role == 'PR' and ed.role == 'ED' and ed.fin is None


# ---------------------------------------------------------------- refus : rôle (403), périmètre (404), état (400)

@pytest.mark.parametrize('auteur, role, perimetre', [
    ('PR', roles.PR, {}), ('PR', roles.ED, {}), ('PR', roles.SU, {}), ('VN', roles.PR, {}), ('VN', roles.VN, {}),
    ('VN', roles.VI, {}), ('VP', roles.VP, {'coordination': 'P'}), ('VP', roles.VN, {}), ('VA', roles.VA, {'antenne': 'antenne_p'}),
    ('VA', roles.VP, {'coordination': 'P'}), ('AT', roles.AT, {'antenne': 'antenne_p'}), ('VI', roles.AT, {'antenne': 'antenne_p'}),
    ('ED', roles.VI, {}),
])
def test_F02_anti_escalade_on_ne_nomme_jamais_un_role_superieur_ou_egal(monde, chefs, auteur, role, perimetre):
    kw = {cle: monde[valeur] for cle, valeur in perimetre.items()}
    avant = Nomination.objects.count()
    with pytest.raises(DroitInsuffisant):
        N.nommer(chefs[auteur], actif(monde, 'Cible'), role, **kw)
    assert Nomination.objects.count() == avant and not Compte.objects.filter(username__startswith='cible').exists()


@pytest.mark.parametrize('auteur, role, perimetre', [
    ('VP', roles.VA, {'antenne': 'antenne_q'}), ('VP', roles.AT, {'antenne': 'antenne_q'}),
    ('VA', roles.AT, {'antenne': 'antenne_q'}),
])
def test_F02_perimetre_vise_hors_du_sien_404(monde, chefs, auteur, role, perimetre):
    kw = {cle: monde[valeur] for cle, valeur in perimetre.items()}
    with pytest.raises(HorsPerimetre):
        N.nommer(chefs[auteur], actif(monde, 'Cible'), role, **kw)


def test_F02_membre_hors_du_perimetre_de_l_auteur_404(monde, chefs):
    chez_q = actif(monde, 'Chez Q', antenne=monde['antenne_q'], province=monde['Q'])
    for auteur, role, kw in (('VP', roles.VA, {'antenne': monde['antenne_p']}), ('VA', roles.AT, {'antenne': monde['antenne_p']})):
        with pytest.raises(HorsPerimetre):
            N.nommer(chefs[auteur], chez_q, role, **kw)
    supprime = actif(monde, 'Supprimé')
    Membre.objects.filter(pk=supprime.pk).update(is_delete=True)
    with pytest.raises(HorsPerimetre):
        N.nommer(chefs['PR'], supprime, roles.VN)


def test_F02_le_membre_nomme_doit_etre_actif(monde, chefs):
    for etat in ({}, {'is_validate2': True}):
        membre = Membre.objects.create(nom='Pas actif', antenne=monde['antenne_p'], province=monde['P'], **etat)
        with pytest.raises(RegleMetier):
            N.nommer(chefs['VA'], membre, roles.AT, antenne=monde['antenne_p'])


def test_F02_une_seule_nomination_active_membre_deja_nomme_ou_compte_su(monde, chefs):
    membre = actif(monde, 'Déjà nommé')
    N.nommer(chefs['PR'], membre, roles.VN)
    with pytest.raises(RegleMetier):
        N.nommer(chefs['PR'], membre, roles.VP, coordination=monde['P'])
    assert Nomination.objects.filter(membre=membre, active=True).count() == 1
    su_membre = actif(monde, 'Membre du SU')
    _compte('un-su', is_superuser=True, membreId=su_membre.id)
    with pytest.raises(RegleMetier):
        N.nommer(chefs['PR'], su_membre, roles.VN)


@pytest.mark.parametrize('role, kw', [(roles.VP, {}), (roles.VA, {}), (roles.AT, {})])
def test_F02_incoherence_role_perimetre_refusee_par_le_service(monde, chefs, role, kw):
    with pytest.raises(RegleMetier):
        N.nommer(chefs['VN'], actif(monde, 'Incohérent'), role, **kw)


def test_F02_compte_sans_role_ou_visiteur_ne_peut_pas_nommer(monde, chefs):
    for auteur in (_compte('sans-role'), chefs['VI'], chefs['ED'], chefs['AT']):
        with pytest.raises(DroitInsuffisant):
            N.nommer(auteur, actif(monde, 'Cible2'), roles.AT, antenne=monde['antenne_p'])


# ---------------------------------------------------------------- membres nommables

def test_F02_membres_nommables_actifs_du_perimetre_sans_nomination(monde, chefs):
    a = actif(monde, 'Actif P')
    b = actif(monde, 'Actif Q', antenne=monde['antenne_q'], province=monde['Q'])
    Membre.objects.create(nom='Saisi P', antenne=monde['antenne_p'], province=monde['P'])  # pas actif
    deja = actif(monde, 'Déjà nommé')
    N.nommer(chefs['PR'], deja, roles.VN)
    pr = set(N.membres_nommables(chefs['PR']).values_list('pk', flat=True))
    assert {a.id, b.id} <= pr and deja.id not in pr and monde['M'].id not in pr
    vp = set(N.membres_nommables(chefs['VP']).values_list('pk', flat=True))
    assert a.id in vp and b.id not in vp
    va = set(N.membres_nommables(chefs['VA']).values_list('pk', flat=True))
    assert a.id in va and b.id not in va
    assert N.membres_nommables(chefs['AT']).count() == 0 and N.membres_nommables(chefs['VI']).count() == 0
