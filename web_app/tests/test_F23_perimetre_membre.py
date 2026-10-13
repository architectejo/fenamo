"""F-21, F-23, F-25 : fiche, modification, validation et demande de suppression d'un membre sous contrôle de périmètre et de droit.

Règle provisoire (privilèges hérités, voir coptapp/services/droits_provisoires.py) : 404 hors périmètre, 403 si
l'action est interdite.
"""
from datetime import date

import pytest
from django.urls import reverse

from compte.models import Compte, JournalAction
from coptapp.models import AssociationMembre, Membre
from tests.test_plan_url import hachage_rapide, jeu  # noqa: F401

CHAMPS = ('nom about genre titre fonction comite nation brevet etat_civil epouse adresse telephone mail categorie '
          'permis qualite autre_asbl numero_carte_d_electeur numero_carte_de_membre nom_pere nom_mere village '
          'chefferie territoire province_origine').split()


def _compte(nom, **kw):
    return Compte.objects.create_user(nom, password='x', **kw)


def _donnees_modifier(nom='Nom modifié'):
    donnees = {c: 'x' for c in CHAMPS}
    donnees.update({'nom': nom, 'date': '02-03-1991', 'modifier': '1', 'mail': 'a@example.invalid'})
    return donnees


def _membre(jeu, nom, **kw):
    base = dict(province=jeu['province'], antenne=jeu['antenne'], structure=jeu['association'], date_naissance=date(1990, 1, 1))
    base.update(kw)
    return Membre.objects.create(nom=nom, **base)


def url_fiche(m):
    return reverse('membre-view', kwargs={'id': m.id})


def url_valider(m):
    return reverse('validate', kwargs={'id': m.id})


# ------------------------------------------------------------------ lecture (GET)

def test_F23_anonyme_redirige(client, jeu):
    assert client.get(url_fiche(jeu['membre'])).status_code == 302


def test_F23_connecte_sans_privilege_ne_voit_pas_une_fiche_quelconque(client, jeu):
    client.force_login(_compte('nu'))
    assert client.get(url_fiche(jeu['membre'])).status_code == 404


def test_F23_connecte_sans_privilege_voit_sa_propre_fiche(client, jeu):
    moi = _compte('moi', membreId=jeu['membre'].id)
    client.force_login(moi)
    r = client.get(url_fiche(jeu['membre']))
    assert r.status_code == 200 and not r.context['peut_modifier'] and not r.context['peut_valider']


def test_F23_agent_ne_voit_que_ses_saisies(client, jeu):
    agent = _compte('agent', privilege1=True)
    sien = _membre(jeu, 'Saisi par agent', user=agent)
    client.force_login(agent)
    assert client.get(url_fiche(sien)).status_code == 200
    assert client.get(url_fiche(jeu['membre'])).status_code == 404


def test_F23_visiteur_ne_voit_que_les_actifs(client, jeu):
    actif = _membre(jeu, 'Actif', is_validate2=True, is_validate3=True)
    client.force_login(_compte('vis', privilege4=True))
    assert client.get(url_fiche(actif)).status_code == 200
    assert client.get(url_fiche(jeu['membre'])).status_code == 404


def test_F23_privilege3_voit_les_membres_valides_aux_deux_premieres_etapes(client, jeu):
    avance = _membre(jeu, 'Avancé', is_validate2=True)
    client.force_login(_compte('p3', privilege3=True))
    assert client.get(url_fiche(avance)).status_code == 200
    assert client.get(url_fiche(jeu['membre'])).status_code == 404


def test_F23_membre_inexistant_404(client, jeu):
    client.force_login(jeu['compte'])
    assert client.get(reverse('membre-view', kwargs={'id': 99999})).status_code == 404


def test_F23_membre_supprime_visible_des_seuls_roles_qui_peuvent_annuler(client, jeu):
    supprime = _membre(jeu, 'Supprimé', is_delete=True, is_validate2=True, is_validate3=True)
    client.force_login(jeu['compte'])
    assert client.get(url_fiche(supprime)).status_code == 200
    client.force_login(_compte('vis2', privilege4=True))
    assert client.get(url_fiche(supprime)).status_code == 404


def test_F23_contexte_de_la_fiche_porte_les_droits(client, jeu):
    client.force_login(jeu['compte'])
    c = client.get(url_fiche(jeu['membre'])).context
    assert c['peut_modifier'] and c['peut_valider'] and c['peut_attribuer_privileges'] and c['peut_voir_historique']
    assert c['droits']['peut_gerer_engins']


# ------------------------------------------------------------------ modification (POST modifier)

@pytest.mark.parametrize('privileges', [{}, {'privilege1': True}, {'privilege2': True}, {'privilege4': True},
                                        {'privilege4': True, 'privilege3': True}])
def test_F21_modifier_refuse_403(client, jeu, privileges):
    compte = _compte('refuse', membreId=jeu['membre'].id, **privileges)  # voit au moins sa fiche
    jeu['association'].users.add(compte)
    client.force_login(compte)
    r = client.post(url_fiche(jeu['membre']), _donnees_modifier())
    assert r.status_code == 403
    jeu['membre'].refresh_from_db()
    assert jeu['membre'].nom == 'Membre Fictif'


def test_F21_modifier_hors_perimetre_404(client, jeu):
    client.force_login(_compte('nu2'))
    assert client.post(url_fiche(jeu['membre']), _donnees_modifier()).status_code == 404
    jeu['membre'].refresh_from_db()
    assert jeu['membre'].nom == 'Membre Fictif'


def test_F21_modifier_privilege3_hors_de_son_association_403(client, jeu):
    autre = AssociationMembre.objects.create(nom='Autre', num_justice='F-77')
    p3 = _compte('p3x', privilege3=True)
    autre.users.add(p3)
    etranger = _membre(jeu, 'Chez nous', is_validate2=True)  # visible (étape 2 franchie) mais autre association
    client.force_login(p3)
    assert client.post(url_fiche(etranger), _donnees_modifier()).status_code == 403


def test_F21_modifier_privilege3_dans_son_association_autorise(client, jeu):
    p3 = _compte('p3y', privilege3=True)
    jeu['association'].users.add(p3)
    cible = _membre(jeu, 'À modifier', is_validate2=True)
    client.force_login(p3)
    r = client.post(url_fiche(cible), _donnees_modifier('Modifié par p3'))
    assert r.status_code == 200
    cible.refresh_from_db()
    assert cible.nom == 'Modifié par p3'


def test_F21_modifier_super_utilisateur_autorise(client, jeu):
    client.force_login(jeu['compte'])
    assert client.post(url_fiche(jeu['membre']), _donnees_modifier('Par le SU')).status_code == 200
    jeu['membre'].refresh_from_db()
    assert jeu['membre'].nom == 'Par le SU'


def test_F21_demande_de_modification_reservee_aux_agents_et_su(client, jeu):
    agent = _compte('agent3', privilege1=True)
    cible = _membre(jeu, 'Cible', user=agent)
    client.force_login(agent)
    assert client.post(url_fiche(cible), {'envoyer': '1', 'demande': 'Corriger'}).status_code == 200
    p2 = _compte('p2z', privilege2=True)
    client.force_login(p2)
    assert client.post(url_fiche(cible), {'envoyer': '1', 'demande': 'Corriger'}).status_code == 403


def test_F21_attribution_de_privileges_reservee_aux_su(client, jeu):
    p5 = _compte('p5z', privilege5=True)
    cible = jeu['membre']
    _compte('cible-compte', membreId=cible.id)
    client.force_login(p5)
    assert client.post(url_fiche(cible), {'privilege': '1', 'privilege5': 'on'}).status_code == 403


# ------------------------------------------------------------------ validation (POST valider)

def test_F23_valider_get_interdit(client, jeu):
    client.force_login(jeu['compte'])
    assert client.get(url_valider(jeu['membre'])).status_code == 405


def test_F23_valider_hors_perimetre_404(client, jeu):
    client.force_login(_compte('nu3'))
    assert client.post(url_valider(jeu['membre'])).status_code == 404
    jeu['membre'].refresh_from_db()
    assert not jeu['membre'].is_validate2


def test_F23_valider_refuse_sans_droit_403(client, jeu):
    actif = _membre(jeu, 'Actif', is_validate2=True, is_validate3=True)
    for nom, kw in (('vis3', {'privilege4': True}), ('vis4', {'privilege4': True, 'privilege2': True})):
        client.force_login(_compte(nom, **kw))
        assert client.post(url_valider(actif)).status_code == 403
    moi = _compte('moi2', membreId=jeu['membre'].id)
    client.force_login(moi)
    assert client.post(url_valider(jeu['membre'])).status_code == 403
    jeu['membre'].refresh_from_db()
    assert not jeu['membre'].is_validate2


def test_F23_valider_privilege2_puis_privilege3_et_journal(client, jeu):
    cible = jeu['membre']
    client.force_login(_compte('p2v', privilege2=True))
    client.post(url_valider(cible))
    cible.refresh_from_db()
    assert cible.is_validate2 and not cible.is_validate3
    client.force_login(_compte('p3v', privilege3=True))
    client.post(url_valider(cible))
    cible.refresh_from_db()
    assert cible.is_validate3
    lignes = JournalAction.objects.filter(action=JournalAction.Action.VALIDATION, objet_id=cible.id)
    assert lignes.count() == 2 and not JournalAction.objects.filter(action=JournalAction.Action.RENVOI).exists()


def test_F23_valider_est_idempotente_ne_devalide_jamais(client, jeu):
    cible = jeu['membre']
    client.force_login(jeu['compte'])
    for _ in range(3):
        assert client.post(url_valider(cible)).status_code == 302
    cible.refresh_from_db()
    assert cible.is_validate2 and cible.is_validate3
    assert JournalAction.objects.filter(action=JournalAction.Action.VALIDATION).count() == 1
    assert not JournalAction.objects.filter(action=JournalAction.Action.RENVOI).exists()
    client.force_login(_compte('p2w', privilege2=True))
    client.post(url_valider(cible))
    cible.refresh_from_db()
    assert cible.is_validate2 and cible.is_validate3


def test_F23_privilege3_ne_valide_pas_un_membre_non_visible(client, jeu):
    client.force_login(_compte('p3w', privilege3=True))
    assert client.post(url_valider(jeu['membre'])).status_code == 404


# ------------------------------------------------------------------ suppression logique

def test_F23_valider_exige_l_etape_precedente_et_pas_sa_propre_fiche(client, jeu):
    suivant = _membre(jeu, 'Suivant')
    p3 = _compte('p3s', privilege3=True)
    client.force_login(p3)
    # privilege3 ne voit que les membres déjà validés à l'étape 2 : l'étape précédente est donc exigée
    assert client.post(url_valider(suivant)).status_code == 404
    p23 = _compte('p23', privilege2=True, privilege3=True)
    client.force_login(p23)
    client.post(url_valider(suivant))
    suivant.refresh_from_db()
    assert suivant.is_validate2 and not suivant.is_validate3  # une seule étape par action
    client.post(url_valider(suivant))
    suivant.refresh_from_db()
    assert suivant.is_validate3
    # propre fiche et propres saisies
    propre = _membre(jeu, 'Ma fiche')
    saisie = _membre(jeu, 'Ma saisie', user=p23)
    p23.membreId = propre.id
    p23.save()
    client.force_login(p23)
    for membre in (propre, saisie):
        client.post(url_valider(membre))
        membre.refresh_from_db()
        assert not membre.is_validate2
    p5 = _compte('p5s', privilege5=True, membreId=propre.id)
    client.force_login(p5)
    client.post(url_valider(propre))
    propre.refresh_from_db()
    assert not propre.is_validate2
