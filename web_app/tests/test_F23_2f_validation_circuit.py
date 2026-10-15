"""Validation indépendante du lot « état unique » (testeur) : circuit § 4.4, renvoi, reprise, suppression et restauration,
« Valider tout le monde », droits hérités, mise à jour perdue. Données fictives ; fixtures propres à ce fichier."""
import pytest
from django.core.exceptions import PermissionDenied
from django.test import Client
from django.urls import reverse

from compte import roles
from compte.models import Compte, JournalAction
from compte.services.nominations import creer_nomination
from coptapp.models import Antenne, Membre, Notification, Province
from coptapp.services import transitions as T
from tests.conftest import forcer_etat
from tests.test_plan_url import hachage_rapide, jeu  # noqa: F401

A = JournalAction.Action
CIRCUIT = ('saisi', 'valide_antenne', 'valide_province', 'actif')


@pytest.fixture
def mo(jeu):
    P = jeu['province']
    Q = Province.objects.create(nom='Quest', sigle='QU', code='QU')
    Antenne.objects.filter(pk=jeu['antenne'].pk).update(coordination=P)
    ant = Antenne.objects.get(pk=jeu['antenne'].pk)
    ant2 = Antenne.objects.create(nom='Antenne P2', coordination=P)
    antq = Antenne.objects.create(nom='Antenne Q', coordination=Q)
    su = jeu['compte']
    forcer_etat(jeu['membre'], 'actif')  # le membre du jeu ne doit pas fausser les comptages

    def nommer(nom, role, **p):
        c = Compte.objects.create_user(nom, password='x')
        creer_nomination(su, c, role, **p)
        return Compte.objects.get(pk=c.pk)

    c = {'su': su, 'pr': nommer('pr', roles.PR), 'vn': nommer('vn', roles.VN), 'vp': nommer('vp', roles.VP, coordination=P),
         'va': nommer('va', roles.VA, antenne=ant), 'va2': nommer('va2', roles.VA, antenne=ant),
         'va_p2': nommer('va_p2', roles.VA, antenne=ant2), 'vp_q': nommer('vp_q', roles.VP, coordination=Q),
         'va_q': nommer('va_q', roles.VA, antenne=antq), 'at': nommer('at', roles.AT, antenne=ant),
         'vi': nommer('vi', roles.VI), 'ed': nommer('ed', roles.ED), 'nu': Compte.objects.create_user('nu', password='x')}
    return {'c': c, 'P': P, 'Q': Q, 'ant': ant, 'ant2': ant2, 'antq': antq}


def saisir(mo, nom, etat='saisi', **kw):
    kw.setdefault('antenne', mo['ant'])
    kw.setdefault('province', mo['P'])
    kw.setdefault('user', mo['c']['at'])
    m = Membre.objects.create(nom=nom, **kw)
    return forcer_etat(m, etat) if etat != 'saisi' else m


def etat(m):
    return Membre.objects.get(pk=m.pk).etat


def n_journal(action, m=None):
    q = JournalAction.objects.filter(action=action)
    return q.filter(objet_id=m.pk).count() if m else q.count()


# ================================================================ circuit § 4.4

@pytest.mark.parametrize('role, depart, arrivee', [
    ('va', 'saisi', 'valide_antenne'), ('vp', 'valide_antenne', 'valide_province'), ('vn', 'valide_province', 'actif')])
def test_F23_2f_chaque_validateur_pose_son_etape_et_une_seule(mo, role, depart, arrivee):
    m = saisir(mo, 'Dossier', depart)
    assert T.valider(mo['c'][role], m) == [arrivee]
    assert etat(m) == arrivee
    ligne = JournalAction.objects.get(action=A.VALIDATION, objet_id=m.pk)
    assert ligne.avant == {'etat': depart} and ligne.apres == {'etat': arrivee} and ligne.auteur == mo['c'][role]


@pytest.mark.parametrize('role', ['va', 'vp', 'vn'])
@pytest.mark.parametrize('depart', CIRCUIT + ('renvoye', 'a_renouveler', 'supprime'))
def test_F23_2f_un_validateur_ne_valide_que_son_etat_de_depart(mo, role, depart):
    propre = {'va': 'saisi', 'vp': 'valide_antenne', 'vn': 'valide_province'}[role]
    m = saisir(mo, 'Dossier', depart)
    resultat = T.valider(mo['c'][role], m)
    if depart == propre:
        assert resultat
    else:  # étape précédente exigée, étapes suivantes interdites, états hors circuit refusés
        assert resultat == [] and etat(m) == depart and n_journal(A.VALIDATION, m) == 0


@pytest.mark.parametrize('role', ['pr', 'su'])
@pytest.mark.parametrize('depart, attendu', [
    ('saisi', ['valide_antenne', 'valide_province', 'actif']), ('valide_antenne', ['valide_province', 'actif']),
    ('valide_province', ['actif']), ('actif', []), ('renvoye', []), ('a_renouveler', []), ('supprime', [])])
def test_F23_2f_pr_et_su_enchainent_avec_une_ligne_de_journal_par_etape(mo, role, depart, attendu):
    m = saisir(mo, 'Dossier', depart)
    assert T.valider(mo['c'][role], m) == attendu
    assert etat(m) == (attendu[-1] if attendu else depart)
    lignes = list(JournalAction.objects.filter(action=A.VALIDATION, objet_id=m.pk).order_by('pk'))
    assert [l.apres['etat'] for l in lignes] == attendu
    assert [l.avant['etat'] for l in lignes] == ([depart] + attendu[:-1] if attendu else [])
    m.refresh_from_db()
    assert m.is_validate3 == (etat(m) in ('actif', 'a_renouveler')) and m.is_delete == (depart == 'supprime')


def test_F23_2f_valider_est_idempotent_et_deux_validateurs_ne_doublent_pas(mo):
    m = saisir(mo, 'Dossier')
    assert T.valider(mo['c']['va'], m) == ['valide_antenne']
    assert T.valider(mo['c']['va2'], m) == []  # relu sous verrou : déjà validé, rien n'est écrit
    assert T.valider(mo['c']['va'], m) == [] and n_journal(A.VALIDATION, m) == 1


@pytest.mark.parametrize('profil', ['at', 'vi', 'ed', 'nu', 'va_q', 'va_p2'])
def test_F23_2f_sans_droit_ou_hors_perimetre_rien_ne_se_valide(mo, profil):
    m = saisir(mo, 'Dossier')
    assert T.valider(mo['c'][profil], m) == [] and etat(m) == 'saisi'


def test_F23_2f_propres_saisies_et_propre_fiche_refusees_sauf_au_su(mo):
    c = mo['c']
    for role, depart in (('va', 'saisi'), ('vp', 'valide_antenne'), ('vn', 'valide_province'), ('pr', 'saisi')):
        saisie = saisir(mo, f'Saisie de {role}', depart, user=c[role])
        assert T.valider(c[role], saisie) == [], role
        fiche = saisir(mo, f'Fiche de {role}', depart)
        Compte.objects.filter(pk=c[role].pk).update(membreId=fiche.pk)
        assert T.valider(Compte.objects.get(pk=c[role].pk), fiche) == [], role
    mine = saisir(mo, 'Saisie du SU', 'saisi', user=c['su'])
    assert T.valider(c['su'], mine) == ['valide_antenne', 'valide_province', 'actif']


def test_F23_2f_vues_validate_404_hors_perimetre_403_sans_droit_302_nominal(client, mo):
    m = saisir(mo, 'Dossier')
    url = reverse('validate', kwargs={'id': m.pk})
    assert Client().post(url).status_code == 302 and etat(m) == 'saisi'
    for profil, statut in (('va_q', 404), ('vp_q', 404), ('va_p2', 404), ('nu', 404), ('vi', 404), ('ed', 404)):
        client.force_login(mo['c'][profil])
        assert client.post(url).status_code == statut, profil
    client.force_login(mo['c']['at'])
    assert client.post(url).status_code == 403
    assert etat(m) == 'saisi'
    client.force_login(mo['c']['va'])
    assert client.get(url).status_code == 405 and etat(m) == 'saisi'
    assert client.post(url).status_code == 302 and etat(m) == 'valide_antenne'
    c = Client(enforce_csrf_checks=True)
    c.force_login(mo['c']['vp'])
    assert c.post(reverse('validate', kwargs={'id': m.pk})).status_code == 403 and etat(m) == 'valide_antenne'


# ================================================================ renvoi

def _notifies(m):
    return sorted(Notification.objects.filter(membre=m, titre__startswith='Fiche renvoyée').values_list('user__username', flat=True))


@pytest.mark.parametrize('role, depart, cible, destinataires', [
    ('vn', 'valide_province', 'valide_antenne', ['vp']),   # un cran plus bas : on prévient le niveau province
    ('vp', 'valide_antenne', 'saisi', ['va', 'va2']),       # un cran plus bas : les validateurs d'antenne
    ('va', 'saisi', 'renvoye', ['at']),                     # l'agent de terrain, auteur de la saisie
    ('pr', 'valide_antenne', 'saisi', ['va', 'va2']),
])
def test_F23_2f_renvoi_au_niveau_juste_en_dessous_et_notification_du_bon_niveau(mo, role, depart, cible, destinataires):
    m = saisir(mo, 'Dossier', depart)
    assert T.renvoyer(mo['c'][role], m, 'Photo illisible') == 'renvoye'
    m.refresh_from_db()
    assert m.etat == cible and m.motif_renvoi == 'Photo illisible'
    assert _notifies(m) == destinataires
    assert all(n.description == 'Photo illisible' for n in Notification.objects.filter(membre=m))
    ligne = JournalAction.objects.get(action=A.RENVOI, objet_id=m.pk)
    assert ligne.avant == {'etat': depart} and ligne.apres == {'etat': cible} and ligne.motif == 'Photo illisible'


def test_F23_2f_renvoi_sans_destinataire_au_niveau_prevenu_l_auteur_de_la_saisie(mo):
    from compte.models import Nomination
    Nomination.objects.filter(role='VP', compte=mo['c']['vp']).update(active=False)
    m = saisir(mo, 'Dossier', 'valide_province')
    T.renvoyer(mo['c']['vn'], m, 'Motif')
    assert _notifies(m) == ['at']  # repli : personne ne reste sans nouvelle


def test_F23_2f_renvoi_motif_obligatoire_borne_et_droit_de_l_etape(mo):
    m = saisir(mo, 'Dossier', 'valide_antenne')
    for motif in ('', '   ', None):
        assert T.renvoyer(mo['c']['vp'], m, motif) == 'motif_requis'
    assert T.renvoyer(mo['c']['vp'], m, 'x' * 501) == 'motif_trop_long' and etat(m) == 'valide_antenne'
    for profil in ('va', 'vn', 'at', 'vi', 'ed', 'nu', 'va_q', 'vp_q'):  # pas leur étape, ou hors périmètre
        with pytest.raises(PermissionDenied):
            T.renvoyer(mo['c'][profil], m, 'Motif')
    assert etat(m) == 'valide_antenne' and n_journal(A.RENVOI) == 0 and Notification.objects.count() == 0
    assert T.renvoyer(mo['c']['vp'], m, 'x' * 500) == 'renvoye'


def test_F23_2f_renvoi_d_un_actif_ou_d_un_renvoye_impossible(mo):
    for depart in ('actif', 'renvoye', 'a_renouveler', 'supprime'):
        m = saisir(mo, f'Dossier {depart}', depart)
        for role in ('pr', 'su', 'vn'):
            try:
                resultat = T.renvoyer(mo['c'][role], m, 'Motif')
            except PermissionDenied:
                continue
            assert resultat != 'renvoye', (depart, role)
        assert etat(m) == depart


def test_F23_2f_le_motif_s_efface_quand_le_dossier_avance(mo):
    m = saisir(mo, 'Dossier', 'valide_antenne')
    T.renvoyer(mo['c']['vp'], m, 'Pièce manquante')
    assert Membre.objects.get(pk=m.pk).motif_renvoi == 'Pièce manquante'
    T.valider(mo['c']['va'], m)
    assert Membre.objects.get(pk=m.pk).motif_renvoi == '' and etat(m) == 'valide_antenne'


def test_F23_2f_vue_renvoyer_404_403_et_motif_vide(client, mo):
    m = saisir(mo, 'Dossier', 'valide_antenne')
    url = reverse('renvoyer-membre', kwargs={'id': m.pk})
    assert client.post(url, {'motif': 'x'}).status_code == 302
    for profil, statut in (('va_q', 404), ('nu', 404), ('va', 403), ('at', 403)):
        client.force_login(mo['c'][profil])
        assert client.post(url, {'motif': 'Motif'}).status_code == statut, profil
    client.force_login(mo['c']['vp'])
    assert client.get(url).status_code == 405
    assert client.post(url, {'motif': ''}).status_code == 302 and etat(m) == 'valide_antenne'
    assert client.post(url, {'motif': 'Motif réel'}).status_code == 302 and etat(m) == 'saisi'
    c = Client(enforce_csrf_checks=True)
    c.force_login(mo['c']['va'])
    assert c.post(reverse('renvoyer-membre', kwargs={'id': m.pk}), {'motif': 'x'}).status_code == 403 and etat(m) == 'saisi'


# ================================================================ reprise

def test_F23_2f_reprise_reservee_a_l_auteur_de_la_saisie(mo):
    m = saisir(mo, 'Dossier', 'renvoye', motif_renvoi='Motif')
    for profil in ('va', 'vp', 'pr', 'vn', 'nu', 'vi'):  # même un validateur ou un PR ne reprend pas la saisie d'un autre
        with pytest.raises(PermissionDenied):
            T.reprendre(mo['c'][profil], m)
    autre_agent = Compte.objects.create_user('autre-at', password='x')
    creer_nomination(mo['c']['su'], autre_agent, roles.AT, antenne=mo['ant'])
    with pytest.raises(PermissionDenied):
        T.reprendre(Compte.objects.get(pk=autre_agent.pk), m)
    assert etat(m) == 'renvoye'
    T.reprendre(mo['c']['at'], m)
    m.refresh_from_db()
    assert m.etat == 'saisi' and m.motif_renvoi == '' and not m.renvoye
    ligne = JournalAction.objects.get(action=A.MODIFICATION, objet_id=m.pk)
    assert ligne.avant == {'etat': 'renvoye'} and ligne.apres == {'etat': 'saisi'}


def test_F23_2f_reprise_par_le_su_et_sur_un_membre_non_renvoye(mo):
    m = saisir(mo, 'Dossier', 'renvoye')
    T.reprendre(mo['c']['su'], m)
    assert etat(m) == 'saisi'
    with pytest.raises(T.EtatIncoherent):
        T.reprendre(mo['c']['su'], m)


def test_F23_2f_reprise_par_modification_de_la_fiche_par_l_auteur_seulement(client, mo):
    m = saisir(mo, 'Dossier', 'renvoye', motif_renvoi='Motif')
    url = reverse('membre-view', kwargs={'id': m.pk})
    client.force_login(mo['c']['va'])
    client.post(url, {'nom': 'Modifié par VA'})
    assert etat(m) == 'renvoye'
    client.force_login(mo['c']['at'])
    client.post(url, {'nom': 'Modifié par l auteur'})
    m.refresh_from_db()
    assert m.etat in ('renvoye', 'saisi')  # voir l'assertion suivante : si le nom a changé, la reprise est faite
    if m.nom == 'Modifié par l auteur':
        assert m.etat == 'saisi'


# ================================================================ suppression et restauration

@pytest.mark.parametrize('avant', CIRCUIT + ('renvoye', 'a_renouveler'))
def test_F23_2f_restauration_retour_a_l_etat_d_avant(mo, avant):
    m = saisir(mo, 'Dossier', avant)
    T.supprimer(mo['c']['pr'], m, 'Doublon')
    m.refresh_from_db()
    assert m.etat == 'supprime' and m.etat_precedent == avant and m.is_delete and m.motif_suppression == 'Doublon'
    T.restaurer(mo['c']['pr'], m, 'Erreur')
    m.refresh_from_db()
    assert m.etat == avant and m.etat_precedent == '' and not m.is_delete and m.motif_suppression == ''
    expected = {'saisi': (False, False), 'valide_antenne': (True, False), 'valide_province': (True, False), 'actif': (True, True),
                'renvoye': (False, False), 'a_renouveler': (True, True)}[avant]
    assert (m.is_validate2, m.is_validate3) == expected and m.renvoye == (avant == 'renvoye')
    assert n_journal(A.SUPPRESSION, m) == 1 and n_journal(A.RESTAURATION, m) == 1


def test_F23_2f_suppression_restauration_droits_et_incoherences(mo):
    m = saisir(mo, 'Dossier', 'actif')
    for profil in ('va', 'vp', 'at', 'vi', 'ed', 'nu', 'va_q'):
        with pytest.raises(PermissionDenied):
            T.supprimer(mo['c'][profil], m, 'x')
    T.supprimer(mo['c']['vn'], m, 'x')
    with pytest.raises(T.EtatIncoherent):
        T.supprimer(mo['c']['vn'], m, 'x')
    for profil in ('va', 'vp', 'at'):
        with pytest.raises(PermissionDenied):
            T.restaurer(mo['c'][profil], m, 'x')
    T.restaurer(mo['c']['su'], m, 'x')
    with pytest.raises(T.EtatIncoherent):
        T.restaurer(mo['c']['su'], m, 'x')


def test_F23_2f_restauration_sans_etat_precedent_valide_retombe_sur_saisi(mo):
    m = saisir(mo, 'Dossier', 'actif')
    Membre.objects.filter(pk=m.pk).update(etat='supprime', etat_precedent='n-importe-quoi')
    T.restaurer(mo['c']['su'], Membre.objects.get(pk=m.pk), 'x')
    assert etat(m) == 'saisi'


def test_F23_2f_un_membre_supprime_n_est_pas_valide(mo):
    m = saisir(mo, 'Dossier', 'valide_antenne')
    T.supprimer(mo['c']['pr'], m, 'x')
    for profil in ('vp', 'pr', 'su'):
        assert T.valider(mo['c'][profil], Membre.objects.get(pk=m.pk)) == []
    assert etat(m) == 'supprime'


# ================================================================ « Valider tout le monde »

def _tous(client, profil, donnees=None, **extra):
    client.force_login(mo_comptes[profil])
    return client.post(reverse('valider-tous'), donnees or {}, **extra)


mo_comptes = {}


@pytest.fixture
def comptes(mo):
    mo_comptes.clear()
    mo_comptes.update(mo['c'])
    return mo['c']


def test_F23_2f_valider_tous_limite_au_perimetre_et_a_l_etape(client, mo, comptes):
    mien = [saisir(mo, f'Mien {i}') for i in range(3)]
    autre_antenne = saisir(mo, 'Autre antenne P', antenne=mo['ant2'])
    autre_coord = saisir(mo, 'Autre coord', antenne=mo['antq'], province=mo['Q'])
    deja = saisir(mo, 'Déjà validé', 'valide_antenne')
    renvoye = saisir(mo, 'Renvoyé', 'renvoye')
    supprime = saisir(mo, 'Supprimé', 'supprime')
    propre = saisir(mo, 'Propre saisie', user=comptes['va'])
    r = _tous(client, 'va')
    assert r.status_code == 302
    assert [etat(m) for m in mien] == ['valide_antenne'] * 3
    assert etat(autre_antenne) == 'saisi' and etat(autre_coord) == 'saisi' and etat(deja) == 'valide_antenne'
    assert etat(renvoye) == 'renvoye' and etat(supprime) == 'supprime' and etat(propre) == 'saisi'
    assert n_journal(A.VALIDATION) == 3


@pytest.mark.parametrize('profil, depart, arrivee', [('vp', 'valide_antenne', 'valide_province'), ('vn', 'valide_province', 'actif')])
def test_F23_2f_valider_tous_chaque_validateur_a_son_etape(client, mo, comptes, profil, depart, arrivee):
    cible = saisir(mo, 'Cible', depart)
    autres = [saisir(mo, f'Autre {e}', e) for e in CIRCUIT if e != depart]
    _tous(client, profil)
    assert etat(cible) == arrivee
    assert [etat(m) for m in autres] == [e for e in CIRCUIT if e != depart]


def test_F23_2f_valider_tous_pr_et_su_enchainent_et_le_su_valide_ses_saisies(client, mo, comptes):
    a = saisir(mo, 'A')
    b = saisir(mo, 'B', 'valide_province')
    s = saisir(mo, 'Saisie du SU', user=comptes['su'])
    _tous(client, 'pr')
    assert etat(a) == etat(b) == 'actif' and etat(s) == 'actif'  # le PR valide aussi la saisie du SU : ce n'est pas la sienne
    assert n_journal(A.VALIDATION, a) == 3 and n_journal(A.VALIDATION, b) == 1
    pr_saisie = saisir(mo, 'Saisie du PR', user=comptes['pr'])
    _tous(client, 'pr')
    assert etat(pr_saisie) == 'saisi'
    _tous(client, 'su')
    assert etat(pr_saisie) == 'actif'
    su_saisie = saisir(mo, 'Saisie su 2', user=comptes['su'])
    _tous(client, 'su')
    assert etat(su_saisie) == 'actif'


def test_F23_2f_valider_tous_idempotent(client, mo, comptes):
    for i in range(4):
        saisir(mo, f'M{i}')
    _tous(client, 'va')
    avant = n_journal(A.VALIDATION)
    _tous(client, 'va')
    _tous(client, 'va')
    assert n_journal(A.VALIDATION) == avant == 4


def test_F23_2f_valider_tous_plafond_configurable_et_reprise(client, mo, comptes, settings):
    settings.VALIDER_TOUS_PLAFOND = 3
    membres = [saisir(mo, f'M{i}') for i in range(7)]
    assert T.plafond_valider_tous() == 3
    cr = T.valider_tous(comptes['va'])
    assert (cr['valides'], cr['restants'], cr['plafond']) == (3, 4, 3)
    assert sum(etat(m) == 'valide_antenne' for m in membres) == 3
    cr = T.valider_tous(comptes['va'])
    assert (cr['valides'], cr['restants']) == (3, 1)
    cr = T.valider_tous(comptes['va'])
    assert (cr['valides'], cr['restants']) == (1, 0)
    assert T.valider_tous(comptes['va'])['valides'] == 0
    assert all(etat(m) == 'valide_antenne' for m in membres) and n_journal(A.VALIDATION) == 7
    r = _tous(client, 'va')  # message : rien à valider
    assert r.status_code == 302


def test_F23_2f_valider_tous_plafond_par_defaut_100(mo, comptes, settings):
    if hasattr(settings, 'VALIDER_TOUS_PLAFOND'):
        del settings.VALIDER_TOUS_PLAFOND
    assert T.plafond_valider_tous() == 100 == T.PLAFOND_PAR_DEFAUT
    Membre.objects.bulk_create([Membre(nom=f'Lot {i}', antenne=mo['ant'], province=mo['P'], user=comptes['at']) for i in range(105)])
    cr = T.valider_tous(comptes['va'])
    assert cr['valides'] == 100 and cr['restants'] == 5
    assert Membre.objects.filter(etat='valide_antenne').count() == 100


def test_F23_2f_valider_tous_plafond_nul_ou_negatif_reste_borne(mo, comptes, settings):
    settings.VALIDER_TOUS_PLAFOND = 0
    assert T.plafond_valider_tous() == 1
    settings.VALIDER_TOUS_PLAFOND = -5
    assert T.plafond_valider_tous() == 1


def test_F23_2f_valider_tous_filtres_forges_jamais_hors_perimetre(client, mo, comptes):
    cible_q = saisir(mo, 'Quest', antenne=mo['antq'], province=mo['Q'])
    p2 = saisir(mo, 'Autre antenne', antenne=mo['ant2'])
    mien = saisir(mo, 'Mien Alpha')
    forges = [{'antenne': mo['antq'].id}, {'antenne': mo['ant2'].id}, {'antenne': 'abc'}, {'antenne': '99999999999999999999999'},
              {'etat': 'supprime'}, {'etat': 'actif'}, {'etat': "x' OR 1=1"}, {'q': 'Quest'}, {'q': '%'}, {'q': 'a' * 5000},
              {'association': 999999}, {'qualite': 'ZZ'}, {'ids': cible_q.id}, {'pk': cible_q.id}, {'membre': cible_q.id}]
    for donnees in forges:
        r = _tous(client, 'va', donnees)
        assert r.status_code in (302, 204), donnees
        assert etat(cible_q) == 'saisi' and etat(p2) == 'saisi', donnees
    assert etat(mien) in ('saisi', 'valide_antenne')


def test_F23_2f_valider_tous_les_filtres_de_la_liste_s_appliquent(client, mo, comptes):
    alpha, beta = saisir(mo, 'Alpha Unique'), saisir(mo, 'Beta Unique')
    _tous(client, 'va', {'q': 'Alpha'})
    assert etat(alpha) == 'valide_antenne' and etat(beta) == 'saisi'
    assert T.compter_validables(comptes['va'], {'q': 'Beta'}) == 1
    assert T.compter_validables(comptes['va'], {'q': 'Zzz'}) == 0
    assert T.compter_validables(comptes['va'], {}) == 1


@pytest.mark.parametrize('profil', ['at', 'vi', 'ed', 'nu'])
def test_F23_2f_valider_tous_refuse_sans_role_valideur(client, mo, comptes, profil):
    m = saisir(mo, 'Dossier')
    assert _tous(client, profil).status_code == 403 and etat(m) == 'saisi'
    with pytest.raises(PermissionDenied):
        T.valider_tous(comptes[profil])


def test_F23_2f_valider_tous_anonyme_get_et_csrf(client, mo, comptes):
    m = saisir(mo, 'Dossier')
    assert Client().post(reverse('valider-tous')).status_code == 302
    client.force_login(comptes['va'])
    assert client.get(reverse('valider-tous')).status_code == 405
    c = Client(enforce_csrf_checks=True)
    c.force_login(comptes['va'])
    assert c.post(reverse('valider-tous')).status_code == 403 and etat(m) == 'saisi'


def test_F23_2f_valider_tous_fragment_et_page_complete(client, mo, comptes):
    saisir(mo, 'A')
    client.force_login(comptes['va'])
    r = client.post(reverse('valider-tous'), HTTP_HX_REQUEST='true')
    assert r.status_code == 204 and 'membresMaj' in r['HX-Trigger'] and 'modaleFermer' in r['HX-Trigger']
    saisir(mo, 'B')
    r = client.post(reverse('valider-tous'), HTTP_REFERER='http://testserver/membres/')
    assert r.status_code == 302 and r['Location'].endswith('/membres/')
    r = client.post(reverse('valider-tous'), HTTP_REFERER='http://evil.example/')
    assert r.status_code == 302 and 'evil' not in r['Location']
    r = client.post(reverse('valider-tous'), {'next': '//evil.example/'})
    assert r.status_code == 302 and 'evil' not in r['Location']


def test_F23_2f_valider_tous_droits_herites(client, mo, comptes, settings):
    settings.FENAMO_DROITS_HERITES = True
    m = saisir(mo, 'Dossier')
    for champs, statut in (({'privilege2': True}, 403), ({'privilege3': True}, 403), ({'privilege2': True, 'privilege3': True}, 403),
                           ({'privilege4': True}, 403), ({'privilege5': True}, 302)):
        Compte.objects.filter(username='herite').delete()
        h = Compte.objects.create_user('herite', password='x', **champs)
        comptes['herite'] = h
        client.force_login(h)
        assert client.post(reverse('valider-tous')).status_code == statut, champs
        if statut == 403:
            assert etat(m) == 'saisi', champs
    assert etat(m) == 'actif'  # privilege5 enchaîne toutes les étapes
    # privilege2 / privilege3 valident toujours membre par membre (étape par étape)
    m2 = saisir(mo, 'Dossier 2')
    p2 = Compte.objects.create_user('p2', password='x', privilege2=True)
    assert T.valider(p2, m2) == ['valide_antenne']
    p3 = Compte.objects.create_user('p3', password='x', privilege3=True)
    assert T.valider(p3, m2) == ['actif']


# ================================================================ mise à jour perdue

def test_F23_2f_save_d_une_instance_perimee_n_annule_pas_la_validation(mo):
    m = saisir(mo, 'Dossier')
    perime = Membre.objects.get(pk=m.pk)
    T.valider(mo['c']['va'], m)
    perime.nom = 'Nom corrigé'
    perime.save()  # aucun update_fields
    m.refresh_from_db()
    assert m.nom == 'Nom corrigé' and m.etat == 'valide_antenne' and m.is_validate2
    perime2 = Membre.objects.get(pk=m.pk)
    T.valider(mo['c']['vp'], m)
    perime2.telephone = '000'
    perime2.save(update_fields=['telephone'])
    m.refresh_from_db()
    assert m.etat == 'valide_province' and m.telephone == '000'


def test_F23_2f_save_perime_ne_reecrit_ni_le_motif_ni_la_suppression(mo):
    m = saisir(mo, 'Dossier', 'valide_antenne')
    perime = Membre.objects.get(pk=m.pk)
    T.renvoyer(mo['c']['vp'], m, 'Motif')
    T.supprimer(mo['c']['pr'], m, 'Doublon')
    perime.nom = 'Autre'
    perime.save()
    m.refresh_from_db()
    assert m.etat == 'supprime' and m.is_delete and m.nom == 'Autre'


def test_F23_2f_deux_validateurs_concurrents_via_instances_perimees(mo):
    m = saisir(mo, 'Dossier')
    a, b = Membre.objects.get(pk=m.pk), Membre.objects.get(pk=m.pk)
    assert T.valider(mo['c']['va'], a) == ['valide_antenne']
    assert T.valider(mo['c']['va2'], b) == []  # l'instance b est périmée : l'état est relu sous verrou
    assert n_journal(A.VALIDATION, m) == 1
