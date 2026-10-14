"""Revalidation indépendante (testeur) : suppression d'un membre avec motif (F-25), écrite pour le code de 322e2da.

Compatible avec la variante à action explicite (champ POST ``action``) : le champ est toujours envoyé ; l'ancienne vue
l'ignore. Seules diffèrent deux réponses (409 au lieu de 403 sur une demande redéposée, annulation journalisée sous
une action propre) : les assertions acceptent les deux.
Règles : agent / validateurs DEMANDENT (motif obligatoire), l'auteur seul annule ; SU et privilege5 EXÉCUTENT et
RESTAURENT ; tout est journalisé sans donnée sensible ; GET interdit, CSRF exigé.
"""
import json

import pytest
from django.contrib.contenttypes.models import ContentType
from django.test import Client
from django.urls import reverse

from compte.models import JournalAction
from coptapp.models import Membre, Notification
from tests.test_F21_matrice_routes import acteurs  # noqa: F401
from tests.test_plan_url import hachage_rapide, jeu  # noqa: F401

SENTINELLES = {
    'telephone': '+243990000001', 'mail': 'sentinelle@example.invalid', 'numero_carte_d_electeur': 'ELEC-SENTINELLE-77',
    'permis': 'PERMIS-SENTINELLE-88', 'brevet': 'BREVET-SENTINELLE-99', 'password': 'MDP-SENTINELLE-123',
}
ANNULATION = ('restauration', 'annulation_demande_suppression')  # nom de l'action de journal selon la variante


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


def _journal(cible, *actions):
    lignes = JournalAction.objects.filter(objet_type=ContentType.objects.get_for_model(Membre), objet_id=cible.id)
    return lignes.filter(action__in=actions) if actions else lignes


def _etat(cible):
    cible.refresh_from_db()
    return cible.is_delete, cible.suppression_demandee, cible.suppression_demandee_par_id


# ---------------------------------------------------------------- motif obligatoire

@pytest.mark.parametrize('motif', [None, '', '   ', '\t\n  '])
@pytest.mark.parametrize('profil, action', [('p1', 'demander'), ('p2', 'demander'), ('p3', 'demander'),
                                            ('p5', 'executer'), ('su', 'executer')])
def test_F25_reval_sans_motif_ou_motif_d_espaces_refuse(client, acteurs, cible, profil, action, motif):
    r = _agir(client, acteurs, profil, cible, action, **({} if motif is None else {'motif': motif}))
    assert r.status_code == 302  # retour sur la fiche avec un message d'erreur
    assert _etat(cible) == (False, False, None) and cible.motif_suppression == ''
    assert not _journal(cible).exists()
    assert 'Indiquez le motif' in client.get(r['Location']).content.decode()


# ---------------------------------------------------------------- demande, annulation

def test_F25_reval_demande_par_agent(client, acteurs, cible):
    assert _agir(client, acteurs, 'p1', cible, 'demander', motif='  Doublon avec une autre fiche  ').status_code == 302
    assert _etat(cible) == (False, True, acteurs['comptes']['p1'].pk)
    assert cible.motif_suppression == 'Doublon avec une autre fiche'
    ligne = _journal(cible, 'demande_suppression').get()
    assert ligne.auteur == acteurs['comptes']['p1'] and ligne.motif == 'Doublon avec une autre fiche'


def test_F25_reval_agent_et_validateurs_n_executent_pas(client, acteurs, cible):
    for profil in ('p1', 'p2', 'p3'):
        # variante historique : l'agent qui poste « executer » ne fait qu'une demande (302) ; variante explicite : 403
        assert _agir(client, acteurs, profil, cible, 'executer', motif='x').status_code in (302, 403, 409)
        assert _etat(cible)[0] is False  # jamais supprimé par eux


def test_F25_reval_annulation_par_l_auteur_sans_motif(client, acteurs, cible):
    _agir(client, acteurs, 'p1', cible, 'demander', motif='Erreur de saisie')
    assert _agir(client, acteurs, 'p1', cible, 'annuler').status_code == 302
    assert _etat(cible) == (False, False, None)
    assert _journal(cible, *ANNULATION).filter(auteur=acteurs['comptes']['p1']).count() == 1


@pytest.mark.parametrize('tiers', ['p2', 'p3'])
def test_F25_reval_annulation_par_un_tiers_403(client, acteurs, cible, tiers):
    _agir(client, acteurs, 'p1', cible, 'demander', motif='Erreur de saisie')
    assert _agir(client, acteurs, tiers, cible, 'annuler').status_code == 403
    assert _etat(cible) == (False, True, acteurs['comptes']['p1'].pk) and _journal(cible).count() == 1


def test_F25_reval_un_tiers_ne_redepose_pas_une_demande_en_cours(client, acteurs, cible):
    _agir(client, acteurs, 'p1', cible, 'demander', motif='Erreur de saisie')
    assert _agir(client, acteurs, 'p2', cible, 'demander', motif='Autre').status_code in (403, 409)
    cible.refresh_from_db()
    assert cible.motif_suppression == 'Erreur de saisie' and cible.suppression_demandee_par_id == acteurs['comptes']['p1'].pk


def test_F25_reval_visiteur_lecture_seule(client, acteurs, cible):
    Membre.objects.filter(pk=cible.pk).update(is_validate3=True)
    assert _agir(client, acteurs, 'p4', cible, 'demander', motif='x').status_code == 403
    assert _etat(cible) == (False, False, None)


@pytest.mark.parametrize('profil', ['su', 'p5'])
def test_F25_reval_su_et_p5_annulent_une_demande_en_cours(client, acteurs, cible, profil):
    _agir(client, acteurs, 'p1', cible, 'demander', motif='Erreur de saisie')
    assert _agir(client, acteurs, profil, cible, 'annuler').status_code == 302
    assert _etat(cible) == (False, False, None)


# ---------------------------------------------------------------- exécution, restauration

@pytest.mark.parametrize('profil', ['su', 'p5'])
def test_F25_reval_execution_puis_restauration(client, acteurs, cible, profil):
    _agir(client, acteurs, 'p1', cible, 'demander', motif='Demande de l’agent')
    assert _agir(client, acteurs, profil, cible, 'executer', motif='Décès confirmé').status_code == 302
    assert _etat(cible) == (True, False, None) and cible.motif_suppression == 'Décès confirmé'
    ligne = _journal(cible, 'suppression').get()
    assert ligne.auteur == acteurs['comptes'][profil] and ligne.motif == 'Décès confirmé'
    assert ligne.avant == {'etat': cible.etat_precedent} and ligne.apres == {'etat': 'supprime'}  # l'état d'avant est gardé pour la restauration
    client.force_login(acteurs['comptes']['p2'])
    assert cible.nom not in client.get(reverse('liste-membre')).content.decode()
    assert _agir(client, acteurs, profil, cible, 'restaurer', motif='Erreur').status_code == 302
    assert _etat(cible) == (False, False, None)
    assert _journal(cible, 'restauration').filter(auteur=acteurs['comptes'][profil]).exists()


@pytest.mark.parametrize('profil', ['p1', 'p2', 'p3'])
def test_F25_reval_restauration_refusee_aux_non_executants(client, acteurs, cible, profil):
    _agir(client, acteurs, 'su', cible, 'executer', motif='Décès')
    assert _agir(client, acteurs, profil, cible, 'restaurer', motif='x').status_code in (403, 404)
    assert _etat(cible)[0] is True


def test_F25_reval_membre_supprime_invisible_du_visiteur(client, acteurs, cible):
    _agir(client, acteurs, 'su', cible, 'executer', motif='Décès')
    client.force_login(acteurs['comptes']['p4'])
    assert client.get(reverse('membre-view', kwargs={'id': cible.id})).status_code == 404


@pytest.mark.parametrize('profil', ['nu', 'ed', 'p4'])
def test_F25_reval_hors_perimetre_404(client, acteurs, cible, profil):
    assert _agir(client, acteurs, profil, cible, 'demander', motif='x').status_code == 404


def test_F25_reval_get_interdit_et_csrf_exige(acteurs, cible):
    client = Client(enforce_csrf_checks=True)
    client.force_login(acteurs['comptes']['su'])
    url = reverse('delete-membre', kwargs={'id': cible.id})
    assert client.get(url).status_code == 405
    assert client.post(url, {'action': 'executer', 'motif': 'x'}).status_code == 403
    assert _etat(cible) == (False, False, None)


def test_F25_reval_motif_demesure_ne_provoque_pas_d_erreur(client, acteurs, cible):
    assert _agir(client, acteurs, 'su', cible, 'executer', motif='m' * 20000).status_code == 302


# ---------------------------------------------------------------- journal complet, sans donnée sensible

def test_F25_reval_journal_complet_sans_donnee_sensible(client, acteurs, cible):
    _agir(client, acteurs, 'p1', cible, 'demander', motif='Doublon')
    _agir(client, acteurs, 'p1', cible, 'annuler')
    _agir(client, acteurs, 'p1', cible, 'demander', motif='Doublon encore')
    _agir(client, acteurs, 'su', cible, 'executer', motif='Décès')
    _agir(client, acteurs, 'su', cible, 'restaurer', motif='Erreur')
    lignes = list(_journal(cible).order_by('id'))
    actions = ['restauration' if l.action in ANNULATION else l.action for l in lignes]
    assert actions == ['demande_suppression', 'restauration', 'demande_suppression', 'suppression', 'restauration']
    for ligne in lignes:
        assert ligne.auteur_id and ligne.role and ligne.date and ligne.objet_id == cible.id
        assert ligne.objet_libelle == cible.nom
        brut = json.dumps([ligne.avant, ligne.apres, ligne.motif, ligne.objet_libelle], default=str)
        for valeur in SENTINELLES.values():
            assert valeur not in brut, valeur
        for cle in ('password', 'photo', 'fiche', 'token'):
            assert cle not in brut.lower()
    client.force_login(acteurs['comptes']['su'])
    page = client.get(reverse('membre-view', kwargs={'id': cible.id})).content.decode()
    assert 'suppression_demandee' not in page and '"is_delete"' not in page  # avant / après jamais affichés


def test_F25_reval_notification_pour_une_action_reussie_pas_pour_un_refus(client, acteurs, cible):
    _agir(client, acteurs, 'p1', cible, 'demander')
    assert Notification.objects.count() == 0
    _agir(client, acteurs, 'p1', cible, 'demander', motif='Doublon')
    assert Notification.objects.filter(membre=cible).count() == 1
