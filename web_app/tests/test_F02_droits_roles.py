"""F-02 / § 4 : rôles et nominations : profil effectif, périmètres, matrice des droits (§ 4.3), validations, nominations."""
from datetime import date, timedelta

import pytest
from django.contrib.auth.models import Group
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.urls import reverse
from django.utils import timezone

from compte import roles
from compte.models import Compte, JournalAction, Nomination
from compte.services import droits, droits_herites
from compte.services.nominations import creer_nomination, synchroniser_groupe, terminer_nomination, valider_coherence
from coptapp.models import Antenne, AssociationMembre, Membre, Province, Ville
from tests.test_plan_url import hachage_rapide, jeu  # noqa: F401

D = droits


@pytest.fixture
def monde(jeu):
    """Deux coordinations (P : celle du jeu, Q), une antenne chacune, un membre saisi par l'agent dans chaque."""
    P, Q = jeu['province'], Province.objects.create(nom='Quest', sigle='QU', code='QU')
    Antenne.objects.filter(pk=jeu['antenne'].pk).update(coordination=P)
    antenne_p = Antenne.objects.get(pk=jeu['antenne'].pk)
    ville_q = Ville.objects.create(nom='Ville Q', province=Q)
    antenne_q = Antenne.objects.create(nom='Antenne Q', coordination=Q, ville_origine=ville_q)
    agent = Compte.objects.create_user('agent-at', password='x')
    m = jeu['membre']
    Membre.objects.filter(pk=m.pk).update(user=agent, province=P, antenne=antenne_p)
    m.refresh_from_db()
    n = Membre.objects.create(nom='Membre Q', province=Q, antenne=antenne_q, ville=ville_q, is_validate2=True, is_validate3=True)
    nonvalide_q = Membre.objects.create(nom='Saisi Q', province=Q, antenne=antenne_q, ville=ville_q)
    return {**jeu, 'P': P, 'Q': Q, 'antenne_p': antenne_p, 'antenne_q': antenne_q, 'ville_q': ville_q, 'agent': agent,
            'M': m, 'N': n, 'N2': nonvalide_q}


def _compte(nom, **kw):
    return Compte.objects.create_user(nom, password='x', **kw)


def _nommer(monde, role, **perimetre):
    compte = _compte(f'c-{role.lower()}-{Compte.objects.count()}')
    creer_nomination(monde['compte'], compte, role, **perimetre)
    return Compte.objects.get(pk=compte.pk)


@pytest.fixture
def acteurs_roles(monde):
    return {
        'PR': _nommer(monde, roles.PR), 'VN': _nommer(monde, roles.VN),
        'VP': _nommer(monde, roles.VP, coordination=monde['P']),
        'VA': _nommer(monde, roles.VA, antenne=monde['antenne_p']),
        'AT': _nommer_agent(monde),
        'VI': _nommer(monde, roles.VI), 'ED': _nommer(monde, roles.ED),
    }


def _nommer_agent(monde):
    creer_nomination(monde['compte'], monde['agent'], roles.AT, antenne=monde['antenne_p'])
    return Compte.objects.get(pk=monde['agent'].pk)


# ---------------------------------------------------------------- interface identique à l'ancien module

def test_F02_interface_16_cles_et_renvoi_de_l_ancien_module(monde):
    assert len(D.CLES_DROITS) == 16 and set(D.CLES_DROITS) == set(droits_herites.droits_membre(monde['compte']).keys())
    for compte in (monde['compte'], _compte('sans')):
        assert set(D.droits_membre(compte, monde['M']).keys()) == set(D.CLES_DROITS)
        assert set(D.droits_membre(compte).keys()) == set(D.CLES_DROITS)
    from coptapp.services import droits_provisoires as ancien
    for nom in ('droits_membre', 'membres_du_perimetre', 'etapes_a_valider', 'membre_pour', 'cible_rattachable', 'voit_tout'):
        assert getattr(ancien, nom) is getattr(D, nom)


# ---------------------------------------------------------------- profil effectif

def test_F02_profil_su_nomination_herite_et_fiche(monde, settings):
    assert D.profil_de(monde['compte']).mode == 'su' and D.role_de(monde['compte']) == 'SU'
    sans = _compte('sans-nomination', privilege1=True)
    assert D.profil_de(sans).mode == 'herite' and D.role_de(sans) == ''
    va = _nommer(monde, roles.VA, antenne=monde['antenne_p'])
    assert D.profil_de(va).mode == 'nomination' and D.role_de(va) == 'VA'
    settings.FENAMO_DROITS_HERITES = False
    autre = _compte('autre-sans-nomination', privilege5=True)
    assert D.profil_de(autre).mode == 'fiche'
    assert D.profil_de(monde['compte']).mode == 'su'  # le SU ne dépend jamais du réglage
    assert D.profil_de(va).mode == 'nomination'


def test_F02_compte_sans_nomination_et_droits_herites_coupes_ne_voit_que_sa_fiche(monde, settings):
    settings.FENAMO_DROITS_HERITES = False
    compte = _compte('fiche-seule', privilege5=True, membreId=monde['M'].id)
    assert set(D.membres_du_perimetre(compte).values_list('pk', flat=True)) == {monde['M'].id}
    assert not any(D.droits_membre(compte, monde['M']).values()) and not any(D.droits_membre(compte).values())
    assert not D.voit_tout(compte) and not D.est_editeur(compte) and not D.peut_ecrire_referentiel(compte)
    assert not D.associations_du_compte(compte).exists()
    sans_fiche = _compte('rien', privilege5=True)
    assert D.membres_du_perimetre(sans_fiche).count() == 0


def test_F02_droits_herites_inchanges_pour_un_compte_sans_nomination(monde):
    for privileges in ({'privilege1': True}, {'privilege2': True}, {'privilege3': True}, {'privilege4': True}, {'privilege5': True}, {}):
        compte = _compte(f'h{len(privileges)}{list(privileges)}', **privileges)
        for membre in (monde['M'], monde['N']):
            assert D.droits_membre(compte, membre) == droits_herites.droits_membre(compte, membre)
        assert set(D.membres_du_perimetre(compte)) == set(droits_herites.membres_du_perimetre(compte))


def test_F02_nomination_echue_reste_valable_tant_qu_elle_n_est_pas_terminee(monde):
    compte = _compte('echue')
    n = creer_nomination(monde['compte'], compte, roles.VA, antenne=monde['antenne_p'], debut=date(2020, 1, 1), fin=date(2023, 1, 1))
    assert n.est_echue() and D.profil_de(compte).mode == 'nomination' and D.role_de(compte) == 'VA'
    terminer_nomination(monde['compte'], n, 'Mandat clos')
    compte = Compte.objects.get(pk=compte.pk)
    assert D.profil_de(compte).mode == 'herite'  # sans nomination : retour aux droits hérités (réglage par défaut)


def test_F02_nomination_pas_encore_commencee_ou_inactive_ignoree(monde):
    futur = _compte('futur')
    Nomination.objects.create(compte=futur, role='VA', antenne=monde['antenne_p'], debut=timezone.localdate() + timedelta(days=5))
    assert D.profil_de(futur).mode == 'herite'
    ancien = _compte('ancien')
    Nomination.objects.create(compte=ancien, role='VA', antenne=monde['antenne_p'], active=False)
    assert D.profil_de(ancien).mode == 'herite'


def test_F02_aucune_nomination_automatique(monde):
    assert not Nomination.objects.exists()
    D.profil_de(monde['compte'])
    assert not Nomination.objects.exists()


def test_F02_le_profil_est_memorise_puis_efface_a_la_nomination(monde):
    compte = _compte('memo')
    assert D.profil_de(compte).mode == 'herite'
    creer_nomination(monde['compte'], compte, roles.VA, antenne=monde['antenne_p'])  # efface la mémoire de CET objet
    assert D.profil_de(compte).mode == 'nomination'


def test_F02_profil_sans_requete_supplementaire_une_fois_memorise(monde, django_assert_num_queries):
    va = _nommer(monde, roles.VA, antenne=monde['antenne_p'])
    D.profil_de(va)
    with django_assert_num_queries(0):
        D.profil_de(va)
        D.role_de(va)


# ---------------------------------------------------------------- périmètre des membres

def _ids(compte, **kw):
    return set(D.membres_du_perimetre(compte, **kw).values_list('pk', flat=True))


def test_F02_perimetre_membres_par_role(monde, acteurs_roles):
    M, N, N2 = monde['M'].id, monde['N'].id, monde['N2'].id
    tous = {M, N, N2} | set(Membre.objects.values_list('pk', flat=True))
    assert _ids(acteurs_roles['PR']) == tous == _ids(acteurs_roles['VN'])
    assert M in _ids(acteurs_roles['VP']) and N not in _ids(acteurs_roles['VP']) and N2 not in _ids(acteurs_roles['VP'])
    assert M in _ids(acteurs_roles['VA']) and N not in _ids(acteurs_roles['VA'])
    assert _ids(acteurs_roles['AT']) == {M}  # ses seules saisies
    assert _ids(acteurs_roles['ED']) == set()  # aucun membre
    # visiteur national : membres actifs seulement
    assert _ids(acteurs_roles['VI']) == set(Membre.objects.filter(is_validate3=True, is_delete=False).values_list('pk', flat=True))
    assert N in _ids(acteurs_roles['VI']) and N2 not in _ids(acteurs_roles['VI']) and M not in _ids(acteurs_roles['VI'])


def test_F02_perimetre_vp_dans_une_autre_coordination_et_visiteurs_locaux(monde):
    vp_q = _nommer(monde, roles.VP, coordination=monde['Q'])
    assert {monde['N'].id, monde['N2'].id} <= _ids(vp_q) and monde['M'].id not in _ids(vp_q)
    vi_q = _nommer(monde, roles.VI, coordination=monde['Q'])
    assert _ids(vi_q) == {monde['N'].id}  # actifs de la coordination Q seulement
    vi_antenne = _nommer(monde, roles.VI, antenne=monde['antenne_q'])
    assert _ids(vi_antenne) == {monde['N'].id}
    Membre.objects.filter(pk=monde['M'].pk).update(is_validate3=True)
    vi_p = _nommer(monde, roles.VI, antenne=monde['antenne_p'])
    assert _ids(vi_p) == {monde['M'].id}


def test_F02_perimetre_va_suit_la_ville_d_origine_de_l_antenne(monde):
    va = _nommer(monde, roles.VA, antenne=monde['antenne_q'])  # antenne issue de ville_q
    assert {monde['N'].id, monde['N2'].id} <= _ids(va)
    sans_antenne = Membre.objects.create(nom='Par la ville', ville=monde['ville_q'])  # rattaché à la ville d'origine seulement
    assert sans_antenne.id in _ids(va)  # membres rattachés à la ville d'origine ou à l'antenne


def test_F02_membres_supprimes_exclus_sauf_demande_et_propre_fiche_toujours_lisible(monde, acteurs_roles):
    Membre.objects.filter(pk=monde['M'].pk).update(is_delete=True)
    assert monde['M'].id not in _ids(acteurs_roles['VA']) and monde['M'].id in _ids(acteurs_roles['VA'], avec_supprimes=True)
    ed = acteurs_roles['ED']
    Compte.objects.filter(pk=ed.pk).update(membreId=monde['N'].id)
    ed = Compte.objects.get(pk=ed.pk)
    D.oublier = None
    assert _ids(ed) == {monde['N'].id}  # propre fiche


# ---------------------------------------------------------------- matrice des droits (§ 4.3) sur un membre « saisi »

VRAIS = {
    # rôle : clés vraies sur le membre M « saisi » (is_validate2 faux), dans la portée du rôle
    'PR': {'peut_creer_membre', 'peut_modifier', 'peut_valider', 'peut_demander_suppression', 'peut_voir_historique',
           'peut_ajouter_engin', 'peut_ajouter_famille', 'peut_modifier_engin', 'peut_supprimer_engin', 'peut_modifier_famille',
           'peut_supprimer_famille', 'peut_executer_suppression'},
    'VN': set(),  # rempli ci-dessous
    'VP': {'peut_creer_membre', 'peut_modifier', 'peut_demander_suppression', 'peut_voir_historique', 'peut_ajouter_engin',
           'peut_ajouter_famille', 'peut_modifier_engin', 'peut_supprimer_engin', 'peut_modifier_famille', 'peut_supprimer_famille'},
    'VA': {'peut_creer_membre', 'peut_modifier', 'peut_valider', 'peut_demander_suppression', 'peut_voir_historique',
           'peut_ajouter_engin', 'peut_ajouter_famille', 'peut_modifier_engin', 'peut_supprimer_engin', 'peut_modifier_famille',
           'peut_supprimer_famille'},
    'AT': {'peut_creer_membre', 'peut_modifier', 'peut_demander_suppression', 'peut_demander_modification', 'peut_ajouter_engin',
           'peut_ajouter_famille', 'peut_modifier_engin', 'peut_supprimer_engin', 'peut_modifier_famille', 'peut_supprimer_famille'},
    'VI': set(), 'ED': set(),
}
VRAIS['VN'] = (VRAIS['PR'] - {'peut_valider'}) | set()  # VN ne pose pas la 1re validation : is_validate2 manque, sa étape est la 3e


def _vrais(d):
    return {cle for cle, v in d.items() if v}


@pytest.mark.parametrize('role', ['PR', 'VN', 'VP', 'VA', 'AT'])
def test_F02_matrice_droits_sur_un_membre_saisi(monde, acteurs_roles, role):
    assert _vrais(D.droits_membre(acteurs_roles[role], monde['M'])) == VRAIS[role], role


@pytest.mark.parametrize('role', ['VI', 'ED'])
def test_F02_visiteur_et_editeur_n_ont_aucun_droit_sur_un_membre(monde, acteurs_roles, role):
    Membre.objects.filter(pk=monde['M'].pk).update(is_validate2=True, is_validate3=True)
    membre = Membre.objects.get(pk=monde['M'].pk)
    assert _vrais(D.droits_membre(acteurs_roles[role], membre)) == set()
    assert _vrais(D.droits_membre(acteurs_roles[role])) == set()


def test_F02_agent_perd_la_modification_apres_la_premiere_validation(monde, acteurs_roles):
    Membre.objects.filter(pk=monde['M'].pk).update(is_validate2=True)
    membre = Membre.objects.get(pk=monde['M'].pk)
    droits = D.droits_membre(acteurs_roles['AT'], membre)
    for cle in ('peut_modifier', 'peut_modifier_engin', 'peut_supprimer_engin', 'peut_modifier_famille', 'peut_supprimer_famille'):
        assert not droits[cle], cle
    assert droits['peut_demander_modification'] and droits['peut_ajouter_engin'] and droits['peut_ajouter_famille']
    # les rôles supérieurs gardent la main
    for role in ('PR', 'VN', 'VP', 'VA'):
        assert D.droits_membre(acteurs_roles[role], membre)['peut_modifier'], role


def test_F02_agent_ne_gere_pas_les_membres_des_autres(monde, acteurs_roles):
    assert D.droits_membre(acteurs_roles['AT'], monde['N2'])['peut_modifier'] is False
    assert monde['N2'].id not in _ids(acteurs_roles['AT'])


def test_F02_hors_portee_aucun_droit_d_ecriture(monde, acteurs_roles):
    for role in ('VP', 'VA'):
        droits = D.droits_membre(acteurs_roles[role], monde['N'])
        assert not droits['peut_modifier'] and not droits['peut_valider'] and not droits['peut_demander_suppression'], role


def test_F02_attribution_des_privileges_reservee_au_su(monde, acteurs_roles):
    for role, compte in acteurs_roles.items():
        assert D.droits_membre(compte, monde['M'])['peut_attribuer_privileges'] is False, role
    assert D.droits_membre(monde['compte'], monde['M'])['peut_attribuer_privileges'] is True


def test_F02_historique_pour_va_vp_vn_pr_seulement(monde, acteurs_roles):
    voient = {r for r, c in acteurs_roles.items() if D.droits_membre(c, monde['M'])['peut_voir_historique']}
    assert voient == {'PR', 'VN', 'VP', 'VA'}


# ---------------------------------------------------------------- validations

def test_F02_va_pose_is_validate2_vn_pose_is_validate3(monde, acteurs_roles):
    membre = Membre.objects.get(pk=monde['M'].pk)
    assert D.etapes_a_valider(acteurs_roles['VA'], membre) == ['is_validate2']
    assert D.etapes_a_valider(acteurs_roles['VN'], membre) == []  # l'étape précédente est exigée
    Membre.objects.filter(pk=membre.pk).update(is_validate2=True)
    membre = Membre.objects.get(pk=membre.pk)
    assert D.etapes_a_valider(acteurs_roles['VN'], membre) == ['is_validate3']
    assert D.etapes_a_valider(acteurs_roles['VA'], membre) == []  # déjà posée : idempotent
    Membre.objects.filter(pk=membre.pk).update(is_validate3=True)
    membre = Membre.objects.get(pk=membre.pk)
    assert all(D.etapes_a_valider(c, membre) == [] for c in acteurs_roles.values())


def test_F02_pr_pose_toutes_les_etapes_d_un_coup(monde, acteurs_roles):
    membre = Membre.objects.get(pk=monde['M'].pk)
    assert D.etapes_a_valider(acteurs_roles['PR'], membre) == ['is_validate2', 'is_validate3']


def test_F02_vp_sans_etape_propre_pour_l_instant_point_d_extension_documente(monde, acteurs_roles):
    for etat in ({}, {'is_validate2': True}):
        Membre.objects.filter(pk=monde['M'].pk).update(**etat)
        assert D.etapes_a_valider(acteurs_roles['VP'], Membre.objects.get(pk=monde['M'].pk)) == []
    assert D.ETAPES_PAR_ROLE[roles.VP] is None and 'province' in D.__doc__.lower()


@pytest.mark.parametrize('role', ['VI', 'ED', 'AT'])
def test_F02_visiteur_editeur_et_agent_ne_valident_jamais(monde, acteurs_roles, role):
    assert D.etapes_a_valider(acteurs_roles[role], Membre.objects.get(pk=monde['M'].pk)) == []


def test_F02_personne_ne_valide_ses_propres_saisies_ni_sa_fiche_sauf_le_su(monde):
    va = _nommer(monde, roles.VA, antenne=monde['antenne_p'])
    Membre.objects.filter(pk=monde['M'].pk).update(user=va)
    assert D.etapes_a_valider(va, Membre.objects.get(pk=monde['M'].pk)) == []  # sa saisie
    Compte.objects.filter(pk=va.pk).update(membreId=monde['M'].id)
    Membre.objects.filter(pk=monde['M'].pk).update(user=None)
    va = Compte.objects.get(pk=va.pk)
    assert D.etapes_a_valider(va, Membre.objects.get(pk=monde['M'].pk)) == []  # sa propre fiche
    pr = _nommer(monde, roles.PR)
    Membre.objects.filter(pk=monde['M'].pk).update(user=pr)
    assert D.etapes_a_valider(pr, Membre.objects.get(pk=monde['M'].pk)) == []  # même le président
    # le SU garde l'exception (décision de la FENAMO) : sa propre fiche et ses saisies restent validables
    su = monde['compte']
    assert su.membreId == monde['M'].id
    Membre.objects.filter(pk=monde['M'].pk).update(user=su, is_validate2=False, is_validate3=False)
    assert D.etapes_a_valider(su, Membre.objects.get(pk=monde['M'].pk)) == ['is_validate2', 'is_validate3']


def test_F02_membre_supprime_non_validable_et_sans_droits_d_ecriture(monde, acteurs_roles):
    Membre.objects.filter(pk=monde['M'].pk).update(is_delete=True)
    membre = Membre.objects.get(pk=monde['M'].pk)
    for role in ('PR', 'VN', 'VP', 'VA', 'AT'):
        droits = D.droits_membre(acteurs_roles[role], membre)
        assert not any(droits[c] for c in ('peut_modifier', 'peut_valider', 'peut_ajouter_engin', 'peut_modifier_famille')), role
    assert D.droits_membre(acteurs_roles['PR'], membre)['peut_restaurer'] and D.droits_membre(acteurs_roles['VN'], membre)['peut_restaurer']
    assert not D.droits_membre(acteurs_roles['VA'], membre)['peut_restaurer']


# ---------------------------------------------------------------- suppression

def test_F02_suppression_demande_par_les_agents_et_validateurs_executee_par_vn_et_pr(monde, acteurs_roles):
    for role, demande, execute in (('AT', True, False), ('VA', True, False), ('VP', True, False), ('VN', True, True),
                                   ('PR', True, True), ('VI', False, False), ('ED', False, False)):
        d = D.droits_membre(acteurs_roles[role], monde['M'])
        assert (d['peut_demander_suppression'], d['peut_executer_suppression']) == (demande, execute), role


def test_F02_annulation_de_la_demande_par_son_auteur_ou_qui_execute(monde, acteurs_roles):
    Membre.objects.filter(pk=monde['M'].pk).update(suppression_demandee=True, suppression_demandee_par=acteurs_roles['AT'])
    membre = Membre.objects.get(pk=monde['M'].pk)
    assert D.droits_membre(acteurs_roles['AT'], membre)['peut_annuler_demande_suppression']  # son auteur
    assert D.droits_membre(acteurs_roles['VN'], membre)['peut_annuler_demande_suppression']  # qui exécute
    assert not D.droits_membre(acteurs_roles['VA'], membre)['peut_annuler_demande_suppression']  # un tiers


# ---------------------------------------------------------------- rattachement, associations, géographie

def test_F02_cible_rattachable_par_role(monde, acteurs_roles):
    ant_p, ant_q = monde['antenne_p'], monde['antenne_q']
    assert D.cible_rattachable(acteurs_roles['PR'], 'antenne', ant_q) and D.cible_rattachable(acteurs_roles['VN'], 'ville', monde['ville_q'])
    assert D.cible_rattachable(acteurs_roles['VP'], 'antenne', ant_p) and not D.cible_rattachable(acteurs_roles['VP'], 'antenne', ant_q)
    assert D.cible_rattachable(acteurs_roles['VP'], 'ville', monde['ville']) and not D.cible_rattachable(acteurs_roles['VP'], 'ville', monde['ville_q'])
    assert D.cible_rattachable(acteurs_roles['VP'], 'structure', monde['association'])
    assert D.cible_rattachable(acteurs_roles['VA'], 'antenne', ant_p) and not D.cible_rattachable(acteurs_roles['VA'], 'antenne', ant_q)
    for role in ('AT', 'VI', 'ED'):
        assert not D.cible_rattachable(acteurs_roles[role], 'antenne', ant_p), role
    assert not D.cible_rattachable(acteurs_roles['PR'], 'antenne', None)


def test_F02_associations_et_geographie_par_role(monde, acteurs_roles):
    assert D.associations_du_compte(acteurs_roles['PR']).count() == AssociationMembre.objects.count()
    assert monde['association'] in D.associations_du_compte(acteurs_roles['VP'])
    autre = AssociationMembre.objects.create(nom='Assoc Q', province=monde['Q'], num_justice='F-Q')
    assert autre not in D.associations_du_compte(acteurs_roles['VP']) and autre in D.associations_du_compte(acteurs_roles['VN'])
    assert not D.associations_du_compte(acteurs_roles['ED']).exists()
    assert set(D.provinces_du_perimetre(acteurs_roles['VP'])) == {monde['P']}
    assert set(D.provinces_du_perimetre(acteurs_roles['VN'])) == set(Province.objects.all())
    assert monde['antenne_p'] in D.antennes_du_perimetre(acteurs_roles['VA']) and monde['antenne_q'] not in D.antennes_du_perimetre(acteurs_roles['VA'])
    assert monde['antenne_q'] in D.antennes_du_perimetre(acteurs_roles['PR'])
    assert monde['ville'] in D.villes_du_perimetre(acteurs_roles['VP']) and monde['ville_q'] not in D.villes_du_perimetre(acteurs_roles['VP'])
    assert set(D.provinces_du_perimetre(acteurs_roles['ED'])) == set()


def test_F02_engins_visibles_suivent_les_membres_du_perimetre(monde, acteurs_roles):
    from coptapp.models import Moto
    moto_q = Moto.objects.create(proprietaire=monde['N'], province=monde['Q'], abonnement=date(2030, 1, 1), numero='001QU')
    assert moto_q in D.engins_visibles(acteurs_roles['VN']) and moto_q not in D.engins_visibles(acteurs_roles['VA'])
    assert monde['moto'] in D.engins_visibles(acteurs_roles['VA'])


# ---------------------------------------------------------------- accès par identifiant (vues)

def test_F02_acces_par_identifiant_404_hors_perimetre_403_sans_droit(monde, acteurs_roles):
    from django.http import Http404
    va, vi = acteurs_roles['VA'], acteurs_roles['VI']
    assert D.membre_pour(va, monde['M'].id).pk == monde['M'].id
    with pytest.raises(Http404):
        D.membre_pour(va, monde['N'].id)
    Membre.objects.filter(pk=monde['N'].pk).update(is_validate3=True)
    with pytest.raises(Exception) as erreur:
        D.membre_pour(vi, monde['N'].id, 'peut_modifier')
    assert type(erreur.value).__name__ == 'PermissionDenied'


def test_F02_vues_avec_roles(client, monde, acteurs_roles):
    url = lambda m: reverse('membre-view', kwargs={'id': m.id})  # noqa: E731
    client.force_login(acteurs_roles['VA'])
    assert client.get(url(monde['M'])).status_code == 200 and client.get(url(monde['N'])).status_code == 404
    donnees = {'modifier': '1', 'nom': 'Modifié', 'date': '01-01-1990'}
    assert client.post(url(monde['M']), donnees).status_code == 200
    client.force_login(acteurs_roles['VI'])
    Membre.objects.filter(pk=monde['N'].pk).update(is_validate3=True)
    assert client.get(url(monde['N'])).status_code == 200
    assert client.post(url(monde['N']), donnees).status_code == 403
    client.force_login(acteurs_roles['ED'])
    assert client.get(url(monde['N'])).status_code == 404
    client.force_login(acteurs_roles['AT'])
    assert client.get(url(monde['M'])).status_code == 200 and client.get(url(monde['N2'])).status_code == 404
    client.force_login(acteurs_roles['VP'])
    assert client.get(reverse('validate', kwargs={'id': monde['M'].id})).status_code == 405
    r = client.post(reverse('validate', kwargs={'id': monde['M'].id}))
    assert r.status_code in (302, 403)  # le VP n'a pas d'étape propre : rien n'est posé
    assert not Membre.objects.get(pk=monde['M'].pk).is_validate2


def test_F02_liste_des_membres_selon_le_role(client, monde, acteurs_roles):
    client.force_login(acteurs_roles['VP'])
    corps = client.get(reverse('liste-membre')).content.decode()
    assert 'Membre Fictif' in corps and 'Membre Q' not in corps
    client.force_login(acteurs_roles['VN'])
    corps = client.get(reverse('liste-membre')).content.decode()
    assert 'Membre Fictif' in corps and 'Membre Q' in corps


# ---------------------------------------------------------------- éditeur, référentiel, menu

def test_F02_editeur_et_ecriture_du_referentiel_par_role(monde, acteurs_roles):
    assert D.est_editeur(monde['compte']) and D.est_editeur(acteurs_roles['ED'])
    assert not any(D.est_editeur(acteurs_roles[r]) for r in ('PR', 'VN', 'VP', 'VA', 'AT', 'VI'))
    assert D.peut_ecrire_referentiel(monde['compte']) and D.peut_ecrire_referentiel(acteurs_roles['PR']) and D.peut_ecrire_referentiel(acteurs_roles['VN'])
    assert not any(D.peut_ecrire_referentiel(acteurs_roles[r]) for r in ('VP', 'VA', 'AT', 'VI', 'ED'))
    herite = _compte('herite-editeur', editor=True, privilege5=True)
    assert D.est_editeur(herite) and D.peut_ecrire_referentiel(herite)  # comportement hérité inchangé
    assert not D.est_editeur(_compte('herite-visiteur', editor=True, privilege4=True))


def test_F02_permissions_et_perimetre_delegues_aux_roles(client, monde, acteurs_roles):
    from compte import permissions
    from compte.services.perimetre import notifications_du_perimetre, role_et_perimetre
    assert permissions.est_editeur(acteurs_roles['ED']) and permissions.peut_ecrire_referentiel(acteurs_roles['VN'])
    assert not permissions.peut_ecrire_referentiel(acteurs_roles['VA'])
    assert [str(x) for x in role_et_perimetre(acteurs_roles['VA'])] == ["Validateur d'antenne", monde['antenne_p'].nom]
    assert [str(x) for x in role_et_perimetre(acteurs_roles['VP'])] == ['Validateur provincial', monde['P'].nom]
    assert [str(x) for x in role_et_perimetre(acteurs_roles['PR'])] == ['Président', 'National']
    from coptapp.models import Notification
    Notification.objects.create(user=acteurs_roles['VA'], titre='a')
    Notification.objects.create(user=acteurs_roles['VN'], titre='b')
    assert notifications_du_perimetre(acteurs_roles['PR']).count() == 2 and notifications_du_perimetre(acteurs_roles['VN']).count() == 1
    client.force_login(acteurs_roles['ED'])
    assert client.get(reverse('site')).status_code == 200  # l'éditeur ouvre le contenu du site
    client.force_login(acteurs_roles['VA'])
    assert client.get(reverse('site')).status_code == 403 and client.get(reverse('add-province')).status_code == 403
    client.force_login(acteurs_roles['VN'])
    assert client.get(reverse('add-province')).status_code == 200


def test_F02_droits_du_menu_et_processeur_de_contexte(client, monde, acteurs_roles):
    menu = D.droits_menu(acteurs_roles['ED'])
    assert menu['role'] == 'ED' and not menu['voit_membres'] and menu['est_editeur'] and not menu['est_su']
    assert D.droits_menu(acteurs_roles['VN'])['peut_ecrire_referentiel'] and D.droits_menu(monde['compte'])['voit_journal']
    assert D.droits_menu(acteurs_roles['VA'])['role_libelle'] == "Validateur d'antenne" and not D.droits_menu(acteurs_roles['VA'])['voit_journal']
    client.force_login(acteurs_roles['VA'])
    r = client.get(reverse('tableau-bord'))
    assert r.context['fn_droits']['role'] == 'VA' and r.context['fn_droits']['voit_membres']
    fragment = client.get(reverse('liste-membre'), HTTP_HX_REQUEST='true')
    assert 'fn_droits' not in fragment.context  # aucune requête pour un fragment
    from django.test import Client
    assert 'fn_droits' not in (Client().get('/connexion/').context or {})  # anonyme : rien


# ---------------------------------------------------------------- nominations (service, modèle, admin, groupes)

COHERENTES = [
    ('SU', {}), ('PR', {}), ('VN', {}), ('ED', {}), ('VP', {'coordination': 1}), ('VA', {'antenne': 1}), ('AT', {'antenne': 1}),
    ('AT', {'antenne': 1, 'association': 1}), ('VI', {}), ('VI', {'coordination': 1}), ('VI', {'antenne': 1}),
]
INCOHERENTES = [
    ('PR', {'coordination': 1}), ('VN', {'antenne': 1}), ('SU', {'association': 1}), ('ED', {'coordination': 1}),
    ('VP', {}), ('VP', {'coordination': 1, 'antenne': 1}), ('VA', {}), ('VA', {'antenne': 1, 'coordination': 1}),
    ('VA', {'antenne': 1, 'association': 1}), ('AT', {}), ('AT', {'antenne': 1, 'coordination': 1}),
    ('VI', {'coordination': 1, 'antenne': 1}), ('VI', {'association': 1}), ('XX', {}),
]


@pytest.mark.parametrize('role, perimetre', COHERENTES)
def test_F02_coherence_role_perimetre_valide(role, perimetre):
    valider_coherence(role, perimetre.get('coordination'), perimetre.get('antenne'), perimetre.get('association'))


@pytest.mark.parametrize('role, perimetre', INCOHERENTES)
def test_F02_coherence_role_perimetre_refusee(role, perimetre):
    with pytest.raises(ValidationError):
        valider_coherence(role, perimetre.get('coordination'), perimetre.get('antenne'), perimetre.get('association'))


def test_F02_le_modele_controle_la_coherence(monde):
    with pytest.raises(ValidationError):
        Nomination(compte=_compte('x'), role='VP').full_clean()
    Nomination(compte=_compte('y'), role='VP', coordination=monde['P']).full_clean()


def test_F02_durees_de_mandat_de_la_charte(monde):
    assert roles.DUREES_MANDAT_ANS == {'antenne': 3, 'coordination': 4, 'national': 5}
    debut = date(2026, 3, 1)
    for role, kw, ans in ((roles.VA, {'antenne': monde['antenne_p']}, 3), (roles.AT, {'antenne': monde['antenne_p']}, 3),
                          (roles.VP, {'coordination': monde['P']}, 4), (roles.PR, {}, 5), (roles.VN, {}, 5)):
        n = creer_nomination(monde['compte'], _compte(f'd-{role}'), role, debut=debut, **kw)
        assert n.duree_mandat_ans == ans and n.fin == date(2026 + ans, 3, 1), role
    for role in (roles.VI, roles.ED):
        n = creer_nomination(monde['compte'], _compte(f'd-{role}'), role, debut=debut)
        assert n.fin is None and n.duree_mandat_ans is None
    n = creer_nomination(monde['compte'], _compte('bissextile'), roles.PR, debut=date(2024, 2, 29))
    assert n.fin == date(2029, 3, 1)
    n = creer_nomination(monde['compte'], _compte('explicite'), roles.VA, antenne=monde['antenne_p'], debut=debut, fin=date(2027, 1, 1))
    assert n.fin == date(2027, 1, 1)


def test_F02_une_seule_nomination_active_par_compte(monde):
    compte = _compte('unique')
    creer_nomination(monde['compte'], compte, roles.PR)
    with pytest.raises(ValidationError):
        creer_nomination(monde['compte'], compte, roles.VN)
    with pytest.raises(IntegrityError), transaction.atomic():  # la base le garantit aussi (SQLite)
        Nomination.objects.create(compte=compte, role='VN')
    n = Nomination.objects.get(compte=compte, active=True)
    terminer_nomination(monde['compte'], n, 'Remplacé')
    creer_nomination(monde['compte'], compte, roles.VN)  # après la fin : une nouvelle est possible
    assert Nomination.objects.filter(compte=compte).count() == 2 and Nomination.objects.filter(compte=compte, active=True).count() == 1


def test_F02_fin_de_nomination_conservee_et_journalisee(monde):
    compte = _compte('fin')
    n = creer_nomination(monde['compte'], compte, roles.VA, antenne=monde['antenne_p'])
    terminer_nomination(monde['compte'], n, 'Démission')
    n.refresh_from_db()
    assert not n.active and n.terminee_par == monde['compte'] and n.terminee_le and n.motif_fin == 'Démission'
    assert JournalAction.objects.filter(action=JournalAction.Action.NOMINATION, objet_id=compte.id).exists()
    fin = JournalAction.objects.get(action=JournalAction.Action.FIN_NOMINATION)
    assert fin.motif == 'Démission' and fin.auteur == monde['compte']
    assert terminer_nomination(monde['compte'], n).active is False  # idempotent
    assert JournalAction.objects.filter(action=JournalAction.Action.FIN_NOMINATION).count() == 1


def test_F02_huit_groupes_miroirs_et_synchronisation(monde):
    assert set(Group.objects.filter(name__startswith='role_').values_list('name', flat=True)) == {f'role_{r}' for r in roles.ROLES}
    compte = _compte('groupes')
    n = creer_nomination(monde['compte'], compte, roles.VA, antenne=monde['antenne_p'])
    assert list(compte.groups.values_list('name', flat=True)) == ['role_VA']
    terminer_nomination(monde['compte'], n)
    assert compte.groups.count() == 0
    autre = Group.objects.create(name='groupe-sans-rapport')
    compte.groups.add(autre)
    creer_nomination(monde['compte'], compte, roles.PR)
    synchroniser_groupe(compte)
    assert set(compte.groups.values_list('name', flat=True)) == {'groupe-sans-rapport', 'role_PR'}  # les autres groupes sont intacts


def test_F02_admin_des_nominations_reserve_au_su(client, monde):
    from django.contrib.admin.sites import site
    admin = site._registry[Nomination]
    class R:  # noqa: E701
        def __init__(self, user):
            self.user = user
    simple = _compte('staff', is_staff=True)
    assert admin.has_module_permission(R(monde['compte'])) and admin.has_add_permission(R(monde['compte']))
    assert not admin.has_module_permission(R(simple)) and not admin.has_view_permission(R(simple)) and not admin.has_change_permission(R(simple))
    assert not admin.has_delete_permission(R(monde['compte']))  # une nomination se conserve
    client.force_login(monde['compte'])
    assert client.get('/gestion-technique/compte/nomination/').status_code == 200


def test_F02_roles_constantes_et_libelles():
    assert roles.ROLES == ('SU', 'PR', 'VN', 'VP', 'VA', 'AT', 'VI', 'ED') and set(roles.LIBELLES) == set(roles.ROLES)
    assert roles.nom_du_groupe('PR') == 'role_PR' and roles.duree_par_defaut('VI') is None
    assert roles.RANG['SU'] < roles.RANG['PR'] < roles.RANG['VN'] < roles.RANG['VP'] < roles.RANG['VA'] < roles.RANG['AT']
    assert {c for c, _ in Nomination.Role.choices} == set(roles.ROLES)
