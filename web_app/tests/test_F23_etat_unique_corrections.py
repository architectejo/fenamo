"""F-23 : corrections du lot « état unique » après audit : mise à jour perdue, règle transitoire, notification du renvoi, reprise réservée
à l'auteur, « Valider tout le monde » plafonné, droits hérités, journal, mobapp."""
import logging

import pytest
from django.contrib import admin
from django.core.exceptions import PermissionDenied
from django.urls import reverse

from compte import roles
from compte.models import Compte, JournalAction
from compte.services import droits as D
from compte.services.journal_lecture import lister_journal
from compte.services.nominations import compte_a_privileges_herites, membres_nommables
from coptapp.models import CIRCUIT, Membre, Notification, Province
from coptapp.services import transitions as T
from mobapp.views import _deja_valide
from tests.conftest import forcer_etat
from tests.test_F02_droits_roles import _compte, _nommer, acteurs_roles, monde  # noqa: F401
from tests.test_plan_url import hachage_rapide, jeu  # noqa: F401


def _saisi(monde, nom='Dossier', **kw):
    return Membre.objects.create(nom=nom, antenne=monde['antenne_p'], province=monde['P'], user=monde['agent'], **kw)


# ---------------------------------------------------------------- M1 : mise à jour perdue

def test_F23_save_sans_update_fields_n_annule_pas_une_validation_concurrente(monde, acteurs_roles):
    m = _saisi(monde)
    lecture_perimee = Membre.objects.get(pk=m.pk)  # lue AVANT la validation
    assert T.valider(acteurs_roles['VA'], m) == ['valide_antenne']
    lecture_perimee.nom = 'Nom corrigé'
    lecture_perimee.save()  # sans update_fields : l'état n'est pas réécrit
    relu = Membre.objects.get(pk=m.pk)
    assert relu.nom == 'Nom corrigé' and relu.etat == 'valide_antenne' and relu.is_validate2


def test_F23_save_sans_update_fields_ne_reecrit_ni_suppression_ni_renvoi(monde, acteurs_roles):
    m = _saisi(monde)
    perimee = Membre.objects.get(pk=m.pk)
    T.supprimer(acteurs_roles['PR'], m, 'Doublon')
    perimee.telephone = '+243 1'
    perimee.save()
    relu = Membre.objects.get(pk=m.pk)
    assert relu.etat == 'supprime' and relu.is_delete and relu.etat_precedent == 'saisi' and relu.telephone == '+243 1'


def test_F23_changer_explicitement_etat_dans_le_code_reste_ecrit(monde):
    m = _saisi(monde)
    m.etat = 'actif'
    m.save()
    relu = Membre.objects.get(pk=m.pk)
    assert relu.etat == 'actif' and relu.is_validate3


def test_F23_creer_un_compte_pour_un_membre_n_ecrit_pas_son_etat(monde):
    from compte.services.comptes import creer_compte_pour_membre
    m = _saisi(monde, 'Compte futur')
    perimee = Membre.objects.get(pk=m.pk)
    forcer_etat(m, 'actif')
    creer_compte_pour_membre(perimee, auteur=monde['compte'])
    relu = Membre.objects.get(pk=m.pk)
    assert relu.is_user and relu.etat == 'actif'


# ---------------------------------------------------------------- règle transitoire

def test_F23_update_de_booleen_sans_changement_ne_fait_pas_perdre_valide_province(monde):
    m = forcer_etat(_saisi(monde), 'valide_province')
    Membre.objects.filter(pk=m.pk).update(is_validate3=False)  # valeur déjà celle du miroir : rien ne change
    m.refresh_from_db()
    assert m.etat == 'valide_province'
    m.is_validate2 = True
    m.save()
    m.refresh_from_db()
    assert m.etat == 'valide_province'
    Membre.objects.filter(pk=m.pk).update(is_validate3=True)  # un vrai changement hérité : traduit
    m.refresh_from_db()
    assert m.etat == 'actif'


def test_F23_ecriture_heritee_est_journalisee_en_avertissement(monde, caplog):
    m = _saisi(monde)
    with caplog.at_level(logging.WARNING, logger='coptapp.models'):
        Membre.objects.filter(pk=m.pk).update(is_validate2=True)
        m.refresh_from_db()
        m.is_validate3 = True
        m.save()
    assert caplog.text.count('règle transitoire') == 2 and Membre.objects.get(pk=m.pk).etat == 'actif'


def test_F23_la_suppression_heritee_garde_l_etat_courant_comme_precedent(monde):
    m = forcer_etat(_saisi(monde), 'valide_province')
    m.is_delete = True
    m.save()
    m.refresh_from_db()
    assert m.etat == 'supprime' and m.etat_precedent == 'valide_province'  # pas recalculé depuis les booléens (aurait donné valide_antenne)
    Membre.objects.filter(pk=m.pk).update(is_delete=False)  # restauration héritée : retour à l'état d'avant
    m.refresh_from_db()
    assert m.etat == 'valide_province' and m.etat_precedent == '' and not m.is_delete


def test_F23_update_de_l_etat_vide_l_etat_precedent_comme_save(monde):
    m = forcer_etat(_saisi(monde), 'supprime', precedent='actif')
    assert m.etat_precedent == 'actif'
    Membre.objects.filter(pk=m.pk).update(etat='saisi')
    m.refresh_from_db()
    assert m.etat == 'saisi' and m.etat_precedent == '' and not m.is_delete


# ---------------------------------------------------------------- admin, mobapp, circuit

def test_F23_admin_membre_etat_et_miroirs_en_lecture_seule():
    modele_admin = admin.site._registry[Membre]
    assert {'etat', 'etat_precedent', 'motif_renvoi', 'is_delete', 'is_validate2', 'is_validate3', 'renvoye'} <= set(modele_admin.readonly_fields)


@pytest.mark.parametrize('etat, verrouille', [('saisi', False), ('renvoye', True), ('valide_antenne', True), ('valide_province', True),
                                              ('actif', True), ('a_renouveler', True), ('supprime', True)])
def test_F23_mobapp_seul_un_dossier_saisi_reste_modifiable_par_le_membre(etat, verrouille):
    assert _deja_valide(Membre(nom='M', etat=etat)) is verrouille


def test_F23_une_seule_definition_du_circuit():
    import compte.services.droits as droits
    import compte.services.droits_herites as herites
    import coptapp.services.transitions as transitions
    assert CIRCUIT == ('saisi', 'valide_antenne', 'valide_province', 'actif')
    assert droits.CIRCUIT is CIRCUIT and herites.CIRCUIT is CIRCUIT and transitions.CIRCUIT is CIRCUIT
    assert not hasattr(transitions, 'etapes_possibles')


# ---------------------------------------------------------------- renvoi : destinataires, reprise

def test_F23_renvoi_sans_destinataire_au_niveau_previent_l_auteur_de_la_saisie(monde, acteurs_roles):
    m = forcer_etat(_saisi(monde), 'valide_province')
    Compte.objects.filter(pk=acteurs_roles['VP'].pk).update(is_active=False)  # plus de VP actif dans la coordination
    T.renvoyer(acteurs_roles['VN'], m, 'À revoir')
    assert Notification.objects.filter(user=monde['agent'], membre=m).exists()
    assert not Notification.objects.filter(user=acteurs_roles['VP'], membre=m).exists()


def test_F23_renvoi_titre_traduisible_et_motif_dans_la_description(monde, acteurs_roles):
    m = _saisi(monde, 'Titre')
    T.renvoyer(acteurs_roles['VA'], m, 'Pièce manquante')
    notification = Notification.objects.get(user=monde['agent'], membre=m)
    assert notification.titre == 'Fiche renvoyée : Titre' and notification.description == 'Pièce manquante'


def test_F23_reprise_reservee_a_l_auteur_de_la_saisie(monde, acteurs_roles):
    auteur = acteurs_roles['AT']  # = monde['agent'] : auteur de la saisie
    autre_agent = _compte('autre-agent-reprise')
    from compte.services.nominations import creer_nomination
    creer_nomination(monde['compte'], autre_agent, roles.AT, antenne=monde['antenne_p'])
    autre_agent = Compte.objects.get(pk=autre_agent.pk)
    m = Membre.objects.create(nom='A reprendre', antenne=monde['antenne_p'], province=monde['P'], user=auteur)
    T.renvoyer(acteurs_roles['VA'], m, 'Corriger')
    for non_auteur in (autre_agent, acteurs_roles['VA'], acteurs_roles['VI']):
        with pytest.raises(PermissionDenied):
            T.reprendre(non_auteur, m)
    assert Membre.objects.get(pk=m.pk).etat == 'renvoye'
    T.reprendre(auteur, m)
    assert Membre.objects.get(pk=m.pk).etat == 'saisi'


def test_F23_la_modification_par_un_non_auteur_ne_remet_pas_dans_le_circuit(monde, acteurs_roles):
    from coptapp.services.membres import modifier_membre
    m = Membre.objects.create(nom='Renvoyé', antenne=monde['antenne_p'], province=monde['P'], user=acteurs_roles['AT'])
    T.renvoyer(acteurs_roles['VA'], m, 'Corriger')
    formulaire, modifie = modifier_membre(acteurs_roles['VA'], Membre.objects.get(pk=m.pk), {'nom': 'Corrigé par le VA', 'date_naissance': '1990-01-01'})
    assert modifie and Membre.objects.get(pk=m.pk).etat == 'renvoye'


# ---------------------------------------------------------------- Valider tout le monde : plafond, filtres, droits hérités

def test_F23_valider_tous_plafond_par_defaut_100_et_reglage(monde, acteurs_roles, settings):
    assert T.plafond_valider_tous() == 100
    settings.VALIDER_TOUS_PLAFOND = 2
    va = acteurs_roles['VA']
    for i in range(4):
        _saisi(monde, f'Plafond reglage {i}')
    base = T.compter_validables(va)
    compte_rendu = T.valider_tous(va)
    assert compte_rendu['plafond'] == 2 and compte_rendu['valides'] == 2 and compte_rendu['restants'] == base - 2


def test_F23_valider_tous_propres_saisies_comptees_avec_les_memes_filtres(monde, acteurs_roles):
    va = acteurs_roles['VA']
    Membre.objects.create(nom='Zed propre', antenne=monde['antenne_p'], province=monde['P'], user=va)
    Membre.objects.create(nom='Autre propre', antenne=monde['antenne_p'], province=monde['P'], user=va)
    assert T.valider_tous(va, {'q': 'Zed'})['ignores'].get('propres_saisies') == 1
    assert T.valider_tous(va)['ignores'].get('propres_saisies') == 2


def test_F23_droits_herites_valider_tous_seulement_su_et_privilege5(monde):
    for nom, reglage, attendu in (('p2', {'privilege2': True}, False), ('p3', {'privilege3': True}, False),
                                  ('p5', {'privilege5': True}, True), ('p1', {'privilege1': True}, False)):
        assert D.droits_membre(_compte(f'{nom}-hh', **reglage))['peut_valider_tous'] is attendu, nom
    with pytest.raises(PermissionDenied):
        T.valider_tous(_compte('p2-refus', privilege2=True))
    assert D.droits_membre(monde['compte'])['peut_valider_tous']


def test_F23_visiteur_herite_et_role_ne_voient_que_les_membres_actifs(monde, acteurs_roles):
    actif = forcer_etat(_saisi(monde, 'Actif seul'), 'actif')
    renouveler = forcer_etat(_saisi(monde, 'A renouveler'), 'a_renouveler')
    saisi = _saisi(monde, 'Pas actif')
    p4 = _compte('p4-visiteur', privilege4=True)
    for visiteur in (p4, acteurs_roles['VI']):
        visibles = set(D.membres_du_perimetre(visiteur).values_list('pk', flat=True))
        assert actif.pk in visibles and saisi.pk not in visibles and renouveler.pk not in visibles, visiteur.username


# ---------------------------------------------------------------- privilèges hérités, journal

def test_F23_une_seule_liste_de_privileges_herites(monde, acteurs_roles):
    from compte.services.nominations import PRIVILEGES_HERITES
    assert PRIVILEGES_HERITES == ('privilege1', 'privilege2', 'privilege3', 'privilege4', 'privilege5', 'editor')
    for champ in PRIVILEGES_HERITES:
        compte = _compte(f'herite-{champ}', **{champ: True})
        assert compte_a_privileges_herites(compte), champ
        membre = Membre.objects.create(nom=f'Membre {champ}', antenne=monde['antenne_p'], province=monde['P'], etat='actif')
        Compte.objects.filter(pk=compte.pk).update(membreId=membre.pk)
        assert membre.pk not in set(membres_nommables(acteurs_roles['VA']).values_list('pk', flat=True)), champ


def test_F23_journal_filtre_des_auteurs_sans_role_et_coordination_sans_code(client, monde, acteurs_roles):
    herite = _compte('auteur-herite', privilege2=True)
    from compte.services.journal import journaliser
    ligne = journaliser(herite, JournalAction.Action.MODIFICATION, None, libelle='Action héritée')
    assert ligne.role.startswith('privil')
    assert ligne in list(lister_journal({'role': 'herites'}).object_list)
    assert ligne not in list(lister_journal({'role': 'PR'}).object_list)
    sans_code = Province.objects.create(nom='Sans code officiel')
    client.force_login(monde['compte'])
    contexte = client.get(reverse('journal')).context
    assert sans_code in list(contexte['coordinations'])
    assert 'herites' in [code for code, _libelle in contexte['roles']]
