"""F-23 / F-25 : champ d'état unique du membre (Membre.etat), transitions (valider, renvoyer, reprendre, supprimer, restaurer,
renouveler), miroirs des anciens booléens, « Valider tout le monde » (valider_tous, compter_validables, vue valider-tous)."""
import pytest
from django.core.exceptions import PermissionDenied
from django.test import Client
from django.urls import reverse

from compte import roles
from compte.models import Compte, JournalAction
from compte.services import droits as D
from coptapp.models import Membre, Notification, miroirs_de
from coptapp.services import transitions as T
from coptapp.services.actions import traiter_suppression_membre
from coptapp.services.etats import etat_de, filtrer_membres_par_etat
from coptapp.services.tableau_bord import indicateurs_tableau_bord
from tests.conftest import forcer_etat
from tests.test_F02_droits_roles import _compte, _nommer, acteurs_roles, monde  # noqa: F401
from tests.test_plan_url import hachage_rapide, jeu  # noqa: F401

A = JournalAction.Action
ETATS = ('saisi', 'valide_antenne', 'valide_province', 'actif', 'renvoye', 'a_renouveler', 'supprime')


def _saisi(monde, nom='Dossier', **kw):
    """Membre de l'antenne P saisi par un agent qui n'est AUCUN des acteurs de test (jamais « sa propre saisie »)."""
    return Membre.objects.create(nom=nom, antenne=monde['antenne_p'], province=monde['P'], user=monde['agent'], **kw)


# ---------------------------------------------------------------- modèle : état unique et miroirs

@pytest.mark.django_db
@pytest.mark.parametrize('etat, attendu', [
    ('saisi', (False, False, False, False)), ('valide_antenne', (False, True, False, False)), ('valide_province', (False, True, False, False)),
    ('actif', (False, True, True, False)), ('renvoye', (False, False, False, True)), ('a_renouveler', (False, True, True, False)),
    ('supprime', (True, False, False, False))])
def test_F23_miroirs_deduits_de_l_etat(etat, attendu):
    m = Membre.objects.create(nom='Miroir', etat=etat)
    assert (m.is_delete, m.is_validate2, m.is_validate3, m.renvoye) == attendu
    m.refresh_from_db()
    assert (m.is_delete, m.is_validate2, m.is_validate3, m.renvoye) == attendu and etat_de(m) == etat


@pytest.mark.django_db
def test_F23_un_membre_supprime_garde_les_miroirs_de_son_etat_precedent():
    assert miroirs_de('supprime', 'actif') == {'is_delete': True, 'is_validate2': True, 'is_validate3': True, 'renvoye': False}
    m = Membre.objects.create(nom='Suppr', etat='supprime', etat_precedent='valide_antenne')
    assert m.is_delete and m.is_validate2 and not m.is_validate3


@pytest.mark.django_db
def test_F23_ecritures_heritees_des_booleens_sont_traduites_en_etat():
    m = Membre.objects.create(nom='Herite', is_validate2=True, is_validate3=True)  # création : état déduit
    assert m.etat == 'actif'
    m.is_validate3 = False
    m.save()
    assert m.etat == 'valide_antenne'
    Membre.objects.filter(pk=m.pk).update(is_validate2=False)  # update() de masse
    m.refresh_from_db()
    assert m.etat == 'saisi' and not m.is_validate2
    Membre.objects.filter(pk=m.pk).update(is_delete=True)
    m.refresh_from_db()
    assert m.etat == 'supprime' and m.etat_precedent == 'saisi'
    Membre.objects.filter(pk=m.pk).update(is_delete=False)
    m.refresh_from_db()
    assert m.etat == 'saisi' and m.etat_precedent == ''


@pytest.mark.django_db
def test_F23_ecrire_l_etat_met_les_miroirs_a_jour_meme_par_update():
    m = Membre.objects.create(nom='Etat')
    Membre.objects.filter(pk=m.pk).update(etat='actif')
    m.refresh_from_db()
    assert m.is_validate2 and m.is_validate3 and not m.renvoye
    m.etat = 'renvoye'
    m.save(update_fields=['etat'])
    m.refresh_from_db()
    assert m.renvoye and not m.is_validate2 and not m.is_validate3


# ---------------------------------------------------------------- matrice rôle x état : validation

ATTENDU_VALIDER = {
    'PR': {'saisi': ['valide_antenne', 'valide_province', 'actif'], 'valide_antenne': ['valide_province', 'actif'], 'valide_province': ['actif']},
    'VA': {'saisi': ['valide_antenne']},
    'VP': {'valide_antenne': ['valide_province']},
    'VN': {'valide_province': ['actif']},
    'AT': {}, 'VI': {}, 'ED': {},
}


@pytest.mark.parametrize('role', ['PR', 'VA', 'VP', 'VN', 'AT', 'VI', 'ED'])
@pytest.mark.parametrize('etat', ETATS)
def test_F23_matrice_validation_role_par_etat(monde, acteurs_roles, role, etat):
    m = forcer_etat(_saisi(monde), etat, precedent='actif')
    assert D.etapes_a_valider(acteurs_roles[role], m) == ATTENDU_VALIDER[role].get(etat, []), (role, etat)


@pytest.mark.django_db
def test_F23_le_superutilisateur_enchaine_et_peut_valider_ses_propres_saisies(monde):
    su = monde['compte']
    m = Membre.objects.create(nom='Saisie du SU', antenne=monde['antenne_p'], province=monde['P'], user=su)
    assert T.valider(su, m) == ['valide_antenne', 'valide_province', 'actif']


def test_F23_valider_ecrit_une_ligne_de_journal_par_etape(monde, acteurs_roles):
    m = _saisi(monde)
    assert T.valider(acteurs_roles['PR'], m) == ['valide_antenne', 'valide_province', 'actif']
    lignes = list(JournalAction.objects.filter(action=A.VALIDATION, objet_id=m.pk).order_by('id'))
    assert [(l.avant['etat'], l.apres['etat']) for l in lignes] == [('saisi', 'valide_antenne'), ('valide_antenne', 'valide_province'),
                                                                    ('valide_province', 'actif')]
    assert all(l.auteur == acteurs_roles['PR'] and l.role == 'PR' for l in lignes)
    m.refresh_from_db()
    assert m.etat == 'actif' and m.is_validate3
    assert T.valider(acteurs_roles['PR'], m) == []  # idempotent : rien de plus, aucune ligne de plus
    assert JournalAction.objects.filter(action=A.VALIDATION, objet_id=m.pk).count() == 3


def test_F23_circuit_complet_par_les_trois_validateurs(monde, acteurs_roles):
    m = _saisi(monde)
    for role, attendu in (('VA', 'valide_antenne'), ('VP', 'valide_province'), ('VN', 'actif')):
        assert T.valider(acteurs_roles[role], m) == [attendu]
        m.refresh_from_db()
        assert m.etat == attendu
    assert JournalAction.objects.filter(action=A.VALIDATION, objet_id=m.pk).count() == 3


def test_F23_jamais_sa_propre_fiche_ni_ses_saisies(monde, acteurs_roles):
    va = acteurs_roles['VA']
    propre = Membre.objects.create(nom='Saisie du VA', antenne=monde['antenne_p'], user=va)
    assert T.valider(va, propre) == []
    Compte.objects.filter(pk=va.pk).update(membreId=_saisi(monde, 'Fiche du VA').pk)
    assert T.valider(Compte.objects.get(pk=va.pk), Membre.objects.get(pk=Compte.objects.get(pk=va.pk).membreId)) == []


# ---------------------------------------------------------------- renvoi : reculer d'un cran

@pytest.mark.parametrize('role, depart, cible', [('VA', 'saisi', 'renvoye'), ('VP', 'valide_antenne', 'saisi'),
                                                 ('VN', 'valide_province', 'valide_antenne'), ('PR', 'valide_province', 'valide_antenne')])
def test_F23_renvoi_recule_d_un_cran_avec_motif(monde, acteurs_roles, role, depart, cible):
    m = forcer_etat(_saisi(monde), depart)
    assert T.renvoyer(acteurs_roles[role], m, 'Photo floue') == 'renvoye'
    m.refresh_from_db()
    assert m.etat == cible and m.motif_renvoi == 'Photo floue'
    assert (m.renvoye is True) == (cible == 'renvoye')  # « renvoye » seulement pour le retour à l'agent
    ligne = JournalAction.objects.get(action=A.RENVOI, objet_id=m.pk)
    assert ligne.avant == {'etat': depart} and ligne.apres == {'etat': cible} and ligne.motif == 'Photo floue'
    destinataire = {'renvoye': monde['agent'], 'saisi': acteurs_roles['VA'], 'valide_antenne': acteurs_roles['VP']}[cible]  # niveau où le dossier retourne
    assert Notification.objects.filter(user=destinataire, membre=m, description='Photo floue').exists()


def test_F23_renvoi_motif_obligatoire_et_droit_de_l_etape(monde, acteurs_roles):
    m = forcer_etat(_saisi(monde), 'valide_antenne')
    assert T.renvoyer(acteurs_roles['VP'], m, '  ') == 'motif_requis' and T.renvoyer(acteurs_roles['VP'], m, 'x' * 501) == 'motif_trop_long'
    for role in ('VA', 'VN', 'AT', 'VI'):  # ce n'est pas leur étape
        with pytest.raises(PermissionDenied):
            T.renvoyer(acteurs_roles[role], m, 'Motif')
    m.refresh_from_db()
    assert m.etat == 'valide_antenne' and not JournalAction.objects.filter(action=A.RENVOI).exists()


def test_F23_le_motif_est_efface_quand_le_dossier_avance(monde, acteurs_roles):
    m = forcer_etat(_saisi(monde), 'valide_province')
    T.renvoyer(acteurs_roles['VN'], m, 'À revoir')  # -> valide_antenne, motif affiché
    m.refresh_from_db()
    assert m.motif_renvoi == 'À revoir' and m.etat == 'valide_antenne'
    T.valider(acteurs_roles['VP'], m)
    m.refresh_from_db()
    assert m.etat == 'valide_province' and m.motif_renvoi == ''


def test_F23_reprendre_remet_un_renvoye_dans_le_circuit(monde, acteurs_roles):
    at = acteurs_roles['AT']  # l'agent de la saisie
    m = Membre.objects.create(nom='Renvoyé', antenne=monde['antenne_p'], province=monde['P'], user=at)
    T.renvoyer(acteurs_roles['VA'], m, 'Corriger')
    m.refresh_from_db()
    assert m.etat == 'renvoye'
    assert T.valider(acteurs_roles['VA'], m) == []  # un renvoyé n'est pas validable avant sa reprise
    T.reprendre(at, m)
    m.refresh_from_db()
    assert m.etat == 'saisi' and m.motif_renvoi == '' and not m.renvoye
    with pytest.raises(T.EtatIncoherent):
        T.reprendre(at, m)
    with pytest.raises(PermissionDenied):
        T.reprendre(acteurs_roles['VI'], forcer_etat(m, 'renvoye'))


# ---------------------------------------------------------------- suppression, restauration, renouvellement

def test_F25_restauration_rend_l_etat_d_avant_la_suppression(monde, acteurs_roles):
    for etat in ('saisi', 'valide_antenne', 'valide_province', 'actif'):
        m = forcer_etat(_saisi(monde, f'Suppr {etat}'), etat)
        T.supprimer(acteurs_roles['PR'], m, 'Doublon')
        m.refresh_from_db()
        assert m.etat == 'supprime' and m.etat_precedent == etat and m.is_delete and m.motif_suppression == 'Doublon'
        T.restaurer(acteurs_roles['PR'], m, 'Erreur')
        m.refresh_from_db()
        assert m.etat == etat and m.etat_precedent == '' and not m.is_delete and m.motif_suppression == ''
        assert JournalAction.objects.filter(action=A.SUPPRESSION, objet_id=m.pk).count() == 1
        assert JournalAction.objects.filter(action=A.RESTAURATION, objet_id=m.pk, apres={'etat': etat}).count() == 1


def test_F25_suppression_par_les_actions_explicites_passe_par_les_transitions(monde, acteurs_roles):
    m = forcer_etat(_saisi(monde), 'valide_antenne')
    assert traiter_suppression_membre(acteurs_roles['VA'], m, 'demander', 'Doublon') == 'demande'
    assert traiter_suppression_membre(acteurs_roles['VN'], m, 'executer', 'Doublon') == 'supprime'
    m.refresh_from_db()
    assert m.etat == 'supprime' and not m.suppression_demandee and m.etat_precedent == 'valide_antenne'
    with pytest.raises(T.EtatIncoherent):
        T.supprimer(acteurs_roles['PR'], m, 'Encore')
    assert traiter_suppression_membre(acteurs_roles['VN'], m, 'restaurer', 'Retour') == 'restaure'
    m.refresh_from_db()
    assert m.etat == 'valide_antenne'


def test_F23_a_renouveler_et_renouveler(monde, acteurs_roles):
    m = forcer_etat(_saisi(monde), 'actif')
    T.marquer_a_renouveler(acteurs_roles['PR'], m, 'Échéance')
    m.refresh_from_db()
    assert m.etat == 'a_renouveler' and m.is_validate3  # toujours compté actif par les miroirs hérités
    with pytest.raises(T.EtatIncoherent):
        T.marquer_a_renouveler(acteurs_roles['PR'], m)
    T.renouveler(acteurs_roles['PR'], m, 'Payé')
    m.refresh_from_db()
    assert m.etat == 'actif'
    with pytest.raises(PermissionDenied):
        T.marquer_a_renouveler(acteurs_roles['VI'], m)


def test_F23_filtres_et_visiteur_par_etat(monde, acteurs_roles):
    m = forcer_etat(_saisi(monde, 'Visible'), 'actif')
    cache = _saisi(monde, 'Non actif')
    visibles = set(D.membres_du_perimetre(acteurs_roles['VI']).values_list('pk', flat=True))
    assert m.pk in visibles and cache.pk not in visibles
    for etat in ETATS[:-1]:
        forcer_etat(cache, etat)
        assert filtrer_membres_par_etat(Membre.objects.all(), etat).filter(pk=cache.pk).exists()
    assert not filtrer_membres_par_etat(Membre.objects.all(), 'supprime').exists()


def test_F23_tableau_de_bord_une_agregation_par_etat(monde, acteurs_roles, django_assert_num_queries):
    for etat in ('saisi', 'valide_antenne', 'valide_province', 'valide_province', 'actif', 'renvoye'):
        forcer_etat(_saisi(monde, f'TB {etat}'), etat)
    pr = acteurs_roles['PR']
    indicateurs = indicateurs_tableau_bord(pr)
    assert indicateurs['valides_province'] == 2 and indicateurs['renvoyes'] == 1
    assert indicateurs['en_attente_total'] == indicateurs['saisis'] + indicateurs['valides_antenne'] + indicateurs['valides_province']
    assert [l['etat'] for l in indicateurs['graphique']['lignes']] == ['saisi', 'valide_antenne', 'valide_province', 'actif', 'renvoye']
    assert all(m.etat in ('saisi', 'valide_antenne', 'valide_province') for m in indicateurs['en_attente'])


# ---------------------------------------------------------------- droits hérités

def test_F23_droits_herites_privilege2_et_privilege3(monde):
    p2, p3 = _compte('p2-herite', privilege2=True), _compte('p3-herite', privilege3=True)
    m = _saisi(monde)
    assert D.etapes_a_valider(p2, m) == ['valide_antenne'] and D.etapes_a_valider(p3, m) == []
    forcer_etat(m, 'valide_antenne')
    assert D.etapes_a_valider(p2, m) == [] and D.etapes_a_valider(p3, m) == ['actif']  # étape nationale seule
    forcer_etat(m, 'valide_province')
    assert D.etapes_a_valider(p3, m) == ['actif']
    forcer_etat(m, 'renvoye')
    assert D.etapes_a_valider(p2, m) == [] and D.etapes_a_valider(p3, m) == []


# ---------------------------------------------------------------- « Valider tout le monde »

def test_F23_valider_tous_perimetre_etape_et_propres_saisies(monde, acteurs_roles):
    va = acteurs_roles['VA']
    a_valider = [_saisi(monde, f'A valider {i}') for i in range(3)]
    deja = forcer_etat(_saisi(monde, 'Deja valide'), 'valide_antenne')  # pas à l'étape du VA
    propre = Membre.objects.create(nom='Saisie du VA', antenne=monde['antenne_p'], province=monde['P'], user=va)
    ailleurs = monde['N2']  # antenne Q, état saisi : hors périmètre du VA
    avant_ailleurs = ailleurs.etat
    compte_rendu = T.valider_tous(va)
    assert compte_rendu['valides'] >= 3 and compte_rendu['restants'] == 0
    assert compte_rendu['ignores'].get('propres_saisies') == 1
    for m in a_valider:
        m.refresh_from_db()
        assert m.etat == 'valide_antenne'
    for m in (deja, propre, ailleurs):
        m.refresh_from_db()
    assert deja.etat == 'valide_antenne' and propre.etat == 'saisi' and ailleurs.etat == avant_ailleurs
    assert JournalAction.objects.filter(action=A.VALIDATION, auteur=va, objet_id__in=[m.pk for m in a_valider]).count() == 3  # 1 par membre


def test_F23_valider_tous_le_president_enchaine_les_etapes_une_ligne_par_etape(monde, acteurs_roles):
    pr = acteurs_roles['PR']
    m1, m2 = _saisi(monde, 'Chaine 1'), forcer_etat(_saisi(monde, 'Chaine 2'), 'valide_antenne')
    avant = JournalAction.objects.filter(action=A.VALIDATION).count()
    compte_rendu = T.valider_tous(pr)
    m1.refresh_from_db(), m2.refresh_from_db()
    assert m1.etat == 'actif' and m2.etat == 'actif'
    assert JournalAction.objects.filter(action=A.VALIDATION).count() - avant == compte_rendu['etapes'] >= 5  # 3 + 2 (+ ceux du jeu)


def test_F23_valider_tous_plafond_reste_signale_et_idempotent(monde, acteurs_roles):
    va = acteurs_roles['VA']
    base = T.compter_validables(va)
    for i in range(5):
        _saisi(monde, f'Plafond {i}')
    assert T.compter_validables(va) == base + 5
    premier = T.valider_tous(va, plafond=3)
    assert premier['valides'] == 3 and premier['restants'] == base + 2 and premier['plafond'] == 3
    second = T.valider_tous(va, plafond=100)
    assert second['valides'] == base + 2 and second['restants'] == 0
    troisieme = T.valider_tous(va)
    assert troisieme['valides'] == 0 and troisieme['restants'] == 0  # idempotent : plus rien à valider
    assert T.compter_validables(va) == 0


def test_F23_valider_tous_filtres_de_la_liste(monde, acteurs_roles):
    va = acteurs_roles['VA']
    voulu = _saisi(monde, 'Zebulon Cible')
    autre = _saisi(monde, 'Autre Personne')
    assert T.compter_validables(va, {'q': 'Zebulon'}) == 1
    T.valider_tous(va, {'q': 'Zebulon'})
    voulu.refresh_from_db(), autre.refresh_from_db()
    assert voulu.etat == 'valide_antenne' and autre.etat == 'saisi'


def test_F23_valider_tous_droits(monde, acteurs_roles):
    for role in ('AT', 'VI', 'ED'):
        assert not D.droits_membre(acteurs_roles[role])['peut_valider_tous'], role
        assert T.compter_validables(acteurs_roles[role]) == 0
        with pytest.raises(PermissionDenied):
            T.valider_tous(acteurs_roles[role])
    for role in ('PR', 'VA', 'VP', 'VN'):
        assert D.droits_membre(acteurs_roles[role])['peut_valider_tous'], role
    assert D.droits_membre(monde['compte'])['peut_valider_tous']
    assert not D.droits_membre(_compte('sans-privilege-herite', privilege1=True))['peut_valider_tous']
    assert not D.droits_membre(_compte('p2-vt', privilege2=True))['peut_valider_tous']  # jamais privilege2 ni privilege3
    assert not D.droits_membre(_compte('p3-vt', privilege3=True))['peut_valider_tous']
    assert D.droits_membre(_compte('p5-vt', privilege5=True))['peut_valider_tous']


def test_F23_valider_tous_chaque_validateur_a_son_etape(monde, acteurs_roles):
    saisi, antenne, province = _saisi(monde, 'E1'), forcer_etat(_saisi(monde, 'E2'), 'valide_antenne'), forcer_etat(_saisi(monde, 'E3'), 'valide_province')
    assert T.valider_tous(acteurs_roles['VN'])['valides'] >= 1
    for m in (saisi, antenne, province):
        m.refresh_from_db()
    assert (saisi.etat, antenne.etat, province.etat) == ('saisi', 'valide_antenne', 'actif')  # le VN ne touche que valide_province
    T.valider_tous(acteurs_roles['VP'])
    antenne.refresh_from_db()
    assert antenne.etat == 'valide_province'


# ---------------------------------------------------------------- vue valider-tous

def test_F23_vue_valider_tous_post_csrf_get_405_et_refus(monde, acteurs_roles):
    url = reverse('valider-tous')
    m = _saisi(monde, 'Via la vue')
    client = Client(enforce_csrf_checks=True)
    client.force_login(acteurs_roles['VA'])
    assert client.get(url).status_code == 405
    assert client.post(url).status_code == 403  # sans jeton CSRF
    sain = Client()
    sain.force_login(acteurs_roles['AT'])
    assert sain.post(url).status_code == 403  # l'agent ne valide aucune étape
    assert Client().post(url).status_code in (302, 403)  # anonyme
    m.refresh_from_db()
    assert m.etat == 'saisi'


def test_F23_vue_valider_tous_page_complete_et_fragment_htmx(client, monde, acteurs_roles):
    m1, m2 = _saisi(monde, 'Page 1'), _saisi(monde, 'Fragment 2')
    url = reverse('valider-tous')
    client.force_login(acteurs_roles['VA'])
    page = client.post(url, {'q': 'Page 1'}, HTTP_REFERER='http://testserver' + reverse('liste-membre'))
    assert page.status_code == 302 and page.url.endswith(reverse('liste-membre'))
    m1.refresh_from_db(), m2.refresh_from_db()
    assert m1.etat == 'valide_antenne' and m2.etat == 'saisi'  # le filtre de la liste est respecté
    fragment = client.post(url, {}, HTTP_HX_REQUEST='true')
    assert fragment.status_code == 204 and 'membresMaj' in fragment['HX-Trigger'] and 'toast' in fragment['HX-Trigger']
    m2.refresh_from_db()
    assert m2.etat == 'valide_antenne'


def test_F23_liste_expose_le_nombre_de_membres_validables(client, monde, acteurs_roles):
    _saisi(monde, 'Compteur 1'), _saisi(monde, 'Compteur 2')
    client.force_login(acteurs_roles['VA'])
    contexte = client.get(reverse('liste-membre')).context
    assert contexte['nb_validables'] >= 2 and contexte['peut_valider_tous']
    client.force_login(acteurs_roles['AT'])
    contexte = client.get(reverse('liste-membre')).context
    assert contexte['nb_validables'] == 0 and not contexte['peut_valider_tous']
