"""Revalidation indépendante (testeur) : circuit de validation d'un membre (F-23).

Ordre des étapes (p2 pose is_validate2, p3 pose is_validate3 seulement après), jamais sa propre fiche ni ses propres
saisies, double clic idempotent, deux validateurs simultanés, SU et privilege5 posent toutes les étapes manquantes.
"""
import pytest
from django.contrib.contenttypes.models import ContentType
from django.test import Client
from django.urls import reverse

from compte.models import Compte, JournalAction
from coptapp.models import Membre
from compte.services.droits import etapes_a_valider
from tests.test_F21_matrice_routes import acteurs  # noqa: F401
from tests.test_plan_url import hachage_rapide, jeu  # noqa: F401


def _membre(acteurs, nom='Candidat', **kw):
    """Membre saisi (is_validate1 par défaut), sans validation de l'antenne ni finale."""
    return Membre.objects.create(nom=nom, structure=acteurs['association'], province=acteurs['province'],
                                 antenne=acteurs['antenne'], **kw)


def _valider(client, acteurs, profil, membre, **donnees):
    client.force_login(acteurs['comptes'][profil])
    return client.post(reverse('validate', kwargs={'id': membre.id}), donnees)


def _drapeaux(membre):
    membre.refresh_from_db()
    return (membre.is_validate1, membre.is_validate2, membre.is_validate3)


def _lignes(membre, *actions):
    qs = JournalAction.objects.filter(objet_type=ContentType.objects.get_for_model(Membre), objet_id=membre.id)
    return qs.filter(action__in=actions) if actions else qs


# ---------------------------------------------------------------- ordre des étapes

def test_F23_ordre_des_etapes_p2_puis_p3(client, acteurs):
    m = _membre(acteurs)
    # p3 ne voit pas encore le membre (validé aux deux premières étapes seulement) : rien ne change
    assert _valider(client, acteurs, 'p3', m).status_code == 404
    assert _drapeaux(m) == (True, False, False)
    # p2 pose la première validation
    assert _valider(client, acteurs, 'p2', m).status_code == 302
    assert _drapeaux(m) == (True, True, False)
    ligne = _lignes(m, 'validation').get()
    assert ligne.auteur == acteurs['comptes']['p2']
    assert ligne.avant == {'etat': 'saisi'} and ligne.apres == {'etat': 'valide_antenne'}
    # p2 ne pose pas l'étape finale
    _valider(client, acteurs, 'p2', m)
    assert _drapeaux(m) == (True, True, False) and _lignes(m).count() == 1
    # p3 pose l'étape finale
    assert _valider(client, acteurs, 'p3', m).status_code == 302
    assert _drapeaux(m) == (True, True, True)
    assert _lignes(m, 'validation').count() == 2


def test_F23_aucune_etape_sautee_pour_p2_et_p3(acteurs):
    sans_v2 = _membre(acteurs)
    assert etapes_a_valider(acteurs['comptes']['p3'], sans_v2) == []  # étape précédente exigée
    assert etapes_a_valider(acteurs['comptes']['p2'], sans_v2) == ['valide_antenne']
    avec_v2 = _membre(acteurs, 'Deux', is_validate2=True)
    assert etapes_a_valider(acteurs['comptes']['p2'], avec_v2) == []
    assert etapes_a_valider(acteurs['comptes']['p3'], avec_v2) == ['actif']
    termine = _membre(acteurs, 'Fini', is_validate2=True, is_validate3=True)
    for profil in ('p2', 'p3', 'p5', 'su'):
        assert etapes_a_valider(acteurs['comptes'][profil], termine) == []


def test_F23_double_clic_idempotent_sans_nouvelle_ligne_de_journal(client, acteurs):
    m = _membre(acteurs)
    _valider(client, acteurs, 'p2', m)
    reponse = _valider(client, acteurs, 'p2', m)  # deuxième clic
    assert reponse.status_code == 302
    assert _drapeaux(m) == (True, True, False) and _lignes(m).count() == 1


def test_F23_su_pose_toutes_les_etapes_d_un_coup_puis_ne_refait_rien(client, acteurs):
    m = _membre(acteurs)
    _valider(client, acteurs, 'su', m)
    assert _drapeaux(m) == (True, True, True)
    lignes = list(_lignes(m).order_by('id'))  # une ligne par étape franchie
    assert [(l.avant['etat'], l.apres['etat']) for l in lignes] == [
        ('saisi', 'valide_antenne'), ('valide_antenne', 'valide_province'), ('valide_province', 'actif')]
    assert all(l.action == 'validation' for l in lignes)
    _valider(client, acteurs, 'su', m)
    assert _lignes(m).count() == 3


def test_F23_privilege5_pose_toutes_les_etapes(client, acteurs):
    m = _membre(acteurs)
    _valider(client, acteurs, 'p5', m)
    assert _drapeaux(m) == (True, True, True)


# ---------------------------------------------------------------- jamais sa propre fiche ni ses propres saisies

@pytest.mark.parametrize('profil', ['p2', 'p3', 'p5'])
def test_F23_auto_validation_interdite_sur_sa_propre_fiche(client, acteurs, profil):
    m = _membre(acteurs, 'Moi', is_validate2=(profil != 'p2'))
    Compte.objects.filter(pk=acteurs['comptes'][profil].pk).update(membreId=m.id)
    acteurs['comptes'][profil].refresh_from_db()
    avant = _drapeaux(m)
    r = _valider(client, acteurs, profil, m)
    assert r.status_code == 302 and _drapeaux(m) == avant and not _lignes(m).exists()
    assert etapes_a_valider(acteurs['comptes'][profil], m) == []


@pytest.mark.parametrize('profil', ['p2', 'p3', 'p5'])
def test_F23_auto_validation_interdite_sur_ses_propres_saisies(client, acteurs, profil):
    m = _membre(acteurs, 'Ma saisie', is_validate2=(profil != 'p2'), user=acteurs['comptes'][profil])
    avant = _drapeaux(m)
    r = _valider(client, acteurs, profil, m)
    assert r.status_code == 302 and _drapeaux(m) == avant and not _lignes(m).exists()


def test_F23_su_peut_valider_sa_propre_fiche_DECISION_A_CONFIRMER(client, acteurs):
    """CONSTAT, pas une approbation : le code exempte le super-utilisateur (compte technique du prestataire) de la
    séparation des tâches. A confirmer par la FENAMO : un SU peut-il valider sa propre fiche ou ses saisies ?"""
    m = _membre(acteurs, 'Fiche du SU')
    Compte.objects.filter(pk=acteurs['comptes']['su'].pk).update(membreId=m.id)
    acteurs['comptes']['su'].refresh_from_db()
    _valider(client, acteurs, 'su', m)
    assert _drapeaux(m) == (True, True, True)
    saisie = _membre(acteurs, 'Saisie du SU', user=acteurs['comptes']['su'])
    _valider(client, acteurs, 'su', saisie)
    assert _drapeaux(saisie) == (True, True, True)


# ---------------------------------------------------------------- refus de rôle et de périmètre

@pytest.mark.parametrize('profil, statut', [('p1', 403), ('nu', 404), ('ed', 404)])
def test_F23_refus_de_role_et_de_perimetre(client, acteurs, profil, statut):
    m = _membre(acteurs, user=acteurs['comptes']['p1'])
    assert _valider(client, acteurs, profil, m).status_code == statut
    assert _drapeaux(m) == (True, False, False)


def test_F23_visiteur_ne_valide_jamais(client, acteurs):
    m = _membre(acteurs, 'Actif', is_validate2=True, is_validate3=True)
    assert _valider(client, acteurs, 'p4', m).status_code == 403
    cumul = Compte.objects.create_user('p2p4', password='x', privilege2=True, privilege4=True)
    client.force_login(cumul)
    r = client.post(reverse('validate', kwargs={'id': _membre(acteurs, 'Autre').id}))
    assert r.status_code in (403, 404)


def test_F23_membre_supprime_non_validable(client, acteurs):
    m = _membre(acteurs, is_delete=True)
    assert _valider(client, acteurs, 'su', m).status_code == 404
    assert _drapeaux(m) == (True, False, False)


def test_F23_get_interdit_et_csrf_exige(acteurs):
    m = _membre(acteurs)
    client = Client(enforce_csrf_checks=True)
    client.force_login(acteurs['comptes']['p2'])
    url = reverse('validate', kwargs={'id': m.id})
    assert client.get(url).status_code == 405
    assert client.post(url).status_code == 403
    assert _drapeaux(m) == (True, False, False)


def test_F23_retour_refuse_une_adresse_externe(client, acteurs):
    m = _membre(acteurs)
    r = _valider(client, acteurs, 'p2', m, next='https://evil.example/hameconnage')
    assert r.status_code == 302 and 'evil.example' not in r['Location']
    r = _valider(client, acteurs, 'p2', m, next='//evil.example/x')
    assert 'evil.example' not in r['Location']
    r = _valider(client, acteurs, 'p2', m, next='/membres/?page=2')
    assert r['Location'] == '/membres/?page=2'


# ---------------------------------------------------------------- deux validateurs simultanés

def test_F23_deux_validateurs_simultanes_drapeaux_coherents(client, acteurs, monkeypatch):
    """Simule deux p2 qui lisent le membre avant que l'autre écrive : l'état final est correct (is_validate2 posé)."""
    import coptapp.services.transitions as vues
    m = _membre(acteurs)
    second = Compte.objects.create_user('p2bis', password='x', privilege2=True)
    acteurs['comptes']['p2bis'] = second
    original = vues.etapes_a_valider
    deja = {'fait': False}

    def entrelace(user, membre):
        calcule = original(user, membre)  # lecture « périmée » : is_validate2 encore faux
        if not deja['fait']:
            deja['fait'] = True
            autre = Client()
            autre.force_login(second)
            assert autre.post(reverse('validate', kwargs={'id': m.id})).status_code == 302  # l'autre écrit en premier
        return calcule

    monkeypatch.setattr(vues, 'etapes_a_valider', entrelace)
    assert _valider(client, acteurs, 'p2', m).status_code == 302
    assert _drapeaux(m) == (True, True, False)


def test_F23_deux_validateurs_simultanes_une_seule_ligne_de_journal(acteurs):
    """Deux validateurs dont la lecture du membre est PÉRIMÉE (chacun a chargé l'instance avant l'écriture de l'autre) :
    l'état est relu sous verrou, une seule étape est posée et une seule ligne est journalisée."""
    from coptapp.services.transitions import valider as valider_membre
    m = _membre(acteurs)
    second = Compte.objects.create_user('p2ter', password='x', privilege2=True)
    lecture_a, lecture_b = Membre.objects.get(pk=m.pk), Membre.objects.get(pk=m.pk)  # deux lectures avant toute écriture
    assert valider_membre(acteurs['comptes']['p2'], lecture_a) == ['valide_antenne']
    assert valider_membre(second, lecture_b) == []  # l'étape est déjà posée : rien à faire
    assert _drapeaux(m) == (True, True, False)
    assert _lignes(m, 'validation').count() == 1


def test_F23_validation_n_ecrase_pas_une_modification_concurrente(client, acteurs, monkeypatch):
    """La validation n'enregistre que les drapeaux (update_fields) : un changement de nom survenu entre-temps survit."""
    import coptapp.services.transitions as vues
    m = _membre(acteurs)
    original = vues.etapes_a_valider

    def entrelace(user, membre):
        calcule = original(user, membre)
        Membre.objects.filter(pk=membre.pk).update(nom='Nom corrigé ailleurs')
        return calcule

    monkeypatch.setattr(vues, 'etapes_a_valider', entrelace)
    _valider(client, acteurs, 'p2', m)
    m.refresh_from_db()
    assert m.nom == 'Nom corrigé ailleurs' and m.is_validate2


def test_F23_renvoi_au_niveau_inferieur_pas_encore_livre(client, acteurs):
    """Le renvoi avec motif n'existe pas encore (la vue le dit) : aucune route ne retire une validation."""
    m = _membre(acteurs, is_validate2=True, is_validate3=True)
    for profil in ('su', 'p5', 'p3', 'p2'):
        _valider(client, acteurs, profil, m, motif='Renvoi', renvoyer='1')
        assert _drapeaux(m) == (True, True, True)
