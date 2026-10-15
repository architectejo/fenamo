"""F-40 : communiqués reçus comme notifications dans l'application (publication ED et SU, ciblage, destinataires, « lu » par compte, compteur)."""
from datetime import timedelta

import pytest
from django.core.exceptions import PermissionDenied
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from compte import roles
from compte.models import Compte, JournalAction
from compte.services.nominations import creer_nomination
from coptapp.models import Antenne, Communique, LectureCommunique, Notification
from coptapp.services import communiques as S
from tests.test_F02_droits_roles import _compte, _nommer, acteurs_roles, monde  # noqa: F401
from tests.test_plan_url import hachage_rapide, jeu  # noqa: F401

A = JournalAction.Action


@pytest.fixture
def equipe(monde):
    """Un compte par rôle de terrain : P (antenne_p, antenne_p2) et Q (antenne_q)."""
    antenne_p2 = Antenne.objects.create(nom='Antenne P2', coordination=monde['P'], code='P2')
    e = {'ED': _nommer(monde, roles.ED), 'PR': _nommer(monde, roles.PR), 'VN': _nommer(monde, roles.VN),
         'VP_P': _nommer(monde, roles.VP, coordination=monde['P']), 'VP_Q': _nommer(monde, roles.VP, coordination=monde['Q']),
         'VA_P': _nommer(monde, roles.VA, antenne=monde['antenne_p']), 'AT_P': _nommer(monde, roles.AT, antenne=monde['antenne_p']),
         'VA_P2': _nommer(monde, roles.VA, antenne=antenne_p2), 'VA_Q': _nommer(monde, roles.VA, antenne=monde['antenne_q']),
         'VI_NAT': _nommer(monde, roles.VI), 'VI_P': _nommer(monde, roles.VI, coordination=monde['P'])}
    e['antenne_p2'] = antenne_p2
    return e


def _qui(communique):
    return set(Compte.objects.filter(pk__in=list(S.destinataires_ids(communique))).values_list('username', flat=True))


def _noms(equipe, *cles):
    return {equipe[c].username for c in cles}


# ---------------------------------------------------------------- droits de publication

def test_F40_seuls_editeur_et_super_utilisateur_publient(monde, equipe, acteurs_roles):
    assert S.peut_publier(monde['compte']) and S.peut_publier(equipe['ED'])
    for cle in ('PR', 'VN', 'VP_P', 'VA_P', 'AT_P', 'VI_NAT'):
        assert not S.peut_publier(equipe[cle]), cle
        with pytest.raises(PermissionDenied):
            S.publier(equipe[cle], 'Titre', 'Message')
    assert not S.peut_publier(None) and not Communique.objects.filter(user__in=[equipe['PR'], equipe['VN']]).exists()


def test_F40_validation_du_titre_du_message_et_du_ciblage(monde, equipe):
    ed = equipe['ED']
    avant = Communique.objects.count()
    for titre, message in (('', 'm'), ('  ', 'm'), ('t' * 121, 'm'), ('t', ''), ('t', ' '), ('t', 'm' * 5001)):
        with pytest.raises(S.ErreurCommunique):
            S.publier(ed, titre, message)
    with pytest.raises(S.ErreurCommunique):
        S.publier(ed, 'T', 'M', coordination=monde['Q'], antenne=monde['antenne_p'])  # l'antenne n'est pas dans cette coordination
    assert Communique.objects.count() == avant
    c = S.publier(ed, 't' * 120, 'M', antenne=monde['antenne_p'])
    assert c.province_id == monde['P'].pk and c.antenne_id == monde['antenne_p'].pk  # l'antenne pose sa coordination


def test_F40_publication_journalisee_et_auteur(monde, equipe):
    c = S.publier(equipe['ED'], 'Réunion', 'Ce jeudi à 10 h.')
    ligne = JournalAction.objects.get(action=A.CREATION, objet_id=c.pk)
    assert ligne.auteur == equipe['ED'] and not ligne.avant and 'creation' not in ligne.apres and ligne.apres['type'] == 'communique' and ligne.apres['destinataires'] > 0 and ligne.objet_libelle == 'Réunion'
    assert c.auteur == equipe['ED'] and c.publie_le is not None and c.titre == 'Réunion'


# ---------------------------------------------------------------- destinataires selon le ciblage

def test_F40_national_tous_les_roles_de_terrain_sauf_vi_ed_et_auteur(monde, equipe):
    c = S.publier(equipe['ED'], 'National', 'Pour tous')
    attendu = _noms(equipe, 'PR', 'VN', 'VP_P', 'VP_Q', 'VA_P', 'AT_P', 'VA_P2', 'VA_Q') | {monde['compte'].username}
    assert _qui(c) == attendu  # le super-utilisateur aussi ; ni VI, ni ED (auteur)
    assert equipe['VI_NAT'].username not in _qui(c) and equipe['ED'].username not in _qui(c)


def test_F40_super_utilisateur_auteur_n_est_pas_son_propre_destinataire(monde, equipe):
    c = S.publier(monde['compte'], 'Du SU', 'Message')
    assert monde['compte'].username not in _qui(c) and equipe['PR'].username in _qui(c)


def test_F40_coordination_son_perimetre_et_les_niveaux_au_dessus(monde, equipe):
    c = S.publier(equipe['ED'], 'Coordination P', 'Message', coordination=monde['P'])
    assert _qui(c) == _noms(equipe, 'PR', 'VN', 'VP_P', 'VA_P', 'AT_P', 'VA_P2') | {monde['compte'].username}
    assert not _qui(c) & _noms(equipe, 'VP_Q', 'VA_Q')


def test_F40_antenne_son_perimetre_et_les_niveaux_au_dessus(monde, equipe):
    c = S.publier(equipe['ED'], 'Antenne P', 'Message', antenne=monde['antenne_p'])
    assert _qui(c) == _noms(equipe, 'PR', 'VN', 'VP_P', 'VA_P', 'AT_P') | {monde['compte'].username}
    assert not _qui(c) & _noms(equipe, 'VA_P2', 'VP_Q', 'VA_Q')  # ni l'autre antenne, ni l'autre coordination


def test_F40_comptes_inactifs_et_terminaisons_exclus(monde, equipe):
    Compte.objects.filter(pk=equipe['VA_P'].pk).update(is_active=False)
    c = S.publier(equipe['ED'], 'T', 'M')
    assert equipe['VA_P'].username not in _qui(c)


def test_F40_chaque_destinataire_recoit_une_notification(monde, equipe):
    c = S.publier(equipe['ED'], 'Alerte', 'Texte du communiqué', coordination=monde['P'])
    recus = set(Notification.objects.filter(titre='Communiqué : Alerte').values_list('user__username', flat=True))
    assert recus == _qui(c) and len(recus) == Notification.objects.filter(titre='Communiqué : Alerte').count()
    notif = Notification.objects.filter(user=equipe['VA_P']).get()
    assert notif.description == 'Texte du communiqué'
    from compte.services.perimetre import notifications_du_perimetre
    assert notif in notifications_du_perimetre(equipe['VA_P'])


# ---------------------------------------------------------------- visibilité

def test_F40_visibilite_par_role_et_perimetre(monde, equipe):
    ed = equipe['ED']
    Communique.objects.exclude(user=ed).delete()  # le jeu d'essai crée un communiqué national : isolé ici
    nat = S.publier(ed, 'Nat', 'm')
    coord_p = S.publier(ed, 'CoordP', 'm', coordination=monde['P'])
    ant_p = S.publier(ed, 'AntP', 'm', antenne=monde['antenne_p'])
    ant_p2 = S.publier(ed, 'AntP2', 'm', antenne=equipe['antenne_p2'])
    coord_q = S.publier(ed, 'CoordQ', 'm', coordination=monde['Q'])
    ids = lambda u: set(S.communiques_visibles(u).values_list('pk', flat=True))  # noqa: E731
    tout = {nat.pk, coord_p.pk, ant_p.pk, ant_p2.pk, coord_q.pk}
    assert ids(equipe['PR']) == ids(equipe['VN']) == ids(ed) == ids(monde['compte']) == tout
    assert ids(equipe['VI_NAT']) == tout  # visiteur national : lecture de tout
    assert ids(equipe['VP_P']) == {nat.pk, coord_p.pk, ant_p.pk, ant_p2.pk}
    assert ids(equipe['VA_P']) == ids(equipe['AT_P']) == {nat.pk, coord_p.pk, ant_p.pk}
    assert ids(equipe['VA_P2']) == {nat.pk, coord_p.pk, ant_p2.pk}
    assert ids(equipe['VA_Q']) == {nat.pk, coord_q.pk}
    assert ids(equipe['VI_P']) == {nat.pk, coord_p.pk, ant_p.pk, ant_p2.pk}  # visiteur de coordination
    assert ids(_compte('sans-role')) == {nat.pk}  # compte sans nomination : le national
    assert not S.communiques_visibles(None).exists()


def test_F40_un_communique_futur_n_est_pas_visible(monde, equipe):
    c = S.publier(equipe['ED'], 'Futur', 'm')
    Communique.objects.filter(pk=c.pk).update(publie_le=timezone.now() + timedelta(days=1))
    assert c.pk not in set(S.communiques_visibles(equipe['PR']).values_list('pk', flat=True))


# ---------------------------------------------------------------- lu par compte et compteur

def test_F40_lu_par_compte_pas_pour_tous(monde, equipe):
    c = S.publier(equipe['ED'], 'Commun', 'm')
    a, b = equipe['VA_P'], equipe['AT_P']
    assert S.nombre_non_lus(a) == S.nombre_non_lus(b) == 1
    assert S.marquer_lu(a, c) is True and S.marquer_lu(a, c) is False  # idempotent
    assert S.nombre_non_lus(a) == 0 and S.nombre_non_lus(b) == 1  # un « lu » commun serait faux
    assert LectureCommunique.objects.filter(communique=c).count() == 1


def test_F40_compteur_ignore_ses_propres_communiques_les_anciens_et_les_invisibles(monde, equipe):
    ed = equipe['ED']
    propre = S.publier(ed, 'Du ED', 'm')
    assert S.nombre_non_lus(ed) == 0  # l'auteur ne compte pas ses propres communiqués
    avant = S.nombre_non_lus(equipe['VA_P'])
    S.publier(ed, 'Pour Q', 'm', coordination=monde['Q'])
    assert S.nombre_non_lus(equipe['VA_P']) == avant  # hors périmètre : le compteur ne bouge pas
    ancien = Communique.objects.create(user=ed, titre='Ancien', message='m', publie_le=timezone.now() - timedelta(days=400))
    Compte.objects.filter(pk=equipe['VA_P'].pk).update(date_joined=timezone.now() + timedelta(hours=1))  # compte créé APRÈS ces publications
    assert S.nombre_non_lus(Compte.objects.get(pk=equipe['VA_P'].pk)) == 0  # publié avant la création du compte : pas « non lu »
    assert S.nombre_non_lus(None) == 0 and propre.pk and ancien.pk


def test_F40_marquer_lu_refuse_hors_perimetre(monde, equipe):
    c = S.publier(equipe['ED'], 'Pour Q', 'm', coordination=monde['Q'])
    with pytest.raises(Communique.DoesNotExist):
        S.marquer_lu(equipe['VA_P'], c)
    assert not LectureCommunique.objects.exists()


def test_F40_liste_filtres_pagination_et_drapeau_lu(monde, equipe):
    ed, va = equipe['ED'], equipe['VA_P']
    Communique.objects.exclude(user=ed).delete()
    cs = [S.publier(ed, f'Communiqué {i}', f'texte {i}') for i in range(25)]
    S.marquer_lu(va, cs[0])
    page = S.lister_communiques(va, {}, 1)
    assert len(page) == 20 and page.paginator.count == 25 and [c.titre for c in page][0] == 'Communiqué 24'
    assert S.lister_communiques(va, {}, 2).has_previous() and len(S.lister_communiques(va, {}, 'x')) == 20 and len(S.lister_communiques(va, {}, 99)) == 5
    non_lus = S.lister_communiques(va, {'etat': 'non_lus'}, 1)
    assert non_lus.paginator.count == 24 and all(not c.lu for c in non_lus)
    assert [c.lu for c in S.lister_communiques(va, {'q': 'Communiqué 0'}, 1)] == [True]
    assert S.lister_communiques(va, {'q': 'texte 7'}, 1).paginator.count == 1
    assert S.lister_communiques(va, {'coordination': '99999999999999999999', 'antenne': 'x'}, 1).paginator.count == 25  # entiers invalides ignorés
    assert S.lister_communiques(ed, {}, 1)[0].lu is True  # les siens sont « lus »


# ---------------------------------------------------------------- vues

def test_F40_vue_publier_403_csrf_422_et_succes(client, monde, equipe):
    url = reverse('message')
    client.force_login(equipe['PR'])
    assert client.get(url).status_code == 403 and client.post(url, {'titre': 't', 'message': 'm'}).status_code == 403
    client.force_login(equipe['ED'])
    assert client.get(url).status_code == 200
    protege = Client(enforce_csrf_checks=True)
    protege.force_login(equipe['ED'])
    assert protege.post(url, {'titre': 't', 'message': 'm'}).status_code == 403 and not Communique.objects.filter(titre='t').exists()
    assert client.post(url, {'titre': '', 'message': 'm'}, HTTP_HX_REQUEST='true').status_code == 422
    assert client.post(url, {'titre': 't', 'message': 'm', 'coordination': '999999'}).status_code == 422
    ok = client.post(url, {'titre': 'Titre', 'message': 'Message', 'coordination': monde['P'].pk}, HTTP_HX_REQUEST='true')
    assert ok.status_code == 204 and 'communiquesMaj' in ok['HX-Trigger'] and 'toast' in ok['HX-Trigger']
    assert Communique.objects.get(titre='Titre').province_id == monde['P'].pk
    assert client.post(url, {'titre': 'Autre', 'message': 'M'}).status_code == 302  # page complète


def test_F40_liste_lecture_get_sans_effet_page_et_fragment(client, monde, equipe):
    c = S.publier(equipe['ED'], 'Lisible', 'm')
    client.force_login(equipe['VA_P'])
    page = client.get(reverse('list-message'))
    assert page.status_code == 200 and '<html' in page.content.decode() and page.context['nb_non_lus'] == 1
    fragment = client.get(reverse('list-message'), {'etat': 'non_lus'}, HTTP_HX_REQUEST='true')
    assert fragment.status_code == 200 and '<html' not in fragment.content.decode() and 'Lisible' in fragment.content.decode()
    avant = (LectureCommunique.objects.count(), JournalAction.objects.count())
    lecture = client.get(reverse('communique', kwargs={'id': c.pk}))
    assert lecture.status_code == 200 and lecture.context['lu'] is False and (LectureCommunique.objects.count(), JournalAction.objects.count()) == avant


def test_F40_lecture_404_hors_perimetre(client, monde, equipe):
    ed = equipe['ED']
    prive = S.publier(ed, 'Pour Q', 'm', coordination=monde['Q'])
    ouvert = S.publier(ed, 'Pour tous', 'm')
    client.force_login(equipe['VA_P'])
    assert client.get(reverse('communique', kwargs={'id': prive.pk})).status_code == 404
    assert client.post(reverse('communique-lu', kwargs={'id': prive.pk})).status_code == 404
    lecture = client.get(reverse('communique', kwargs={'id': ouvert.pk}))
    assert lecture.status_code == 200 and 'reactions' not in lecture.context


def test_F40_vue_lu_post_csrf_htmx_et_par_compte(client, monde, equipe):
    c = S.publier(equipe['ED'], 'À lire', 'm')
    url = reverse('communique-lu', kwargs={'id': c.pk})
    client.force_login(equipe['VA_P'])
    assert client.get(url).status_code == 405
    protege = Client(enforce_csrf_checks=True)
    protege.force_login(equipe['VA_P'])
    assert protege.post(url).status_code == 403 and not LectureCommunique.objects.exists()
    ok = client.post(url, HTTP_HX_REQUEST='true')
    assert ok.status_code == 204 and 'communiquesMaj' in ok['HX-Trigger']
    assert S.nombre_non_lus(equipe['VA_P']) == 0 and S.nombre_non_lus(equipe['AT_P']) == 1
    assert client.post(url).status_code == 302  # page complète : retour à la lecture


def test_F40_compteur_fragment_no_store(client, monde, equipe):
    S.publier(equipe['ED'], 'Badge', 'm')
    url = reverse('communique-compteur')
    assert Client().get(url).status_code == 302  # connexion exigée
    client.force_login(equipe['VA_P'])
    reponse = client.get(url, HTTP_HX_REQUEST='true')
    assert reponse.status_code == 200 and reponse.context['nb_non_lus'] == 1 and 'no-store' in reponse['Cache-Control']
    assert client.post(url).status_code == 405


# ---------------------------------------------------------------- écarts : ciblage explicite, règle unique du « non lu »

def test_F40_cible_sans_choix_refusee_jamais_nationale(monde, equipe):
    ed, avant = equipe['ED'], Communique.objects.count()
    for cible, champ in (('antenne', 'antenne'), ('coordination', 'coordination')):
        with pytest.raises(S.ErreurCommunique) as e:
            S.publier(ed, 'T', 'M', cible=cible)
        assert e.value.champ == champ
    with pytest.raises(S.ErreurCommunique):
        S.publier(ed, 'T', 'M', cible='planete')
    with pytest.raises(S.ErreurCommunique):
        S.publier(ed, 'T', 'M', coordination=monde['P'], cible='antenne')  # une coordination ne remplace pas l'antenne
    assert Communique.objects.count() == avant
    national = S.publier(ed, 'T', 'M', coordination=monde['P'], antenne=monde['antenne_p'], cible='national')
    assert national.province_id is None and national.antenne_id is None
    coord = S.publier(ed, 'T', 'M', coordination=monde['P'], antenne=monde['antenne_p'], cible='coordination')
    assert coord.province_id == monde['P'].pk and coord.antenne_id is None


def test_F40_vue_cible_sans_choix_422_message_sous_le_champ(client, monde, equipe):
    client.force_login(equipe['ED'])
    avant = Communique.objects.count()
    for cible, champ, texte in (('antenne', 'antenne', "Choisissez l'antenne qui reçoit le communiqué."),
                                ('coordination', 'coordination', 'Choisissez la coordination qui reçoit le communiqué.')):
        r = client.post(reverse('message'), {'titre': 'T', 'message': 'M', 'cible': cible}, HTTP_HX_REQUEST='true')
        assert r.status_code == 422 and r.context['erreurs'] == {champ: texte} and r.context['valeurs']['cible'] == cible
    r = client.post(reverse('message'), {'titre': '', 'message': 'M', 'cible': 'national'}, HTTP_HX_REQUEST='true')
    assert r.status_code == 422 and list(r.context['erreurs']) == ['titre']
    assert Communique.objects.count() == avant
    ok = client.post(reverse('message'), {'titre': 'T', 'message': 'M', 'cible': 'antenne', 'antenne': monde['antenne_p'].pk}, HTTP_HX_REQUEST='true')
    assert ok.status_code == 204 and Communique.objects.get(titre='T').antenne_id == monde['antenne_p'].pk


def test_F40_non_lu_meme_regle_liste_filtre_et_compteur(client, monde, equipe):
    va = equipe['VA_P']
    ancien = S.publier(equipe['ED'], 'Avant le compte', 'm')
    recent = S.publier(equipe['ED'], 'Après le compte', 'm')
    Communique.objects.filter(pk=ancien.pk).update(publie_le=va.date_joined - timedelta(days=1))
    va = Compte.objects.get(pk=va.pk)
    page = S.lister_communiques(va, {}, 1)
    lus = {c.pk: c.lu for c in page}
    assert lus[ancien.pk] is True and lus[recent.pk] is False
    non_lus = S.lister_communiques(va, {'etat': 'non_lus'}, 1)
    assert [c.pk for c in non_lus] == [recent.pk] and S.nombre_non_lus(va) == 1  # liste, filtre et compteur d'accord
    assert S.nombres_liste(va)['non_lus'] == 1 and S.nombres_liste(va, {'q': 'Avant'}) == {'tous': 1, 'non_lus': 0}
    ancien.refresh_from_db()
    assert S.est_lu(va, ancien) and not S.est_lu(va, recent)
    assert S.suivant_non_lu(va).pk == recent.pk and S.suivant_non_lu(va, apres=recent) is None
    client.force_login(va)
    assert client.get(reverse('communique', kwargs={'id': ancien.pk})).context['lu'] is True
    lecture = client.get(reverse('communique', kwargs={'id': recent.pk}))
    assert lecture.context['lu'] is False and lecture.context['suivant'] is None


def test_F40_titre_de_repli_pour_ancien_communique_sans_titre(monde, equipe):
    assert S.titre_affiche(Communique(titre='', message='x' * 100)) == 'x' * 80
    assert S.titre_affiche(Communique(titre='Un titre', message='m')) == 'Un titre'
