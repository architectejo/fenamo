"""F-06 / F-05 : compléments de services pour l'écran Utilisateurs : mot de passe temporaire, renouvellement, motif obligatoire,
réactivation sans mot de passe, liste filtrée des comptes gérables, mandats à traiter."""
from datetime import timedelta

import pytest
from django.contrib.auth.hashers import check_password
from django.utils import timezone

from compte import roles
from compte.models import Compte, JournalAction, Nomination
from compte.services import comptes as C
from compte.services import nominations as N
from compte.services.nominations import DroitInsuffisant, HorsPerimetre, RegleMetier
from coptapp.models import Membre
from tests.test_F02_droits_roles import _compte, _nommer, monde  # noqa: F401
from tests.test_plan_url import hachage_rapide, jeu  # noqa: F401

A = JournalAction.Action


@pytest.fixture
def equipe(monde):
    return {'PR': _nommer(monde, roles.PR), 'VN': _nommer(monde, roles.VN),
            'VP': _nommer(monde, roles.VP, coordination=monde['P']),
            'VA': _nommer(monde, roles.VA, antenne=monde['antenne_p']),
            'AT': _nommer(monde, roles.AT, antenne=monde['antenne_p'])}


# ---------------------------------------------------------------- 1. mot de passe temporaire

def test_F05_mot_de_passe_temporaire_12_caracteres_sans_ambigus_avec_secrets(monkeypatch):
    mots = {C.mot_de_passe_temporaire() for _ in range(300)}
    assert len(mots) == 300
    for mot in mots:
        assert len(mot) == 12 and mot.isalnum()
        assert not set(C.CARACTERES_INTERDITS) & set(mot) and not set('0O1lI') & set(mot)
        assert any(c.islower() for c in mot) and any(c.isupper() for c in mot) and any(c.isdigit() for c in mot)
    appels = []
    import secrets
    vrai = secrets.choice
    monkeypatch.setattr(C.secrets, 'choice', lambda seq: appels.append(1) or vrai(seq))
    C.mot_de_passe_temporaire()
    assert len(appels) >= 12  # tirage par `secrets`, pas par `random`


def test_F05_presentation_par_groupes_de_quatre():
    assert C.en_groupes('abcdefghijkl') == 'abcd efgh ijkl' and C.en_groupes('abcdefghij') == 'abcd efgh ij'
    assert C.en_groupes('abcdefghijkl', 3) == 'abc def ghi jkl'


def test_F05_nommer_creer_externe_et_reinitialiser_utilisent_le_meme_generateur(monde, equipe, monkeypatch):
    appels = []
    vrai = C.mot_de_passe_temporaire
    monkeypatch.setattr(C, 'mot_de_passe_temporaire', lambda: appels.append(1) or vrai())
    membre = Membre.objects.create(nom='Nouveau', antenne=monde['antenne_p'], province=monde['P'], is_validate2=True, is_validate3=True)
    _n, mdp1 = N.nommer(equipe['VA'], membre, roles.AT, antenne=monde['antenne_p'])
    _c, _n, mdp2 = N.creer_compte_externe(equipe['PR'], 'externe-gen', roles.VI)
    mdp3 = N.reinitialiser_mot_de_passe(equipe['PR'], equipe['VN'])
    assert len(appels) == 3 and all(len(m) == 12 and not set('0O1lI') & set(m) for m in (mdp1, mdp2, mdp3))


# ---------------------------------------------------------------- 3. désactivation : motif obligatoire

@pytest.mark.parametrize('motif', ['', '   ', None, '\n\t'])
def test_F06_desactiver_exige_un_motif(equipe, motif):
    with pytest.raises(RegleMetier):
        N.desactiver(equipe['PR'], equipe['VN'], motif)
    equipe['VN'].refresh_from_db()
    assert equipe['VN'].is_active and not JournalAction.objects.filter(action=A.DESACTIVATION_COMPTE).exists()


def test_F06_le_motif_de_desactivation_est_nettoye_et_conserve_au_journal(equipe):
    N.desactiver(equipe['PR'], equipe['VN'], '  Départ à la retraite  ')
    assert JournalAction.objects.get(action=A.DESACTIVATION_COMPTE).motif == 'Départ à la retraite'


def test_F06_le_droit_est_controle_avant_le_motif(equipe):
    with pytest.raises(DroitInsuffisant):
        N.desactiver(equipe['VN'], equipe['VN'], '')  # soi-même : refus de droit, pas « motif manquant »


# ---------------------------------------------------------------- 4. réactivation : aucun mot de passe automatique

def test_F06_reactiver_ne_change_pas_le_mot_de_passe_ni_l_obligation_de_le_changer(equipe):
    cible = equipe['VN']
    Compte.objects.filter(pk=cible.pk).update(doit_changer_mot_de_passe=False)
    avant = Compte.objects.get(pk=cible.pk).password
    N.desactiver(equipe['PR'], Compte.objects.get(pk=cible.pk), 'Pause')
    retour = N.reactiver(equipe['PR'], Compte.objects.get(pk=cible.pk), 'Retour')
    assert retour.is_active and retour.password == avant and not retour.doit_changer_mot_de_passe
    assert not JournalAction.objects.filter(action=A.REINITIALISATION_MOT_DE_PASSE).exists()


# ---------------------------------------------------------------- 2. renouvellement de mandat

def test_F06_renouveler_cloture_et_rouvre_meme_role_meme_perimetre(monde, equipe):
    cible = equipe['AT']
    avant = Nomination.objects.get(compte=cible, active=True)
    Nomination.objects.filter(pk=avant.pk).update(fin=timezone.localdate() - timedelta(days=10))  # mandat échu
    nouvelle = N.renouveler_mandat(equipe['VA'], Compte.objects.get(pk=cible.pk))
    avant.refresh_from_db()
    assert not avant.active and avant.motif_fin == 'renouvellement' and avant.terminee_par == equipe['VA']
    assert nouvelle.active and nouvelle.role == 'AT' and nouvelle.antenne == monde['antenne_p'] and nouvelle.membre == avant.membre
    assert nouvelle.debut == timezone.localdate() and nouvelle.fin == nouvelle.debut.replace(year=nouvelle.debut.year + 3)
    assert nouvelle.nomme_par == equipe['VA'] and nouvelle.alerte_envoyee_le is None
    assert Nomination.objects.filter(compte=cible, active=True).count() == 1 and Nomination.objects.filter(compte=cible).count() == 2
    ligne = JournalAction.objects.get(action=A.CHANGEMENT_ROLE)
    assert ligne.motif == 'renouvellement' and ligne.avant['role'] == ligne.apres['role'] == 'AT' and ligne.auteur == equipe['VA']
    assert JournalAction.objects.filter(action=A.FIN_NOMINATION).count() == 1 and JournalAction.objects.filter(action=A.NOMINATION, apres__role='AT').count() >= 1


@pytest.mark.parametrize('auteur, cible, ans', [('PR', 'VN', 5), ('PR', 'VP', 4), ('VN', 'VA', 3), ('VP', 'AT', 3)])
def test_F06_renouveler_duree_selon_le_role(equipe, auteur, cible, ans):
    nouvelle = N.renouveler_mandat(equipe[auteur], equipe[cible])
    assert nouvelle.duree_mandat_ans == ans and nouvelle.fin.year == nouvelle.debut.year + ans


def test_F06_renouveler_memes_controles_que_changer_role(monde, equipe):
    for auteur, cible, erreur in (('VA', 'VA', DroitInsuffisant), ('VN', 'PR', DroitInsuffisant), ('VA', 'VP', (HorsPerimetre, DroitInsuffisant))):
        with pytest.raises(erreur):
            N.renouveler_mandat(equipe[auteur], equipe[cible])
    at_q = _nommer(monde, roles.AT, antenne=monde['antenne_q'])
    with pytest.raises(HorsPerimetre):
        N.renouveler_mandat(equipe['VP'], at_q)
    legacy = _compte('legacy-renouv', privilege1=True)
    with pytest.raises(HorsPerimetre):
        N.renouveler_mandat(equipe['PR'], legacy)
    assert Nomination.objects.filter(compte=equipe['VA']).count() == 1 and Nomination.objects.filter(compte=at_q).count() == 1
    assert not JournalAction.objects.filter(action=A.CHANGEMENT_ROLE).exists()


def test_F06_renouveler_refus_sans_mandat_ou_sans_nomination(monde, equipe):
    visiteur = _nommer(monde, roles.VI)
    with pytest.raises(RegleMetier):
        N.renouveler_mandat(equipe['PR'], visiteur)
    N.terminer(equipe['PR'], equipe['VN'])
    with pytest.raises(HorsPerimetre):  # sans nomination active : gérable par le SU seulement
        N.renouveler_mandat(equipe['PR'], Compte.objects.get(pk=equipe['VN'].pk))
    with pytest.raises(RegleMetier):
        N.renouveler_mandat(monde['compte'], Compte.objects.get(pk=equipe['VN'].pk))


def test_F06_renouveler_est_atomique(monde, equipe, monkeypatch):
    def echec(*a, **k):
        raise RuntimeError('panne')

    monkeypatch.setattr(N, 'creer_nomination', echec)
    with pytest.raises(RuntimeError):
        N.renouveler_mandat(equipe['VP'], equipe['AT'])
    assert Nomination.objects.filter(compte=equipe['AT']).count() == 1 and Nomination.objects.get(compte=equipe['AT']).active


def test_F06_renouveler_un_mandat_echu_remet_la_nomination_en_cours_sans_alerte(monde, equipe):
    cible = equipe['AT']
    Nomination.objects.filter(compte=cible, active=True).update(fin=timezone.localdate() - timedelta(days=1))
    assert [n.compte for n in N.mandats_a_traiter(equipe['VA'])] == [cible]
    N.renouveler_mandat(equipe['VA'], Compte.objects.get(pk=cible.pk))
    assert list(N.mandats_a_traiter(equipe['VA'])) == []


# ---------------------------------------------------------------- 5. liste des comptes gérables

def _noms(auteur, **filtres):
    return [c.username for c in N.lister_comptes_gerables(auteur, filtres)]


def test_F06_liste_sans_filtre_les_comptes_gerables_tries_par_nom(monde, equipe):
    assert _noms(equipe['PR']) == sorted(_noms(equipe['PR'])) and set(_noms(equipe['PR'])) == {equipe[r].username for r in ('VN', 'VP', 'VA', 'AT')}
    assert set(_noms(equipe['VA'])) == {equipe['AT'].username}
    assert N.lister_comptes_gerables(equipe['PR']).count() == 4 and list(N.lister_comptes_gerables(equipe['PR'], None))
    assert set(_noms(monde['compte'])) == {c.username for c in Compte.objects.exclude(is_superuser=True)}


def test_F06_liste_recherche_q_sur_compte_courriel_nom_et_membre(monde, equipe):
    Compte.objects.filter(pk=equipe['VA'].pk).update(first_name='Honoré', last_name='Mukendi', email='honore@example.invalid')
    membre = Membre.objects.create(nom='Kasongo Joseph', antenne=monde['antenne_p'], province=monde['P'])
    Compte.objects.filter(pk=equipe['AT'].pk).update(membreId=membre.id)
    assert _noms(equipe['PR'], q='honor') == [equipe['VA'].username] and _noms(equipe['PR'], q='MUKENDI') == [equipe['VA'].username]
    assert _noms(equipe['PR'], q='honore@example') == [equipe['VA'].username]
    assert _noms(equipe['PR'], q='kasongo') == [equipe['AT'].username]
    assert _noms(equipe['PR'], q=equipe['VP'].username[:8]) == [c for c in _noms(equipe['PR']) if c.startswith(equipe['VP'].username[:8])]
    assert _noms(equipe['PR'], q='introuvable-xyz') == [] and _noms(equipe['PR'], q='   ') == _noms(equipe['PR'])


def test_F06_liste_filtre_par_role_et_comptes_sans_nomination(monde, equipe):
    legacy = _compte('legacy-liste', privilege1=True)
    assert _noms(equipe['PR'], role='VA') == [equipe['VA'].username] and _noms(equipe['PR'], role='va') == [equipe['VA'].username]
    assert _noms(equipe['PR'], role='ED') == []
    sans = _noms(monde['compte'], role='sans')
    assert legacy.username in sans and not {equipe[r].username for r in equipe} & set(sans)
    assert set(_noms(monde['compte'], role='AT')) == {equipe['AT'].username}


def test_F06_liste_filtre_par_lieu(monde, equipe):
    at_q = _nommer(monde, roles.AT, antenne=monde['antenne_q'])
    pr = equipe['PR']
    assert set(_noms(pr, coordination=monde['P'].id)) == {equipe['VP'].username, equipe['VA'].username, equipe['AT'].username}
    assert _noms(pr, coordination=monde['Q'].id) == [at_q.username]  # par l'antenne de la coordination
    assert set(_noms(pr, antenne=monde['antenne_p'].id)) == {equipe['VA'].username, equipe['AT'].username}
    assert _noms(pr, antenne=monde['antenne_q'].id) == [at_q.username]
    assert _noms(pr, role='AT', antenne=monde['antenne_p'].id) == [equipe['AT'].username]  # critères combinés sur la même nomination
    assert _noms(pr, role='VA', antenne=monde['antenne_q'].id) == []


def test_F06_liste_filtre_par_etat_du_compte(monde, equipe):
    Compte.objects.filter(pk=equipe['VN'].pk).update(doit_changer_mot_de_passe=False)
    Compte.objects.filter(pk=equipe['VP'].pk).update(doit_changer_mot_de_passe=True)
    Compte.objects.filter(pk=equipe['VA'].pk).update(doit_changer_mot_de_passe=False, is_active=False)
    Compte.objects.filter(pk=equipe['AT'].pk).update(doit_changer_mot_de_passe=False)
    pr = equipe['PR']
    assert set(_noms(pr, etat='actif')) == {equipe['VN'].username, equipe['AT'].username}
    assert _noms(pr, etat='temporaire') == [equipe['VP'].username]
    assert _noms(pr, etat='desactive') == [equipe['VA'].username]
    assert _noms(pr, etat='inconnu') == _noms(pr)  # filtre inconnu ignoré


def test_F06_liste_filtre_par_mandat(monde, equipe):
    jour = timezone.localdate()
    Nomination.objects.filter(compte=equipe['VN']).update(fin=jour - timedelta(days=5))
    Nomination.objects.filter(compte=equipe['VP']).update(fin=jour + timedelta(days=30))
    Nomination.objects.filter(compte=equipe['VA']).update(fin=jour + timedelta(days=90))
    Nomination.objects.filter(compte=equipe['AT']).update(fin=None)
    pr = equipe['PR']
    assert _noms(pr, mandat='echu') == [equipe['VN'].username] and _noms(pr, mandat='a_echoir') == [equipe['VP'].username]
    assert _noms(pr, mandat='sans_fin') == [equipe['AT'].username]
    assert _noms(pr, mandat='echu', role='VA') == []


def test_F06_liste_sans_doublon_et_sans_requete_par_ligne(monde, equipe, django_assert_max_num_queries):
    for i in range(6):
        _nommer(monde, roles.AT, antenne=monde['antenne_p'])
    with django_assert_max_num_queries(8):
        comptes = list(N.lister_comptes_gerables(equipe['PR'], {'role': 'AT'}))
        lieux = [(c.nomination_active_liste[0].role, c.nomination_active_liste[0].antenne.nom, c.nomination_active_liste[0].nomme_par) for c in comptes]
    assert len(comptes) == len({c.pk for c in comptes}) == 7 and all(l[0] == 'AT' for l in lieux)


def test_F06_liste_est_limitee_aux_comptes_gerables(monde, equipe):
    at_q = _nommer(monde, roles.AT, antenne=monde['antenne_q'])
    assert at_q.username not in _noms(equipe['VP']) and monde['compte'].username not in _noms(equipe['PR'])
    assert equipe['PR'].username not in _noms(equipe['PR'])
    assert _noms(equipe['AT']) == [] and list(N.lister_comptes_gerables(equipe['AT'], {'role': 'AT'})) == []


# ---------------------------------------------------------------- mandats à traiter

def test_F06_mandats_a_traiter_echus_et_a_echoir_les_plus_urgents_d_abord(monde, equipe):
    jour = timezone.localdate()
    Nomination.objects.filter(compte=equipe['VN']).update(fin=jour - timedelta(days=5))
    Nomination.objects.filter(compte=equipe['VP']).update(fin=jour + timedelta(days=30))
    Nomination.objects.filter(compte=equipe['VA']).update(fin=jour + timedelta(days=61))
    Nomination.objects.filter(compte=equipe['AT']).update(fin=None)
    liste = list(N.mandats_a_traiter(equipe['PR']))
    assert [n.compte_id for n in liste] == [equipe['VN'].pk, equipe['VP'].pk]
    assert [N.etat_mandat(n, jour) for n in liste] == ['echu', 'a_echoir']
    assert [n.compte_id for n in N.mandats_a_traiter(equipe['PR'], jours=90)][-1] == equipe['VA'].pk
    assert list(N.mandats_a_traiter(equipe['PR'], jours=10)) == [liste[0]]


def test_F06_mandats_a_traiter_limites_aux_comptes_gerables_et_actifs(monde, equipe):
    at_q = _nommer(monde, roles.AT, antenne=monde['antenne_q'])
    Nomination.objects.filter(compte__in=[at_q, equipe['AT'], equipe['VA']]).update(fin=timezone.localdate() - timedelta(days=1))
    assert [n.compte_id for n in N.mandats_a_traiter(equipe['VP'])] == sorted([equipe['AT'].pk, equipe['VA'].pk])  # pas at_q (hors coordination)
    assert [n.compte_id for n in N.mandats_a_traiter(equipe['VA'])] == [equipe['AT'].pk]
    assert list(N.mandats_a_traiter(equipe['AT'])) == []
    N.terminer(equipe['VA'], equipe['AT'])
    assert [n.compte_id for n in N.mandats_a_traiter(equipe['VA'])] == []  # terminée : plus à traiter
    assert monde['compte'].username  # le SU voit les comptes non SU
    assert at_q.pk in [n.compte_id for n in N.mandats_a_traiter(monde['compte'])]


def test_F06_mandats_a_traiter_sans_requete_par_ligne(monde, equipe, django_assert_max_num_queries):
    for i in range(5):
        n = N.creer_nomination(monde['compte'], _compte(f'echu-{i}'), roles.VA, antenne=monde['antenne_p'])
        Nomination.objects.filter(pk=n.pk).update(fin=timezone.localdate() - timedelta(days=i + 1))
    with django_assert_max_num_queries(5):
        lignes = [(n.compte.username, n.antenne.nom if n.antenne_id else '', n.nomme_par, N.etat_mandat(n)) for n in N.mandats_a_traiter(monde['compte'])]
    assert len(lignes) == 5 and all(l[3] == 'echu' for l in lignes)
