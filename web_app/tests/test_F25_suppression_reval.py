"""F-25 : suppression d'un membre par actions explicites (demander, annuler, executer, restaurer), motif, journal.

Règles vérifiées (service `traiter_suppression_membre` et vue `delete-membre`) :
- agent / validateurs : DEMANDE de suppression, motif obligatoire ; annulation par l'auteur seul ;
- SU et privilege5 : EXÉCUTION et RESTAURATION (motif obligatoire), annulation de toute demande ;
- action confrontée à l'état courant : 409 en cas d'écart ; 400 sans action ; tout est journalisé, sans donnée sensible.
"""
import json

import pytest
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import PermissionDenied
from django.test import Client
from django.urls import reverse

from compte.models import JournalAction
from coptapp.models import Membre
from coptapp.services.actions import MOTIF_MAX, EtatIncoherent, traiter_suppression_membre
from tests.test_F21_matrice_routes import acteurs  # noqa: F401
from tests.test_plan_url import hachage_rapide, jeu  # noqa: F401

A = JournalAction.Action
SENTINELLES = {
    'telephone': '+243990000001', 'mail': 'sentinelle@example.invalid', 'numero_carte_d_electeur': 'ELEC-SENTINELLE-77',
    'permis': 'PERMIS-SENTINELLE-88', 'brevet': 'BREVET-SENTINELLE-99', 'password': 'MDP-SENTINELLE-123',
}


@pytest.fixture
def cible(acteurs):
    """Membre saisi par p1 (donc visible de p1), avec des données personnelles sentinelles."""
    for champ, valeur in SENTINELLES.items():
        setattr(acteurs['membre'], champ, valeur)
    acteurs['membre'].save()
    return acteurs['membre']


def _agir(client, acteurs, profil, cible, action, **donnees):
    client.force_login(acteurs['comptes'][profil])
    return client.post(reverse('delete-membre', kwargs={'id': cible.id}), {'action': action, **donnees})


def _journal(cible, action=None):
    lignes = JournalAction.objects.filter(objet_type=ContentType.objects.get_for_model(Membre), objet_id=cible.id)
    return lignes.filter(action=action) if action else lignes


def _etat(cible):
    cible.refresh_from_db()
    return cible.is_delete, cible.suppression_demandee, cible.suppression_demandee_par_id


# ---------------------------------------------------------------- motif obligatoire

@pytest.mark.parametrize('motif', [None, '', '   ', '\t\n  '])
@pytest.mark.parametrize('profil, action', [('p1', 'demander'), ('p2', 'demander'), ('p3', 'demander'),
                                            ('p5', 'executer'), ('su', 'executer'), ('su', 'demander')])
def test_F25_demande_ou_suppression_sans_motif_refusee(client, acteurs, cible, profil, action, motif):
    donnees = {} if motif is None else {'motif': motif}
    r = _agir(client, acteurs, profil, cible, action, **donnees)
    assert r.status_code == 302  # retour sur la fiche avec un message d'erreur
    assert _etat(cible) == (False, False, None)
    assert cible.motif_suppression == '' and not _journal(cible).exists()
    assert 'Indiquez le motif' in client.get(r['Location']).content.decode()


def test_F25_motif_limite_a_500_caracteres(client, acteurs, cible):
    r = _agir(client, acteurs, 'su', cible, 'executer', motif='m' * (MOTIF_MAX + 1))
    assert r.status_code == 302 and _etat(cible) == (False, False, None)
    assert 'limité à 500' in client.get(r['Location']).content.decode()
    _agir(client, acteurs, 'su', cible, 'executer', motif='m' * MOTIF_MAX)
    assert _etat(cible)[0] is True


def test_F25_restauration_exige_un_motif(client, acteurs, cible):
    _agir(client, acteurs, 'su', cible, 'executer', motif='Décès')
    _agir(client, acteurs, 'su', cible, 'restaurer')
    assert _etat(cible)[0] is True and not _journal(cible, A.RESTAURATION).exists()
    _agir(client, acteurs, 'su', cible, 'restaurer', motif='Erreur de saisie')
    assert _etat(cible)[0] is False
    assert _journal(cible, A.RESTAURATION).get().motif == 'Erreur de saisie'


# ---------------------------------------------------------------- demande par l'agent

def test_F25_demande_par_agent_avec_motif(client, acteurs, cible):
    r = _agir(client, acteurs, 'p1', cible, 'demander', motif='  Doublon avec une autre fiche  ')
    assert r.status_code == 302
    assert _etat(cible) == (False, True, acteurs['comptes']['p1'].pk)  # pas encore supprimé
    assert cible.motif_suppression == 'Doublon avec une autre fiche'  # motif nettoyé
    ligne = _journal(cible, A.DEMANDE_SUPPRESSION).get()
    assert ligne.auteur == acteurs['comptes']['p1'] and ligne.motif == 'Doublon avec une autre fiche'
    assert ligne.role.startswith('privilèges') and 'P1' in ligne.role


def test_F25_agent_et_validateurs_ne_peuvent_pas_executer(client, acteurs, cible):
    for profil in ('p1', 'p2', 'p3'):
        assert _agir(client, acteurs, profil, cible, 'executer', motif='x').status_code == 403
    assert _etat(cible) == (False, False, None)


def test_F25_membre_demande_reste_visible_des_listes_jusqu_a_l_execution(client, acteurs, cible):
    _agir(client, acteurs, 'p1', cible, 'demander', motif='Doublon')
    client.force_login(acteurs['comptes']['p2'])
    assert 'Suppression demandée' in client.get(reverse('membre-view', kwargs={'id': cible.id})).content.decode()
    assert cible.nom in client.get(reverse('liste-membre')).content.decode()


# ---------------------------------------------------------------- annulation : auteur et exécutants, pas un tiers

def test_F25_annulation_par_l_auteur_de_la_demande(client, acteurs, cible):
    _agir(client, acteurs, 'p1', cible, 'demander', motif='Erreur de saisie')
    r = _agir(client, acteurs, 'p1', cible, 'annuler')  # l'annulation n'exige pas de motif
    assert r.status_code == 302 and _etat(cible) == (False, False, None)
    ligne = _journal(cible, A.ANNULATION_DEMANDE_SUPPRESSION).get()  # action propre, pas « restauration »
    assert ligne.auteur == acteurs['comptes']['p1']
    assert not _journal(cible, A.RESTAURATION).exists()


@pytest.mark.parametrize('profil', ['su', 'p5'])
def test_F25_su_et_p5_annulent_une_demande_en_cours(client, acteurs, cible, profil):
    _agir(client, acteurs, 'p1', cible, 'demander', motif='Erreur de saisie')
    assert _agir(client, acteurs, profil, cible, 'annuler').status_code == 302
    assert _etat(cible) == (False, False, None)


@pytest.mark.parametrize('tiers', ['p2', 'p3'])
def test_F25_annulation_par_un_tiers_refusee_403(client, acteurs, cible, tiers):
    _agir(client, acteurs, 'p1', cible, 'demander', motif='Erreur de saisie')
    assert _agir(client, acteurs, tiers, cible, 'annuler').status_code == 403
    assert _etat(cible) == (False, True, acteurs['comptes']['p1'].pk)
    assert _journal(cible).count() == 1  # seule la demande initiale


def test_F25_tiers_ne_peut_pas_redeposer_une_demande_deja_en_cours(client, acteurs, cible):
    _agir(client, acteurs, 'p1', cible, 'demander', motif='Erreur de saisie')
    assert _agir(client, acteurs, 'p2', cible, 'demander', motif='Autre motif').status_code == 409
    cible.refresh_from_db()
    assert cible.motif_suppression == 'Erreur de saisie' and cible.suppression_demandee_par_id == acteurs['comptes']['p1'].pk


def test_F25_visiteur_ne_demande_ni_n_annule(client, acteurs, cible):
    Membre.objects.filter(pk=cible.pk).update(is_validate3=True)
    assert _agir(client, acteurs, 'p4', cible, 'demander', motif='x').status_code == 403  # visible mais lecture seule
    assert _etat(cible) == (False, False, None)


# ---------------------------------------------------------------- exécution, restauration

@pytest.mark.parametrize('profil', ['su', 'p5'])
def test_F25_execution_par_su_ou_privilege5_puis_restauration(client, acteurs, cible, profil):
    _agir(client, acteurs, 'p1', cible, 'demander', motif='Demande de l’agent')  # une demande en cours est consommée
    r = _agir(client, acteurs, profil, cible, 'executer', motif='Décès confirmé')
    assert r.status_code == 302 and _etat(cible) == (True, False, None)
    assert cible.motif_suppression == 'Décès confirmé'
    suppression = _journal(cible, A.SUPPRESSION).get()
    assert suppression.auteur == acteurs['comptes'][profil] and suppression.motif == 'Décès confirmé'
    assert suppression.avant == {'is_delete': False} and suppression.apres == {'is_delete': True}
    client.force_login(acteurs['comptes']['p2'])  # disparu des listes d'un validateur
    assert cible.nom not in client.get(reverse('liste-membre')).content.decode()
    r = _agir(client, acteurs, profil, cible, 'restaurer', motif='Erreur')
    assert r.status_code == 302 and _etat(cible) == (False, False, None)
    assert _journal(cible, A.RESTAURATION).filter(auteur=acteurs['comptes'][profil]).exists()


def test_F25_membre_supprime_introuvable_pour_l_agent_les_validateurs_et_le_visiteur(client, acteurs, cible):
    _agir(client, acteurs, 'su', cible, 'executer', motif='Décès')
    for profil in ('p1', 'p2', 'p3', 'p4', 'nu', 'ed'):
        client.force_login(acteurs['comptes'][profil])
        assert client.get(reverse('membre-view', kwargs={'id': cible.id})).status_code == 404, profil
        r = client.post(reverse('delete-membre', kwargs={'id': cible.id}), {'action': 'restaurer', 'motif': 'x'})
        assert r.status_code == 404, profil
    assert _etat(cible)[0] is True
    client.force_login(acteurs['comptes']['su'])
    assert client.get(reverse('membre-view', kwargs={'id': cible.id})).status_code == 200  # qui restaure le voit


def test_F25_service_refuse_sans_droit_et_confronte_a_l_etat(acteurs, cible):
    with pytest.raises(PermissionDenied):
        traiter_suppression_membre(acteurs['comptes']['p2'], cible, 'executer', 'x')
    with pytest.raises(EtatIncoherent):
        traiter_suppression_membre(acteurs['comptes']['su'], cible, 'restaurer', 'x')  # pas supprimé
    with pytest.raises(EtatIncoherent):
        traiter_suppression_membre(acteurs['comptes']['su'], cible, 'annuler')  # aucune demande
    with pytest.raises(ValueError):
        traiter_suppression_membre(acteurs['comptes']['su'], cible, 'basculer', 'x')


def test_F25_409_quand_l_action_ne_correspond_pas_a_l_etat(client, acteurs, cible):
    assert _agir(client, acteurs, 'su', cible, 'restaurer', motif='x').status_code == 409  # rien à restaurer
    assert _agir(client, acteurs, 'p1', cible, 'annuler').status_code == 409  # aucune demande
    _agir(client, acteurs, 'su', cible, 'executer', motif='Décès')
    assert _agir(client, acteurs, 'su', cible, 'executer', motif='Décès').status_code == 409  # déjà supprimé
    assert _journal(cible, A.SUPPRESSION).count() == 1  # un double clic n'écrit pas deux fois


def test_F25_action_manquante_ou_inconnue_400(client, acteurs, cible):
    client.force_login(acteurs['comptes']['su'])
    url = reverse('delete-membre', kwargs={'id': cible.id})
    assert client.post(url, {'motif': 'x'}).status_code == 400
    assert client.post(url, {'action': 'basculer', 'motif': 'x'}).status_code == 400
    assert _etat(cible) == (False, False, None)


def test_F25_ecriture_par_colonnes_ne_perd_pas_une_modification_concurrente(acteurs, cible):
    ancien = Membre.objects.get(pk=cible.pk)  # lu avant la modification concurrente
    Membre.objects.filter(pk=cible.pk).update(village='Concurrent')
    traiter_suppression_membre(acteurs['comptes']['p1'], ancien, 'demander', 'Doublon')
    cible.refresh_from_db()
    assert cible.village == 'Concurrent' and cible.suppression_demandee


@pytest.mark.parametrize('profil', ['nu', 'ed', 'p4'])
def test_F25_hors_perimetre_404(client, acteurs, cible, profil):
    assert _agir(client, acteurs, profil, cible, 'demander', motif='x').status_code == 404


def test_F25_get_interdit_et_csrf_exige(acteurs, cible):
    client = Client(enforce_csrf_checks=True)
    client.force_login(acteurs['comptes']['su'])
    url = reverse('delete-membre', kwargs={'id': cible.id})
    assert client.get(url).status_code == 405
    assert client.post(url, {'action': 'executer', 'motif': 'x'}).status_code == 403  # pas de jeton CSRF
    assert _etat(cible) == (False, False, None)


# ---------------------------------------------------------------- journal complet, sans donnée sensible

def test_F25_journal_complet_sans_donnee_sensible(client, acteurs, cible):
    _agir(client, acteurs, 'p1', cible, 'demander', motif='Doublon')
    _agir(client, acteurs, 'p1', cible, 'annuler')
    _agir(client, acteurs, 'p1', cible, 'demander', motif='Doublon encore')
    _agir(client, acteurs, 'su', cible, 'executer', motif='Décès')
    _agir(client, acteurs, 'su', cible, 'restaurer', motif='Erreur')
    lignes = list(_journal(cible).order_by('id'))
    assert [ligne.action for ligne in lignes] == ['demande_suppression', 'annulation_demande_suppression',
                                                 'demande_suppression', 'suppression', 'restauration']
    for ligne in lignes:
        assert ligne.auteur_id and ligne.role and ligne.date and ligne.objet_id == cible.id
        assert ligne.objet_libelle == cible.nom
        brut = json.dumps([ligne.avant, ligne.apres, ligne.motif, ligne.objet_libelle], default=str)
        for valeur in SENTINELLES.values():
            assert valeur not in brut, valeur
        for cle in ('password', 'photo', 'fiche', 'token'):
            assert cle not in brut.lower()
    client.force_login(acteurs['comptes']['su'])  # la fiche n'affiche jamais avant / après
    page = client.get(reverse('membre-view', kwargs={'id': cible.id})).content.decode()
    for valeur in ('suppression_demandee', '"is_delete"'):
        assert valeur not in page


def test_F25_notification_creee_pour_chaque_action_reussie_mais_pas_pour_un_refus(client, acteurs, cible):
    from coptapp.models import Notification
    _agir(client, acteurs, 'p1', cible, 'demander')  # sans motif
    assert Notification.objects.count() == 0
    _agir(client, acteurs, 'p1', cible, 'demander', motif='Doublon')
    assert Notification.objects.filter(membre=cible).count() == 1


def test_F25_motif_d_annulation_limite_a_500_caracteres(client, acteurs, cible):
    _agir(client, acteurs, 'p1', cible, 'demander', motif='Doublon')
    r = _agir(client, acteurs, 'p1', cible, 'annuler', motif='m' * (MOTIF_MAX + 1))
    assert r.status_code == 302 and _etat(cible) == (False, True, acteurs['comptes']['p1'].pk)
    assert 'limité à 500' in client.get(r['Location']).content.decode()


def test_F25_restauration_vide_le_motif_de_suppression_le_journal_le_garde(client, acteurs, cible):
    _agir(client, acteurs, 'su', cible, 'executer', motif='Décès')
    assert Membre.objects.get(pk=cible.pk).motif_suppression == 'Décès'
    _agir(client, acteurs, 'su', cible, 'restaurer', motif='Erreur')
    assert Membre.objects.get(pk=cible.pk).motif_suppression == ''
    assert _journal(cible, A.SUPPRESSION).get().motif == 'Décès'
