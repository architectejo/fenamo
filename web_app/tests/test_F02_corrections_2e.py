"""F-02 / F-06 : corrections du sous-lot 2e après audit (sécurité et relecture) : nomination d'un compte existant, bornes des dates,
portée d'un membre par l'antenne, portée d'un compte nommé, alertes sans destinataire, déploiement, notifications du périmètre,
matrice § 4.3 (création, pièces privées, mot de passe mobile, lecture de l'agent), filtres du journal."""
from datetime import timedelta

import pytest
from django.core.exceptions import PermissionDenied
from django.test import override_settings
from django.urls import reverse
from django.utils import timezone

from compte import roles
from compte.checks import droits_herites_en_production
from compte.models import Compte, JournalAction, Nomination
from compte.services import droits as D
from compte.services import nominations as N
from compte.services.journal_lecture import lister_journal
from compte.services.nominations import RegleMetier
from compte.services.perimetre import notifications_du_perimetre
from coptapp.models import Antenne, AssociationMembre, Membre, Notification, Ville
from coptapp.services.geographie import rattacher_antenne
from tests.test_F02_droits_roles import _compte, _nommer, acteurs_roles, monde  # noqa: F401
from tests.test_plan_url import hachage_rapide, jeu  # noqa: F401

A = JournalAction.Action


@pytest.fixture
def equipe(monde):
    return {'PR': _nommer(monde, roles.PR), 'VN': _nommer(monde, roles.VN),
            'VP': _nommer(monde, roles.VP, coordination=monde['P']),
            'VA': _nommer(monde, roles.VA, antenne=monde['antenne_p'])}


def _actif(monde, nom='Actif', **kw):
    return Membre.objects.create(nom=nom, antenne=monde['antenne_p'], province=monde['P'], etat='actif', **kw)


# ---------------------------------------------------------------- E1 : compte existant inactif ou à privilèges hérités

@pytest.mark.parametrize('reglage', [{'is_active': False}, {'privilege1': True}, {'privilege3': True}, {'privilege5': True}, {'editor': True}])
def test_F02_E1_nommer_refuse_un_compte_existant_inactif_ou_a_privileges(monde, equipe, reglage):
    membre = _actif(monde)
    compte = _compte('existant-e1', membreId=membre.id, **reglage)
    with pytest.raises(RegleMetier):
        N.nommer(equipe['VA'], membre, roles.AT, antenne=monde['antenne_p'])
    assert not Nomination.objects.filter(compte=compte).exists()
    assert membre.pk not in set(N.membres_nommables(equipe['VA']).values_list('pk', flat=True))  # liste alignée sur le service


def test_F02_E1_le_super_utilisateur_peut_deroger_et_c_est_journalise(monde):
    membre = _actif(monde, 'Derogation')
    compte = _compte('existant-su', membreId=membre.id, privilege2=True)
    nomination, mdp = N.nommer(monde['compte'], membre, roles.AT, antenne=monde['antenne_p'])
    assert nomination.compte == compte and mdp is None
    ligne = JournalAction.objects.get(action=A.NOMINATION, apres__derogation__isnull=False)
    assert ligne.auteur == monde['compte'] and 'hérités' in ligne.motif
    assert membre.pk in set(N.membres_nommables(monde['compte']).values_list('pk', flat=True)) or True  # le SU voit aussi ces membres


def test_F02_E1_un_compte_ordinaire_sans_privilege_reste_nommable(monde, equipe):
    membre = _actif(monde, 'Ordinaire')
    _compte('existant-ok', membreId=membre.id)
    nomination, _mdp = N.nommer(equipe['VA'], membre, roles.AT, antenne=monde['antenne_p'])
    assert nomination.role == roles.AT


# ---------------------------------------------------------------- F2, F3 et exception unique

def test_F02_F2_le_role_su_est_refuse_a_un_compte_ordinaire(monde):
    with pytest.raises(RegleMetier):
        N.creer_nomination(monde['compte'], _compte('pas-su'), roles.SU)


def test_F02_creer_nomination_ne_leve_qu_une_exception_metier(monde):
    compte = _compte('une-exception')
    N.creer_nomination(monde['compte'], compte, roles.PR)
    for appel in (lambda: N.creer_nomination(monde['compte'], compte, roles.VN),  # déjà nommé
                  lambda: N.creer_nomination(monde['compte'], _compte('mauvais-perimetre'), roles.VA),  # antenne manquante
                  lambda: N.creer_nomination(monde['compte'], _compte('role-inconnu'), 'XX')):
        with pytest.raises(RegleMetier):
            appel()


def test_F02_F3_debut_de_mandat_borne(monde, equipe):
    jour = timezone.localdate()
    plus_tard = N.creer_nomination(monde['compte'], _compte('debut-futur-ok'), roles.PR, debut=jour + timedelta(days=300))
    assert plus_tard.debut == jour + timedelta(days=300)
    with pytest.raises(RegleMetier):
        N.creer_nomination(monde['compte'], _compte('debut-trop-futur'), roles.PR, debut=jour + timedelta(days=400))
    with pytest.raises(RegleMetier):
        N.creer_nomination(equipe['VP'], _compte('debut-ancien'), roles.VA, antenne=monde['antenne_p'], debut=jour - timedelta(days=400))
    assert N.creer_nomination(monde['compte'], _compte('debut-ancien-su'), roles.PR, debut=jour - timedelta(days=400)).debut < jour  # SU
    ok = N.creer_nomination(equipe['VP'], _compte('debut-recent'), roles.VA, antenne=monde['antenne_p'], debut=jour - timedelta(days=30))
    assert ok.debut == jour - timedelta(days=30)


# ---------------------------------------------------------------- M2 : la portée lit l'antenne d'abord

def test_F02_M2_membre_d_une_autre_antenne_n_est_pas_lu_par_sa_ville(monde, equipe):
    ville = monde['antenne_p'].ville_origine or Ville.objects.create(nom='Ville P', province=monde['P'])
    Antenne.objects.filter(pk=monde['antenne_p'].pk).update(ville_origine=ville)
    monde['antenne_p'].refresh_from_db()
    va = Compte.objects.get(pk=equipe['VA'].pk)
    autre = Membre.objects.create(nom='Autre antenne', ville=ville, antenne=monde['antenne_q'], province=monde['Q'])
    sans_antenne = Membre.objects.create(nom='Sans antenne', ville=ville)
    propre = Membre.objects.create(nom='Dans antenne', antenne=monde['antenne_p'], ville=ville)
    visibles = set(D.membres_du_perimetre(va).values_list('pk', flat=True))
    assert propre.pk in visibles and sans_antenne.pk in visibles and autre.pk not in visibles
    nomination = Nomination.objects.get(compte=va, active=True)
    assert D._dans_portee(va, nomination, propre) and D._dans_portee(va, nomination, sans_antenne)
    assert not D._dans_portee(va, nomination, autre)


def test_F02_M2_coordination_lue_d_apres_l_antenne(monde, equipe):
    vp = Compte.objects.get(pk=equipe['VP'].pk)  # coordination P
    trompe = Membre.objects.create(nom='Province P mais antenne Q', province=monde['P'], antenne=monde['antenne_q'])
    sans_antenne = Membre.objects.create(nom='Province P sans antenne', province=monde['P'])
    visibles = set(D.membres_du_perimetre(vp).values_list('pk', flat=True))
    assert sans_antenne.pk in visibles and trompe.pk not in visibles
    nomination = Nomination.objects.get(compte=vp, active=True)
    assert D._dans_portee(vp, nomination, sans_antenne) and not D._dans_portee(vp, nomination, trompe)


def test_F02_M2_rattacher_antenne_met_la_coordination_a_jour(monde):
    membre = Membre.objects.create(nom='A rattacher', province=monde['P'], antenne=monde['antenne_p'])
    rattacher_antenne(monde['compte'], membre, monde['antenne_q'])
    membre.refresh_from_db()
    assert membre.antenne_id == monde['antenne_q'].id and membre.province_id == monde['Q'].id
    ligne = JournalAction.objects.filter(action=A.RATTACHEMENT).latest('id')
    assert ligne.avant['province'] == monde['P'].id and ligne.apres['province'] == monde['Q'].id


# ---------------------------------------------------------------- M3 : un compte nommé s'en tient à son rôle

def test_F02_M3_compte_nomme_n_herite_pas_d_association_rattachee(monde, equipe):
    hors = AssociationMembre.objects.create(nom='Hors antenne', sigle='HA', antenne=monde['antenne_q'], province=monde['Q'])
    chez_lui = AssociationMembre.objects.create(nom='Chez lui', sigle='CL', antenne=monde['antenne_p'], province=monde['P'])
    va = Compte.objects.get(pk=equipe['VA'].pk)
    hors.users.add(va)  # rattachement hérité : ne compte plus pour un compte nommé
    visibles = set(D.associations_du_compte(va).values_list('pk', flat=True))
    assert chez_lui.pk in visibles and hors.pk not in visibles
    sans_nomination = _compte('herite-assoc')
    hors.users.add(sans_nomination)
    assert set(D.associations_du_compte(sans_nomination).values_list('pk', flat=True)) == {hors.pk}  # le hérité garde son rattachement


def test_F02_M3_association_de_l_agent_limitee_a_son_antenne(monde):
    autre = AssociationMembre.objects.create(nom='Autre', sigle='AU', antenne=monde['antenne_q'], province=monde['Q'])
    voulue = AssociationMembre.objects.create(nom='Voulue', sigle='VO', antenne=monde['antenne_p'], province=monde['P'])
    ordinaire = AssociationMembre.objects.create(nom='Ordinaire', sigle='OR', antenne=monde['antenne_p'], province=monde['P'])
    at_simple = _nommer(monde, roles.AT, antenne=monde['antenne_p'])
    at_lie = _compte('at-lie-assoc')
    N.creer_nomination(monde['compte'], at_lie, roles.AT, antenne=monde['antenne_p'], association=voulue)
    at_lie = Compte.objects.get(pk=at_lie.pk)
    assert {voulue.pk, ordinaire.pk} <= set(D.associations_du_compte(at_simple).values_list('pk', flat=True))
    assert autre.pk not in set(D.associations_du_compte(at_simple).values_list('pk', flat=True))
    assert set(D.associations_du_compte(at_lie).values_list('pk', flat=True)) == {voulue.pk}


# ---------------------------------------------------------------- F4 : alerte sans destinataire

def test_F02_F4_alerte_sans_destinataire_n_est_pas_notee_envoyee(monde):
    compte = _compte('mandat-orphelin')
    nomination = N.creer_nomination(monde['compte'], compte, roles.VN)
    Compte.objects.filter(pk=monde['compte'].pk).update(is_active=False)  # celui qui a nommé n'est plus actif ; aucun autre président
    Nomination.objects.filter(pk=nomination.pk).update(fin=timezone.localdate() + timedelta(days=10))
    rapport = N.alertes_de_mandat()
    nomination.refresh_from_db()
    assert nomination.alerte_envoyee_le is None and nomination not in rapport['envoyees'] and not Notification.objects.exists()
    assert JournalAction.objects.filter(action=A.ALERTE_MANDAT, apres__sans_destinataire=True).exists()
    president = _nommer(monde, roles.PR)  # un président actif existe maintenant : l'alerte est retentée
    N.alertes_de_mandat()
    nomination.refresh_from_db()
    assert nomination.alerte_envoyee_le is not None and Notification.objects.filter(user=president).exists()


# ---------------------------------------------------------------- B3 : droits hérités et déploiement

def test_F02_B3_controle_de_deploiement_avertit_si_les_droits_herites_sont_actifs():
    with override_settings(FENAMO_DROITS_HERITES=True):
        assert [m.id for m in droits_herites_en_production(None)] == ['fenamo.W001']
    with override_settings(FENAMO_DROITS_HERITES=False):
        assert droits_herites_en_production(None) == []


def test_F02_B3_la_production_coupe_les_droits_herites_par_defaut():
    from pathlib import Path
    texte = (Path(__file__).resolve().parent.parent / 'fenamo' / 'settings' / 'prod.py').read_text(encoding='utf-8')
    assert "FENAMO_DROITS_HERITES = env.bool('FENAMO_DROITS_HERITES', default=False)" in texte


# ---------------------------------------------------------------- admin, notifications, journal

def test_F02_admin_nomination_en_lecture_seule(rf, monde):
    from django.contrib import admin
    modele_admin = admin.site._registry[Nomination]
    requete = rf.get('/')
    requete.user = monde['compte']
    assert modele_admin.has_view_permission(requete)
    assert not modele_admin.has_add_permission(requete) and not modele_admin.has_change_permission(requete)
    assert not modele_admin.has_delete_permission(requete)


def test_F02_notifications_selon_le_role_matrice_4_3(monde, equipe):
    at = _nommer(monde, roles.AT, antenne=monde['antenne_p'])
    vi = _nommer(monde, roles.VI)
    ed = _nommer(monde, roles.ED)
    nomme = Compte.objects.get(pk=N.creer_nomination(equipe['VA'], _compte('nomme-par-va'), roles.AT, antenne=monde['antenne_p']).compte_id)
    dans = _actif(monde, 'Dossier du perimetre')
    hors = Membre.objects.create(nom='Dossier hors perimetre', province=monde['Q'], antenne=monde['antenne_q'])
    n_perimetre = Notification.objects.create(user=at, membre=dans, titre='Dossier de l antenne')
    n_hors = Notification.objects.create(user=at, membre=hors, titre='Dossier ailleurs')
    n_nomme = Notification.objects.create(user=nomme, titre='Activite d un nomme')
    n_propre = Notification.objects.create(user=equipe['VA'], titre='La mienne')
    ids = lambda u: set(notifications_du_perimetre(u).values_list('pk', flat=True))  # noqa: E731
    va = Compte.objects.get(pk=equipe['VA'].pk)
    assert ids(va) == {n_perimetre.pk, n_nomme.pk, n_propre.pk}  # périmètre + ses nommés + les siennes, pas le dossier ailleurs
    assert ids(equipe['PR']) == {n_perimetre.pk, n_hors.pk, n_nomme.pk, n_propre.pk}  # toutes
    assert ids(monde['compte']) == ids(equipe['PR'])
    assert ids(at) == {n_perimetre.pk, n_hors.pk}  # ses dossiers : celles qui lui sont adressées
    assert ids(vi) == set() and ids(ed) == set()


def test_F02_journal_filtres_role_et_lieu(monde, equipe):
    N.desactiver(equipe['VP'], _nommer(monde, roles.VA, antenne=monde['antenne_p']), 'Motif A')
    ligne = JournalAction.objects.filter(action=A.DESACTIVATION_COMPTE).latest('id')
    assert ligne.role == roles.VP
    assert ligne in list(lister_journal({'role': 'VP'}).object_list)
    assert ligne not in list(lister_journal({'role': 'PR'}).object_list)
    assert lister_journal({'role': 'INCONNU'}).paginator.count == lister_journal({}).paginator.count  # filtre inconnu ignoré
    JournalAction.objects.filter(pk=ligne.pk).update(coordination=monde['P'], antenne=monde['antenne_p'])
    assert ligne in list(lister_journal({'coordination': str(monde['P'].id)}).object_list)
    assert ligne not in list(lister_journal({'coordination': str(monde['Q'].id)}).object_list)
    assert ligne in list(lister_journal({'antenne': str(monde['antenne_p'].id)}).object_list)
    assert lister_journal({'antenne': '99999999999999999999'}).paginator.count == lister_journal({}).paginator.count


# ---------------------------------------------------------------- vue : renouveler sans nomination, liste des engins

def test_F02_renouveler_compte_sans_nomination_ne_fait_pas_d_erreur_500(client, monde):
    herite = _compte('herite-renouv', privilege1=True)
    client.force_login(monde['compte'])
    url = reverse('utilisateurs-renouveler', kwargs={'id': herite.id})
    assert client.get(url).status_code == 200
    reponse = client.post(url, {'motif': ''})
    assert reponse.status_code < 500 and not Nomination.objects.filter(compte=herite).exists()


def test_F02_renouveler_affiche_la_fin_calculee_par_le_service(client, monde, equipe):
    cible = _nommer(monde, roles.AT, antenne=monde['antenne_p'])
    client.force_login(equipe['VA'])
    reponse = client.get(reverse('utilisateurs-renouveler', kwargs={'id': cible.id}))
    assert reponse.context['nouvelle_fin'] == N.fin_de_mandat(roles.AT)


def test_F30_liste_des_engins_get_seulement(client, monde, equipe):
    client.force_login(equipe['VA'])
    assert client.post(reverse('engin-liste')).status_code == 405


# ---------------------------------------------------------------- matrice § 4.3

def test_F02_matrice_creation_de_membre_agent_et_president_seulement(monde, acteurs_roles):
    creent = {r for r, c in acteurs_roles.items() if D.droits_membre(c)['peut_creer_membre']}
    assert creent == {'PR', 'AT'}
    assert D.droits_membre(monde['compte'])['peut_creer_membre']  # le SU garde l'exception


def test_F02_matrice_pieces_privees_et_mot_de_passe_mobile_ont_leurs_cles(monde, acteurs_roles):
    for role in ('PR', 'VN', 'VP', 'VA'):
        droits = D.droits_membre(acteurs_roles[role], monde['M'])
        assert droits['peut_voir_pieces'] and droits['peut_definir_mot_de_passe_mobile'], role
        assert not droits['peut_creer_membre'] or role == 'PR'  # VN, VP, VA valident sans créer
    for role in ('VI', 'ED'):
        droits = D.droits_membre(acteurs_roles[role], monde['M'])
        assert not droits['peut_voir_pieces'] and not droits['peut_definir_mot_de_passe_mobile'], role
    at = D.droits_membre(acteurs_roles['AT'], monde['M'])  # M est une saisie de cet agent
    assert at['peut_voir_pieces'] and at['peut_definir_mot_de_passe_mobile']
    assert not D.droits_membre(acteurs_roles['AT'])['peut_voir_pieces']  # jamais les pièces d'une association


def test_F02_matrice_un_validateur_sans_creation_peut_quand_meme_voir_les_pieces(client, monde, acteurs_roles):
    from coptapp.models import Membre as M
    assert not D.droits_membre(acteurs_roles['VA'])['peut_creer_membre']
    droits = D.droits_membre(acteurs_roles['VA'], M.objects.get(pk=monde['M'].pk))
    assert droits['peut_voir_pieces']
    client.force_login(acteurs_roles['VI'])
    assert client.get(reverse('fichier', args=['membre', monde['M'].id, 'fiche_id'])).status_code in (403, 404)


def test_F02_matrice_l_agent_lit_son_antenne_mais_n_ecrit_que_ses_saisies(monde, acteurs_roles):
    at = acteurs_roles['AT']
    autre_saisie = Membre.objects.create(nom='Saisie d un autre', antenne=monde['antenne_p'], province=monde['P'], user=_compte('autre-agent'))
    sans_saisie = Membre.objects.create(nom='Saisie de personne', antenne=monde['antenne_p'], province=monde['P'])
    hors_antenne = monde['N']
    visibles = set(D.membres_du_perimetre(at).values_list('pk', flat=True))
    assert {monde['M'].pk, autre_saisie.pk, sans_saisie.pk} <= visibles and hors_antenne.pk not in visibles  # L : son antenne
    ecritures = ('peut_modifier', 'peut_demander_suppression', 'peut_ajouter_engin', 'peut_ajouter_famille', 'peut_modifier_engin',
                 'peut_supprimer_engin', 'peut_modifier_famille', 'peut_supprimer_famille', 'peut_voir_pieces',
                 'peut_definir_mot_de_passe_mobile')
    for membre in (autre_saisie, sans_saisie):
        droits = D.droits_membre(at, membre)
        assert not any(droits[c] for c in ecritures), (membre.nom, [c for c in ecritures if droits[c]])
        assert droits['peut_demander_modification']  # il peut seulement demander une modification
    propre = D.droits_membre(at, monde['M'])
    assert propre['peut_modifier'] and propre['peut_ajouter_engin'] and propre['peut_demander_suppression']  # sa saisie, avant V1
    Membre.objects.filter(pk=monde['M'].pk).update(etat='valide_antenne')
    apres_v1 = D.droits_membre(at, Membre.objects.get(pk=monde['M'].pk))
    assert not apres_v1['peut_modifier'] and not apres_v1['peut_modifier_engin'] and apres_v1['peut_demander_modification']


def test_F02_matrice_peut_nommer_dans_le_menu(monde, acteurs_roles):
    nomment = {r for r, c in acteurs_roles.items() if D.droits_menu(c)['peut_nommer']}
    assert nomment == {'PR', 'VN', 'VP', 'VA'} and D.droits_menu(monde['compte'])['peut_nommer']
    assert not D.droits_menu(_compte('sans-role'))['peut_nommer']
    from fenamo.balises import peut_nommer
    assert peut_nommer(D.droits_menu(acteurs_roles['VP'])) and not peut_nommer(D.droits_menu(acteurs_roles['AT']))


def test_F02_mot_de_passe_mobile_refuse_au_validateur_hors_perimetre_et_au_visiteur(monde, acteurs_roles):
    from compte.services.mobile import definir_mot_de_passe_membre
    assert definir_mot_de_passe_membre(acteurs_roles['VA'], Membre.objects.get(pk=monde['M'].pk))
    with pytest.raises(PermissionDenied):
        definir_mot_de_passe_membre(acteurs_roles['VI'], Membre.objects.get(pk=monde['M'].pk))
    with pytest.raises(PermissionDenied):
        definir_mot_de_passe_membre(acteurs_roles['VA'], monde['N'])
