"""Droits provisoires déduits des privilèges hérités (remplacés par compte/services/droits.py au sous-lot 2e)."""
from datetime import date

import pytest

from compte.models import Compte
from coptapp.models import AssociationMembre, Membre
from compte.services.droits import droits_membre, etapes_a_valider, membres_du_perimetre
from coptapp.services.tableau_bord import indicateurs_tableau_bord
from tests.test_plan_url import hachage_rapide, jeu  # noqa: F401

CLES = ('peut_modifier', 'peut_valider', 'peut_demander_suppression', 'peut_attribuer_privileges',
        'peut_ajouter_famille', 'peut_ajouter_engin', 'peut_voir_historique')


def _compte(nom, **privileges):
    return Compte.objects.create_user(nom, password='x', **privileges)


def _vrais(droits):
    return {cle for cle in CLES if droits[cle]}


def test_F28_droits_super_utilisateur(jeu):
    assert _vrais(droits_membre(jeu['compte'], jeu['membre'])) == {
        'peut_modifier', 'peut_valider', 'peut_demander_suppression', 'peut_attribuer_privileges',
        'peut_ajouter_famille', 'peut_ajouter_engin', 'peut_voir_historique'}


def test_F28_privilege5_ne_donne_pas_l_attribution_des_privileges(jeu):
    droits = droits_membre(_compte('p5', privilege5=True), jeu['membre'])
    assert droits['peut_modifier'] and droits['peut_valider'] and not droits['peut_attribuer_privileges']


def test_F28_droits_visiteur_lecture_seule_meme_cumule(jeu):
    for compte in (_compte('v', privilege4=True), _compte('v2', privilege4=True, privilege1=True, privilege2=True, privilege3=True)):
        assert _vrais(droits_membre(compte, jeu['membre'])) == set()
        assert not droits_membre(compte, jeu['membre'])['peut_demander_modification']


def test_F28_droits_agent_privilege1(jeu):
    agent = _compte('agent', privilege1=True)
    droits = droits_membre(agent, jeu['membre'])
    assert _vrais(droits) == {'peut_demander_suppression'}  # pas sa saisie : ni engins ni famille
    assert droits_membre(agent, Membre(user=agent, structure=None))['peut_ajouter_engin']
    assert droits_membre(agent, Membre(user=agent))['peut_ajouter_famille']
    assert droits['peut_demander_modification'] and not droits['peut_modifier']


def test_F28_droits_privilege2_valide_et_voit_l_historique(jeu):
    droits = droits_membre(_compte('p2', privilege2=True), jeu['membre'])
    assert _vrais(droits) == {'peut_valider', 'peut_demander_suppression', 'peut_voir_historique'}


def test_F28_droits_privilege3_modifie_seulement_dans_son_association(jeu):
    p3 = _compte('p3', privilege3=True)
    assert not droits_membre(p3, jeu['membre'])['peut_modifier']
    jeu['association'].users.add(p3)
    droits = droits_membre(p3, jeu['membre'])
    assert droits['peut_modifier'] and droits['peut_ajouter_famille'] and not droits['peut_valider']  # étape 2 pas encore validée
    autre = AssociationMembre.objects.create(nom='Autre', num_justice='F-9')
    etranger = Membre.objects.create(nom='Etranger', structure=autre, etat='valide_antenne')
    assert not droits_membre(p3, etranger)['peut_modifier']


def test_F28_droits_sans_privilege_ni_connexion(jeu):
    assert _vrais(droits_membre(_compte('nu'), jeu['membre'])) == set()
    from django.contrib.auth.models import AnonymousUser
    assert _vrais(droits_membre(AnonymousUser(), jeu['membre'])) == set()
    inactif = _compte('inactif', privilege5=True, is_active=False)
    assert _vrais(droits_membre(inactif, jeu['membre'])) == set()


def test_F28_droits_liste_sans_membre(jeu):
    assert droits_membre(_compte('p3b', privilege3=True))['peut_modifier']
    assert droits_membre(_compte('p2b', privilege2=True))['peut_valider']
    assert not droits_membre(_compte('p1b', privilege1=True))['peut_valider']


def test_F28_peut_valider_faux_quand_rien_a_valider(jeu):
    Membre.objects.filter(pk=jeu['membre'].pk).update(etat='actif')
    membre = Membre.objects.get(pk=jeu['membre'].pk)
    assert not droits_membre(jeu['compte'], membre)['peut_valider']
    assert etapes_a_valider(jeu['compte'], membre) == []


def test_F28_etapes_a_valider(jeu):
    membre = jeu['membre']
    assert etapes_a_valider(jeu['compte'], membre) == ['valide_antenne', 'valide_province', 'actif']
    assert etapes_a_valider(_compte('p2c', privilege2=True), membre) == ['valide_antenne']
    assert etapes_a_valider(_compte('p3c', privilege3=True), membre) == []  # étape d'antenne exigée avant l'étape nationale
    Membre.objects.filter(pk=membre.pk).update(etat='valide_antenne')
    membre.refresh_from_db()
    assert etapes_a_valider(_compte('p3d', privilege3=True), membre) == ['actif']
    assert etapes_a_valider(_compte('p2d', privilege2=True), membre) == []
    assert etapes_a_valider(_compte('p1c', privilege1=True), membre) == []
    assert etapes_a_valider(_compte('p4c', privilege4=True, privilege2=True), membre) == []


def test_F28_perimetre_agent_ses_saisies_et_sa_fiche(jeu):
    agent = _compte('agent2', privilege1=True)
    sien = Membre.objects.create(nom='Saisi par agent', user=agent)
    Membre.objects.create(nom='Saisi par un autre', user=jeu['compte'])
    assert [m.nom for m in membres_du_perimetre(agent)] == ['Saisi par agent']
    agent.membreId = jeu['membre'].id
    agent.save()
    assert {m.nom for m in membres_du_perimetre(agent)} == {'Saisi par agent', 'Membre Fictif'}
    assert sien.pk


def test_F28_perimetre_supprimes_exclus_sauf_demande(jeu):
    Membre.objects.filter(pk=jeu['membre'].pk).update(etat='supprime', etat_precedent='saisi')
    assert membres_du_perimetre(jeu['compte']).count() == 0
    assert membres_du_perimetre(jeu['compte'], avec_supprimes=True).count() == 1


def test_F28_perimetre_sans_privilege_est_vide(jeu):
    assert membres_du_perimetre(_compte('rien')).count() == 0


def test_F28_compteurs_engins_et_associations_suivent_le_meme_perimetre(jeu):
    visiteur = _compte('visit', privilege4=True)  # voit seulement les membres actifs
    ind = indicateurs_tableau_bord(visiteur)
    assert (ind['actifs'], ind['engins'], ind['associations']) == (0, 0, 0)
    Membre.objects.filter(pk=jeu['membre'].pk).update(etat='actif')
    ind = indicateurs_tableau_bord(visiteur)
    assert (ind['actifs'], ind['engins'], ind['associations']) == (1, 1, 1)
    assert indicateurs_tableau_bord(_compte('nu2'))['engins'] == 0
    jeu['association'].users.add(visiteur)
    Membre.objects.filter(pk=jeu['membre'].pk).update(is_validate3=False)
    assert indicateurs_tableau_bord(visiteur)['associations'] == 1  # l'association du compte reste comptée
    assert indicateurs_tableau_bord(visiteur)['engins'] == 0
